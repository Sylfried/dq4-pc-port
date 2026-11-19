"""EXACT position of menu texts, as in the original game. Unity's TextMesh with the SE-GARRIR font is placed exactly as in the APK: anchor, line spacing, tabs,
alignment; no more vertical re-centering (formerly `text_recentering`: variable `DQ_ORIGINAL_TEXT` removed with it), no more re-cutting or compression (descriptions, spell cost line, poker), no more shift of the start menu title.
Pure logic, no window or engine (`tests/_text_render.py`: the real `Render._text` with a fake GL):

  1. `first_line_baseline` reproduces the original game: baselines measured on the mobile's capture (ecran4: target button "Rat volant" = 1 line, "Scarapince / x2" = string "Scarapince\\n\\n\\t x2" = 3 lines;
     button 82 px high centered at y = 159.2; scale 1.688 px / unit; characterSize 9.945, lineSpacing 0.441, anchor MiddleLeft) to within 0.6 unit;
  2. nothing of the re-centering remains (no function, no constant, no environment variable) and `Render._text` draws the 1st baseline at `first_line_baseline` to within zero, for all anchors and all line spacings;
  3. no compression: a text wider than any frame keeps its natural width (scale 1), whatever the window type (poker 48, spell info panel 7, battle item info 38...); only the fallback font (GMaruGoPro-M, without ui_garrir.*) still compresses;
  4. with the REAL layout and the real font (interface cache: DQ_UI_CACHE, default /tmp/audit_final/interface/uicache): the 465 text cells of the 80 types, with a long multi-line string containing a no-break space, are drawn
     exactly at the layout's position (baseline, left edge, scale 1); the start menu title (type 54) does not move when the game changes frame.

    python3 tests/test_text_exact_position.py        (Linux without a screen: pyglet in "headless" mode)
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM

LINE, ASCENT, CAP_HEIGHT = TR.LEADING, TR.ASCENT, 14.0              # SE-GARRIR: line spacing, ascent, capital height (font px)
SCALE, CENTER_Y = 1.688, 159.2                                      # mobile capture: px per unit, vertical center of the target button (px from the top)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def units(y_px): return -(y_px - CENTER_Y) / SCALE                  # measured ordinate (px, downward) -> units relative to the button center (upward)


class OriginPlacement(unittest.TestCase):
    def test_target_button_one_line(self):
        u = 9.945 * 0.1; step = LINE * u * 0.441
        base = UM.first_line_baseline(0.0, 1, 1, step, ASCENT * u)
        self.assertAlmostEqual(base, units(182.0), delta=0.6)       # "Rat volant": baseline at y = 182 px

    def test_target_button_three_lines(self):
        u = 9.945 * 0.1; step = LINE * u * 0.441
        b1 = UM.first_line_baseline(0.0, 1, 3, step, ASCENT * u)
        self.assertAlmostEqual(b1, units(165.0), delta=0.6)         # "Scarapince": y = 165 px
        self.assertAlmostEqual(b1 - 2 * step, units(200.0), delta=0.6)       # "x2" (3rd line): y = 200 px

    def test_anchors(self):
        self.assertAlmostEqual(UM.first_line_baseline(100.0, 0, 2, 10.0, 18.0), 82.0)     # top: the block hangs below the anchor
        self.assertAlmostEqual(UM.first_line_baseline(100.0, 1, 2, 10.0, 18.0), 92.0)     # middle
        self.assertAlmostEqual(UM.first_line_baseline(100.0, 2, 2, 10.0, 18.0), 102.0)    # bottom: the block rises above the anchor


class OptionOff(unittest.TestCase):
    def test_option_off_means_no_recentering(self):
        """re-centering (`text_recentering`) exists again, on by default; these tests turn it off (`_text_render`, like DQ_ORIGINAL_TEXT=1) to measure the game's exact position."""
        self.assertFalse(UM.TEXT_CENTERING)
        self.assertEqual(UM.text_recentering(LINE, 9.945 * 0.1, 0.441), 0.0)
        for name in ('compress_label', 'THIN_SPACES', 'BUTTON_COMPRESSION_TYPES'): self.assertFalse(hasattr(UM, name), name)          # (compression of button labels, narrow spaces: always removed; spell descriptions and cost lines have been realigned)


class ExactPlacement(unittest.TestCase):
    """Synthetic windows, dummy font (8 px per character): the drawn geometry is that of TextMesh (anchor, line spacing, alignment), nothing more."""
    TEXTS = ('Abandonner', 'Abandonner\nOk', 'Abc\n\nDefghij')

    def test_first_baseline_for_every_anchor_and_line_spacing(self):
        for anchor in range(9):
            for ls in (0.441, 0.481, 0.801, 0.873, 0.962, 1.0, 1.258):
                for text in self.TEXTS:
                    wnd = TR.make_window(3, [dict(pos=[10.0, 4.0, 20.0], anchor=anchor, alignment=0, ls=ls)]); wnd.param_str(0, 0, text)
                    node = wnd.N[10]; quads = TR.draw(wnd, node)
                    u = node['text']['characterSize'] * 0.1; step = LINE * u * ls; lines = text.split('\n')
                    base0 = UM.first_line_baseline(20.0, anchor // 3, len(lines), step, ASCENT * u)
                    expected = [base0 - i * step for i, l in enumerate(lines) if l]
                    self.assertEqual(len(quads), len(expected), (anchor, ls, text))
                    for q, b in zip(quads, expected): self.assertAlmostEqual(q.base, b, delta=0.01, msg=(anchor, ls, text))      # no re-centering: neither a lift of (1 - ls) x line spacing x u / 2, nor any other

    def test_the_text_is_not_lifted_for_a_low_line_spacing(self):
        """With lineSpacing 0.441 (battle targets) the re-centering raised the text by 6.5 units; it is now exactly at the game's baseline."""
        wnd = TR.make_window(33, [dict(pos=[0.0, 4.0, 0.0], anchor=4, alignment=1, ls=0.441)]); wnd.param_str(0, 0, 'Rat volant')
        q = TR.draw(wnd, wnd.N[10])[0]; u = 0.9945
        self.assertAlmostEqual(q.base, UM.first_line_baseline(0.0, 1, 1, LINE * u * 0.441, ASCENT * u), delta=0.01)

    def test_horizontal_anchor_and_alignment(self):
        for col, side in ((0, 'left'), (1, 'centre'), (2, 'right')):
            wnd = TR.make_window(3, [dict(pos=[-50.0, 4.0, 0.0], anchor=col, alignment=col)]); wnd.param_str(0, 0, 'Abcdefghij\nAbc')
            long_, short = TR.draw(wnd, wnd.N[10]); u = 0.9945; w1, w2 = 80 * u, 24 * u
            edge = {0: lambda q, w: q.x, 1: lambda q, w: q.x + w / 2, 2: lambda q, w: q.x + w}[col]
            self.assertAlmostEqual(edge(long_, w1), -50.0, delta=0.01, msg=side)                                         # the longest line: its edge (left, middle, right) is at the anchor
            self.assertAlmostEqual(edge(short, w2), -50.0, delta=0.01, msg=side)                                         # identical alignment at the anchor: the short line is aligned to the same edge

    def test_no_compression_whatever_the_window(self):
        """A 400-pixel string on a frame of a few tens of units: scale 1 and natural width, for all the types that used to compress (poker 48, spell info panel 7, item info 38) and the others."""
        for typ in (3, 7, 38, 46, 48, 53, 54, 60):
            for anchor, x in ((0, 75.0), (1, 0.0), (3, -214.0)):
                wnd = TR.make_window(typ, [dict(pos=[x, 4.0, 0.0], anchor=anchor)]); wnd.param_str(0, 0, 'Coût en PM  10/ 30 Abandonner Doubler Changer Garder x' * 2)
                for q in TR.draw(wnd, wnd.N[10]): self.assertAlmostEqual(q.ts, 1.0, places=6, msg=(typ, anchor)); self.assertAlmostEqual(q.width, (8 * len(q.text) + 4) * 0.9945, delta=0.01)


class FallbackFont(unittest.TestCase):
    """Without ui_garrir.* (fallback font GMaruGoPro-M, whose metrics are not the game's) compression within the plate or the window remains: it is the only case where it is still used."""
    def test_wide_text_is_compressed_in_its_frame(self):
        import types
        neighbor = types.SimpleNamespace(rects=lambda: [(-50.0, -50.0, 50.0, 50.0)])        # a neighboring window 100 units wide contains the text anchor
        r = TR.render(None, neighbors=[neighbor])
        wnd = TR.make_window(3, [dict(pos=[0.0, 4.0, 0.0], anchor=4, alignment=1)]); wnd.param_str(0, 0, 'Un texte tres long qui depasse la fenetre voisine')
        q = TR.draw(wnd, wnd.N[10], r=r)[0]
        self.assertLess(q.ts, 1.0); self.assertGreaterEqual(q.ts, 0.7 - 1e-9)


class RealLayoutAndFont(unittest.TestCase):
    """The 465 text cells of the real layout (80 types), the real font."""
    @classmethod
    def setUpClass(cls):
        cls.font = TR.real_font(); j = os.path.join(TR.CACHE, 'ui_layout.json'); b = os.path.join(TR.CACHE, 'ui_frameData.bin')
        if cls.font is None or not os.path.exists(j): raise unittest.SkipTest('cache de l\'interface absent (DQ_UI_CACHE : ui_layout.json, ui_garrir.json / .png)')
        cls.ml = UM.PageLayout(j, b if os.path.exists(b) else None); cls.dy = cls.ml.hdr['lang']['dy']

    def cells(self):
        for typ in sorted(self.ml.types, key=int):
            t = self.ml.types[typ]
            if t.get('err') or not t.get('nodes') or not t.get('params'): continue
            wnd = UM.Window(self.ml, int(typ))
            for (i, no), p in wnd.params.items():
                if 'custom' in p or p.get('textcolor') is not None: continue
                pt, ib = wnd._ib(p)
                if ib and ib['k'] == 'text': yield int(typ), i, no

    def test_every_cell_is_where_the_layout_puts_it(self):
        probes = ('Abcdefgh', 'Coût : 10/ 30 Abandonner Doubler Changer un texte bien plus large que toutes les plaques', "Peut aussi être utilisée comme objet au\r\ncombat.\nEt une troisième ligne")
        n = 0
        for typ, i, no in self.cells():
            for probe in probes:
                wnd = UM.Window(self.ml, typ); wnd.param_str(i, no, probe)
                pt, ib = wnd._ib(wnd.params[(i, no)]); node = wnd.N[ib['go']]; t = node['text']
                if not t.get('text') or {'wrap_x', 'fit_x', 'in_plate', 'mute', 'ink_center'} & set(node): continue                              # (cells realigned for French: tests/test_item_description.py and test_magic_entries.py; the battle list, test_magic_entries.py)
                u = t['characterSize'] * 0.1; step = self.font.leading * u * t['lineSpacing']; lines = t['text'].split('\n'); col = t['anchor'] % 3
                base0 = UM.first_line_baseline(node['pos'][2] - self.dy, t['anchor'] // 3, len(lines), step, self.font.ascent * u)
                quads = TR.draw(wnd, node, r=TR.render(self.font, ml=self.ml))
                shown = [l for l in lines if l]; self.assertEqual([q.text for q in quads], shown, (typ, i, no))
                wid = [self.font.width_px(l) * u * node['tscale'] for l in lines]; bl = max(wid); it = iter(quads)
                for idx, l in enumerate(lines):
                    if not l: continue
                    q = next(it)
                    self.assertAlmostEqual(q.ts, node['tscale'], places=5, msg=(typ, i, no, probe))                                   # no compression, no thin space replaced
                    self.assertAlmostEqual(q.base, base0 - idx * step, delta=0.01, msg=(typ, i, no, probe))                           # no re-centering
                    al = {0: 0.0, 1: (bl - wid[idx]) / 2, 2: bl - wid[idx]}[t['alignment']]
                    self.assertAlmostEqual(q.x, node['pos'][0] - {0: 0.0, 1: bl / 2, 2: bl}[col] + al, delta=0.01, msg=(typ, i, no, probe))      # no re-cutting: the line starts from the game's anchor
                n += 1
        self.assertGreater(n, 1300)                                                     # 465 cells x 3 strings (minus the cells without text)

    def test_poker_labels(self):
        """"Abandonner", "Doubler", "Changer", "Garder" (types 48): natural width, as on mobile, even when they exceed their plate (the translation project will shorten the strings)."""
        for (i, no) in ((4, 0), (4, 2), (2, 0), (0, 5)):
            for s in ('Abandonner', 'Doubler', 'Garder', 'Changer'):
                wnd = UM.Window(self.ml, 48)
                if (i, no) not in wnd.params: continue
                wnd.param_str(i, no, s); pt, ib = wnd._ib(wnd.params[(i, no)])
                q = TR.draw(wnd, wnd.N[ib['go']], r=TR.render(self.font, ml=self.ml))[0]; self.assertAlmostEqual(q.ts, 1.0, places=5, msg=(i, no, s))

    def test_start_menu_title_does_not_move(self):
        """Type 54, option off (the game's exact position): the start menu title stays where the layout puts it, whatever frame is chosen by code 3 (with re-centering, it follows its frame: test_text_recentering)."""
        for c in (0, 1, 2):
            wnd = UM.Window(self.ml, 54)
            frame = next((ib for pt in wnd.parts for ib in pt['ib'] if ib['k'] == 'frame'), None); self.assertIsNotNone(frame)
            title = next(n for n in wnd.N.values() if n['par'] == frame.get('go') and n['text'] is not None); before = list(title['pos'])
            wnd.code(3, c); self.assertEqual(title['pos'], before, c)


if __name__ == '__main__':
    unittest.main(verbosity=2)
