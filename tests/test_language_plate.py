"""Language plate of the start menu (redone): a plate of the port between "License" and "Saves" with a globe, that opens the language screen, where each
language is chosen by its flag; choosing the other one starts the game again in it on its title screen, exactly as the "Language" setting does.

  1. without the engine: the flags and the globe drawn by the port, the plate built in the gap of the game's layout (`ui_layout.json`, DQ_UI_CACHE) with its own number, reached with the
     keys from "License" and "Saves", grayed and dimmed when the other language cannot be loaded; the plate confirmed (A or a click) opens the language screen and never sends anything to
     the engine; on the screen, the other language starts the game again in it (no start-menu option any more), the language being played or the back button close it;
  2. with the real engine (DQ_APK = French APK folder, its English sibling `../en` or DQ_APK_EN, DQ_SAVES, DQ_MAP_CACHE, DQ_UI_CACHE): in a separate process with a hidden window, French start
     menu -> right arrow from "License" -> A -> language screen -> English -> English game, on its title screen.

    python3 tests/test_language_plate.py"""
import glob, json, os, shutil, subprocess, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)


def english_apk():
    if os.environ.get('DQ_APK_EN'): return os.environ['DQ_APK_EN']
    if os.environ.get('DQ_APK'): return os.path.join(os.path.dirname(os.path.normpath(os.environ['DQ_APK'])), 'en')
    return ''


def real_engine_ready():
    fr, en = os.environ.get('DQ_APK', ''), english_apk()
    return all(os.path.isfile(os.path.join(f, 'base.apk')) for f in (fr, en)) and glob.glob(os.path.join(os.environ.get('DQ_SAVES', '/inexistant'), 'data*.dat')) \
        and os.path.isdir(os.environ.get('DQ_MAP_CACHE', '/inexistant'))


if __name__ != '__main__' or not os.environ.get('DQ_PLATE_SCENARIO'):
    import pyglet
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True
    pyglet.options['shadow_window'] = False
    import _paths
    from dq4_pc import main as M
    from dq4_pc.core import engine as ENGINE
    from dq4_pc.menus import flags as FL, ui_menu as UM, language_screen as LS
    from dq4_pc import language as LG
    from dq4_pc.window import constants as C, game as GM
    LAYOUT = os.path.join(_paths.ui_cache(), 'ui_layout.json')

    class Flags(unittest.TestCase):
        def test_french(self):
            a = FL.flag('fr', 60, 40); self.assertEqual(a.shape, (40, 60, 4)); self.assertTrue((a[..., 3] == 255).all())
            self.assertEqual(tuple(a[20, 8, :3]), FL.FR_BLUE); self.assertEqual(tuple(a[20, 30, :3]), FL.FR_WHITE); self.assertEqual(tuple(a[20, 52, :3]), FL.FR_RED)
            self.assertEqual(tuple(a[0, 30, :3]), FL.OUTLINE)                                                           # (thin dark outline)

        def test_union_flag(self):
            a = FL.flag('en', 60, 40)
            self.assertEqual(tuple(a[20, 30, :3]), FL.UK_RED)                                                          # red cross in the middle
            self.assertEqual(tuple(a[4, 24, :3]), FL.UK_WHITE)                                                         # white edge of the upright of the cross
            self.assertEqual(tuple(a[2, 16, :3]), FL.UK_BLUE)                                                         # (corner area between the saltire's arms)
            self.assertEqual(tuple(a[8, 15, :3]), FL.UK_WHITE)                                                         # broad white of the saltire, above its red stripe in the upper hoist
            reds = [(y, x) for y in range(1, 19) for x in range(1, 29) if tuple(a[y, x, :3]) == FL.UK_RED and abs(x - 30) > 6 and abs(y - 20) > 6]
            self.assertTrue(reds and all(y > x * 40 / 60 for y, x in reds), reds[:5])                                  # upper hoist arm: the red stripe is below the diagonal, the broad white uppermost, as on the real flag

        def test_globe(self):
            a = FL.globe(48); self.assertEqual(a.shape, (48, 48, 4))
            self.assertEqual(a[0, 0, 3], 0); self.assertEqual(a[24, 24, 3], 255)                                     # (transparent corners; the center is on the equator)
            self.assertTrue((a[..., :3] == 255).all(), 'white strokes, no colour')
            self.assertEqual(a[30, 28, 3], 0, 'no fill between the strokes')
            self.assertEqual(a[24, 1:4, 3].max(), 255, 'the outline of the planet')

    @unittest.skipUnless(os.path.isfile(LAYOUT), 'no ui_layout.json (DQ_UI_CACHE)')
    class Plate(unittest.TestCase):
        def window(self):
            with open(LAYOUT, encoding='utf-8') as f: d = json.load(f)
            ml = types.SimpleNamespace(types=d['types'], info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0))
            return UM.Window(ml, 53)

        def extent(self, node): return (node['pos'][0] + min(v[0] for v in node['vtx']), node['pos'][0] + max(v[0] for v in node['vtx']))

        def test_in_the_gap_between_licence_and_saves(self):
            w = self.window(); pl = w.language_plate; lic, sav = w._plate(UM.LICENSE_BUTTON), w._plate(8)
            self.assertIsNotNone(pl); self.assertEqual(pl['buttonId'], UM.LANGUAGE_BUTTON); self.assertEqual(C.BTN_LANGUAGE, UM.LANGUAGE_BUTTON)
            (a0, a1), (b0, b1), (c0, c1) = self.extent(lic), self.extent(pl), self.extent(sav)
            self.assertGreater(b0, a1 + 4.0); self.assertLess(b1, c0 - 4.0)                                           # in the gap, not touching
            self.assertAlmostEqual(abs(b0 - a1), abs(c0 - b1), 6)                                                   # exactly between them
            self.assertEqual(pl['pos'][2], lic['pos'][2]); self.assertEqual(max(v[1] for v in pl['vtx'][:36]), max(v[1] for v in lic['vtx']))     # same row, same height
            self.assertIn(UM.LANGUAGE_BUTTON, [b[0] for b in w.buttons()])
            self.assertEqual([m.get('part') for m in pl['mats']], [7, None]); self.assertEqual(pl['mats'][1]['sheet'], 'globe')

        def test_globe_and_gray(self):
            w = self.window(); w.set_language_globe(True)
            self.assertEqual(w.language_plate['mats'][1]['sheet'], 'globe'); self.assertIn(UM.LANGUAGE_BUTTON, [b[0] for b in w.buttons()])
            w.set_language_globe(False)                                                                        # the other language's APK files are missing
            self.assertEqual(w.language_plate['state'], UM.STATE_GRAYED); self.assertNotIn(UM.LANGUAGE_BUTTON, [b[0] for b in w.buttons()])
            self.assertLess(w.language_plate['mats'][1]['color'][0], 1.0)

        def test_reached_with_the_keys(self):
            w = self.window(); z = {b: ((x0 + x1) / 2, (z0 + z1) / 2) for b, pad, x0, z0, x1, z1, _ in w.buttons() if b >= 0 and pad & 0x10}
            self.assertEqual(GM.Game._neighbor(z, UM.LICENSE_BUTTON, ENGINE.RIGHT), UM.LANGUAGE_BUTTON)
            self.assertEqual(GM.Game._neighbor(z, UM.LANGUAGE_BUTTON, ENGINE.RIGHT), 8); self.assertEqual(GM.Game._neighbor(z, 8, ENGINE.LEFT), UM.LANGUAGE_BUTTON)
            self.assertEqual(GM.Game._neighbor(z, UM.LANGUAGE_BUTTON, ENGINE.LEFT), UM.LICENSE_BUTTON)

    class Reg(dict):
        keys = {}
        def action_of(self, s): return self.keys.get(s)

    class Switch(unittest.TestCase):
        def setUp(self): self.lg_before = LG.current_language()
        def tearDown(self): LG.select_language(self.lg_before)

        def game(self, other='en'):
            calls = []
            j = types.SimpleNamespace(game_language='fr', args=types.SimpleNamespace(apk_forced=False), calls=calls, port_screen=None, press_state=None, hover_node=None)
            j.other_game_language = lambda: other
            j.reload_game = lambda language=None, state=None: calls.append(('reload', language, state))
            j._close_port_screen = lambda: setattr(j, 'port_screen', None) or calls.append('closed')
            j.reg = Reg(language='fr'); j.sound = types.SimpleNamespace(play_sfx=lambda n: calls.append(('sfx', n)))
            return j

        def screen(self, j, system='fr'):
            sc = LS.LanguageScreen(j, system_reader=lambda: 'fr_FR' if system == 'fr' else 'en_US'); j.port_screen = sc; return sc

        def test_plate_opens_the_language_screen(self):
            j = self.game(); GM.Game.open_language_screen(j); self.assertIsInstance(j.port_screen, LS.LanguageScreen); self.assertEqual(j.calls, [])
            j = self.game(None); GM.Game.open_language_screen(j); self.assertIsNone(j.port_screen)                     # nothing to choose: nothing opens

        def test_screen_choices(self):
            """a flag = the "Language" setting's change (the tool switches at once, the game starts again when the window closes: see test_restart_when_closed); the back
            button or Esc only close the screen."""
            j = self.game(); sc = self.screen(j)
            self.assertEqual(sc.cur, LS.I_SYSTEM)                                                               # (the checkbox first)
            self.assertTrue(sc.press(1)); self.assertEqual((j.calls, j.reg['language'], LG.current_language(), sc.chosen()), ([], 'en', 'en', 'en'))          # nothing closes, nothing restarts yet
            self.assertEqual(LG.tr('settings.french'), 'French')                                                       # (the names in the language displayed)
            sc.press(LS.I_BACK); self.assertEqual(j.calls, ['closed'])
            j = self.game(); sc = self.screen(j); sc.press(0); self.assertEqual((j.calls, j.reg['language']), ([], 'fr'))
            j = self.game(); sc = self.screen(j); sc.press(LS.I_BACK); self.assertEqual(j.calls, ['closed'])
            j = self.game(); sc = self.screen(j); sc.key_press(pyglet.window.key.ESCAPE); self.assertEqual(j.calls, ['closed'])
            j = self.game(); j.reg.keys = {pyglet.window.key.D: 'right', pyglet.window.key.SPACE: 'A'}
            sc = self.screen(j); sc.key_press(pyglet.window.key.D); sc.key_press(pyglet.window.key.D); self.assertEqual(sc.cur, 1); sc.key_press(pyglet.window.key.SPACE)
            self.assertEqual(j.reg['language'], 'en')
            j = self.game(); sc = self.screen(j); sc.key_press(pyglet.window.key.RIGHT); self.assertEqual(sc.cur, LS.I_SYSTEM)          # (the arrows are no menu keys of their own)

        def test_system_language(self):
            """"System language" checked (the default) grays the flags; unchecked, a flag can be chosen, the cursor on the system's language; checked again from another language, the game
            starts again in the system's one."""
            j = self.game(); j.reg['language'] = 'system'; sc = self.screen(j, system='fr')
            self.assertFalse(sc.press(1)); self.assertEqual(j.calls, [])                                        # (grayed)
            j.reg.keys = {pyglet.window.key.D: 'right'}; sc.key_press(pyglet.window.key.D); self.assertEqual(sc.cur, LS.I_BACK)          # (the flags are skipped)
            sc.press(LS.I_SYSTEM); self.assertEqual((j.reg['language'], sc.cur), ('fr', 0))                     # unchecked: the language played becomes the choice, the cursor on the system's flag
            sc.press(LS.I_SYSTEM); self.assertEqual((j.reg['language'], j.calls), ('system', []))               # (checked again: the system's language is the one played: nothing to restart)
            j = self.game(); j.reg['language'] = 'fr'; sc = self.screen(j, system='en')
            sc.press(LS.I_SYSTEM); self.assertEqual((j.calls, j.reg['language'], sc.chosen()), ([], 'system', 'en'))          # (the restart waits for the window to close)

        def test_restart_when_closed(self):
            """the game starts again in the chosen language only once the language screen is closed (Game._reload_step waits for it, as for the Esc menu)."""
            calls = []; j = types.SimpleNamespace(reload_request=None, pause=types.SimpleNamespace(opened=False), port_screen=object(), on_title=lambda: True,
                                                  language_target=lambda: 'en', game_language='fr', reload_game=lambda: calls.append('reload'))
            self.assertFalse(GM.Game._reload_step(j)); self.assertEqual(calls, [])
            j.port_screen = None; self.assertTrue(GM.Game._reload_step(j)); self.assertEqual(calls, ['reload'])
            j = self.game(); sc = self.screen(j); j.language_pending = lambda: j.reg['language'] != 'fr'; j.toast = lambda t, d=1.8: j.calls.append(('toast', t)); sc.press(1); sc.close()
            self.assertEqual(j.calls, [('toast', 'menus.language_will_change_when_leave'), 'closed', ('reload', None, None)])          # (a notice at the choice; closed from the start menu: the restart is asked at once)
            j.calls.clear(); sc2 = self.screen(j); sc2.press(0); self.assertEqual(j.calls, [])                                    # (back to the language played: no notice)

        def test_never_sent_to_the_engine(self):
            sent = []; j = self.game()
            eng = types.SimpleNamespace(ui=types.SimpleNamespace(f={30: {'order': 1, 'cur': UM.LANGUAGE_BUTTON}}), send_menu=lambda *a: sent.append(a))
            wnd = types.SimpleNamespace(typ=53, buttons=lambda ident=False: [(UM.LANGUAGE_BUTTON, 16, -90.0, -390.0, -30.0, -340.0, 4.0)])
            j.engine = eng; j.ui_g = types.SimpleNamespace(f={30: wnd}); j.cur_local = {(30, 1): UM.LANGUAGE_BUTTON}; j.hover_node = None
            j._is_start_menu = lambda port: True; j.open_language_screen = lambda: j.calls.append('screen')
            j._step_entry = lambda *a: False; j._page_arrow = lambda *a: None; j._port_for_gamepad = lambda port, pad: port; j.menu_to_release = None
            j._neighbor = GM.Game._neighbor
            GM.Game._menu_input(j, 30, ENGINE.A)
            self.assertEqual([c for c in j.calls if c == 'screen'], ['screen']); self.assertEqual(sent, [])

    @unittest.skipUnless(real_engine_ready(), 'real engine: DQ_APK (French), DQ_APK_EN or ../en, DQ_SAVES, DQ_MAP_CACHE')
    class RealEngine(unittest.TestCase):
        def test_plate_switches_to_english_title(self):
            out = tempfile.mkdtemp(prefix='lp_scenario_'); self.addCleanup(shutil.rmtree, out, True)
            env = dict(os.environ, DQ_PLATE_SCENARIO=out, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent')
            p = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__)], env=env, capture_output=True, text=True, timeout=800)
            try:
                with open(os.path.join(out, 'result.json'), encoding='utf-8') as f: r = json.load(f)
            except OSError: self.fail('no result: %s' % (p.stdout[-3000:] + p.stderr[-3000:]))
            log = p.stdout[-3000:]
            self.assertEqual(r.get('main'), 0, log); self.assertEqual(r.get('after_right'), UM.LANGUAGE_BUTTON, log); self.assertEqual(r.get('screen'), 'LanguageScreen', log)
            self.assertEqual(r.get('sent_12'), 0, log)
            self.assertEqual((r.get('lang2'), r.get('setting'), r.get('title2')), ('en', 'en', True), log)          # (on the title screen, as from the setting)


def scenario(out):
    """French start menu -> right from "License" -> A -> language screen -> English -> English title screen (separate process: DQ4_DATA is set before dq4_pc is imported). Writes `result.json` in `out`."""
    import time
    D = os.path.join(out, 'data')
    for sub in ('settings', 'saves/savestates', 'cache', 'cache_en', 'apk'): os.makedirs(os.path.join(D, sub))
    os.symlink(os.path.abspath(os.environ['DQ_APK']), os.path.join(D, 'apk', 'fr')); os.symlink(os.path.abspath(english_apk()), os.path.join(D, 'apk', 'en'))
    for f in glob.glob(os.path.join(os.environ['DQ_SAVES'], 'data*.dat')): shutil.copy(f, os.path.join(D, 'saves'))
    for c in [os.environ['DQ_MAP_CACHE']] + [c for c in (os.environ.get('DQ_UI_CACHE'),) if c and os.path.isdir(c)]:
        for f in os.listdir(c):
            for sub in ('cache', 'cache_en'):
                dst = os.path.join(D, sub, f)
                if sub == 'cache_en' and not f.startswith(('ui_layout', 'map15', 'sprite_', 'world', 'backgrounds', 'fbx4', 'preparation')): continue      # (the English cache: what is the same in both languages, read only)
                if not os.path.exists(dst): os.symlink(os.path.abspath(os.path.join(c, f)), dst)
    with open(os.path.join(D, 'settings', 'settings.json'), 'w') as f: json.dump({'language': 'fr'}, f)
    os.environ['DQ4_DATA'] = D
    sys.path.insert(0, ROOT)
    import pyglet
    from dq4_pc import main as M
    from dq4_pc.core import engine as ENGINE
    games = []; r = {'sent_12': 0}; st = {'k': 0, 'ph': 'title'}; t0 = time.time()
    class G(M.Game):
        def __init__(self, *a, **k):
            q = pyglet.window.Window._enable_event_queue; pyglet.window.Window._enable_event_queue = True          # (headless pyglet: a second window needs the event queue as before the first loop)
            try: super().__init__(*a, **k)
            finally: pyglet.window.Window._enable_event_queue = q
            games.append(self)
    M.Game = G
    def step(dt):
        if time.time() - t0 > 600: r['timeout'] = st['ph']; pyglet.app.exit(); return
        if not games or not getattr(games[-1], '_ready', False): return
        g = games[-1]; st['k'] += 1; k = st['k']; ph = st['ph']
        if not getattr(g.engine, '_watched', False):
            orig = g.engine.send_menu
            def send(port, kind, b, pad, orig=orig):
                if b == 12: r['sent_12'] += 1
                return orig(port, kind, b, pad)
            g.engine.send_menu = send; g.engine._watched = True
        if ph == 'title':
            if k in (300, 360): g.click_a = True
            if k > 420 and g.engine.state.part == ENGINE.PART_INITIAL and g.engine.active_menu() is not None: st.update(ph='nav', k=0)
        elif ph == 'nav':
            port = g.engine.active_menu(); f = g.engine.ui.f[port]; key = (port, f['order'])
            if k == 10: g.cur_local[key] = 11
            if k == 20: g._menu_input(port, ENGINE.RIGHT); r['after_right'] = g.cur_local[key]
            if k == 30: g._menu_input(port, ENGINE.A); r['screen'] = type(g.port_screen).__name__
            if k == 40 and g.port_screen is not None: g.port_screen.press(1); g.port_screen.close(); st.update(ph='en', k=0)          # (the game restarts when the window closes)
        elif ph == 'en':
            if len(games) < 2: return
            if g.title_screen is not None:
                st['seen'] = st.get('seen', k)
                if k > st['seen'] + 60:
                    r.update(lang2=g.game_language, setting=g.reg['language'], title2=g.title_screen is not None and g.engine.state.part == ENGINE.PART_TOWN); pyglet.app.exit()
    run = pyglet.app.run
    def run_with_scenario(**kw):
        if not st.get('scheduled'): st['scheduled'] = True; pyglet.clock.schedule(step)
        run(**kw)
    pyglet.app.run = run_with_scenario
    r['main'] = M.main(['--no-sound', '--msaa', '0', '--width', '1280', '--height', '720', '--no-logos', '--images', '100000', '--shot', os.path.join(out, 'x.png'), '--history', os.path.join(out, 'fav.json')])
    with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f: json.dump(r, f)


if __name__ == '__main__':
    if os.environ.get('DQ_PLATE_SCENARIO'): scenario(os.environ['DQ_PLATE_SCENARIO'])
    else: unittest.main()
