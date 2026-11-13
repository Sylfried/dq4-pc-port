"""Save play time on real time (survey): the engine adds 2 units (1/60 s) per step; when the game is accelerated (walking x1.5 to x8, accelerator, fast battle) it makes `a` times
more steps per real second: the hook of `Engine._game_time_hooks` lets through only 1 / a of the `GameStatus::addPlayTime` calls.

    python3 tests/test_play_time.py
    DQ_APK=... DQ_SAVES=... python3 tests/test_play_time.py      (adds the real-engine tests)
"""
import os, sys, struct, shutil, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import encounters as RE


class TestFormula(unittest.TestCase):
    def test_share_of_steps(self):
        """Over 1200 steps at speed a, 1200 / a calls go through (give or take one): 2 x 1200 / a time units, i.e. 2400 / a / 60 s of play time for 1200 / (30 a) s of real clock time."""
        for a in (1.25, 1.5, 2.0, 3.0, 4.0, 8.0):
            p = RE.Passer(1.0 / a); n = sum(1 for _ in range(1200) if p.allows())
            self.assertLessEqual(abs(n - 1200 / a), 1.0, a)
            game_time = 2 * n / 60.0; real_time = 1200 / (30.0 * a)
            self.assertAlmostEqual(game_time, real_time, delta=0.1, msg=a)               # play time follows the real-time clock

    def test_at_x1_everything_passes(self):
        p = RE.Passer(1.0); self.assertTrue(all(p.allows() for _ in range(100)))


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'DQ_APK and DQ_SAVES required (real engine)')
class TestRealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        cls.ENGINE = ENGINE
        cls.wdir = '/tmp/sv_test_temps_de_jeu'; shutil.rmtree(cls.wdir, ignore_errors=True); os.makedirs(cls.wdir)
        cls.m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], cls.wdir); cls.m.load_save(4)
        for _ in range(200): cls.m.step(0, 0)
        cls.g = cls.m.core.export('_ZN6status6g_GameE')

    def clock(self): return struct.unpack('<I', self.m.core.mem(self.g + 4, 4))[0]

    def measure(self, v, step=600):
        m = self.m; m.clock_speed = v; t0 = self.clock()
        for _ in range(step): m.step(0, 0)
        m.clock_speed = 1.0
        return self.clock() - t0

    def test_hook_installed(self):
        self.assertFalse([x for x in self.m.missing_hooks if 'temps de jeu' in x], self.m.missing_hooks)

    def test_x1_the_game_as_is(self):
        self.assertEqual(self.measure(1.0), 1200)                                          # exactly 2 per step
        self.assertEqual(self.measure(0.5), 1200)                                          # (slowed down: unchanged, the hook does not catch up)

    def test_acceleration_reduces_time_per_step(self):
        for v in (1.5, 2.0, 3.0, 4.0, 8.0):
            d = self.measure(v)
            self.assertLessEqual(abs(d - 1200 / v), 2.0, 'x%g : +%d' % (v, d))
            self.assertEqual(d % 2, 0, v)                                                 # time always advances by 2 (calls are skipped, never cut)

    def test_return_to_x1_after_acceleration(self):
        self.measure(4.0); self.assertEqual(self.measure(1.0), 1200)


if __name__ == '__main__': unittest.main(verbosity=1)
