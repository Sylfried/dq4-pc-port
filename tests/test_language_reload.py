"""Game language changed in the game: the game's APK files follow the "Language" setting and are read when the game starts, so changing the language starts the game again, in the same process,
on the title screen of the new language; a savestate of the other language offers to switch the game to that language and loads it.

  1. without APK (fakes): the fingerprint check (`savestates.check`, `OtherEngine`, `OtherLanguage`: nothing is written into the engine), `load_state` telling a state of the other language from one of another
     update, `state_language`, the language asked for by the setting (`Game.language_target`, `language_pending`, forced `--apk`), the reload only on the title screen with the Esc menu closed (`_reload_step`),
     what `reload_game` keeps (size, position, state to load, setting), the state loaded at the first loop of the new game, the arguments of the new game (`main.args_for_restart`, `choose_game_files`);
  2. with the real engine (DQ_APK = French APK folder, its English sibling `../en` or DQ_APK_EN, DQ_SAVES, DQ_MAP_CACHE, DQ_UI_CACHE): the whole sequence in a separate process with a hidden window:
     French game, setting switched to English (nothing happens away from the title screen), return to the title screen -> English game on its title screen (English APK and cache, the old engine
     released, same window size), French state refused with OtherLanguage('fr'), reload_game('fr', 1) -> French game with the state loaded.

    python3 tests/test_language_reload.py"""
import glob, json, os, shutil, subprocess, sys, tempfile, time, types, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)


def english_apk():
    """English APK folder for the real-engine scenario: DQ_APK_EN, otherwise the `en` sibling of DQ_APK (data\\apk\\fr -> data\\apk\\en)."""
    if os.environ.get('DQ_APK_EN'): return os.environ['DQ_APK_EN']
    if os.environ.get('DQ_APK'): return os.path.join(os.path.dirname(os.path.normpath(os.environ['DQ_APK'])), 'en')
    return ''


def real_engine_ready():
    fr, en = os.environ.get('DQ_APK', ''), english_apk()
    return all(os.path.isfile(os.path.join(f, 'base.apk')) for f in (fr, en)) and glob.glob(os.path.join(os.environ.get('DQ_SAVES', '/inexistant'), 'data*.dat')) \
        and os.path.isdir(os.environ.get('DQ_MAP_CACHE', '/inexistant'))


if __name__ != '__main__' or not os.environ.get('DQ_RELOAD_SCENARIO'):
    import pyglet
    pyglet.options['shadow_window'] = False
    import _paths
    from dq456_pc import language as LG, main as M
    from dq456_pc.persistence import savestates as SS
    from dq456_pc.window import game as GM, snapshots as SN


    def fake_engine(img=b'library image'):
        writes = []
        uc = types.SimpleNamespace(mem_write=lambda *a: writes.append(a))
        return types.SimpleNamespace(core=types.SimpleNamespace(elf=types.SimpleNamespace(img=img, size=len(img)), uc=uc, LIB_BASE=0)), writes


    class Fingerprint(unittest.TestCase):
        def test_check(self):
            m, _ = fake_engine(); sha = SS.lib_fingerprint(m.core)
            SS.check(m, {}); SS.check(m, {'lib_sha': None}); SS.check(m, {'lib_sha': sha})              # (states: no fingerprint, accepted)
            with self.assertRaises(SS.OtherEngine) as c: SS.check(m, {'lib_sha': '0123456789abcdef'})
            self.assertEqual(c.exception.lib_sha, '0123456789abcdef'); self.assertNotIsInstance(c.exception, SS.OtherLanguage)
            self.assertTrue(issubclass(SS.OtherLanguage, SS.OtherEngine) and issubclass(SS.OtherEngine, ValueError))          # (the callers that caught ValueError still catch it)
            ex = SS.OtherLanguage('abcd', 'en'); self.assertEqual((ex.lib_sha, ex.language), ('abcd', 'en'))

        def test_apply_refuses_before_writing(self):
            m, writes = fake_engine()
            with self.assertRaises(SS.OtherEngine): SS.apply(m, {'version': SS.VERSION, 'lib_sha': 'ffff'})
            self.assertEqual(writes, [])

        def test_apk_fingerprint_without_files(self):
            self.assertIsNone(SS.apk_fingerprint(tempfile.mkdtemp(prefix='lr_vide_')))


    class FakeSnapshots:
        game_language = 'en'; engine = object()
        def __init__(self, languages=None): self.applied = []; self.undo_state = 'avant'; self.languages = languages or {}
        def state_path(self, n): return 'etat_%d' % n
        def _complete_savestate(self): return 'courant'
        def _apply_savestate(self, d): self.applied.append(d)
        def state_language(self, sha): return self.languages.get(sha)


    class LoadState(unittest.TestCase):
        def load(self, j, refused=True):
            d = {'lib_sha': 'aaaa'}
            with mock.patch.object(SN.SS, 'read', return_value=d), mock.patch.object(SN.SS, 'check', side_effect=SS.OtherEngine('aaaa') if refused else None):
                SN.SnapshotsMixin.load_state(j, 2)
            return d

        def test_state_of_the_other_language(self):
            j = FakeSnapshots({'aaaa': 'fr'})
            with self.assertRaises(SS.OtherLanguage) as c: self.load(j)
            self.assertEqual(c.exception.language, 'fr'); self.assertEqual(j.applied, []); self.assertEqual(j.undo_state, 'avant')          # (nothing touched)

        def test_state_of_another_update_or_unknown(self):
            for languages in ({'aaaa': 'en'}, {}):                                         # the loaded language's fingerprint is not the state's: another update of the APK files, not a language question
                j = FakeSnapshots(languages)
                with self.assertRaises(SS.OtherEngine) as c: self.load(j)
                self.assertNotIsInstance(c.exception, SS.OtherLanguage); self.assertEqual(j.applied, [])

        def test_same_engine_loads(self):
            j = FakeSnapshots(); d = self.load(j, refused=False)
            self.assertEqual(j.applied, [d]); self.assertEqual(j.undo_state, 'courant')

        def test_state_language(self):
            t = tempfile.mkdtemp(prefix='lr_apk_'); self.addCleanup(shutil.rmtree, t, True)
            for lg in ('fr', 'en'): os.makedirs(os.path.join(t, lg)); open(os.path.join(t, lg, 'base.apk'), 'w').close()
            folders = types.SimpleNamespace(apk_for=lambda lg: os.path.join(t, lg)); prints = {os.path.join(t, 'fr'): '1111', os.path.join(t, 'en'): '2222'}
            with mock.patch.object(SN.CH, 'FOLDERS', folders), mock.patch.object(SN.SS, 'apk_fingerprint', side_effect=lambda f: prints[f]):
                j = types.SimpleNamespace()
                self.assertEqual(SN.SnapshotsMixin.state_language(j, '2222'), 'en'); self.assertEqual(SN.SnapshotsMixin.state_language(j, '1111'), 'fr')
                self.assertIsNone(SN.SnapshotsMixin.state_language(j, '3333'))
                os.remove(os.path.join(t, 'en', 'base.apk')); self.assertIsNone(SN.SnapshotsMixin.state_language(j, '2222'))           # (APK files of that language not there)


    class FakeGame:
        def __init__(self, game_language='fr', forced=False):
            self.game_language = game_language; self.args = types.SimpleNamespace(apk_forced=forced, reload_state=None); self.reg = {'language': game_language}
            self.pause = types.SimpleNamespace(opened=False); self.reload_request = None; self.title = True; self.calls = []; self.toasts = []
            self.is_fullscreen = False; self.width, self.height = 1600, 900; self.window_size = (2560, 1440)
        def language_target(self): return GM.Game.language_target(self)
        def on_title(self): return self.title
        def reload_game(self, *a): self.calls.append(('reload',) + a)
        def quit_game(self): self.calls.append('quit')
        def get_location(self): return (40, 60)
        def load_state(self, n): self.calls.append(('load', n))
        def toast(self, t): self.toasts.append(t)
        def _note_state_failure(self, *a): self.calls.append(('failure', a[0]))


    class Reload(unittest.TestCase):
        def setUp(self): LG.select_language('fr'); self.addCleanup(LG.select_language, 'fr')

        def folders(self, only=None):
            """Fake folders: choose_apk falls back on the other language when only `only` has its files."""
            return types.SimpleNamespace(choose_apk=lambda lg: ('apk_' + (only or lg), only or lg))

        def test_language_target_and_pending(self):
            j = FakeGame('fr')
            with mock.patch.object(GM.CH, 'FOLDERS', self.folders()):
                self.assertEqual(GM.Game.language_target(j), 'fr'); self.assertFalse(GM.Game.language_pending(j))
                LG.select_language('en'); self.assertEqual(GM.Game.language_target(j), 'en'); self.assertTrue(GM.Game.language_pending(j))
            with mock.patch.object(GM.CH, 'FOLDERS', self.folders(only='fr')): self.assertFalse(GM.Game.language_pending(j))          # (no English APK files: the game stays French, nothing to reload)
            j = FakeGame('fr', forced=True)
            with mock.patch.object(GM.CH, 'FOLDERS', self.folders()): self.assertFalse(GM.Game.language_pending(j))                    # (--apk forced: tests, special installations)

        def test_reload_only_on_the_title_with_the_menu_closed(self):
            with mock.patch.object(GM.CH, 'FOLDERS', self.folders()):
                j = FakeGame('fr'); self.assertFalse(GM.Game._reload_step(j)); self.assertEqual(j.calls, [])               # same language: nothing
                LG.select_language('en')
                j = FakeGame('fr'); j.title = False; self.assertFalse(GM.Game._reload_step(j)); self.assertEqual(j.calls, [])  # away from the title screen: waits
                j = FakeGame('fr'); j.pause.opened = True; self.assertFalse(GM.Game._reload_step(j)); self.assertEqual(j.calls, [])     # menu open: waits for it to close
                j = FakeGame('fr'); self.assertTrue(GM.Game._reload_step(j)); self.assertEqual(j.calls, [('reload',)])
                j = FakeGame('fr'); j.reload_request = {}; self.assertTrue(GM.Game._reload_step(j)); self.assertEqual(j.calls, [])        # already closing

        def test_reload_game_keeps_size_position_and_state(self):
            j = FakeGame('fr'); GM.Game.reload_game(j)
            self.assertEqual(j.reload_request, {'state': None, 'size': (1600, 900), 'location': (40, 60)}); self.assertEqual(j.calls, ['quit']); self.assertEqual(j.reg['language'], 'fr')
            j = FakeGame('en'); j.is_fullscreen = True; GM.Game.reload_game(j, 'fr', 3)
            self.assertEqual(j.reload_request, {'state': 3, 'size': (2560, 1440), 'location': None}); self.assertEqual(j.reg['language'], 'fr'); self.assertEqual(LG.current_language(), 'fr')
            j = FakeGame('fr'); j.get_location = lambda: None; GM.Game.reload_game(j, 'en')                          # (no position known: the system places the window)
            self.assertIsNone(j.reload_request['location']); self.assertEqual(LG.current_language(), 'en')

        def test_state_loaded_at_the_first_loop(self):
            j = FakeGame('fr'); j.args.reload_state = 4; GM.Game._load_after_reload(j)
            self.assertEqual(j.calls, [('load', 4)]); self.assertEqual(j.toasts, ['État 4 chargé']); self.assertIsNone(j.args.reload_state)
            j = FakeGame('fr'); j.args.reload_state = 2; j.load_state = lambda n: (_ for _ in ()).throw(OSError('disque'))
            GM.Game._load_after_reload(j); self.assertEqual(j.calls, [('failure', "Chargement de l'état 2")]); self.assertIsNone(j.args.reload_state)

        def args(self, **kw):
            a = types.SimpleNamespace(apk_forced=False, cache_forced=False, apk='apk_fr', cache='cache_fr', game_language='fr', hd=0, msaa=0, full_screen=0, music_volume=0, sfx_volume=0,
                                      width_px=1280, height_px=720, no_logos=False, logos=True, slot=2, reload_state=None, reload_location=None)
            for k, v in kw.items(): setattr(a, k, v)
            return a

        def test_args_for_restart(self):
            t = tempfile.mkdtemp(prefix='lr_dossiers_'); self.addCleanup(shutil.rmtree, t, True)
            d = types.SimpleNamespace(choose_apk=lambda lg: (os.path.join(t, 'apk', lg), lg), apk_for=lambda lg: os.path.join(t, 'apk', lg), cache=os.path.join(t, 'cache'),
                                      cache_for=lambda lg: os.path.join(t, 'cache_en' if lg == 'en' else 'cache'))
            reg = {'sprite_mode': 1, 'msaa': 4, 'window_mode': 0, 'music_volume': 70, 'sfx_volume': 60, 'resolution': [1920, 1080]}
            LG.select_language('en')
            a = M.args_for_restart(self.args(), reg, d, {'state': 3, 'size': (1600, 900), 'location': (10, 20)})
            self.assertEqual((a.apk, a.game_language, a.cache), (os.path.join(t, 'apk', 'en'), 'en', os.path.join(t, 'cache_en')))
            self.assertEqual((a.width_px, a.height_px, a.reload_location, a.reload_state), (1600, 900, (10, 20), 3))
            self.assertEqual((a.no_logos, a.logos, a.slot), (True, False, 0))                        # (no entry logos, no direct start on a save)
            self.assertEqual((a.hd, a.msaa, a.full_screen, a.music_volume, a.sfx_volume), (1, 4, 0, 70, 60))   # (the settings as they are now)
            a = M.args_for_restart(self.args(), dict(reg, resolution='damaged'), d, {'state': None})
            self.assertEqual((a.width_px, a.height_px, a.reload_location, a.reload_state), (1920, 1080, None, None))
            a = M.args_for_restart(self.args(), reg, d, {})
            self.assertEqual((a.width_px, a.height_px), (1920, 1080))
            a = M.args_for_restart(self.args(apk_forced=True, cache_forced=True, apk='mes_apk', cache='mon_cache'), reg, d, {})
            self.assertEqual((a.apk, a.cache, a.game_language), ('mes_apk', 'mon_cache', 'en'))   # (--apk / --cache kept)

        def test_redrawing_scheduled_once_per_game(self):
            """pyglet.app.run(interval=0) schedules the redrawing of the windows at each call and never removes it; `main.run_loop` removes it when the loop stops, so a game started again
            (language change, savestate of the other language) draws each frame once, not twice, three times..."""
            import pyglet
            loop = pyglet.app.event_loop
            count = lambda: sum(1 for it in pyglet.clock.get_default()._schedule_items if it.func == loop._redraw_windows)
            seen = []
            for _ in range(3):
                pyglet.clock.schedule_once(lambda dt: (seen.append(count()), pyglet.app.exit()), 0)
                M.run_loop()
            self.assertEqual(seen, [1, 1, 1]); self.assertEqual(count(), 0)

        def test_background_tasks_of_the_closed_game_stop(self):
            from concurrent.futures import ThreadPoolExecutor
            import threading
            gate = threading.Event(); ran = []
            pool = ThreadPoolExecutor(max_workers=1); first = pool.submit(gate.wait, 5); queued = pool.submit(ran.append, 1)
            M.release_workers(types.SimpleNamespace(pool=pool)); gate.set(); first.result(5); pool.shutdown(wait=True)
            self.assertTrue(queued.cancelled()); self.assertEqual(ran, [])
            M.release_workers(types.SimpleNamespace())                                  # (a game without a pool: nothing to do)


    @unittest.skipUnless(real_engine_ready(), 'real engine: DQ_APK (French), DQ_APK_EN or ../en, DQ_SAVES, DQ_MAP_CACHE')
    class RealEngine(unittest.TestCase):
        def test_language_change_and_state_of_the_other_language(self):
            out = tempfile.mkdtemp(prefix='lr_scenario_'); self.addCleanup(shutil.rmtree, out, True)
            env = dict(os.environ, DQ_RELOAD_SCENARIO=out, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent')
            p = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__)], env=env, capture_output=True, text=True, timeout=800)
            try:
                with open(os.path.join(out, 'result.json'), encoding='utf-8') as f: r = json.load(f)
            except OSError: self.fail('no result: %s' % (p.stdout[-3000:] + p.stderr[-3000:]))
            log = p.stdout[-3000:]
            self.assertEqual(r.get('main'), 0, log)
            self.assertEqual(r['game1'], 'fr', log); self.assertTrue(r['pending']); self.assertFalse(r['on_title_1'])
            self.assertEqual(r['games_while_away'], 1, log)                          # (away from the title screen: no reload)
            self.assertEqual(r['game2'], 'en', log); self.assertTrue(r['on_title_2'], log); self.assertTrue(r['apk2'].endswith('en'), log); self.assertTrue(r['cache2'].endswith(os.path.join('cache', 'dq4', 'en')), log)
            self.assertFalse(r['engine1_alive'], log); self.assertEqual(r['size2'], [1280, 720], log)
            self.assertEqual(r['refused'], 'fr', log)
            self.assertEqual(r['game3'], 'fr', log); self.assertEqual(r['setting3'], 'fr', log)
            self.assertEqual([r['map3'], r['part3']], [r['map1'], r['part1']], log); self.assertIsNone(r['reload_state3'], log)
            self.assertEqual(r['games'], 3, log)
            self.assertEqual((r['redraws2'], r['redraws3']), (1, 1), log)                 # (each game started again draws its frames once)


def scenario(out):
    """The real-engine sequence (separate process: DQ_DATA must be set before dq456_pc is imported). Writes `result.json` in `out`."""
    D = os.path.join(out, 'data')
    for sub in ('settings', 'saves/dq4/savestates', 'cache/dq4/fr', 'cache/dq4/en', 'apk/dq4'): os.makedirs(os.path.join(D, sub))
    os.symlink(os.path.abspath(os.environ['DQ_APK']), os.path.join(D, 'apk', 'dq4', 'fr')); os.symlink(os.path.abspath(english_apk()), os.path.join(D, 'apk', 'dq4', 'en'))
    for f in glob.glob(os.path.join(os.environ['DQ_SAVES'], 'data*.dat')): shutil.copy(f, os.path.join(D, 'saves', 'dq4'))
    caches = [os.environ['DQ_MAP_CACHE']] + [c for c in (os.environ.get('DQ_UI_CACHE'),) if c and os.path.isdir(c)]
    for c in caches:
        for f in os.listdir(c):
            dst = os.path.join(D, 'cache', 'dq4', 'fr', f)
            if not os.path.exists(dst): os.symlink(os.path.abspath(os.path.join(c, f)), dst)          # (read only: the French cache is ready, nothing is written there)
    with open(os.path.join(D, 'settings', 'settings.json'), 'w') as f: json.dump({'language': 'fr'}, f)
    os.environ['DQ_DATA'] = D
    sys.path.insert(0, ROOT)
    import gc, weakref
    import pyglet
    from dq456_pc import main as M, language as LG
    from dq456_pc.persistence import savestates as SS
    argv = ['--slot', '4', '--no-sound', '--msaa', '0', '--width', '1280', '--height', '720', '--no-logos', '--images', '100000', '--shot', os.path.join(out, 'x.png'), '--history', os.path.join(out, 'fav.json')]
    games = []; refs = []; r = {}; st = {'phase': 'fr_wait', 'k': 0}; t0 = time.time()
    class G(M.Game):
        def __init__(self, *a, **k):
            queued = pyglet.window.Window._enable_event_queue; pyglet.window.Window._enable_event_queue = True          # (headless pyglet: a second window needs the event queue as before the first loop; not the case under Windows)
            try: super().__init__(*a, **k)
            finally: pyglet.window.Window._enable_event_queue = queued
            games.append(self); refs.append(weakref.ref(self.engine))
    M.Game = G
    def say(*a): print('[%.0fs]' % (time.time() - t0), *a, flush=True)
    def redraws(): return sum(1 for it in pyglet.clock.get_default()._schedule_items if it.func == pyglet.app.event_loop._redraw_windows)          # (one per running game)
    def step(dt):
        if time.time() - t0 > 600: say('too long:', st['phase']); pyglet.app.exit(); return
        if not games or not getattr(games[-1], '_ready', False): return
        while len(games) > 1: games.pop(0)
        g = games[-1]; st['k'] += 1; k = st['k']; p = st['phase']
        if p == 'fr_wait':
            if g.n_loop < 200: return
            r['game1'] = g.game_language; r['map1'] = g.engine.state.game_map; r['part1'] = g.engine.state.part
            g.save_state(1); g.reg['language'] = 'en'; LG.select_language('en')
            r['pending'] = g.language_pending(); r['on_title_1'] = g.on_title(); say('game 1', r); st.update(phase='fr_hold', k=0)
        elif p == 'fr_hold':
            if k == 90: r['games_while_away'] = len(refs); g.back_to_title(); st.update(phase='fr_title', k=0)
        elif p == 'fr_title':
            if g.engine.back_to_title_state == 'dialog' and k % 8 == 0: g.click_a = True
            if k > 900: say('no reload'); pyglet.app.exit()
            if len(refs) == 2: st.update(phase='en_wait', k=0)
        elif p == 'en_wait':
            if k < 120: return
            r.update(game2=g.game_language, on_title_2=g.on_title(), apk2=os.path.normpath(g.args.apk), cache2=os.path.normpath(g.args.cache), size2=[g.width, g.height], redraws2=redraws())
            gc.collect(); r['engine1_alive'] = refs[0]() is not None
            try: g.load_state(1); r['refused'] = None
            except SS.OtherLanguage as ex: r['refused'] = ex.language
            except Exception as ex: r['refused'] = repr(ex)
            say('game 2', r); g.reload_game('fr', 1); st.update(phase='fr2', k=0)
        elif p == 'fr2':
            if len(refs) < 3 or k < 60: return
            e = g.engine.state
            r.update(game3=g.game_language, setting3=g.reg['language'], map3=e.game_map, part3=e.part, reload_state3=g.args.reload_state, redraws3=redraws()); say('game 3', r); pyglet.app.exit()
    run = pyglet.app.run
    def run_with_scenario(**kw):
        if not st.get('scheduled'): st['scheduled'] = True; pyglet.clock.schedule(step)
        run(**kw)
    pyglet.app.run = run_with_scenario
    r['main'] = M.main(argv); r['games'] = len(refs)
    with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f: json.dump(r, f)
    say('main returned', r['main'], 'games', r['games'])


if __name__ == '__main__':
    if os.environ.get('DQ_RELOAD_SCENARIO'): scenario(os.environ['DQ_RELOAD_SCENARIO'])
    else: unittest.main()
