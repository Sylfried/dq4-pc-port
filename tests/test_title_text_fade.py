"""Title screen: "Touchez l'ecran" and the copyright line fade out with the screen.

The game's front fade plane (packet 9 without bit 14, "FadeForMenu", Overlay queue) covers everything, the interface included.
The port drew TapToStart (pre_game.TitleTouch) after that plane: when A was pressed during the title animation, the screen
faded to black but the two texts stayed bright on top of it.

Part 1 (no engine): in Game.on_draw, the title texts are drawn before the front fade plane.
Part 2 (real engine, Mesa without a screen): the title runs, A is pressed at loop frame 1500 (sunset, both texts shown);
before the press both texts are bright, 28 frames later (fade almost black) both are as dark as the rest of the screen.

    python3 tests/test_title_text_fade.py --apk "<patched APK folder>" --saves "<saves folder>" --cache "<interface cache folder>"
(or the DQ_APK, DQ_SAVES and DQ_UI_CACHE variables; without them only part 1 runs). Part 2 takes about 2 minutes.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
from dq456_pc.menus import pre_game as AP

PRESS, BEFORE, DARK = 1500, 1496, 1528           # loop frames: A pressed, last frame before it, fade almost black (measured: screen mean 6 / 255)
ARGS = None; REST = sys.argv[1:]
if __name__ == '__main__':
    _ap = argparse.ArgumentParser(); _ap.add_argument('--apk'); _ap.add_argument('--saves'); _ap.add_argument('--cache')
    _a, REST = _ap.parse_known_args()
    ARGS = _a
APK = (ARGS.apk if ARGS else None) or os.environ.get('DQ_APK'); SAVES = (ARGS.saves if ARGS else None) or os.environ.get('DQ_SAVES')
CACHE = (ARGS.cache if ARGS else None) or os.environ.get('DQ_UI_CACHE') or _paths.ui_cache(None)          # (run_tests.sh gives --apk and --saves, and the cache through DQ_UI_CACHE)


class DrawOrder(unittest.TestCase):
    def test_title_texts_under_front_fade(self):
        src = _paths.source('game.py')
        line = next(l for l in src.splitlines() if 'self._draw_menus();' in l and 'self._draw_title()' in l)
        calls = re.findall(r'self\.(_draw_\w+)\(\)', line)
        self.assertLess(calls.index('_draw_title'), calls.index('_draw_fade'), line)          # _draw_fade() without argument = front plane


def bands(path):
    """Brightest gray level in the "Touchez l'ecran" box and in the copyright box (placement of TitleTouch.draw_all, scale H / 800 x UI_ZOOM)."""
    a = np.asarray(Image.open(path).convert('L')).astype(int); h, w = a.shape; s = h / 800.0 * 1.12
    cy = int(h / 2 + AP.TT_BOTTOM * s); tt = a[cy - int(AP.TT_H / 2 * s):cy + int(AP.TT_H / 2 * s), int(w / 2 - AP.TT_L / 2 * s):int(w / 2 + AP.TT_L / 2 * s)]
    cyc = int(h - AP.CP_TOP * s); cp = a[cyc - int(AP.CP_H / 2 * s):cyc + int(AP.CP_H / 2 * s), int(w / 2 - AP.CP_L / 2 * s):int(w / 2 + AP.CP_L / 2 * s)]
    return int(tt.max()), int(cp.max()), float(a.mean())


@unittest.skipIf(not (APK and SAVES and CACHE), 'original engine: --apk, --saves and --cache required')
class TitleFade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apk, saves, cache = APK, SAVES, CACHE
        cls.tmp = tempfile.mkdtemp(prefix='titre_fondu_'); rg = os.path.join(cls.tmp, 'settings.json'); json.dump({}, open(rg, 'w'))
        if 'taptostart' not in AP.paths(cache):                                  # the title images are extracted once (they are not in every interface cache)
            c2 = os.path.join(cls.tmp, 'cache'); os.makedirs(c2)
            for f in glob.glob(os.path.join(cache, 'ui_*')): shutil.copy(f, c2)
            AP.prepare(apk, c2); cache = c2
        shot = os.path.join(cls.tmp, 't.png')
        cmd = [sys.executable, '-W', 'ignore', '-m', 'dq456_pc', '--apk', apk, '--saves-read', saves, '--saves-write', os.path.join(cls.tmp, 'sv'), '--settings', rg, '--slot', '0', '--no-logos',
               '--cache', cache, '--msaa', '0', '--width', '1280', '--height', '720', '--no-preparation', '--no-sound', '--shot', shot, '--images', '100000',
               '--test-keys', '%d:SPACE' % PRESS, '--shots-loop', '%d,%d' % (BEFORE, DARK)]
        env = dict(os.environ, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent')
        subprocess.run(cmd, cwd=os.path.join(HERE, '..'), env=env, timeout=1200, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.before = bands(os.path.join(cls.tmp, 't_b%d.png' % BEFORE)); cls.dark = bands(os.path.join(cls.tmp, 't_b%d.png' % DARK))

    def test_texts_shown_before_the_press(self):
        self.assertGreater(self.before[0], 200, 'Touchez l\'ecran'); self.assertGreater(self.before[1], 200, 'copyright')

    def test_screen_almost_black_after_the_press(self):
        self.assertLess(self.dark[2], 20)

    def test_texts_fade_with_the_screen(self):
        self.assertLess(self.dark[0], 40, 'the tap-to-start text stays visible in the fade'); self.assertLess(self.dark[1], 40, 'the copyright stays visible in the fade')


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + REST)
