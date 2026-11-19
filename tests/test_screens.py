"""Test of the full screen monitor: full screen (F11, Alt + Enter, "Fullscreen" switch) always happens on the monitor where the window is. There is no choice of monitor (the old setting `ecran_plein`
is ignored). Without a real window, with fake monitors (`FakeScreen`) and the real logic of screens.py and window.Game (bound to a fake
window that logs its calls).

  1. screens.py: list of monitors (primary marked), the window's monitor (the one of its center), target (the window's, failing that the primary);
  2. settings: `ecran_plein` and `sortie_audio` no longer exist (obsolete keys, never read again); the mouse camera keys remain boolean;
  3. full screen: the monitor where the window is is used at each entry (even after a move), a single monitor as before; unreadable monitors = fallback without a crash; failure = window kept;
     return to windowed mode where it was (or centered on the full screen monitor);
  4. Display page: no "full screen monitor" line.

    python3 tests/test_screens.py
"""
import json, os, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import pyglet
pyglet.options['shadow_window'] = False          # no hidden window: the test runs without a display server
from dq456_pc.window import screens as EK
from dq456_pc.persistence import settings as RG

try:
    from dq456_pc.window import game as WND
    from test_window_mode import FakeWindow, FakeScreen
except Exception as ex:
    WND = None; ERROR_WND = ex

A = lambda: FakeScreen(0, 0, 1920, 1080, 'Moniteur A', True)
B = lambda: FakeScreen(1920, 0, 2560, 1440, 'Moniteur B')
C = lambda: FakeScreen(-1280, 0, 1280, 1024, '')


class Logic(unittest.TestCase):
    def test_entries_main_marked(self):
        d = EK.listing([B(), A()])                                                    # (pyglet may give the primary one second)
        self.assertEqual([x['primary'] for x in d], [False, True]); self.assertEqual([x['index'] for x in d], [0, 1])
        self.assertEqual((d[1]['width'], d[1]['height'], d[1]['name']), (1920, 1080, 'Moniteur A')); self.assertEqual(EK.listing([C()])[0]['name'], '')

    def test_a_single_primary_even_if_the_system_announces_none(self):
        e1, e2 = FakeScreen(0, 0, 100, 100), FakeScreen(100, 0, 100, 100)
        e1.is_primary = e2.is_primary = False
        d = EK.listing([e2, e1]); self.assertEqual(sum(x['primary'] for x in d), 1); self.assertTrue(d[1]['primary'])          # (failing that: the one at (0, 0))
        e1.x = 5; self.assertTrue(EK.listing([e2, e1])[0]['primary'])                                           # (failing the default: the first)

    def test_unreadable_screens(self):
        self.assertEqual(EK.listing(None), []); self.assertEqual(EK.listing([]), [])
        d = EK.listing([object(), A()]); self.assertEqual(len(d), 1); self.assertEqual(d[0]['source'], 1)         # (an unreadable screen is ignored; `source` finds the pyglet object)

    def test_target_is_window_monitor(self):
        d = EK.listing([A(), B()])
        self.assertEqual(EK.target(d, 0), 0); self.assertEqual(EK.target(d, 1), 1)                                   # the window's
        self.assertEqual(EK.target(d, None), 0); self.assertEqual(EK.target(d, 7), 0); self.assertEqual(EK.target(d, -1), 0)          # unknown window: the primary
        self.assertEqual(EK.target(EK.listing([B(), A()]), None), 1)                                                    # (the primary, even when second)
        self.assertIsNone(EK.target([], None)); self.assertIsNone(EK.target([], 0))

    def test_window_screen(self):
        d = EK.listing([A(), B(), C()])
        self.assertEqual(EK.screen_of((100, 80, 1280, 720), d), 0)
        self.assertEqual(EK.screen_of((2000, 100, 1280, 720), d), 1)
        self.assertEqual(EK.screen_of((-1000, 0, 1280, 720), d), 2)
        self.assertEqual(EK.screen_of((1500, 100, 1280, 720), d), 1)                                              # straddling: the one at the center (2140, 460)
        self.assertEqual(EK.screen_of((1500, 100, 600, 300), d), 0)                                               # straddling, center (1800, 250): A
        self.assertEqual(EK.screen_of((1800, 100, 400, 300), d), 1)                                               # center (2000, 250): B
        self.assertIsNone(EK.screen_of((9000, 9000, 100, 100), d)); self.assertIsNone(EK.screen_of(None, d)); self.assertIsNone(EK.screen_of((1, 2), d))

class Setting(unittest.TestCase):
    def load(self, content):
        f = os.path.join(tempfile.mkdtemp(prefix='rg_ecran_'), 'settings.json')
        with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
        return RG.Settings(f), f

    def test_monitor_and_audio_output_choices_removed(self):
        for k in ('ecran_plein', 'sortie_audio'):
            self.assertNotIn(k, RG.DEFAULT); self.assertIn(k, RG.OBSOLETE_KEYS); self.assertNotIn(k, RG.Settings(None).v)
        r, f = self.load({'sound': False, 'ecran_plein': {'indice': 1, 'x': 1920, 'y': 0, 'largeur': 2560, 'hauteur': 1440, 'nom': 'B'}, 'sortie_audio': {'id': 'a', 'nom': 'Casque'}})
        for k in ('ecran_plein', 'sortie_audio'): self.assertNotIn(k, r.v, k)          # an old settings file: the two keys are not read again
        self.assertFalse(r['sound']); r.store()
        with open(f, encoding='utf-8') as fh: raw_value = json.load(fh)
        for k in ('ecran_plein', 'sortie_audio'): self.assertNotIn(k, raw_value, k)          # ... and disappear from the file on the next save

    def test_camera_key_boolean(self):
        r = RG.Settings(None); self.assertIs(r['camera_invert_lr'], False)          # default = dragging to the right rotates like the right arrow
        r, _ = self.load({'camera_invert_lr': True}); self.assertIs(r['camera_invert_lr'], True)
        r, _ = self.load({'camera_invert_lr': 'window.yes'}); self.assertIs(r['camera_invert_lr'], False)      # (absurd value: default)
        r, f = self.load({}); r['camera_invert_lr'] = True; r.store(); self.assertIs(RG.Settings(f)['camera_invert_lr'], True)
        r, _ = self.load({'camera_inverser_hb': True}); self.assertNotIn('camera_inverser_hb', r.v)      # (the tilt is removed: no more up / down inversion)



def win(screens=None, screen_page=0, **kw):
    return FakeWindow(WND, screens=screens, screen_page=screen_page, **kw)


@unittest.skipIf(WND is None, 'window.py non importable ici')
class FullScreen(unittest.TestCase):
    def setUp(self):
        os.environ.pop('DQ_SIM_FAILURE', None); os.environ.pop('DQ_SIMPLE_TOGGLE', None)
        self.zone = WND.useful_zone; WND.useful_zone = lambda: (1904, 1040)

    def tearDown(self):
        WND.useful_zone = self.zone; os.environ.pop('DQ_SIM_FAILURE', None); os.environ.pop('DQ_SIMPLE_TOGGLE', None)

    def two(self, **kw): return win([A(), B()], **kw)

    def sets(self, f): return [e for e in f.logfile if e.startswith('set_fullscreen')]

    def test_window_on_pyglet_monitor_as_before(self):
        f = self.two(); f.set_full_screen(True)
        self.assertEqual(self.sets(f), ['set_fullscreen(True)']); self.assertEqual((f.width, f.height), (1920, 1080))          # it is already pyglet's monitor: nothing imposed
        f = win(); f.set_full_screen(True); self.assertEqual(self.sets(f), ['set_fullscreen(True)'])             # a single monitor

    def test_follows_window_moved_to_another_monitor(self):
        f = self.two(); f._windowed_location = (2000, 100)                                                       # (pyglet still believes the window is on A, it is on B)
        f.set_full_screen(True); self.assertEqual(self.sets(f), ['set_fullscreen(True,screen 2)']); self.assertEqual((f.width, f.height), (2560, 1440))

    def test_each_entry_uses_monitor_where_window_is(self):
        """Window moved from one monitor to another between two passes: each entry into full screen happens on the monitor where it is."""
        f = self.two()
        for slot, expected in (((2000, 100), 'set_fullscreen(True,screen 2)'), ((100, 80), 'set_fullscreen(True,screen 1)'), ((2300, 200), 'set_fullscreen(True,screen 2)')):
            f.logfile.clear(); f._windowed_location = slot; f.toggle_full_screen()
            self.assertTrue(f.fullscreen); self.assertEqual(self.sets(f), [expected], slot)
            f.toggle_full_screen(); self.assertFalse(f.fullscreen)

    def test_straddling_window_uses_center_monitor(self):
        f = self.two(); f._windowed_location = (1500, 100)                                                       # 1280 x 720 window: center in x = 2140 -> monitor B
        f.set_full_screen(True); self.assertEqual(self.sets(f), ['set_fullscreen(True,screen 2)'])

    def test_full_screen_already_taken_reasks_nothing(self):
        f = self.two(); f.set_full_screen(True); f.logfile.clear(); f.set_full_screen(True); self.assertEqual(f.logfile, [])          # (already in full screen: nothing moves)

    def test_unreadable_monitors_no_crash(self):
        f = self.two()
        def breaks(): raise OSError('plus de moniteurs')
        f.display = types.SimpleNamespace(get_screens=breaks)
        self.assertEqual(f._read_screens(True), ([], [])); self.assertEqual(f._screen_for_fullscreen(), (None, None))
        f.set_full_screen(True); self.assertTrue(f.fullscreen); self.assertEqual(self.sets(f), ['set_fullscreen(True)'])                  # pyglet keeps its monitor

    def test_full_screen_entry_failure_stays_windowed(self):
        f = self.two(); f._windowed_location = (2000, 100); os.environ['DQ_SIM_FAILURE'] = '1'; f.set_full_screen(True)
        self.assertFalse(f.fullscreen); self.assertTrue(f._visible); self.assertEqual((f.win_mode, f.reg['window_mode']), (0, 0))

    def test_return_to_window_no_saved_place_centers_on_fullscreen_monitor(self):
        f = self.two(full=True, screen_page=1); f._note_full_zone(); f.set_full_screen(False)                     # (launched in full screen on B)
        self.assertIn('set_location(%d,%d)' % (1920 + (2560 - 1280) // 2, (1440 - 720) // 2), f.logfile)
        f = self.two(full=True, screen_page=0); f._note_full_zone(); f.set_full_screen(False); self.assertIn('set_location(320,180)', f.logfile)

    def test_return_to_window_if_its_monitor_vanished(self):
        f = self.two(); f.set_full_screen(True)
        f.display = types.SimpleNamespace(get_screens=lambda: [f._screens[1]])                                       # (A unplugged during full screen): only B remains
        f._windowed_location = (100, 80)
        f.logfile.clear(); f.set_full_screen(False)
        self.assertTrue([e for e in f.logfile if e.startswith('set_location')], f.logfile)                         # the window would be off all the monitors: it is recentered

    def test_alt_enter_and_f11_go_through_same_code(self):
        self.assertIs(WND.Game.toggle_full_screen.__code__.co_names.count('set_full_screen') >= 1, True)
        import inspect; src = inspect.getsource(WND.Game._window_shortcut); self.assertIn('toggle_full_screen', src)

    def test_signature_of_pyglet_set_fullscreen(self):
        """The return to windowed mode passes the size through `width` / `height`: the 2nd and 3rd positional arguments of pyglet are the monitor and the mode (the old call `set_fullscreen(False, width_px, height_px)` mixed them up)."""
        import inspect
        p = list(inspect.signature(pyglet.window.BaseWindow.set_fullscreen).parameters)
        self.assertEqual(p[:6], ['self', 'fullscreen', 'screen', 'mode', 'width', 'height'])
        self.assertNotIn('set_fullscreen(False, *size_value)', inspect.getsource(WND.Game._apply_full_screen))




@unittest.skipIf(WND is None, 'window.py non importable ici')
class DisplayPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.menus import pause; cls.PA = pause

    def test_no_more_line_to_choose_monitor(self):
        f = win([A(), B()]); f.mode = 4; f.zoom = 1.0; f.post = types.SimpleNamespace(max_msaa=None); f.resolutions = lambda: [(1280, 720), (1920, 1080)]; f.current_resolution = lambda: (1280, 720)
        f.set_resolution = lambda v: None; f.set_mode = lambda v: None; f.set_distance = lambda v: None
        order = [x['l'] for x in self.PA.Pause(f)._entries_display()]
        self.assertEqual(order[:3], ['settings.language', 'settings.fullscreen', 'settings.brightness']); self.assertNotIn('settings.resolution', order); self.assertFalse([l for l in order if 'monitor' in l], order)
        for name_str in ('valeurs_ecran', 'valeur_ecran', 'nom_ecran', 'ecran_modifiable', 'regler_ecran_plein'): self.assertFalse(hasattr(WND.Game, name_str), name_str)          # (and nothing left in the window to choose it)


if __name__ == '__main__':
    unittest.main(verbosity=1)
