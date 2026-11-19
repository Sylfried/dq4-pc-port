"""Camera motion blur ("Motion blur" setting, 0 % to 100 %).

The scene of the previous frame (with its own blur: trails) is laid over the new one with an opacity that follows how far the camera moved since that frame: still camera, no blur at all (the
characters walking under a still camera leave no trail); a camera that turns, follows the hero, scrolls the world map or moves in battle leaves a short trail. Measured on the camera itself, not on
the picture: the matrix of the previous frame and the current one project the same five points (the middle and four points around it, at mid-depth of the view), the mean shift in pixels is the
motion. The interface is drawn afterwards: never blurred. 0 % (default) = nothing is copied or drawn."""
import numpy as np
import pyglet
from pyglet import gl

MB_MAX = 0.8                    # opacity of the previous frame at 100 % and a fast camera
MB_FULL_PX = 12.0               # camera shift (pixels per frame) at which the blur is full
MB_DECAY = 0.6                  # the measured shift decays by this factor per frame instead of dropping at once: a frame drawn twice or a camera moved at the engine's pace (30 per second) under a
                                # display at 60 does not make the blur flicker
MB_CUT = 0.12                   # a shift larger than this share of the window's width in one frame is a cut (map change, camera jump): no blur, the trail starts again
SAMPLES = np.array([[0.0, 0.0], [0.5, 0.5], [-0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]])
DEPTH = 0.9                     # NDC depth of the measured points (well inside the scene for the town, battle and world map cameras)


def camera_shift(prev, cur, width, height):
    """Mean shift in pixels, between two frames, of the points that the previous camera (`prev`, 4 x 4 matrix, clip = M @ (x, y, z, 1)) showed at SAMPLES; 0 if there is no previous camera or a
    matrix cannot be inverted."""
    if prev is None or cur is None: return 0.0
    try: inv = np.linalg.inv(np.asarray(prev, float))
    except np.linalg.LinAlgError: return 0.0
    pts = np.column_stack([SAMPLES, np.full(len(SAMPLES), DEPTH), np.ones(len(SAMPLES))])
    world = pts @ inv.T; world = world / world[:, 3:4]
    clip = world @ np.asarray(cur, float).T
    w = clip[:, 3:4]
    if np.any(np.abs(w) < 1e-9): return 0.0
    ndc = clip[:, :2] / w
    d = (ndc - SAMPLES) * np.array([width / 2.0, height / 2.0])
    return float(np.mean(np.hypot(d[:, 0], d[:, 1])))


def blur_opacity(setting, shift):
    """Opacity of the previous frame: the setting (0 to 1) times MB_MAX, scaled by the camera's shift (full from MB_FULL_PX pixels)."""
    return max(0.0, min(1.0, setting)) * MB_MAX * min(1.0, max(0.0, shift) / MB_FULL_PX)


class MotionBlurMixin:
    mb_tex = None; mb_prev = None; mb_valid = False; mb_vl = None; mb_frame = None; mb_shift = 0.0

    def _motion_blur(self, M):
        """The scene of this frame has just been drawn into the window (interface not yet): the previous one laid over it according to the camera's motion, then this result kept for the next."""
        v = float(self.reg['motion_blur'])
        W, H = self.get_framebuffer_size()
        if v <= 0.005 or W < 2 or H < 2: self.mb_prev = None; self.mb_valid = False; return
        frame = getattr(self, '_drawing_count', 0)
        if self.mb_frame is None or frame != self.mb_frame + 1: self.mb_valid = False; self.mb_prev = None          # (a frame drawn without scene in between: black screen, effect, title)
        self.mb_frame = frame
        shift = camera_shift(self.mb_prev, M, W, H); self.mb_prev = None if M is None else np.array(M, float)
        if shift > MB_CUT * W or not self.mb_valid: self.mb_valid = False; self.mb_shift = 0.0
        else: self.mb_shift = max(shift, self.mb_shift * MB_DECAY)
        a = blur_opacity(v, self.mb_shift)
        try:
            if self.mb_tex is None or (self.mb_tex.width, self.mb_tex.height) != (W, H):
                if self.mb_tex is not None: self.mb_tex.delete()
                self.mb_tex = pyglet.image.Texture.create(W, H, internalformat=gl.GL_RGBA8); self.mb_valid = False
                gl.glBindTexture(self.mb_tex.target, self.mb_tex.id)
                for p_, v_ in ((gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR), (gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR), (gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE), (gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)):
                    gl.glTexParameteri(self.mb_tex.target, p_, v_)
            t = self.mb_tex
            if self.mb_valid and a > 0.004:
                u, vv = t.tex_coords[3], t.tex_coords[7]
                prog = self.program_effect
                if self.mb_vl is None:
                    self.mb_vl = prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', [-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]), tex_coords=('f', [0] * 12), colors=('f', [1.0] * 24))
                self.mb_vl.tex_coords[:] = [0, 0, u, 0, u, vv, 0, 0, u, vv, 0, vv]; self.mb_vl.colors[:] = [1.0, 1.0, 1.0, a] * 6
                gl.glViewport(0, 0, W, H); gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
                prog.use(); prog['lum'] = 1.0; prog['blur'] = 0.0
                gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(t.target, t.id); self.mb_vl.draw(gl.GL_TRIANGLES)
                prog.stop()
            gl.glBindTexture(t.target, t.id); gl.glCopyTexSubImage2D(t.target, 0, 0, 0, 0, 0, W, H); self.mb_valid = True
        except Exception as ex:
            self.reg['motion_blur'] = 0.0; self.mb_valid = False
            print('Motion blur unavailable (%r): setting put back to 0' % (ex,), flush=True)
