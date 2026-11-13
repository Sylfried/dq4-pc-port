"""Vertical re-centering of menu texts (every text is centered), pure logic, no window or engine:

1. `text_recentering`: raising the ink to the center of the line box = line spacing x u x (1 - lineSpacing) / 2; zero for lineSpacing >= 1 (gauges) and with DQ_ORIGINAL_TEXT=1 (`TEXT_CENTERING` false);
2. after re-centering, the middle of the capital letters of a single line is within 0.6 unit of the anchor point, for all lineSpacing values and all sizes in the game; the 3-line block ("Scarapince / x2") is centered;
3. the real `Render._text` (fake GL) applies the raise to the three anchors, without touching x or the scale; with the REAL layout and the real font: the 465 text cells of the 80 types;
4. the title of type 54 follows its frame (code 3); with the option off it does not move.

  python3 tests/test_text_recentering.py        (Linux without a screen: pyglet in "headless" mode)
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM

LINE, ASCENT, CAP_HEIGHT = TR.LEADING, TR.ASCENT, 14.0              # SE-GARRIR: line spacing, ascent, capital height (font px)


class Centered(unittest.TestCase):
    def setUp(self): self._rec = UM.TEXT_CENTERING; UM.TEXT_CENTERING = True
    def tearDown(self): UM.TEXT_CENTERING = self._rec

    def test_values(self):
        u = 9.945 * 0.1
        self.assertAlmostEqual(UM.text_recentering(LINE, u, 0.441), 6.53, delta=0.05)       # targets: 6.5 units (11 px at 1.688)
        self.assertAlmostEqual(UM.text_recentering(LINE, 9.393 * 0.1, 0.481), 5.73, delta=0.05)     # monster plates
        self.assertAlmostEqual(UM.text_recentering(LINE, 9.945 * 0.1, 0.801), 2.34, delta=0.05)      # tabs, buttons, names
        for ls in (1.0, 1.002, 1.258, 2.46): self.assertEqual(UM.text_recentering(LINE, u, ls), 0.0)     # "PV / PM / Nv." and lists: unchanged

    def test_original_option(self):
        UM.TEXT_CENTERING = False
        self.assertEqual(UM.text_recentering(LINE, 0.99, 0.441), 0.0)

    def test_a_centered_line(self):
        for ls in (0.441, 0.481, 0.801, 0.841, 0.873, 0.881, 0.962):
            for cs in (6.63, 9.393, 9.945, 10.498):
                u = cs * 0.1; step = LINE * u * ls
                base = UM.first_line_baseline(0.0, 1, 1, step, ASCENT * u) + UM.text_recentering(LINE, u, ls)
                middle = base + CAP_HEIGHT * u / 2                      # middle of the capital letters
                self.assertAlmostEqual(middle, 0.0, delta=0.6, msg=(ls, cs))

    def test_three_centered_lines(self):
        u = 9.945 * 0.1; ls = 0.441; step = LINE * u * ls
        b1 = UM.first_line_baseline(0.0, 1, 3, step, ASCENT * u) + UM.text_recentering(LINE, u, ls)
        ink_top, ink_bottom = b1 + CAP_HEIGHT * u, b1 - 2 * step       # capital letters of the 1st line ... baseline of the 3rd
        self.assertAlmostEqual((ink_top + ink_bottom) / 2, 0.0, delta=1.0)
        self.assertLess(ink_top, 24.3); self.assertGreater(ink_bottom, -24.3)       # the block fits in the button (visible half-height 24.3 units): "x2" no longer touches the bottom

    def test_render_applies_it_to_every_anchor(self):
        for anchor in range(9):
            for ls in (0.441, 0.801, 1.0, 1.258):
                wnd = TR.make_window(3, [dict(pos=[10.0, 4.0, 20.0], anchor=anchor, alignment=0, ls=ls)]); wnd.param_str(0, 0, 'Abandonner')
                node = wnd.N[10]; q = TR.draw(wnd, node)[0]
                u = node['text']['characterSize'] * 0.1; step = LINE * u * ls
                exact = UM.first_line_baseline(20.0, anchor // 3, 1, step, ASCENT * u)
                self.assertAlmostEqual(q.base, exact + UM.text_recentering(LINE, u, ls), delta=0.01, msg=(anchor, ls))
                self.assertAlmostEqual(q.ts, 1.0, places=5)


class RealLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = TR.real_font(); j = os.path.join(TR.CACHE, 'ui_layout.json'); b = os.path.join(TR.CACHE, 'ui_frameData.bin')
        if cls.font is None or not os.path.exists(j): raise unittest.SkipTest('cache de l\'interface absent (DQ_UI_CACHE : ui_layout.json, ui_garrir.json / .png)')
        cls.ml = UM.PageLayout(j, b if os.path.exists(b) else None); cls.dy = cls.ml.hdr['lang']['dy']

    def setUp(self): self._rec = UM.TEXT_CENTERING; UM.TEXT_CENTERING = True
    def tearDown(self): UM.TEXT_CENTERING = self._rec

    def cells(self):
        for typ in sorted(self.ml.types, key=int):
            t = self.ml.types[typ]
            if t.get('err') or not t.get('nodes') or not t.get('params'): continue
            wnd = UM.Window(self.ml, int(typ))
            for (i, no), p in wnd.params.items():
                if 'custom' in p or p.get('textcolor') is not None: continue
                pt, ib = wnd._ib(p)
                if ib and ib['k'] == 'text': yield int(typ), i, no

    def test_every_cell_is_recentered_and_nothing_else_moves(self):
        n = shifted = 0
        for typ, i, no in self.cells():
            for probe in ('Abcdefgh', "Peut aussi être utilisée comme objet au\r\ncombat.\nEt une troisième ligne"):
                wnd = UM.Window(self.ml, typ); wnd.param_str(i, no, probe)
                pt, ib = wnd._ib(wnd.params[(i, no)]); node = wnd.N[ib['go']]; t = node['text']
                if not t.get('text') or {'wrap_x', 'fit_x', 'in_plate', 'mute', 'ink_center'} & set(node): continue                              # (cells realigned for French: tests/test_item_description.py and test_magic_entries.py; test_magic_entries.py)
                u = t['characterSize'] * 0.1; ls = t['lineSpacing']; step = self.font.leading * u * ls; lines = t['text'].split('\n'); col = t['anchor'] % 3
                base0 = UM.first_line_baseline(node['pos'][2] - self.dy, t['anchor'] // 3, len(lines), step, self.font.ascent * u) + self.font.leading * u * (1.0 - ls) / 2 * (ls < 1.0)
                quads = TR.draw(wnd, node, r=TR.render(self.font, ml=self.ml)); it = iter(quads)
                wid = [self.font.width_px(l) * u * node['tscale'] for l in lines]; bl = max(wid)
                for idx, l in enumerate(lines):
                    if not l: continue
                    q = next(it)
                    self.assertAlmostEqual(q.base, base0 - idx * step, delta=0.01, msg=(typ, i, no))                                  # remontee de (1 - ls) x interligne x u / 2 si ls < 1
                    self.assertAlmostEqual(q.ts, node['tscale'], places=5, msg=(typ, i, no))                                          # ni compression
                    al = {0: 0.0, 1: (bl - wid[idx]) / 2, 2: bl - wid[idx]}[t['alignment']]
                    self.assertAlmostEqual(q.x, node['pos'][0] - {0: 0.0, 1: bl / 2, 2: bl}[col] + al, delta=0.01, msg=(typ, i, no))      # ni decalage horizontal
                n += 1; shifted += ls < 1.0
        self.assertGreater(n, 800); self.assertGreater(shifted, n // 2)                  # most cells have a line spacing < 1: all lifted

    def test_middle_anchored_single_lines_are_centered(self):
        """Any cell with a "middle" anchor and a single line: the middle of the capital letters is within 0.6 unit of the anchor point."""
        n = 0
        for typ, i, no in self.cells():
            wnd = UM.Window(self.ml, typ); wnd.param_str(i, no, 'Abcdefgh')
            pt, ib = wnd._ib(wnd.params[(i, no)]); node = wnd.N[ib['go']]; t = node['text']
            if not t.get('text') or t['anchor'] // 3 != 1 or {'wrap_x', 'fit_x', 'in_plate', 'mute', 'ink_center'} & set(node): continue
            u = t['characterSize'] * 0.1; q = TR.draw(wnd, node, r=TR.render(self.font, ml=self.ml))[0]
            if t['lineSpacing'] < 1.0: self.assertAlmostEqual(q.base + CAP_HEIGHT * u / 2, node['pos'][2] - self.dy, delta=0.6, msg=(typ, i, no)); n += 1
        self.assertGreater(n, 100)

    def test_start_menu_title_follows_its_frame(self):
        """Type 54: the title follows the frame tab chosen by code 3 (otherwise it floats above frame 220 / 221); option off: it does not move."""
        moved = False
        for c in (0, 1, 2):
            for option in (True, False):
                UM.TEXT_CENTERING = option
                wnd = UM.Window(self.ml, 54)
                frame = next((ib for pt in wnd.parts for ib in pt['ib'] if ib['k'] == 'frame'), None); self.assertIsNotNone(frame)
                title = next(n for n in wnd.N.values() if n['par'] == frame.get('go') and n['text'] is not None); before = list(title['pos'])
                wnd.code(3, c)
                if option and title['pos'] != before: moved = True
                if not option: self.assertEqual(title['pos'], before, c)
        self.assertTrue(moved)


if __name__ == '__main__':
    unittest.main(verbosity=2)
