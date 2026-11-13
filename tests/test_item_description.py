"""Item and spell descriptions in their 2-line frame (on mobile they overflow: a long description covered the battle cost cell).
The patch's French text has lines of 38 characters, or a single line of 50 ("Peut aussi etre utilisee comme objet au / combat."): it stuck out of the frame. `Render._text` re-wraps it to the frame width then, if 2 lines are not enough, compresses it (down to x0.7).

The eight cells concerned (type, port, string number): spell info panel (7, 0, 1), Items menu (10, 0, 4), spell or item info in battle (38, 2, 3), casino (46, 4, 3), shops (60, 4, 4), (61, 4, 4), (63, 0, 4), sale item info panel (70, 0, 3).

  1. each cell carries its re-wrap limit (`wrap_x` = UM.DESCRIPTIONS, `wrap_n` = 2), its text is the engine's; the neighboring cells carry none;
  2. `Render._text` (dummy font, no GL): a text that fits (2 lines in the frame) is drawn as is, with the patch's line breaks; otherwise at most 2 lines, none of which exceeds the limit, compressed at most to COMPRESSION_MIN;
  3. with the real layout (interface cache: DQ_UI_CACHE): the eight cells exist and the long text (4 lines) fits in the frame;
  4. with DQ_APK=<folder of the patched APKs> and the real font: the 360 descriptions of the patch (assets/msg/en/b0831000.mpt and b0835000.mpt) all fit in their frame (at most 2 lines, right edge respected).

    python3 tests/test_item_description.py
    DQ_APK=<patched APKs> [DQ_UI_CACHE=<interface cache>] python3 tests/test_item_description.py
"""
import os, re, sys, unittest, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM

APK = os.environ.get('DQ_APK')
CELLS = ((7, 0, 1), (10, 0, 4), (38, 2, 3), (46, 4, 3), (60, 4, 4), (61, 4, 4), (63, 0, 4), (70, 0, 3))
PAD_SLACK = 4.5                                                                             # a quad overflows the texture margin (2 px on each side): ink = width - 4
ONE_LINE = "Au combat, ils peuvent inverser le cours du temps."                      # a single line of 50 characters
TWO_LINES = "Peut aussi être utilisée comme objet au\r\ncombat."                      # 1re ligne de 39 caracteres
FOUR_LINES = "Permet de sortir\r\nimmédiatement des\r\ndonjons, grottes et\r\ntours."


def description_window(typ, port, no):
    """Synthetic window: `no` + 1 text cells of port `port`, the last one is the description (at anchor x = -214, at the bottom: z = -324)."""
    return TR.make_window(typ, [dict(pos=[-214.0, 4.0, -324.0], anchor=3, ls=0.881)] * (no + 1), port=port)


class Cells(unittest.TestCase):
    def test_limit_on_the_description_cell_only(self):
        for typ, port, no in CELLS:
            wnd = description_window(typ, port, no)
            for k in range(no + 1): wnd.param_str(port, k, 'x' * 60 if k != no else FOUR_LINES)
            for k in range(no):
                self.assertFalse({'wrap_x', 'wrap_n', '_adj'} & set(wnd.N[10 + k]), (typ, port, no, k))
            node = wnd.N[10 + no]; self.assertEqual((node['wrap_x'], node['wrap_n']), (UM.DESCRIPTIONS[(typ, port, no)], 2), (typ, port, no))
            self.assertEqual(node['text']['text'], FOUR_LINES, (typ, port, no))                 # the engine's text is not modified


class Drawn(unittest.TestCase):
    FONT = TR.FakeFont(advance=8)                                                             # 8 font px per character: 7.96 units at size 9.945

    def draw(self, typ, port, no, text, font=None):
        wnd = description_window(typ, port, no)
        for k in range(no + 1): wnd.param_str(port, k, 'x')
        wnd.param_str(port, no, text); return TR.draw(wnd, wnd.N[10 + no], font=font or self.FONT)

    def test_text_that_fits_is_unchanged(self):
        for typ, port, no in CELLS:
            quads = self.draw(typ, port, no, "Ne semble pas avoir d'effets\r\nparticuliers.\n")
            self.assertEqual([q.text for q in quads], ["Ne semble pas avoir d'effets\r", 'particuliers.']); self.assertTrue(all(abs(q.ts - 1.0) < 1e-6 for q in quads))

    def test_too_long_text_is_cut_to_two_lines_inside_the_frame(self):
        for typ, port, no in CELLS:
            limit = UM.DESCRIPTIONS[(typ, port, no)]
            for text in (ONE_LINE, TWO_LINES, FOUR_LINES):
                quads = self.draw(typ, port, no, text)
                self.assertLessEqual(len(quads), 2, (typ, text)); self.assertGreaterEqual(min(q.ts for q in quads), UM.COMPRESSION_MIN - 1e-6, (typ, text))
                for q in quads: self.assertLessEqual(q.x + q.width, limit + PAD_SLACK, (typ, text, q))      # right edge of the frame respected

    def test_words_are_kept(self):
        quads = self.draw(38, 2, 3, ONE_LINE); self.assertEqual(' '.join(q.text for q in quads).split(), ONE_LINE.split())


@unittest.skipUnless(os.path.exists(os.path.join(TR.CACHE, 'ui_layout.json')) and TR.real_font() is not None, 'real layout and font: interface cache (DQ_UI_CACHE: ui_layout.json, ui_garrir.json / .png)')
class RealPageLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ml = UM.PageLayout(os.path.join(TR.CACHE, 'ui_layout.json')); cls.font = TR.real_font()

    def test_each_cell_is_the_bottom_description_cell_and_fits(self):
        for typ, port, no in CELLS:
            wnd = UM.Window(self.ml, typ); pt, ib = wnd._ib(wnd.params[(port, no)])
            self.assertEqual(ib['k'], 'text', (typ, port, no)); node = wnd.N[ib['go']]
            self.assertTrue(node['pos'][2] < -190 and node['pos'][0] < -200, (typ, port, no, node['pos']))      # bottom bar (z -324 or -323.5) or left cell in battle (z -197), text on the left
            wnd.param_str(port, no, FOUR_LINES); self.assertEqual(node['wrap_x'], UM.DESCRIPTIONS[(typ, port, no)])
            quads = TR.draw(wnd, node, r=TR.render(self.font, ml=self.ml))
            self.assertLessEqual(len(quads), 2, (typ, port, no))
            for q in quads: self.assertLessEqual(q.x + q.width, node['wrap_x'] + PAD_SLACK, (typ, port, no, q)); self.assertGreaterEqual(q.ts, UM.COMPRESSION_MIN - 1e-6)


@unittest.skipUnless(APK and os.path.exists(os.path.join(APK, 'split_UnityDataAssetPack.apk')) and os.path.exists(os.path.join(TR.CACHE, 'ui_layout.json')) and TR.real_font() is not None,
                     'real descriptions: DQ_APK=<folder of the patched APKs> and the interface cache (ui_layout.json, ui_garrir.*)')
class RealDescriptions(unittest.TestCase):
    """The 360 descriptions of the patch (assets/msg/en/b0831000.mpt and b0835000.mpt: two twin tables of 180 items), the real font and the real window: each one fits in its frame."""
    SEP = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]+|@c\d@(?:@a@b)?|@a@b")

    @classmethod
    def setUpClass(cls):
        cls.ml = UM.PageLayout(os.path.join(TR.CACHE, 'ui_layout.json')); cls.font = TR.real_font()
        z = zipfile.ZipFile(os.path.join(APK, 'split_UnityDataAssetPack.apk')); cls.texts = []
        for name_str in ('assets/msg/en/b0831000.mpt', 'assets/msg/en/b0835000.mpt'):
            b = z.read(name_str).decode('utf-8', 'replace'); cls.texts += [e for e in cls.SEP.split(b[b.find('@a@b'):]) if len(e.strip()) >= 6]

    def test_patch_descriptions_exist(self):
        self.assertGreaterEqual(len(self.texts), 300)
        self.assertTrue(any('Peut aussi être utilisée comme objet au' in t for t in self.texts))

    def test_every_description_fits_its_frame(self):
        for typ, port, no in ((38, 2, 3), (10, 0, 4), (7, 0, 1)):
            wnd = UM.Window(self.ml, typ); pt, ib = wnd._ib(wnd.params[(port, no)]); node = wnd.N[ib['go']]; r = TR.render(self.font, ml=self.ml)
            for text in self.texts:
                wnd.param_str(port, no, text); quads = TR.draw(wnd, node, r=r)
                self.assertLessEqual(len(quads), 2, (typ, text))                                                 # the frame shows only 2 lines
                for q in quads: self.assertLessEqual(q.x + q.width, node['wrap_x'] + PAD_SLACK, (typ, text, q)); self.assertGreaterEqual(q.ts, UM.COMPRESSION_MIN - 1e-6, (typ, text))


if __name__ == '__main__':
    unittest.main()
