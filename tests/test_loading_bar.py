"""The loading bar of the startup's black screen (window/loading_bar.py): it only goes forward, creeps toward 50 % while the engine loads, moves at each line of a
once-only read during the startup only, stays across the bottom of the screen, and its text is in every language.

    python3 tests/test_loading_bar.py"""
import os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc import language as LG
try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq456_pc.window import loading_bar as LB
    ERROR = None
except Exception as ex:                       # (no pyglet here)
    LB = None; ERROR = ex


@unittest.skipIf(LB is None, 'pyglet not importable here: %r' % (ERROR,))
class Bar(unittest.TestCase):
    def fake(self):
        j = types.SimpleNamespace(load_fraction=0.0, loading=True, shown=[])
        j.load_progress = lambda f: LB.LoadingBarMixin.load_progress(j, f)
        j.show_loading = lambda f=None: (j.load_progress(f) if f is not None else None, j.shown.append(round(j.load_fraction, 3)))
        return j

    def test_never_goes_back(self):
        j = self.fake(); j.load_progress(0.5); j.load_progress(0.2); self.assertEqual(j.load_fraction, 0.5); j.load_progress(3); self.assertEqual(j.load_fraction, 1.0)

    def test_creep_while_the_engine_loads(self):
        a, b = LB.ENGINE_SHARE
        self.assertEqual(LB.creep(0), a); self.assertLess(LB.creep(60), b); self.assertGreater(LB.creep(60), b - 0.01)
        self.assertTrue(all(LB.creep(t) < LB.creep(t + 1) for t in range(30)))

    def test_log_lines_move_the_bar_during_the_startup_only(self):
        j = self.fake(); log = LB.LoadingBarMixin.loading_log(j, 0.8)
        log('Reading the title images (once)...'); log('...'); self.assertEqual(j.shown, [0.2, 0.35]); self.assertLess(j.load_fraction, 0.8)
        j.loading = False; log('Extracting map x ...'); self.assertEqual(j.shown, [0.2, 0.35])                   # (once the game runs: printed only)

    def test_across_the_bottom(self):
        for w, h in ((1280, 720), (1920, 1080), (640, 480)):
            x, y, bw, bh = LB.bar_geometry(w, h)
            self.assertEqual(x + bw + x, w); self.assertLess(y + bh, h * 0.06); self.assertGreaterEqual(bh, 4)

    def test_text_in_every_language(self):
        for lg in LG.LANGUAGES:
            t = LG.catalog(lg).get(LB.LOADING_TEXT); self.assertTrue(t, lg); self.assertIn('42', t % 42, lg)


if __name__ == '__main__':
    unittest.main(verbosity=1)
