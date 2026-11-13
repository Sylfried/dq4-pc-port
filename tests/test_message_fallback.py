"""`Engine.read_message` ("simple menus" fallback, without ui_layout.json) reads the message canvas as a circular texture of 512 lines (Unity's REPEAT): the engine's scroll
grows without bound, after a dozen lines it exceeded 512 and the text became empty. Fake engine (simulated memory and canvas), without map or data.
    python3 tests/test_message_fallback.py"""
import os, struct, sys, types, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import engine as ENGINE

L, OBJ = 0x100000, 0x200000


def dummy_engine(scroll, lines=4, lh=28, canvas='ok'):
    """Fake engine where only `read_canvas` and the reading of the settings (number of lines, line height, scroll) exist."""
    val = {L + 0x2523a0: lines - 1, OBJ + 0x42: lh, OBJ + 0x4a: scroll}
    m = types.SimpleNamespace(L=L, obj_msg=OBJ, core=types.SimpleNamespace(mem=lambda ad, n: struct.pack('<h', val[ad])))
    img = np.repeat((np.arange(ENGINE.CANVAS_H) % 251 + 1).astype(np.uint8)[:, None], ENGINE.CANVAS_L, axis=1)       # each line r carries the value r % 251 + 1 (never 0)
    m.read_canvas = lambda: img if canvas == 'ok' else None
    return m, img


def lines(sub): return [int(v) for v in sub[:, 0]]


class Fold(unittest.TestCase):
    def read(self, scroll, **kw):
        m, img = dummy_engine(scroll, **kw); return ENGINE.Engine.read_message(m), img

    def expected(self, is_first, n): return [(r % ENGINE.CANVAS_H) % 251 + 1 for r in range(is_first, is_first + n)]

    def test_start(self):
        sub, _ = self.read(-3); self.assertEqual(sub.shape, (112, ENGINE.CANVAS_L)); self.assertEqual(lines(sub), self.expected(0, 112))

    def test_in_canvas(self):
        sub, _ = self.read(100); self.assertEqual(lines(sub), self.expected(103, 112))

    def test_end_of_canvas_wraps_to_start(self):
        sub, _ = self.read(450)                                                               # lines 453 to 511 then 0 to 52 (before: nothing after line 511)
        self.assertEqual(lines(sub), self.expected(453, 59) + self.expected(0, 53)); self.assertTrue((sub != 0).all())

    def test_scroll_beyond_512(self):
        for scroll in (509, 1000, 5000, 30000):
            sub, _ = self.read(scroll); self.assertEqual(lines(sub), self.expected((scroll + 3) % 512, 112), scroll); self.assertTrue((sub != 0).all(), scroll)

    def test_small_negative_scroll_unchanged(self):
        sub, _ = self.read(-10); self.assertEqual(lines(sub), self.expected(0, 112))

    def test_inconsistent_settings_use_default_values(self):
        sub, _ = self.read(200, lines=20); self.assertEqual(lines(sub), self.expected(0, 112))                      # (4 lines of 28, scroll -3)

    def test_other_line_count(self):
        sub, _ = self.read(300, lines=3, lh=40); self.assertEqual(sub.shape[0], 120); self.assertEqual(lines(sub), self.expected(303, 120))

    def test_without_canvas(self):
        m, _ = dummy_engine(0, canvas=None); self.assertIsNone(ENGINE.Engine.read_message(m))

    def test_canvas_is_not_modified(self):
        m, img = dummy_engine(450); before = img.copy(); ENGINE.Engine.read_message(m); self.assertTrue((img == before).all())


if __name__ == '__main__':
    unittest.main(verbosity=1)
