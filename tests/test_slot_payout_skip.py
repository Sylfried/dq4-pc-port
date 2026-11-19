"""The casino's slot machine pays a win out one token a frame (Casino_Slot::cashCoin); on the phone a screen tap pays the rest at once (cashAllCoin, read in the game's pad
trigger g_Pad + 2). The port sends that tap (GameUpdate's 0x100) when A is pressed during the payout (Engine.slot_paying, keyboard_mouse._entries).

1. Without APK: the slot menu objects and states of the three games;
2. real engine (DQ_APK, DQ_SAVES, DQ_GAME): the menu in its payout state with 50 tokens to pay: Engine.slot_paying is true; a step with the tap then the payout pays them all at once,
   a step without it pays one (DQ V / VI; DQ IV's menu first waits for its sound effect).
    DQ_GAME=dq5 DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_slot_payout_skip.py
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine as ENGINE
from dq456_pc import games as GM
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')

# game -> (Casino_Slot singleton, the payout step called by the menu's update, offset of the tokens in the menu, offset of the tokens left to pay in the Casino_Slot object)
SLOT = {'dq4': ('_ZN11Casino_Slot12getSingletonEv', '_ZN17MaterielMenu_SLOT10menuUpdateEv', 0x2c, 0x8),
        'dq5': ('_ZN6casino11Casino_Slot12getSingletonEv', '_ZN4menu17MaterielMenu_SLOT10showEffectEv', 0x2c, 0x10),
        'dq6': ('_ZN6casino15CasinoSlotFrame12getSingletonEv', '_ZN4menu16MaterielMenuSlot10showEffectEv', 0x100, 0x14)}


class WithoutApk(unittest.TestCase):
    def test_objects(self):
        self.assertEqual(ENGINE.SLOT_MENU, {'dq4': ('gMaterielMenu_SLOT', 0x24), 'dq5': ('_ZN4menu18gMaterielMenu_SLOTE', 0x1c), 'dq6': ('_ZN4menu17gMaterielMenuSlotE', 0xf0)})
        self.assertEqual(ENGINE.SLOT_PAYING, 3)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> (DQ_GAME: the game)')
class RealEngine(unittest.TestCase):
    def test_tap_pays_the_rest(self):
        g = GM.profile().key
        e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='slot_')); c = e.core
        for _ in range(3): e.step(0, 0)
        single, pay, coins, left = SLOT[g]; sym, state = ENGINE.SLOT_MENU[g]
        menu = c.export(sym); slot = c.call(c.export(single), label='slot')
        self.assertTrue(menu and slot)
        def payout(tap):
            e.state.part = ENGINE.PART_CASINO
            c.mem_w(menu + state, struct.pack('<i', ENGINE.SLOT_PAYING)); c.mem_w(menu + coins, struct.pack('<i', 100)); c.mem_w(slot + left, struct.pack('<i', 50))
            self.assertTrue(e.slot_paying())
            for _ in range(60):                                             # (DQ IV's menu update first waits for the menu sound effect to end)
                e.step(0, 0x100 if tap else 0)
                c.mem_w(menu + state, struct.pack('<i', ENGINE.SLOT_PAYING))
                c.call(c.export(pay), menu, label='payout')
                r = struct.unpack('<i', c.mem(menu + coins, 4))[0], struct.unpack('<i', c.mem(slot + left, 4))[0]
                if r != (100, 50): return r
            return r
        if g != 'dq4': self.assertEqual(payout(False), (101, 49))
        self.assertEqual(payout(True), (150, 0))
        e.state.part = ENGINE.PART_TOWN; self.assertFalse(e.slot_paying())


if __name__ == '__main__':
    unittest.main(verbosity=1)
