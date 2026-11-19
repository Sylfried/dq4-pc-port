"""The king's experience gift (chapter 1) freezes the game at the last level message.

The menu `MaterielMenu_EXTRA_PRESENT_EXP` (added by the mobile game) waits, once the levels are shown, for a trigger from the game's pad (`dss::g_Pad + 2`, filled by `Global::NativeExec` from the 2nd argument of `GameUpdate`):
screen touch exactly 0x100, or buttons 0x400 to 0x2000. The A key of a message (0x10) never releases it.

  1. `Engine.awaits_touch` (no engine: memory is simulated): true only if the menu is in the menu manager's array AND in its last state;
  2. `inputs.touch_for_engine`: A sends 0x100 alone when the menu is waiting, nothing changes otherwise;
  3. a model of `Global::NativeExec + 0x74` (machine code re-read) shows why 0x10 and 0x110 are not enough and 0x100 or 0x400 are;
  4. wiring: `Game._entries` does call the conversion when a message is open (the test reads the code, without pyglet).

    python3 tests/test_exp_gift_touch.py
"""
import os, sys, types, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from dq456_pc.window import inputs as EN
from dq456_pc.core import engine as ENGINE

A, B, TALK = 0x10, 0x20, 0x100          # (port keys; screen touch, see window/constantes.BTN_TALK)
L = 0x10000000


def game_pad(decl):
    """g_Pad + 2 from the 2nd argument of GameUpdate (Global::NativeExec + 0x38 to + 0x74): bits 10 to 13 of `decl` (shifts -5, -5, -5, -3, masks 0x20, 0x40, 0x80, 0x400), plus 0x10 when
    `decl & 0x7fff` is exactly 0x100 (the touch)."""
    v = ((decl >> 5) & 0x20) | ((decl >> 5) & 0x40) | ((decl >> 5) & 0x80) | ((decl >> 3) & 0x400)
    return v | (0x10 if (decl & 0x7fff) == 0x100 else 0)


def mock_engine(opened=True, state=2, place=0, manager=True, crash=False):
    """An engine with only `mem`: menu manager at GES, array of 8 pointers at GES + 8, experience gift menu at L + 0x24c730 (state at + 0x30)."""
    GES = L + 0x300000; menu = L + ENGINE.MENU_GIFT_EXP
    m = {}
    m[(L + ENGINE.MENU_MANAGER, 8)] = (GES if manager else 0).to_bytes(8, 'little')
    for i in range(8): m[(GES + 8 + 8 * i, 8)] = (menu if (opened and i == place) else L + 0x2000 + i).to_bytes(8, 'little')      # (the other cells: other menus)
    m[(menu + ENGINE.MENU_GIFT_EXP_STATE, 1)] = bytes([state])
    def mem(ad, n):
        if crash: raise RuntimeError('memoire illisible')
        return m[(ad, n)]
    return types.SimpleNamespace(core=types.SimpleNamespace(mem=mem), L=L)


def is_waiting(eng): return ENGINE.Engine.awaits_touch(eng)


class MenuDetection(unittest.TestCase):
    def test_opened_at_last_state(self): self.assertTrue(is_waiting(mock_engine()))

    def test_all_cells_of_the_array(self):
        for i in range(8): self.assertTrue(is_waiting(mock_engine(place=i)), i)

    def test_other_menu_states(self):
        for state in (0, 1, 3): self.assertFalse(is_waiting(mock_engine(state=state)), state)          # experience counting, levels, ...: A turns the message pages as usual

    def test_menu_closed_even_if_state_remained_at_2(self):
        self.assertFalse(is_waiting(mock_engine(opened=False)))                                    # the state stays at 2 after closing: without the array, every following message of the game would receive the touch instead of A

    def test_without_manager(self): self.assertFalse(is_waiting(mock_engine(manager=False)))

    def test_unreadable_memory(self): self.assertFalse(is_waiting(mock_engine(crash=True)))      # never an exception in the key loop

    def test_game_addresses(self):
        self.assertEqual((ENGINE.MENU_MANAGER, ENGINE.MENU_GIFT_EXP, ENGINE.MENU_GIFT_EXP_STATE, ENGINE.MENU_GIFT_EXP_WAIT, ENGINE.OPENED_MENUS), (0x252078, 0x24c730, 0x30, 2, 8))      # MenuManager::execute and gMaterielMenu_EXTRA_PRESENT_EXP (re-read in the library)


class KeyConversion(unittest.TestCase):
    def test_a_becomes_touch_only(self):
        p, decl = EN.touch_for_engine(A | 0x1, A, A, B, TALK, True)
        self.assertEqual(decl, TALK); self.assertEqual(p, 0x1)                               # A and B removed from the held keys, the direction remains
        p, decl = EN.touch_for_engine(A | B, A | B, A, B, TALK, True)
        self.assertEqual((p, decl), (0, TALK))                                               # exactly 0x100: 0x110 would not pass

    def test_without_wait_nothing_changes(self):
        for p, decl in ((A, A), (0, 0), (B, B), (A | 0x4, A | 0x4)): self.assertEqual(EN.touch_for_engine(p, decl, A, B, TALK, False), (p, decl))

    def test_another_key_does_not_trigger(self):
        self.assertEqual(EN.touch_for_engine(0x4, 0x4, A, B, TALK, True), (0x4, 0x4))        # a direction, B alone: only A (or click, Enter, Space which become A) counts as a touch
        self.assertEqual(EN.touch_for_engine(B, B, A, B, TALK, True), (B, B))


class GamePad(unittest.TestCase):
    def test_why_a_was_not_enough(self):
        self.assertEqual(game_pad(A), 0)                    # A key: g_Pad + 2 stays zero, the menu waits forever (the lock-up)
        self.assertEqual(game_pad(A | TALK), 0)           # not 0x110 either: the touch must be alone
        self.assertEqual(game_pad(0), 0)
        self.assertEqual(game_pad(TALK), 0x10)            # the screen touch: it passes
        self.assertEqual(game_pad(0x400), 0x20); self.assertEqual(game_pad(0x800), 0x40); self.assertEqual(game_pad(0x1000), 0x80); self.assertEqual(game_pad(0x2000), 0x400)

    def test_conversion_lifts_the_wait(self):
        p, decl = EN.touch_for_engine(A, A, A, B, TALK, True)
        self.assertNotEqual(game_pad(decl), 0)


class Wiring(unittest.TestCase):
    def test_inputs_calls_the_conversion(self):
        """Game._entries (window/keyboard_mouse.py, needs pyglet: read as text) sends A to the engine after the conversion, only when a message is open (on the field, A = talk, already 0x100)."""
        with open(os.path.join(ROOT, 'dq456_pc', 'window', 'keyboard_mouse.py'), encoding='utf-8') as f: src = f.read()
        self.assertIn('from dq456_pc.window import inputs as EN', src)
        line = [l for l in src.split('\n') if 'EN.touch_for_engine(' in l]
        self.assertEqual(len(line), 1)
        self.assertIn('elif decl & ENGINE.A:', line[0]); self.assertIn('eng.awaits_touch()', line[0]); self.assertIn('BTN_TALK', line[0])
        i = src.index('elif not eng.msg_visible:'); j = src.index('EN.touch_for_engine(')
        self.assertLess(i, j)                                  # after the field branch (without a message): it keeps priority


if __name__ == '__main__':
    unittest.main(verbosity=1)
