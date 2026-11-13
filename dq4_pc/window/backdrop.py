"""Blurred scenery behind the casino and the bestiary: these engine parts (slot machine, poker, monster book) draw a picture made for the portrait screen of the phone on a
black background; the port shows the blurred scenery behind it instead of black.

How: after each frame of a town or of the world map, the scene (without the interface) is copied at a quarter of the window size (a blit, cheap); the last copy is the place the player has just
left. On the first frame of a mini-game it is blurred once (Gaussian, on the CPU) and drawn over the whole window in place of the black, under the mini-game's picture, the windows and the fades.
Only when the background of the screen is black (clear color black, no `BackColor` gradient). No copy yet (a savestate loaded straight into the casino): black, as before."""
import ctypes
import numpy as np
import pyglet
from pyglet import gl
from PIL import Image, ImageFilter
from dq4_pc.core import engine as ENGINE
from dq4_pc.window.constants import TITLE_MAP
from dq4_pc.render.screen_blur import ScreenBlur

BACKDROP_REDUCTION = 4          # the copy: a quarter of the window in width and in height
BACKDROP_BLUR = 6.0             # Gaussian radius, in pixels of the copy (24 pixels at 1080p)
BACKDROP_LUM = 0.75             # the blurred scenery slightly darkened: the mini-game's picture and its windows stay in front


def _gen(f):
    n = gl.GLuint(); f(1, ctypes.byref(n)); return n.value


def black_background(background, gradient):
    """The screen's background is black: clear color (r, g, b) black and no gradient."""
    return not gradient and max(float(c) for c in background[:3]) < 0.02


def blurred(rgb, radius=BACKDROP_BLUR):
    """Copy (h x w x 3, uint8) -> blurred copy, same size."""
    return np.asarray(Image.fromarray(np.ascontiguousarray(rgb)).filter(ImageFilter.GaussianBlur(radius)))


class BackdropMixin:
    backdrop_fbo = None; backdrop_copy = None; backdrop_size = None; backdrop_serial = 0; backdrop_tex = None; backdrop_built = 0; backdrop_vl = None; screen_blur = None

    def _blur_window(self):
        """What has just been drawn in the window, blurred in place (the port's own screens are drawn on top: "Settings" menu, history, Sauvegardes and language screens)."""
        if self.screen_blur is None: self.screen_blur = ScreenBlur()
        self.screen_blur.apply(*self.get_framebuffer_size())

    def _backdrop_keep(self, e):
        """The scene of a town or of the world map has just been drawn (interface not yet): reduced copy, kept for the mini-games (not the title screen, not a mini-game itself)."""
        if e.part not in (ENGINE.PART_TOWN, ENGINE.PART_FIELD) or (e.part == ENGINE.PART_TOWN and e.game_map == TITLE_MAP): return
        W, H = self.get_framebuffer_size(); w, h = max(1, W // BACKDROP_REDUCTION), max(1, H // BACKDROP_REDUCTION)
        if W < 2 or H < 2: return
        try:
            if self.backdrop_size != (w, h):
                if self.backdrop_copy is not None: self.backdrop_copy.delete()
                if self.backdrop_fbo is not None: gl.glDeleteFramebuffers(1, ctypes.byref(gl.GLuint(self.backdrop_fbo)))
                t = pyglet.image.Texture.create(w, h, internalformat=gl.GL_RGBA8)
                fbo = _gen(gl.glGenFramebuffers); gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, fbo)
                gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, t.target, t.id, 0)
                self.backdrop_copy, self.backdrop_fbo, self.backdrop_size = t, fbo, (w, h)
            gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, 0); gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, self.backdrop_fbo)
            gl.glBlitFramebuffer(0, 0, W, H, 0, 0, w, h, gl.GL_COLOR_BUFFER_BIT, gl.GL_LINEAR)
            self.backdrop_serial += 1
        except Exception: self.backdrop_serial = 0                  # (no blit on this machine: black behind the mini-games, as before)
        finally:
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0); gl.glViewport(0, 0, W, H)

    def _blur_edges(self):
        """"Edge blur" setting: the edges of the game picture blurred, like the vignette darkens them (the scene has just been drawn, interface not yet)."""
        v = float(self.reg['edge_blur'])
        if v <= 0.005: return
        if self.screen_blur is None: self.screen_blur = ScreenBlur()
        self.screen_blur.apply(*self.get_framebuffer_size(), edges=v)

    def _backdrop_forget(self):
        """Savestate loaded: the copy belonged to the game before the load."""
        self.backdrop_serial = 0

    def _backdrop_texture(self):
        """The blurred scenery (texture), built once per copy; None if there is no copy."""
        if not self.backdrop_serial or self.backdrop_fbo is None: return None
        if self.backdrop_built != self.backdrop_serial or self.backdrop_tex is None:
            w, h = self.backdrop_size; buf = (ctypes.c_ubyte * (w * h * 4))()
            drawn, read = gl.GLint(), gl.GLint()                       # (called while the scene is being drawn: the off-screen target stays bound afterwards)
            gl.glGetIntegerv(gl.GL_DRAW_FRAMEBUFFER_BINDING, ctypes.byref(drawn)); gl.glGetIntegerv(gl.GL_READ_FRAMEBUFFER_BINDING, ctypes.byref(read))
            gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, self.backdrop_fbo); gl.glReadPixels(0, 0, w, h, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, buf)
            gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, read.value); gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, drawn.value)
            rgb = blurred(np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, :3])
            if self.backdrop_tex is not None: self.backdrop_tex.delete()
            t = pyglet.image.ImageData(w, h, 'RGB', rgb.tobytes()).get_texture()
            gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            self.backdrop_tex, self.backdrop_built = t, self.backdrop_serial
        return self.backdrop_tex

    def _draw_backdrop(self, e, background, gradient):
        """Mini-game on a black background: the blurred scenery over the whole drawing area, before the mini-game's picture (depth neither read nor written)."""
        if e.part not in ENGINE.MINIGAME_PARTS or not black_background(background, gradient): return
        t = self._backdrop_texture()
        if t is None: return
        u, v = t.tex_coords[3], t.tex_coords[7]                      # (texture rounded up to a power of 2 on some drivers: the picture's part only)
        prog = self.program_effect
        if self.backdrop_vl is None:
            self.backdrop_vl = prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', [-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]), tex_coords=('f', [0] * 12), colors=('f', [1.0] * 24))
        self.backdrop_vl.tex_coords[:] = [0, 0, u, 0, u, v, 0, 0, u, v, 0, v]
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glDepthMask(gl.GL_FALSE); gl.glDisable(gl.GL_BLEND)
        prog.use(); prog['lum'] = 1.0; prog['blur'] = 0.0
        self.backdrop_vl.colors[:] = [BACKDROP_LUM, BACKDROP_LUM, BACKDROP_LUM, 1.0] * 6
        gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(t.target, t.id); self.backdrop_vl.draw(gl.GL_TRIANGLES)
        prog.stop()
        gl.glDepthMask(gl.GL_TRUE); gl.glEnable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
