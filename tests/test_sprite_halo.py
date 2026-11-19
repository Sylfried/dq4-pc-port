"""the halo of the heroes' sprites is removed, and the partly transparent pixels enclosed by the body are opaque.

Without it, a purple outline shows around the characters, Alina looks partly transparent and Kiryl has a hole in his torso.
The hero sheets (h100 to h127) carry a halo of alpha 1 to 120 around the body; a few pixels of the same kind are inside the body (between an arm and the chest: 7 in Kiryl's sheet, h112).

1. Without APK: `hd.outside` (flood from the edge of each cell), `clean_sheet` on small sheets.
2. With the APK (DQ_APK): the 11 hero sheets come out with binary alpha, the body never loses a pixel, Kiryl's enclosed pixels are opaque.
    DQ_APK=<patched APKs folder> python3 tests/test_sprite_halo.py
"""
import os, sys, tempfile, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.world import hd as HD

APK = os.environ.get('DQ_APK')


def sheet(rows):
    """Alpha rows ('.' 0, 'h' halo 60, 'B' body 230) -> RGBA sheet, magenta halo, green body."""
    a = np.zeros((len(rows), len(rows[0]), 4), np.uint8)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            a[y, x] = {'.': (255, 0, 255, 0), 'h': (255, 0, 255, 60), 'B': (20, 200, 30, 230)}[ch]
    return a


class Outside(unittest.TestCase):
    def test_enclosed_pixel_is_not_outside(self):
        free = np.array([[1, 1, 1, 1, 1], [1, 0, 0, 0, 1], [1, 0, 1, 0, 1], [1, 0, 0, 0, 1], [1, 1, 1, 1, 1]], bool)
        out = HD.outside(free)
        self.assertFalse(out[2, 2]); self.assertTrue(out[0, 0]); self.assertEqual(int(out.sum()), 16)

    def test_cell_edge_counts_as_outside(self):
        """The flood starts from the edge of each cell: a gap open on the side of the next cell is outside, even if that cell is full."""
        free = np.zeros((3, 6), bool); free[1, 1] = free[1, 2] = True
        self.assertFalse(HD.outside(free)[1, 1], 'image entiere : entoure')
        self.assertTrue(HD.outside(free, (3, 3))[1, 1], 'per cell: open on the edge of its cell')


class Clean(unittest.TestCase):
    def test_halo_removed_hole_filled(self):
        a = sheet(['.....',
                   '.hhh.',
                   'hBBBh',
                   'hBhBh',
                   'hBBBh',
                   '.hhh.'])
        c, cleaned = HD.clean_sheet(a)
        self.assertTrue(cleaned)
        al = c[..., 3]
        self.assertEqual(sorted(set(al.ravel().tolist())), [0, 255], 'alpha binaire')
        self.assertEqual(int(al[3, 2]), 255, 'the pixel enclosed by the body becomes opaque (no more hole)')
        self.assertEqual(int(al[1, 1]), 0); self.assertEqual(int(al[2, 0]), 0)       # the halo around: gone
        self.assertEqual(int((al == 255).sum()), 9)

    def test_binary_sheet_untouched(self):
        a = sheet(['.B.', 'BBB']); a[..., 3] = np.where(a[..., 3] > 0, 255, 0)
        c, cleaned = HD.clean_sheet(a)
        self.assertFalse(cleaned); self.assertIs(c, a)

    def test_soft_trial_still_available(self):
        """(the soft halo stays reachable with soft=True, no longer used by the window.)"""
        a = sheet(['hBh']); c, _ = HD.clean_sheet(a, soft=True)
        self.assertEqual(c[0, :, 3].tolist(), [60, 255, 60]); self.assertEqual(c[0, 0, :3].tolist(), [20, 200, 30])

    def test_window_uses_the_hard_cleaning(self):
        src = open(os.path.join(HERE, '..', 'dq456_pc', 'window', 'field.py'), encoding='utf-8').read()
        self.assertIn("arr = HD.clean_sheet(arr, cell=(geo['width'], geo['height']))[0]", src)
        self.assertNotIn('clean_sheet(arr, soft=True)', src)
        self.assertGreaterEqual(HD.VERSION, 5, 'the HD caches made with the soft halo are redone')


@unittest.skipUnless(APK, 'APK: DQ_APK=<folder of the patched APKs>')
class RealSheets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.world import data as DO
        cls.d = DO.Data(os.path.join(APK, 'split_UnityDataAssetPack.apk'), tempfile.mkdtemp(prefix='halo_'), log=lambda *a: None)

    def test_heroes(self):
        seen = 0
        for i in range(100, 128):
            a = self.d.sheet(i)
            if a is None: continue
            g = HD.sheet_geometry(i, a); c, cleaned = HD.clean_sheet(a, cell=(g['width'], g['height']))
            if not cleaned: continue
            seen += 1
            al = c[..., 3]
            self.assertFalse(((al > 0) & (al < 255)).any(), 'h%d : plus de pixel a moitie transparent' % i)
            self.assertTrue((al[a[..., 3] >= 128] == 255).all(), 'h%d: the body is kept' % i)
        self.assertGreaterEqual(seen, 10)

    def test_kiryl_torso(self):
        a = self.d.sheet(112); c, _ = HD.clean_sheet(a, cell=(24, 32))
        for y, x in ((2 * 32 + 16, 2 * 24 + 7), (2 * 32 + 17, 2 * 24 + 8), (2 * 32 + 17, 2 * 24 + 9)):
            self.assertLess(int(a[y, x, 3]), 128, (y, x))                         # (half transparent in the sheet...)
            self.assertEqual(int(c[y, x, 3]), 255, (y, x))                        # (...opaque now: no hole in the chest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
