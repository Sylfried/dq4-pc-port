"""Rules of each game (difficulty, cheats, randomizer) and the randomizer's seed code, without window:

  1. seed code: drawn, read back (lowercase, without dashes, I / L / O typed for 1 / 0), rejected when a character is mistyped (check character), of another length or of an unknown version;
  2. one file per game ID (8 hexadecimal digits) next to the saves; an unreadable file gives none; only valid settings are read from it;
  3. GameRules follows the game being played: a new game (the engine's new ID) gets the rules prepared by the "new game" panel (or those of the moment) and writes them; entering a game puts its
     settings in place (each game keeps its own), what is changed during it is written to its file, the title forgets the game; a game without a file gets one with the settings of the start;
  4. export / import of the saves: the rules files go with the adventure logs;
  5. the "new game" panel of the Esc menu: opens on Difficulty, every setting at its default; Randomizer, the hero's name (the name entry, on the right, without OK) and gender, "Start the
     adventure" (grayed until the name and the gender are chosen); the Randomizer page shows the drawn seed, takes a typed or pasted one, draws another; starting records the rules and sends the name and the gender (without a name: the name
     page), Enter after typing the name goes to "Start the adventure"; the back button (or Esc, from any page) goes back to the start menu; during a game the Randomizer page shows the game's seed
     (Enter copies it) or says the game was started without the randomizer;
  6. the name entry opens the panel on the start menu only; the gender the game asks after the name is answered for the player, its window not drawn;
  7. real engine (DQ_APK, DQ_SAVES): GameStatus::resetUniqueID gives an ID of 32 bits, at least 256, and the engine reports it; a whole new game from the start menu (the name, then the
     gender buttons: 0 male, 1 female); Engine.in_game is false on the title and the start menu, true once a game is loaded.

    python3 tests/test_game_rules.py
"""
import json, os, shutil, sys, tempfile, types, unittest, zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.randomizer import seed as SD
from dq456_pc.persistence import game_rules as GR
from dq456_pc.persistence import settings as RG
from dq456_pc.persistence import saves as S
from dq456_pc import language as LG

PA = K = None


def menu_module():
    """The Esc menu (pyglet): imported for the panel's tests only; without a display (CI), they are skipped."""
    global PA, K
    if PA is None:
        try:
            import pyglet
            pyglet.options['shadow_window'] = False
            from dq456_pc.menus import pause
            PA, K = pause, pyglet.window.key
        except Exception as ex: raise unittest.SkipTest('Esc menu not importable here (%s)' % ex)
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class Seed(unittest.TestCase):
    def test_round_trip(self):
        c = SD.new_code(number=0x123456789A)
        self.assertRegex(c, r'^[0-9A-Z]{12}$')                                                   # (in one piece, no dashes)
        zero = {'safety': 0, 'items': 0, 'loot': 0, 'encounters': 0, 'single_enemy': 0, 'boss_encounters': 0, 'bosses': 0, 'two_bosses': 0}
        p = SD.parse(c); self.assertEqual((p['version'], p['number'], p['code'], p['options']), (SD.VERSION, 0x123456789A, c, zero))
        every = {'safety': 1, 'items': 2, 'loot': 1, 'encounters': 2, 'single_enemy': 1, 'boss_encounters': 1, 'bosses': 2, 'two_bosses': 1}
        c = SD.new_code(every, number=99); self.assertEqual(SD.parse(c)['options'], every)

    def test_settings_packed(self):
        """From version 3 the settings are packed: every combination comes back, in as few characters as they need (versions 5 to 7: 2 characters, the code 12)."""
        import itertools
        keys = [k for k, _n in SD.OPTIONS[SD.VERSION]]
        for vals in itertools.product(*[range(n) for _k, n in SD.OPTIONS[SD.VERSION]]):
            o = dict(zip(keys, vals)); c = SD.new_code(o, number=123)
            self.assertEqual(SD.parse(c)['options'], o); self.assertEqual(len(c), 1 + SD._option_digits(SD.VERSION) + SD.RANDOM_DIGITS + 1)
        self.assertEqual(SD._option_digits(3), 2); self.assertEqual(SD._option_digits(4), 3); self.assertEqual(SD._option_digits(5), 2); self.assertEqual(SD._option_digits(6), 2); self.assertEqual(SD._option_digits(7), 2)
        v = [SD.VERSION] + [31] * SD._option_digits(SD.VERSION) + [0] * SD.RANDOM_DIGITS
        self.assertIsNone(SD.parse(SD._text(v)))                                                    # (packed value out of range)

    def test_codes_of_version_2(self):
        """A code of version 2 (one character per setting) keeps its meaning; the settings added after it take their first value."""
        v = [2, 1, 2] + [(77 >> (5 * (SD.RANDOM_DIGITS - 1 - i))) & 31 for i in range(SD.RANDOM_DIGITS)]
        p = SD.parse(SD._text(v))
        self.assertEqual((p['version'], p['number'], p['options']), (2, 77, dict({'safety': 0, 'items': 0, 'loot': 0, 'encounters': 0, 'single_enemy': 0, 'boss_encounters': 0, 'bosses': 0, 'two_bosses': 0}, safety=1, items=2)))

    def test_codes_of_an_older_version(self):
        """A code of version 1 (no setting yet) keeps its meaning: the settings added after it take their first value (Safety on, Items unchanged)."""
        v = [1] + [(77 >> (5 * (SD.RANDOM_DIGITS - 1 - i))) & 31 for i in range(SD.RANDOM_DIGITS)]
        old = SD._text(v); p = SD.parse(old)
        self.assertEqual((p['version'], p['number'], p['options']), (1, 77, {'safety': 0, 'items': 0, 'loot': 0, 'encounters': 0, 'single_enemy': 0, 'boss_encounters': 0, 'bosses': 0, 'two_bosses': 0}))

    def test_typing_is_forgiving(self):
        c = SD.new_code(number=7)
        self.assertEqual(SD.parse(c.lower().replace('-', ''))['code'], c)
        self.assertEqual(SD.parse(' ' + c[:4] + '-' + c[4:8] + ' ' + c[8:] + ' ')['code'], c)                 # (dashes and spaces typed: ignored)
        o = c.replace('0', 'O').replace('1', 'I')
        self.assertEqual(SD.parse(o)['code'], c)                                                     # (O for 0, I or L for 1)

    def test_mistakes_are_rejected(self):
        c = SD.new_code(number=123456)
        last = c[-1]; wrong = c[:-1] + ('2' if last != '2' else '3')
        self.assertIsNone(SD.parse(wrong))                                                         # check character
        self.assertIsNone(SD.parse(c[:-2]))                                                        # length
        self.assertIsNone(SD.parse('Z' + c[1:]))                                                   # unknown version
        self.assertIsNone(SD.parse(c[:5] + 'U' + c[6:]))                                           # letter outside the alphabet
        for t in (None, '', '----'): self.assertIsNone(SD.parse(t))

    def test_random_draws_differ(self):
        self.assertEqual(len({SD.new_code() for _ in range(20)}), 20)


class Files(unittest.TestCase):
    def setUp(self): self.t = tempfile.mkdtemp(prefix='rules_')
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def test_one_file_per_id(self):
        r = GR.snapshot(dict(RG.DEFAULT), 'X')
        self.assertIsNone(GR.save(self.t, 0x1234abcd, r))
        self.assertTrue(os.path.isfile(os.path.join(self.t, 'rules', '1234abcd.json')))
        got = GR.load(self.t, 0x1234abcd); self.assertEqual(got['id'], 0x1234abcd); self.assertEqual(got['randomizer'], {'seed': 'X'})
        self.assertEqual(set(got['difficulty']), set(GR.DIFFICULTY_KEYS)); self.assertEqual(set(got['cheats']), set(GR.CHEAT_KEYS))
        self.assertEqual(list(GR.files(self.t)), ['1234abcd.json'])

    def test_game_ids_and_missing_files(self):
        GR.save(self.t, 0x80, {'randomizer': {'seed': 'X'}})
        self.assertEqual(GR.load(self.t, 0x80)['randomizer'], {'seed': 'X'})                       # (a game started before the port's rules: its file once made)
        self.assertIsNone(GR.load(self.t, None)); self.assertIsNone(GR.load(self.t, 0x55555555))
        os.makedirs(os.path.join(self.t, 'rules'), exist_ok=True)
        with open(GR.path(self.t, 0x1000), 'w') as f: f.write('{not json')
        self.assertIsNone(GR.load(self.t, 0x1000))

    def test_settings_are_checked_like_the_settings_file(self):
        r = {'difficulty': {'difficulty': 5, 'exp_rate': 1.25, 'gold_rate': 'x', 'level_up_heal': 1, 'battle_end_heal': True, 'other': 3}, 'cheats': {'random_encounters': False},
             'settings': {'music_volume': 0.5, 'msaa': 3, 'keys': {'menu': ['M', None]}}}
        v = GR.values(r)                                                                         # (a wrong value: the default; a key the file does not have: absent)
        self.assertEqual((v['difficulty'], v['exp_rate'], v['gold_rate'], v['level_up_heal'], v['battle_end_heal'], v['random_encounters']), (5, 1.25, 1.0, False, True, False))
        self.assertFalse({'music_volume', 'msaa', 'keys', 'other'} & set(v))                     # (an older file's display, sound and controls: no longer the game's)
        self.assertEqual(GR.values(None), {}); self.assertEqual(GR.values({'difficulty': 'x'}), {})

    def test_only_difficulty_and_cheats_belong_to_the_game(self):
        self.assertEqual(GR.GAME_KEYS, GR.DIFFICULTY_KEYS + GR.CHEAT_KEYS)
        for k in ('music_volume', 'keys', 'gamepads', 'interface_windows', 'msaa', 'sprite_mode', 'battle_speed', 'text_speed', 'language', 'window_mode', 'resolution'): self.assertIn(k, GR.APP_KEYS)
        self.assertEqual(set(GR.GAME_KEYS) | set(GR.APP_KEYS), set(RG.DEFAULT)); self.assertFalse(set(GR.GAME_KEYS) & set(GR.APP_KEYS))


class FakeEngine:
    def __init__(self, uid=None): self.uid = uid; self.new_game_uid = None; self.playing = True
    def game_uid(self): return self.uid
    def in_game(self): return self.playing


class Following(unittest.TestCase):
    def setUp(self): self.t = tempfile.mkdtemp(prefix='rules_'); self.R = json.loads(json.dumps(RG.DEFAULT)); self.applied = []; self.sync = GR.SYNC_EVERY; GR.SYNC_EVERY = 1          # (checked at every step)
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True); GR.SYNC_EVERY = self.sync
    def follow(self, g, e): g.update(e, self.R, lambda: self.applied.append(dict(self.R)))

    def test_new_game_gets_the_prepared_rules(self):
        g = GR.GameRules(self.t); e = FakeEngine(); e.playing = False
        R2 = dict(self.R, difficulty=5, exp_rate=1.5, random_encounters=False)                       # (the panel's settings)
        g.prepare(GR.snapshot(R2, 'SEED-1')); e.new_game_uid = e.uid = 0xdeadbeef
        self.follow(g, e)
        self.assertIsNone(e.new_game_uid); self.assertEqual(g.seed(), 'SEED-1'); self.assertIsNone(g.pending)
        self.assertEqual(GR.load(self.t, 0xdeadbeef)['randomizer']['seed'], 'SEED-1')
        e.playing = True; self.follow(g, e)                                                           # (the game is entered: its settings are put in place)
        self.assertEqual((self.R['difficulty'], self.R['exp_rate'], self.R['random_encounters']), (5, 1.5, False)); self.assertEqual(len(self.applied), 1)

    def test_each_game_keeps_its_settings(self):
        GR.save(self.t, 0x1111, GR.snapshot(dict(self.R, difficulty=5, random_encounters=False), 'A')); GR.save(self.t, 0x2222, GR.snapshot(self.R, 'B'))          # (A: Custom, the notches set by hand)
        g = GR.GameRules(self.t); e = FakeEngine(0x1111); self.follow(g, e)
        self.assertEqual((self.R['difficulty'], self.R['random_encounters']), (5, False))
        self.R['exp_rate'] = 1.5; self.follow(g, e)                                                  # (changed during the game: written to its file)
        self.assertEqual(GR.load(self.t, 0x1111)['difficulty']['exp_rate'], 1.5)
        e.uid = 0x2222; self.follow(g, e); self.assertEqual((self.R['difficulty'], self.R['exp_rate'], self.R['random_encounters']), (2, 1.0, True))
        self.assertEqual(GR.load(self.t, 0x2222)['difficulty']['exp_rate'], 1.0)                    # (B's file untouched by A's settings)
        e.playing = False; self.follow(g, e); GR.reset(self.R); self.R['gold_rate'] = 0.5; self.follow(g, e)          # the title (a new game's panel changes the settings): no game, nothing written
        self.assertEqual(GR.load(self.t, 0x2222)['difficulty']['gold_rate'], 1.0)
        e.playing = True; self.follow(g, e); self.assertEqual(self.R['gold_rate'], 1.0)              # (back in the same game: its settings again)
        e.uid = 0x1111; self.follow(g, e); self.assertEqual((self.R['difficulty'], self.R['exp_rate']), (5, 1.5))

    def test_display_sound_and_keys_are_the_same_for_every_game(self):
        old = dict(GR.snapshot(self.R, None), settings={'music_volume': 0.25, 'sprite_mode': 1, 'keys': dict(self.R['keys'], menu=['M', None])})          # (a file written before 16/11)
        GR.save(self.t, 0x1111, old); GR.save(self.t, 0x2222, {'difficulty': {'difficulty': 0}})
        self.R['music_volume'] = 0.75; g = GR.GameRules(self.t, self.R); e = FakeEngine(0x1111); self.follow(g, e)
        self.assertEqual((self.R['music_volume'], self.R['sprite_mode'], self.R['keys']['menu']), (0.75, RG.DEFAULT['sprite_mode'], RG.DEFAULT['keys']['menu']))          # (the application's: untouched)
        self.R['sfx_volume'] = 0.5; self.R['exp_rate'] = 1.5; self.follow(g, e)
        f = GR.load(self.t, 0x1111); self.assertEqual(f['difficulty']['exp_rate'], 1.5); self.assertNotIn('settings', f)          # (only the rules written; the old section dropped)
        e.uid = 0x2222; self.follow(g, e)
        self.assertEqual((self.R['difficulty'], self.R['music_volume'], self.R['sfx_volume']), (0, 0.75, 0.5))                    # (another game: same display, sound and controls)
        self.assertNotIn('settings', GR.load(self.t, 0x2222))

    def test_settings_written_every_second_only(self):
        GR.SYNC_EVERY = self.sync; GR.save(self.t, 0x1111, GR.snapshot(self.R, None))
        g = GR.GameRules(self.t); e = FakeEngine(0x1111); self.follow(g, e); self.R['gold_rate'] = 0.5
        for _ in range(GR.SYNC_EVERY - 1): self.follow(g, e)
        self.assertEqual(GR.load(self.t, 0x1111)['difficulty']['gold_rate'], 1.0); self.follow(g, e); self.assertEqual(GR.load(self.t, 0x1111)['difficulty']['gold_rate'], 0.5)

    def test_game_without_file_gets_the_settings_of_the_start(self):
        start = dict(self.R, difficulty=3, battle_end_heal=True)
        g = GR.GameRules(self.t, start); self.R['difficulty'] = 0
        e = FakeEngine(7); self.follow(g, e)
        self.assertEqual((self.R['difficulty'], self.R['battle_end_heal']), (3, True)); self.assertIsNone(g.seed())
        self.assertEqual(GR.load(self.t, 7)['difficulty']['difficulty'], 3)

    def test_new_game_without_panel_gets_the_rules_of_the_moment(self):
        g = GR.GameRules(self.t); e = FakeEngine(); self.R['difficulty'] = 4
        e.new_game_uid = e.uid = 0x100; g.update(e, self.R)
        self.assertIsNone(g.seed()); self.assertEqual(GR.load(self.t, 0x100)['difficulty']['difficulty'], 4)          # (no panel: no randomizer, no seed)

    def test_loading_another_game_reads_its_rules(self):
        GR.save(self.t, 0x1111, GR.snapshot(self.R, 'A')); GR.save(self.t, 0x2222, GR.snapshot(self.R, 'B'))
        g = GR.GameRules(self.t); e = FakeEngine(0x1111); g.update(e, self.R); self.assertEqual(g.seed(), 'A')
        e.uid = 0x2222; g.update(e, self.R); self.assertEqual(g.seed(), 'B')
        e.uid = 3; g.update(e, self.R); self.assertIsNone(g.seed())


class ExportImport(unittest.TestCase):
    def setUp(self): self.t = tempfile.mkdtemp(prefix='rules_zip_')
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def test_rules_travel_with_the_saves(self):
        src = os.path.join(self.t, 'a'); os.makedirs(src)
        with open(os.path.join(src, 'data1.dat'), 'wb') as f: f.write(valid_logfile())
        GR.save(src, 0xabcdef01, {'randomizer': {'seed': 'Z'}})
        z = os.path.join(self.t, 'out.zip'); S.export_saves(src, None, z)
        with zipfile.ZipFile(z) as zz: self.assertIn('rules/abcdef01.json', zz.namelist())
        dst = os.path.join(self.t, 'b'); S.import_saves([z], dst, None)
        self.assertEqual(GR.load(dst, 0xabcdef01)['randomizer'], {'seed': 'Z'})


def valid_logfile():
    """An adventure log that passes the import's checks (see test_paths.valid_logfile)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_paths
    return test_paths.valid_logfile(1)


class FakeGame:
    last_device = 'keyboard'
    def __init__(self, t, seed=None):
        from dq456_pc.menus import name_entry as NE
        self.reg = RG.Settings(os.path.join(t, 'settings.json')); self.mouse = None; self.width, self.height = 1280, 720
        self.game_rules = GR.GameRules(t); self.clip = None; self.sent = []
        self.sound = types.SimpleNamespace(play_sfx=lambda *a: None); self.name_entry = NE.NameEntry(self); self.name_entry.open_menu(8)
        if seed: self.game_rules.rules = {'randomizer': {'seed': seed}}
    def _name_entry_ok(self, name_str, gender=None): self.sent.append(('ok', name_str, gender))
    def _name_entry_back(self): self.sent.append(('back',))
    def pause_game(self, yes): pass
    def apply_game(self): pass
    def set_clipboard_text(self, t): self.clip = t
    def get_clipboard_text(self): return self.clip


class NewGamePanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls): menu_module()
    def setUp(self): self.t = tempfile.mkdtemp(prefix='rules_panel_'); LG.select_language('fr')
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    ROOT = ['settings.difficulty', 'settings.randomizer', 'settings.display', 'settings.sound', 'settings.controls', 'settings.hero_name', 'settings.hero_gender', 'settings.start_adventure']
    NAME, GENDER, START = 5, 6, 7

    def test_panel_pages_and_starting_records_the_rules(self):
        J = FakeGame(self.t); J.reg['difficulty'] = 4; J.reg['random_encounters'] = False; J.reg['exp_rate'] = 1.5; J.reg['music_volume'] = 0.5
        p = PA.Pause(J); p.open_menu(new_game=True)
        self.assertEqual(p.stack, ['root', 'difficulty'])                                            # (opens on Difficulty)
        self.assertEqual([J.reg[k] for k in GR.GAME_KEYS], [RG.DEFAULT[k] for k in GR.GAME_KEYS])     # (a new game: its rules at their default)
        self.assertEqual(J.reg['music_volume'], 0.5)                                                 # (display, sound, controls: the application's, as they are)
        self.assertEqual([e.get('page') for e in p._entries_root()][2:5], ['display', 'sound', 'controls'])          # (their pages, the same as during a game)
        self.assertEqual([e['l'] for e in p._entries_root()], self.ROOT)
        self.assertIsNone(p.draft_seed)                                                               # (randomizer mode off: no seed drawn)
        p.stack[-1] = 'randomizer'; e = p._entries(); self.assertEqual([x['l'] for x in e], ['settings.randomizer_mode'])          # (off: the switch alone)
        self.assertFalse(e[0]['get']()); e[0]['ok'](); seed = p.draft_seed; self.assertIsNotNone(SD.parse(seed))                      # (turned on: a seed is drawn)
        e = p._entries(); self.assertEqual([x['l'] for x in e[:3]], ['settings.randomizer_mode', 'settings.seed', 'settings.safety']); self.assertEqual(e[1]['v'](), seed)
        e[1]['default'](); self.assertNotEqual(p.draft_seed, seed)                                 # (the round button on the right of the seed: a new seed)
        p.stack.pop(); start = p._entries()[self.START]; self.assertTrue(start['off']()); self.assertEqual(start['hint'], 'settings.choose_name_gender_first')          # (grayed: no name, no gender)
        start['ok'](); self.assertTrue(p.opened); self.assertEqual(p.stack, ['root', 'name']); self.assertEqual(J.sent, [])          # (its action without a name: the name page)
        J.name_entry.text_entered('Solo'); p.back(); self.assertEqual(p.stack, ['root'])                     # (letters typed on the name page; back to the list)
        self.assertNotIn('v', p._entries()[self.NAME]); self.assertTrue(p._entries()[self.START]['off']())                     # (the name is not shown in the list; still no gender)
        p._entries()[self.START]['ok'](); self.assertEqual(p.stack, ['root', 'gender'])                                # (without a gender: its page)
        g = p._entries_root()[self.GENDER]; self.assertNotIn('v', g); self.assertNotIn('vals', g)                       # (no value shown, no drop-down list: a page)
        p.key_press(K.RIGHT); p.key_press(K.ENTER); self.assertEqual(p.hero_gender, 1)
        self.assertEqual(p.stack, ['root']); self.assertEqual(p._entries()[p.selected['root']]['l'], 'settings.start_adventure')          # (both chosen: on "Start the adventure")
        self.assertFalse(p._entries()[self.START]['off']()); self.assertEqual(p._entries()[self.START]['hint'], 'settings.rules_saved_with_game')
        J.reg['gold_rate'] = 0.75; draft = p.draft_seed; p._entries()[self.START]['ok']()
        self.assertFalse(p.opened); self.assertFalse(p.new_game); self.assertTrue(J.name_entry.handed); self.assertEqual(J.sent, [('ok', 'Solo', 1)])
        self.assertEqual(J.game_rules.pending['randomizer']['seed'], draft); self.assertEqual(J.game_rules.pending['difficulty']['gold_rate'], 0.75)

    def test_name_page_has_no_ok_and_enter_after_typing_goes_to_start(self):
        from dq456_pc.menus import name_entry as NE
        J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p._switch_side(self.NAME)
        self.assertEqual(p.stack, ['root', 'name']); ne = J.name_entry; self.assertTrue(ne.in_panel())
        ne.text_entered('Ana'); self.assertEqual(ne.cur, 0); p.key_press(K.ENTER)                   # (typed on the keyboard, then Enter: the gender, not chosen yet)
        self.assertEqual(p.stack, ['root', 'gender']); self.assertIsNone(p.hero_gender); p.key_press(K.ENTER)          # (Enter: Masculin, under the cursor)
        self.assertEqual(p.stack, ['root']); self.assertEqual(p._entries()[p.selected['root']]['l'], 'settings.start_adventure'); self.assertEqual(J.sent, [])
        p.key_press(K.ENTER); self.assertEqual(J.sent, [('ok', 'Ana', 0)]); self.assertFalse(p.opened)
        self.assertIsNone(ne.on_ok)                                                                   # (an ordinary name entry has its OK again)
        J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p._switch_side(self.NAME); ne = J.name_entry
        ne.text_entered('Bo'); ne.cur = NE.I_OK; self.assertFalse(ne.press(NE.I_OK)); self.assertFalse(ne.press(NE.I_BACK)); self.assertEqual(J.sent, [])
        ne.cur = 34; ne.move_by(0, -1); self.assertEqual(ne.cur, NE.I_ALPHA + 3)                       # (the grid's last column, down: "Suppr.", the 4th and last function button)
        ne.move_by(1, 0); self.assertEqual(ne.cur, NE.I_ALPHA); ne.move_by(-1, 0); self.assertEqual(ne.cur, NE.I_ALPHA + 3)
        ne.move_by(0, -1); self.assertLess(ne.cur, NE.COLS)                                          # (down from the buttons: the top of the grid)
        ne.key_press(K.ENTER); self.assertEqual(J.sent, [])                                          # (Enter on a key types it)

    def test_gender_page(self):
        J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p._switch_side(self.GENDER)
        self.assertEqual(p.stack, ['root', 'gender']); self.assertEqual(p._entries(), []); self.assertIsNone(p.hero_gender)          # (nothing chosen at the start)
        p.key_press(K.RIGHT); self.assertEqual(p.hero_gender, 1); p.key_press(K.RIGHT); self.assertEqual(p.hero_gender, 1)
        p.key_press(K.LEFT); self.assertEqual(p.hero_gender, 0); p.key_press(K.UP); self.assertEqual(p.stack, ['root', 'gender'])
        p.gender_zones = [(0, (0, 0, 10, 10)), (1, (20, 0, 30, 10))]; p.zone_ret = None
        p.click(25, 5, 1); self.assertEqual(p.hero_gender, 1); p.click(15, 5, 1); self.assertEqual(p.hero_gender, 1)          # (a click on a column chooses it; elsewhere, nothing)
        p.click(5, 5, 1); self.assertEqual(p.hero_gender, 0); self.assertEqual(p.stack, ['root', 'gender'])
        p.key_press(K.BACKSPACE); self.assertEqual(p.stack, ['root']); self.assertTrue(p.opened)
        self.assertIsNone(p._hero_frame(1, 0, False))                                                # (no sprite sheet without the game window: nothing drawn)
        drawn = []; p._label = lambda t, size_value, color=PA.WHITE, translate=True: drawn.append(color) or types.SimpleNamespace(content_width=10, content_height=10, x=0, y=0, draw=lambda: None)
        for a in ('_border', '_plate', '_cursor', '_restore_blend', '_help_zone'): setattr(p, a, lambda *a, **k: None)
        grayed = []; p._hero_frame = lambda g, col, gray: grayed.append((g, gray))
        p.hero_gender = 1; p._draw_gender(0, 500, 400, 400, 1.0); self.assertEqual(drawn[1:], [PA.WHITE, PA.GOLD]); self.assertEqual(grayed, [(0, True), (1, False)])          # (the gender not chosen: its sprite grayed, its label white)
        drawn.clear(); grayed.clear(); p.hero_gender = None; p._draw_gender(0, 500, 400, 400, 1.0); self.assertEqual(drawn[1:], [PA.WHITE, PA.WHITE]); self.assertEqual(grayed, [(0, True), (1, True)])          # (nothing chosen yet: both grayed)

    def test_back_button_and_esc_go_back_to_the_start_menu(self):
        for page in ('difficulty', 'name', 'randomizer', 'gender'):
            J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p.stack = ['root', page]
            p.zone_ret = (0, 0, 10, 10); p.click(5, 5, 1)
            self.assertFalse(p.opened, page); self.assertEqual(J.sent, [('back',)]); self.assertIsNone(J.game_rules.pending); self.assertTrue(J.name_entry.handed)
        for page in ('difficulty', 'name', 'gender', 'root'):                                         # Esc, from any page: back to the start menu
            J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p.stack = ['root', page] if page != 'root' else ['root']
            p.key_press(K.ESCAPE); self.assertFalse(p.opened, page); self.assertEqual(J.sent, [('back',)])

    def test_typing_or_pasting_a_seed(self):
        J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p.stack[-1] = 'randomizer'; p._entries()[0]['ok'](); p.selected['randomizer'] = 1
        good = SD.new_code(number=42)
        p.key_press(K.ENTER); self.assertEqual(p.entry, [1, ''])
        p.text(good.lower()); p.key_press(K.ENTER)
        self.assertIsNone(p.entry); self.assertEqual(p.draft_seed, good)
        p.key_press(K.ENTER); p.text('1234'); p.key_press(K.ENTER)
        self.assertEqual(p.draft_seed, good); self.assertEqual(p.message[3], 'settings.invalid_seed')          # (wrong: the seed stays, a message says so)
        other = SD.new_code(number=99); J.clip = other
        p.key_press(K.ENTER); p.key_press(K.V, K.MOD_CTRL); p.key_press(K.ENTER)
        self.assertEqual(p.draft_seed, other)
        J.name_entry.text = 'Kiryl'; p.hero_gender = 0; p._start_adventure()
        self.assertFalse(p.opened); self.assertEqual(J.game_rules.pending['randomizer']['seed'], other)
        J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p.stack[-1] = 'randomizer'; p._entries()[0]['ok'](); p._entries()[0]['ok']()          # (on, then off again: a game without the randomizer)
        J.name_entry.text = 'Kiryl'; p.hero_gender = 0; p._start_adventure(); self.assertEqual(J.game_rules.pending['randomizer'], {'seed': None})

    def test_settings_go_with_the_seed(self):
        """The settings of the page (Safety, Items, Monster drops, Random encounters, Bosses in random encounters, Bosses, Two bosses) are carried by the seed code: changing one changes the code, not its random number; a new seed (the seed's round button) keeps them; a typed seed sets them."""
        J = FakeGame(self.t); p = PA.Pause(J); p.open_menu(new_game=True); p.stack[-1] = 'randomizer'; p._entries()[0]['ok']()
        e = p._entries(); self.assertEqual([x['l'] for x in e], ['settings.randomizer_mode', 'settings.seed', 'settings.safety', 'settings.items_setting', 'settings.loot_setting',
                                                                 'settings.encounters_setting', 'settings.single_enemy_setting', 'settings.boss_encounters_setting', 'settings.bosses_setting', 'settings.two_bosses_setting'])
        self.assertEqual([x['l'] for x in e if p._inactive(x)], ['settings.single_enemy_setting'])                          # (Safety does not gray the bosses' lines: "Unchanged" keeps them; one enemy only: with "Random" encounters)
        self.assertTrue(e[2]['get']()); self.assertEqual(e[3]['get'](), 0); self.assertEqual(e[3]['vals'], [0, 1, 2]); n = SD.parse(p.draft_seed)['number']
        zero = {'loot': 0, 'encounters': 0, 'single_enemy': 0, 'boss_encounters': 0, 'bosses': 0, 'two_bosses': 0}
        e[3]['plus'](); self.assertEqual(SD.parse(p.draft_seed)['options'], dict(zero, safety=0, items=1)); self.assertEqual(SD.parse(p.draft_seed)['number'], n)
        e[2]['ok'](); self.assertEqual(SD.parse(p.draft_seed)['options'], dict(zero, safety=1, items=1))
        self.assertEqual(p._value_name('settings.items_setting', 1), 'settings.items_shuffled')
        self.assertEqual(e[4]['vals'], [0, 1]); e[4]['plus'](); self.assertEqual(SD.parse(p.draft_seed)['options']['loot'], 1)
        self.assertEqual(p._value_name('settings.loot_setting', 1), 'settings.loot_random')
        e = p._entries(); self.assertEqual(e[5]['vals'], [0, 1, 2]); self.assertFalse(e[7]['get']())
        e[5]['plus'](); self.assertTrue(p._inactive(p._entries()[6])); e[5]['plus'](); e = p._entries(); self.assertFalse(p._inactive(e[6])); e[6]['ok'](); e[7]['ok']()
        e = p._entries(); self.assertEqual(e[8]['vals'], [0, 1, 2]); self.assertFalse(e[9]['get']()); e[8]['plus'](); e[8]['plus'](); e[9]['ok']()
        every = {'safety': 1, 'items': 1, 'loot': 1, 'encounters': 2, 'single_enemy': 1, 'boss_encounters': 1, 'bosses': 2, 'two_bosses': 1}
        self.assertEqual(SD.parse(p.draft_seed)['options'], every); self.assertEqual(p._value_name('settings.bosses_setting', 1), 'settings.bosses_shuffled')
        self.assertEqual(p._value_name('settings.encounters_setting', 2), 'settings.encounters_random')
        e[1]['default'](); q = SD.parse(p.draft_seed); self.assertNotEqual(q['number'], n); self.assertEqual(q['options'], every)          # (a new seed: the settings stay)
        typed = SD.new_code({'safety': 0, 'items': 2}, number=42); p._type_seed(typed)
        e = p._entries(); self.assertTrue(e[2]['get']()); self.assertEqual(e[3]['get'](), 2)
        e[3]['default'](); self.assertEqual(SD.parse(p.draft_seed)['options']['items'], 0)

    def test_during_a_game(self):
        code = SD.new_code({'safety': 1, 'items': 2, 'encounters': 2}, number=5)
        J = FakeGame(self.t, seed=code); p = PA.Pause(J); p.open_menu(); p.stack.append('randomizer')
        e = p._entries(); self.assertEqual(e[0]['l'], 'settings.seed'); self.assertEqual(e[0]['v'](), code)
        e[0]['ok'](); self.assertEqual(J.clip, code); self.assertEqual(p.message[3], 'settings.seed_copied')
        self.assertEqual([(x['l'], x['get'](), p._inactive(x)) for x in e[1:]], [('settings.safety', False, True), ('settings.items_setting', 2, True), ('settings.loot_setting', 0, True),
                                                                                    ('settings.encounters_setting', 2, True), ('settings.single_enemy_setting', False, True),
                                                                                    ('settings.boss_encounters_setting', False, True),
                                                                                    ('settings.bosses_setting', 0, True), ('settings.two_bosses_setting', False, True)])          # (the game's settings, shown only)
        self.assertNotIn('default', e[0])                                                             # (no new seed during a game)
        p.stack.pop(); self.assertNotIn('settings.start_adventure', [x['l'] for x in p._entries()])          # (the root of a game: the usual one)
        J2 = FakeGame(self.t); p2 = PA.Pause(J2); p2.open_menu(); p2.stack.append('randomizer')
        self.assertEqual(p2._entries()[0]['l'], 'settings.game_without_randomizer')
        p2.shutdown(); self.assertIsNone(J2.game_rules.pending)                                      # (the menu of a game records nothing)


class NameEntryOpensThePanel(unittest.TestCase):
    """The name entry of the start menu is the start of a new game: when the engine shows its keyboard, the rules panel opens (once), the name entry in it; the gender asked after the name
    is answered for the player."""
    def setUp(self):
        menu_module()
        from dq456_pc.window import title_screen as TS
        from dq456_pc.core import engine as ENGINE
        self.calls = []; self.sent = []
        self.f = {'type': 55, 'closed': False, 'indicators': {0: 8, 1: 1}, 'visible': False, 'input': False}
        eng = types.SimpleNamespace(ui=types.SimpleNamespace(f={15: self.f}), state=types.SimpleNamespace(part=ENGINE.PART_INITIAL), send_menu=lambda *a: self.sent.append(a))
        J = self.J = types.SimpleNamespace(engine=eng, entry_port=None, auto_gender=None, menu_to_release=None,
                                           name_entry=types.SimpleNamespace(active=False), pause=types.SimpleNamespace(open_menu=lambda **kw: self.calls.append(kw)))
        J.name_entry.open_menu = lambda n: setattr(J.name_entry, 'active', True)
        J.name_entry.shutdown = lambda: setattr(J.name_entry, 'active', False)
        self.cls = next(v for v in vars(TS).values() if isinstance(v, type) and hasattr(v, '_update_name_entry'))

    def test_once_per_name_entry(self):
        J, cls, f = self.J, self.cls, self.f
        for _ in range(3): cls._update_name_entry(J)
        self.assertEqual(self.calls, [{'new_game': True}]); self.assertTrue(J.name_entry.active)
        f['indicators'][1] = 0; cls._update_name_entry(J); f['indicators'][1] = 1; cls._update_name_entry(J)          # (back to the list, then a new adventure again: the panel again)
        self.assertEqual(len(self.calls), 2)

    def test_not_during_a_game(self):
        self.J.engine.state.part = 0xc; self.cls._update_name_entry(self.J)                           # (a name asked during the game: the name entry alone)
        self.assertEqual(self.calls, []); self.assertTrue(self.J.name_entry.active)

    def test_gender_answered_for_the_player(self):
        J, cls, f = self.J, self.cls, self.f
        cls._update_name_entry(J); J.auto_gender = 1                                                  # (the name sent, female chosen in the panel)
        f['indicators'][1] = 0; cls._update_name_entry(J); self.assertEqual(self.sent, [])            # (checking the name: the window does not take input yet)
        f['visible'] = f['input'] = True; cls._update_name_entry(J)
        self.assertEqual(self.sent, [(15, 1, 1, 0x10)]); self.assertEqual(J.menu_to_release, 15); self.assertEqual(J.auto_gender, -1)          # (button 1: Féminin)
        cls._update_name_entry(J); self.assertEqual(len(self.sent), 1)
        f['closed'] = True; cls._update_name_entry(J); self.assertIsNone(J.auto_gender)              # (the window closed: drawn again next time)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def test_new_game_id(self):
        from dq456_pc.core import engine as ENGINE
        m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_rules_'))
        for _ in range(3): m.step(0, 0)
        c = m.core; g = c.export('_ZN6status6g_GameE'); f = c.export(ENGINE.UNIQUE_ID_STORE[0])
        self.assertNotIn(True, ['game rules' in x for x in m.missing_hooks])
        seen = set()
        for _ in range(4):
            c.call(f, g, label='resetUniqueID')
            uid = m.game_uid(); self.assertGreaterEqual(uid, GR.FIRST_PORT_UID); self.assertEqual(m.new_game_uid, uid); seen.add(uid); m.new_game_uid = None
        self.assertEqual(len(seen), 4)

    def test_whole_new_game_from_the_start_menu(self):
        """Start menu > "Créer un nouveau journal" (a free log, or the question when there is none), the name, then the gender buttons (0 Masculin, 1 Féminin): the game starts with that gender."""
        import struct
        from dq456_pc.core import engine as ENGINE
        m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_rules_')); c = m.core
        gender = lambda: c.call(c.export('_ZN21MaterielMenu_NameEdit9getGenderEv'), c.export('gMaterielMenu_NameEdit'))
        visible = lambda t: next((p for p, f in m.ui.f.items() if f.get('type') == t and f.get('visible') and f.get('input') and not f.get('closed')), None)
        def tap(port, b, pad=0x10):
            m.send_menu(port, 1, b, pad)
            for _ in range(2): m.step(0, 0)
            m.send_menu(port, 1, -1, 0)
            for _ in range(10): m.step(0, 0)
        named = asked = False
        for i in range(1500):
            a = ENGINE.A if i % 30 == 0 and not any(f.get('type') in (53, 54, 55) and f.get('visible') for f in m.ui.f.values()) and not named else 0          # (the title: A, until the start menu)
            m.step(a, a); self.assertFalse(m.in_game())
            f = next((f for f in m.ui.f.values() if f.get('type') == 55 and not f.get('closed')), None)
            if f is not None and f['indicators'].get(1) == 1 and not named:
                b = 'Ana'.encode() + b'\0'; m.send_menu(15, 2, 3); m.send_menu(15, *struct.unpack('<2h', b)); named = True
            elif named and visible(55) is not None and not asked: self.assertIn((3, 0), f['cells']); tap(15, 1); asked = True
            elif m.new_game_uid is not None: break
            elif not named and visible(1) is not None: tap(visible(1), 0)                         # (no free log: "Oui", one is replaced)
            elif not named and visible(54) is not None: tap(visible(54), 3, 0x800); tap(visible(54) or 0, 3)          # "Créer un nouveau journal" (cursor, then A)
            elif not named and visible(53) is not None: tap(visible(53), 2, 0x800); tap(visible(53) or 0, 2)
        self.assertTrue(asked); self.assertIsNotNone(m.new_game_uid); self.assertEqual(gender(), 1)
        for _ in range(200):
            m.step(0, 0)
            if m.in_game(): break
        self.assertTrue(m.in_game()); self.assertEqual(m.game_uid(), m.new_game_uid)


if __name__ == '__main__':
    unittest.main(verbosity=1)
