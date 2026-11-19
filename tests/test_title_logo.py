"""Test of the title screen logo and subtitle enlarged 1.5 times (INTENDED DEVIATION from the APK).

Part 1 (without the engine): the pure functions of `pre_game` (`upscale_logo`, `logo_factor`): x and y are multiplied around a fixed point, the depth does not change, the factor is reduced
in a window that is too narrow (the logo never overflows) and never drops below 1.

Part 2 (real rendering, Mesa without a screen): the viewer is launched with the original engine at 16:9, 4:3 and 21:9, at frame 770 (logo, subtitle, "Touchez l'ecran" at the maximum of its blinking),
and once with DQ_LOGO_SCALE=1 (the APK's logo, at 16:9) for comparison. We measure on the captures:
  1. the width of the "DRAGON QUEST" lettering (red-violet pixels) is 1.5 times that of the APK (to within 3%), at all formats (in window heights);
  2. the logo stays within the window (no lettering pixel on the 1% edge);
  3. the bottom of the "IV" stays above the top of "Touchez l'ecran" (area computed like `Game._ui_reference`: 228 units below the center, height 41.48, scale H / 800 x UI_ZOOM) by at least 2% of the height;
  4. the top of the logo stays within the window (more than 5% from the top edge);
  5. the logo is horizontally centered (to within 1% of the width).

    python3 tests/test_title_logo.py --apk "<patched APK folder>" --saves "<saves folder>" --cache "<interface cache folder, with ui_layout.json and ap_taptostart.png>"
(or the DQ_APK, DQ_SAVES, DQ_UI_CACHE variables; without them only part 1 runs). Part 2 takes about 2 minutes.
"""
import argparse, json, os, re, subprocess, sys, tempfile, unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
from dq456_pc.menus import pre_game as AP

FORMATS = ((1280, 720), (1280, 800), (1024, 768), (2560, 1080))              # 16:9,, 4:3, 21:9
FRAME = 770
ARGS = None; REST = sys.argv[1:]
if __name__ == '__main__':
    _ap = argparse.ArgumentParser(); _ap.add_argument('--apk'); _ap.add_argument('--saves'); _ap.add_argument('--cache')
    _a, REST = _ap.parse_known_args()
    if _a.apk and _a.saves and _a.cache: ARGS = _a


class Functions(unittest.TestCase):
    def test_upscale_x_and_y_around_fixed_point(self):
        loc = np.array([[-4.5, 0.8, 0.0], [4.5, 3.7, 0.0], [-1.4, -0.87, 0.062]], np.float32)
        r = AP.upscale_logo(loc, 2.0, 0.7)
        np.testing.assert_allclose(r[:, 0], loc[:, 0] * 2.0, atol=1e-5)
        np.testing.assert_allclose(r[:, 1], 0.7 + 2.0 * (loc[:, 1] - 0.7), atol=1e-5)
        np.testing.assert_array_equal(r[:, 2], loc[:, 2])                            # depth (layer order) unchanged
        self.assertEqual(float(loc[0, 0]), -4.5)                                    # the input is not modified

    def test_fixed_point_does_not_move(self):
        r = AP.upscale_logo(np.array([[0.0, 0.7, 0.0]], np.float32), 2.0, 0.7)
        self.assertAlmostEqual(float(r[0, 1]), 0.7, places=5); self.assertAlmostEqual(float(r[0, 0]), 0.0, places=5)

    def test_wanted_factor_when_window_wide_enough(self):
        for wid in (0.1, 0.25, 0.40, 0.60): self.assertEqual(AP.logo_factor(wid), 1.5)

    def test_factor_reduced_in_narrow_window(self):
        for wid in (0.7, 0.8, 0.9):
            f = AP.logo_factor(wid); self.assertLess(f, 1.5); self.assertGreaterEqual(f, 1.0); self.assertLessEqual(f * wid, AP.LOGO_WIDTH_MARGIN + 1e-9)             # the enlarged logo fits within 96% of the width
        self.assertEqual(AP.logo_factor(1.2), 1.0)                                  # never smaller than the APK's, even if the original logo already overflows

    def test_factor_without_measure(self):
        self.assertEqual(AP.logo_factor(0.0), 1.5)

    def test_constants(self):
        self.assertEqual(AP.LOGO_SCALE, 1.5); self.assertEqual(set(AP.LOGO_MODELS), {8900, 8901})              # 8901: logo + subtitle; 8900: animated glint


def measures(path):
    """Dict: lettering width (in window heights), x0 / x1 / y0 (window fractions), bottom of the "IV" (fraction of the height, central band), width / height."""
    a = np.asarray(Image.open(path).convert('RGB')).astype(int); h, w = a.shape[:2]; R, G, B = a[..., 0], a[..., 1], a[..., 2]
    letters = (R > 170) & (G < 60) & (B > 40) & (B < 140) & (R - B > 70)             # red-violet lettering of "DRAGON QUEST"
    yl, xl = np.nonzero(letters)
    if len(xl) < 500: return None
    golden = (R > 190) & (G > 90) & (G < 200) & (B < 90) & (R - B > 130)                # gold of the "IV"
    band = np.zeros_like(golden); band[:, int(w / 2 - 0.07 * h):int(w / 2 + 0.07 * h)] = True       # central band: the "IV" alone (the castle island starts further right)
    band[:int(0.3 * h)] = False
    yi, _ = np.nonzero(golden & band)
    return dict(w=w, h=h, larg_h=(xl.max() - xl.min()) / h, x0=xl.min() / w, x1=xl.max() / w, y0=yl.min() / h, iv_bottom=(yi.max() / h if len(yi) else None), center=((xl.min() + xl.max()) / 2 - w / 2) / w)


def prompt_top(ui_zoom):
    """Top of "Touchez l'ecran" as a fraction of the window height: center 228 units below the screen center, height 41.48, scale H / 800 x UI_ZOOM (Game._ui_reference, title with no window open)."""
    return 0.5 + (AP.TT_BOTTOM - AP.TT_H / 2) * ui_zoom / 800.0


@unittest.skipIf(ARGS is None and not (os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES') and os.environ.get('DQ_UI_CACHE')), 'original engine: --apk, --saves and --cache required')
class TitleRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apk = ARGS.apk if ARGS else os.environ['DQ_APK']; saves = ARGS.saves if ARGS else os.environ['DQ_SAVES']; cache = ARGS.cache if ARGS else os.environ['DQ_UI_CACHE']
        src = _paths.source('window.py'); cls.zoom = float(re.search(r'^UI_ZOOM = ([0-9.]+)', src, re.M).group(1))
        cls.tmp = tempfile.mkdtemp(prefix='titre_logo_'); rg = os.path.join(cls.tmp, 'settings.json'); json.dump({}, open(rg, 'w'))
        def launch(w, h, name_str, extra_env):
            shot = os.path.join(cls.tmp, name_str + '.png')
            cmd = [sys.executable, '-W', 'ignore', '-m', 'dq456_pc', '--apk', apk, '--saves-read', saves, '--saves-write', os.path.join(cls.tmp, 'sv'), '--settings', rg, '--slot', '0', '--no-logos',
                   '--cache', cache, '--msaa', '0', '--width', str(w), '--height', str(h), '--no-preparation', '--no-sound', '--shot', shot, '--images', '100000', '--test-keys', '', '--shots-loop', str(FRAME)]
            env = dict(os.environ, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent', **extra_env)
            subprocess.run(cmd, cwd=os.path.join(HERE, '..'), env=env, timeout=900, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return measures(os.path.join(cls.tmp, '%s_b%d.png' % (name_str, FRAME)))
        cls.origin = launch(1280, 720, 'origine', {'DQ_LOGO_SCALE': '1'})
        cls.res = {f: launch(f[0], f[1], 'titre_%dx%d' % f, {}) for f in FORMATS}

    def test_screenshots_taken(self):
        self.assertIsNotNone(self.origin, 'lettering not found on the APK capture')
        for f in FORMATS: self.assertIsNotNone(self.res[f], 'lettrage introuvable a %dx%d' % f)

    def test_one_and_a_half_times_wider_at_all_formats(self):
        for f in FORMATS:
            r = self.res[f]['larg_h'] / self.origin['larg_h']
            self.assertAlmostEqual(r, 1.5, delta=0.05, msg='rapport de largeur %.3f a %dx%d' % ((r,) + f))

    def test_logo_stays_in_window(self):
        for f in FORMATS:
            r = self.res[f]; self.assertGreater(r['x0'], 0.01, f); self.assertLess(r['x1'], 0.99, f); self.assertGreater(r['y0'], 0.05, f)

    def test_logo_is_centered(self):
        for f in FORMATS: self.assertLess(abs(self.res[f]['center']), 0.01, f)

    def test_iv_does_not_cover_touch_the_screen(self):
        limit = prompt_top(self.zoom) - 0.02
        for f in FORMATS:
            self.assertIsNotNone(self.res[f]['iv_bottom'], f)
            self.assertLess(self.res[f]['iv_bottom'], limit, 'bottom of the IV at %.3f H, top of the tap-to-start text at %.3f H (%dx%d)' % ((self.res[f]['iv_bottom'], prompt_top(self.zoom)) + f))

    def test_same_placement_at_all_formats(self):
        for lookup_key in ('larg_h', 'y0', 'iv_bottom'):
            v = [self.res[f][lookup_key] for f in FORMATS]; self.assertLess(max(v) - min(v), 0.02, (lookup_key, v))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + REST)
