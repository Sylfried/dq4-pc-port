"""Test of the casino and the bestiary (engine parts 0xf and 0x10), without a window or an engine (fake objects):

1. engine constants: PART_CASINO, PART_BESTIARY, MINIGAME_PARTS;
2. free camera of the casino (`camera_free`): position + rotation from packet 10, without packet 11; not elsewhere;
3. walking speed: never accelerated in the casino and the bestiary (the held arrows are used for menus there);
4. Esc: back button of the open window (gamepad 0x20) in the casino and the bestiary, otherwise Esc menu;
5. numeric keyboard entry menus (slot machine bet, poker, tokens, arena): columns, ▲ / ▼, confirm, back;
6. window code with a bit mask (poker: touch areas of the cards and "Donner", value 63 outside the exported array);
7. arena battle: back button instead of the "Quit" window.

  python3 tests/test_casino_bestiary.py        (Linux without a display: pyglet in "headless" mode)
"""
import functools, os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.core import engine as ENGINE
from dq4_pc.window import game as F
from dq4_pc.menus import ui_menu as UI


class Constants(unittest.TestCase):
    def test_parts(self):
        self.assertEqual((ENGINE.PART_CASINO, ENGINE.PART_BESTIARY), (0xf, 0x10))
        self.assertEqual(set(ENGINE.MINIGAME_PARTS), {ENGINE.PART_CASINO, ENGINE.PART_BESTIARY})
        self.assertFalse({ENGINE.PART_INITIAL, ENGINE.PART_TOWN, ENGINE.PART_BATTLE, ENGINE.PART_FIELD} & set(ENGINE.MINIGAME_PARTS))


class FreeCamera(unittest.TestCase):
    def e(self, part, free=False, rot=None): return types.SimpleNamespace(part=part, cam_free=free, cam_rot=rot)

    def test_casino(self):
        self.assertTrue(F.camera_free(self.e(ENGINE.PART_CASINO, rot=(10.0, 0.0, 0.0))), 'casino: position + rotation, without packet 11')
        self.assertFalse(F.camera_free(self.e(ENGINE.PART_CASINO, rot=None)), 'no rotation: target camera')

    def test_other_parts(self):
        self.assertTrue(F.camera_free(self.e(ENGINE.PART_TOWN, free=True, rot=(0.0, 0.0, 0.0))), 'scene (paquet 11, bit 7)')
        self.assertFalse(F.camera_free(self.e(ENGINE.PART_TOWN, rot=(10.0, 0.0, 0.0))), 'town: the rotation alone does not make the camera free')
        self.assertFalse(F.camera_free(self.e(ENGINE.PART_BESTIARY, rot=(10.0, 0.0, 0.0))), 'bestiary: town camera kept in memory')

    def test_fake_state_without_game(self):
        """The camera tests pass a fake state without `part`: town camera, no error."""
        self.assertFalse(F.camera_free(types.SimpleNamespace(cam_free=False, cam_rot=None)))


def fake_walk(part, msg=False):
    eng = types.SimpleNamespace(state=types.SimpleNamespace(part=part, effect=None, load_wait=None, transition_guard=0, battle_transition=lambda: False), msg_visible=msg, active_menu=lambda: None, flags=lambda: 0x28)
    return types.SimpleNamespace(reg={'accel_speed': 3.0}, engine=eng, pad=lambda: ENGINE.RIGHT, _held=lambda a: a == 'accel', hud=types.SimpleNamespace(dpad_run=lambda: False), pause=types.SimpleNamespace(opened=False), _battle_clock=lambda: False)


class WalkSpeed(unittest.TestCase):
    def test_terrain(self):
        self.assertEqual(F.Game._speed_factor(fake_walk(ENGINE.PART_TOWN)), 3.0, 'ville : accelerateur tenu')

    def test_casino_bestiary(self):
        for part in ENGINE.MINIGAME_PARTS: self.assertEqual(F.Game._speed_factor(fake_walk(part)), 1.0, hex(part))


class FakeWindow:
    """Game menu window (ui_menu.Window) reduced to what the tested functions read: typ, buttons() = (number, gamepad, x0, z0, x1, z1, depth)."""
    def __init__(self, typ, buttons): self.typ = typ; self._b = buttons
    def buttons(self): return list(self._b)


def b(num, pad, x, z=0.0): return (num, pad, x - 10.0, z - 10.0, x + 10.0, z + 10.0, 0)


def fake_game_menu(buttons, typ=47, part=ENGINE.PART_CASINO, port=12):
    sends = []
    wnd = FakeWindow(typ, buttons)
    eng = types.SimpleNamespace(state=types.SimpleNamespace(part=part), msg_visible=False, active_menu=lambda: port, send_menu=lambda *a: sends.append(a), ui=types.SimpleNamespace(f={port: {'order': 1, 'grid': None, 'visible': True}}))
    j = types.SimpleNamespace(engine=eng, ui_g=types.SimpleNamespace(f={port: wnd}), cursor_step={}, hover_node=1, menu_to_release=None, sound=types.SimpleNamespace(play_sfx=lambda *a: None), sends=sends,
                              name_entry=types.SimpleNamespace(active=False), license_panel=None)
    for name_str in ('_step_columns', '_active_step', '_step_entry', '_can_go_back', '_esc_back'): setattr(j, name_str, functools.partial(getattr(F.Game, name_str), j))
    j._port_for_gamepad = lambda p, pad: p
    return j, wnd


# slot machine (type 47): one ▲ (gamepad 0x2) / ▼ (0x1) column with number 1, "Lancer" (0x10) with number 0; back 0x20 with number -1
SLOT = [b(1, 0x2, 100, -50), b(1, 0x1, 100, 50), b(0, 0x10, 0, 100), b(-1, 0x20, 200, 150)]
# tokens (type 44): five columns (1, 10, 100, 1000, 10000) from left to right: 10000, 1000, 100, 10, 1 (increasing positions), confirm number 0, back -1
CHIPS = [b(n, 0x2, x, -50) for n, x in ((10000, -200), (1000, -100), (100, 0), (10, 100), (1, 200))] + [b(n, 0x1, x, 50) for n, x in ((10000, -200), (1000, -100), (100, 0), (10, 100), (1, 200))] + [b(0, 0x10, 0, 150), b(-1, 0x20, 250, 200)]


class NumericEntry(unittest.TestCase):
    def test_columns(self):
        j, wnd = fake_game_menu(SLOT); self.assertEqual(j._step_columns(wnd), [1])
        j, wnd = fake_game_menu(CHIPS, 44); self.assertEqual(j._step_columns(wnd), [10000, 1000, 100, 10, 1], 'de gauche a droite')

    def test_ordinary_window(self):
        """A list (gifts, bestiary) has no ▲ / ▼ column: ordinary cursor. The page arrows (number -1) do not count."""
        j, wnd = fake_game_menu([b(0, 0x10, 0, 0), b(1, 0x10, 0, 50), b(-1, 0x2, 50, 0), b(-1, 0x1, 50, 100)], 45)
        self.assertEqual(j._step_columns(wnd), [])
        self.assertFalse(j._step_entry(12, j.engine.ui.f[12], wnd, {0: 1}, ENGINE.UP))
        self.assertEqual(j.sends, [])

    def test_up_down(self):
        j, wnd = fake_game_menu(SLOT); f = j.engine.ui.f[12]
        self.assertTrue(j._step_entry(12, f, wnd, {0: 1}, ENGINE.UP)); self.assertEqual(j.sends[-1], (12, 1, 1, 0x2), '▲ of column 1 (gamepad 0x2)')
        self.assertEqual(j.menu_to_release, 12, 'the release follows at the next frame')
        self.assertTrue(j._step_entry(12, f, wnd, {0: 1}, ENGINE.DOWN)); self.assertEqual(j.sends[-1], (12, 1, 1, 0x1), '▼ (manette 0x1)')
        self.assertIsNone(j.hover_node, 'a key: the cursor takes over again')

    def test_left_right_columns(self):
        j, wnd = fake_game_menu(CHIPS, 44); f = j.engine.ui.f[12]; z = {0: 1}
        self.assertEqual(j._active_step(12), 1, 'at first: the units (right column)')
        j._step_entry(12, f, wnd, z, ENGINE.LEFT); self.assertEqual(j._active_step(12), 10)
        j._step_entry(12, f, wnd, z, ENGINE.LEFT); j._step_entry(12, f, wnd, z, ENGINE.LEFT); j._step_entry(12, f, wnd, z, ENGINE.LEFT); j._step_entry(12, f, wnd, z, ENGINE.LEFT); j._step_entry(12, f, wnd, z, ENGINE.LEFT)
        self.assertEqual(j._active_step(12), 10000, 'bornee a gauche')
        j._step_entry(12, f, wnd, z, ENGINE.UP); self.assertEqual(j.sends[-1], (12, 1, 10000, 0x2))
        for _ in range(8): j._step_entry(12, f, wnd, z, ENGINE.RIGHT)
        self.assertEqual(j._active_step(12), 1, 'bornee a droite')
        self.assertEqual(j.sends, [(12, 1, 10000, 0x2)], 'gauche / droite ne transmettent rien au moteur')

    def test_validate_and_back(self):
        j, wnd = fake_game_menu(SLOT); f = j.engine.ui.f[12]
        self.assertTrue(j._step_entry(12, f, wnd, {0: 1}, ENGINE.A)); self.assertEqual(j.sends[-1], (12, 1, 0, 0x10), 'A = bouton de validation (Lancer)')
        self.assertTrue(j._step_entry(12, f, wnd, {0: 1}, ENGINE.B)); self.assertEqual(j.sends[-1], (12, 1, -1, 0x20), 'B = retour (manette 0x20)')

    def test_no_useful_key(self):
        j, wnd = fake_game_menu(SLOT); self.assertFalse(j._step_entry(12, j.engine.ui.f[12], wnd, {0: 1}, 0)); self.assertEqual(j.sends, [])

    def test_several_validations_ordinary_cursor(self):
        """A window with several confirm buttons (a choice to make) keeps the ordinary cursor."""
        j, wnd = fake_game_menu(SLOT + [b(2, 0x10, 0, 200)]); self.assertIsNone(j._active_step(12))


class EscBack(unittest.TestCase):
    def test_casino_with_back_button(self):
        j, wnd = fake_game_menu(SLOT); self.assertTrue(j._esc_back(), 'machine a sous : Echap = retour')

    def test_bestiary_with_back_button(self):
        j, wnd = fake_game_menu([b(0, 0x10, 0, 0), b(-1, 0x20, 200, 0)], 28, ENGINE.PART_BESTIARY); self.assertTrue(j._esc_back())

    def test_without_back_button_esc_opens_the_menu(self):
        """Reels spinning, cards being dealt: the window no longer has an active back button."""
        j, wnd = fake_game_menu([b(0, 0x10, 0, 0)]); self.assertFalse(j._esc_back())

    def test_message_visible(self):
        j, wnd = fake_game_menu(SLOT); j.engine.msg_visible = True; self.assertFalse(j._esc_back(), 'a message: the Esc menu')

    def test_no_menu(self):
        j, wnd = fake_game_menu(SLOT); j.engine.active_menu = lambda: None; self.assertFalse(j._esc_back())


class ArenaBackButton(unittest.TestCase):
    """Arena battle: the "Quit" window (type 71) has no input in the viewer (Engine.ignored_types) and is not drawn; a back button at the top right, the B key and the right click send the back key (0x400) to
    the engine at every step until it has switched the window off. The button is shown exactly as long as the window is open over a battle that is not ending."""
    def game(self, part=ENGINE.PART_BATTLE, visible=True, fade=0.0, replay=None, pause=False):
        eng = types.SimpleNamespace(state=types.SimpleNamespace(part=part, fade={'a': fade}, background_fade={'a': 0.0}), ui=types.SimpleNamespace(f={12: {'type': 71, 'visible': visible, 'order': 1, 'cells': {0: 'x'}}}),
                                    msg_visible=False, ignored_types=(71,))
        j = types.SimpleNamespace(engine=eng, pause=types.SimpleNamespace(opened=pause), width=1280, height=720, mouse=None, _replay=replay, arena_pending=False, arena_pressed=False, arena_zone=(1100, 600, 1200, 700))
        for name_str in ('arena_back_shown', 'arena_abort_decl', 'arena_back_press', 'arena_back_release'): setattr(j, name_str, functools.partial(getattr(F.Game, name_str), j))
        return j

    def test_shown_with_the_window(self):
        self.assertTrue(self.game().arena_back_shown())

    def test_not_shown(self):
        self.assertFalse(self.game(visible=False).arena_back_shown(), 'window turned off by the engine ("Wait!" in progress)')
        self.assertFalse(self.game(part=ENGINE.PART_CASINO).arena_back_shown(), 'hors combat')
        self.assertFalse(self.game(fade=0.8).arena_back_shown(), 'end of the battle: fade to black')
        self.assertFalse(self.game(replay=object()).arena_back_shown(), 'rediffusion : son propre bouton')
        self.assertFalse(self.game(pause=True).arena_back_shown(), 'menu Echap ouvert')

    def test_click_on_the_button(self):
        L = pyglet.window.mouse.LEFT; j = self.game()
        self.assertTrue(j.arena_back_press(1150, 650, L)); self.assertTrue(j.arena_pressed); self.assertFalse(j.arena_pending, 'the request goes on release')
        self.assertTrue(j.arena_back_release(1150, 650, L)); self.assertTrue(j.arena_pending); self.assertFalse(j.arena_pressed)

    def test_click_elsewhere_or_other_button(self):
        L, R = pyglet.window.mouse.LEFT, pyglet.window.mouse.RIGHT; j = self.game()
        self.assertFalse(j.arena_back_press(100, 100, L), 'outside the button: the click stays with the game'); self.assertFalse(j.arena_back_press(1150, 650, R), 'the right click goes through the B key')
        self.assertFalse(j.arena_back_release(100, 100, L), 'no click started on the button'); self.assertFalse(j.arena_pending)
        self.assertTrue(j.arena_back_press(1150, 650, L)); self.assertTrue(j.arena_back_release(100, 100, L), 'released elsewhere: the button keeps this release'); self.assertFalse(j.arena_pending, 'released outside the button: nothing')

    def test_no_click_when_not_shown(self):
        j = self.game(visible=False); self.assertFalse(j.arena_back_press(1150, 650, pyglet.window.mouse.LEFT)); self.assertFalse(j.arena_pressed)

    def test_back_key_until_the_window_is_off(self):
        """The request is repeated at every step while the window is open (the engine only reads it when its round task runs), then it ends by itself."""
        j = self.game(); self.assertEqual(j.arena_abort_decl(0x10), 0x10, 'no request: nothing')
        j.arena_pending = True
        for _ in range(3): self.assertEqual(j.arena_abort_decl(0x10), 0x10 | 0x400)
        j.engine.ui.f[12]['visible'] = False
        self.assertEqual(j.arena_abort_decl(0x10), 0x10); self.assertFalse(j.arena_pending, 'window turned off: the request is taken into account')
        j.engine.ui.f[12]['visible'] = True; self.assertEqual(j.arena_abort_decl(0), 0, 'if the window turns on again ("No"), nothing is sent')

    def test_request_dropped_with_the_battle(self):
        j = self.game(); j.arena_pending = True; j.engine.state.part = ENGINE.PART_TOWN
        self.assertEqual(j.arena_abort_decl(0), 0); self.assertFalse(j.arena_pending)

    def test_window_has_no_input(self):
        """Engine.active_menu / input_menus skip the ignored types: "Quit" no longer owns the keys, and the battle does not wait for the player."""
        ui = types.SimpleNamespace(f={12: {'type': 71, 'visible': True, 'order': 1, 'cells': {0: 'x'}, 'input': True}, 13: {'type': 1, 'visible': True, 'order': 2, 'cells': {0: 'x'}, 'input': True}})
        e = types.SimpleNamespace(ui=ui, ignored_types=(71,)); self.assertEqual(ENGINE.Engine.input_menus(e), [13], 'the Yes / No stays active')
        ui.f[13]['visible'] = False; self.assertEqual(ENGINE.Engine.input_menus(e), []); e.ignored_types = (); self.assertEqual(ENGINE.Engine.input_menus(e), [12], 'no filter (engine only): as before')

    def test_wiring(self):
        """Code read as text: the mixin is a base of Game, the engine ignores the type, the window is neither drawn nor listed in the interface editor, the click and B key go through the button."""
        import inspect
        self.assertTrue(issubclass(F.Game, F.ArenaAbortMixin)); self.assertEqual(F.ARENA_ABORT, 71)
        from dq4_pc.persistence import settings as RG
        self.assertIn('FightStadiumAbort', RG.REMOVED_WINDOWS)
        self.assertIn('ignored_types = (ARENA_ABORT,)', inspect.getsource(F.Game._start_engine))
        self.assertIn('arena_back_press', inspect.getsource(F.Game.on_mouse_press)); self.assertIn('arena_back_release', inspect.getsource(F.Game.on_mouse_release))
        src = inspect.getsource(F.Game._entries); self.assertIn('self.arena_abort_decl(decl)', src); self.assertIn('pressed & ENGINE.B', src)
        self.assertIn("f['type'] not in eng.ignored_types", inspect.getsource(F.Game._draw_menus)); self.assertIn('draw_arena_back', inspect.getsource(F.Game._draw))
        self.assertFalse(hasattr(F.Game, '_quit_only')); self.assertFalse(hasattr(F, 'without_validation'))


class ArenaWaiting(unittest.TestCase):
    """The battle waits for the player on a menu that has the input or a message that shows its cursor; "Quit" (no input) is no wait."""
    def game(self, active):
        eng = types.SimpleNamespace(active_menu=lambda: active, msg_visible=False, ui=types.SimpleNamespace(msg={}), state=types.SimpleNamespace(part=ENGINE.PART_BATTLE))
        j = types.SimpleNamespace(engine=eng, _replay=None); j._wait_for_player = functools.partial(F.Game._wait_for_player, j); return j

    def test_waiting_for_player(self):
        self.assertFalse(self.game(None)._wait_for_player(), 'arena: no window with the input, the battle waits for nobody')
        self.assertTrue(self.game(12)._wait_for_player(), 'menu with the input (commands, targets, Yes / No): waiting for the player')
        j = self.game(None); j.engine.msg_visible = True; j.engine.ui.msg = {'feed': True}; self.assertTrue(j._wait_for_player(), 'message with its cursor: waiting for the player')


class MaskCode(unittest.TestCase):
    """Poker (type 48): the window's code 2 receives a MASK (63 = all active); the exported `fx` array only knows 0 to 5."""
    def window(self, fx):
        e = {'kind': 'func', 'fx': fx}
        f = types.SimpleNamespace(N={10: {'buttonId': 0, 'act': False}, 11: {'buttonId': 1, 'act': False}, 12: {'buttonId': 5, 'act': False}, 13: {'buttonId': None, 'act': True}}, codes={2: [e]}, vals_code={}, church=False, status=False, names=False, begin=False)
        f.code = functools.partial(UI.Window.code, f); f._mask_code = functools.partial(UI.Window._mask_code, f)
        return f, e

    FX_REGULAR = {'0': {'d': {'10': {'act': False}, '11': {'act': False}, '12': {'act': False}}}, '1': {'d': {'11': {'act': False}, '12': {'act': False}}}, '2': {'d': {'10': {'act': False}, '12': {'act': False}}},
                   '3': {'d': {'12': {'act': False}}}}

    def test_mask_outside_array(self):
        f, e = self.window(self.FX_REGULAR)
        f.code(2, 63); self.assertEqual([f.N[n]['act'] for n in (10, 11, 12)], [True, True, True], '63: all the touch zones (cards 0, 1 and "Give")')
        f.code(2, 33); self.assertEqual([f.N[n]['act'] for n in (10, 11, 12)], [True, False, True], 'bits 0 and 5')
        self.assertTrue(f.N[13]['act'], 'an element outside the mask is not touched')

    def test_array_value_unchanged(self):
        f, e = self.window(self.FX_REGULAR)
        f.code(2, 1); self.assertEqual([f.N[n]['act'] for n in (10, 11, 12)], [True, False, False], 'value 1 of the table: as before')

    def test_irregular_array_does_nothing(self):
        """An array that does not have the form "bit n = button n": nothing is invented (original behavior)."""
        fx = {'0': {'d': {'10': {'act': False}, '11': {'act': False}}}, '1': {'d': {'10': {'act': False}, '11': {'act': False}}}}
        f, e = self.window(fx); f.code(2, 63); self.assertEqual([f.N[n]['act'] for n in (10, 11)], [False, False])

    def test_negative_or_non_integer_value(self):
        f, e = self.window(self.FX_REGULAR)
        f.code(2, -1); f.code(2, 'x'); self.assertEqual([f.N[n]['act'] for n in (10, 11, 12)], [False, False, False])


if __name__ == '__main__':
    unittest.main(verbosity=1)
