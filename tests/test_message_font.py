"""Test of the game's message font (dq456_pc/menus/message_font.py): the one the engine uses to draw dialogues (and that the history reuses).

    python3 tests/test_message_font.py                                      (rules, with a synthetic font: without pyglet or engine)
    DQ_APK=<patched APK folder> DQ_SAVES=<saves folder> python3 tests/test_message_font.py     (in addition: the real font, compared with the real engine)

Without engine: glyph reading (repeated bytes / bytes as is / end), advance of the writing position (glyph width, flagged glyph placed one pixel to the left and advancing two pixels less, engine space and font
step, tab, ";" and "$" not drawn, missing code -> the "@" glyph), pixels of a line, line wrapping (`CTextAutoReturn::AutoReturn`: break points, hyphen, line break, word longer than the line),
extraction of the font into the cache.
With the real engine (optional, skipped otherwise): the pixels of `SDrawCTRL::PutChar` in the engine's canvas are those of `MessageFont.pixels` for a French sentence, the patch's Russian letters (я, и) and the flagged
glyphs; the lines of `MessageFont.wrap_text` are those of `AutoReturn` on game messages. No character is written "hard-coded": everything comes from the font file (DQ5 and DQ6: same format).
"""
import os, struct, sys, tempfile, unittest, zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import numpy as np
from dq456_pc.menus.message_font import MessageFont, extract_message_font, TABLE_SIZE, TABLE_START, DATA_START, CODE_DEFAULT

H = 24


def rle_encode(bitmap):
    """Glyph data (height x width bytes, flat) as 'repeat' (1xxxxxxx + byte) when a byte repeats, otherwise 'as is' (0xxxxxxx + bytes), then 0."""
    b = bytes(bitmap); out = bytearray(); i = 0
    while i < len(b):
        k = 1
        while i + k < len(b) and b[i + k] == b[i] and k < 127: k += 1
        if k >= 3: out += bytes([0x80 | k, b[i]]); i += k
        else:
            j = i + 1
            while j < len(b) and j - i < 127 and not (j + 2 < len(b) and b[j] == b[j + 1] == b[j + 2]): j += 1
            out += bytes([j - i]) + b[i:j]; i = j
    return bytes(out) + b'\0'


def synthetic_font(glyphs):
    """Minimal TNOF file: glyphs = {code: (width, flag, byte)}; the glyph is a ramp column 1..255 (byte = base value) so that each cell can be recognized."""
    table = np.zeros(TABLE_SIZE, '<u4'); data = bytearray()
    for code, (w, flag, val) in glyphs.items():
        bm = bytes(((val + 7 * (r % 5) + 11 * (c % 3)) % 250) + 1 for r in range(H) for c in range(w))
        table[code] = ((w | (0x80 if flag else 0)) << 24) | len(data)
        data += rle_encode(bm)
    head = bytearray(28); head[:4] = b'TNOF'; struct.pack_into('<H', head, 24, H)
    return bytes(head) + table.tobytes() + bytes(data)


GLYPHS = {ord('A'): (7, 0, 10), ord('B'): (9, 0, 40), ord('@'): (11, 0, 70), ord('V'): (10, 1, 100), ord('t'): (6, 1, 130), ord('-'): (4, 0, 160),
           ord(' '): (5, 0, 190), ord('я'): (8, 0, 220), ord('é'): (8, 0, 20), ord(','): (3, 0, 50), ord('x'): (6, 0, 80), ord('$'): (9, 0, 90), ord(';'): (9, 0, 95)}


def synth(**kw): return MessageFont(data=synthetic_font(GLYPHS), **kw)


class TestGlyphs(unittest.TestCase):
    def test_read_rle(self):
        p = synth()
        for code, (w, flag, val) in GLYPHS.items():
            d, width_px, bm = p.glyph(code)
            self.assertEqual((d, width_px, bm.shape), (flag, w, (H, w)), chr(code))
            expected = [((val + 7 * (r % 5) + 11 * (c % 3)) % 250) + 1 for r in range(H) for c in range(w)]
            self.assertEqual(list(bm.reshape(-1)), expected, chr(code))

    def test_header_and_signature(self):
        with self.assertRaises(ValueError): MessageFont(data=b'XXXX' + bytes(DATA_START))
        self.assertEqual(synth().height_px, H)
        self.assertEqual(DATA_START, 28 + 4 * 65536)

    def test_missing_code_takes_the_at_sign(self):
        p = synth()
        self.assertIn(ord('A'), p); self.assertNotIn(ord('z'), p); self.assertNotIn(0x4e2d, p)
        self.assertEqual(p.glyph(ord('z'))[1], 11); self.assertTrue((p.glyph(0x4e2d)[2] == p.glyph(CODE_DEFAULT)[2]).all())
        self.assertEqual(p.width_px('zz'), 22)

    def test_no_hardcoded_character(self):
        """A character added to the font (DQ5, DQ6: other letters) is displayed, without changing anything in the code."""
        g = dict(GLYPHS); g[0x0416] = (13, 0, 33)                       # « Ж »
        p = MessageFont(data=synthetic_font(g))
        self.assertEqual(p.width_px('Ж'), 13); self.assertEqual(p.width_px('ЖЖ'), 26)
        self.assertEqual(synth().width_px('Ж'), 11)                       # absent: the "@"


class TestPlacement(unittest.TestCase):
    def test_advance_width_of_glyph(self):
        p = synth(); self.assertEqual(p.width_px('AB'), 16); self.assertEqual(p.width_px('я'), 8); self.assertEqual(p.width_px(''), 0)

    def test_engine_space_not_the_font_one(self):
        p = synth(space=6); self.assertEqual(p.glyph(32)[1], 5); self.assertEqual(p.width_px('A A'), 7 + 6 + 7)
        self.assertEqual(synth(space=4).width_px('A A'), 7 + 4 + 7)

    def test_tab_and_wide_space(self):
        p = synth(tab_width=15, wide_space=6); self.assertEqual(p.width_px('A\tA'), 7 + 15 + 7); self.assertEqual(p.width_px('A　A'), 7 + 6 + 7)

    def test_glyph_with_flag(self):
        """Placed 1 pixel to the left, advances 2 less (kerning)."""
        p = synth(); cel, end = p.plan('AV')
        self.assertEqual([x for x, _ in cel], [0, 7 - 1]); self.assertEqual(end, 7 + 10 - 2); self.assertEqual(p.width_px('t'), 4)

    def test_line_breaks_do_nothing(self):
        self.assertEqual(synth().width_px('A\nB\rA'), 7 + 9 + 7)

    def test_dollar_and_semicolon(self):
        p = synth(language=1); self.assertEqual(p.width_px('A$A'), 14); self.assertEqual(p.width_px('A;A'), 14)         # neither is drawn (English)
        self.assertEqual(synth(language=2).width_px('A;A'), 7 + 6 + 7)                                                   # ";" is a space for language 2

    def test_letter_spacing(self):
        self.assertEqual(synth(spacing=1).width_px('AB'), 18)

    def test_pixels_one_line(self):
        """The flagged glyph replaces the previous glyph's last pixel (no blending), as in the engine's canvas."""
        p = synth(); a = p.pixels('AV'); P = p.PAD; A = p.glyph(ord('A'))[2]; V = p.glyph(ord('V'))[2]
        self.assertEqual(a.shape, (H, 2 * P + 16))
        self.assertTrue((a[:, P:P + 6] == A[:, :6]).all()); self.assertTrue((a[:, P + 6:P + 16] == V).all())
        self.assertEqual(p.pixels('').shape, (H, 2 * P))


class TestCut(unittest.TestCase):
    def test_a_short_line(self):
        self.assertEqual(synth().wrap_text('AB AB'), ['AB AB'])

    def test_cut_after_last_space(self):
        """"AAA AAA" is 7 x 6 + 6 = 48; with the 2nd space 54; the limit 60 is reached within the 3rd word: wrap after the 2nd space."""
        self.assertEqual(synth().wrap_text('AAA AAA AAA', limit=60), ['AAA AAA ', 'AAA'])
        self.assertEqual(synth().wrap_text('AAA AAA AAA', limit=40), ['AAA ', 'AAA ', 'AAA'])

    def test_word_longer_than_line(self):
        """Without a break point the overflowing character stays on the line; the break leaves an empty line at the end when the text stops right after it (as the engine does)."""
        self.assertEqual(synth().wrap_text('AAAAAA', limit=20), ['AAA', 'AAA', ''])
        self.assertEqual(synth().wrap_text('AAAAAAA', limit=20), ['AAA', 'AAA', 'A'])

    def test_text_line_break(self):
        self.assertEqual(synth().wrap_text('AB\nAB'), ['AB', 'AB']); self.assertEqual(synth().wrap_text('AB\r\nAB'), ['AB', 'AB'])
        self.assertEqual(synth().wrap_text('AAA AAA AAA\nAAA', limit=60), ['AAA AAA ', 'AAA', 'AAA'])

    def test_newline_after_automatic_wrap_is_swallowed(self):
        self.assertEqual(synth().wrap_text('AAAAAAAAAAAA\nB', limit=7 * 12), ['AAAAAAAAAAAA', 'B'])         # the break falls exactly at the end of the line: the line break that follows is swallowed

    def test_dash_is_a_break_point(self):
        p = synth()
        self.assertEqual(p.wrap_text('AAA-AAA-AAA', limit=65), ['AAA-AAA-', 'AAA'])                       # break after a hyphen
        self.assertEqual(p.wrap_text('AAA-AAA', limit=30), ['AAA-', 'AAA'])
        self.assertEqual(p.wrap_text('AAA--AAA', limit=30), ['AAA--A', 'AA'])                             # "--" is not a break point (English)

    def test_width_for_cutting(self):
        p = synth(); self.assertEqual(p.cut_width(';'), 0); self.assertEqual(p.cut_width('$'), 9); self.assertEqual(p.cut_width(' '), 6)
        self.assertEqual(p.cut_width('V'), 8); self.assertEqual(synth(language=2).cut_width(';'), 6)

    def test_default_limit(self):
        self.assertEqual(MessageFont.LIMIT, 410)


def inked_font(glyphs):
    """Font whose glyphs have ink only inside a rectangle: glyphs = {code: (width, flag, top_row, bottom_row, left_column, right_column)} (bounds included)."""
    table = np.zeros(TABLE_SIZE, '<u4'); data = bytearray()
    for code, (w, flag, r0, r1, c0, c1) in glyphs.items():
        bm = bytes(255 if (r0 <= r <= r1 and c0 <= c <= c1) else 0 for r in range(H) for c in range(w))
        table[code] = ((w | (0x80 if flag else 0)) << 24) | len(data); data += rle_encode(bm)
    head = bytearray(28); head[:4] = b'TNOF'; struct.pack_into('<H', head, 24, H)
    return MessageFont(data=bytes(head) + table.tobytes() + bytes(data))


class TestKerning(unittest.TestCase):
    """a pair whose optical gap (empty columns between the ink, row by row) exceeds 3 is tightened down to 3 (at most 4 pixels); nothing else moves."""
    F = inked_font({ord('A'): (8, 0, 0, 23, 0, 5), ord('B'): (8, 0, 0, 23, 2, 7), ord('C'): (8, 0, 0, 23, 0, 6), ord('D'): (8, 0, 0, 23, 1, 7),
                    ord('F'): (8, 0, 0, 23, 0, 2), ord('-'): (8, 0, 10, 11, 1, 6),            # F: a stem; "-": two rows in the middle
                    ord('P'): (8, 0, 0, 3, 0, 7), ord('o'): (8, 0, 8, 23, 0, 5),                 # P: a bar at the top; o: lower, with no neighboring row
                    ord('*'): (8, 0, 0, 23, 0, 5), ord('V'): (8, 1, 0, 23, 1, 6), ord('Z'): (8, 0, 0, 23, 0, 1), ord(' '): (5, 0, 0, 0, 0, 0)})

    def test_gap_above_three_is_brought_back_to_three(self):
        F = self.F; k = lambda a, b: F.kern(ord(a), ord(b))
        self.assertEqual(k('A', 'B'), 1, 'A ends 2 columns before its cell, B starts at the 3rd: 4 empty columns -> 3')
        self.assertEqual(k('A', 'C'), 0); self.assertEqual(k('C', 'D'), 0, 'ecart 1 + 1 = 2 : intact')
        self.assertEqual(k('F', '-'), 3, 'stem of F 5 columns from the hyphen: only the rows of the hyphen are looked at (6 empty columns -> 3)')
        self.assertEqual(k('A', 'A'), 0, 'ecart 2 : intact')

    def test_no_contact_between_rows_far_apart(self):
        self.assertEqual(self.F.kern(ord('P'), ord('o')), 0, 'the bar of the P is far from the rows of the o: nothing to tighten')

    def test_limits(self):
        F = self.F
        self.assertEqual(F.kern(ord('*'), ord('B')), 0, '"*" (speaker mark) keeps the game\'s gap')
        self.assertEqual(F.kern(ord('Z'), ord('B')), 4, 'gap of 8 empty columns: 5 too many, but at most 4 pixels')

    def test_plan_and_width(self):
        F = self.F
        cells, end = F.plan('AB'); self.assertEqual([x for x, _ in cells], [0, 8 - 1]); self.assertEqual(end, 8 + 8 - 1)
        self.assertEqual(F.width_px('AB'), 15); self.assertEqual(F.width_px('A B'), 8 + 6 + 8, 'after a space: no kerning')
        self.assertEqual(F.width_px('A\u3000B'), 8 + 6 + 8)
        self.assertEqual(F.cut_width('A') + F.cut_width('B'), 16, 'line breaking (like CTextAutoReturn) does not know about the kerning')

    def test_flag_glyph(self):
        F = self.F
        a = F.kern(ord('V'), ord('B')); b = F.kern(ord('B'), ord('V'))
        self.assertGreaterEqual(a, 0); self.assertGreaterEqual(b, 0)                                  # (flagged glyph: the computation accounts for its one-pixel shift; no error)

    def test_advance(self):
        F = self.F; self.assertEqual(F.advance(ord('A')), 8); self.assertEqual(F.advance(ord('V')), 6)
        for c in (0x09, 0x0a, 0x0d, 0x20, 0x3000, 0x3b, 0x24): self.assertIsNone(F.advance(c), hex(c))


class TestExtraction(unittest.TestCase):
    def test_extract(self):
        with tempfile.TemporaryDirectory() as d:
            apk = os.path.join(d, 'apks'); os.makedirs(apk); cache = os.path.join(d, 'cache'); data = synthetic_font(GLYPHS)
            with zipfile.ZipFile(os.path.join(apk, 'split_UnityDataAssetPack.apk'), 'w') as z: z.writestr('assets/English.font', data)
            logfile = []
            self.assertTrue(extract_message_font(apk, cache, logfile.append))
            with open(os.path.join(cache, 'ui_messages.font'), 'rb') as f: self.assertEqual(f.read(), data)
            self.assertTrue(extract_message_font(os.path.join(d, 'absent'), cache, logfile.append)); self.assertEqual(logfile, [])        # already there: nothing to reread
            self.assertEqual(MessageFont(os.path.join(cache, 'ui_messages.font')).width_px('AB'), 16)

    def test_absent_or_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            logfile = []; self.assertFalse(extract_message_font(os.path.join(d, 'rien'), os.path.join(d, 'c1'), logfile.append)); self.assertEqual(len(logfile), 1)
            apk = os.path.join(d, 'apks'); os.makedirs(apk)
            with zipfile.ZipFile(os.path.join(apk, 'split_UnityDataAssetPack.apk'), 'w') as z: z.writestr('assets/English.font', b'PAS UNE POLICE')
            self.assertFalse(extract_message_font(apk, os.path.join(d, 'c2'), logfile.append)); self.assertFalse(os.path.exists(os.path.join(d, 'c2', 'ui_messages.font')))


# ---------------------------------------------------------------- real font and real engine (optional)
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class TestRealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        cls.tmp = tempfile.mkdtemp()
        assert extract_message_font(APK, cls.tmp, print), 'font not found in the data pack'
        cls.mp = MessageFont(os.path.join(cls.tmp, 'ui_messages.font'))
        cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(dir=cls.tmp)); cls.eng.load_save(1)
        for i in range(80):                                             # a few frames: the engine sets its text parameters when a dialogue opens
            cls.eng.step(0, 0x10 if i % 9 == 5 else 0)
            cv = cls.eng.read_canvas()
            if i > 30 and cv is not None and cv.max() > 100: break
        c = cls.eng.core; cls.c = c; cls.obj = cls.eng.obj_msg
        c.mem_w(cls.obj + 0x38, struct.pack('<3H', 6, 6, 15))           # space, wide space, tab (game values)

    def test_font_has_the_patch_letters(self):
        for ch in 'Je suis Ragnar éèêàçÉ,.!?' + 'яиЯ':
            self.assertIn(ord(ch), self.mp, ch)
        self.assertEqual(self.mp.height_px, 24)

    def _render_in_engine(self, text, x=6, y=0):
        c, obj, eng = self.c, self.obj, self.eng
        buffer = struct.unpack('<Q', c.mem(obj + 0x10, 8))[0]
        c.mem_w(buffer, bytes(512 * 512))                               # empty canvas: each test starts from zero
        c.mem_w(obj + 0x46, struct.pack('<H', x)); c.mem_w(obj + 0x48, struct.pack('<H', y))
        put = c.export('_ZN9SDrawCTRL7PutCharEt')
        for ch in text: c.call(put, obj, ord(ch), label='putchar')
        cv = eng.read_canvas(); end = struct.unpack('<H', c.mem(obj + 0x46, 2))[0]
        return cv[y:y + 24].copy(), end - x

    def _compare(self, text):
        x = 6; was_seen, advance = self._render_in_engine(text, x)
        a = self.mp.pixels(text)                                       # the writing position is at column PAD
        expected = np.zeros_like(was_seen); w = min(a.shape[1], was_seen.shape[1] - (x - self.mp.PAD)); expected[:, x - self.mp.PAD:x - self.mp.PAD + w] = a[:, :w]
        self.assertEqual(advance, self.mp.width_px(text), text)
        self.assertTrue((was_seen == expected).all(), 'different pixels for %r: %d' % (text, int((was_seen != expected).sum())))

    def test_pixels_like_engine(self):
        for t in ('Quelle joie de vous revoir, Ragnar !', "J'espère que vous vous êtes bien reposé.", 'Pourquoи cеtte guеяяе, mon fиls ?', 'яиЯ', 'VWtvwy Vive la Yougoslavie', 'a;b c$d', 'Où ça ? Là-bas… »',
                  '\xa0Ça va ?\t.'):
            with self.subTest(t): self._compare(t)

    def test_kerned_pairs_like_the_engine(self):
        """the engine hook and `MessageFont.plan` tighten the same pairs (identical pixels and advance); after a space, nothing."""
        for t in ('Ouaf-ouaf.', "Tu viens ? To-to, L'ami, très-fort, peut-être", 'Ouaf -ouaf', 'ft- ft -f', '*: Tout-à-fait'):
            with self.subTest(t):
                self._compare(t)
        t = 'Ouaf-ouaf. Tu To L\'ami'
        self.assertLess(self.mp.width_px(t), sum(self.mp.cut_width(ch) for ch in t), 'at least one pair tightened')
        self.assertEqual(self.mp.width_px('Ouaf -ouaf'), self.mp.width_px('Ouaf') + 6 + self.mp.width_px('-ouaf'), 'nothing is tightened across a space')
        self.assertLess(self.mp.width_px('Ouaf-ouaf'), self.mp.width_px('Ouaf') + self.mp.width_px('-ouaf'), 'f- is tightened')

    def test_all_glyphs_like_the_engine(self):
        """Every glyph of the font (all the codes the table knows), in chunks: the pixels and the advance are the engine's."""
        codes = [k for k in range(TABLE_SIZE) if k in self.mp and k not in (0x09, 0x0a, 0x0d, 0x20, 0x24, 0x3b, 0x3000, 0x1b)]
        step = 24
        for i in range(0, len(codes), step):
            t = ''.join(chr(k) for k in codes[i:i + step])
            if self.mp.width_px(t) > 500: continue
            with self.subTest(i=i): self._compare(t)

    def _engine_lines(self, seg):
        """Lines of a text as the engine's `CTextAutoReturn::AutoReturn` breaks them (empty lines and trailing spaces ignored: like `wrap_like_the_game`)."""
        c = self.c
        if not hasattr(self, '_ar'):
            type(self)._ar = (c.export('_ZN15CTextAutoReturn10AutoReturnEPtPKh'), c.malloc(0x80), c.malloc(0x8000), c.malloc(0x4000)); c.mem_w(self._ar[1], bytes(0x80))
        ar, obj, output, input_buf = self._ar
        c.mem_w(input_buf, seg.encode('utf-8') + b'\0'); c.mem_w(output, bytes(0x400)); c.call(ar, obj, output, input_buf, label='AutoReturn')
        words = struct.unpack('<2048H', c.mem(output, 0x1000)); end = words.index(0) if 0 in words else len(words)
        return [x.rstrip(' ') for x in ''.join(chr(u) for u in words[:end]).replace('\u328a', '').replace('\r', '').split('\n') if x]

    def _own_lines(self, seg): return [x.rstrip(' ') for x in self.mp.wrap_text(seg) if x]

    def test_cut_like_auto_return(self):
        """Game messages (about 1 in 7 of each file, per page): the lines are the engine's."""
        import re
        eng = self.eng
        z = zipfile.ZipFile(os.path.join(APK, 'split_UnityDataAssetPack.apk'))
        files = sorted(int(re.search(r'b(\d{7})\.mpt', n).group(1)) for n in z.namelist() if re.search(r'assets/msg/en/b\d{7}\.mpt$', n))
        sample = []
        for f in files:
            for r in range(0, 1000, 7):
                t = eng.sensor.model(f + r)
                if t is not None: sample.append((f + r, t))
        self.assertGreater(len(sample), 200)
        checked = 0
        for mid, t in sample[:: max(1, len(sample) // 400)]:
            for seg in t.split('\u3221'):
                seg = seg.rstrip('\n')
                if not seg.strip(): continue
                self.assertEqual(self._own_lines(seg), self._engine_lines(seg), 'message %d : %r' % (mid, seg[:80]))
                checked += 1
        self.assertGreater(checked, 200)

    def test_symbols_cut_like_auto_return(self):
        """"$" (width counted for the wrap, not drawn), ";" (zero width), hyphens, wide spaces, Russian letters, too-long word: texts constructed so that the break falls near these characters."""
        base = ["Ragnar$ obtient ;l'herbe ;médicinale et un bâton de ;cyprès.", 'Pourquoи cеtte guеяяе ? Mon fиls, яeviens-moi vivaиt, sиnon je serai très triste !', 'Va-t-en, petit-fils-du-roi-qui-pars-là-bas--vite !',
                'A\u3000B C\u3000D E\u3000F G\u3000H I\u3000J K\u3000L M\u3000N O\u3000P Q\u3000R S\u3000T', 'x' * 120 + ' fin', 'Tsar$$ Stepan$ ;;; ' * 8]
        checked = 0
        for t in base:
            for k in range(0, 24):
                seg = ('éé ' * (k % 6)) + t
                with self.subTest(seg=seg[:50]): self.assertEqual(self._own_lines(seg), self._engine_lines(seg))
                checked += 1
        self.assertGreater(checked, 100)


if __name__ == '__main__':
    unittest.main(verbosity=2)
