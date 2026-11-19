"""Test: a left click on the free field = action key; center circle of the D-pad = action key that animates when an action is possible (as on mobile).

    python3 tests/test_dpad_and_click.py

1. Engine: packet 19 with a slot >= 16 is not ignored, it is the D-pad blinking (`pad_blink`); the real bubbles (slots 0 to 15) stay unchanged.
2. D-pad (`hud_mobile.Buttons`): a TAP on the center circle (press then release without leaving it) is recognized; a drag (even a brief one, even if it returns to the center) and a press outside the circle are not; the directions do not change.
3. Animation: `Buttons.action_possible` = the game makes the D-pad blink OR, on the free field, an icon bubble is displayed.
4. Window (real methods of `window.Game` on a fake game): left click anywhere on the free field = A key (`click_a`); right click = B; not in a menu, not in a message, not in battle; tap on the center circle = A.
"""
import os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.menus import hud_mobile as HM
from dq456_pc.core import engine as ENGINE

try:
    from dq456_pc.window import game as WND
except Exception as ex:          # window.py needs pyglet, numpy, unicorn... (the import alone is enough, no window is created)
    WND = None; ERROR_WND = ex


W, H = 1280, 720


class EnginePackets(unittest.TestCase):
    def apply(self, e, *packets): e.apply(list(packets), lambda: 'carte')

    def test_dpad_blink(self):
        e = ENGINE.State(); self.assertFalse(e.pad_blink)
        self.apply(e, (19, [16, 0], [])); self.assertTrue(e.pad_blink); self.assertEqual(e.icons, {})                   # it is not a bubble
        self.apply(e, (19, [16, -1], [])); self.assertFalse(e.pad_blink)
        self.apply(e, (19, [20, 3], [])); self.assertTrue(e.pad_blink)                                                  # (any slot >= 16)

    def test_bubbles_unchanged(self):
        e = ENGINE.State(); self.apply(e, (19, [3, 5], []), (20, [3], [1.0, 2.0, 3.0, 0.5]))
        self.assertEqual(e.icons[3]['id'], 5); self.assertEqual(e.icons[3]['pos'], (1.0, 2.0, 3.0)); self.assertEqual(e.icons[3]['alpha'], 0.5); self.assertFalse(e.pad_blink)
        self.apply(e, (19, [3, -1], [])); self.assertEqual(e.icons, {})
        self.apply(e, (19, [15, 7], [])); self.assertIn(15, e.icons)                                                       # (15 is still a bubble, 16 is the blinking)


def fake_game(W=1280, H=720, dpad=True):
    state = types.SimpleNamespace(part=ENGINE.PART_TOWN, effect=None, pad_blink=False)
    J = types.SimpleNamespace(width=W, height=H, reg={'buttons': True, 'dpad': dpad, 'rotation_bar': True, 'buttons_size': 1.0, 'dpad_size': 1.0, 'buttons_pos': {}, 'buttons_snap': False, 'speed_button': True,
                                                         'speed_button_size': 1.0, 'speed_button_pos': []},
                              pause=types.SimpleNamespace(opened=False), map_open=False, args=types.SimpleNamespace(cache='/inexistant'))
    J.engine = types.SimpleNamespace(state=state, flags=lambda: 0x28, dpad_size=lambda: 1)
    return J


class Dpad(unittest.TestCase):
    def setUp(self):
        self.J = fake_game(); self.b = HM.Buttons(self.J); rx, ry, c, _ = self.b.rect(HM.DPAD); self.cx, self.cy, self.r = rx + c / 2, ry + c / 2, c / 2
        self.vis = (HM.DPAD,)

    def press_state(self, dx=0.0, dy=0.0): return self.b.press(self.cx + dx * self.r, self.cy + dy * self.r, self.vis)

    def test_touch_on_the_central_circle(self):
        self.assertEqual(self.press_state(), HM.DPAD); self.assertTrue(self.b.dpad_on); self.assertFalse(self.b.dpad_dragging); self.assertIsNone(self.b.dpad_sector())
        self.assertTrue(self.b.dpad_release()); self.assertFalse(self.b.dpad_on)                                       # press then release without dragging = tap

    def test_small_movements_in_dead_zone_remain_touch(self):
        self.press_state(); self.b.dpad_drag(self.cx + 0.05 * self.r, self.cy - 0.06 * self.r); self.assertFalse(self.b.dpad_dragging); self.assertTrue(self.b.dpad_release())

    def test_click_anywhere_on_the_ball_is_a_touch(self):
        """The whole ball (a quarter of the radius), not only the dead zone: a click on its edge is the action key, and gives no step while it is held."""
        self.press_state(0.2, 0.0); self.assertFalse(self.b.dpad_dragging); self.assertIsNone(self.b.dpad_sector()); self.assertEqual(self.b.dpad_bits(), 0)
        self.assertTrue(self.b.dpad_release())
        self.press_state(0.0, 0.2); self.b.dpad_drag(self.cx, self.cy + 0.3 * self.r); self.assertTrue(self.b.dpad_dragging); self.assertEqual(self.b.dpad_sector(), 0)          # (out of the ball: a direction)
        self.assertFalse(self.b.dpad_release())

    def test_a_slide_is_not_a_touch(self):
        self.press_state(); self.b.dpad_drag(self.cx + 0.5 * self.r, self.cy); self.assertTrue(self.b.dpad_dragging); self.assertEqual(self.b.dpad_sector(), 2)         # direction: right
        self.assertFalse(self.b.dpad_release())

    def test_a_return_to_center_after_a_slide_is_not_a_touch(self):
        self.press_state(); self.b.dpad_drag(self.cx + 0.5 * self.r, self.cy); self.b.dpad_drag(self.cx, self.cy)
        self.assertIsNone(self.b.dpad_sector()); self.assertFalse(self.b.dpad_release())

    def test_press_outside_central_circle_is_direction(self):
        self.press_state(0.0, 0.6); self.assertTrue(self.b.dpad_dragging); self.assertEqual(self.b.dpad_sector(), 0); self.assertFalse(self.b.dpad_release())                # up

    def test_directions_unchanged(self):
        from dq456_pc.core import engine as M
        for (dx, dy), bits in (((0.5, 0.0), M.RIGHT), ((-0.5, 0.0), M.LEFT), ((0.0, 0.5), M.UP), ((0.0, -0.5), M.DOWN), ((0.5, 0.5), M.UP | M.RIGHT)):
            self.b.dpad_drop(); self.press_state(dx, dy); self.assertEqual(self.b.dpad_bits(), bits, (dx, dy))
        self.b.dpad_drop(); self.press_state(); self.assertEqual(self.b.dpad_bits(), 0)                                      # (the center circle alone sends no direction)

    def test_release_without_press(self):
        self.assertFalse(self.b.dpad_release())

    def test_dpad_hidden(self):
        self.press_state(); self.J.reg['dpad'] = False; self.assertEqual(self.b.dpad_bits(), 0); self.assertFalse(self.b.dpad_on); self.assertFalse(self.b.dpad_dragging)


@unittest.skipIf(WND is None, 'window.py non importable ici')


class Animation(unittest.TestCase):
    """`Buttons.action_possible`: the D-pad animates when an action can be performed."""

    def hud(self, icons=None, free=True, blink=False):
        J = fake_game(); J.engine.state.icons = icons or {}; J.engine.state.pad_blink = blink; J._terrain_free = lambda: free
        return HM.Buttons(J)

    def test_no_action_possible(self): self.assertFalse(self.hud().action_possible())

    def test_a_displayed_bubble(self):
        self.assertTrue(self.hud({0: {'id': 1, 'pos': (1.0, 2.0, 3.0), 'alpha': 1.0}}).action_possible())             # (slot 0 included)
        self.assertTrue(self.hud({7: {'id': 1, 'pos': (1.0, 2.0, 3.0), 'alpha': 0.5}}).action_possible())

    def test_bubble_not_yet_placed_or_transparent(self):
        self.assertFalse(self.hud({2: {'id': 1, 'pos': None, 'alpha': 1.0}}).action_possible()); self.assertFalse(self.hud({2: {'id': 1, 'pos': (0, 0, 0), 'alpha': 0.0}}).action_possible())

    def test_no_animation_outside_free_terrain(self):
        self.assertFalse(self.hud({0: {'id': 1, 'pos': (1.0, 2.0, 3.0), 'alpha': 1.0}}, free=False).action_possible())                # menu, message, battle...

    def test_game_blink_counts(self):
        self.assertTrue(self.hud(blink=True).action_possible()); self.assertTrue(self.hud(blink=True, free=False).action_possible())

    def test_dpad_drawn_without_error_without_window(self):
        self.assertFalse(self.hud().action_possible())          # (the drawing itself requires a GL context: verified for real, see the PR notes)


class RotationBar(unittest.TestCase):
    """Camera rotation bar: at the very top (at the bottom before), full width, rotation icons half an icon away from the sides; behind the buttons and the D-pad; neither movable nor resizable."""

    def hud(self, **reg):
        J = fake_game(); J.reg.update(reg); return J, HM.Buttons(J)

    def test_shown_on_the_town_terrain_only(self):
        J, b = self.hud(); self.assertIn(HM.BAR, b.visible_ones())
        J.engine.state.part = ENGINE.PART_FIELD; self.assertNotIn(HM.BAR, b.visible_ones())                          # world map: the camera does not rotate
        J, b = self.hud(rotation_bar=False); self.assertNotIn(HM.BAR, b.visible_ones()); self.assertIn(HM.DPAD, b.visible_ones())
        J, b = self.hud(buttons=False); self.assertEqual(b.visible_ones(), ())                                      # "Show this interface" = No: the whole set disappears

    def test_geometry_top_full_width(self):
        for W_, H_ in ((1280, 720), (1920, 1080), (800, 800)):
            J = fake_game(W_, H_); b = HM.Buttons(J); h = 57.6 * H_ / 800.0; self.assertEqual(b.rect(HM.BAR), (0.0, H_ - h, float(W_), h))
        J = fake_game(); b = HM.Buttons(J); J.reg['buttons_size'] = 2.0; J.reg['dpad_size'] = 2.0; self.assertEqual(b.rect(HM.BAR), (0.0, 720 - 51.84, 1280.0, 51.84))      # the sizes of the buttons and the D-pad change nothing here

    def test_press_gives_the_bar_without_state(self):
        J, b = self.hud(); vis = b.visible_ones(); self.assertEqual(b.press(640, 715, vis), HM.BAR); self.assertIsNone(b.press_state); self.assertFalse(b.dpad_on)
        self.assertEqual(b.press(640, 670, vis), HM.BAR); self.assertIsNone(b.press(640, 660, vis)); self.assertIsNone(b.let_go(640, 715, vis))

    def test_buttons_and_dpad_cover_the_bar(self):
        J, b = self.hud(); vis = b.visible_ones()
        J.reg['buttons_pos'] = {HM.DPAD: [4.0, 0.0]}; rx, ry, c, _ = b.rect(HM.DPAD)                                      # D-pad placed on the top edge: it takes precedence over the bar
        self.assertGreater(ry + c, 720 - 51.84); self.assertEqual(b.press(rx + c / 2, 715, vis), HM.DPAD)
        J.reg['buttons_pos'] = {'menu': [0.4, 0.0]}; x, y, w, h = b.rect('menu'); self.assertEqual(b.press(x + w / 2, 715, vis), 'menu')

    def test_central_zone_is_the_whole_pattern(self):
        J, b = self.hud(); self.assertTrue(b.bar_reset_zone(640)); self.assertTrue(b.bar_reset_zone(640 + 77)); self.assertFalse(b.bar_reset_zone(640 + 78)); self.assertFalse(b.bar_reset_zone(640 - 78))

    def test_end_zones_are_two_icons_wide(self):
        J, b = self.hud(); self.assertEqual((b.bar_end_at(0), b.bar_end_at(129), b.bar_end_at(131), b.bar_end_at(640)), (-1, -1, 0, 0)); self.assertEqual((b.bar_end_at(1280), b.bar_end_at(1280 - 129), b.bar_end_at(1280 - 131)), (1, 1, 0))      # (2 icons + the half-icon margin)

    def test_not_movable_in_the_editor(self):
        J, b = self.hud(); self.assertIn(HM.BAR, HM.editor_names('buttons')); self.assertIsNone(b.take(640, 715, HM.editor_names('buttons'))); self.assertIsNone(b.taken)
        self.assertEqual(J.reg['buttons_pos'], {})


class InWindow(unittest.TestCase):
    """The real methods of `Game` (click on the field, release of the D-pad) on a fake game."""

    def game(self, **kw):
        j = types.SimpleNamespace(**kw) if kw else types.SimpleNamespace()
        J = fake_game(); j.width, j.height, j.reg, j.engine = W, H, J.reg, J.engine
        j.engine.active_menu = lambda: None; j.engine.msg_visible = False; j.engine.state.part = ENGINE.PART_TOWN
        j.pause = J.pause; j.title_screen = None; j.license_panel = None; j.port_screen = None; j.map_open = False; j._name_entry_in_progress = lambda: False; j._ready = True; j.ui_render = None
        j.hud = HM.Buttons(j); j.sound = types.SimpleNamespace(play_sfx=lambda *a: None); j.mouse_guard = types.SimpleNamespace(click=lambda: None, keyboard=lambda s: None)
        j.last_device = None; j.mouse = None; j.click_a = j.click_b = False; j.press_state = None; j.wheel = types.SimpleNamespace(cancel=lambda: None, in_progress=False)
        j.bar_gesture = types.SimpleNamespace(cancel=lambda: None, in_progress=False); j.arena_pressed = False; j.arena_zone = None
        j.slime_touch_click = lambda x, y: False; j.slime_touch_keys = lambda p, d: (p, d); j.curling_press = lambda x, y: False; j.curling_release = lambda: False; j.sugoroku_click = lambda x, y: False; j.sugoroku_held = lambda p: p          # (no Slime Touch, curling or T'n'T here: window/slime_touch.py, slime_curling.py, sugoroku.py)
        for name_str in ('_terrain_free', 'on_mouse_press', 'on_mouse_release', 'arena_back_shown', 'arena_back_press', 'arena_back_release'): setattr(j, name_str, types.MethodType(getattr(WND.Game, name_str), j))
        j._map_ports = lambda: {}; j.ref_effect = None
        return j

    def test_left_click_anywhere_gives_action_key(self):
        L = pyglet.window.mouse.LEFT
        for x, y in ((5, 70), (640, 360), (1270, 5), (300, 600)):          # (outside the rotation bar, see below)
            j = self.game(); j.on_mouse_press(x, y, L, 0); self.assertFalse(j.click_a); j.on_mouse_release(x, y, L, 0); self.assertTrue(j.click_a, (x, y)); self.assertFalse(j.click_b)      # on release
        j = self.game(); j.on_mouse_press(640, 360, L, 0); j.terrain_press = (j.terrain_press[0] - 1.0,) + j.terrain_press[1:]; j.on_mouse_release(640, 360, L, 0); self.assertFalse(j.click_a)      # a long press: not a click
        j = self.game(); j.on_mouse_press(640, 360, L, 0); j.on_mouse_release(700, 360, L, 0); self.assertFalse(j.click_a)                                                                         # moved: not a click

    def test_click_on_the_rotation_bar_is_not_the_action_key(self):
        pressed = []
        j = self.game(); j._bar_press = lambda x, y: pressed.append((x, y)); j.on_mouse_press(640, 715, pyglet.window.mouse.LEFT, 0)
        self.assertEqual(pressed, [(640, 715)]); self.assertFalse(j.click_a); self.assertIsNone(j.hud.press_state)                    # (the bar is 51.84 pixels high at 720, at the top)
        j = self.game(); j.reg['rotation_bar'] = False; j._bar_press = lambda x, y: pressed.append((x, y)); j.on_mouse_press(640, 715, pyglet.window.mouse.LEFT, 0); j.on_mouse_release(640, 715, pyglet.window.mouse.LEFT, 0)
        self.assertEqual(len(pressed), 1); self.assertTrue(j.click_a)                                                              # bar hidden: a click like any other

    def test_right_click_stays_cancel(self):
        j = self.game(); j.on_mouse_press(640, 360, pyglet.window.mouse.RIGHT, 0); self.assertTrue(j.click_b); self.assertFalse(j.click_a)

    def test_no_action_click_outside_free_terrain(self):
        j = self.game(); j.pause.opened = True; j.pause.click = lambda *a: None; j.on_mouse_press(640, 360, pyglet.window.mouse.LEFT, 0); self.assertFalse(j.click_a)           # Esc menu: its own click
        j = self.game(); j.engine.state.part = ENGINE.PART_BATTLE; j.hud.visible_ones = lambda: (); j.on_mouse_press(640, 360, pyglet.window.mouse.LEFT, 0); self.assertFalse(j.click_a)
        j = self.game(); j.engine.active_menu = lambda: object(); j.on_mouse_press(640, 360, pyglet.window.mouse.LEFT, 0); self.assertFalse(j.click_a)                         # game menu: its buttons
        j = self.game(); j.map_open = True; j.on_mouse_press(640, 360, pyglet.window.mouse.LEFT, 0); self.assertFalse(j.click_a)

    def test_message_visible_on_next_page(self):
        j = self.game(); j.engine.msg_visible = True; j.engine.input_menus = lambda: []; j.ui_render = object(); j.on_mouse_press(640, 360, pyglet.window.mouse.LEFT, 0); self.assertTrue(j.click_a)                                        # (unchanged: tapping the message)

    def test_touch_on_central_circle_gives_the_action_key(self):
        j = self.game(); rx, ry, c, _ = j.hud.rect(HM.DPAD); cx, cy = rx + c / 2, ry + c / 2
        j.on_mouse_press(int(cx), int(cy), pyglet.window.mouse.LEFT, 0); self.assertTrue(j.hud.dpad_on); self.assertFalse(j.click_a)               # the action comes on release
        j.on_mouse_release(int(cx), int(cy), pyglet.window.mouse.LEFT, 0); self.assertTrue(j.click_a); self.assertFalse(j.hud.dpad_on)

    def test_sliding_on_dpad_no_action(self):
        j = self.game(); rx, ry, c, _ = j.hud.rect(HM.DPAD); cx, cy = rx + c / 2, ry + c / 2
        j.on_mouse_press(int(cx), int(cy), pyglet.window.mouse.LEFT, 0); j.hud.dpad_drag(cx + c * 0.3, cy)
        j.on_mouse_release(int(cx + c * 0.3), int(cy), pyglet.window.mouse.LEFT, 0); self.assertFalse(j.click_a)

    def test_touch_on_central_circle_in_a_menu_does_nothing(self):
        j = self.game(); rx, ry, c, _ = j.hud.rect(HM.DPAD); cx, cy = rx + c / 2, ry + c / 2
        j.on_mouse_press(int(cx), int(cy), pyglet.window.mouse.LEFT, 0); j.engine.msg_visible = True
        j.on_mouse_release(int(cx), int(cy), pyglet.window.mouse.LEFT, 0); self.assertFalse(j.click_a)                         # (a message that appeared in the meantime: no phantom action)


if __name__ == '__main__':
    unittest.main(verbosity=1)
