"""Test of the "Menu" key (field menu: Objets / Magie / Carac. / Divers): default Enter and Tab, migration of an old reglages.json (without overwriting a player's choice), Tab free elsewhere, line of the "Controls" page
and ↺ button (real code of settings.py, of pause.py and, without a window, of Game.on_key_press / _edges).

    python3 tests/test_menu_key.py
"""
import glob, json, os, re, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.persistence import settings as RG
import test_pause_pages as TP

K = pyglet.window.key


def load(content):
    f = os.path.join(tempfile.mkdtemp(prefix='rg_menu_'), 'settings.json')
    with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
    return RG.Settings(f), f


class Default(unittest.TestCase):
    def test_enter_and_tab(self):
        self.assertEqual(RG.DEFAULT_KEYS['menu'], ['RETURN', 'TAB']); self.assertEqual(RG.Settings(None)['keys']['menu'], ['RETURN', 'TAB'])
        r = RG.Settings(None)
        self.assertEqual(r.action_of(K.TAB), 'menu'); self.assertEqual(r.codes('menu')[:2], (K.RETURN, K.TAB))          # (action_of(K.RETURN) is None: pyglet names 0xff0d "ENTER"; the game reads keys through `codes`, see Game._held)
        self.assertEqual(dict(RG.ACTIONS)['menu'], 'settings.menu')

    def test_tab_belongs_to_no_other_action(self):
        for a, ts in RG.DEFAULT_KEYS.items():
            if a != 'menu': self.assertNotIn('TAB', ts, a)
        self.assertNotIn('TAB', RG.RESERVED); self.assertNotIn('RETURN', RG.RESERVED)
        every = [n for ts in RG.DEFAULT_KEYS.values() for n in ts if n]
        self.assertEqual(len(every), len(set(every)), 'a key serves only one action')

    def test_tab_elsewhere_in_the_code(self):
        """The only uses of Tab (K.TAB): collapsing the interface editor's panel (Pause menu), changing mode in name entry, moving to the next button of the Saves screen. These three screens
        take the key in Game.on_key_press BEFORE the game's actions (Pause menu open, name entry, Saves screen): Tab is never the "Menu" key there. A new use must be examined here."""
        here = os.path.join(HERE, '..', 'dq456_pc'); found_set = set()
        for f in glob.glob(os.path.join(here, '**', '*.py'), recursive=True):
            with open(f, encoding='utf-8') as fh:
                if re.search(r'\bK\.TAB\b', fh.read()): found_set.add(os.path.basename(f))
        self.assertEqual(found_set, {'pause.py', 'name_entry.py', 'saves_screen.py', 'language_screen.py'})


class Migration(unittest.TestCase):
    def test_old_default_receives_tab(self):
        for v in (3, 4):
            r, _ = load({'keys_version': v, 'keys': {'menu': ['RETURN', None], 'map': ['M', None], 'A': ['SPACE', None]}})
            self.assertEqual(r['keys']['menu'], ['RETURN', 'TAB'], 'keys_version %d' % v)
        r, _ = load({'keys_version': 4, 'keys': {k: list(v) for k, v in RG.DEFAULT_KEYS.items() if k != 'menu'} | {'menu': ['RETURN']}}); self.assertEqual(r['keys']['menu'], ['RETURN', 'TAB'])       # (single-key list)
        r, _ = load({'keys_version': 4, 'keys': {k: list(v) for k, v in RG.DEFAULT_KEYS.items()} | {'menu': ['RETURN', None]}}); self.assertEqual(r['keys']['menu'], ['RETURN', 'TAB'])      # (full file from before)

    def test_player_choice_kept(self):
        for menu in (['E', None], ['RETURN', 'F2'], ['F2', None], [None, None], ['SPACE', 'RETURN'], [None, 'RETURN'], ['E', 'RETURN']):
            r, _ = load({'keys_version': 4, 'keys': {'menu': list(menu), 'A': ['SPACE', None]}}); self.assertEqual(r['keys']['menu'], menu, menu)

    def test_tab_already_taken_by_another_action(self):
        r, _ = load({'keys_version': 4, 'keys': {'menu': ['RETURN', None], 'info': ['TAB', None]}})
        self.assertEqual(r['keys']['menu'], ['RETURN', None]); self.assertEqual(r['keys']['info'], ['TAB', None]); self.assertEqual(r.action_of(K.TAB), 'info')      # the player's choice takes precedence

    def test_only_once(self):
        """After the migration the file is saved as v5: Tab later removed by the player (slot cleared) is not put back."""
        r, f = load({'keys_version': 4, 'keys': {'menu': ['RETURN', None]}}); r.store()
        with open(f, encoding='utf-8') as fh: d = json.load(fh)
        self.assertEqual((d['keys_version'], d['keys']['menu']), (RG.DEFAULT['keys_version'], ['RETURN', 'TAB']))
        r2 = RG.Settings(f); r2.unbind('menu', 1); r2.store()
        self.assertEqual(RG.Settings(f)['keys']['menu'], ['RETURN', None])
        r3, _ = load({'keys_version': 5, 'keys': {'menu': ['RETURN', None]}}); self.assertEqual(r3['keys']['menu'], ['RETURN', None])

    def test_files_without_keys_or_too_old(self):
        for content in ({}, {'sound': False}, {'keys_version': 2, 'keys': {'menu': ['RETURN', None]}}, {'keys': {'menu': ['RETURN', None]}}):
            r, _ = load(content); self.assertEqual(r['keys']['menu'], ['RETURN', 'TAB'], content)                      # (keys dropped or missing: the defaults)

    def test_other_keys_do_not_move(self):
        r, _ = load({'keys_version': 4, 'keys': {'menu': ['RETURN', None], 'up': ['W', None], 'map': ['N', None]}})
        self.assertEqual((r['keys']['up'], r['keys']['map']), (['W', None], ['N', None])); self.assertNotIn('history', r['keys'])          # (no more History key)


class CommandsPage(unittest.TestCase):
    def test_default_line_and_button(self):
        J, p = TP.menu('controls'); e = TP.by_caption(p, 'settings.menu')
        self.assertEqual((e['t'], e['act'], e['v']), ('key', 'menu', ['settings.enter', 'Tab', 'PAD_Y'])); self.assertTrue(e['is_default']())
        J.reg.bind('menu', 1, K.F2); J.reg.bind('menu', 0, K.E)
        e = TP.by_caption(p, 'settings.menu'); self.assertEqual(e['v'], ['E', 'F2', 'PAD_Y']); self.assertFalse(e['is_default']())
        e['default'](); e = TP.by_caption(p, 'settings.menu')                                                          # ↺: both keys come back
        self.assertEqual((e['v'], J.reg['keys']['menu']), (['settings.enter', 'Tab', 'PAD_Y'], ['RETURN', 'TAB'])); self.assertTrue(e['is_default']())

    def test_default_takes_tab_from_other_action(self):
        J, p = TP.menu('controls'); J.reg.bind('info', 0, K.TAB)                                            # Tab given to "Info": "Menu" only has Enter left
        self.assertEqual(J.reg['keys']['menu'], ['RETURN', None]); e = TP.by_caption(p, 'settings.menu'); self.assertFalse(e['is_default']())
        e['default'](); self.assertEqual(J.reg['keys']['menu'], ['RETURN', 'TAB']); self.assertEqual(J.reg['keys']['info'], [None, None])      # ↺ takes Tab back (and says so: message)
        self.assertIn('settings.screen_info', p.message[4])
        J.reg.bind('menu', 0, K.F3); J.reg.default_keys(); self.assertEqual(J.reg['keys']['menu'], ['RETURN', 'TAB'])         # "Restore default keys" too

    def test_tab_key_capture(self):
        """Binding Tab to "Menu" in the "Controls" page (secondary slot): key capture takes Tab like any other key."""
        J, p = TP.menu('controls'); J.reg.unbind('menu', 1)
        p.capture = ('menu', 1, False); p.key_press(K.TAB, 0); self.assertEqual(J.reg['keys']['menu'], ['RETURN', 'TAB']); self.assertIsNone(p.capture)

    def test_tab_folds_the_editor_panel(self):
        """In the interface editor, Tab collapses the panel (it triggers nothing else); outside the editor, Tab does nothing in the Pause menu."""
        J, p = TP.menu('interface'); self.assertFalse(p.folded)
        p.key_press(K.TAB, 0); self.assertTrue(p.folded); p.key_press(K.TAB, 0); self.assertFalse(p.folded)
        J, p = TP.menu('display'); before = dict(p.selected); p.key_press(K.TAB, 0); self.assertEqual((p.screen_page, p.selected), ('display', before))


class InWindow(unittest.TestCase):
    """Real code of Game.on_key_press / _edges on a fake Game (like test_window_mode.py)."""
    @classmethod
    def setUpClass(cls):
        try: from dq456_pc.window import game as window; cls.WND = window
        except Exception as ex: raise unittest.SkipTest('window.py non importable ici (%r)' % (ex,))

    def fake_game(self, pause=False, name_str=False):
        WND = self.WND
        j = types.SimpleNamespace(swallowed=set(), alt_cand=False, alt_tap=False, reg=RG.Settings(None), key_list=K.KeyStateHandler(), prev_action={}, n=0, _ready=True, combo=[False, False], _logo_touched=False, pause_presses=0, name_presses=0,
                                  pause=None, port_screen=None, license_panel=None, title_screen=None, last_device='', bascules=0, cancellations=0, is_fullscreen=False, mouse=(0, 0), mouse_guard=__import__('dq456_pc.window.inputs', fromlist=['MouseGuard']).MouseGuard(), helptext=False)
        j.pause = types.SimpleNamespace(opened=pause, capture=None, last_page=lambda: 'display', key_press=lambda sym, mods: setattr(j, 'pause_presses', j.pause_presses + 1))
        j.name_entry = types.SimpleNamespace(key_press=lambda sym, mods: setattr(j, 'name_presses', j.name_presses + 1))
        j.toggle_full_screen = lambda: setattr(j, 'bascules', j.bascules + 1)
        j._held = lambda a: WND.Game._held(j, a); j._name_entry_in_progress = lambda: name_str; j._state_number = WND.Game._state_number; j._window_shortcut = lambda sym, mods: WND.Game._window_shortcut(j, sym, mods)
        j.cancel_loading = lambda: None
        return j

    def press_state(self, j, sym):
        j.key_list.on_key_press(sym, 0); return self.WND.Game.on_key_press(j, sym, 0)

    def test_tab_as_enter_on_the_field(self):
        for sym in (K.RETURN, K.TAB):
            j = self.fake_game(); self.press_state(j, sym); self.assertTrue(self.WND.Game._edges(j)['menu'], sym)                # one press = one "Menu" edge (opens the field menu, confirms, turns the message pages)
            j.key_list.on_key_release(sym, 0); self.assertFalse(self.WND.Game._edges(j)['menu'])
        j = self.fake_game(); self.press_state(j, K.TAB); self.press_state(j, K.RETURN); self.assertTrue(self.WND.Game._edges(j)['menu']); self.assertFalse(self.WND.Game._edges(j)['menu'])          # both together: a single edge

    def test_tab_taken_before_actions_in_menu_and_name_entry(self):
        j = self.fake_game(pause=True); self.press_state(j, K.TAB); self.assertEqual(j.pause_presses, 1)                    # Pause menu: the key belongs to it
        j = self.fake_game(name_str=True); self.press_state(j, K.TAB); self.assertEqual(j.name_presses, 1)                         # name entry: Tab changes mode (name_entry.py)
        j = self.fake_game(); j.port_screen = types.SimpleNamespace(key_press=lambda sym, mods: setattr(j, 'name_presses', 7)); self.press_state(j, K.TAB); self.assertEqual(j.name_presses, 7)      # Saves screen: next button
        from dq456_pc.persistence import pad_inputs as PI
        got = []; j = self.fake_game(); j.port_screen = types.SimpleNamespace(key_press=lambda sym, mods: got.append(sym)); self.press_state(j, PI.SYMBOL['PAD_UP'])
        self.assertEqual(got, [PI.SYMBOL['PAD_UP']]); self.assertEqual(j.reg.action_of(got[0]), 'up')          # (the port screens get the input itself and read its action, no arrow in between)

    def test_esc_menu_only_when_free(self):
        """Esc opens the Esc menu only when the player moves freely; elsewhere (battle, message, scene, title) it does nothing (or Cancel in a game window, _esc_back)."""
        for free, opened in ((True, 1), (False, 0)):
            j = self.fake_game(); j.opened = 0; j.pause.open_menu = lambda **kw: setattr(j, 'opened', j.opened + 1); j._esc_back = lambda: False; j.history_possible = lambda: free
            self.press_state(j, K.ESCAPE); self.assertEqual(j.opened, opened, free)
        j = self.fake_game(); j.opened = 0; j.pause.open_menu = lambda **kw: setattr(j, 'opened', 1); j._esc_back = lambda: True; j.history_possible = lambda: True
        self.press_state(j, K.ESCAPE); self.assertEqual((j.opened, j.click_b), (0, True))          # (a game window: Esc = Cancel)


if __name__ == '__main__':
    unittest.main(verbosity=1)
