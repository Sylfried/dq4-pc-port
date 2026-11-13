"""Viewer mouse / keyboard inputs: the pure logic (no window or OpenGL), so that it can be tested (tests/test_entries.py).
- mouse_active / MouseGuard: when the pointer takes over again after keyboard use (hover and selection);
- WheelGesture / rotate: wheel click (simple click = camera brought back to north by the game, drag left / right = camera rotation, adjustable direction);
- info_zone: where the F1 info block is placed (top right)."""
import math, sys

# ---- pointer and keyboard
MOUSE_TOLERANCE = 4.0        # pixels: distance, from the pointer position when the keyboard was last used, beyond which the mouse takes over again (hover, selection). CUMULATIVE count from that position
                              # (and not from one event to the next: a modern mouse sends events of 1 to 2 pixels, never "large enough" one at a time); a tremor of the table or the sensor (1 to 2
                              # px) does not take over


def mouse_active(ref, pos, tol=MOUSE_TOLERANCE):
    """Has the pointer really moved? `ref`: pointer position (x, y) when the keyboard was last used (None = the mouse already has control: a click, or a real movement since);
    `pos`: current position. True if the mouse has control or if the pointer has moved away from `ref` by at least `tol` pixels. A click never needs this test: it always acts."""
    if ref is None or pos is None: return True
    return math.hypot(pos[0] - ref[0], pos[1] - ref[1]) >= tol


class MouseGuard:
    """Memory of the "last device": the keyboard (key pressed) freezes the reference position; the first real movement (mouse_active) or a click gives control back to the mouse, with no delay."""

    def __init__(self, tol=MOUSE_TOLERANCE):
        self.tol = tol; self.ref = None

    def keyboard(self, pos):
        """A key has just been pressed, the pointer is at `pos` (None: position unknown, the first movement counts)."""
        self.ref = None if pos is None else (float(pos[0]), float(pos[1]))

    def click(self):
        self.ref = None

    @property
    def mouse(self):
        return self.ref is None

    def has_moved(self, pos):
        """Pointer movement to `pos`: true if the mouse has (or takes back) control, false if it is just a tremor after keyboard use."""
        if mouse_active(self.ref, pos, self.tol): self.ref = None; return True
        return False


# ---- the system's own click values (Windows is the reference)
CLICK_DEFAULTS = (0.5, 4, 4)    # Windows defaults: double-click time 500 ms, drag rectangle 4 x 4 pixels (used without Windows, or if the call fails)


def system_click():
    """Windows mouse settings, re-read at each call (the player may change them while the game runs): (click / hold limit in seconds, drag threshold x, y in pixels).
    Click / hold: GetDoubleClickTime ("Double-click speed" slider of the Mouse panel): a press held longer can no longer be a click, it is a hold (Windows has no separate mouse "hold" setting).
    Drag: SM_CXDRAG / SM_CYDRAG, the distance Windows itself requires before a press becomes a drag. The double click itself: menus.pause.system_double_click."""
    t, w, h = CLICK_DEFAULTS
    if sys.platform == 'win32':
        try:
            import ctypes; u = ctypes.windll.user32
            t = max(0.05, u.GetDoubleClickTime() / 1000.0); w, h = max(1, int(u.GetSystemMetrics(68))), max(1, int(u.GetSystemMetrics(69)))
        except Exception: pass
    return t, w, h


def is_drag(dx, dy):
    """Has the pointer moved far enough since the press to be a drag (Windows' drag rectangle)?"""
    _t, w, h = system_click()
    return abs(dx) > w or abs(dy) > h


# ---- wheel click
CAM_MOUSE_YAW = 180.0      # horizontal drag: degrees of camera rotation for a movement equal to the window height (the sensitivity does not depend on the resolution); right = right arrow


class WheelGesture:
    """A middle-button gesture: press, movements, release. A click (release before leaving Windows' drag rectangle, see is_drag) recenters the camera; a drag makes it rotate left / right
    (only the horizontal movement counts), from the point where the threshold is crossed (no jump at the start); after a drag, the release recenters nothing (a click followed by a movement is not a click)."""

    def __init__(self, threshold=None):
        self.threshold = threshold; self.cancel()          # (None: the system's drag threshold; a number: that distance, for the tests)

    def cancel(self):
        self.in_progress = False; self.dragging = False; self.origin = None; self.last = None

    def press_state(self, x, y):
        self.in_progress = True; self.dragging = False; self.origin = (x, y); self.last = (x, y)

    def move_to(self, x, y):
        """Pointer at (x, y), middle button down -> horizontal movement in pixels (to the right: positive) to apply to the camera; 0 as long as the gesture remains a click."""
        if not self.in_progress: return 0.0
        if not self.dragging:
            dx, dy = x - self.origin[0], y - self.origin[1]
            if (math.hypot(dx, dy) < self.threshold) if self.threshold is not None else not is_drag(dx, dy): return 0.0
            self.dragging = True; self.last = (x, y); return 0.0
        dx = x - self.last[0]; self.last = (x, y)
        return float(dx)

    def let_go(self):
        """-> True if it was a simple click (the camera recenters), False after a drag or with no press."""
        was_in_progress, was_dragging = self.in_progress, self.dragging
        self.cancel()
        return bool(was_in_progress and not was_dragging)


def rotate(requested, dx, height_px, invert_gd=False, maximum=180.0):
    """Horizontal drag of dx pixels -> camera rotation to perform, in degrees (positive: to the right, like the right arrow): same magnitude as the arrows. `requested`: what remained to rotate (the game only rotates in notches,
    see Game._camera_after_step); the total stays between -maximum and +maximum. `invert_gd` ("Invert left / right" setting): the drag direction is inverted; the keyboard arrows do not go through here.
    The location's limits, the locks and the scenes are the game's: it refuses the rotation (Engine.camera_wait) and the request is dropped."""
    if invert_gd: dx = -dx
    return max(-maximum, min(maximum, requested + dx / max(1.0, float(height_px)) * CAM_MOUSE_YAW))


# ---- F1 info block
def info_zone(width_px, height_px, column, ui_zoom, ui_pos='center'):
    """F1 info block (location, settings, performance): (side, available width); the side is 'right' by default (top right of the screen), 'left' if the interface column occupies the right.
    The width is the free margin next to the interface column (portrait 450 x 800, enlarged by ui_zoom; `column` false: no game windows, the whole screen), so as not to hide its windows; at least 260 pixels."""
    col_width = 450 * height_px / 800.0 * ui_zoom
    if column and ui_pos == 'right': return 'left', int(max(260, width_px - col_width - 16))
    if column and ui_pos == 'left': return 'right', int(max(260, width_px - col_width - 16))
    if column: return 'right', int(max(260, (width_px - col_width) / 2 - 16))
    return 'right', int(max(260, width_px - 20))


# ---- menu that receives the keys when a message is displayed
def menu_under_message(eng, port):
    """Port that receives the keys when a message is visible and the menu designated by the engine (`active_menu`) is not waiting for input: the one that is waiting (`input_menus`, the most recent), otherwise None
    (the keys go to the message: A turns the page).

    `active_menu` first takes the engine's menu stack and falls back to `input_menus` only if it is empty: a Yes / No box opened ON TOP OF a menu in the stack is therefore not the one it returns.
    Measured (poker, hand won, frame 879): `active_menu` returns the board (port 12, type 48, no input) while the quit-or-double (port 2, type 1, "Yes" / "No" cells) asks for it;
    the keys went nowhere while the mouse, which walks `input_menus`, responded. Applies to any engine box opened under a message, not just poker.
    """
    if port is None or not eng.msg_visible or eng.ui.f[port].get('input'): return port
    return next(iter(eng.input_menus()), None)


# ---- A key while waiting for a "touch"
def touch_for_engine(p, decl, bit_a, bit_b, touch, is_waiting):
    """(p, decl) sent to the engine. `is_waiting`: a game menu is waiting for the screen touch (Engine.awaits_touch: the king's experience gift); `touch`: the value it reads (exactly 0x100). A (key, click, Enter, Space) sends this touch
    alone, without A or B; the rest of the time nothing changes. An open message would otherwise receive A (0x10), which this menu does not read: the game stayed frozen on the last level message."""
    if is_waiting and decl & bit_a: return p & ~(bit_a | bit_b), touch
    return p, decl
