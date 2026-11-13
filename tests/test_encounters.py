"""Random encounters with accelerated walking: the viewer no longer touches the encounter counter, as on mobile. The game counts steps: at x4 the hero takes 4 times more steps per
real second, so battles arrive 4 times faster than at x1, for the same number of steps (reduced them to (1 + a) / 2: hook removed).

    python3 tests/test_encounters.py
    DQ_APK=... DQ_SAVES=... python3 tests/test_encounters.py      (real-engine tests: the counter loss of CountDown::exec does not depend on the speed)

The statistical simulation (real walking on the world map and in a dungeon, number of encounters per step at x1 / x2 / x4) is in tools/simulate_encounters.py.
"""
import os, sys, struct, shutil, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import encounters as RE


class NoReduction(unittest.TestCase):
    def test_no_encounter_reduction_left(self):
        for name_str in ('Reducer', 'encounters_per_second', 'factor_per_step'): self.assertFalse(hasattr(RE, name_str), name_str)


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'DQ_APK and DQ_SAVES required (real engine)')
class TestRealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        wdir = '/tmp/sv_test_rencontres'; shutil.rmtree(wdir, ignore_errors=True); os.makedirs(wdir)
        cls.m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], wdir)
        cls.m.load_save(4)
        for _ in range(60): cls.m.step(0, 0)
        c = cls.m.core
        cls.c = c; cls.enc = c.call(c.export('_ZN7Encount12getSingletonEv')); cls.cd = c.export('_ZN9CountDown4execEv')

    def write(self, counter, rate):
        self.c.mem_w(self.enc + 0x134, struct.pack('<i', counter)); self.c.mem_w(self.enc + 0x144, struct.pack('<i', rate))

    def read(self): return struct.unpack('<i', self.c.mem(self.enc + 0x134, 4))[0]

    def invoke(self, n, speed, counter=1 << 24, rate=423):
        """n calls of CountDown::exec of the real engine (`speed`: kept for comparison, the engine no longer has a walking speed): total counter loss."""
        self.write(counter, rate)
        for _ in range(n): self.c.call(self.cd, self.enc + 0x134)
        return counter - self.read()

    def test_no_encounter_hook(self):
        self.assertFalse(hasattr(self.m, '_encounter_hooks')); self.assertFalse(hasattr(self.m, 'encounters'))

    def test_counter_loss_does_not_depend_on_speed(self):
        for speed in (0.5, 1.0, 2.0, 3.0, 4.0, 8.0): self.assertEqual(self.invoke(100, speed), 100 * 2 * 423, speed)          # the game: 2 x [+0x10] per call, at all speeds

    def test_same_number_of_calls_to_trigger_at_x1_and_x4(self):
        """The counter goes below zero after the same number of calls (hence of steps) at x1 and at x4: at x4 the steps are 4 times more numerous per second, that is all."""
        def calls(speed):
            self.write(8326, 423); n = 0
            while self.read() >= 0 and n < 1000: self.c.call(self.cd, self.enc + 0x134); n += 1
            return n
        self.assertEqual((calls(1.0), calls(4.0)), (10, 10))                                      # 8326 / 846: the original game

    def test_negative_counter_stays_negative(self):
        self.write(-5, 423)
        for _ in range(20):
            self.c.call(self.cd, self.enc + 0x134); self.assertLess(self.read(), 0)


class ForcedMonsterConstants(unittest.TestCase):
    def test_hook_points(self):
        from dq4_pc.core import engine as ENGINE
        self.assertEqual((ENGINE.ENCOUNT_BREW_END, ENGINE.ENCOUNT_BREW_RET), (0x1c0, 0x200))
        self.assertEqual((ENGINE.ENCOUNT_MONSTERS, ENGINE.ENCOUNT_COUNTS), (0x34, 0x44))
        self.assertEqual((ENGINE.MOV_X0_X19, ENGINE.RET), (0xaa1303e0, 0xd65f03c0))

    def test_option_exists_and_is_off_by_default(self):
        """(read from the source: importing dq4_pc.main opens a pyglet window, there is no screen in the CI)"""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import _paths
        self.assertIn("'--force-monster', type=int, default=0", _paths.source('main.py'))
        self.assertIn('self.engine.force_monster = args.force_monster', _paths.source('game.py'))


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'DQ_APK and DQ_SAVES required (real engine)')
class ForcedMonster(unittest.TestCase):
    """`--force-monster N` (Engine.force_monster): `Encount::brew()` of the real engine gives a single monster N; at 0 the game is untouched."""
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        wdir = '/tmp/sv_test_monstre_force'; shutil.rmtree(wdir, ignore_errors=True); os.makedirs(wdir)
        cls.m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], wdir)
        cls.m.load_save(4)
        for _ in range(60): cls.m.step(0, 0)
        c = cls.c = cls.m.core; cls.enc = c.call(c.export('_ZN7Encount12getSingletonEv')); cls.brew = c.export('_ZN7Encount4brewEv')

    def group(self):
        mem = self.c.mem; return struct.unpack('<4I', mem(self.enc + 0x34, 16)), struct.unpack('<4I', mem(self.enc + 0x44, 16))

    def draw(self):
        self.c.mem_w(self.enc + 8, struct.pack('<i', 78)); self.assertEqual(self.c.call(self.brew, self.enc, label='brew') & 0xffffffff, 1); return self.group()

    def test_hook_installed(self):
        self.assertEqual(self.m.force_monster, 0)
        self.assertFalse([x for x in self.m.missing_hooks if 'forced monster' in x])

    def test_forced_then_released(self):
        self.m.force_monster = 65
        try:
            for _ in range(5): self.assertEqual(self.draw(), ((65, 0, 0, 0), (1, 0, 0, 0)))
        finally: self.m.force_monster = 0
        seen = {self.draw()[0][0] for _ in range(10)}
        self.assertNotEqual(seen, {65}, 'the game draws its own groups again')


if __name__ == '__main__': unittest.main(verbosity=1)
