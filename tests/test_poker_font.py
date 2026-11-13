"""Casino poker labels (type 48) at the game's EXACT width. Before: "Abandonner" stuck out of the five buttons under the cards and overlapped (French is longer than the button's English);
a compression of these labels (down to x0.70) was tried and dropped: everything keeps the exact position and size of the game, overflows are to be fixed in the translation. There is no more compression,
neither for poker nor elsewhere (with SE-GARRIR).

  1. button plate (part 7) of 80 units and a centered label wider than it: scale 1, centered on the plate, the same as for any other window type;
  2. with the REAL layout and the real font (interface cache: DQ_UI_CACHE): the labels of the five buttons "Abandonner", "Doubler", "Changer", "Garder" keep their natural width.

    python3 tests/test_poker_font.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _text_render as TR           # needs pyglet (absent from the CI: the tests are then skipped)
    UM = TR.UM
except ImportError:
    TR = UM = None


@unittest.skipIf(TR is None, 'pyglet absent (CI)')
class Poker(unittest.TestCase):
    def test_label_wider_than_its_plate_is_not_compressed(self):
        for typ in (48, 3, 44, 46, 47, 49, 53, 54):                       # poker, and the windows that did not compress either
            wnd = TR.make_window(typ, [dict(pos=[0.0, 4.0, 0.0], anchor=4, alignment=1)], plates=[dict(pos=[0.0, 0.0], w=80.0, h=40.0)]); wnd.param_str(0, 0, 'Abandonner')
            q = TR.draw(wnd, wnd.N[10])[0]
            self.assertAlmostEqual(q.ts, 1.0, places=6, msg=typ); self.assertAlmostEqual(q.width, (8 * 10 + 4) * 0.9945, delta=0.01)
            self.assertGreater(q.width, 80.0 - 14.0)                      # (wider than the plate minus its margins: this is indeed the case that used to be compressed)
            self.assertAlmostEqual(q.x + (q.width - 4 * 0.9945) / 2, 0.0, delta=0.01)       # centered on the anchor, as in the game

    def test_no_compression_machinery_left(self):
        for name in ('compress_label', 'BUTTON_COMPRESSION_TYPES'): self.assertFalse(hasattr(UM, name), name)


@unittest.skipIf(TR is None, 'pyglet absent (CI)')
class RealPoker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = TR.real_font(); j = os.path.join(TR.CACHE, 'ui_layout.json'); b = os.path.join(TR.CACHE, 'ui_frameData.bin')
        if cls.font is None or not os.path.exists(j): raise unittest.SkipTest('cache de l\'interface absent (DQ_UI_CACHE : ui_layout.json, ui_garrir.json / .png)')
        cls.ml = UM.PageLayout(j, b if os.path.exists(b) else None)

    def test_labels_keep_their_natural_width(self):
        n = 0
        for (i, no) in ((4, 0), (4, 2), (2, 0), (0, 5)):
            wnd = UM.Window(self.ml, 48)
            if (i, no) not in wnd.params: continue
            for s in ('Abandonner', 'Doubler', 'Garder', 'Changer'):
                wnd = UM.Window(self.ml, 48); wnd.param_str(i, no, s); pt, ib = wnd._ib(wnd.params[(i, no)])
                q = TR.draw(wnd, wnd.N[ib['go']], r=TR.render(self.font, ml=self.ml))[0]
                self.assertAlmostEqual(q.ts, 1.0, places=5, msg=(i, no, s)); n += 1
        self.assertGreaterEqual(n, 8)
        self.assertGreater(self.font.width_px('Abandonner') * 0.9945, 100.0)               # "Abandonner" is 103 units: more than the plate of 72 (it overflows, as on mobile)


if __name__ == '__main__':
    unittest.main()
