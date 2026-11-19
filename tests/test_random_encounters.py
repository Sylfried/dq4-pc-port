"""Esc menu > Modifiers > Difficulty: "Random encounters" (Yes / No) and "Encounter rate" (5 notches, grayed while there is none). The game runs an encounter countdown at each step on a map with
encounters (Encount::exec -> CountDown::exec: the counter loses 2 x the step value of the terrain, a battle below 0); the hooks of Engine._encounter_hooks multiply that step value (0: no random battle).

1. Without APK: the setting given to the engine (No -> factor 0).
2. Real engine (DQ_APK, DQ_SAVES): Ragnar walks the same path from save 4 (chapter 1, world map): the first random battle comes at the game's step, later at x0.5, sooner at x1.5, never with "No".
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_random_encounters.py        (about 30 s)
"""
import os, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG
from dq456_pc.window import options as OP
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class WithoutApk(unittest.TestCase):
    def test_setting_to_engine(self):
        reg = RG.Settings(None); j = types.SimpleNamespace(reg=reg, engine=types.SimpleNamespace())
        OP.OptionsMixin.apply_game(j)
        self.assertEqual(j.engine.encounter_rate, 1.0)
        reg['encounter_rate'] = 1.5; reg['random_encounters'] = False
        OP.OptionsMixin.apply_game(j); self.assertEqual(j.engine.encounter_rate, 0.0)
        reg['random_encounters'] = True; OP.OptionsMixin.apply_game(j); self.assertEqual(j.engine.encounter_rate, 1.5)
        self.assertEqual(ENGINE.Engine.encounter_rate, 1.0); self.assertTrue(RG.DEFAULT['random_encounters']); self.assertIn('encounter_rate', RG.RATE_KEYS)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def first_battle(self, rate, limit=3000):
        """Steps of the same walk (40 steps up, right, down, left...) before the first random battle, None if none in `limit` steps."""
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='encounters_'))
        for _ in range(3): eng.step(0, 0)
        if not eng.load_save(4): self.skipTest('no data4.dat')
        eng.encounter_rate = rate; dirs = [ENGINE.UP, ENGINE.RIGHT, ENGINE.DOWN, ENGINE.LEFT]
        for n in range(limit):
            d = dirs[(n // 40) % 4]; eng.step(d, d)
            if eng.state.part == ENGINE.PART_BATTLE: return n
        return None

    def test_rates(self):
        game = self.first_battle(1.0)
        if game is None: self.skipTest('no random battle on this walk')
        self.assertGreater(self.first_battle(0.5), game); self.assertLess(self.first_battle(1.5), game)
        self.assertIsNone(self.first_battle(0.0))


if __name__ == '__main__':
    unittest.main()
