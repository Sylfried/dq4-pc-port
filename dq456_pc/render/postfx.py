"""Off-screen scene rendering then final pass: MSAA antialiasing adjustable on the fly, supersampling, sharpness, colour filter, contrast, brightness; the game's own sepia (DQ V / VI).

The scene (scenery, characters, vignette, background fades) is drawn into an off-screen buffer (multisample renderbuffers) then copied into the window;
the interface (messages, menus, buttons, Esc menu) is then drawn directly into the window: it is neither smoothed nor retouched.
No active setting (MSAA 0, scale 1, sharpness 0, no filter, contrast 0, normal brightness) = no off-screen buffer: the direct drawing of before.
Any creation failure (driver without multisampling...) falls back to direct drawing and says so in the log.
"""
import ctypes, os
import numpy as np
from pyglet import gl
from dq456_pc.render import gl_errors as GE
from pyglet.graphics.shader import Shader, ShaderProgram

VERTEX = '''#version 330 core
in vec2 position; in vec2 tex_coords;
out vec2 v_uv;
void main() { gl_Position = vec4(position, 0.0, 1.0); v_uv = tex_coords; }'''
# Final pass: bilinear reading of the scene (an exact x2 reduction gives the average of 4 pixels), adaptive sharpening (AMD FidelityFX CAS, MIT license: the gain is
# limited where the local contrast is already strong, so no halo), colour filter (3 x 3 matrix, "Filter"), contrast around mid-gray ("Contrast": x1 to x2), brightness = gamma
# curve (black and white unchanged).
FRAG = '''#version 330 core
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D tex; uniform vec2 texel; uniform float sharpness; uniform float gamma; uniform float contrast; uniform float filtered; uniform mat3 cmat; uniform float game_sepia;
vec3 S(vec2 d) { return texture(tex, v_uv + d * texel).rgb; }
void main() {
    vec3 c = S(vec2(0.0));
    if (sharpness > 0.001) {
        vec3 n = S(vec2(0.0, 1.0)), s = S(vec2(0.0, -1.0)), e = S(vec2(1.0, 0.0)), o = S(vec2(-1.0, 0.0));
        vec3 mn = min(c, min(min(n, s), min(e, o))), mx = max(c, max(max(n, s), max(e, o)));
        vec3 amp = sqrt(clamp(min(mn, 1.0 - mx) / max(mx, vec3(1e-4)), 0.0, 1.0));
        vec3 w = amp * (-1.0 / mix(8.0, 5.0, sharpness));
        c = clamp((c + (n + s + e + o) * w) / (1.0 + 4.0 * w), 0.0, 1.0);
    }
    if (game_sepia > 0.5) c = clamp(vec3((c.r + c.g + c.b) * 0.333333343) + vec3(0.109375, -0.0546875, 0.0), 0.0, 1.0);      // the game's own sepia (DQ V / VI Custom/Sepia), before the player's display settings
    if (filtered > 0.5) c = clamp(cmat * c, 0.0, 1.0);
    if (contrast > 0.001) c = clamp((c - 0.5) * (1.0 + contrast) + 0.5, 0.0, 1.0);
    if (abs(gamma - 1.0) > 0.001) c = pow(c, vec3(1.0 / gamma));
    fragColor = vec4(c, 1.0);
}'''

LUMA = (0.299, 0.587, 0.114)


def _saturation(k):
    return tuple(tuple((1.0 - k) * LUMA[j] + (k if i == j else 0.0) for j in range(3)) for i in range(3))


# "Filter" (changes the colours of the game): rows = output red, green, blue as mixes of the input red, green, blue
COLOR_FILTERS = {
    'none': None,
    'sepia': ((0.393, 0.769, 0.189), (0.349, 0.686, 0.168), (0.272, 0.534, 0.131)),
    'gray': (LUMA, LUMA, LUMA),
    'vivid': _saturation(1.4),
    'soft': _saturation(0.6),
    'warm': ((1.08, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.86)),
    'cool': ((0.9, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.1)),
}

SAMPLE_ALPHA_TO_COVERAGE = 0x809E
MAX_SAMPLES = 0x8D57


def _gen(function):
    i = gl.GLuint(0); function(1, ctypes.byref(i)); return i.value


class PostFX:
    def __init__(self, win, log=print):
        self.f = win; self.log = log
        self.ok = True                 # False after a failure: direct drawing for the rest of the session
        self.msaa = 0                  # actual antialiasing (limited by the graphics card)
        self.max_msaa = None
        self.fb = None                 # (width, height) of the created buffers
        self.lookup_key = None                # (size, samples) for which they were created
        self.fbo = self.fbo_res = self.rb_col = self.rb_prof = self.tex = 0
        self.prog = None; self.vl = None
        self.frame_active = False       # the current frame is drawn off-screen
        self.a2c = False               # alpha-to-coverage usable (multisample buffer)
        self.game_sepia = False        # DQ V / VI: the game puts its scene in sepia (engine.State.screen_sepia), set by the window before begin()

    # ---- settings (read every frame: a change in the Esc menu applies immediately)
    def settings(self):
        r = self.f.reg
        return int(r['msaa']), float(r['render_scale']), float(r['sharpness']), float(r['brightness'])

    def requested(self):
        """(requested samples, scale, sharpness, gamma); the scale is only useful below 1 screen pixel per scene pixel."""
        ms, ui_scale, sharp, lum = self.settings()
        return ms, max(1.0, min(2.0, ui_scale)), max(0.0, min(1.0, sharp)), max(0.5, min(1.5, lum))

    def colors(self):
        """(contrast 0 to 1, filter matrix or None): "Contrast" and "Filter"."""
        r = self.f.reg
        try: k = max(0.0, min(1.0, float(r['contrast'])))
        except (KeyError, TypeError, ValueError): k = 0.0
        try: m = COLOR_FILTERS.get(r['color_filter'])
        except KeyError: m = None
        return k, m

    def limit(self):
        if self.max_msaa is None:
            v = (gl.GLint * 1)(); gl.glGetIntegerv(MAX_SAMPLES, v); self.max_msaa = int(v[0])
        return self.max_msaa

    # ---- buffer creation
    def _release(self):
        for name_str, f in (('fbo', gl.glDeleteFramebuffers), ('fbo_res', gl.glDeleteFramebuffers), ('rb_col', gl.glDeleteRenderbuffers), ('rb_prof', gl.glDeleteRenderbuffers)):
            v = getattr(self, name_str)
            if v: f(1, ctypes.byref(gl.GLuint(v))); setattr(self, name_str, 0)
        if self.tex: gl.glDeleteTextures(1, ctypes.byref(gl.GLuint(self.tex))); self.tex = 0
        self.lookup_key = None

    def _create(self, w, h, ms):
        self._release()
        self.fbo = _gen(gl.glGenFramebuffers); self.rb_prof = _gen(gl.glGenRenderbuffers)
        gl.glBindRenderbuffer(gl.GL_RENDERBUFFER, self.rb_prof)
        if ms: gl.glRenderbufferStorageMultisample(gl.GL_RENDERBUFFER, ms, gl.GL_DEPTH_COMPONENT24, w, h)
        else: gl.glRenderbufferStorage(gl.GL_RENDERBUFFER, gl.GL_DEPTH_COMPONENT24, w, h)
        tex = gl.GLuint(0); gl.glGenTextures(1, ctypes.byref(tex)); self.tex = tex.value
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA8, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, None)
        for p, v in ((gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR), (gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR), (gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE), (gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)):
            gl.glTexParameteri(gl.GL_TEXTURE_2D, p, v)
        if ms:      # multisample scene, then copy (resolve) into the texture
            self.rb_col = _gen(gl.glGenRenderbuffers)
            gl.glBindRenderbuffer(gl.GL_RENDERBUFFER, self.rb_col)
            gl.glRenderbufferStorageMultisample(gl.GL_RENDERBUFFER, ms, gl.GL_RGBA8, w, h)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
            gl.glFramebufferRenderbuffer(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_RENDERBUFFER, self.rb_col)
            gl.glFramebufferRenderbuffer(gl.GL_FRAMEBUFFER, gl.GL_DEPTH_ATTACHMENT, gl.GL_RENDERBUFFER, self.rb_prof)
            state = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            self.fbo_res = _gen(gl.glGenFramebuffers)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo_res)
            gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, self.tex, 0)
            state2 = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            if state != gl.GL_FRAMEBUFFER_COMPLETE or state2 != gl.GL_FRAMEBUFFER_COMPLETE: raise RuntimeError('incomplete framebuffer (%#x, %#x)' % (state, state2))
        else:       # without multisampling: drawing directly into the texture
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
            gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, self.tex, 0)
            gl.glFramebufferRenderbuffer(gl.GL_FRAMEBUFFER, gl.GL_DEPTH_ATTACHMENT, gl.GL_RENDERBUFFER, self.rb_prof)
            state = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            if state != gl.GL_FRAMEBUFFER_COMPLETE: raise RuntimeError('incomplete framebuffer (%#x)' % state)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
        self.fb = (w, h); self.lookup_key = (w, h, ms)

    def _render_pass(self):
        if self.prog is None:
            self.prog = ShaderProgram(Shader(VERTEX, 'vertex'), Shader(FRAG, 'fragment'))
            q = np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], np.float32); uv = np.array([0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1], np.float32)
            self.vl = self.prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', q), tex_coords=('f', uv))

    # ---- frame
    def begin(self, background):
        """Starts drawing the scene; returns (width, height) of the drawing area to use for glViewport. Clears with the background color."""
        W, H = self.f.get_framebuffer_size(); self.frame_active = False; self.a2c = False
        if not self.ok or W < 2 or H < 2: return W, H            # (window minimized to the taskbar: empty drawing area, nothing to create; this is not a failure)
        ms, ui_scale, sharp, lum = self.requested()
        k, m = self.colors()
        if ms == 0 and ui_scale <= 1.0 and sharp <= 0.001 and abs(lum - 1.0) <= 0.001 and k <= 0.001 and m is None and not self.game_sepia: return W, H       # nothing to do: direct drawing
        try:
            real = min(ms, self.limit()) if ms else 0
            if real == 1: real = 0
            w, h = int(round(W * ui_scale)), int(round(H * ui_scale))
            if self.lookup_key != (w, h, real):
                GE.clear(); self._create(w, h, real); GE.check('offscreen rendering'); self.msaa = real
                self.log(('Offscreen rendering: %d x %d (x%.2g), antialiasing x%d' % (w, h, ui_scale, real) if real else 'Offscreen rendering: %d x %d (x%.2g), antialiasing off' % (w, h, ui_scale)) + (' (requested x%d)' % ms if real != ms else ''))
            self._render_pass()
        except Exception as ex:
            self.ok = False; self.msaa = 0; gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
            self.log('Offscreen rendering failed (%r): direct drawing, no antialiasing' % (ex,)); return W, H
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
        gl.glViewport(0, 0, *self.fb)
        gl.glClearColor(float(background[0]), float(background[1]), float(background[2]), 1.0); gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        self.frame_active = True; self.a2c = self.msaa > 0 and not os.environ.get('DQ_NO_A2C')       # (test) DQ_NO_A2C=1: cutouts with hard alpha test, as before
        return self.fb

    def end(self):
        """Ends the scene: copies into the window (with the final pass if an effect is set). Restores the state expected by the interface drawing."""
        if not self.frame_active: return
        self.frame_active = False; self.a2c = False
        W, H = self.f.get_framebuffer_size(); ms, ui_scale, sharp, lum = self.requested(); w, h = self.fb
        gl.glDisable(SAMPLE_ALPHA_TO_COVERAGE); gl.glDisable(gl.GL_DEPTH_TEST)
        k, m = self.colors()
        direct = abs(ui_scale - 1.0) < 1e-3 and sharp <= 0.001 and abs(lum - 1.0) <= 0.001 and k <= 0.001 and m is None and not self.game_sepia            # no final pass: plain copy (including the multisample resolve)
        if direct:
            gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, self.fbo); gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, 0)
            gl.glBlitFramebuffer(0, 0, w, h, 0, 0, W, H, gl.GL_COLOR_BUFFER_BIT, gl.GL_NEAREST)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
        else:
            if self.msaa:
                gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, self.fbo); gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, self.fbo_res)
                gl.glBlitFramebuffer(0, 0, w, h, 0, 0, w, h, gl.GL_COLOR_BUFFER_BIT, gl.GL_NEAREST)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
            gl.glViewport(0, 0, W, H); gl.glDisable(gl.GL_BLEND)
            self.prog.use(); self.prog['texel'] = (1.0 / W, 1.0 / H); self.prog['sharpness'] = sharp; self.prog['gamma'] = lum; self.prog['contrast'] = k
            self.prog['filtered'] = 1.0 if m is not None else 0.0; self.prog['game_sepia'] = 1.0 if self.game_sepia else 0.0
            if m is not None: self.prog['cmat'] = tuple(float(m[i][j]) for j in range(3) for i in range(3))          # (column-major, as GLSL reads a mat3)
            gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
            self.vl.draw(gl.GL_TRIANGLES)
            self.prog.stop()
        gl.glViewport(0, 0, W, H); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
