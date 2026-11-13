"""No-break (U+00A0), narrow (U+202F) and thin (U+2009) spaces: the FR patch puts a no-break space before "!", "?" and ":"; the menu font (SE-GARRIR) gives its glyph 160 an advance of 11 px against 5 px for the normal space, hence an almost
double space. History: drew them like the normal space EVERYWHERE; limited that to the history; **("removes the extra visual spaces"): `ui_menu.BitmapFont` draws them like the normal space again in all menus** (no more `normal_spaces` function in the history: the font handles it). The message font (`MessageFont`, the engine's: its U+00A0 is already 5 px) is not touched.

    python3 tests/test_nonbreaking_space.py

No game data: dummy font (space 5, no-break space 11, "!" 6). With the real extracted font (DQ_UI_CACHE: folder of ui_garrir.json / .png): the same checks on its real metrics.
"""
import json, os, sys, tempfile, types, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
import pyglet
pyglet.options['shadow_window'] = False
UM = TR.UM
try:
    from dq4_pc.menus import ui_history as UH
    from dq4_pc.core import history as HI
    from PIL import Image
except Exception as ex:
    UH = None; ERROR = ex

THIN = (' ', ' ', ' ')


def dummy_font():
    d = tempfile.mkdtemp()
    j, p = os.path.join(d, 'f.json'), os.path.join(d, 'f.png')
    Image.new('RGBA', (256, 256), (255, 255, 255, 255)).save(p)
    def g(code, adv, w=3, h=5): return [code, 0.0, -10.0, float(w), -float(h), float(adv), 0, 0.1, 0.1, 0.01, -0.02]
    with open(j, 'w') as f:
        json.dump({'nom': 'test', 'fontSize': 20.0, 'lineSpacing': 23.5, 'ascent': 18.9, 'descent': -4.0, 'pixelScale': 1.0,
                   'glyphes': [g(32, 5, 0, 0), g(0xa0, 11, 0, 0), g(33, 6), g(63, 9), g(58, 6), g(ord('a'), 8), g(ord('l'), 4)]}, f)
    return UM.BitmapFont(j, p)


def real_font():
    f = TR.real_font()
    return f.bm if f is not None else None


@unittest.skipIf(UH is None, 'ui_history non importable ici')
class ThinSpacesAreNormalSpaces(unittest.TestCase):
    def controls(self, F):
        sp = F.G[32][0]
        for c in THIN: self.assertEqual(F.width_px('a%s!' % c), F.width_px('a') + sp + F.width_px('!'), repr(c))
        self.assertEqual(F.width_px('a   '), F.width_px('a') + 3 * sp)
        for c in THIN: self.assertIs(F.G[ord(c)], F.G[32], repr(c))

    def test_dummy_font(self):
        F = dummy_font(); self.assertEqual(F.width_px('a !'), 8 + 5 + 6); self.controls(F)

    def test_real_font(self):
        F = real_font()
        if F is None: self.skipTest('DQ_UI_CACHE (ui_garrir.json / .png) absent')
        self.assertEqual(F.G[32][0], 5); self.controls(F)

    def test_line_image(self):
        """The texture of a line with the no-break space has the width of the one with the normal space (needs a GL context: hidden window)."""
        try: win = pyglet.window.Window(width=64, height=64, visible=False)
        except Exception as ex: self.skipTest('no GL context: %r' % (ex,))
        try:
            F = dummy_font(); t, w, h, b = F.line('a !'); t2, w2, h2, b2 = F.line('a !')
            self.assertEqual((w, h, b), (w2, h2, b2))
        finally: win.close()

    def test_other_chars_do_not_change(self):
        F = dummy_font()
        self.assertEqual(F.width_px('al!?:'), 4 + 8 + 6 + 9 + 6)
        self.assertEqual(F.width_px('a l'), 8 + 5 + 4)

    def test_no_constant_left_in_the_modules(self):
        self.assertFalse(hasattr(UM, 'THIN_SPACES')); self.assertFalse(hasattr(UH, 'THIN_SPACES')); self.assertFalse(hasattr(UH, 'normal_spaces'))

    def test_history_wrapping(self):
        """History line breaks (SE-GARRIR font, without the message font): "aa<nbsp>! al" (44 px) fits in 46 px."""
        F = dummy_font(); view = object.__new__(UH.HistoryView); view._lines = {}; view._bmm = lambda: None
        e = types.SimpleNamespace(n=1, type=HI.TYPE_DIALOGUE, text='aa ! al')
        B = types.SimpleNamespace(text_scale=1.0, text_width=lambda: 46.0, LINES=3)
        self.assertEqual(view._pages_of(F, e, B, 1.0, 17), [['aa ! al']])
        self.assertEqual(view._text_width(F, 'a !', 2.0, 17), (8 + 5 + 6) * 2.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
