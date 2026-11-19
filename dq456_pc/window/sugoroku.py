"""Dragon Quest V's T'n'T board: the direction arrows of the Make_Sugoroku_Arrow window, lying on the board (core/sugoroku.py)."""
import numpy as np
from pyglet import gl

from dq456_pc import games as GM
from dq456_pc.core import sugoroku as SG
from dq456_pc.menus import sheets as SH


class SugorokuMixin:
    """The arrows are drawn in the scene, after the board's squares and before the characters."""

    def _sugoroku_arrows(self, e):
        """[(position, turn, frame)] of the arrows shown (DQ V only)."""
        if GM.profile().key != 'dq5': return []
        ui = getattr(self.engine, 'ui', None)
        if ui is None: return []
        out = []
        for f in ui.f.values():
            if f.get('type') == SG.ARROW_TYPE and not f.get('closed'): out += SG.shown(f)
        return out

    def _sugoroku_arrow_tex(self, frame):
        """Texture of the arrow's icon `frame` (MenuTexture sheet, PartsInfo ARROW_PARTS)."""
        cache = self.__dict__.setdefault('_sg_tex', {})
        if frame in cache: return cache[frame]
        t = None
        try:
            info = self.ui_render.ml.info[SG.ARROW_PARTS] if getattr(self, 'ui_render', None) is not None else None
            if info is not None:
                x, y, px = SG.icon_rect(info, frame)
                sheet = SH.rgba(self.args.cache, 'ui_MenuTexture.png')
                t = self._tex(np.ascontiguousarray(sheet[y:y + px, x:x + px]), False, 0)
                gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        except Exception as ex:
            print('T\'n\'T arrow icon not loaded:', ex, flush=True)
        cache[frame] = t
        return t

    def _paint_sugoroku_arrows(self, e):
        arrows = self._sugoroku_arrows(e)
        if not arrows: return
        vls = self.__dict__.setdefault('_sg_vl', {})
        self.prog['cutoff'] = 0.05; self.prog['crisp'] = 1.0; self.prog['tsize'] = (32.0, 32.0); gl.glDisable(gl.GL_CULL_FACE); self._linked_domain = None
        for k, (pos, turn, frame) in enumerate(arrows):
            tex = self._sugoroku_arrow_tex(frame)
            if tex is None: continue
            a, b, c, d = SG.corners(pos, turn)
            q = np.array([a, b, c, a, c, d], np.float32).ravel().tolist()
            uv = [0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0]
            col = [1.0] * 24
            vl = vls.get(k)
            if vl is None: vl = vls[k] = self.prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', q), tex_coords=('f', uv), colors=('f', col))
            else: vl.position[:] = q
            self._paint(tex, vl)
        self.prog['crisp'] = 0.0; self.prog['tsize'] = (1.0, 1.0); self.prog['cutoff'] = 0.5

    def _sg_screen(self, M, p):
        """A point of the map -> window pixel (from the bottom left) through the scene's camera of the last drawing, or None."""
        c = M @ np.array([p[0], p[1], p[2], 1.0])
        if c[3] <= 1e-9: return None
        return ((c[0] / c[3] + 1.0) / 2.0 * self.width, (c[1] / c[3] + 1.0) / 2.0 * self.height)

    def sugoroku_click(self, x, y):
        """Left click on a T'n'T arrow: its direction is pushed for a few steps, as if the player held that key (the engine moves the hero only along an arrow).
        -> True if the click is the board's (not while a game window waits for the keys or a message is open)."""
        eng = self.engine
        if eng.msg_visible or eng.input_menus(): return False
        arrows = self._sugoroku_arrows(eng.state); M = getattr(self, '_M_town', None)
        if not arrows or M is None: return False
        for pos, turn, frame in arrows:
            quad = [self._sg_screen(M, p) for p in SG.corners(pos, turn)]
            if None in quad or not SG.inside((x, y), quad, 1.4): continue
            a = self._sg_screen(M, pos); b = self._sg_screen(M, np.array(pos, float) + SG.tip(turn))
            if a is None or b is None: continue
            self._sg_hold = [SG.key_of(b[0] - a[0], b[1] - a[1]), SG.HOLD]; return True
        return False

    def sugoroku_held(self, p):
        """The keys of the step, with the direction of a clicked arrow while it lasts."""
        h = getattr(self, '_sg_hold', None)
        if not h: return p
        h[1] -= 1
        if h[1] <= 0: self._sg_hold = None
        return p | h[0]
