""""Edge blur": the edges of the game picture blurred, like the vignette darkens them; a slider just under "Vignette effect" on the Display page.

1. Without APK: the shape (the vignette's ellipse), the setting (0 by default, 0 to 100 %), the place of the line, the drawing places (those of the vignette: not in battle nor on the world map).
2. Real window (DQ_APK, DQ_SAVES): save 1 (the church), the same frame without then with the setting at 100 %: the corners lose their detail, the middle keeps it.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_edge_blur.py        (about 30 s)
"""
import json, os, subprocess, sys, tempfile, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _paths
from dq4_pc.render import screen_blur as SB
from dq4_pc.persistence import settings as RG

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
L, H = 1280, 720
SHOT_OFF, SET_ON, SHOT_ON = 290, 292, 296


class Shape(unittest.TestCase):
    def test_middle_untouched_corners_full(self):
        self.assertEqual(SB.edge_weight(0.5, 0.5), 0.0)
        self.assertEqual(SB.edge_weight(0.6, 0.6), 0.0, 'up to 45 % of the radius: sharp')
        self.assertAlmostEqual(SB.edge_weight(0.0, 0.0), 1.0)
        self.assertAlmostEqual(SB.edge_weight(1.0, 1.0, 0.4), 0.4, msg='corners: the value of the setting')
        self.assertGreater(SB.edge_weight(0.0, 0.5), 0.6, 'bord gauche, a mi-hauteur')

    def test_growing_toward_the_edge(self):
        w = [SB.edge_weight(x, 0.5) for x in np.linspace(0.5, 0.0, 30)]
        self.assertTrue(all(b >= a for a, b in zip(w, w[1:])))

    def test_same_formula_as_the_shader(self):
        self.assertIn('smoothstep(0.45, 1.3, r)', SB.FRAG_EDGES)


class Setting(unittest.TestCase):
    def test_default_off_like_mobile(self):
        self.assertEqual(RG.DEFAULT['edge_blur'], 0.0)
        self.assertEqual(RG.BOUNDS['edge_blur'], (0.0, 1.0))

    def test_line_just_under_the_vignette(self):
        src = open(os.path.join(HERE, '..', 'dq4_pc', 'menus', 'pause.py'), encoding='utf-8').read()
        lines = src[src.index('def _entries_display'):].split('\n')
        i = next(n for n, l in enumerate(lines) if "('settings.vignette_effect'" in l)
        self.assertIn("('settings.edge_blur'", lines[i + 1])

    def test_drawn_where_the_vignette_is(self):
        """After the scene (the interface stays sharp), not in battle, on the world map nor during the end credits (source read as text: no display needed)."""
        src = open(os.path.join(HERE, '..', 'dq4_pc', 'window', 'game.py'), encoding='utf-8').read()
        self.assertIn('if e.part != ENGINE.PART_BATTLE and not field and not staff: self._draw_vignette()', src)
        a = src.index('        self.post.end()\n'); b = src.index('self._blur_edges()', a)
        self.assertIn('if e.part != ENGINE.PART_BATTLE and not field and not staff: self._blur_edges()', src[a:b + 20])
        self.assertLess(b, src.index('self._update_message(); self._draw_name_entry()', a))


def probe(out_dir):
    """Session on save 1: screenshot with the setting at 0, then at 100 %."""
    import pyglet
    pyglet.options['shadow_window'] = False
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True
    from dq4_pc.window import game as F
    from dq4_pc import main
    sys.argv = ['window.py', '--apk', APK, '--saves-read', SAVES, '--saves-write', tempfile.mkdtemp(prefix='sv_flou_'), '--settings', os.path.join(tempfile.mkdtemp(prefix='rg_flou_'), 'r.json'),
                '--slot', '1', '--cache', _paths.ui_cache('/tmp/uicache_flou'), '--msaa', '0', '--width', str(L), '--height', str(H), '--no-preparation', '--no-sound', '--no-logos',
                '--shots-loop', '%d,%d' % (SHOT_OFF, SHOT_ON), '--shot', os.path.join(out_dir, 'f.png'), '--images', str(SHOT_ON + 40)]
    loop = F.Game._loop
    def loop2(self, dt):
        if self.n_loop == SET_ON:
            self.reg['edge_blur'] = 1.0
            with open(os.path.join(out_dir, 'done.json'), 'w') as f: json.dump({'part': self.engine.state.part}, f)
        return loop(self, dt)
    F.Game._loop = loop2
    main.main()


def detail(a):
    return float(np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean())


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.dir = tempfile.mkdtemp(prefix='flou_bords_')
        env = dict(os.environ, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent')
        r = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__), '--sonde', cls.dir], capture_output=True, text=True, timeout=900, env=env)
        if not os.path.exists(os.path.join(cls.dir, 'f_b%d.png' % SHOT_ON)): raise RuntimeError('probe without a capture: ' + r.stdout[-600:] + r.stderr[-600:])
        cls.img = {n: np.asarray(Image.open(os.path.join(cls.dir, 'f_b%d.png' % n)).convert('L')).astype(float) for n in (SHOT_OFF, SHOT_ON)}

    def test_corners_blurred(self):
        c = lambda a: np.concatenate([a[:H // 6, :L // 8], a[:H // 6, -L // 8:]], axis=1)          # top corners (the dialogue box is at the bottom)
        off, on = detail(c(self.img[SHOT_OFF])), detail(c(self.img[SHOT_ON]))
        self.assertLess(on, 0.5 * off, (off, on))

    def test_middle_sharp(self):
        m = lambda a: a[H // 3:H // 2, 2 * L // 5:3 * L // 5]
        off, on = detail(m(self.img[SHOT_OFF])), detail(m(self.img[SHOT_ON]))
        self.assertGreater(on, 0.85 * off, (off, on))


if __name__ == '__main__':
    if '--sonde' in sys.argv: probe(sys.argv[sys.argv.index('--sonde') + 1])
    else: unittest.main(verbosity=2)
