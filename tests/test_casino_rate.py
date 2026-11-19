"""Esc menu > Difficulty: "Casino tokens won" (5 notches, Normal x1 = the game; set by the difficulty level like the other notched lines). The engine computes a win in a register just before
it keeps it; the hooks of Engine._casino_hooks multiply it there (CASINO_WINS): the slot machine's payout (Casino_Slot::getResultAllCoin: x0 and Casino_Slot + 8), poker's bet x multiple
(MaterielMenuPokerChangecard, and the stake of its double-up games MaterielMenuPokerSelectcard / Hiandlow), the monster arena's bet x odds (MaterielMenu_FIGHT_STADIUM::menuSetup). The message,
the double-up and the tokens paid follow the amount; bought tokens, the bets and the bestiary's reward do not go through these sites.

1. Without APK: the sites, the setting (stored, given to the engine, set by the difficulty).
2. Real engine (DQ_APK, DQ_SAVES): each site's instruction is run alone in the emulator with a known win in its register: x1 = the game's amount, x1.5 / x0.5 multiplied (rounded, at least 1);
   the slot machine's site only when lines were bet.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_casino_rate.py        (a few seconds)
"""
import os, struct, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG
from dq456_pc.window import options as OP
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class WithoutApk(unittest.TestCase):
    def test_sites(self):
        self.assertEqual([s[0] for s in ENGINE.CASINO_WINS], ['_ZN11Casino_Slot16getResultAllCoinEv', '_ZN27MaterielMenuPokerChangecard13pokerDealCardEv', '_ZN27MaterielMenuPokerChangecard13messageUpdataEv',
                                                             '_ZN27MaterielMenuPokerSelectcard9menuSetupEv', '_ZN25MaterielMenuPokerHiandlow9menuSetupEv', '_ZN26MaterielMenu_FIGHT_STADIUM9menuSetupEv'])
        self.assertEqual(ENGINE.Engine.casino_rate, 1.0)

    def test_setting(self):
        reg = RG.Settings(None); self.assertEqual(reg['casino_rate'], 1.0); self.assertIn('casino_rate', RG.RATE_KEYS)
        j = types.SimpleNamespace(reg=reg, engine=types.SimpleNamespace()); reg['casino_rate'] = 1.25; OP.OptionsMixin.apply_game(j); self.assertEqual(j.engine.casino_rate, 1.25)
        self.assertEqual([RG.difficulty_rates(n)['casino_rate'] for n in range(5)], [1.5, 1.25, 1.0, 0.75, 0.5])          # (the easier, the more tokens)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='casino_')); c = cls.c = cls.eng.core
        for _ in range(3): cls.eng.step(0, 0)
        cls.buf = c.malloc(0x200); cls.stack = (c.malloc(0x200) + 0xff) & ~0xf

    def run_site(self, name, off, regs):
        """Runs the one instruction of the site (its hook first) with these registers."""
        c = self.c; a = c.export(name) + off
        for r, v in regs.items(): c.uc.reg_write(c.XREG[r], v)
        c.uc.reg_write(c.C.UC_ARM64_REG_SP, self.stack); c.uc.emu_start(a, a + 4, count=1)

    def test_stores(self):
        """Poker and the monster arena: the win is in a register just before it is stored (str wN, [xM, #off])."""
        sites = {'_ZN27MaterielMenuPokerChangecard13pokerDealCardEv': (8, 19, 0x24), '_ZN27MaterielMenuPokerChangecard13messageUpdataEv': (1, 19, 0x24),
                 '_ZN27MaterielMenuPokerSelectcard9menuSetupEv': (9, 19, 0x28), '_ZN25MaterielMenuPokerHiandlow9menuSetupEv': (8, 19, 0x28), '_ZN26MaterielMenu_FIGHT_STADIUM9menuSetupEv': (8, 22, 0x24)}
        for name, off, word, reg in ENGINE.CASINO_WINS[1:]:
            r, base, field = sites[name]; self.assertEqual(reg, r, name)
            for rate, win, expected in ((1.0, 7, 7), (1.5, 7, 11), (0.5, 7, 4), (0.5, 1, 1), (1.5, 0, 0)):
                self.eng.casino_rate = rate; self.c.mem_w(self.buf + field, b'\xff' * 4)
                self.run_site(name, off, {r: win, base: self.buf})
                self.assertEqual(struct.unpack('<I', self.c.mem(self.buf + field, 4))[0], expected, (name, rate, win))
        self.eng.casino_rate = 1.0

    def test_slot_machine(self):
        """Casino_Slot::getResultAllCoin: the payout summed in x0 and Casino_Slot + 8 (x19), when lines were bet (+ 4)."""
        name, off, word, reg = ENGINE.CASINO_WINS[0]; c = self.c
        for rate, lines, win, expected in ((1.0, 3, 40, 40), (1.5, 3, 40, 60), (0.5, 1, 15, 8), (1.5, 0, 40, 40)):
            self.eng.casino_rate = rate; c.mem_w(self.buf, struct.pack('<iii', 0, lines, win))
            self.run_site(name, off, {0: win, 19: self.buf})
            self.assertEqual((c.uc.reg_read(c.XREG[0]), struct.unpack('<i', c.mem(self.buf + 8, 4))[0]), (expected, expected), (rate, lines, win))
        self.eng.casino_rate = 1.0


if __name__ == '__main__':
    unittest.main()
