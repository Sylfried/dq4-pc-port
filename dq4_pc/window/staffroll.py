"""End credits: what the Unity interface does with the staff roll's port (StaffrollPort, Staffroll).

The engine writes the credits itself, 16 rows at a time, into two 512 x 512 RGBA textures (the engine's side is in core/engine.py: Engine._staffroll_after gives it the textures, the emulator copies the pixels it uploads
into them) and sends, at each frame, the offset of the textures' V coordinate (+1/256 per frame = 2 pixels). Unity shows them on two quads of its interface layer (the interface camera's: top view of the XZ plane, one
unit = one pixel of the 450 x 800 column), `Staffroll.Setup`: quad A (z from 0 to the top) with the engine's second texture, quad B (z from 0 down) with the first, both 450 units wide and (16 / 9 + 0.25) x 225 = 456.25 units
high, shader Custom/Picture, repeating textures: each quad shows its texture shifted by the offset, the rows that leave at the top come back at the bottom of the same quad (the engine writes the new text into the rows
that have just left). The credits cover the whole screen (opaque black background); the port draws a black window with the two quads in the interface column.
"""
import numpy as np
import pyglet
from pyglet import gl
from dq4_pc.core import engine as ENGINE

QUAD_W = 450.0                          # width of the two quads, in interface units
QUAD_H = (16 / 9 + 0.25) * 225          # height of each: (NotchFix.AspectRatio() + 0.25) x 225 (portrait 16 / 9 phone)


def visible_rows(offset, size=ENGINE.STAFF_SIZE):
    """Rows of a credits texture, from the top of its quad to the bottom, for the offset sent by the engine (texture units: 1.0 = the whole texture): [(first row, last row + 1)] (rows counted from the top of the picture).
    The texture repeats: the rows from the offset's to the end, then those before it."""
    s = int(round(offset * size)) % size
    return [(s, size), (0, s)] if s else [(0, size)]


class StaffrollMixin:
    _staff_gl = None                      # the two textures of the viewer (pyglet) and the number of uploads of the engine they hold

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
