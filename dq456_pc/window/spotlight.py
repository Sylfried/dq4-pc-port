"""DQ V / VI Spotlight over the town scene (render/spotlight.py for the geometry): the side color outside the lit square, then the square's two passes with the disc texture; DQ VI's mask."""
import pyglet
from pyglet import gl
from dq456_pc.render import spotlight as SP
from dq456_pc.window.helpers import portrait_base_height


class SpotlightMixin:
    _spot_gl = None                       # {texture name: (texture of the Pre pass: white, alpha 1 - disc; of the Post pass: white, alpha = disc)}
    _mask_gl = None                       # DQ VI mask: its square's texture (etc/ccmsk mirrored into four quarters)

    def _spot_textures(self, name):
        if self._spot_gl is None: self._spot_gl = {}
        t = self._spot_gl.get(name)
        if t is None:
            arr = self.data.texture(name)
            if arr is None: return None
            pre = arr.copy(); pre[..., :3] = 255; pre[..., 3] = 255 - arr[..., 3]
            post = arr.copy(); post[..., :3] = 255
            t = (self._tex(pre, False), self._tex(post, False))
            for x in t:
                gl.glBindTexture(x.target, x.id)
                gl.glTexParameteri(x.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(x.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            self._spot_gl[name] = t
        return t

    def _draw_spotlight(self, e, M, aspect):
        """Over the scene, under the interface (Overlay-50 and -49 of the scene camera)."""
        sp = getattr(e, 'spotlight', None)
        if not sp or not sp['visible'] or M is None: return
        tex = self._spot_textures(SP.texture_name(sp['torch']))
        sq = SP.square(sp['pos'], sp['size'], M, self.width, self.height, portrait_base_height(aspect))
        if tex is None or sq is None: return
        (cx, cy), h = sq
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        side, light = sp['side'], sp['light']
        def rgb(c): return tuple(max(0, min(255, int(round(v * 255)))) for v in c[:3])
        def alpha(c): return max(0, min(255, int(round(c[3] * 255))))
        batch = pyglet.graphics.Batch(); keep = []
        for x, y, w, hh in SP.side_rects((cx, cy), h, self.width, self.height):
            r = pyglet.shapes.Rectangle(x, y, w, hh, color=rgb(side), batch=batch); r.opacity = alpha(side); keep.append(r)
        batch.draw()
        for t, c in ((tex[0], side), (tex[1], light)):
            s = pyglet.sprite.Sprite(t, cx - h, cy - h); s.scale_x = 2 * h / t.width; s.scale_y = 2 * h / t.height
            s.color = rgb(c); s.opacity = alpha(c); s.draw(); s.delete()

    def _draw_screen_mask(self, e, aspect):
        """DQ VI mask (packet 34, effect 11): black around the square, the square's picture over the scene (Custom/ScreenMask: alpha blended)."""
        if not getattr(e, 'screen_mask', False): return
        if self._mask_gl is None:
            arr = self.data.texture('ccmsk')
            if arr is None: return
            t = self._tex(SP.mask_picture(arr), False)
            gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            self._mask_gl = t
        t = self._mask_gl; (cx, cy), h = SP.mask_square(self.width, self.height, portrait_base_height(aspect))
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        batch = pyglet.graphics.Batch(); keep = [pyglet.shapes.Rectangle(x, y, w, hh, color=(0, 0, 0), batch=batch) for x, y, w, hh in SP.side_rects((cx, cy), h, self.width, self.height)]
        batch.draw(); del keep
        s = pyglet.sprite.Sprite(t, cx - h, cy - h); s.scale_x = 2 * h / t.width; s.scale_y = 2 * h / t.height; s.draw(); s.delete()
