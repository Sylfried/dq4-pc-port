"""End credits: what the Unity interface does with the staff roll's port (StaffrollPort, Staffroll).

The engine writes the credits itself, 16 rows at a time, into two 512 x 512 RGBA textures (the engine's side is in core/engine.py: Engine._staffroll_after gives it the textures, the emulator copies the pixels it uploads
into them) and sends, at each frame, the offset of the textures' V coordinate (+1/256 per frame = 2 pixels). Unity shows them on two quads of its interface layer (the interface camera's: top view of the XZ plane, one
unit = one pixel of the 450 x 800 column), `Staffroll.Setup`: quad A (z from 0 to the top) with the engine's second texture, quad B (z from 0 down) with the first, both 450 units wide and (16 / 9 + 0.25) x 225 = 456.25 units
high, shader Custom/Picture, repeating textures: each quad shows its texture shifted by the offset, the rows that leave at the top come back at the bottom of the same quad (the engine writes the new text into the rows
that have just left). The credits cover the whole screen (opaque black background); the port draws a black window with the two quads in the interface column.

Dragon Quest V / VI (EndrollPort, Endroll): the credits are pictures of text of the game (atlases and layouts: core/endroll.py), scrolled by Unity on the orthographic layer; while the port
exists the scene camera is off, so the window shows that layer alone on black (the engine's meshes of that layer, such as the falling petals, then the lines).
"""
import numpy as np
import pyglet
from pyglet import gl
from dq456_pc.core import engine as ENGINE
from dq456_pc.core import endroll as ER
from dq456_pc.window.constants import ORTHO_HALF_WIDTH
from dq456_pc.window.helpers import portrait_base_height

QUAD_W = 450.0                          # width of the two quads, in interface units
QUAD_H = (16 / 9 + 0.25) * 225          # height of each: (NotchFix.AspectRatio() + 0.25) x 225 (portrait 16 / 9 phone)


def visible_rows(offset, size=ENGINE.STAFF_SIZE):
    """Rows of a credits texture, from the top of its quad to the bottom, for the offset sent by the engine (texture units: 1.0 = the whole texture): [(first row, last row + 1)] (rows counted from the top of the picture).
    The texture repeats: the rows from the offset's to the end, then those before it."""
    s = int(round(offset * size)) % size
    return [(s, size), (0, s)] if s else [(0, size)]


class StaffrollMixin:
    _staff_gl = None                      # the two textures of the viewer (pyglet) and the number of uploads of the engine they hold
    _endroll_gl = None                    # DQ V / VI: the credits' atlases (pyglet textures, white letters: the vertex color tints them), by name

    def _staffroll_up(self, e, field, is_battle):
        """The credits are on the screen: the engine created the port and made it visible (not closed yet), in a town (the ending's scene)."""
        st = self.engine.ui.staff
        return st is not None and st['live'] and st['visible'] and not field and not is_battle and e.part == ENGINE.PART_TOWN and bool(st.get('tex'))

    def _staff_textures(self, st):
        """Textures of the credits, updated when the engine has uploaded rows since the last drawing."""
        serial = self.engine.core.gl_serial
        if self._staff_gl is None or self._staff_gl['st'] is not st:
            tex = [self._tex(img, False) for img in st['tex']]
            for t in tex:
                gl.glBindTexture(t.target, t.id)
                gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)         # (Texture2D: bilinear)
            self._staff_gl = {'st': st, 'tex': tex, 'serial': serial}
        elif self._staff_gl['serial'] != serial:
            self._staff_gl['serial'] = serial
            for t, img in zip(self._staff_gl['tex'], st['tex']):
                n = img.shape[0]; t.blit_into(pyglet.image.ImageData(img.shape[1], n, 'RGBA', np.ascontiguousarray(img[::-1]).tobytes(), pitch=img.shape[1] * 4), 0, 0, 0)
        return self._staff_gl['tex']

    def _draw_staffroll(self):
        """Black over the whole window, then the credits' two quads in the interface column (A, the engine's second texture, above the middle of the column, B, the first, under it); black alone once "The End" has started."""
        st = self.engine.ui.staff; tex = self._staff_textures(st)
        gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear()
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        if self.engine.the_end_started(): return                                     # the credits are over (startTheEnd): the last picture is not kept under "The End" (not verified against the game: it would overlap it)
        cx, cy, u = self._ui_reference()
        size = ENGINE.STAFF_SIZE; zq = QUAD_H * u; wq = QUAD_W * u; x0 = cx - wq / 2; row_h = zq / size
        for t, y in ((tex[1], cy + zq), (tex[0], cy)):                              # y: top of the quad (pyglet: y up)
            for r0, r1 in visible_rows(st['offset'], size):
                h = (r1 - r0) * row_h
                spr = pyglet.sprite.Sprite(t.get_region(0, size - r1, size, r1 - r0), x0, y - h)
                spr.scale_x = wq / size; spr.scale_y = row_h; spr.draw(); spr.delete()
                y -= h

    # ---- DQ V / VI (EndrollPort, Endroll: core/endroll.py)
    def _endroll_up(self):
        """DQ V / VI: the credits' port exists (from its creation to its closing): EndrollPort.SetupCamera has turned the scene camera off, only the orthographic layer is seen, on black."""
        er = getattr(self.engine.ui, 'endroll', None)
        return er is not None and er['live']

    def _endroll_texture(self, name):
        """Atlas of the credits: Unity draws it with the font shader (vertex color, the texture's alpha): its letters are made white here, the sprite's color tints them."""
        if self._endroll_gl is None: self._endroll_gl = {}
        t = self._endroll_gl.get(name)
        if t is None:
            arr = self.data.texture(name)
            if arr is None: return None
            arr = arr.copy(); arr[..., :3] = 255
            t = self._tex(arr, False)
            gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            self._endroll_gl[name] = t
        return t

    def _draw_endroll(self, e):
        """Black, the engine's meshes of the orthographic layer (packet MESH_ORTHO), then the credits' lines (their column scrolls up: core/endroll.py), centered like that layer:
        the phone's short side across the window's height (portrait_base_height), so a 16:9 window shows the middle of the phone's column."""
        gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear()
        gl.glViewport(0, 0, *self.get_framebuffer_size())
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        aspect = self.width / max(1, self.height)
        if e.meshes and any(st.get('ortho') for st in e.mesh_state.values()):
            self.prog.use()
            self.prog['mvp'] = tuple(float(x) for x in self._ortho_matrix(aspect, e).T.ravel()); self.prog['cutoff'] = 0.05; self.prog['tsize'] = (1.0, 1.0); self.prog['amul'] = 1.0
            self._gl_tint = None; self._set_tint((1.0, 1.0, 1.0)); gl.glDisable(gl.GL_CULL_FACE); gl.glActiveTexture(gl.GL_TEXTURE0)
            self._linked_domain = None
            for tex, tw, th, vl, shader, hd in self._battle_meshes(e, None, True, ortho=True):
                self.prog['crisp'] = 0.0 if hd else (1.0 if self.smoothing else 2.0); self.prog['tsize'] = (float(tw), float(th)); self._paint(tex, vl)
            self.prog['crisp'] = 0.0; self.prog['tsize'] = (1.0, 1.0)
            self.prog.stop()
        st = self.engine.ui.endroll.get('state')
        if st is None or not st['shown']: return
        hh = ORTHO_HALF_WIDTH * portrait_base_height(aspect); k = self.height / 2.0 / hh
        for ln, x, top, s in ER.visible_lines(st, hh):
            t = self._endroll_texture(ln['atlas'])
            if t is None: continue
            reg = t.get_region(ln['u'], t.height - ln['v'] - ln['h'], ln['w'], ln['h'])
            spr = pyglet.sprite.Sprite(reg, self.width / 2.0 + x * k, self.height / 2.0 + (top - s * ln['h']) * k)
            spr.scale = s * k; spr.color = ln['color'][:3]; spr.draw(); spr.delete()
