"""Test of the floating "Interface" panel (Esc menu > "Display" > "Interface"): drag by the title bar, fold / unfold, double click.

    python3 tests/test_interface_panel.py

Replays the sequence of events of a real mouse, as pyglet sends them to the window (on_mouse_press -> Pause.click, on_mouse_drag -> Pause.drag_to with dx / dy, on_mouse_release -> Pause.release;
the clock is simulated, the frame loop calls Pause.do_update):
  - press then drag right away (without waiting for the long press): the panel follows the pointer and does not fold;
  - press without moving (or with a jitter of a few pixels): fold / unfold;
  - press held without moving (lift) then drag: it follows too;
  - double click: back to the original position; double press followed by a drag: it moves;
  - double click detection aligned with Windows: delay counted from the START of the first press, rectangle SM_CXDOUBLECLK x SM_CYDOUBLECLK centered on it, and a single click folds as soon as the double click has
    become impossible (delay elapsed, pointer left the rectangle, another press) instead of waiting needlessly.
"""
import os, sys, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False          # no hidden window: the test runs without a display server
from dq456_pc.persistence import settings as RG

try:
    from dq456_pc.menus import pause as PA
except Exception as ex:          # pause.py needs pyglet (without a display: the import alone is enough)
    PA = None; ERROR = ex

LEFT, RIGHT_BUTTON = 1, 4             # pyglet.window.mouse.LEFT / RIGHT
BORDER = (600.0, 300.0, 1240.0, 700.0)         # unfolded panel: x0, y0, x1, y1 (1280 x 720 window)
BARRE = (600.0, 636.0, 1240.0, 700.0)         # title bar (fold_zone)


class Mouse:
    """Simulated mouse: clock and pyglet events sent to the Pause menu of a fake game."""
    def __init__(self):
        self.t = 1000.0
        game = types.SimpleNamespace(reg=RG.Settings(None), hud=types.SimpleNamespace(taken=None, place=lambda: None), width=1280, height=720,
                                    sound=types.SimpleNamespace(listening=False, listen=lambda b: None, tick=lambda: None), key_list={})
        self.P = PA.Pause(game); P = self.P
        P.opened = True; P.stack = ['root', 'display', 'interface']; P.panel_border = BORDER; P.fold_zone = BARRE
        self.x = self.y = None
        self.patch = mock.patch.object(PA.time, 'time', lambda: self.t); self.patch.start()

    def end(self): self.patch.stop()

    def wait(self, s):
        """Time passes (loop frames: Pause.do_update on every frame)."""
        for _ in range(max(1, int(s / 0.016))): self.t += 0.016; self.P.do_update()

    def press_state(self, x, y, button=LEFT): self.x, self.y = x, y; self.P.click(x, y, button)

    def dragging(self, x, y):
        self.x, self.y = x, y
        self.P.drag_to(x, y)                                           # (window.on_mouse_drag: x, y, dx, dy, buttons, modifiers; only x and y are used)
        self.t += 0.008; self.P.do_update()

    def release(self, button=LEFT): self.P.release(self.x, self.y, button)

    def gesture(self, initial, points, button=LEFT):
        self.press_state(*initial, button=button)
        for p in points: self.dragging(*p)
        self.release(button)


@unittest.skipIf(PA is None, 'pause.py non importable ici')
class Panel(unittest.TestCase):
    def setUp(self): self.S = Mouse(); self.P = self.S.P
    def tearDown(self): self.S.end()

    def test_slide_right_away(self):
        """Press and immediate movement (less than LONG_PRESS_DELAY): the panel follows the pointer, without folding."""
        S, P = self.S, self.P
        S.gesture((900, 670), [(902, 669), (906, 667), (915, 660), (870, 620), (820, 560), (800, 500)])
        self.assertEqual(P.pan_pos, (800 - (900 - BORDER[2]), 500 - (670 - BORDER[3])))          # top right corner = pointer - press offset
        self.assertFalse(P.folded); self.assertIsNone(P.pan_pressed)
        self.assertEqual(P.pan_click_t, 0.0)                                                    # a drag is not a click (no double click afterwards)

    def test_slide_during_long_press(self):
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.6); self.assertTrue(P.pan_pressed['long'])               # lift after Windows' click / hold limit (0.5 s by default) without moving
        S.dragging(700, 600); S.dragging(500, 300); S.release()
        self.assertEqual(P.pan_pos, (500 - (900 - BORDER[2]), 300 - (670 - BORDER[3]))); self.assertFalse(P.folded)

    def test_long_press_without_moving_does_not_fold(self):
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.6); S.release()
        self.assertFalse(P.folded); self.assertIsNone(P.pan_pos)

    def test_short_press_folds(self):
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.1); S.release(); S.wait(0.6); self.assertTrue(P.folded)       # (the folding waits for the end of the double click delay)
        S.wait(1.0); S.press_state(900, 670); S.wait(0.1); S.release(); S.wait(0.6); self.assertFalse(P.folded)       # (late enough: not a double click)
        self.assertIsNone(P.pan_pos)

    def test_mouse_shake(self):
        """A few pixels of jitter during a click (inside Windows' drag rectangle, 4 x 4 by default): it is a click, not a drag."""
        S, P = self.S, self.P
        S.gesture((900, 670), [(903, 669), (904, 672), (902, 668)]); S.wait(0.6)
        self.assertTrue(P.folded); self.assertIsNone(P.pan_pos)

    def test_double_click_origin_position(self):
        S, P = self.S, self.P
        P.pan_pos = (700.0, 500.0)
        S.press_state(900, 670); S.wait(0.08); S.release(); self.assertFalse(P.folded)             # first click: nothing moves yet (waiting for a possible second click)
        S.wait(0.1); S.press_state(900, 670); S.wait(0.08); S.release()                         # second click within DOUBLE_CLICK_DELAY
        self.assertFalse(P.folded); self.assertIsNone(P.pan_pos)                                 # the panel goes back to its original place, without having changed state
        S.wait(1.0); self.assertFalse(P.folded)                                              # and the first click's folding does not happen afterwards

    def test_simple_click_single_change_after_delay(self):
        """a single click folds only once the double click delay has elapsed, and only once; the delay runs from the START of the press (like Windows), not from its release."""
        S, P = self.S, self.P
        t0 = S.t; savestates = []; instants = []
        S.press_state(900, 670); S.wait(0.05); S.release()
        for _ in range(60): S.wait(0.016); savestates.append(P.folded); instants.append(S.t - t0)
        self.assertFalse(savestates[0]); self.assertTrue(savestates[-1])                                 # folded, but not right away
        self.assertEqual(sum(1 for a, b in zip(savestates, savestates[1:]) if a != b), 1)                # a single state change
        when = instants[savestates.index(True)]
        self.assertGreaterEqual(when, PA.DOUBLE_CLICK_DELAY - 1e-6)                            # not before the end of the delay (counted from the press)
        self.assertLess(when, PA.DOUBLE_CLICK_DELAY + 0.02)                                    # and without waiting any longer: no delay added after the release

    def test_delay_counted_from_start_of_first_press(self):
        """(Windows): second press 0.45 s from the START of the first (so 0.40 s after its release) = double click; at 0.55 s from the start = two single clicks, even if 0.5 s does not separate the release from the second."""
        S, P = self.S, self.P
        P.pan_pos = (700.0, 500.0)
        S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(0.40)                      # 0.45 s after the start of the first press
        self.assertFalse(P.folded)
        S.press_state(900, 670); S.wait(0.05); S.release()
        self.assertIsNone(P.pan_pos); S.wait(1.0); self.assertFalse(P.folded)                # double click: back to the origin, no folding
        S.wait(1.0)
        S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(0.52)                       # 0.57 s after the start of the first: the first click is already registered
        self.assertTrue(P.folded)                                                                # (folds after 0.5 s, without waiting for one more delay)
        S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(0.6); self.assertFalse(P.folded)      # the second is a single click: it unfolds

    def test_double_click_rectangle(self):
        """(Windows): the second press must fall inside the SM_CXDOUBLECLK x SM_CYDOUBLECLK rectangle centered on the first; otherwise it is one more single click."""
        S, P = self.S, self.P
        delay, w, h = PA.system_double_click()
        S.press_state(900, 670); S.wait(0.04); S.release(); S.wait(0.04)
        S.press_state(900 + w / 2.0 + 3, 670); S.wait(0.04); S.release()                         # too far: not a double click, the first click folds right away
        self.assertTrue(P.folded)
        S.wait(1.0); self.assertFalse(P.folded)                                              # and the second (single) one unfolded after its own delay
        P.pan_pos = (700.0, 500.0)
        S.press_state(900, 670); S.wait(0.04); S.release(); S.wait(0.04)
        S.press_state(900 + w / 2.0 - 1, 670 - h / 2.0 + 1); S.wait(0.04); S.release()           # inside the rectangle: double click
        self.assertIsNone(P.pan_pos); S.wait(1.0); self.assertFalse(P.folded)

    def test_folding_does_not_wait_if_double_click_impossible(self):
        """pointer left the rectangle after the release (hover) = the single click is registered, the panel folds right away, without waiting for the end of the delay."""
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.04); S.release(); self.assertFalse(P.folded)
        S.t += 0.03; P.hovered(900, 670); self.assertFalse(P.folded)                              # pointer still in place: still waiting
        S.t += 0.03; P.hovered(900 + 40, 670); self.assertTrue(P.folded)                          # it moved away: no double click possible anymore, the single click acts immediately
        S.wait(1.0); self.assertTrue(P.folded)                                               # only once

    def test_a_press_elsewhere_acquires_the_pending_click(self):
        """another press (outside the rectangle) immediately confirms the single click that was waiting, instead of leaving it pending."""
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.04); S.release(); S.wait(0.04)
        S.press_state(900, 500); self.assertTrue(P.folded)                                              # (click on a panel line, far from the bar)
        S.release(); S.wait(1.0); self.assertTrue(P.folded)

    def test_press_longer_than_delay_folds_on_release(self):
        """if the press already lasted longer than the double click delay (short system delay), the single click is registered as soon as it is released."""
        S, P = self.S, self.P
        with mock.patch.object(PA, 'system_double_click', lambda: (0.2, 4, 4)), mock.patch.object(PA, 'LONG_PRESS_DELAY', 5.0):
            S.press_state(900, 670); S.wait(0.3); S.release()
            self.assertTrue(P.folded); S.wait(1.0); self.assertTrue(P.folded)

    def test_double_click_never_changes_the_state(self):
        """a double click on a folded or unfolded panel neither folds nor unfolds it, at any moment."""
        S, P = self.S, self.P
        for initial in (False, True):
            P.folded = initial; P.pan_pos = (700.0, 500.0); P.pan_click_t = 0.0; P.pan_fold_at = None; P.pan_click_pos = None
            S.wait(1.0)
            seen = set()
            S.press_state(900, 670); S.wait(0.05); S.release(); seen.add(P.folded)
            S.wait(0.1); seen.add(P.folded); S.press_state(900, 670); S.wait(0.05); S.release(); seen.add(P.folded)
            for _ in range(60): S.wait(0.016); seen.add(P.folded)
            self.assertEqual(seen, {initial}, 'depart replie=%s' % initial); self.assertIsNone(P.pan_pos)

    def test_third_click_after_a_double_click_is_a_single_click(self):
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(0.1); S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(1.0)
        self.assertFalse(P.folded)
        S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(0.6); self.assertTrue(P.folded)

    def test_click_then_drag_folds_then_moves(self):
        """A click immediately followed by a drag: the click folds first (as before), then the panel follows the pointer."""
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.05); S.release(); S.wait(0.1)
        S.gesture((900, 670), [(880, 650), (700, 500)])
        self.assertTrue(P.folded); self.assertIsNotNone(P.pan_pos); S.wait(1.0); self.assertTrue(P.folded)      # (a single folding)

    def test_double_press_then_slide(self):
        """A drag right after a click moves the panel (it does not go back to the origin)."""
        S, P = self.S, self.P
        S.press_state(900, 670); S.wait(0.08); S.release(); S.wait(0.1)
        S.gesture((900, 670), [(880, 650), (700, 500)])
        self.assertEqual(P.pan_pos, (700 - (900 - BORDER[2]), 500 - (670 - BORDER[3])))

    def test_slide_then_slide(self):
        S, P = self.S, self.P
        S.gesture((900, 670), [(850, 640), (800, 600)]); p1 = P.pan_pos
        S.wait(0.1); S.gesture((900, 670), [(940, 660)])                                      # new press just afterwards: a drag, not a double click
        self.assertNotEqual(P.pan_pos, p1); self.assertIsNotNone(P.pan_pos); self.assertFalse(P.folded)

    def test_outside_title_bar(self):
        S, P = self.S, self.P
        S.press_state(900, 500); self.assertIsNone(P.pan_pressed)                                       # a panel line, not the bar: no panel drag
        S.release(); S.press_state(900, 670, button=RIGHT_BUTTON); self.assertIsNone(P.pan_pressed)            # right click: Cancel, no drag

    def test_position_kept_within_screen(self):
        P = self.P
        for pos in ((5000.0, 5000.0), (-300.0, -300.0)):
            P.pan_pos = pos; x0, y1 = P._panel_pos(640.0, 400.0, 1280, 720, 0.8)
            self.assertTrue(0 <= x0 and x0 + 640 <= 1280 and 400 <= y1 <= 720, (pos, x0, y1))
        for W, H, pos in ((1920, 1080, (5000.0, 5000.0)), (2560, 1440, (-50.0, -50.0))):         # window larger than 1280 x 720
            P.pan_pos = pos; x0, y1 = P._panel_pos(640.0, 400.0, W, H, 1.2)
            self.assertTrue(0 <= x0 and x0 + 640 <= W and 400 <= y1 <= H, (W, pos, x0, y1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
