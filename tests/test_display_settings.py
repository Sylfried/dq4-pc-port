"""the Display page: settings "Contrast", "Filter" ("Motion blur" too, whose line removed: the setting stays at 0);
"Shader" on "None" by default; "Resolution" removed.
(The order of the page and the move of "Battle speed" to Commandes are checked in test_window_mode and test_pause_pages.)

1. Without a window: settings (defaults, bounds, migration of the old default shader), filter matrices, camera shift and blur opacity.
2. Real window (DQ_APK, DQ_SAVES): save 4 (world map), the hero walks left: with "Filter" on "Black and white" the scene is gray (the interface keeps its colors).
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_display_settings.py        (about a minute)
"""
import json, os, subprocess, sys, tempfile, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _paths
from dq4_pc.persistence import settings as RG

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
SHOT = 215


class Settings(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(RG.DEFAULT['sprite_mode'], 0, 'Shader: None by default')
        self.assertEqual((RG.DEFAULT['contrast'], RG.DEFAULT['color_filter'], RG.DEFAULT['motion_blur']), (0.0, 'none', 0.0))
        self.assertEqual((RG.BOUNDS['contrast'], RG.BOUNDS['motion_blur']), ((0.0, 1.0), (0.0, 1.0)))
        self.assertGreaterEqual(RG.DEFAULT['keys_version'], 7)

    def load(self, d):
        p = os.path.join(tempfile.mkdtemp(prefix='rg_aff_'), 'r.json')
        with open(p, 'w') as f: json.dump(d, f)
        return RG.Settings(p)

    def test_old_default_shader_migrated(self):
        self.assertEqual(self.load({'keys_version': 6, 'sprite_mode': 4})['sprite_mode'], 0)          # (the old default follows the new one)
        self.assertEqual(self.load({'keys_version': 6, 'sprite_mode': 1})['sprite_mode'], 1)          # (a choice of the player stays)
        self.assertEqual(self.load({'keys_version': 7, 'sprite_mode': 4})['sprite_mode'], 4)          # (chosen after the migration)

    def test_values_brought_back(self):
        r = self.load({'keys_version': 7, 'contrast': 3, 'motion_blur': -1, 'color_filter': 'rainbow'})
        self.assertEqual((r['contrast'], r['motion_blur'], r['color_filter']), (1.0, 0.0, 'none'))

    def test_motion_blur_kept_at_zero(self):
        """"Motion blur" has no line, and a value set while the line existed goes back to 0."""
        self.assertEqual(self.load({'keys_version': 7, 'motion_blur': 1.0})['motion_blur'], 0.0)
        src = open(os.path.join(HERE, '..', 'dq4_pc', 'menus', 'pause.py'), encoding='utf-8').read()
        self.assertNotIn("'Flou de mouvement'", src)


class Filters(unittest.TestCase):
    def test_same_names_as_the_settings(self):
        src = open(os.path.join(HERE, '..', 'dq4_pc', 'render', 'postfx.py'), encoding='utf-8').read()
        for k in RG.COLOR_FILTERS: self.assertIn("'%s':" % k, src, k)

    def test_matrices(self):
        src = open(os.path.join(HERE, '..', 'dq4_pc', 'render', 'postfx.py'), encoding='utf-8').read()
        self.assertIn("'none': None", src)
        self.assertIn('if (filtered > 0.5) c = clamp(cmat * c, 0.0, 1.0);', src)
        self.assertIn('c = clamp((c - 0.5) * (1.0 + contrast) + 0.5, 0.0, 1.0);', src)


class CameraShift(unittest.TestCase):
    def setUp(self):
        from dq4_pc.window import motion_blur as MB
        self.MB = MB

    def test_still_camera(self):
        M = np.diag([0.5, 0.8, -0.1, 1.0]); M[2, 3] = -1.0
        self.assertAlmostEqual(self.MB.camera_shift(M, M, 1920, 1080), 0.0, places=6)
        self.assertEqual(self.MB.camera_shift(None, M, 1920, 1080), 0.0)

    def test_moving_camera(self):
        M = np.diag([0.5, 0.8, -0.1, 1.0]); T = np.eye(4); T[0, 3] = 0.02
        s = self.MB.camera_shift(M, T @ M, 1920, 1080)
        self.assertAlmostEqual(s, 0.02 * 960, places=3)                                       # (a shift of 0.02 in NDC = 19.2 pixels at 1920)

    def test_opacity(self):
        MB = self.MB
        self.assertEqual(MB.blur_opacity(0.0, 50.0), 0.0); self.assertEqual(MB.blur_opacity(1.0, 0.0), 0.0)
        self.assertAlmostEqual(MB.blur_opacity(1.0, MB.MB_FULL_PX), MB.MB_MAX); self.assertAlmostEqual(MB.blur_opacity(0.5, MB.MB_FULL_PX / 2), MB.MB_MAX / 4)


def probe(out_dir, reg):
    import pyglet
    pyglet.options['shadow_window'] = False
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True
    from dq4_pc import main
    rg = os.path.join(tempfile.mkdtemp(prefix='rg_aff_'), 'r.json')
    with open(rg, 'w') as f: json.dump(dict(json.loads(reg), keys_version=7, language='fr'), f)
    script = ','.join('%d:4' % i for i in range(150, 400))                                       # (left held: the hero walks, the world map scrolls)
    sys.argv = ['window.py', '--apk', APK, '--saves-read', SAVES, '--saves-write', tempfile.mkdtemp(prefix='sv_aff_'), '--settings', rg, '--slot', '4', '--cache', _paths.ui_cache('/tmp/uicache_aff'),
                '--msaa', '0', '--width', '1280', '--height', '720', '--no-preparation', '--no-sound', '--no-logos', '--script', script, '--shots-loop', str(SHOT), '--shot', os.path.join(out_dir, 's.png'), '--images', str(SHOT + 5)]
    main.main()


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.img = {}
        env = dict(os.environ, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent')
        for name, reg in (('ref', {}), ('gray', {'color_filter': 'gray'})):
            d = tempfile.mkdtemp(prefix='aff_%s_' % name)
            r = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__), '--sonde', d, json.dumps(reg)], capture_output=True, text=True, timeout=900, env=env)
            f = os.path.join(d, 's_b%d.png' % SHOT)
            if not os.path.exists(f): raise RuntimeError('probe without a capture: ' + r.stdout[-600:] + r.stderr[-600:])
            cls.img[name] = np.asarray(Image.open(f).convert('RGB')).astype(float)

    @staticmethod
    def detail_x(a): return float(np.abs(np.diff(a, axis=1)).mean())

    def test_gray_filter(self):
        a = self.img['gray'][200:300, 100:500]
        self.assertLess(float(np.abs(a[..., 0] - a[..., 1]).mean() + np.abs(a[..., 1] - a[..., 2]).mean()), 6.0)          # (gray: +-2 on green, the window's dithering)
        r = self.img['ref'][200:300, 100:500]
        self.assertGreater(float(np.abs(r[..., 0] - r[..., 1]).mean()), 10.0)                 # (control: the world map is colored)


if __name__ == '__main__':
    if '--sonde' in sys.argv:
        i = sys.argv.index('--sonde'); probe(sys.argv[i + 1], sys.argv[i + 2])
    else: unittest.main(verbosity=2)
