"""Test of the port that receives the keys when a message is shown (`inputs.menu_under_message`).

The finding: in poker, once the hand is won, the "Double or nothing" box could be answered **only with the mouse**.

The cause (measured on the real engine, map ev04, frame 879 of a won hand): the engine opens the Yes / No box on a port of its own (port 2, type 1) **on top of** the poker board (port 12, type 48),
and shows a message at the same time. `Engine.active_menu` first consults the engine's menu stack and falls back to `input_menus` only if it is empty: so it returns the board, which waits for no input.
`_entries` then discarded the port (`port = None`) and the keys went to the message. The mouse, for its part, walks through `input_menus`: it found the Yes / No and answered. Hence "the mouse works, the keyboard does not".

The fix is global: any engine box opened under a message receives the keys, as it already receives the touch; when no window waits for input, nothing changes (A turns the page).

    python3 tests/test_menu_under_message.py
No screen, no GL, no APK.
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.window import inputs as EN


def engine(msg, ports):
    """Fake engine: `ports` = {port : (waits_for_input, order)}. `input_menus` sorts like the real one (most recent first)."""
    f = {p: {'input': waits, 'order': order, 'visible': True, 'cells': {(0, 0): 'x'}} for p, (waits, order) in ports.items()}
    eng = types.SimpleNamespace(msg_visible=msg, ui=types.SimpleNamespace(f=f))
    eng.input_menus = lambda: sorted((p for p, g in f.items() if g['input']), key=lambda p: -f[p]['order'])
    return eng


POKER = {12: (False, 2), 2: (True, 1)}          # the measured state: board without input (engine stack), Yes / No with input


class UnderMessage(unittest.TestCase):
    def test_the_box_that_waits_gets_the_keys(self):
        """the double-or-nothing case, as it was measured."""
        self.assertEqual(EN.menu_under_message(engine(True, POKER), 12), 2)

    def test_the_keys_go_where_the_touch_goes(self):
        """The mouse takes `input_menus()`: the keyboard must land on the same port."""
        eng = engine(True, POKER)
        self.assertEqual(EN.menu_under_message(eng, 12), eng.input_menus()[0])

    def test_no_window_waiting_leaves_the_message_the_keys(self):
        """No window waiting for input: nothing changes, A turns the page (this is the usual case of a message on top of a menu)."""
        self.assertIsNone(EN.menu_under_message(engine(True, {12: (False, 2)}), 12))

    def test_the_designated_menu_waits_itself(self):
        """The menu on the stack waits for input: it keeps the keys, with no detour."""
        self.assertEqual(EN.menu_under_message(engine(True, {12: (True, 2), 2: (True, 1)}), 12), 12)

    def test_no_message_changes_nothing(self):
        for port in (12, None):
            self.assertEqual(EN.menu_under_message(engine(False, POKER), port), port)

    def test_no_menu_at_all(self):
        self.assertIsNone(EN.menu_under_message(engine(True, POKER), None))

    def test_the_most_recent_of_several_boxes(self):
        """Several windows waiting for input: the most recent one, as `input_menus` sorts them and as the mouse does."""
        self.assertEqual(EN.menu_under_message(engine(True, {12: (False, 2), 2: (True, 5), 3: (True, 9)}), 12), 3)


class Wiring(unittest.TestCase):
    def test_entries_uses_it(self):
        """The decision is no longer written twice in `_entries` (that was the line that discarded the port)."""
        import inspect
        from dq4_pc.window import keyboard_mouse as KM
        body = inspect.getsource(KM.KeyboardMouseMixin._entries)
        self.assertIn('EN.menu_under_message(eng, port)', body)
        self.assertNotIn("eng.msg_visible and not eng.ui.f[port].get('entree'): port = None", body)


if __name__ == '__main__':
    unittest.main(verbosity=2)
