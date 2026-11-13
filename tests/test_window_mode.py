"""Test of the two window modes (windowed, full screen): `window_mode` setting (bounds, migration of the old boolean `full_screen` and of the old exclusive full screen, abandoned keys), shortcuts F11 and Alt + Enter
(real code of Game.on_key_press / on_key_release / _edges on a fake Game), one-step toggle (real code of Game.set_full_screen / _set_full_screen on a fake window: order of the calls, return to the starting state on
failure), order and graying out of the lines of the "Display" page of the Esc menu ("Fullscreen" switch, no texture smoothing or sprite edge correction setting). No real window is opened.

    python3 tests/test_window_mode.py
"""
import json, os, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq4_pc import language as _LANGUAGE; _LANGUAGE.select_language('fr')          # (these tests expect the French texts, whatever the computer's language)
import _paths          # (test helper: finding the source code in the subfolders of dq4_pc)
from dq4_pc.persistence import settings as RG


def load(content):
    f = os.path.join(tempfile.mkdtemp(prefix='rg_test_'), 'settings.json')
    with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
    return RG.Settings(f), f


class WindowModeSetting(unittest.TestCase):
    def test_default(self):
        r = RG.Settings(None)
        self.assertEqual(r['window_mode'], 0)
        for k in RG.OBSOLETE_KEYS: self.assertNotIn(k, r.v, k)

    def test_old_boolean_migration(self):
        r, _ = load({'plein_ecran': True}); self.assertEqual(r['window_mode'], 1)          # the old full screen = borderless window: mode 1
        r, _ = load({'plein_ecran': False}); self.assertEqual(r['window_mode'], 0)
        r, _ = load({'sound': False}); self.assertEqual(r['window_mode'], 0)                  # neither one nor the other: window
        r, _ = load({'plein_ecran': 'window.yes'}); self.assertEqual(r['window_mode'], 0)          # absurd value
        r, _ = load({'plein_ecran': True, 'window_mode': 1}); self.assertEqual(r['window_mode'], 1)
        r, _ = load({'plein_ecran': True, 'window_mode': 0}); self.assertEqual(r['window_mode'], 0)      # the new setting takes precedence

    def test_old_exclusive_fullscreen_becomes_fullscreen(self):
        r, _ = load({'window_mode': 2}); self.assertEqual(r['window_mode'], 1)
        r, _ = load({'window_mode': 2, 'mode_fenetre_retour': 0, 'plein_ecran': False}); self.assertEqual(r['window_mode'], 1)       # (the last non-exclusive mode is dropped)
        r, _ = load({'window_mode': 2.0}); self.assertEqual(r['window_mode'], 1)

    def test_bounds(self):
        for raw_value, expected in ((0, 0), (1, 1), (2, 1), (3, 0), (-1, 0), (1.5, 0), (2.0, 1), ('x', 0), ('2', 0), (None, 0), ([1], 0), (True, 1), (False, 0), (float('nan'), 0), (float('inf'), 0)):
            r, _ = load({'window_mode': raw_value}); self.assertEqual(r['window_mode'], expected, repr(raw_value))
            self.assertEqual(RG.valid_window_mode(raw_value), expected, repr(raw_value))

    def test_no_more_exclusive_full_screen_symbols(self):
        for name_str in ('MODES_FENETRE', 'NOMS_MODES_FENETRE'): self.assertFalse(hasattr(RG, name_str), name_str)

    def test_abandoned_keys_neither_read_nor_written(self):
        """`mode_fenetre_retour`, `edge_correction` and `smoothing` (removed options), `full_screen` (boolean): an old file contains them, they are ignored then disappear on save; the rest is kept."""
        r, f = load({'plein_ecran': True, 'mode_fenetre_retour': 1, 'correction_bords': False, 'lissage': False, 'music_volume': 0.4, 'msaa': 8})
        for k in RG.OBSOLETE_KEYS: self.assertNotIn(k, r.v, k)
        self.assertEqual((r['window_mode'], r['music_volume'], r['msaa']), (1, 0.4, 8))
        r.store()
        with open(f, encoding='utf-8') as fh: raw_value = json.load(fh)
        for k in RG.OBSOLETE_KEYS: self.assertNotIn(k, raw_value, k)
        r2 = RG.Settings(f); self.assertEqual((r2['window_mode'], r2['music_volume'], r2['msaa']), (1, 0.4, 8))

    def test_round_trip(self):
        r, f = load({'window_mode': 2, 'music_volume': 0.4})
        r['window_mode'] = 0; r.store(); self.assertEqual(RG.Settings(f)['window_mode'], 0)
        r['window_mode'] = 1; r.store(); self.assertEqual(RG.Settings(f)['window_mode'], 1)

    def test_f11_removed_from_old_file(self):
        r, _ = load({'keys_version': 4, 'keys': {'info': ['F11', None], 'map': ['M', 'F11']}})
        self.assertEqual(r['keys']['info'], [None, None]); self.assertEqual(r['keys']['map'], ['M', None])      # (F11 is no longer an action key)

    def test_f11_not_remappable(self):
        self.assertIn('F11', RG.RESERVED); self.assertIn('ESCAPE', RG.RESERVED)
        self.assertFalse(any('F11' in ts for ts in RG.DEFAULT_KEYS.values()))                    # (F11 was not a game key)


class Shortcuts(unittest.TestCase):
    """F11 and Alt + Enter (real code of Game.on_key_press / on_key_release / _edges on a fake Game, no window): toggle, Enter swallowed, party chat (Alt) when Alt alone is released."""
    @classmethod
    def setUpClass(cls):
        try: from dq4_pc.window import game as window; import pyglet; cls.WND = window; cls.K = pyglet.window.key; cls.pyglet = pyglet
        except Exception as ex: raise unittest.SkipTest('window.py non importable ici (%r)' % (ex,))

    def fake_game(self):
        WND = self.WND
        j = types.SimpleNamespace(swallowed=set(), alt_cand=False, alt_tap=False, reg=RG.Settings(None), key_list=self.K.KeyStateHandler(), prev_action={}, n=0, _ready=True, combo=[False, False], _logo_touched=False, pause_presses=0, name_presses=0,
                                  pause=None, _toggling=False, post=object(), port_screen=None, license_panel=None, last_device='', bascules=0, cancellations=0, is_fullscreen=False,
                                  mouse=(0, 0), mouse_guard=__import__('dq4_pc.window.inputs', fromlist=['MouseGuard']).MouseGuard())          # (mouse / mouse_guard: Game.on_key_press remembers the pointer position at each key)
        j.pause = types.SimpleNamespace(opened=False, capture=None, key_press=lambda sym, mods: setattr(j, 'pause_presses', j.pause_presses + 1))
        j.name_entry = types.SimpleNamespace(key_press=lambda sym, mods: setattr(j, 'name_presses', j.name_presses + 1))
        j.toggle_full_screen = lambda: setattr(j, 'bascules', j.bascules + 1)
        j._held = lambda a: WND.Game._held(j, a); j._name_entry_in_progress = lambda: False; j._state_number = WND.Game._state_number; j._window_shortcut = lambda sym, mods: WND.Game._window_shortcut(j, sym, mods)
        j.cancel_loading = lambda: setattr(j, 'cancellations', j.cancellations + 1)
        return j

    def press_state(self, j, sym):
        mods = self.K.MOD_ALT if j.key_list[self.K.LALT] or j.key_list[self.K.RALT] else 0
        j.key_list.on_key_press(sym, mods); return self.WND.Game.on_key_press(j, sym, mods)

    def release(self, j, sym):
        j.key_list.on_key_release(sym, 0); self.WND.Game.on_key_release(j, sym, 0)

    def tick(self, j): return self.WND.Game._edges(j)

    def test_f11_toggles_and_is_not_an_action(self):
        K = self.K; j = self.fake_game(); self.press_state(j, K.F11)
        self.assertEqual(j.bascules, 1); self.assertIn(K.F11, j.swallowed)
        j.reg['keys']['info'][0] = 'F11'; j.reg.codes_cache = {}                       # (an old file that binds F11 to an action: it is not triggered)
        self.assertFalse(j._held('info'))
        self.release(j, K.F11); self.assertNotIn(K.F11, j.swallowed)

    def test_alt_enter_toggles_without_validating_or_chat(self):
        K = self.K; j = self.fake_game()
        self.press_state(j, K.LALT); self.assertTrue(j.alt_cand)
        self.assertFalse(self.tick(j)['chat'])                                       # Alt held: nothing until it is released
        self.press_state(j, K.RETURN)
        self.assertEqual(j.bascules, 1); self.assertFalse(j.alt_cand)
        fr = self.tick(j); self.assertFalse(fr['menu']); self.assertFalse(j._held('menu'))      # Enter swallowed: neither confirmation nor menu
        self.release(j, K.RETURN); self.release(j, K.LALT)
        self.assertFalse(self.tick(j)['chat']); self.assertFalse(j.alt_tap)          # Alt released after Alt + Enter: no party chat
        self.press_state(j, K.RETURN); self.assertTrue(self.tick(j)['menu'])                     # (Enter alone works again)
        self.assertEqual(j.bascules, 1)

    def test_numpad_enter_and_alt_gr(self):
        K = self.K; j = self.fake_game(); self.press_state(j, K.RALT); self.press_state(j, K.ENTER)
        self.assertEqual(j.bascules, 1); self.release(j, K.ENTER); self.release(j, K.RALT); self.assertFalse(self.tick(j)['chat'])

    def test_alt_enter_without_system_flag(self):
        """The event's MOD_ALT flag may be missing (Alt already held down before the focus, unusual keyboard): the state of the Alt keys is enough."""
        K = self.K; j = self.fake_game(); j.key_list.on_key_press(K.LALT, 0)
        self.WND.Game.on_key_press(j, K.RETURN, 0); self.assertEqual(j.bascules, 1)

    def test_enter_alone_does_not_toggle(self):
        K = self.K; j = self.fake_game(); self.press_state(j, K.RETURN); self.assertEqual(j.bascules, 0); self.assertTrue(self.tick(j)['menu'])
        self.press_state(j, K.LALT); self.assertEqual(j.bascules, 0)                             # (nor does Alt alone)

    def test_in_all_contexts(self):
        """Esc menu open, name entry, entry logos: F11 and Alt + Enter toggle and are passed on neither to the menu, nor to the name entry, nor to the logos (which are skipped by any press)."""
        K = self.K
        j = self.fake_game(); j.pause.opened = True; self.press_state(j, K.F11); self.press_state(j, K.LALT); self.assertEqual((j.bascules, j.pause_presses), (1, 1))      # (Alt alone reaches the menu)
        self.press_state(j, K.RETURN); self.assertEqual((j.bascules, j.pause_presses), (2, 1))                    # Alt + Enter: switch, no Enter key for the menu
        self.release(j, K.RETURN); self.release(j, K.LALT); self.press_state(j, K.RETURN); self.assertEqual((j.bascules, j.pause_presses), (2, 2))      # Enter alone reaches it
        j = self.fake_game(); j._name_entry_in_progress = lambda: True; self.press_state(j, K.F11); self.assertEqual((j.bascules, j.name_presses), (1, 0))
        j = self.fake_game(); j._ready = False; self.press_state(j, K.F11); self.assertEqual((j.bascules, j._logo_touched), (1, False))      # (a press on another key skips the logos, not F11)
        self.press_state(j, K.SPACE); self.assertTrue(j._logo_touched)

    def test_alt_alone_triggers_chat_on_release(self):
        K = self.K; j = self.fake_game()
        self.press_state(j, K.LALT); self.assertFalse(self.tick(j)['chat'])
        self.release(j, K.LALT); self.assertTrue(self.tick(j)['chat'])               # only once
        self.assertFalse(self.tick(j)['chat'])
        self.press_state(j, K.RALT); self.release(j, K.RALT); self.assertTrue(self.tick(j)['chat'])      # Alt Gr too

    def test_alt_tab_does_not_start_chat(self):
        K = self.K; j = self.fake_game(); self.press_state(j, K.LALT)
        j.key_list.on_deactivate()                                                          # the window loses focus: the release never arrives
        self.assertFalse(self.tick(j)['chat']); self.assertFalse(j.alt_cand)

    def test_pause_menu_opened_or_key_other_than_alt(self):
        K = self.K; j = self.fake_game(); j.pause.opened = True; self.press_state(j, K.LALT); self.release(j, K.LALT)
        self.assertFalse(self.tick(j)['chat'])                                       # (the Esc menu sends nothing to the game)
        j = self.fake_game(); j.reg.bind('chat', 0, K.G); j.reg.unbind('chat', 1)      # party chat = G alone: at the moment of the press, as before
        self.press_state(j, K.G); self.assertTrue(self.tick(j)['chat']); self.release(j, K.G)
        self.press_state(j, K.LALT); self.release(j, K.LALT); self.assertFalse(self.tick(j)['chat'])        # Alt is no longer used for anything

    def test_key_capture_in_progress(self):
        K = self.K; j = self.fake_game(); j.pause.capture = ('A', 0, False)
        self.assertFalse(j._window_shortcut(K.F11, 0))                                   # the "Controls" page is waiting for a key: F11 goes back to it (it answers "reservee")
        self.assertEqual(j.bascules, 0)

    def test_no_toggle_during_toggle(self):
        K = self.K; j = self.fake_game(); j._toggling = True; self.press_state(j, K.F11)
        self.assertEqual(j.bascules, 0); self.assertIn(K.F11, j.swallowed)                   # (swallowed all the same: no confirmation)


class FakeScreen:
    """A pyglet monitor (x, y, width, height, name, is_primary)."""
    def __init__(self, x, y, w, h, name_str='', main=False, stale=False): self.x, self.y, self.width, self.height, self.name, self.is_primary, self.stale = x, y, w, h, name_str, main, stale          # stale: its Windows handle is no longer valid (after connecting a screen)
    def get_monitor_name(self): return self.name


class FakeWindow:
    """The calls the toggle makes to the pyglet window, in order (`logfile`), with the state they change. `failure`: name of the call that raises an error (once). `screens`: the monitors (FakeScreen; default: just one,
    the desktop); `screen_page`: the one of the window according to pyglet (`screen`, default the first)."""
    def __init__(self, WND, full=False, size_value=(1280, 720), desktop=(1920, 1080), failure=None, screens=None, screen_page=0):
        self.logfile = []; self.fullscreen = full; self._visible = True
        self._screens = screens or [FakeScreen(0, 0, desktop[0], desktop[1], main=True)]; self._screen = self._screens[screen_page]
        self.display = types.SimpleNamespace(get_screens=lambda: list(self._screens)); self.width, self.height = ((self.screen.width, self.screen.height) if full else size_value)
        self.desktop = desktop; self.failure = failure; self._windowed_location = None if full else (100, 80); self._windowed_size = size_value
        self.window_size = size_value; self.win_mode = 1 if full else 0; self._ready = True; self._toggling = False; self.reg = RG.Settings(None)
        self.post = types.SimpleNamespace(lookup_key=('key', 1))
        for name_str in ('set_full_screen', '_set_full_screen', '_apply_full_screen', 'toggle_full_screen', '_toggle_frame', '_read_screens', '_window_screen_index', '_screen_for_fullscreen', '_already_on', '_note_full_zone', '_note_toggle_failure', '_refresh_screen'): setattr(self, name_str, types.MethodType(getattr(WND.Game, name_str), self))
        self._simulated_failure = WND.Game._simulated_failure; self.desktop_ = desktop
        self._check_real_size = lambda: self.logfile.append('verifier')
        self._log_window = lambda q: self.logfile.append('journal(%s)' % q)
        self.set_battle_speed = lambda v: None; self.apply_text = lambda: None          # (the Display page holds the "Text scrolling" section)

    @property
    def is_fullscreen(self): return self.win_mode == 1

    @property
    def screen(self): return self._screen          # (pyglet: BaseWindow.screen returns _screen)

    def _trap(self, name_str):
        self.logfile.append(name_str)
        if self.failure == name_str: self.failure = None; raise RuntimeError('echec de %s' % name_str)

    def set_visible(self, v=True): self._trap('visible(%s)' % bool(v)); self._visible = bool(v)

    def get_location(self): return (self.screen.x, self.screen.y) if self.fullscreen else (self._windowed_location or (0, 0))

    def set_fullscreen(self, fullscreen=True, screen=None, mode=None, width=None, height=None):
        """The pyglet 2.1 signature: (fullscreen, screen, mode, width, height)."""
        size_value = (width, height) if width is not None else ()
        self._trap('set_fullscreen(%s%s%s)' % (bool(fullscreen), ',%dx%d' % size_value if size_value else '', ',screen %d' % (self._screens.index(screen) + 1) if screen is not None else ''))
        if not self.fullscreen: self._windowed_size = (self.width, self.height); self._windowed_location = self._windowed_location or (100, 80)
        self.fullscreen = bool(fullscreen)
        if fullscreen:
            if screen is not None: self._screen = screen
            self.width, self.height = self.screen.width, self.screen.height
        else: self.width, self.height = (size_value if size_value else self._windowed_size); self._windowed_location = self._windowed_location or None
        if self._screen.stale: raise OSError(9, 'Descripteur non valide', None, -2147024890)          # (Win32Window._create: Screen.get_dpi -> GetDpiForMonitor on a handle that is no longer valid; the state has already changed, as in pyglet)

    def set_location(self, x, y): self._trap('set_location(%d,%d)' % (x, y)); self._windowed_location = (x, y)

    def switch_to(self): self.logfile.append('switch_to')

    def on_draw(self): self.logfile.append('on_draw(%dx%d)' % (self.width, self.height))

    def flip(self): self.logfile.append('flip')

    def clear(self): self.logfile.append('clear')


class Toggle(unittest.TestCase):
    """Real code of Game.set_full_screen / _set_full_screen on a fake window: a single step (hidden, one set_fullscreen, a frame at the final size, shown), remembered size, fallback on failure."""
    @classmethod
    def setUpClass(cls):
        try:
            from dq4_pc.window import game as window; cls.WND = window
        except Exception as ex: raise unittest.SkipTest('window.py non importable ici (%r)' % (ex,))

    def failures(self):
        """Number of toggle failures recorded in the error log (the window no longer displays a message: console and log only)."""
        try:
            with open(self.errors_logfile, encoding='utf-8') as fh: return fh.read().count('failed ---')
        except OSError: return 0

    def setUp(self):
        os.environ.pop('DQ_SIM_FAILURE', None); os.environ.pop('DQ_SIMPLE_TOGGLE', None)
        self.errors_logfile = os.path.join(tempfile.mkdtemp(prefix='journal_fenetre_'), 'window_errors.log'); os.environ['DQ_WINDOW_LOG'] = self.errors_logfile          # (the simulated failures are not written to the repository)
        self.zone = self.WND.useful_zone; self.WND.useful_zone = lambda: (1904, 1040)          # (a 1920 x 1080 desktop: the size of the test screen does not matter)

    def tearDown(self):
        self.WND.useful_zone = self.zone; os.environ.pop('DQ_SIM_FAILURE', None); os.environ.pop('DQ_SIMPLE_TOGGLE', None); os.environ.pop('DQ_WINDOW_LOG', None)

    def win(self, **k): return FakeWindow(self.WND, **k)

    def test_to_full_screen_in_one_step(self):
        f = self.win(); self.assertTrue(f.set_full_screen(True))
        self.assertEqual(f.logfile, ['visible(False)', 'set_fullscreen(True)', 'switch_to', 'on_draw(1920x1080)', 'flip', 'visible(True)', 'switch_to', 'on_draw(1920x1080)', 'flip', 'journal(full screen)'])
        self.assertEqual((f.win_mode, f.reg['window_mode'], f.window_size), (1, 1, (1280, 720)))         # (the window size is kept for the return)
        self.assertEqual(f.post.lookup_key, ('key', 1))                                                              # (the off-screen rendering buffers are not forcibly invalidated: redone only if the size changes)

    def test_window_manager_animations_off_before_the_hide(self):
        """(Windows, cannot be verified here): the DWM fade-out / fade-in are turned off BEFORE the window is hidden, otherwise they play around the switch."""
        from dq4_pc.window import full_screen as FS
        old = FS.pause_transitions_dwm
        try:
            for target in (True, False):
                f = self.win(full=not target); FS.pause_transitions_dwm = lambda w, f=f: f.logfile.append('dwm_off')
                f.set_full_screen(target); self.assertEqual(f.logfile[0], 'dwm_off'); self.assertEqual(f.logfile[1], 'visible(False)')
                g = self.win(full=target); FS.pause_transitions_dwm = lambda w, g=g: g.logfile.append('dwm_off')
                g.set_full_screen(target); self.assertNotIn('dwm_off', g.logfile, 'already in this mode: nothing to switch')
        finally: FS.pause_transitions_dwm = old

    def test_pause_transitions_dwm_turns_them_off_then_back_on(self):
        import ctypes
        from dq4_pc.window import helpers as H
        calls = []
        class Dwm:
            def DwmSetWindowAttribute(self, h, attr, ref, size_value): calls.append(ref._obj.value); return 0
        w = types.SimpleNamespace(_hwnd=0x1234); self.assertFalse(H.pause_transitions_dwm(w), 'not Windows: nothing changes')
        old = sys.platform; sys.platform = 'win32'; ctypes.windll = types.SimpleNamespace(dwmapi=Dwm())
        try:
            self.assertTrue(H.pause_transitions_dwm(w)); self.assertTrue(H.pause_transitions_dwm(w))          # (a second switch restarts the delay)
            self.assertEqual(calls, [1, 1]); w._dwm_back(0); self.assertEqual(calls, [1, 1, 0], 'back on after the delay')
        finally: sys.platform = old; del ctypes.windll; self.WND.pyglet.clock.unschedule(w._dwm_back)

    def test_return_to_window_in_one_step_at_remembered_size(self):
        f = self.win(); f.set_full_screen(True); f.logfile.clear(); self.assertFalse(f.set_full_screen(False))
        self.assertEqual(f.logfile, ['visible(False)', 'set_fullscreen(False,1280x720)', 'switch_to', 'on_draw(1280x720)', 'flip', 'visible(True)', 'switch_to', 'on_draw(1280x720)', 'flip', 'journal(window)'])
        self.assertEqual((f.win_mode, f.reg['window_mode'], f.width, f.height), (0, 0, 1280, 720))

    def test_no_double_set_fullscreen(self):
        f = self.win()
        for i in range(6): f.toggle_full_screen()
        self.assertEqual(sum(1 for e in f.logfile if e.startswith('set_fullscreen')), 6)                      # only one per switch, never "window then full screen"
        self.assertEqual(sum(1 for e in f.logfile if e == 'visible(False)'), sum(1 for e in f.logfile if e == 'visible(True)'))      # window always shown again

    def test_already_in_requested_mode(self):
        f = self.win(); f.set_full_screen(False); self.assertEqual(f.logfile, []); self.assertEqual(f.reg['window_mode'], 0)

    def test_too_large_size_clamped_to_the_screen(self):
        f = self.win(full=True, size_value=(1280, 720)); f.window_size = (7680, 4320); f.set_full_screen(False)
        w, h = self.WND.adjust_size(7680, 4320)
        self.assertIn('set_fullscreen(False,%dx%d)' % (w, h), f.logfile)

    def test_launched_full_screen_window_is_centered_on_return(self):
        f = self.win(full=True); f.set_full_screen(False)
        self.assertIn('set_location(320,180)', f.logfile)                                                     # 1920 x 1080: 1280 x 720 window at the center of the desktop
        f = self.win(); f.set_full_screen(True); f.logfile.clear(); f.set_full_screen(False)
        self.assertFalse([e for e in f.logfile if e.startswith('set_location') and e != 'set_location(100,80)'])      # position remembered by the window: kept (no recentering)

    def test_full_screen_failure_keeps_initial_state(self):
        os.environ['DQ_SIM_FAILURE'] = '1'
        f = self.win(); self.assertFalse(f.set_full_screen(True))
        self.assertFalse(f.fullscreen); self.assertTrue(f._visible); self.assertEqual((f.win_mode, f.reg['window_mode']), (0, 0))
        self.assertEqual(self.failures(), 1)
        self.assertEqual([e for e in f.logfile if e.startswith('set_fullscreen')], ['set_fullscreen(True)', 'set_fullscreen(False,1280x720)'])      # (change, then return to the starting state)
        self.assertEqual(f.logfile[-6:], ['flip', 'visible(True)', 'switch_to', 'on_draw(1280x720)', 'flip', 'journal(window)'])                       # (one complete frame is drawn before and after the window is shown)

    def test_return_to_window_failure_stays_full_screen(self):
        f = self.win(); f.set_full_screen(True); os.environ['DQ_SIM_FAILURE'] = '0'
        self.assertTrue(f.set_full_screen(False)); self.assertTrue(f.fullscreen); self.assertTrue(f._visible); self.assertEqual((f.win_mode, f.reg['window_mode']), (1, 1))
        self.assertEqual(self.failures(), 1)

    def test_full_error_is_noted_in_the_log(self):
        """the line "Window failed (...)" does not say where it failed: the full call stack, the state of the window and of the monitors go into window_errors.log (and the console)."""
        f = self.win(full=True, failure='set_fullscreen(False,1280x720)'); self.assertTrue(f.set_full_screen(False))      # (the failure happens only once: the return to the starting state succeeds)
        self.assertEqual(self.failures(), 1)
        txt = open(self.errors_logfile, encoding='utf-8').read()
        self.assertIn('switch to windowed mode failed', txt); self.assertIn('Traceback', txt); self.assertIn('RuntimeError', txt); self.assertIn('echec de set_fullscreen(False,1280x720)', txt)
        self.assertIn('_apply_full_screen', txt)                                                                          # the call stack: where it failed
        self.assertIn('window: full screen = ', txt); self.assertIn('monitors: 1920 x 1080 at (0, 0) (primary)', txt); self.assertIn('pyglet ', txt)
        f2 = self.win(full=True, failure='visible(False)'); f2.set_full_screen(False)
        self.assertEqual(open(self.errors_logfile, encoding='utf-8').read().count('failed ---'), 2)             # (one more entry, appended: the log is never overwritten)

    def test_a_log_error_does_not_hinder_the_toggle(self):
        os.environ['DQ_WINDOW_LOG'] = os.path.join(self.errors_logfile, 'dossier', 'inexistant', 'x.log')       # (unwritable)
        f = self.win(full=True, failure='set_fullscreen(False,1280x720)'); self.assertTrue(f.set_full_screen(False))
        self.assertTrue(f.fullscreen)

    def test_no_entry_without_failure(self):
        f = self.win(); f.set_full_screen(True); f.set_full_screen(False); self.assertFalse(os.path.exists(self.errors_logfile))

    def test_pyglet_window_error(self):
        for k, call in enumerate(('set_fullscreen(True)', 'visible(False)'), 1):
            f = self.win(failure=call); f.set_full_screen(True)
            self.assertFalse(f.fullscreen, call); self.assertTrue(f._visible, call); self.assertEqual((f.win_mode, f.reg['window_mode']), (0, 0), call)
            self.assertEqual(self.failures(), k, call)                                                          # (one more failure on each attempt)
            f.set_full_screen(True); self.assertTrue(f.fullscreen, call)                                 # (the next attempt works)

    # ----: a screen plugged in while the window exists makes pyglet's monitor handle invalid
    def stale_win(self, full=True, **k):
        """A window whose monitor held by pyglet (`_screen`) is stale (same position and same dimensions as monitor 1 of the new list): a second screen has just been plugged in."""
        main = FakeScreen(0, 0, 1920, 1200, main=True); external = FakeScreen(-331, -1440, 2560, 1440)
        f = self.win(full=full, screens=[main, external], **k); f._screen = FakeScreen(0, 0, 1920, 1200, main=True, stale=True)
        return f, main, external

    def test_stale_fake_monitor_reproduces_windows_error(self):
        f, _, _ = self.stale_win()
        with self.assertRaises(OSError) as c: f.set_fullscreen(False, width=1280, height=720)
        self.assertEqual(c.exception.errno, 9)

    def test_full_screen_then_external_screen_plugged_in_back_to_window(self):
        """A real case: full screen, external screen plugged in, switch to windowed mode: works."""
        f, main, _ = self.stale_win()
        self.assertFalse(f.set_full_screen(False))
        self.assertFalse(f.fullscreen); self.assertTrue(f._visible); self.assertEqual((f.win_mode, f.reg['window_mode']), (0, 0))
        self.assertIs(f._screen, main)                                                                  # the kept monitor is the one from the new list
        self.assertFalse(os.path.exists(self.errors_logfile))                                               # no error recorded
        self.assertEqual([e for e in f.logfile if e.startswith('set_fullscreen')], ['set_fullscreen(False,1280x720)'])

    def test_window_then_external_screen_plugged_in_full_screen(self):
        """Same defect the other way around: windowed, screen plugged in, full screen on pyglet's monitor (set_fullscreen(True) without a monitor, as before)."""
        f, main, _ = self.stale_win(full=False)
        self.assertTrue(f.set_full_screen(True)); self.assertTrue(f.fullscreen); self.assertIs(f._screen, main)
        self.assertFalse(os.path.exists(self.errors_logfile))

    def test_return_to_initial_state_also_uses_new_monitor(self):
        """If the switch to windowed mode fails for another reason, the return to full screen does not reuse the stale handle."""
        f, main, _ = self.stale_win(failure='set_fullscreen(False,1280x720)')
        self.assertTrue(f.set_full_screen(False)); self.assertTrue(f.fullscreen); self.assertEqual(self.failures(), 1)
        self.assertIs(f._screen, main)
        self.assertNotIn('Return to the starting state failed', open(self.errors_logfile, encoding='utf-8').read())

    def test_unplugged_monitor_window_takes_current_or_main(self):
        """The old monitor no longer exists (none at the same position): the kept monitor becomes the one where the window is, failing that the primary one."""
        main = FakeScreen(0, 0, 1920, 1080, main=True)
        f = self.win(full=True, screens=[main]); f._screen = FakeScreen(-1920, 0, 1920, 1080, stale=True)
        self.assertFalse(f.set_full_screen(False)); self.assertIs(f._screen, main)

    def test_refresh_never_raises_an_error(self):
        f = self.win(full=True); old = f._screen
        f.display = types.SimpleNamespace(get_screens=lambda: (_ for _ in ()).throw(RuntimeError('moniteurs illisibles')))
        self.assertFalse(f._refresh_screen()); self.assertIs(f._screen, old)
        f.display = types.SimpleNamespace(get_screens=lambda: []); self.assertFalse(f._refresh_screen()); self.assertIs(f._screen, old)
        f._screen = None; self.assertFalse(f._refresh_screen())

    def test_no_toggle_during_toggle(self):
        f = self.win(); f._toggling = True; self.assertFalse(f.set_full_screen(True)); self.assertEqual(f.logfile, [])

    def test_simple_debug_toggle(self):
        os.environ['DQ_SIMPLE_TOGGLE'] = '1'
        f = self.win(); f.set_full_screen(True); self.assertEqual(f.logfile, ['set_fullscreen(True)', 'journal(full screen)'])


class DisplayPage(unittest.TestCase):
    """"Display" page of the Esc menu: desired order, "Fullscreen" line = simple Yes / No switch, no "Resolution", no texture smoothing or sprite edge correction setting."""
    ORDER = ['settings.language', 'settings.fullscreen', 'settings.brightness', 'settings.contrast', 'settings.filter', 'settings.shader', 'settings.vignette_effect', 'settings.edge_blur', 'settings.sharpness', 'settings.antialiasing', 'settings.supersampling', 'settings.text_speed', 'settings.interface']          # ("Filter" above "Shader", no "Motion blur" line)

    @classmethod
    def setUpClass(cls):
        try: from dq4_pc.menus import pause
        except Exception as ex: raise unittest.SkipTest('pause.py non importable ici (%r)' % (ex,))
        cls.PA = pause

    def page(self, full, reg=None):
        reg = reg or RG.Settings(None); reg['window_mode'] = int(full); calls = []
        J = self.J = types.SimpleNamespace(reg=reg, win_mode=int(full), mode=4, zoom=1.0, post=types.SimpleNamespace(max_msaa=None), is_fullscreen=full,
                                  resolutions=lambda: [(1280, 720), (1920, 1080)], current_resolution=lambda: (1920, 1080),
                                  set_resolution=lambda v: calls.append(('res', v)), set_full_screen=lambda v: calls.append(('plein', v)),
                                  set_mode=lambda v: None, set_distance=lambda v: None, set_battle_speed=lambda v: None, apply_text=lambda: None)
        self.P = self.PA.Pause(J); return self.P._entries_display(), calls

    def test_order(self):
        for full in (False, True):
            e, _ = self.page(full); self.assertEqual([x['l'] for x in e], self.ORDER, 'plein %s' % full)

    def test_full_screen_line_is_a_switch(self):
        for full in (False, True):
            e, calls = self.page(full); f = e[1]                                                  # (e[0]: "Language")
            self.assertEqual((f['t'], f['vals'], f['sw'], f['v']()), ('choice', [False, True], True, 'settings.yes' if full else 'settings.no'))      # Yes / No switch, not a drop-down list
            self.assertTrue(f['hint'])
            f['ok'](); self.assertEqual(calls[-1], ('plein', not full))                        # Enter / click toggles (Game.set_full_screen)
            n = len(calls); (f['minus'] if full else f['plus'])(); self.assertEqual(calls[n:], [('plein', not full)])      # left = No, right = Yes
            n = len(calls); (f['plus'] if full else f['minus'])(); self.assertEqual(len(calls), n)                        # (already in that state: no change)

    def test_resolution_removed(self):
        """no "Resolution" line; "Battle speed" is on the Controls page, under its key."""
        for full in (False, True):
            e, calls = self.page(full)
            self.assertNotIn('Résolution', [x['l'] for x in e]); self.assertNotIn('settings.battle_speed', [x['l'] for x in e])
            self.assertFalse(any(x.get('off') for x in e), 'plein %s' % full)
        J = self.J; J.set_battle_speed = lambda v: None
        c = [x.get('l') for x in self.P._entries_commands()]
        i = c.index('settings.battle_speed'); self.assertEqual(self.P._entries_commands()[i - 1].get('act'), 'battle_speed')

    def test_no_more_smoothing_or_edge_correction_options(self):
        e, _ = self.page(False)
        for x in e: self.assertNotIn(x['l'], ('settings.texture_smoothing', 'settings.sprite_edge_correction', 'settings.window'))

    def test_full_screen_and_interface_at_ends(self):
        e, _ = self.page(False); self.assertEqual((e[0]['l'], e[1]['l'], e[-1]['l']), ('settings.language', 'settings.fullscreen', 'settings.interface'))          # ("Interface" at the very end)               # ("Language" at the top)


class RemovedCode(unittest.TestCase):
    """Exclusive full screen, the sprite edge correction option and the texture smoothing option are nowhere in the code (only their debug switches remain: environment variables)."""
    @classmethod
    def setUpClass(cls):
        try: from dq4_pc.window import game as window; cls.WND = window
        except Exception as ex: raise unittest.SkipTest('window.py non importable ici (%r)' % (ex,))

    def test_window(self):
        WND = self.WND
        for name_str in ('set_full_screen', 'toggle_full_screen', '_set_full_screen', '_window_shortcut'): self.assertTrue(hasattr(WND.Game, name_str), name_str)

    def test_read_removed_settings(self):
        """No read of `reg['lissage']` / `reg['edge_correction']` / `reg['mode_fenetre_retour']` in the code."""
        import re
        for file_name in ('window.py', 'pause.py', 'postfx.py', 'flat_sceneries.py', 'settings.py'):
            src = _paths.source(file_name)
            self.assertIsNone(re.search(r"\[\s*'(lissage|correction_bords|mode_fenetre_retour)'\s*\]", src), file_name)
            self.assertNotIn("'lissage':", src, file_name); self.assertNotIn("'correction_bords':", src, file_name)

    def test_smoothing_and_correction_always_active(self):
        """the edge correction is 0 by default (raw position of the NPCs, as in the game); the old full correction is requested with --edge-correction or DQ_EDGE_CORRECTION; an old setting changes nothing here."""
        WND = self.WND; j = types.SimpleNamespace(args=types.SimpleNamespace(), reg=RG.Settings(None))
        os.environ.pop('DQ_EDGE_CORRECTION', None)
        self.assertEqual(WND.Game._edge_correction(j), 0.0)                                                    # raw position, no setting
        j.reg.v['correction_bords'] = True; self.assertEqual(WND.Game._edge_correction(j), 0.0)                # (an old setting changes nothing here)
        os.environ['DQ_EDGE_CORRECTION'] = '100'
        try: self.assertEqual(WND.Game._edge_correction(j), 1.0)                                              # old full correction (debugging)
        finally: os.environ.pop('DQ_EDGE_CORRECTION', None)
        j.args.edge_correction = 40; self.assertAlmostEqual(WND.Game._edge_correction(j), 0.4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
