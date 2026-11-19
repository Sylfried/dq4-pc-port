"""Esc menu > Modifiers > Difficulty: "Experience gained" and "Gold gained" (Less x0.5, Normal x1 = the game, More x1.5). The engine sums a battle's experience and gold in PartyStatus + 0x2f8 / + 0x2fc
while the monsters fall, then shares them out (PartyStatus::reflectBattleExp / reflectBattleGold) before the messages "X reçoit N points d'expérience !" / "... pièces d'or !"; the hooks at the entry of
these two functions multiply the totals (Engine._reward_hooks): the messages, the gold and the levels gained follow.

1. Without APK: the rounding, the settings.
2. Real engine (DQ_APK, DQ_SAVES): a battle against a flying rat (3 experience, 7 gold in the game) at Normal, then at x1.5 / x0.5.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_reward_rates.py        (about a minute)
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class WithoutApk(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual([ENGINE.reward(v, 1.5) for v in (0, 1, 2, 3, 7, 1000)], [0, 2, 3, 5, 11, 1500])          # (to the nearest, half up)
        self.assertEqual([ENGINE.reward(v, 0.5) for v in (0, 1, 2, 3, 7, 1000)], [0, 1, 1, 2, 4, 500])            # (at least 1 when there was some)
        self.assertEqual(ENGINE.reward(12345, 1.0), 12345); self.assertEqual(ENGINE.reward(0x7fffffff, 1.5), 0x7fffffff)

    def test_settings(self):
        self.assertEqual({RG.DEFAULT[k] for k in RG.RATE_KEYS}, {1.0}); self.assertEqual(RG.RATES, (0.5, 0.75, 1.0, 1.25, 1.5))
        self.assertEqual(set(RG.RATE_NAMES), set(RG.RATES))

    def test_hooks_are_known(self):
        self.assertEqual([r[3] for r in ENGINE.REWARDS], ['exp_rate', 'gold_rate']); self.assertEqual((ENGINE.Engine.exp_rate, ENGINE.Engine.gold_rate), (1.0, 1.0))
        self.assertEqual({k: v[1] for k, v in ENGINE.DAMAGE_VALUES.items()}, {0: 'party_damage_rate', 1: 'enemy_damage_rate'})
        self.assertEqual((ENGINE.Engine.party_damage_rate, ENGINE.Engine.enemy_damage_rate), (1.0, 1.0))
        self.assertEqual([ENGINE.reward(v, 0.75) for v in (1, 4, 10)], [1, 3, 8]); self.assertEqual([ENGINE.reward(v, 1.25) for v in (1, 4, 10)], [1, 5, 13])


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def fight(self, exp_rate, gold_rate, party=1.0, enemy=1.0):
        """A battle against monster 20 (flying rat) from save 4 (Ragnar, chapter 1), the first command each time. -> (messages "reçoit", gold added to the party)."""
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='rewards_')); c = eng.core
        for _ in range(3): eng.step(0, 0)
        if not eng.load_save(4): self.skipTest('no data4.dat')
        eng.force_monster = 20; eng.exp_rate, eng.gold_rate = exp_rate, gold_rate; eng.party_damage_rate, eng.enemy_damage_rate = party, enemy
        gp = c.export('_ZN6status7g_PartyE'); dirs = [ENGINE.UP, ENGINE.RIGHT, ENGINE.DOWN, ENGINE.LEFT]; n = 0
        while eng.state.part != ENGINE.PART_BATTLE and n < 3000: d = dirs[(n // 40) % 4]; eng.step(d, d); n += 1
        self.assertEqual(eng.state.part, ENGINE.PART_BATTLE)
        gold0, = struct.unpack('<I', c.mem(gp + 0x2e0, 4)); out = []; k = 0; release = None; after = 0
        while k < 4000 and after <= 30:
            decl = 0
            if release is not None: eng.send_menu(release, 1, -1, 0); release = None
            elif k % 10 == 0:
                port = eng.active_menu(); decl = ENGINE.A if eng.msg_visible else 0
                if not eng.msg_visible and port is not None: eng.send_menu(port, 1, -1, 0x10); release = port
            eng.step(0, decl); k += 1; out += [t['text'].strip() for t in eng.sensor.drain() if any(w in t['text'] for w in ('reçoit', 'receives', 'dégâts', 'damage'))]
            if eng.state.part != ENGINE.PART_BATTLE: after += 1
        gold1, = struct.unpack('<I', c.mem(gp + 0x2e0, 4))
        return out, gold1 - gold0

    def test_the_game_then_multiplied(self):
        out, gold = self.fight(1.0, 1.0); got = [t for t in out if 'reçoit' in t or 'receives' in t]
        if not got or '3' not in got[0]: self.skipTest('another battle than the flying rat (3 experience, 7 gold): %r' % (out,))
        self.assertEqual(gold, 7)
        out, gold = self.fight(1.5, 0.5); got = [t for t in out if 'reçoit' in t or 'receives' in t]
        self.assertIn(' 5 ', got[0]); self.assertIn(' 4 ', got[1]); self.assertEqual(gold, 4)                    # (3 x 1.5 = 4.5 -> 5; 7 x 0.5 = 3.5 -> 4)

    def test_damage(self):
        """The same battle: the rat's first hit on Ragnar (1 point) and Ragnar's on the rat (11 points, then 9) at Normal; then x1.5 on the party, x0.5 on the enemies: the messages and the rat's
        defeat follow (the battle has the same draws: the engine's random numbers do not depend on the damage)."""
        out, _ = self.fight(1.0, 1.0); hits = [t for t in out if 'dégâts' in t or 'damage' in t]
        if len(hits) < 3 or ' 1 point ' not in hits[0] or ' 11 ' not in hits[1]: self.skipTest('another battle: %r' % (hits,))
        out, _ = self.fight(1.0, 1.0, party=1.5, enemy=0.5); hits = [t for t in out if 'dégâts' in t or 'damage' in t]
        self.assertIn(' 2 points ', hits[0]); self.assertIn(' 6 ', hits[1])                                       # (1 x 1.5 = 1.5 -> 2; 11 x 0.5 = 5.5 -> 6)


if __name__ == '__main__':
    unittest.main()
