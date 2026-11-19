"""Test of the mouse / keyboard inputs: pure logic (inputs.py) and wiring into the window (fenetre.Game), without opening a window.

    python3 tests/test_entries.py

1. The mouse after the keyboard ("switching from the keyboard to the mouse makes the mouse unusable for 1 s"): hover takes control again at the first real movement (CUMULATIVE distance since the last key, small
   noise tolerance), a click always acts, immediately. The old test (distance from one event to the next) is replayed to show that a mouse that sends movements of 1 to 2 pixels never took control again.
2. The wheel click: click = the camera returns to north (via the game), drag left / right = requested rotation (no jump at the start, vertical movement rotates nothing), a click followed by a movement
   is not a click; drag direction invertible (setting `camera_invert_lr`), keyboard arrows not. The zoom, the tilt and their gestures (wheel, Ctrl) were removed and do not come back.
3. The F1 info block: at the top right by default.
4. Wiring in Game: the camera is the GAME's. Left / right arrows = the game's camera buttons (bits 4 and 5 of the held keys), both together = return to north (only once), camera speed = more notches
   per step, the accelerator changes nothing there; the viewer rotates NEITHER the camera NOR the hero's directions alongside the game (the game takes care of it, as on mobile, including in its scenes); the wheel click only acts on the free field
   of a town, does nothing else, and the wheel no longer does anything on the field. The test with the real engine (rotation, camera-relative walking, return to north) is tests/test_engine_camera.py.
"""
import math, os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
pyglet.options['shadow_window'] = False          # no hidden window: the test runs without a display server
from dq456_pc.window import inputs as EN
from dq456_pc.menus import hud_mobile as HM

try:
    from dq456_pc.window import game as WND
except Exception as ex:          # window.py needs pyglet, numpy, unicorn... (the import alone is enough, no window is created)
    WND = None; ERROR_WND = ex


class MouseAfterKeyboard(unittest.TestCase):
    def test_without_reference_the_mouse_is_in_control(self):
        self.assertTrue(EN.mouse_active(None, (10, 10)))
        self.assertTrue(EN.mouse_active((10, 10), None))

    def test_tolerance(self):
        t = EN.MOUSE_TOLERANCE
        self.assertFalse(EN.mouse_active((100, 100), (100, 100)))                         # event without movement (sent by Windows when the drawing changes under a resting pointer)
        self.assertFalse(EN.mouse_active((100, 100), (101, 102)))                         # sensor jitter
        self.assertTrue(EN.mouse_active((100, 100), (100 + t, 100)))                      # real movement
        self.assertTrue(EN.mouse_active((100, 100), (100 - t, 100)))
        self.assertTrue(EN.mouse_active((100, 100), (100, 100 + t)))
        self.assertFalse(EN.mouse_active((100, 100), (100 + t - 0.5, 100)))

    def test_cumulative_displacement_slow_mouse_regains_control(self):
        """Slow movement: 1 pixel per event. The old test (distance from one event to the next < 3 px) never regained control; the cumulative distance regains it after a few events (without delay)."""
        def old(prev_pos, pos): return not (prev_pos is None or abs(pos[0] - prev_pos[0]) + abs(pos[1] - prev_pos[1]) < 3)
        path = [(100 + i, 100) for i in range(1, 60)]                                    # 59 events of 1 pixel
        prev = (100, 100); resumed = False
        for p in path:
            if old(prev, p): resumed = True
            prev = p
        self.assertFalse(resumed)                                                           # (the original flaw: the mouse remained unusable until the gesture was fast)
        g = EN.MouseGuard(); g.keyboard((100, 100)); n = 0
        for p in path:
            n += 1
            if g.has_moved(p): break
        self.assertTrue(g.mouse)
        self.assertLessEqual(n, math.ceil(EN.MOUSE_TOLERANCE))                            # 4 events of 1 pixel: a few milliseconds, not a second

    def test_jitter_does_not_resume(self):
        g = EN.MouseGuard(); g.keyboard((300, 200))
        for p in [(300, 200), (301, 200), (300, 201), (299, 199), (301, 201), (300, 200)] * 10: self.assertFalse(g.has_moved(p))
        self.assertFalse(g.mouse)

    def test_tremor_does_not_add_up(self):
        """The distance is measured from the point of the last key press, not summed from one event to the next: going back and forth by 2 px a thousand times does not make a movement."""
        g = EN.MouseGuard(); g.keyboard((50, 50))
        for i in range(1000): self.assertFalse(g.has_moved((52, 50) if i % 2 == 0 else (50, 50)))

    def test_click_always_acts_and_returns_control(self):
        g = EN.MouseGuard(); g.keyboard((10, 10)); self.assertFalse(g.mouse)
        g.click(); self.assertTrue(g.mouse)
        self.assertTrue(g.has_moved((10, 10)))                                                 # mouse in control: every event counts, even without movement

    def test_once_resumed_the_mouse_keeps_control(self):
        g = EN.MouseGuard(); g.keyboard((0, 0))
        self.assertTrue(g.has_moved((40, 0)))
        self.assertTrue(g.has_moved((41, 0))); self.assertTrue(g.has_moved((41, 0)))               # no more tolerance: hover follows every event
        g.keyboard((41, 0)); self.assertFalse(g.has_moved((41, 1)))                             # a new key: the keyboard takes control again

    def test_unknown_position(self):
        g = EN.MouseGuard(); g.keyboard(None); self.assertTrue(g.mouse); self.assertTrue(g.has_moved((5, 5)))


class StandaloneWheelGesture(unittest.TestCase):
    def test_simple_click_recenters(self):
        m = EN.WheelGesture(); m.press_state(500, 300)
        self.assertTrue(m.let_go())

    def test_jitter_stays_a_click(self):
        m = EN.WheelGesture(); m.press_state(500, 300)
        for p in [(502, 301), (499, 302), (501, 299), (503, 300)]: self.assertEqual(m.move_to(*p), 0.0)
        self.assertTrue(m.let_go())

    def test_slide_no_jump_at_start_and_recenters_nothing(self):
        m = EN.WheelGesture(); m.press_state(500, 300)
        self.assertEqual(m.move_to(503, 300), 0.0)                                        # below the threshold
        self.assertEqual(m.move_to(520, 300), 0.0)                                        # threshold crossed: the gesture becomes a drag, the camera does not move yet (no jump of the first 20 pixels)
        self.assertEqual(m.move_to(530, 310), 10.0)                                       # then: the horizontal distance to the previous event (the vertical does not count)
        self.assertEqual(m.move_to(530, 310), 0.0)
        self.assertFalse(m.let_go()); self.assertFalse(m.let_go())                     # after a drag the release recenters nothing

    def test_vertical_slide_does_not_turn_but_is_no_longer_a_click(self):
        m = EN.WheelGesture(); m.press_state(500, 300)
        for y in (330, 380, 450): self.assertEqual(m.move_to(500, y), 0.0)
        self.assertFalse(m.let_go())

    def test_return_to_start_stays_a_slide(self):
        m = EN.WheelGesture(); m.press_state(500, 300); m.move_to(600, 300); m.move_to(500, 300)
        self.assertFalse(m.let_go())                                                     # (the camera was rotated: it is no longer a click)

    def test_nothing_without_press(self):
        m = EN.WheelGesture(); self.assertEqual(m.move_to(10, 10), 0.0); self.assertFalse(m.let_go())
        m.press_state(1, 1); m.cancel(); self.assertFalse(m.let_go()); self.assertEqual(m.move_to(300, 300), 0.0)


class Rotation(unittest.TestCase):
    def piv(self, requested, dx, h=720.0, inv=False, maximum=180.0): return EN.rotate(requested, dx, h, inv, maximum)

    def test_direction_like_the_arrows(self):
        self.assertGreater(self.piv(0.0, 100), 0.0)                                        # right = right arrow
        self.assertLess(self.piv(0.0, -100), 0.0)

    def test_sensitivity_independent_of_resolution(self):
        self.assertAlmostEqual(self.piv(0.0, 360, h=720), self.piv(0.0, 540, h=1080))      # half the height = the same rotation
        self.assertAlmostEqual(self.piv(0.0, 360, h=720), EN.CAM_MOUSE_YAW / 2)

    def test_remaining_rotation_is_added(self):
        self.assertAlmostEqual(self.piv(10.0, 100), 10.0 + self.piv(0.0, 100))
        self.assertAlmostEqual(self.piv(10.0, -100), 10.0 + self.piv(0.0, -100))

    def test_plafond(self):
        """A large drag does not make the camera keep rotating long after the release: the requested rotation is capped (and does not wrap around: the game rotates by notches, there is no longer a heading to bring back between -180 and 180)."""
        self.assertEqual(self.piv(100.0, 5000), 180.0); self.assertEqual(self.piv(-100.0, -5000), -180.0)
        self.assertEqual(self.piv(0.0, 5000, maximum=45.0), 45.0)

    def test_zero_height(self):
        self.assertTrue(math.isfinite(self.piv(0.0, 10, h=0)))

    def test_left_right_inversion(self):
        for dx in (100, -60, 5):
            normal = self.piv(0.0, dx); inv = self.piv(0.0, dx, inv=True)
            self.assertAlmostEqual(inv, -normal); self.assertAlmostEqual(inv, self.piv(0.0, -dx))      # = dragging the other way

    def test_default_without_inversion(self):
        self.assertEqual(EN.rotate(0.0, 100, 720.0), self.piv(0.0, 100))


class InfoF1(unittest.TestCase):
    def test_top_right_by_default(self):
        for l, h in ((1280, 720), (1920, 1080), (2560, 1080), (960, 720)):
            side, wid = EN.info_zone(l, h, True, 1.12, 'center')
            self.assertEqual(side, 'right', (l, h)); self.assertGreaterEqual(wid, 260)
            self.assertEqual(EN.info_zone(l, h, False, 1.12, 'center')[0], 'right')      # without game windows: the whole screen, always on the right

    def test_width_leaves_interface_column(self):
        l, h = 1920, 1080; col = 450 * h / 800.0 * 1.12
        side, wid = EN.info_zone(l, h, True, 1.12, 'center')
        self.assertLessEqual(wid, (l - col) / 2)                                          # does not cover the centered column
        self.assertEqual(EN.info_zone(l, h, False, 1.12, 'center')[1], l - 20)

    def test_right_column_block_moves_left(self):
        self.assertEqual(EN.info_zone(1920, 1080, True, 1.12, 'right')[0], 'left')
        self.assertEqual(EN.info_zone(1920, 1080, True, 1.12, 'left')[0], 'right')


try:
    from dq456_pc.persistence import settings as RG
    from dq456_pc.menus import pause as PA
except Exception as ex:          # pause.py needs pyglet (without a display: the import alone is enough)
    PA = None


@unittest.skipIf(PA is None, 'pause.py non importable ici')
class PauseMouseAfterKeyboard(unittest.TestCase):
    """Esc menu: a key gives the selection back to the keyboard; the mouse takes control again at the first real movement (not after a jitter), a click immediately."""
    LINES = [(500.0, 400.0 - 40 * i, 780.0, 436.0 - 40 * i, i) for i in range(6)]          # six lines of 36 px, the first at the top

    def pause(self, pos=(640.0, 300.0)):
        guard = EN.MouseGuard()
        game = types.SimpleNamespace(reg=RG.Settings(None), hud=types.SimpleNamespace(taken=None, place=lambda: None), width=1280, height=720, mouse=pos, mouse_guard=guard,
                                    sound=types.SimpleNamespace(listening=False, listen=lambda b: None, tick=lambda: None), key_list={}, pause_game=lambda yes: None)
        P = PA.Pause(game); P.opened = True; P.stack = ['root']; P.zones = list(self.LINES); P.mouse_pos = pos; P.selected['root'] = 0; P.mouse_mode = False
        return P

    def test_slow_one_pixel_per_event(self):
        P = self.pause(); P.key_press(pyglet.window.key.F5); self.assertFalse(P.mouse_mode)             # a key (no effect): back to the keyboard
        for i in range(1, 12):                                                                        # the pointer moves down one pixel per event, from y = 300 (line 2, between 276 and 320: line 3 is between 236 and 276)
            P.hovered(640.0, 300.0 - i)
            if P.mouse_mode: break
        self.assertTrue(P.mouse_mode); self.assertLessEqual(i, 5)                                    # at the 4th pixel: no waiting
        P.hovered(640.0, 250.0)
        self.assertEqual(P._zone(640.0, 250.0)[0], P.selected['root'])                                   # the selection follows the pointer

    def test_jitter_changes_nothing(self):
        P = self.pause(); P.key_press(pyglet.window.key.F5); before = P.selected['root']
        for p in [(641, 300), (640, 301), (639, 299), (640, 300)] * 20: P.hovered(*p)
        self.assertFalse(P.mouse_mode); self.assertEqual(P.selected['root'], before)

    def test_click_acts_immediately(self):
        P = self.pause(); P.key_press(pyglet.window.key.F5)
        P.click(640.0, 250.0, 1)                                                                       # left click right after the key
        self.assertTrue(P.mouse_mode); self.assertEqual(P.selected['root'], P._zone(640.0, 250.0)[0])

    def test_pointer_outside_window_first_movement_counts(self):
        P = self.pause(); P.output(); P.key_press(pyglet.window.key.F5); P.hovered(641.0, 250.0)
        self.assertTrue(P.mouse_mode)

    def test_keyboard_opening_mouse_at_rest_takes_nothing(self):
        P = self.pause(); P.opened = False; P.open_menu()
        P.hovered(640.0, 300.0); P.hovered(641.0, 300.0)
        self.assertFalse(P.mouse_mode)
        P.hovered(660.0, 300.0); self.assertTrue(P.mouse_mode)


class DummyEngine:
    """The game as seen by the viewer: accepts (or refuses) this step's camera button, keeps it pending (TownPlayerManager + 0x698) and turns by ONE notch at the next step, unless `camera_turn` already did n right away."""
    def __init__(self):
        ENGINE = WND.ENGINE
        self.state = types.SimpleNamespace(part=ENGINE.PART_TOWN, effect=None, cam_free=False, cam_rot=None, cam_pos=None, cam_target=None)
        self.msg_visible = False; self.active_menu = lambda: None
        self.accepted = True; self.waiting = 0; self.notches = 0; self.calls = []; self.bits = []

    def camera_wait(self): return self.waiting

    def camera_turn(self, direction, times): self.calls.append((direction, times)); self.notches += times * (1 if direction == WND.ENGINE.ROT_CAM_RIGHT else -1); self.waiting = 0

    def step(self, bits):
        """An engine step with these camera buttons."""
        ENGINE = WND.ENGINE; self.bits.append(bits)
        if self.waiting:                                                            # rotation pending since the previous step (not consumed by camera_turn): the game turns by one notch
            self.notches += 1 if self.waiting == ENGINE.ROT_CAM_RIGHT else -1; self.waiting = 0
        if self.accepted and bits in (ENGINE.CAM_D, ENGINE.CAM_G): self.waiting = ENGINE.ROT_CAM_RIGHT if bits == ENGINE.CAM_D else ENGINE.ROT_CAM_LEFT


class Fake:
    """A minimal `Game`: the real methods of fenetre.Game (bound to this object) work on a dummy engine that accepts or refuses the camera buttons."""
    def __init__(self, part=None, **kw):
        ENGINE = WND.ENGINE
        self.engine = DummyEngine()
        if part is not None: self.engine.state.part = part
        self.pause = types.SimpleNamespace(opened=False); self.license_panel = None; self.port_screen = None; self.title_screen = None; self._name_entry_in_progress = lambda: False; self.map_open = False; self.map_name = None
        self.hud = types.SimpleNamespace(dpad_on=False, dpad_bits=lambda: 0, bar_reset_zone=lambda x: HM.Buttons.bar_reset_zone(types.SimpleNamespace(J=self), x), bar_end_at=lambda x: HM.Buttons.bar_end_at(types.SimpleNamespace(J=self), x)); self.press_state = None; self.wheel = EN.WheelGesture(); self.width = 1280; self.height = 720
        self.bar_gesture = EN.WheelGesture(); self.bar_center = False; self.bar_end = 0
        self.cam_direction = (0, False); self.cam_recenter = False; self.cam_two = False; self.cam_request = 0.0
        self.key_list = {}; self.reg = {'camera_invert_lr': False, 'accel_speed': 1.5}
        self._ready = True; self.fixed_test = True
        for k, v in kw.items(): setattr(self, k, v)
        for name_str in ('_terrain_free', '_drivable_camera', 'recenter_camera', '_wheel_press', '_wheel_drag', '_wheel_release', '_rotate_by', '_bar_press', '_bar_drag', '_bar_release', '_axis_state', '_bits_camera', '_camera_after_step', '_camera_forget', 'pad', 'on_mouse_scroll'):
            setattr(self, name_str, types.MethodType(getattr(WND.Game, name_str), self))
        self._held = lambda a: False

    def hold(self, *actions): self._held = lambda a: a in actions

    def frames(self, n):
        """n engine steps: the camera buttons the viewer sends (`Game._entries`, field), then the step tracking (`Game.tick`)."""
        for _ in range(n):
            bits = self._bits_camera(); self.engine.step(bits); self._camera_after_step(self.engine)
        return self.engine.bits[-n:]

    def click(self, x=500, y=300):
        self._wheel_press(x, y); self._wheel_release()


BOTH = lambda: WND.ENGINE.CAM_G | WND.ENGINE.CAM_D


@unittest.skipIf(WND is None, 'window.py non importable ici')
class WheelInGame(unittest.TestCase):
    def recenter(self, j): return j.cam_recenter

    def test_click_in_town_requests_return_to_north(self):
        j = Fake(); j.click()
        self.assertTrue(self.recenter(j)); self.assertEqual(j.frames(3), [BOTH(), 0, 0])        # both camera buttons together, only once: the game animates the return to north (and holds the player)

    def dragging(self, gd, ndy=-40):
        j = Fake(); j.reg['camera_invert_lr'] = gd
        j._wheel_press(500, 300); j._wheel_drag(520, 300); j._wheel_drag(620, 300 + ndy)          # 100 px to the right, ndy upward (pyglet y goes up)
        return j

    def test_slide_inversion_in_game(self):
        self.assertGreater(self.dragging(False).cam_request, 0.0)                            # without inversion: right = to the right, like the right arrow
        for dy in (-40, 0, 40):
            self.assertAlmostEqual(self.dragging(True, dy).cam_request, -self.dragging(False, dy).cam_request)
        self.assertAlmostEqual(self.dragging(False, 40).cam_request, self.dragging(False, -40).cam_request)      # the vertical movement changes nothing

    def test_inversion_leaves_keyboard_arrows_alone(self):
        """Left / right arrows held for 30 steps: same camera buttons and same number of notches whatever the inversion setting."""
        ENGINE = WND.ENGINE
        for held_name, bit, sign in (('cam_right', ENGINE.CAM_D, 1), ('cam_left', ENGINE.CAM_G, -1)):
            res = []
            for gd in (False, True):
                j = Fake(); j.reg['camera_invert_lr'] = gd; j.hold(held_name); b = j.frames(30); res.append((set(b), j.engine.notches))
            self.assertEqual(res[0], res[1], held_name); self.assertEqual(res[0][0], {bit}); self.assertEqual(res[0][1], 29 * sign)      # (the last notch is consumed at the next step)

    def test_inversion_has_no_effect_on_return_to_north(self):
        for gd in (False, True):
            j = Fake(); j.reg['camera_invert_lr'] = gd; j.click(); self.assertEqual(j.frames(1), [BOTH()])

    def test_click_followed_by_movement_is_not_a_click(self):
        j = Fake(); j._wheel_press(500, 300); j._wheel_drag(530, 300); j._wheel_drag(500, 300); j._wheel_release()      # back at the starting point: still a drag
        self.assertFalse(self.recenter(j))
        j = Fake(); j._wheel_press(500, 300); j._wheel_drag(502, 301); j._wheel_release()                                    # a mere jitter remains a click
        self.assertTrue(self.recenter(j))

    def test_slide_requests_rotation_like_arrows(self):
        ENGINE = WND.ENGINE
        j = Fake(); j._wheel_press(500, 300); j._wheel_drag(520, 300); j._wheel_drag(620, 360)
        self.assertGreater(j.cam_request, 0.0); requested = j.cam_request
        j._wheel_release(); self.assertFalse(self.recenter(j))                           # releasing a drag does not request a return to north
        b = j.frames(1); self.assertEqual(b, [ENGINE.CAM_D])                                   # the camera turns right, via the game's camera button
        j = Fake(); j._wheel_press(500, 300); j._wheel_drag(500, 340); j._wheel_drag(500, 480); self.assertEqual(j.cam_request, 0.0); self.assertEqual(j.frames(3), [0, 0, 0])      # purely vertical: nothing rotates
        j = Fake(); j.reg['camera_invert_lr'] = True; j._wheel_press(500, 300); j._wheel_drag(520, 300); j._wheel_drag(620, 300); self.assertEqual(j.frames(1), [ENGINE.CAM_G])

    def test_sliding_follows_pointer_in_notches(self):
        """The requested rotation is made by game notches (ENGINE.CAM_STEP each, at most CAM_DRAG_STEP per step), then stops: the remainder of less than half a notch is not rotated, it is added to the next drag."""
        ENGINE = WND.ENGINE
        j = Fake(); j.cam_request = 40.0; j.frames(60)
        self.assertAlmostEqual(j.engine.notches * ENGINE.CAM_STEP, 40.0, delta=ENGINE.CAM_STEP / 2 + 1e-9); self.assertLess(abs(j.cam_request), ENGINE.CAM_STEP / 2 + 1e-9)
        self.assertLessEqual(max(f for _, f in j.engine.calls), WND.CAM_DRAG_STEP)
        j = Fake(); j.cam_request = 40.0; j.frames(1); self.assertEqual(j.engine.calls, [(ENGINE.ROT_CAM_RIGHT, WND.CAM_DRAG_STEP)])         # a large drag: several notches in the same step
        j = Fake(); j.cam_request = -1.0; self.assertEqual(j.frames(3), [0, 0, 0])                                                   # less than half a notch: nothing
        j = Fake(); j.cam_request = -ENGINE.CAM_STEP; j.frames(3); self.assertEqual(j.engine.notches, -1)

    def test_arrows_prevail_over_sliding(self):
        j = Fake(); j.cam_request = -40.0; j.hold('cam_right'); self.assertEqual(j.frames(2), [WND.ENGINE.CAM_D] * 2)

    def test_game_refuses_rotation(self):
        """Player lock, scene, location that forbids turning, limit reached: the game does not take the button (nothing pending). The viewer adds no lock of its own (it sends the button, the game decides) but drops the rotation requested by the mouse."""
        j = Fake(); j.engine.accepted = False; j.cam_request = 40.0; j.frames(3)
        self.assertEqual(j.cam_request, 0.0); self.assertEqual(j.engine.notches, 0); self.assertEqual(j.engine.calls, [])
        j = Fake(); j.engine.accepted = False; j.hold('cam_right'); self.assertEqual(j.frames(3), [WND.ENGINE.CAM_D] * 3); self.assertEqual(j.engine.notches, 0)          # (the arrows are not dropped: the game can pick it up again at the end of the scene)
        j = Fake(); j.engine.accepted = False; j.click(); self.assertEqual(j.frames(2), [BOTH(), 0])

    def test_terrain_changes_between_press_and_release(self):
        """A message that opens while the middle button is pressed: the release requests nothing, and the drag rotates nothing."""
        j = Fake(); j._wheel_press(500, 300); j.engine.msg_visible = True
        j._wheel_drag(520, 300); j._wheel_drag(560, 300); self.assertEqual(j.cam_request, 0.0)
        j._wheel_release(); self.assertFalse(self.recenter(j))
        j = Fake(); j._wheel_press(500, 300); j.engine.msg_visible = True; j._wheel_release(); self.assertFalse(self.recenter(j))                  # a simple click, but the field is no longer free

    def test_a_pending_request_is_not_sent_after_a_menu(self):
        """Rotation requested or return to north requested, then a message opens before the step: they are forgotten (`Game._entries`: off the field), they are not sent when the message closes."""
        j = Fake(); j.cam_request = 40.0; j.recenter_camera(); j.engine.msg_visible = True; j._camera_forget(); j.engine.msg_visible = False
        self.assertEqual(j.frames(3), [0, 0, 0])

    def test_return_to_north_clears_rotation_requested_by_mouse(self):
        """Wheel click (return to north) while a mouse rotation was still to be done: the game brings the camera back to north, the remaining rotation is not done afterward."""
        j = Fake(); j.cam_request = 40.0; j.recenter_camera()
        self.assertEqual(j.frames(4), [BOTH(), 0, 0, 0]); self.assertEqual(j.cam_request, 0.0); self.assertEqual(j.engine.calls, [])

    def test_slide_cancels_return_to_north_not_yet_sent(self):
        j = Fake(); j.recenter_camera(); j._wheel_press(500, 300); j._wheel_drag(520, 300); j._wheel_drag(620, 300)
        self.assertFalse(self.recenter(j)); self.assertEqual(j.frames(1), [WND.ENGINE.CAM_D])

    def test_press_in_menu_then_free_field_on_release(self):
        """The middle button pressed during a message, the message closes, then it is released: this is not a click on the field (the gesture never started)."""
        j = Fake(); j.engine.msg_visible = True; j._wheel_press(500, 300); j.engine.msg_visible = False
        j._wheel_release(); self.assertFalse(self.recenter(j))
        j._wheel_drag(560, 300); self.assertEqual(j.cam_request, 0.0)

    def test_outside_terrain_nothing_happens(self):
        ENGINE = WND.ENGINE
        def fake(name_str):
            j = Fake()
            if name_str == 'pause': j.pause.opened = True
            elif name_str == 'message': j.engine.msg_visible = True
            elif name_str == 'menu': j.engine.active_menu = lambda: 12
            elif name_str == 'battle': j.engine.state.part = ENGINE.PART_BATTLE
            elif name_str == 'title': j.title_screen = object()
            elif name_str == 'license': j.license_panel = object()
            elif name_str == 'saves': j.port_screen = object()
            elif name_str == 'name': j._name_entry_in_progress = lambda: True
            elif name_str == 'map': j.map_open = True
            elif name_str == 'effect': j.engine.state.effect = object()
            elif name_str == 'dpad': j.hud.dpad_on = True
            elif name_str == 'button': j.press_state = (12, 0, 16)
            elif name_str == 'title-map': j.map_name = WND.TITLE_MAP
            return j
        for name_str in ('pause', 'message', 'menu', 'battle', 'title', 'license', 'saves', 'name', 'map', 'effect', 'dpad', 'button', 'title-map'):
            j = fake(name_str); j.click(); j._wheel_press(0, 0); j._wheel_drag(50, 50); j._wheel_drag(120, 90); j._wheel_release()
            self.assertEqual(j.cam_request, 0.0, name_str); self.assertFalse(self.recenter(j), name_str)
            if name_str in ('dpad', 'button'): continue                                                           # (the D-pad and the on-screen buttons are held with the mouse: they only block the wheel click, not the keyboard arrows)
            j = fake(name_str); j.hold('cam_right', 'cam_left'); self.assertEqual(j.frames(30), [0] * 30, name_str); self.assertFalse(self.recenter(j), name_str)
            j = fake(name_str); j.hold('cam_right'); self.assertEqual(j.frames(5), [0] * 5, name_str)

    def test_world_map_no_rotation(self):
        j = Fake(part=WND.ENGINE.PART_FIELD); j.click(); self.assertFalse(self.recenter(j))          # no rotation on the world map (like the arrows)
        j.hold('cam_right'); self.assertEqual(j.frames(30), [0] * 30)

    def test_wheel_no_longer_does_anything_on_terrain(self):
        for part in (None, WND.ENGINE.PART_FIELD):
            j = Fake(part=part); j.hold('modifier'); j.on_mouse_scroll(0, 0, 0, 1); j.on_mouse_scroll(0, 0, 0, -3)
            self.assertEqual(j.cam_request, 0.0); self.assertFalse(self.recenter(j)); self.assertEqual(j.frames(2), [0, 0])
            self.assertFalse(hasattr(j, 'zoom'))


@unittest.skipIf(WND is None, 'window.py non importable ici')
class BarInGame(unittest.TestCase):
    """Rotation bar: left button on the bottom bar; drag = rotation (like the middle button), tap on the central zone = back to north."""
    CX, Y = 640, 5                                              # center of the 1280 x 720 window; the bar is 21.6 pixels high

    def test_drag_rotates_like_the_wheel(self):
        j = Fake(); j._bar_press(500, self.Y); j._bar_drag(520, self.Y); j._bar_drag(620, self.Y + 100)          # 100 px to the right (the vertical does not matter), after the threshold of 8 units
        w = Fake(); w._wheel_press(500, 300); w._wheel_drag(520, 300); w._wheel_drag(620, 300)
        self.assertGreater(j.cam_request, 0.0); self.assertAlmostEqual(j.cam_request, w.cam_request)
        j = Fake(); j.reg['camera_invert_lr'] = True; j._bar_press(500, self.Y); j._bar_drag(520, self.Y); j._bar_drag(620, self.Y); self.assertAlmostEqual(j.cam_request, -w.cam_request)

    def test_threshold_is_8_units(self):
        j = Fake(); j._bar_press(500, self.Y); j._bar_drag(507, self.Y); j._bar_drag(514, self.Y)          # 7,2 pixels = 8 unites a 720 : en dessous, un toucher ; au-dela, un glissement
        self.assertEqual(j.cam_request, 0.0)
        j._bar_drag(540, self.Y); j._bar_drag(560, self.Y); self.assertGreater(j.cam_request, 0.0)

    def test_touch_of_the_central_zone_returns_to_north(self):
        j = Fake(); j._bar_press(self.CX + 5, self.Y); j._bar_release(); self.assertTrue(j.cam_recenter)
        j = Fake(); j._bar_press(self.CX + 77, self.Y); j._bar_release(); self.assertTrue(j.cam_recenter)          # the whole central pattern (3 icons of 51.84 px: half-width 77.76 px)
        j = Fake(); j._bar_press(self.CX + 79, self.Y); j._bar_release(); self.assertFalse(j.cam_recenter)          # outside the pattern: a tap does nothing
        j = Fake(); j._bar_press(300, self.Y); j._bar_release(); self.assertFalse(j.cam_recenter)

    def test_end_held_turns_the_camera_like_an_arrow(self):
        """pressing the left / right end of the bar (2 icons + the half-icon margin = 129.6 px) turns the camera that way for as long as the button is held, with no drag; a release stops it and recenters nothing."""
        ENGINE = WND.ENGINE
        for x, bit, direction in ((50, ENGINE.CAM_G, -1), (1280 - 50, ENGINE.CAM_D, 1)):
            j = Fake(); j._bar_press(x, self.Y); self.assertEqual(j.bar_end, direction)
            self.assertEqual(j.frames(3), [bit, bit, bit]); j._bar_drag(x + 60, self.Y); j._bar_drag(x + 200, self.Y); self.assertEqual(j.cam_request, 0.0)          # (no drag rotation on top)
            j._bar_release(); self.assertFalse(j.cam_recenter); self.assertEqual(j.frames(2), [0, 0])
        j = Fake(); j._bar_press(129, self.Y); self.assertEqual(j.bar_end, -1)
        j = Fake(); j._bar_press(131, self.Y); self.assertEqual(j.bar_end, 0); j._bar_release(); self.assertEqual(j.frames(1), [0])

    def test_slide_from_the_central_zone_is_not_a_touch(self):
        j = Fake(); j._bar_press(self.CX, self.Y); j._bar_drag(self.CX + 30, self.Y); j._bar_drag(self.CX + 100, self.Y); j._bar_release()
        self.assertFalse(j.cam_recenter); self.assertGreater(j.cam_request, 0.0)

    def test_nothing_outside_the_free_terrain(self):
        for name_str in ('pause', 'message', 'battle', 'map', 'effet'):
            j = Fake()
            if name_str == 'pause': j.pause.opened = True
            elif name_str == 'message': j.engine.msg_visible = True
            elif name_str == 'battle': j.engine.state.part = WND.ENGINE.PART_BATTLE
            elif name_str == 'map': j.map_open = True
            else: j.engine.state.effect = object()
            j._bar_press(self.CX, self.Y); j._bar_drag(self.CX + 30, self.Y); j._bar_drag(self.CX + 100, self.Y); j._bar_release()
            self.assertEqual(j.cam_request, 0.0, name_str); self.assertFalse(j.cam_recenter, name_str); self.assertFalse(j.bar_gesture.in_progress, name_str)

    def test_world_map_no_rotation(self):
        j = Fake(part=WND.ENGINE.PART_FIELD); j._bar_press(self.CX, self.Y); j._bar_release(); self.assertFalse(j.cam_recenter)


@unittest.skipIf(WND is None, 'window.py non importable ici')
class ArrowsInGame(unittest.TestCase):
    def test_arrows_rotate_game_camera(self):
        ENGINE = WND.ENGINE
        j = Fake(); j.hold('cam_right'); self.assertEqual(j.frames(30), [ENGINE.CAM_D] * 30); self.assertEqual(j.engine.notches, 29); self.assertEqual(j.engine.calls, [])          # one notch per step, by the game: 84.4 degrees per second
        j = Fake(); j.hold('cam_left'); self.assertEqual(j.frames(30), [ENGINE.CAM_G] * 30); self.assertEqual(j.engine.notches, -29)

    def test_camera_buttons_are_bits_4_and_5_of_held_keys(self):
        """On a town's field, (Global + 0xe0) >> 4 & 3: 1 = left, 2 = right, 3 = return to north (NormalControl::checkCamera). These are the values of A and B in menus: the viewer removes A and B from the field (the engine wants BTN_TALK there)."""
        ENGINE = WND.ENGINE
        self.assertEqual((ENGINE.CAM_G, ENGINE.CAM_D), (0x10, 0x20)); self.assertEqual((ENGINE.CAM_G, ENGINE.CAM_D), (ENGINE.A, ENGINE.B))
        self.assertAlmostEqual(ENGINE.CAM_STEP, 2.8125)

    def test_camera_one_notch_per_step(self):
        """With the arrow keys: one notch per step, like the game (the first notch is the button's, no notch is added: no more camera speed setting)."""
        j = Fake(); j.hold('cam_right'); j.frames(10); self.assertEqual(j.engine.notches, 9); self.assertEqual(j.engine.calls, [])
        j = Fake(); j.hold('cam_left'); j.frames(10); self.assertEqual(j.engine.notches, -9); self.assertEqual(j.engine.calls, [])
        self.assertNotIn('vitesse_camera', j.reg)

    def test_no_extra_notch_during_return_to_north(self):
        """The game holds the camera (return to north in progress: the pending type is the north one, not that of the button sent): the viewer adds no notch to it, neither for the arrows nor for the drag."""
        ENGINE = WND.ENGINE
        j = Fake(); j.cam_direction = (-1, False); j.engine.waiting = ENGINE.ROT_CAM_NORTH
        j._camera_after_step(j.engine); self.assertEqual(j.engine.calls, [])
        j.cam_request = -40.0; j.cam_direction = (-1, True); j._camera_after_step(j.engine); self.assertEqual(j.engine.calls, []); self.assertEqual(j.cam_request, 0.0)

    def test_no_sliding_while_arrow_is_held(self):
        j = Fake(); j.hold('cam_left', 'cam_right'); self.assertEqual(j.frames(1), [BOTH()])
        j.cam_request = 40.0; self.assertEqual(j.frames(3), [0, 0, 0])
        j.hold('cam_right'); self.assertEqual(j.frames(2), [0, 0])                  # (the arrow remaining after the double press)
        j.hold(); self.assertEqual(j.frames(1), [WND.ENGINE.CAM_D])                       # everything released: the rotation requested by the mouse resumes

    def test_accelerator_does_not_accelerate_camera(self):
        j = Fake(); j.hold('cam_right'); j.frames(30); ref = j.engine.notches
        j = Fake(); j.hold('cam_right', 'accel'); j.frames(30); self.assertEqual(j.engine.notches, ref)
        j = Fake(); j.reg['accel_speed'] = 2.0; j.hold('cam_left', 'accel'); j.frames(30); self.assertEqual(j.engine.notches, -ref)

    def test_no_up_down_arrow_actions(self):
        """the up / down arrows are no longer actions (menus are walked with the movement keys; only the camera keys remain on the arrows)."""
        from dq456_pc.persistence import settings as S
        self.assertNotIn('cam_up', S.DEFAULT_KEYS); self.assertNotIn('cam_down', S.DEFAULT_KEYS); self.assertEqual({a for a, _ in S.ACTIONS} & {'cam_up', 'cam_down'}, set())
        K = pyglet.window.key; r = S.Settings(None)
        for k in (K.UP, K.DOWN): self.assertIsNone(r.action_of(k))
        self.assertEqual((r.action_of(K.LEFT), r.action_of(K.RIGHT)), ('cam_left', 'cam_right'))

    def test_two_arrows_return_camera_to_north_once(self):
        ENGINE = WND.ENGINE
        j = Fake(); j.hold('cam_left', 'cam_right'); self.assertEqual(j.frames(10), [BOTH()] + [0] * 9)          # the game's two camera buttons at the first step only: the game does the rest (animation, player held)
        self.assertEqual(j.engine.notches, 0)

    def test_arrow_still_pressed_after_double_press_does_nothing(self):
        ENGINE = WND.ENGINE
        j = Fake(); j.hold('cam_left', 'cam_right'); j.frames(1); j.hold('cam_right'); self.assertEqual(j.frames(10), [0] * 10)        # the remaining arrow (release is never simultaneous) does not rotate
        j.hold('cam_left', 'cam_right'); self.assertEqual(j.frames(2), [0, 0])                                                         # (the other pressed again while the first stayed held: no new return to north)
        j.hold(); j.frames(1); j.hold('cam_right'); self.assertEqual(j.frames(3), [ENGINE.CAM_D] * 3)                                      # everything released, then a single arrow: the camera rotates again
        j.hold('cam_left', 'cam_right'); self.assertEqual(j.frames(2), [BOTH(), 0])                                                    # one arrow held, the other is added: double press, return to north

    def test_two_arrows_already_held_when_returning_to_field(self):
        """Both arrows held during a message, then the message closes: no return to north (this is not a double press on the field)."""
        j = Fake(); j.engine.msg_visible = True; j.hold('cam_left', 'cam_right'); j._camera_forget(); j.engine.msg_visible = False
        self.assertEqual(j.frames(5), [0] * 5)

    def test_viewer_no_longer_rotates_walk_directions(self):
        """The walking directions are those of the screen, rotated by the game according to its camera (as on mobile): no more rotation done by the viewer."""
        ENGINE = WND.ENGINE
        for held_name, wanted in ((('up',), ENGINE.UP), (('down',), ENGINE.DOWN), (('left',), ENGINE.LEFT), (('right',), ENGINE.RIGHT), (('up', 'right'), ENGINE.UP | ENGINE.RIGHT)):
            j = Fake(); j.hold(*held_name); self.assertEqual(j.pad(), wanted, held_name)
        j = Fake(); j.hold('A'); self.assertEqual(j.pad(), ENGINE.A)
        for name_str in ('_lacet_eff', '_tourner_dir', '_maj_camera', '_camera_menee', '_coupure_camera'): self.assertFalse(hasattr(WND.Game, name_str), name_str)
        for name_str in ('yaw', 'cam_w', 'cam_jeu', 'cam_bloquee', 'cam_limite', 'cam_saut', 'cam_axe'): self.assertFalse(hasattr(Fake(), name_str), name_str)

    def test_in_menus_arrows_are_directions(self):
        ENGINE = WND.ENGINE
        j = Fake(); j.engine.msg_visible = True
        for action, bit in (('cam_left', ENGINE.LEFT), ('cam_right', ENGINE.RIGHT)):
            j.hold(action); self.assertEqual(j.pad(), bit, action)

    def test_inputs_sends_camera_buttons_on_terrain_only(self):
        """Wiring (the code is re-read, the window is not opened): `_entries` adds the camera buttons after removing A and B, in the field branch; elsewhere it forgets the requests; `tick` follows the step with _camera_after_step."""
        import inspect
        src = inspect.getsource(WND.Game._entries)
        self.assertIn('p &= ~(ENGINE.A | ENGINE.B)\n            terrain = True; p |= self._bits_camera()', src)
        self.assertIn('if not terrain: self._camera_forget()', src)
        tick = inspect.getsource(WND.Game.tick)
        self.assertLess(tick.index('eng.step(p, decl)'), tick.index('self._camera_after_step(eng)'))


if __name__ == '__main__':
    unittest.main(verbosity=1)
