"""Night arrival with accelerated walking: the viewer no longer touches it, as on mobile. World time advances with each hero step; at x4 there are 4 times more steps per second, so night
arrives 4 times faster (limited it to (1 + a) / 2 with a hook on FieldPlayerDoku::checkDokuDamage, removed).

    python3 tests/test_day_clock.py
    DQ_APK=... DQ_SAVES=... python3 tests/test_day_clock.py      (adds the real-engine tests: world time advances by 2 per step, with no jump)

On the world map, world time (`status::g_Stage + 0xcc`, cycle of 0xd40) advances by 2 per engine frame where the hero changed position (`FieldStage::ChangeTime(0)`).
"""
import os, sys, struct, shutil, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import encounters as RE


class TestFormulas(unittest.TestCase):          # (`Passer` is still used for the play time, see test_play_time)
    def test_passer_at_one_lets_everything_pass(self):
        p = RE.Passer(1.0)
        self.assertTrue(all(p.allows() for _ in range(100)))
        p = RE.Passer(); self.assertTrue(all(p.allows() for _ in range(100)))                   # (default: transparent)

    def test_passer_exact_fraction(self):
        for a in (1.25, 1.5, 2.0, 3.0, 4.0, 8.0):
            p = RE.Passer(1.0 / a); n = sum(1 for _ in range(1200) if p.allows())
            self.assertLessEqual(abs(n - 1200 / a), 1.0, a)                  # to within one call

    def test_passer_regular(self):
        """The skipped calls are spread out (3 out of 4 at x2: never two skips in a row): time does not advance in jerks."""
        p = RE.Passer(0.75); seen = [p.allows() for _ in range(40)]
        self.assertEqual(sum(seen), 30); self.assertFalse(any(not a and not b for a, b in zip(seen, seen[1:])))


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'DQ_APK and DQ_SAVES required (real engine)')
class TestRealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        cls.ENGINE = ENGINE
        cls.wdir = '/tmp/sv_test_horloge_jour'; shutil.rmtree(cls.wdir, ignore_errors=True); os.makedirs(cls.wdir)

    def world(self):
        """Engine on the world map (save 4), the hero in the corridor with no entrance or exit from tools/simulate_encounters.py, without a battle (Encount::brew returns false); -> (engine, world time reader)."""
        ENGINE = self.ENGINE
        m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], self.wdir); c = m.core; m.load_save(4)
        for i in range(700):
            m.step(0, 0)
            if i >= 130 and 0 in m.state.sprites: break
        c.mem_w(c.export('_ZN7Encount4brewEv'), struct.pack('<II', 0x52800000, 0xd65f03c0))
        m.enc = c.call(c.export('_ZN7Encount12getSingletonEv')); m.enc_setup = c.export('_ZN7Encount5setupE11EncountPart8LandType')
        for _ in range(10): m.step(ENGINE.UP, ENGINE.UP)                                                  # from the starting cell to the corridor (y = 354)
        g = c.export('_ZN6status7g_StageE')
        return m, (lambda: struct.unpack('<i', c.mem(g + 0xcc, 4))[0])

    def walk(self, m, clock, frames=500):
        """Walks back and forth in the corridor (the direction reverses when the hero is blocked): -> (steps, world time advance, hero positions after each frame)."""
        ENGINE = self.ENGINE; c = m.core
        step = 0; dt = 0; last = clock(); prev = tuple(m.state.sprites[0]['pos']); trace = []; d = ENGINE.LEFT; blocked = 0
        for k in range(frames):
            m.step(d, d)
            if struct.unpack('<i', c.mem(m.enc + 0x1c, 4))[0] >= 1: c.call(m.enc_setup, m.enc, 0, 0)         # encounter triggered (without a battle): the counter restarts, the hero can walk
            pos = tuple(m.state.sprites[0]['pos']); t = clock(); trace.append(pos)
            if pos != prev:
                step += 1; blocked = 0; dd = t - last; dt += dd + (0xd40 if dd < 0 else 0)
            else:
                blocked += 1
                if blocked >= 2: d = ENGINE.RIGHT if d == ENGINE.LEFT else ENGINE.LEFT; blocked = 0
            last = t; prev = pos
        return step, dt, trace

    def test_no_hook_the_world_time_is_two_per_step(self):
        m, clock = self.world()
        self.assertFalse(hasattr(m, '_day_clock_hooks')); self.assertFalse(hasattr(m, 'walking_speed'))
        step, dt, _ = self.walk(m, clock)
        self.assertGreater(step, 200); self.assertEqual(dt, 2 * step, '+%d in %d steps' % (dt, step))          # the original game: exactly 2 per step, with no jump


if __name__ == '__main__': unittest.main(verbosity=1)
