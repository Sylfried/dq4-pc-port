"""Port folders (paths.py) and resume from the old layout: default layout, environment variables, migration without overwriting or deleting,
import / export of saves with the new folders, old savestates (module names from before the tidy-up). Without window or engine.

    python3 tests/test_paths.py"""
import os, pickle, shutil, sys, tempfile, unittest, zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc import paths as CH
from dq456_pc import language as LG
from dq456_pc.persistence import savestates as SS
from dq456_pc.persistence import saves as S


def write(path, content=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(content)
    return path


class Layout(unittest.TestCase):
    def test_default(self):
        d = CH.Folders('/projet', env={})
        self.assertEqual(d.data, os.path.normpath('/projet/data'))
        for name_str, expected in (('apk', 'data/apk/dq4/fr'), ('apk_fr', 'data/apk/dq4/fr'), ('apk_en', 'data/apk/dq4/en'), ('apk_root', 'data/apk'), ('apk_game', 'data/apk/dq4'), ('cache_en', 'data/cache/dq4/en'), ('cache_root', 'data/cache'), ('old_cache_en', 'data/cache_en'), ('mobile', 'data/saves/dq4/mobile'), ('portage', 'data/saves/dq4'), ('old_port_dir', 'data/saves/dq4/portage'), ('savestates', 'data/saves/dq4/savestates'), ('saves_root', 'data/saves'),
                             ('cache', 'data/cache/dq4/fr'), ('settings', 'data/settings/settings.json'), ('favorites', 'data/settings/history_favorites.json'),
                             ('window_logfile', 'data/logs/window_errors.log')):
            self.assertEqual(getattr(d, name_str), os.path.normpath('/projet/' + expected), name_str)

    def test_environment_variables(self):
        d = CH.Folders('/projet', env={'DQ_DATA': '/ailleurs/mes_donnees'})
        self.assertEqual(d.apk, os.path.normpath('/ailleurs/mes_donnees/apk/dq4/fr')); self.assertEqual(d.apk_en, os.path.normpath('/ailleurs/mes_donnees/apk/dq4/en')); self.assertEqual(d.cache, os.path.normpath('/ailleurs/mes_donnees/cache/dq4/fr'))
        d = CH.Folders('/projet', env={'DQ4_GAMES': '/jeux/DQ4'})                      # old behavior: APK and phone saves over there, the rest in donnees
        self.assertEqual(d.apk, os.path.normpath('/jeux/DQ4/patched_apks')); self.assertEqual(d.apk_en, os.path.normpath('/jeux/DQ4/patched_apks_en')); self.assertEqual(d.mobile, os.path.normpath('/jeux/DQ4/saves'))
        self.assertEqual(d.portage, os.path.normpath('/projet/data/saves/dq4'))

    def test_savestates_and_copies_per_write_folder(self):
        d = CH.Folders('/projet', env={})
        self.assertEqual(d.savestates_folder(d.portage), d.savestates); self.assertEqual(d.clones_folder(d.portage), d.saves)
        self.assertEqual(d.savestates_folder('/tmp/sv_test'), os.path.join('/tmp/sv_test', 'savestates')); self.assertEqual(d.clones_folder('/tmp/sv_test'), '/tmp/sv_test')

    def test_most_recent_mobile_save(self):
        with tempfile.TemporaryDirectory() as t:
            d = CH.Folders(t, env={}); self.assertIsNone(d.recent_mobile_save())
            for n in ('20261003_100000', '20261103_222423', '20261007_190735'): write(os.path.join(d.mobile, n, 'data1.dat'))
            write(os.path.join(d.mobile, 'zz_un_fichier.txt'))
            self.assertEqual(os.path.basename(d.recent_mobile_save()), '20261103_222423')


class Migration(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='migr_'); self.d = CH.Folders(self.t, env={})
        r = self.t
        write(os.path.join(r, 'jeux', 'DQ4', 'patched_apks', 'base.apk'), b'APK1'); write(os.path.join(r, 'jeux', 'DQ4', 'patched_apks', 'split_config.arm64_v8a.apk'), b'APK2')
        write(os.path.join(r, 'jeux', 'DQ4', 'saves', '20261103_222423', 'data1.dat'), b'T1'); write(os.path.join(r, 'jeux', 'DQ4', 'saves', '20261007_190735', 'data1.dat'), b'T0')
        write(os.path.join(r, 'jeux', 'DQ4', 'saves', '20261103_222423', 'data2.dat'), b'T2'); write(os.path.join(r, 'jeux', 'DQ4', 'saves', '20261007_190735', 'data3.dat'), b'T3_ancien')
        write(os.path.join(r, 'dq4_pc', 'cache', 'carte10_a.pkl'), b'CACHE'); write(os.path.join(r, 'dq4_pc', 'cache', 'il2cpp', 'dump.cs'), b'DUMP')
        write(os.path.join(r, 'dq4_pc', 'sauvegardes', 'data1.dat'), b'P1'); write(os.path.join(r, 'dq4_pc', 'sauvegardes', 'etats', 'etat_01.dqs'), b'E1')
        write(os.path.join(r, 'dq4_pc', 'sauvegardes', 'avant_import_20261101_101010', 'data2.dat'), b'AV')
        write(os.path.join(r, 'dq4_pc', 'reglages.json'), b'{"a": 1}'); write(os.path.join(r, 'dq4_pc', 'historique_favoris.json'), b'[]'); write(os.path.join(r, 'dq4_pc', 'erreurs_fenetre.log'), b'LOG')

    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def read(self, *p):
        with open(os.path.join(self.t, *p), 'rb') as f: return f.read()

    def test_complete_resume(self):
        done = CH.migrate(self.d, log=lambda *a: None)
        self.assertGreaterEqual(len(done), 6)
        self.assertEqual(self.read('data', 'apk', 'dq4', 'fr', 'base.apk'), b'APK1')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'data1.dat'), b'P1')                                        # the earlier port's adventure logs take precedence over the phone copy (T1)
        self.assertEqual(self.read('data', 'saves', 'dq4', 'data2.dat'), b'T2')                                        # ... which fills in what is missing (the most recent one only)
        self.assertFalse(os.path.exists(os.path.join(self.t, 'data', 'saves', 'dq4', 'data3.dat')))             # (not the one from an older date)
        self.assertFalse(os.path.exists(os.path.join(self.t, 'data', 'saves', 'dq4', 'mobile'))); self.assertFalse(os.path.exists(os.path.join(self.t, 'data', 'saves', 'dq4', 'portage')))
        self.assertEqual(os.listdir(os.path.join(self.t, 'data', 'saves')), ['dq4'])
        self.assertEqual(self.read('data', 'cache', 'dq4', 'fr', 'carte10_a.pkl'), b'CACHE'); self.assertEqual(self.read('data', 'cache', 'dq4', 'fr', 'il2cpp', 'dump.cs'), b'DUMP')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_01.dqs'), b'E1')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'before_import_20261101_101010', 'data2.dat'), b'AV')
        self.assertEqual(self.read('data', 'settings', 'settings.json'), b'{"a": 1}'); self.assertEqual(self.read('data', 'settings', 'history_favorites.json'), b'[]')
        self.assertEqual(self.read('data', 'logs', 'window_errors.log'), b'LOG')

    def test_originals_remain_except_cache(self):
        CH.migrate(self.d, log=lambda *a: None)
        for p in (('jeux', 'DQ4', 'patched_apks', 'base.apk'), ('jeux', 'DQ4', 'saves', '20261103_222423', 'data1.dat'), ('dq4_pc', 'sauvegardes', 'data1.dat'),
                  ('dq4_pc', 'sauvegardes', 'etats', 'etat_01.dqs'), ('dq4_pc', 'reglages.json'), ('dq4_pc', 'historique_favoris.json')):
            self.assertTrue(os.path.isfile(os.path.join(self.t, *p)), p)
        self.assertFalse(os.path.exists(os.path.join(self.t, 'dq4_pc', 'cache')), 'the cache is moved (same volume: a rename)')

    def test_nothing_overwritten_and_resume_does_not_repeat(self):
        write(os.path.join(self.t, 'data', 'settings', 'settings.json'), b'{"nouveau": 2}')                 # settings already changed in the new version: kept
        write(os.path.join(self.t, 'data', 'saves', 'portage', 'data1.dat'), b'NEUF')                       # yesterday's write folder: what the game wrote afterwards wins over the old port (P1)
        CH.migrate(self.d, log=lambda *a: None)
        self.assertEqual(self.read('data', 'settings', 'settings.json'), b'{"nouveau": 2}'); self.assertEqual(self.read('data', 'saves', 'dq4', 'data1.dat'), b'NEUF')
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])

    def test_what_you_erase_does_not_come_back(self):                                  # the deleted avant_import_... folder came back at every startup (copied again from dq4_pc\\sauvegardes)
        CH.migrate(self.d, log=lambda *a: None)
        av = os.path.join(self.t, 'data', 'saves', 'dq4', 'before_import_20261101_101010'); self.assertTrue(os.path.isdir(av))
        shutil.rmtree(os.path.join(self.t, 'data', 'saves')); shutil.rmtree(os.path.join(self.t, 'data', 'settings'))        # (everything deleted: only the resume file prevents the copy)
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])
        for p in (('saves',), ('settings',)): self.assertFalse(os.path.exists(os.path.join(self.t, 'data', *p)), p)
        self.assertTrue(os.path.isfile(os.path.join(self.t, 'dq4_pc', 'sauvegardes', 'data1.dat')))              # (the old folder is still untouched)

    def test_layout_already_in_use_nothing_is_copied(self):                 # the resume took place with an older version, then avant_import_... was deleted by hand
        write(os.path.join(self.t, 'data', 'saves', 'dq4', 'data3.dat'), b'A_MOI'); write(os.path.join(self.t, 'data', 'settings', 'settings.json'), b'{}')
        write(os.path.join(self.t, 'data', 'cache', 'dq4', 'fr', 'x.pkl'), b'C'); write(os.path.join(self.t, 'data', 'apk', 'dq4', 'fr', 'base.apk'), b'A'); write(os.path.join(self.t, 'data', 'logs', 'window_errors.log'), b'J')
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])
        self.assertEqual(sorted(os.listdir(os.path.join(self.t, 'data', 'saves', 'dq4'))), ['data3.dat'])
        self.assertEqual(self.read('data', 'settings', 'settings.json'), b'{}')
        with open(self.d.resume_file, encoding='utf-8') as f: stages = __import__('json').load(f)['stages']
        self.assertEqual(sorted(stages), sorted(set(CH.STAGES) - {CH.ENGLISH_STAGE})); self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])         # (nothing to rename: the stage is not noted)

    def test_saves_go_into_the_game_folder(self):                       # (16/11) one folder per game: what data\\saves held goes into data\\saves\\dq4, the other games' folders stay
        sv = os.path.join(self.t, 'data', 'saves')
        write(os.path.join(sv, 'data1.dat'), b'D1'); write(os.path.join(sv, 'savestates', '0000abcd', 'state_01.dqs'), b'E1'); write(os.path.join(sv, 'rules', '0000abcd.json'), b'{}')
        write(os.path.join(sv, 'dq4', 'data2.dat'), b'D2'); write(os.path.join(sv, 'dq4', 'data1.dat'), b'NEWER'); os.makedirs(os.path.join(sv, 'dq5', 'rules')); os.makedirs(os.path.join(sv, 'dq6'))
        done = CH.saves_into_game_folder(self.d)
        self.assertEqual(sorted(os.listdir(sv)), ['data1.dat', 'dq4', 'dq5', 'dq6'])                          # (data1.dat already in dq4: never overwritten, left where it is)
        self.assertEqual(self.read('data', 'saves', 'dq4', 'data1.dat'), b'NEWER'); self.assertEqual(self.read('data', 'saves', 'dq4', 'data2.dat'), b'D2')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', '0000abcd', 'state_01.dqs'), b'E1'); self.assertEqual(self.read('data', 'saves', 'dq4', 'rules', '0000abcd.json'), b'{}')
        self.assertTrue(any('moved' in x for x in done) and any('data1.dat' in x and 'NOT moved' in x for x in done), done)
        self.assertTrue(os.path.isdir(os.path.join(sv, 'dq5', 'rules')))
        os.remove(os.path.join(sv, 'data1.dat')); self.assertEqual(CH.saves_into_game_folder(self.d), [])     # (nothing left: nothing to do)

    def test_unreadable_migration_file(self):
        write(self.d.resume_file, b'{pas du json')
        done = CH.migrate(self.d, log=lambda *a: None)                                                      # like a first time: copy without overwriting anything, then the file is redone
        self.assertGreaterEqual(len(done), 6); self.assertEqual(self.read('data', 'saves', 'dq4', 'data1.dat'), b'P1')
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])

    def test_a_stage_without_old_folder_writes_nothing(self):
        with tempfile.TemporaryDirectory() as empty:
            dv = CH.Folders(empty, env={}); self.assertEqual(CH.migrate(dv, log=lambda *a: None), []); self.assertFalse(os.path.exists(dv.resume_file)); self.assertFalse(os.path.exists(dv.data))

    def test_existing_cache_left_untouched(self):
        write(os.path.join(self.t, 'data', 'cache', 'autre.pkl'), b'N')
        CH.migrate(self.d, log=lambda *a: None)
        self.assertTrue(os.path.isfile(os.path.join(self.t, 'dq4_pc', 'cache', 'carte10_a.pkl'))); self.assertFalse(os.path.exists(os.path.join(self.t, 'data', 'cache', 'carte10_a.pkl')))

    def test_nothing_to_resume(self):
        with tempfile.TemporaryDirectory() as empty: self.assertEqual(CH.migrate(CH.Folders(empty, env={}), log=lambda *a: None), [])


class EnglishNames(unittest.TestCase):
    """the folders and files that earlier versions created in French are renamed in place (without copying, without overwriting or deleting anything)."""
    @classmethod
    def setUpClass(cls): LG.select_language('fr')                      # (the resume sentences are tested in French)

    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='en_'); self.d = CH.Folders(self.t, env={})
        o = os.path.join(self.t, 'donnees')                       # the layout, as it is on the PC
        write(os.path.join(o, 'apk', 'base.apk'), b'A'); write(os.path.join(o, 'cache', 'x.pkl'), b'C'); write(os.path.join(o, 'sauvegardes', 'data1.dat'), b'D1')
        write(os.path.join(o, 'sauvegardes', 'etats', 'etat_01.dqs'), b'E1'); write(os.path.join(o, 'sauvegardes', 'etats', 'etat_09.dqs'), b'E9')
        write(os.path.join(o, 'sauvegardes', 'avant_import_20261101_101010', 'data2.dat'), b'AV'); write(os.path.join(o, 'sauvegardes', 'avant_import_20261101_101010', 'etats', 'etat_02.dqs'), b'AE')
        write(os.path.join(o, 'sauvegardes', 'avant_rangement_20261102_090000', 'portage', 'etats', 'etat_05.dqs'), b'ARCH')
        write(os.path.join(o, 'reglages', 'reglages.json'), b'{"a": 1}'); write(os.path.join(o, 'reglages', 'historique_favoris.json'), b'[]'); write(os.path.join(o, 'reglages', 'historique_messages.json'), b'[1]')
        write(os.path.join(o, 'journaux', 'erreurs_fenetre.log'), b'LOG')
        write(os.path.join(o, 'reprise.json'), b'{"etapes": {"cache": "01/11/2026", "sauvegardes_portage": "01/11/2026", "reglages": "en place", "journal": "en place"}}')

    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def read(self, *p):
        with open(os.path.join(self.t, *p), 'rb') as f: return f.read()

    def test_names(self):
        for old, new, is_dir in (('etats', 'savestates', True), ('etat_07.dqs', 'state_07.dqs', False), ('avant_import_20261101_101010', 'before_import_20261101_101010', True), ('avant_rangement_x', 'before_tidy_x', True),
                                 ('reglages.json', 'settings.json', False), ('reglages.json.tmp', 'settings.json.tmp', False), ('historique_favoris.json', 'history_favorites.json', False),
                                 ('erreurs_fenetre.log', 'window_errors.log', False), ('reprise.json', 'resume.json', False), ('sauvegardes', 'saves', True), ('journaux', 'logs', True)):
            self.assertEqual(CH.english_name(old, is_dir), new, old)
        for same, is_dir in (('data1.dat', False), ('cache', True), ('apk', True), ('state_01.dqs', False), ('portage', True), ('etat_1.dqs', False), ('etats', False)):
            self.assertIsNone(CH.english_name(same, is_dir), same)

    def test_complete_renaming(self):
        done = CH.migrate(self.d, log=lambda *a: None)
        self.assertTrue(any('donnees' in x and 'data' in x for x in done), done)
        self.assertFalse(os.path.exists(os.path.join(self.t, 'donnees')))
        self.assertEqual(self.read('data', 'apk', 'dq4', 'fr', 'base.apk'), b'A'); self.assertEqual(self.read('data', 'cache', 'dq4', 'fr', 'x.pkl'), b'C')          # (the cache of the old layout goes into `cache\\dq4\\fr`; the APK of the old layout goes straight into `apk\\fr`)
        self.assertEqual(self.read('data', 'saves', 'dq4', 'data1.dat'), b'D1')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_01.dqs'), b'E1'); self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_09.dqs'), b'E9')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'before_import_20261101_101010', 'data2.dat'), b'AV')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'before_import_20261101_101010', 'savestates', 'state_02.dqs'), b'AE')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'before_tidy_20261102_090000', 'portage', 'etats', 'etat_05.dqs'), b'ARCH')           # (the folders put away by the resume stay as they are)
        self.assertEqual(self.read('data', 'settings', 'settings.json'), b'{"a": 1}'); self.assertEqual(self.read('data', 'settings', 'history_favorites.json'), b'[]')
        self.assertEqual(self.read('data', 'settings', 'history_messages.json'), b'[1]'); self.assertEqual(self.read('data', 'logs', 'window_errors.log'), b'LOG')
        self.assertFalse(os.path.exists(os.path.join(self.t, 'data', 'reprise.json')))
        with open(self.d.resume_file, encoding='utf-8') as f: stages = __import__('json').load(f)['stages']
        self.assertEqual(sorted(stages), sorted(CH.STAGES)); self.assertEqual(stages['saves_pc_port'], '01/11/2026')                      # (old stage names translated, dates kept; the other stages: destination already in use; stage added)
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])                                                                    # (only once)

    def test_same_files_after_renaming(self):
        before = sorted((os.path.relpath(os.path.join(r, f), os.path.join(self.t, 'donnees')), open(os.path.join(r, f), 'rb').read())
                        for r, _, files in os.walk(os.path.join(self.t, 'donnees')) for f in files if f != 'reprise.json')
        CH.migrate(self.d, log=lambda *a: None)
        after = sorted((os.path.relpath(os.path.join(r, f), os.path.join(self.t, 'data')), open(os.path.join(r, f), 'rb').read())
                       for r, _, files in os.walk(os.path.join(self.t, 'data')) for f in files if f != 'resume.json')
        self.assertEqual([c for _, c in before], [c for _, c in sorted(after, key=lambda x: [b for a, b in before].index(x[1]))])        # (no content lost, none added)

    def test_nothing_overwritten_on_conflict(self):
        write(os.path.join(self.t, 'data', 'settings', 'settings.json'), b'{"nouveau": 2}')                  # a setting already exists at the new place: it wins, the old one stays where it is
        write(os.path.join(self.t, 'data', 'saves', 'savestates', 'state_01.dqs'), b'NEUF')
        done = CH.migrate(self.d, log=lambda *a: None)
        self.assertEqual(self.read('data', 'settings', 'settings.json'), b'{"nouveau": 2}'); self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_01.dqs'), b'NEUF')
        self.assertEqual(self.read('data', 'settings', 'reglages.json'), b'{"a": 1}'); self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'etat_01.dqs'), b'E1')      # (at their former place, intact)
        self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_09.dqs'), b'E9')                       # (the rest is renamed)
        self.assertTrue(any('kept where they are' in x for x in done), done)                                # (a single sentence for all names already taken)
        self.assertIn(CH.ENGLISH_STAGE, CH._read_resume(self.d))                                            # noted done from the first pass (a taken name will stay taken: repeating it every time teaches nothing)
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [], 'the resume must not speak again at the next launch')

    def test_both_folders_exist_merge(self):
        write(os.path.join(self.t, 'data', 'saves', 'data3.dat'), b'D3')                                   # `data\\saves` already exists (interrupted renaming): the rest is put back into it, one file at a time
        done = CH.migrate(self.d, log=lambda *a: None)
        self.assertEqual(self.read('data', 'saves', 'dq4', 'data3.dat'), b'D3'); self.assertEqual(self.read('data', 'saves', 'dq4', 'data1.dat'), b'D1')
        self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_01.dqs'), b'E1'); self.assertFalse(os.path.exists(os.path.join(self.t, 'donnees')))
        self.assertFalse(any('NOT renamed' in x for x in done), done)

    def test_locked_folder_falls_back_to_its_content(self):               # Windows: a folder open in Explorer cannot be renamed; its files, however, can be moved one by one
        actual = os.replace

        def refuse_folders(src, dst):
            if os.path.isdir(src): raise PermissionError('dossier ouvert')
            return actual(src, dst)
        with mock.patch('dq456_pc.paths.os.replace', side_effect=refuse_folders): done = CH.migrate(self.d, log=lambda *a: None)
        self.assertFalse(any('NOT renamed' in x for x in done), done); self.assertFalse(os.path.exists(os.path.join(self.t, 'donnees')))
        self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_01.dqs'), b'E1'); self.assertEqual(self.read('data', 'apk', 'dq4', 'fr', 'base.apk'), b'A'); self.assertEqual(self.read('data', 'settings', 'settings.json'), b'{"a": 1}')
        self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [])

    def test_nothing_can_be_renamed_then_it_is_retried(self):
        def refuse_all(src, dst): raise PermissionError('acces refuse')
        with mock.patch('dq456_pc.paths.os.replace', side_effect=refuse_all): done = CH.migrate(self.d, log=lambda *a: None)
        self.assertTrue(any('NOT renamed' in x and 'acces refuse' in x for x in done), done)
        self.assertEqual(self.read('donnees', 'sauvegardes', 'etats', 'etat_01.dqs'), b'E1'); self.assertEqual(self.read('donnees', 'sauvegardes', 'data1.dat'), b'D1')          # (nothing moved or disappeared)
        self.assertNotIn(CH.ENGLISH_STAGE, CH._read_resume(self.d))
        done = CH.migrate(self.d, log=lambda *a: None)                                                           # the next startup finishes the job
        self.assertFalse(any('NOT renamed' in x for x in done), done); self.assertEqual(self.read('data', 'saves', 'dq4', 'savestates', 'state_01.dqs'), b'E1')
        self.assertIn(CH.ENGLISH_STAGE, CH._read_resume(self.d))

    def test_english_sentences(self):
        for code, begins in (('fr', ('folders renamed to English: ', 'file(s) renamed to English')), ('en', ('folders renamed to English: ', 'file(s) renamed to English'))):
            shutil.rmtree(self.t); self.setUp(); LG.select_language(code)
            done = CH.migrate(self.d, log=lambda *a: None)
            for b in begins: self.assertTrue(any(b in x for x in done), (b, done))
        LG.select_language('fr')

    def test_custom_folder_is_not_renamed(self):                       # DQ_DATA / DQ_DATA / DQ4_DONNEES: the folder is yours, only its contents are renamed
        mine = os.path.join(self.t, 'mes_donnees'); shutil.move(os.path.join(self.t, 'donnees'), mine)
        for var in ('DQ_DATA', 'DQ4_DONNEES'):
            d = CH.Folders(self.t, env={var: mine})
            self.assertEqual(d.data, mine)
        CH.migrate(d, log=lambda *a: None)
        self.assertEqual(open(os.path.join(mine, 'saves', 'dq4', 'savestates', 'state_01.dqs'), 'rb').read(), b'E1'); self.assertFalse(os.path.exists(os.path.join(self.t, 'data')))

    def test_old_variable_names_still_work(self):
        self.assertEqual(CH.Folders('/p', env={'DQ4_DONNEES': '/x/d'}).data, os.path.normpath('/x/d'))
        self.assertEqual(CH.Folders('/p', env={'DQ4_JEUX': '/j/DQ4'}).apk, os.path.normpath('/j/DQ4/patched_apks'))
        self.assertEqual(CH.Folders('/p', env={'DQ_DATA': '/new', 'DQ4_DONNEES': '/old'}).data, os.path.normpath('/new'))                  # (the new name wins)

    def test_old_resume_file_is_read_before_renaming(self):
        shutil.move(os.path.join(self.t, 'donnees'), os.path.join(self.t, 'data'))                               # (folder already renamed, but the earlier `reprise.json`, with `etapes` and the old stage names, not yet)
        self.assertEqual(CH._read_resume(self.d).get('saves_pc_port'), '01/11/2026')

    def test_old_layout_copied_in_english_names(self):               # the resume of the very first layout already arrives with the right names (savestates, backups)
        with tempfile.TemporaryDirectory() as t:
            write(os.path.join(t, 'dq4_pc', 'sauvegardes', 'etats', 'etat_04.dqs'), b'E4'); write(os.path.join(t, 'dq4_pc', 'sauvegardes', 'avant_import_20261101_101010', 'etats', 'etat_06.dqs'), b'E6')
            write(os.path.join(t, 'dq4_pc', 'reglages.json'), b'{}'); write(os.path.join(t, 'dq4_pc', 'historique_messages.json'), b'[]'); write(os.path.join(t, 'dq4_pc', 'erreurs_fenetre.log'), b'L')
            d = CH.Folders(t, env={}); CH.migrate(d, log=lambda *a: None)
            for p in (('saves', 'dq4', 'savestates', 'state_04.dqs'), ('saves', 'dq4', 'before_import_20261101_101010', 'savestates', 'state_06.dqs'), ('settings', 'settings.json'), ('settings', 'history_messages.json'), ('logs', 'window_errors.log')):
                self.assertTrue(os.path.isfile(os.path.join(t, 'data', *p)), p)


def logfile(raw=0x3c00): return bytes(raw)


def valid_logfile(n=0):
    """A valid game adventure log ("rate" header, checksum, encrypted); `n` distinguishes it from the others."""
    import struct
    from dq456_pc.persistence import logfile_format as FJ
    plain = bytearray(FJ.LOGFILE_SIZE); struct.pack_into('<II', plain, 0, FJ.MAGIC1, FJ.MAGIC2); plain[0x30] = n
    struct.pack_into('<I', plain, 8, FJ.checksum(bytes(plain))); return FJ.decrypt(bytes(plain))


class Saves(unittest.TestCase):
    """Import / export with the data\\saves layout (savestates and copies next to `portage`)."""
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='sv_'); self.d = CH.Folders(self.t, env={}); self.before = CH.FOLDERS; CH.FOLDERS = self.d

    def tearDown(self): CH.FOLDERS = self.before; shutil.rmtree(self.t, ignore_errors=True)

    def test_import_in_usual_layout(self):
        write(os.path.join(self.d.portage, 'data1.dat'), valid_logfile(1)); write(os.path.join(self.d.savestates, 'state_01.dqs'), b'e' * 2000)
        zip_ = os.path.join(self.t, 'import.zip')
        with zipfile.ZipFile(zip_, 'w') as z: z.writestr('data1.dat', valid_logfile(2)); z.writestr('savestates/state_01.dqs', b'f' * 2000)
        nj, n_savestates, copied, pb = S.import_saves([zip_], self.d.portage, self.d.mobile)
        self.assertEqual((nj, n_savestates, pb), (1, 1, []))
        with open(os.path.join(self.d.portage, 'data1.dat'), 'rb') as f: self.assertEqual(f.read(), valid_logfile(2))
        with open(os.path.join(self.d.savestates, 'state_01.dqs'), 'rb') as f: self.assertEqual(f.read(), b'f' * 2000)
        self.assertEqual(os.path.dirname(copied), self.d.saves); self.assertTrue(os.path.basename(copied).startswith('before_import_'))
        with open(os.path.join(copied, 'data1.dat'), 'rb') as f: self.assertEqual(f.read(), valid_logfile(1))
        with open(os.path.join(copied, 'savestates', 'state_01.dqs'), 'rb') as f: self.assertEqual(f.read(), b'e' * 2000)

    def test_zip_from_before_english_names(self):                          # a .zip exported by an earlier version (`etats/etat_NN.dqs`) can be imported, the savestates are written under their new name
        zip_ = os.path.join(self.t, 'ancien.zip')
        with zipfile.ZipFile(zip_, 'w') as z: z.writestr('data1.dat', valid_logfile(2)); z.writestr('etats/etat_04.dqs', b'h' * 2000); z.writestr('ETATS/ETAT_05.DQS', b'i' * 2000)
        jr, label, pb = S.read_sources([zip_]); self.assertEqual((sorted(jr), sorted(label), pb), (['data1.dat'], ['state_04.dqs', 'state_05.dqs'], []))
        S.import_saves([zip_], self.d.portage, self.d.mobile)
        with open(os.path.join(self.d.savestates, 'state_04.dqs'), 'rb') as f: self.assertEqual(f.read(), b'h' * 2000)
        self.assertFalse(os.path.exists(os.path.join(self.d.savestates, 'etat_04.dqs')))

    def test_phone_manifest_json_is_ignored(self):                          # the game does not read manifest.json (file list + sha256 made by the copy tool); the adventure logs have their own check
        src = os.path.join(self.t, 'copie_telephone'); write(os.path.join(src, 'data3.dat'), valid_logfile(3)); write(os.path.join(src, 'manifest.json'), b'{"files": {"data3.dat": {"size": 15360, "sha256": "0"}}}')
        jr, label, pb = S.read_sources([src]); self.assertEqual((sorted(jr), label, pb), (['data3.dat'], {}, []))
        nj, n_savestates, copied, pb = S.import_saves([src], self.d.portage, self.d.mobile); self.assertEqual((nj, n_savestates, copied, pb), (1, 0, None, []))
        self.assertFalse(os.path.exists(os.path.join(self.d.portage, 'manifest.json')))

    def test_export_takes_savestates_from_right_folder(self):
        write(os.path.join(self.d.portage, 'data1.dat'), valid_logfile(1)); write(os.path.join(self.d.savestates, 'state_02.dqs'), b'e' * 2000)
        output = os.path.join(self.t, 'sortie.zip'); self.assertEqual(S.export_saves(self.d.portage, self.d.mobile, output), (1, 1))
        with zipfile.ZipFile(output) as z: self.assertEqual(sorted(z.namelist()), ['data1.dat', 'savestates/state_02.dqs'])

    def test_specific_write_folder(self):                            # (tests, --saves-write): everything stays under this folder
        wdir = os.path.join(self.t, 'autre'); write(os.path.join(wdir, 'data1.dat'), valid_logfile(1))
        zip_ = os.path.join(self.t, 'i.zip')
        with zipfile.ZipFile(zip_, 'w') as z: z.writestr('data1.dat', valid_logfile(2)); z.writestr('savestates/state_03.dqs', b'g' * 2000)
        _, _, copied, _ = S.import_saves([zip_], wdir, self.d.mobile)
        self.assertTrue(os.path.isfile(os.path.join(wdir, 'savestates', 'state_03.dqs'))); self.assertEqual(os.path.dirname(copied), wdir)


class OldSavestates(unittest.TestCase):
    def test_a_pickle_from_before_the_tidy_up_can_be_reread(self):
        from dq456_pc.core import engine as ENGINE
        e = ENGINE.State(); e.game_map = 1234
        # we build a pickle as the old version wrote it: the class's module was called `engine`
        old_dirs = (ENGINE.State.__module__, ENGINE.Interface.__module__); sys.modules['moteur'] = ENGINE
        try:
            ENGINE.State.__module__ = 'moteur'; ENGINE.Interface.__module__ = 'moteur'
            raw = pickle.dumps({'etat': e, 'ui': ENGINE.Interface()}, protocol=pickle.HIGHEST_PROTOCOL)
        finally:
            ENGINE.State.__module__, ENGINE.Interface.__module__ = old_dirs; del sys.modules['moteur']
        self.assertIn(b'moteur', raw); self.assertNotIn(b'dq456_pc', raw)
        with self.assertRaises(ModuleNotFoundError): pickle.loads(raw)               # (without the mapping, that is precisely the problem)
        p = SS._load(raw)
        self.assertIsInstance(p['etat'], ENGINE.State); self.assertEqual(p['etat'].game_map, 1234); self.assertIsInstance(p['ui'], ENGINE.Interface)

    def test_a_current_pickle_can_be_reread(self):
        from dq456_pc.core import engine as ENGINE
        self.assertEqual(SS._load(pickle.dumps(ENGINE.State())).__class__, ENGINE.State)

    def test_all_old_names_exist(self):
        for old, new in SS.OLD_MODULES.items():
            f = os.path.join(CH.ROOT, *new.split('.')) + '.py'
            self.assertTrue(os.path.isfile(f), '%s -> %s' % (old, new))


class GameLanguage(unittest.TestCase):                 # the APKs in the chosen language's folder serve as the game's base
    def setUp(self): self.t = tempfile.mkdtemp(prefix='lang_'); self.d = CH.Folders(self.t, env={})
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def test_each_language_has_its_apk_and_cache_folders(self):
        d = self.d
        self.assertEqual(d.apk_for('fr'), d.apk_fr); self.assertEqual(d.apk_for('en'), d.apk_en); self.assertNotEqual(d.apk_fr, d.apk_en)
        self.assertEqual(d.cache_for('fr'), d.cache); self.assertEqual(d.cache_for('en'), d.cache_en); self.assertNotEqual(d.cache, d.cache_en)

    def test_the_folder_of_the_chosen_language_is_used(self):
        write(os.path.join(self.d.apk_fr, 'base.apk')); write(os.path.join(self.d.apk_en, 'base.apk'))
        self.assertEqual(self.d.choose_apk('fr'), (self.d.apk_fr, 'fr')); self.assertEqual(self.d.choose_apk('en'), (self.d.apk_en, 'en'))

    def test_a_missing_language_falls_back_on_the_other_one(self):
        write(os.path.join(self.d.apk_fr, 'base.apk')); self.assertEqual(self.d.choose_apk('en'), (self.d.apk_fr, 'fr'))
        os.remove(os.path.join(self.d.apk_fr, 'base.apk')); write(os.path.join(self.d.apk_en, 'base.apk')); self.assertEqual(self.d.choose_apk('fr'), (self.d.apk_en, 'en'))

    def test_no_apk_at_all_keeps_the_chosen_language_folder(self):                       # (it is the one the startup error message does not name alone: it also cites the other)
        self.assertEqual(self.d.choose_apk('en'), (self.d.apk_en, 'en')); self.assertEqual(self.d.choose_apk('fr'), (self.d.apk_fr, 'fr'))

    def test_old_games_folder_stays_the_french_one(self):
        d = CH.Folders(self.t, env={'DQ4_JEUX': os.path.join(self.t, 'j', 'DQ4')})
        self.assertEqual(d.apk_fr, os.path.normpath(os.path.join(self.t, 'j', 'DQ4', 'patched_apks'))); self.assertEqual(d.apk_en, os.path.normpath(os.path.join(self.t, 'j', 'DQ4', 'patched_apks_en')))
        self.assertEqual(CH.split_apk_by_language(d), []); self.assertFalse(os.path.exists(d.apk_en))

    def test_flat_apk_files_move_into_fr_and_nothing_is_overwritten(self):
        write(os.path.join(self.d.apk_root, 'base.apk'), b'A'); write(os.path.join(self.d.apk_root, 'split_config.arm64_v8a.apk'), b'B'); write(os.path.join(self.d.apk_fr, 'base.apk'), b'DEJA')
        done = CH.split_apk_by_language(self.d)
        self.assertEqual(len(done), 1, done); self.assertIn('1 APK', done[0])                                                  # only the file missing from `fr` is moved
        self.assertTrue(os.path.isdir(self.d.apk_en)); self.assertEqual(sorted(os.listdir(self.d.apk_fr)), ['base.apk', 'split_config.arm64_v8a.apk'])
        with open(os.path.join(self.d.apk_fr, 'base.apk'), 'rb') as f: self.assertEqual(f.read(), b'DEJA')
        self.assertTrue(os.path.isfile(os.path.join(self.d.apk_root, 'base.apk')))                                           # (l'original reste a sa place : on ne remplace jamais)
        self.assertEqual(CH.split_apk_by_language(self.d), [])                                                              # (2nd startup: nothing left to move, silence)

    def test_language_folders_go_into_the_game_folder(self):            # (16/11) one folder per game: data\\apk\\fr and \\en go into data\\apk\\dq4, the other games' folders stay
        write(os.path.join(self.d.apk_root, 'fr', 'base.apk'), b'F'); write(os.path.join(self.d.apk_root, 'en', 'base.apk'), b'E'); write(os.path.join(self.d.apk_root, 'en', 'split_config.arm64_v8a.apk'), b'E2')
        write(os.path.join(self.d.apk_en, 'base.apk'), b'DEJA'); write(os.path.join(self.d.apk_root, 'dq5', 'fr', 'base.apk'), b'D5')
        done = CH.split_apk_by_language(self.d)
        with open(os.path.join(self.d.apk_fr, 'base.apk'), 'rb') as f: self.assertEqual(f.read(), b'F')
        with open(os.path.join(self.d.apk_en, 'base.apk'), 'rb') as f: self.assertEqual(f.read(), b'DEJA')                     # (never overwritten: the old one stays where it is)
        self.assertTrue(os.path.isfile(os.path.join(self.d.apk_en, 'split_config.arm64_v8a.apk'))); self.assertFalse(os.path.exists(os.path.join(self.d.apk_root, 'fr')))
        self.assertTrue(os.path.isfile(os.path.join(self.d.apk_root, 'en', 'base.apk'))); self.assertTrue(os.path.isfile(os.path.join(self.d.apk_root, 'dq5', 'fr', 'base.apk')))
        self.assertTrue(any('moved' in x for x in done) and any('NOT moved' in x for x in done), done)

    def test_first_installation_creates_nothing(self):
        self.assertEqual(CH.split_apk_by_language(self.d), []); self.assertFalse(os.path.exists(self.d.data))

    def test_the_english_cache_gets_only_the_ui_layout(self):
        write(os.path.join(self.d.cache, 'ui_layout.json'), b'{"a": 1}'); write(os.path.join(self.d.cache, 'tex_1.npy'), b'T')
        self.assertEqual(CH.language_cache(self.d, 'fr', log=lambda *a: None), self.d.cache); self.assertFalse(os.path.exists(self.d.cache_en))
        self.assertEqual(CH.language_cache(self.d, 'en', log=lambda *a: None), self.d.cache_en)
        self.assertEqual(os.listdir(self.d.cache_en), ['ui_layout.json'])
        CH.language_cache(self.d, 'en', log=lambda *a: None)                                                                  # (2e demarrage : rien a refaire)
        self.assertEqual(os.listdir(self.d.cache_en), ['ui_layout.json'])



class Games(unittest.TestCase):                        # one folder per game in apk, saves and cache; the settings are shared
    def test_each_game_has_its_folders(self):
        for g in ('dq4', 'dq5', 'dq6'):
            d = CH.Folders('/projet', env={}, game=g)
            self.assertEqual(d.game, g)
            for name_str, expected in (('apk_fr', 'data/apk/%s/fr'), ('apk_en', 'data/apk/%s/en'), ('saves', 'data/saves/%s'), ('portage', 'data/saves/%s'), ('savestates', 'data/saves/%s/savestates'),
                                       ('cache', 'data/cache/%s/fr'), ('cache_en', 'data/cache/%s/en')):
                self.assertEqual(getattr(d, name_str), os.path.normpath('/projet/' + expected % g), (g, name_str))
            self.assertEqual(d.settings, os.path.normpath('/projet/data/settings/settings.json'))

    def test_the_game_comes_from_dq_game(self):
        self.assertEqual(CH.Folders('/projet', env={}).game, 'dq4')
        self.assertEqual(CH.Folders('/projet', env={'DQ_GAME': 'DQ5'}).game, 'dq5')
        self.assertEqual(CH.Folders('/projet', env={'DQ_GAME': 'dq6'}, game='dq4').game, 'dq4')               # (an explicit game wins)
        with self.assertRaises(ValueError): CH.Folders('/projet', env={'DQ_GAME': 'dq7'})

    def test_for_game_keeps_the_data_folder(self):
        d = CH.Folders('/projet', env={'DQ_DATA': '/ailleurs/d'}, game='dq5')
        d4 = d.for_game('dq4')
        self.assertEqual((d4.game, d4.data, d4.apk_fr), ('dq4', d.data, os.path.normpath('/ailleurs/d/apk/dq4/fr')))
        self.assertIs(d.for_game('dq5'), d)

    def test_old_games_folder_is_dq4_only(self):
        self.assertIsNone(CH.Folders('/projet', env={'DQ4_GAMES': '/jeux/DQ4'}, game='dq5').old_games)
        self.assertEqual(CH.Folders('/projet', env={'DQ4_GAMES': '/jeux/DQ4'}, game='dq5').apk_fr, os.path.normpath('/projet/data/apk/dq5/fr'))


class CachePerGame(unittest.TestCase):                 # data\cache and data\cache_en (DQ4, earlier versions) -> data\cache\dq4\fr and \en
    def setUp(self): self.t = tempfile.mkdtemp(prefix='cache_'); self.d = CH.Folders(self.t, env={})
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)
    def read(self, *p):
        with open(os.path.join(self.t, 'data', *p), 'rb') as f: return f.read()

    def test_flat_caches_move_into_the_game_folder(self):
        c = os.path.join(self.t, 'data', 'cache'); ce = os.path.join(self.t, 'data', 'cache_en')
        write(os.path.join(c, 'map15_a.pkl'), b'M'); write(os.path.join(c, 'il2cpp', 'dump.cs'), b'D'); write(os.path.join(c, 'ui_layout.json'), b'{}')
        write(os.path.join(ce, 'map15_a.pkl'), b'ME'); write(os.path.join(c, 'dq5', 'fr', 'x.pkl'), b'D5')
        done = CH.cache_per_game(self.d)
        self.assertEqual(len(done), 1, done); self.assertIn('cache arranged by game', done[0])
        self.assertEqual(self.read('cache', 'dq4', 'fr', 'map15_a.pkl'), b'M'); self.assertEqual(self.read('cache', 'dq4', 'fr', 'il2cpp', 'dump.cs'), b'D')
        self.assertEqual(self.read('cache', 'dq4', 'en', 'map15_a.pkl'), b'ME'); self.assertEqual(self.read('cache', 'dq5', 'fr', 'x.pkl'), b'D5')          # (the other games' folders stay)
        self.assertEqual(sorted(os.listdir(c)), ['dq4', 'dq5']); self.assertFalse(os.path.exists(ce))
        self.assertEqual(CH.cache_per_game(self.d), [])                                                              # (2nd startup: nothing left to move, silence)

    def test_a_file_already_in_place_is_kept_silently(self):
        c = os.path.join(self.t, 'data', 'cache')
        write(os.path.join(c, 'a.pkl'), b'OLD'); write(os.path.join(c, 'dq4', 'fr', 'a.pkl'), b'NEW')
        self.assertEqual(CH.cache_per_game(self.d), [])                                                                # (only a cache: no message at each launch)
        self.assertEqual(self.read('cache', 'dq4', 'fr', 'a.pkl'), b'NEW'); self.assertEqual(self.read('cache', 'a.pkl'), b'OLD')       # (never overwritten, nothing deleted)

    def test_first_installation_creates_nothing(self):
        self.assertEqual(CH.cache_per_game(self.d), []); self.assertFalse(os.path.exists(self.d.data))

    def test_migration_works_on_dq4_whatever_the_game(self):                # the old layouts are DQ4's: launching DQ5 first still puts them into the dq4 folders
        sv = os.path.join(self.t, 'data', 'saves')
        write(os.path.join(sv, 'data1.dat'), b'D1'); write(os.path.join(self.t, 'data', 'cache', 'x.pkl'), b'C'); write(os.path.join(self.t, 'data', 'apk', 'base.apk'), b'A')
        CH.migrate(CH.Folders(self.t, env={}, game='dq5'), log=lambda *a: None)
        self.assertEqual(self.read('saves', 'dq4', 'data1.dat'), b'D1'); self.assertEqual(self.read('cache', 'dq4', 'fr', 'x.pkl'), b'C'); self.assertEqual(self.read('apk', 'dq4', 'fr', 'base.apk'), b'A')
        self.assertFalse(os.path.exists(os.path.join(sv, 'dq5'))); self.assertFalse(os.path.exists(os.path.join(self.t, 'data', 'apk', 'dq5')))

    def test_the_english_cache_gets_the_ui_layout_of_its_game(self):
        d = CH.Folders(self.t, env={}, game='dq5')
        write(os.path.join(d.cache, 'ui_layout.json'), b'{"a": 1}')
        self.assertEqual(CH.language_cache(d, 'en', log=lambda *a: None), os.path.join(self.t, 'data', 'cache', 'dq5', 'en'))
        self.assertEqual(os.listdir(d.cache_en), ['ui_layout.json'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
