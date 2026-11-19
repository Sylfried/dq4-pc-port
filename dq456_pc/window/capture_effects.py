"""Drawing of the screen effects of the `Capture` class of the Unity layer (packet 34: travel, lamp, Riremito, DQ VI well and Pegasus; see render/capture_effects.py for the rules): capture of the game screen, two half-resolution blur textures
alternating (the persistence: at each step of the effect, the state of the previous frame is redrawn into it), then drawing of the effect mesh in place of the scene, on a black background. The interface (messages,
game windows) and the fade planes remain drawn on top, as Unity's interface camera does (assumed: the exact content of this camera during the effect is not read)."""
import ctypes
import pyglet
from pyglet import gl
from dq456_pc.render import capture_effects as EF
from dq456_pc.render.ido_effect import IdoEffect
from dq456_pc.render.pegasus_effect import PegasusEffect
from dq456_pc.render.lamp_effect import LampEffect
from dq456_pc.render.riremito_effect import RiremitoEffect
from dq456_pc.render.tabi_effect import TabiEffect


def _gen(f):
    n = gl.GLuint(); f(1, ctypes.byref(n)); return n.value


class CaptureEffectsMixin:
    capture_ref = None; capture_ready = False; capture_sim = None; capture_rt = None; capture_fbo = None; capture_vl = None; capture_size = None      # current effect (dict of State.screen_effect), capture taken, simulation, blur textures and buffers, vertex lists

    def _capture_state(self, e):
        """The Capture effect in progress (dict of State.screen_effect) or None; a new effect resets the capture to be done (the first frame is drawn normally then copied, see _capture_grab)."""
        ef = getattr(e, 'screen_effect', None)
        if ef is not self.capture_ref: self.capture_ref = ef; self.capture_ready = False; self.capture_sim = None
        return ef

    def _capture_new_effect(self, ef):
        if ef['kind'] == 'tabi': return TabiEffect(ef['inverse'])
        if ef['kind'] == 'lamp': return LampEffect(ef['morning'])
        if ef['kind'] == 'ido': return IdoEffect(ef['inverse'], self.width / max(1, self.height))
        if ef['kind'] == 'pegasus': return PegasusEffect(ef['inverse'], self.width / max(1, self.height))
        return RiremitoEffect()

    def _capture_grab(self, ef):
        """The game scene has just been drawn (without interface): we copy it into the capture texture, create the effect and the blur targets (black at the start)."""
        self._clone_screen(battle=False)
        w, h = self.get_framebuffer_size(); w2, h2 = max(1, w // 2), max(1, h // 2)
        if self.capture_rt is None or self.capture_size != (w2, h2):
            for t in self.capture_rt or (): t.delete()
            for f in self.capture_fbo or (): gl.glDeleteFramebuffers(1, ctypes.byref(gl.GLuint(f)))
            self.capture_rt = []; self.capture_fbo = []
            for _ in range(2):
                t = pyglet.image.Texture.create(w2, h2, internalformat=gl.GL_RGBA8); gl.glBindTexture(t.target, t.id)
                gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
                gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
                fbo = _gen(gl.glGenFramebuffers); gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, fbo)
                gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, t.target, t.id, 0)
                self.capture_rt.append(t); self.capture_fbo.append(fbo)
            self.capture_size = (w2, h2)
        for fbo in self.capture_fbo:                              # black blur textures (the game does not clear them: initial content not established, black assumed)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, fbo); gl.glClearColor(0.0, 0.0, 0.0, 1.0); gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0); gl.glViewport(0, 0, w, h)
        self.capture_vl = {}
        self.capture_sim = self._capture_new_effect(ef); self.capture_sim.on_blur = self._capture_blur_pass
        self.capture_ready = True

    def _capture_advance(self, ef):
        """Advances the effect up to the MoveNext call that matches the engine frame (several steps per frame when "Transition speed" shortens the effect)."""
        sim = self.capture_sim; target = EF.calls_made(ef['n'], ef['duration'], ef['frames'])
        while sim.frames < target and not sim.finished: sim.stage()
        return sim

    def _capture_paint(self, sim, blur):
        """The effect's drawings in the current target: the background reads the blur texture `blur` (None: black, nothing to draw), the capture reads the copy of the game screen."""
        prog = self.program_effect; prog.use(); prog['lum'] = 1.0; prog['blur'] = 0.0
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glActiveTexture(gl.GL_TEXTURE0)
        for k, (name_str, pos, uv, rgba) in enumerate(sim.drawings()):
            if name_str == 'blur':
                if blur is None: continue
                tex = self.capture_rt[blur]; gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ZERO)               # Custom/CaptureBlur: texture x color replaces the screen
            elif name_str == 'trail':                                                              # DQ VI Custom/CaptureBlur2: the effect's previous frame over the rest (before any pass: the game's first render, the capture)
                tex = self.capture_rt[blur] if blur is not None else self.effect_tex; gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            else:
                tex = self.effect_tex; gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)    # Custom/Capture
            vl = self.capture_vl.get(k)
            if vl is None: vl = self.capture_vl[k] = prog.vertex_list(len(pos), gl.GL_TRIANGLES, position=('f', pos.ravel()), tex_coords=('f', uv.ravel()), colors=('f', rgba.ravel()))
            else:
                vl.position[:] = pos.ravel(); vl.colors[:] = rgba.ravel()
                if name_str == 'capture' and getattr(sim, 'moving_uv', False): vl.tex_coords[:] = uv.ravel()          # (DQ VI well: the texture coordinates move, not the vertices)
            gl.glBindTexture(tex.target, tex.id); vl.draw(gl.GL_TRIANGLES)
        prog.stop()

    def _capture_blur_pass(self, sim, i):
        """Capture.Caputer, blur pass: the state of the previous frame (blurred background + mesh) is redrawn into the half-resolution texture `i`."""
        w, h = self.get_framebuffer_size()
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.capture_fbo[i]); gl.glViewport(0, 0, *self.capture_size)
        gl.glClearColor(0.0, 0.0, 0.0, 1.0); gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        self._capture_paint(sim, sim.blur_read)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0); gl.glViewport(0, 0, w, h)

    def _draw_capture_effect(self, sim):
        """Effect frame: black background, blurred background, mesh; then the fade planes and the interface on top (messages, game windows)."""
        gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear()
        gl.glViewport(0, 0, *self.get_framebuffer_size())
        self._capture_paint(sim, sim.blur_read)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        self._draw_fade(True)
        self._update_message(); self._draw_message(); self._draw_menus(); self._draw_fade()

    def _capture_live(self, sim):
        """An effect that captures the scene at every frame (DQ VI Pegasus): the scene has just been drawn (without interface); it becomes the capture, then the effect is drawn in its place, on black."""
        self._clone_screen(battle=False)
        gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear()
        gl.glViewport(0, 0, *self.get_framebuffer_size())
        self._capture_paint(sim, sim.blur_read)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
