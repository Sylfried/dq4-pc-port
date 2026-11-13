"""Test of the title screen centering on the real RENDERING: the logo and the scenery stay centered.

The viewer is launched (original engine, Mesa rendering without a screen; before the fix, the map's 16/9 bounds slid the title camera by 4.5 units when the "Center the camera"
option (centering on the player) was set to "No", an option since removed) at three formats (16:9 of 1430 x 815, 4:3, 21:9), and we measure on the capture of frame 700 (dragon above the logo, before "Touchez l'ecran"):
  1. the centroid of the logo (red-violet lettering pixels) is in the middle of the window, to within a few pixels: horizontal offset / window height < 0.03 (before the fix: 0.29);
  2. this offset is the same (to within 0.004) at all formats: the logo placement is the game's for the central portrait frame, whatever the window format;
  3. no asymmetric black band: the 8 columns of each edge contain no black pixel (the sky fills the whole window);
  4. the castle (orange island) is to the right of the logo, at the same distance (in window heights, to within 0.01) at all formats.

    python3 tests/test_title_centering.py --apk "<patched APK folder>" --saves "<saves folder>" --cache "<interface cache folder, with ui_layout.json>"
(or the DQ_APK, DQ_SAVES, DQ_UI_CACHE variables; without them the tests are skipped). A test takes about 40 s per format.
"""
import argparse, json, os, subprocess, sys, tempfile, unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS = ((1430, 815), (1024, 768), (2560, 1080))
FRAME = 700
ARGS = None; REST = sys.argv[1:]
if __name__ == '__main__':
    _ap = argparse.ArgumentParser(); _ap.add_argument('--apk'); _ap.add_argument('--saves'); _ap.add_argument('--cache')
    _a, REST = _ap.parse_known_args()
    if _a.apk and _a.saves and _a.cache: ARGS = _a


def measures(path):
    """(horizontal offset of the logo, logo -> island gap, black edge columns), in window heights / pixels."""
    a = np.asarray(Image.open(path).convert('RGB')).astype(int); h, w = a.shape[:2]; R, G, B = a[..., 0], a[..., 1], a[..., 2]
    logo = (R > 170) & (G < 60) & (B > 40) & (B < 140) & (R - B > 70)             # red-violet lettering of the logo
    island = (R > 200) & (G > 80) & (G < 150) & (B < 70) & (R - B > 150)             # orange underside of the castle island
    island[:int(0.66 * h)] = False                                                    # (the island is in the bottom third; higher up, dragon wings and golden edges of the logo are also orange)
    yl, xl = np.nonzero(logo); yi, xi = np.nonzero(island)
    if len(xl) < 500 or len(xi) < 200: return None
    black = int(((a[:, :8].sum(axis=2) < 12).sum()) + ((a[:, -8:].sum(axis=2) < 12).sum()))
    return (xl.mean() - w / 2) / h, (xi.mean() - xl.mean()) / h, black


@unittest.skipIf(ARGS is None and not (os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES') and os.environ.get('DQ_UI_CACHE')), 'original engine: --apk, --saves and --cache required')
class TitleCentering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apk = ARGS.apk if ARGS else os.environ['DQ_APK']; saves = ARGS.saves if ARGS else os.environ['DQ_SAVES']; cache = ARGS.cache if ARGS else os.environ['DQ_UI_CACHE']
        cls.tmp = tempfile.mkdtemp(prefix='titre_centrage_'); rg = os.path.join(cls.tmp, 'settings.json')
        json.dump({}, open(rg, 'w'))             # default settings (there is no "Center the camera" option: the camera is always centered, the title is exempt from it)
        env = dict(os.environ, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent'); cls.res = {}
        for (w, h) in FORMATS:
            shot = os.path.join(cls.tmp, 'titre_%dx%d.png' % (w, h))
            cmd = [sys.executable, '-W', 'ignore', '-m', 'dq4_pc', '--apk', apk, '--saves-read', saves, '--saves-write', os.path.join(cls.tmp, 'sv'), '--settings', rg, '--slot', '0', '--no-logos',
                   '--cache', cache, '--msaa', '0', '--width', str(w), '--height', str(h), '--no-preparation', '--no-sound', '--shot', shot, '--images', '100000', '--test-keys', '', '--shots-loop', str(FRAME)]
            subprocess.run(cmd, cwd=os.path.join(HERE, '..'), env=env, timeout=900, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cls.res[(w, h)] = measures(os.path.join(cls.tmp, 'titre_%dx%d_b%d.png' % (w, h, FRAME)))

    def test_screenshot_taken_at_each_format(self):
        for f in FORMATS: self.assertIsNotNone(self.res[f], 'logo or island not found on the capture %dx%d' % f)

    def test_logo_in_the_middle(self):
        for f in FORMATS: self.assertLess(abs(self.res[f][0]), 0.03, 'centroid of the logo off center at %dx%d: %.3f heights' % (f + (self.res[f][0],)))

    def test_same_placement_at_all_formats(self):
        d = [self.res[f][0] for f in FORMATS]; self.assertLess(max(d) - min(d), 0.004, d)

    def test_no_black_band_at_edges(self):
        for f in FORMATS: self.assertEqual(self.res[f][2], 0, 'black pixels at the edges at %dx%d' % f)

    def test_island_right_of_logo_same_distance(self):
        e = [self.res[f][1] for f in FORMATS]
        for x in e: self.assertGreater(x, 0.05)
        self.assertLess(max(e) - min(e), 0.01, e)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + REST)
