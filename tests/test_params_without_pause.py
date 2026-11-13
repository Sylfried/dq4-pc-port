"""Test (without engine or display) of the "Settings" screen: the screen that used to be called "Pause" (Esc menu) is now called "Settings" and no longer pauses the game: the game keeps running behind it
(with no key or click: the menu keys do not make the hero walk). ("there must be no pause in any menu") NO page stops it, not even "History" or "Quit";
the mechanism (Pause.FROZEN_PAGES, empty) remains and is tried here with a frozen test page.

    python3 tests/test_params_without_pause.py

  1. the root title is "Settings" (no longer "Pause");
  2. Pause.freezes_game: false when the menu is closed, false on ALL pages (root, settings, history, exit question; any `_e_*` page of the menu), Pause.FROZEN_PAGES empty;
  3. Game._sync_freeze: the sound and the clock stop only when entering a frozen page (here a test page added to FROZEN_PAGES; none by default), and restart when leaving it (without catching up the elapsed time); Game.pause_game: opening cuts nothing, closing gives the sound back if it was stopped;
  4. Game.tick: no input is sent to the engine while the menu is open; Game._speed_factor: no accelerated walking while the menu is open (no direction is sent to the game);
  5. Game._loop: the engine runs while the menu is open (except on a frozen page: none).
"""
import inspect, os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq4_pc.window import game as F
from dq4_pc.menus import pause as PA
from dq4_pc.core import engine as ENGINE


def menu(screen_page, opened=True):
    p = PA.Pause.__new__(PA.Pause); p.opened = opened; p.stack = ['root'] + ([screen_page] if screen_page != 'root' else []); return p


class TestTitle(unittest.TestCase):
    def test_root_is_called_settings(self):
        src = inspect.getsource(PA.Pause.draw_all)
        self.assertIn("'root': N_('settings.settings')", src, 'the title of the root page')                    # (N_ marks the text, translated at drawing)
        self.assertNotIn("'root': 'Pause'", src); self.assertNotIn("'root': N_('Pause')", src)


class TestFrozenPages(unittest.TestCase):
    def test_settings_pages_let_game_run(self):
        for page in ('root', 'display', 'sound', 'controls', 'interface', 'states', 'changes'):
            self.assertFalse(menu(page).freezes_game(), page)

    def test_history_and_quit_no_longer_stop_the_game(self):                                                      # "the history menu pauses the game, there must be no pause in any menu"
        for page in ('history', 'quit'): self.assertFalse(menu(page).freezes_game(), page)

    def test_no_menu_page_freezes_the_game(self):
        pages = set(PA.Pause.PAGE_ENTRIES)
        self.assertGreaterEqual(len(pages), 8)                                                                           # (all the menu's pages, not only those this test knows)
        for page in sorted(pages): self.assertFalse(menu(page).freezes_game(), page)
        self.assertEqual(tuple(PA.Pause.FROZEN_PAGES), ())

    def test_closed_menu(self):
        self.assertFalse(menu('history', opened=False).freezes_game())

    def test_page_added_to_frozen_pages_would_freeze_the_game_until_return(self):                                  # (the mechanism remains, empty)
        old = PA.Pause.FROZEN_PAGES
        try:
            PA.Pause.FROZEN_PAGES = ('history',)
            p = menu('history'); self.assertTrue(p.freezes_game()); p.stack.pop(); self.assertFalse(p.freezes_game())
        finally: PA.Pause.FROZEN_PAGES = old


class Fake:
    """What the window loop asks of the menu, the sound and the rest (Game fields used by the tested methods)."""
    def __init__(self, screen_page='root'):
        self.stack_p = menu(screen_page); self.pause = self.stack_p; self.calls = []; self._game_frozen = False; self.acc = 5.0; self.t_loop = 1.0
        self.sound = types.SimpleNamespace(set_paused=lambda yes: self.calls.append(('sound', yes)))
        self.pad_prev = None; self.prev_action = None; self.rep = {}; self.hovered = self.press_state = self.hover_node = None
        self.pad = lambda: 0; self._held = lambda a: False; self.mouse_guard = types.SimpleNamespace(keyboard=lambda s: None); self.mouse = None


class TestStop(unittest.TestCase):
    """The stop mechanism (a FROZEN_PAGES page), tried with the "historique" page added for the duration of the test: by default no page stops the game anymore (see TestFrozenPages)."""
    def setUp(self): self._anc = PA.Pause.FROZEN_PAGES; PA.Pause.FROZEN_PAGES = ('history',)
    def tearDown(self): PA.Pause.FROZEN_PAGES = self._anc

    def test_default_opening_history_cuts_nothing(self):
        PA.Pause.FROZEN_PAGES = self._anc
        J = Fake('root'); J.pause.stack.append('history'); J.acc = 7.0; F.Game._sync_freeze(J)
        self.assertEqual(J.calls, []); self.assertFalse(J._game_frozen); self.assertEqual((J.acc, J.t_loop), (7.0, 1.0))      # neither sound cut nor clock reset

    def test_entering_frozen_page_cuts_sound_and_clock(self):
        J = Fake('root'); F.Game._sync_freeze(J); self.assertEqual(J.calls, []); self.assertFalse(J._game_frozen)       # root: nothing stops
        J.pause.stack.append('history'); J.acc = 7.0; F.Game._sync_freeze(J)
        self.assertEqual(J.calls, [('sound', True)]); self.assertTrue(J._game_frozen); self.assertEqual((J.acc, J.t_loop), (0.0, None))
        F.Game._sync_freeze(J); self.assertEqual(J.calls, [('sound', True)], 'no repetition')

    def test_leaving_frozen_page_restarts(self):
        J = Fake('history'); F.Game._sync_freeze(J); J.pause.stack.pop(); J.acc = 3.0; J.t_loop = 2.0
        F.Game._sync_freeze(J)
        self.assertEqual(J.calls, [('sound', True), ('sound', False)]); self.assertFalse(J._game_frozen); self.assertEqual((J.acc, J.t_loop), (0.0, None), 'no catching up of the time spent')

    def test_open_root_cuts_nothing(self):
        J = Fake('root'); F.Game.pause_game(J, True); self.assertEqual(J.calls, []); self.assertFalse(J._game_frozen)

    def test_closing_from_frozen_page_restores_sound(self):
        J = Fake('history'); F.Game._sync_freeze(J); J.pause.opened = False; F.Game.pause_game(J, False)
        self.assertEqual(J.calls, [('sound', True), ('sound', False)]); self.assertFalse(J._game_frozen)

    def test_closing_root_does_not_touch_sound(self):
        J = Fake('root'); F.Game.pause_game(J, True); J.pause.opened = False; F.Game.pause_game(J, False); self.assertEqual(J.calls, [])


class TestInputs(unittest.TestCase):
    def test_tick_sends_no_input_while_menu_open(self):
        src = inspect.getsource(F.Game.tick)
        self.assertIn('(mute or self.pause.opened)', src)                                               # (0, 0): no key, no click, no direction for the game

    def fake_factor(self, opened, dirs):
        eng = types.SimpleNamespace(state=types.SimpleNamespace(effect=None, transition_guard=0, part=ENGINE.PART_FIELD, load_wait=None), msg_visible=False, active_menu=lambda: None, flags=lambda: 0)
        J = types.SimpleNamespace(reg={'accel_speed': 2.0, 'battle_speed': 0}, engine=eng, pause=types.SimpleNamespace(opened=opened),
                                  pad=lambda: dirs, _held=lambda a: a == 'accel', hud=types.SimpleNamespace(dpad_run=lambda: False))
        J._battle_clock = lambda: F.Game._battle_clock(J)
        return F.Game._speed_factor(J)

    def test_no_accelerated_walk_with_menu_opened(self):
        self.assertEqual(self.fake_factor(False, ENGINE.LEFT), 2.0, 'terrain : l\'accelerateur s\'applique')
        self.assertEqual(self.fake_factor(True, ENGINE.LEFT), 1.0, 'menu open: a menu direction does not make the game run')


class TestLoop(unittest.TestCase):
    def test_engine_runs_with_menu_open_except_frozen_page(self):
        src = inspect.getsource(F.Game._loop)
        self.assertIn('if self.pause.freezes_game():', src)                                           # only the early return of a frozen page (none by default) stops the engine
        self.assertNotIn('if self.pause.opened: self.pause.do_update(); self.acc = 0.0', src)                 # the old general stop is gone
        self.assertIn('self._sync_freeze()', src)


if __name__ == '__main__':
    unittest.main(verbosity=1)
