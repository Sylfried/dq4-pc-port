"""Dragon Quest VI's slime curling: the touch screen of SlimeCurlingPort (the logic is in core/slime_curling.py).

The engine draws the game (a 3D scene) and reads the touch screen: the mouse is the finger (left button held = touching). The window shows the phone's whole height (the slime waits at
the bottom of its screen; camera.py), the phone's screen centered in it, so the points of the world that the engine asks to place (the slime) and the pointer use the same units.
With the keys or a gamepad the port moves the finger for the player: to throw, hold A (the finger grabs the slime and pulls it back, further the longer A is held), aim with left / right,
release A; while the slime slides, left / right rub the ice in that half of the zone shown under it (A alone rubs both halves in turn).
"""
import numpy as np
from dq456_pc.core import slime_curling as SC
from dq456_pc.core import engine as ENGINE
from dq456_pc.window.constants import ASPECT_PORTRAIT

PULL_STEP, PULL_MAX = 3.0, 72.0          # keys: the finger pulls the slime back by 3 LCD units per frame while A is held, 72 at most
AIM_STEP, AIM_MAX = 2.0, 48.0            # keys: left / right move the finger sideways (the slime leaves toward the other side: the throw goes the way the key points)
RUB_PERIOD = 8                           # keys: frames of one back and forth of the finger rubbing the ice
RUB_NEAR, RUB_FAR = 6.0, 56.0            # keys: the finger's sideways range in one half of the zone (its center +- 64)


def rub_x(center_x, side, frame):
    """The finger rubbing the ice in one half of the slide's zone (side -1 left, +1 right): back and forth between RUB_NEAR and RUB_FAR units from the middle."""
    k = frame % RUB_PERIOD; t = (k if k <= RUB_PERIOD // 2 else RUB_PERIOD - k) / (RUB_PERIOD / 2.0)
    return center_x + side * (RUB_NEAR + (RUB_FAR - RUB_NEAR) * t)


class SlimeCurlingMixin:
    _cu_touch = False            # left button held during the curling
    _cu_pull = None              # keys: the throw being prepared [pull, aim] (A held), None otherwise
    _cu_rub = 0                  # keys: frames of rubbing

    def _curling_live(self):
        cu = getattr(self.engine.ui, 'curling', None)
        return cu is not None and cu['live']

    def _cu_viewport(self, wx, wy):
        """The window shows the phone's whole height during the curling (camera.py, _whole_phone_height)."""
        return SC.window_to_viewport(wx, wy, self.width, self.height, 1.0 / ASPECT_PORTRAIT, ASPECT_PORTRAIT)

    def _cu_world_viewport(self, p):
        """A point of the world -> its place on the phone's screen, through the scene's camera of the last drawing (None before one)."""
        M = getattr(self, '_M_town', None)
        if M is None: return None
        c = M @ np.array([p[0], p[1], p[2], 1.0])
        if abs(c[3]) < 1e-9: return None
        wx = (c[0] / c[3] + 1.0) / 2.0 * self.width; wy = (c[1] / c[3] + 1.0) / 2.0 * self.height
        return self._cu_viewport(wx, wy)

    def curling_press(self, x, y):
        """Left button pressed during the curling: the finger touches the screen (on_mouse_drag follows it). -> True if the curling has the click (not while a game window waits
        for the keys or a message is open: the click goes to them)."""
        eng = self.engine
        if not self._curling_live() or eng.msg_visible or eng.input_menus(): return False
        self._cu_touch = True; self.mouse = (x, y); return True

    def curling_release(self):
        if not self._cu_touch: return False
        self._cu_touch = False; return True

    def _cu_key_finger(self, p):
        """Keys / gamepad -> the finger made for the player: (touching, LCD x, LCD y), or None when the keys do nothing.
        Slide (its zone shown): left / right rub the ice in that half of the zone (the slime turns, and goes on longer), A alone rubs both halves in turn.
        Otherwise (the throw): A held grabs the slime where the engine placed it and pulls it back, left / right aim; releasing A lets it go."""
        eng = self.engine; cu = eng.ui.curling
        shown, center = eng.curling_target()
        if shown and center is not None:
            self._cu_pull = None
            side = -1 if p & ENGINE.LEFT else 1 if p & ENGINE.RIGHT else (-1 if (self._cu_rub // RUB_PERIOD) % 2 else 1) if p & ENGINE.A else 0
            if not side: self._cu_rub = 0; return None
            self._cu_rub += 1
            return True, rub_x(center[0], side, self._cu_rub), float(center[1])
        self._cu_rub = 0
        if not p & ENGINE.A:
            if self._cu_pull is None: return None
            pull, aim = self._cu_pull; self._cu_pull = None
            return False, cu['answered'][0] - aim, cu['answered'][1] + pull          # (released: the throw)
        if self._cu_pull is None: self._cu_pull = [0.0, 0.0]
        self._cu_pull[0] = min(PULL_MAX, self._cu_pull[0] + PULL_STEP)
        if p & ENGINE.LEFT: self._cu_pull[1] = max(-AIM_MAX, self._cu_pull[1] - AIM_STEP)
        if p & ENGINE.RIGHT: self._cu_pull[1] = min(AIM_MAX, self._cu_pull[1] + AIM_STEP)
        pull, aim = self._cu_pull if self._cu_pull[0] > PULL_STEP else (0.0, 0.0)          # (the first frame touches the slime itself: the engine grabs it within 14 units)
        return True, cu['answered'][0] - aim, cu['answered'][1] + pull

    def curling_inputs(self):
        """Before each engine step of the curling: the touch panel's message (the finger, or the swipe made for the keys) and the answer to the engine's point."""
        if not self._curling_live(): self._cu_touch = False; self._cu_pull = None; self._cu_rub = 0; return
        eng = self.engine; cu = eng.ui.curling
        p = 0 if self.pause.opened else self.pad()
        keys = None if self._cu_touch else self._cu_key_finger(p)          # (the mouse first)
        if keys is not None:
            touching = keys[0]; vx, vy = keys[1] / SC.LCD_WIDTH, 0.5 - keys[2] / SC.lcd_height(ASPECT_PORTRAIT)
        else:
            touching = self._cu_touch
            vx, vy = self._cu_viewport(*self.mouse) if touching and getattr(self, 'mouse', None) else (0.0, 0.0)
        msg = SC.touch_message(cu, eng.flags(), touching, (vx, vy), ASPECT_PORTRAIT)
        port = SC.port_of(cu, SC.TOUCH_PANEL)
        if msg is not None: eng.send_menu(port, *msg)
        if cu['point'] is not None:
            vp = self._cu_world_viewport(cu['point'])
            ans = SC.convert_answer(cu, vp, ASPECT_PORTRAIT) if vp is not None else None
            if ans is not None: eng.send_menu(SC.port_of(cu, SC.CONVERT_POSITION), *ans)
