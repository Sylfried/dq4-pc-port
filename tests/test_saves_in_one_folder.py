"""A single saves folder (all the files in one folder, like the savestates, so that saves copied from the phone need no sorting), without window or engine:

  1. layout: `data\\saves` receives data1.dat to data5.dat, data9.dat AND `savestates\\` (like the export .zip); `portage` is now just another name for this folder;
  2. resume of the old `saves\\portage` and `saves\\mobile\\<date>` at startup: the adventure logs are COPIED into `saves\\` (the port first, then the most recent phone copy, without overwriting anything: what the game read
     before, file by file), then the two old folders are MOVED as they are into `before_tidy_<date>\\`; nothing is deleted, a second resume does nothing;
  3. A real case: port files older than the phone's, `manifest.json` in the phone copy, old `dq4_pc\\sauvegardes` still there (must not take precedence over today's files);
  4. safety: an adventure log already placed in `saves\\` is not overwritten, a move error leaves everything in place (the game already reads `saves\\`), DQ4_JEUX (phone copy elsewhere) is not touched;
  5. the engine reads this folder (`effective_files`), the export flattens it and the import writes into it.

    python3 tests/test_saves_in_one_folder.py
"""
import os, shutil, sys, tempfile, unittest, zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import language as _LANGUAGE; _LANGUAGE.select_language('fr')          # (these tests expect the French texts, whatever the computer's language)
from dq456_pc import paths as CH
from dq456_pc.persistence import saves as S

NAMES = CH.LOGFILE_NAMES


def write(path, content=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(content)
    return path


def content(*p):
    with open(os.path.join(*p), 'rb') as f: return f.read()


def all_files(root):
    return sorted(os.path.relpath(os.path.join(r, f), root) for r, _, fs in os.walk(root) for f in fs)


class Layout(unittest.TestCase):
    def test_a_single_folder(self):
        d = CH.Folders('/projet', env={})
        self.assertEqual(d.portage, d.saves); self.assertEqual(d.savestates, os.path.join(d.saves, 'savestates'))
        self.assertEqual(d.savestates_folder(d.portage), os.path.join(d.saves, 'savestates')); self.assertEqual(d.clones_folder(d.portage), d.saves)

    def test_game_file_names(self):
        self.assertEqual(NAMES, ('data1.dat', 'data2.dat', 'data3.dat', 'data4.dat', 'data5.dat', 'data9.dat')); self.assertEqual(S.NAMES, NAMES)

    def test_no_code_still_stores_in_port(self):
        """The `portage` folder now exists only as an old name (paths.py: resumed then tidied away); no other module builds it."""
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dq456_pc')
        for folder, _d, files in os.walk(root):
            for f in files:
                if f.endswith('.py') and f != 'paths.py':
                    with open(os.path.join(folder, f), encoding='utf-8') as fh: src = fh.read()
                    self.assertNotIn("'portage'", src, f); self.assertNotIn('sauvegardes\\\\portage', src, f)


class Resume(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='un_dossier_'); self.d = CH.Folders(self.t, env={}); self.sv = self.d.saves

    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def migrate(self, d=None): return CH.migrate(d or self.d, log=lambda *a: None)

    def real_layout(self):
        """A real layout: port (data1, data5, data9 from that day; data2 to data4 older), a more recent phone copy for data2 to data4, plus a manifest, and an old dq4_pc\\sauvegardes."""
        for name_str in ('data1.dat', 'data5.dat', 'data9.dat'): write(os.path.join(self.d.old_port_dir, name_str), b'portage_' + name_str.encode())
        for name_str in ('data2.dat', 'data3.dat', 'data4.dat'): write(os.path.join(self.d.old_port_dir, name_str), b'portage_vieux_' + name_str.encode())
        phone = os.path.join(self.d.mobile, '20261103_222423')
        for name_str in NAMES: write(os.path.join(phone, name_str), b'tel_' + name_str.encode())
        write(os.path.join(phone, 'manifest.json'), b'{"device": "SM S938B"}'); write(os.path.join(self.d.mobile, '20261007_190735', 'data1.dat'), b'tel_ancien')
        write(os.path.join(self.sv, 'before_import_20261101_192625', 'data2.dat'), b'AV'); write(os.path.join(self.d.savestates, 'state_01.dqs'), b'E1')
        write(os.path.join(self.t, 'dq4_pc', 'sauvegardes', 'data1.dat'), b'tres_vieux'); write(os.path.join(self.t, 'dq4_pc', 'sauvegardes', 'data3.dat'), b'tres_vieux3')

    def test_logfiles_moved_up_into_saves(self):
        self.real_layout(); done = self.migrate()
        self.assertTrue(any('old folders moved' in ph for ph in done), done)
        for name_str in ('data1.dat', 'data5.dat', 'data9.dat'): self.assertEqual(content(self.sv, name_str), b'portage_' + name_str.encode(), name_str)                  # the port (what the game used to write) takes precedence
        for name_str in ('data2.dat', 'data3.dat', 'data4.dat'): self.assertEqual(content(self.sv, name_str), b'portage_vieux_' + name_str.encode(), name_str)            # ... even if older: as before (no choice by date)
        self.assertEqual(sorted(f for f in os.listdir(self.sv) if f.endswith('.dat')), sorted(NAMES))

    def test_phone_copy_completes_what_is_missing(self):
        write(os.path.join(self.d.old_port_dir, 'data1.dat'), b'portage1')
        for name_str in NAMES: write(os.path.join(self.d.mobile, '20261103_222423', name_str), b'tel_' + name_str.encode())
        write(os.path.join(self.d.mobile, '20261007_190735', 'data3.dat'), b'tel_ancien3'); write(os.path.join(self.d.mobile, '20261007_190735', 'data1.dat'), b'tel_ancien1')
        self.migrate()
        self.assertEqual(content(self.sv, 'data1.dat'), b'portage1'); self.assertEqual(content(self.sv, 'data3.dat'), b'tel_data3.dat')                     # the most recent copy, not an older one

    def test_old_folders_tidied_as_is_nothing_lost(self):
        self.real_layout(); before = set(all_files(self.sv)); self.migrate()
        placement = [x for x in os.listdir(self.sv) if x.startswith('before_tidy_')]; self.assertEqual(len(placement), 1)
        for under in ('portage', 'mobile'): self.assertFalse(os.path.exists(os.path.join(self.sv, under)), under)                                      # no more portage\ or mobile\
        r = os.path.join(self.sv, placement[0])
        self.assertEqual(content(r, 'portage', 'data2.dat'), b'portage_vieux_data2.dat'); self.assertEqual(content(r, 'mobile', '20261103_222423', 'manifest.json'), b'{"device": "SM S938B"}')
        self.assertEqual(content(r, 'mobile', '20261007_190735', 'data1.dat'), b'tel_ancien')
        after = set(all_files(self.sv))
        for f in before:                                                                                                                                # each earlier file is where it was put away, with the same content
            if f.startswith(('portage' + os.sep, 'mobile' + os.sep)): self.assertIn(os.path.join(placement[0], f), after, f)
            else: self.assertIn(f, after, f)
        self.assertEqual(content(self.sv, 'savestates', 'state_01.dqs'), b'E1'); self.assertEqual(content(self.sv, 'before_import_20261101_192625', 'data2.dat'), b'AV')    # savestates and import copies: in their place

    def test_a_second_resume_does_nothing(self):
        self.real_layout(); self.migrate(); before = all_files(self.t)
        self.assertEqual(self.migrate(), []); self.assertEqual(all_files(self.t), before)

    def test_old_dq4_pc_folder_does_not_outrank_todays_files(self):
        """There is still a `dq4_pc\\sauvegardes` from before the first tidy-up (a copy, not a move): its old data1 and data3 must not replace those of the port."""
        self.real_layout(); self.migrate()
        self.assertEqual(content(self.sv, 'data1.dat'), b'portage_data1.dat'); self.assertEqual(content(self.sv, 'data3.dat'), b'portage_vieux_data3.dat')
        self.assertEqual(content(self.t, 'dq4_pc', 'sauvegardes', 'data1.dat'), b'tres_vieux')                                                      # (and it is not touched)

    def test_save_file_already_in_saves_is_not_overwritten(self):
        """The phone's data files are already copied into `saves\\`: they win; those of the old port are not lost (put away)."""
        write(os.path.join(self.sv, 'data1.dat'), b'copie_du_telephone'); write(os.path.join(self.d.old_port_dir, 'data1.dat'), b'ancien_portage'); write(os.path.join(self.d.old_port_dir, 'data2.dat'), b'portage2')
        self.migrate()
        self.assertEqual(content(self.sv, 'data1.dat'), b'copie_du_telephone'); self.assertEqual(content(self.sv, 'data2.dat'), b'portage2')
        r = os.path.join(self.sv, [x for x in os.listdir(self.sv) if x.startswith('before_tidy_')][0]); self.assertEqual(content(r, 'portage', 'data1.dat'), b'ancien_portage')

    def test_nothing_to_tidy(self):
        write(os.path.join(self.sv, 'data1.dat'), b'a'); self.assertEqual(self.migrate(), []); self.assertEqual(all_files(self.sv), ['data1.dat'])

    def test_empty_folder_is_tidied_without_copying(self):
        os.makedirs(self.d.old_port_dir); self.migrate()
        self.assertFalse(os.path.exists(self.d.old_port_dir)); self.assertEqual(sorted(f for f in os.listdir(self.sv) if f.endswith('.dat')), [])

    def test_a_move_error_leaves_everything_in_place(self):
        self.real_layout()
        actual = os.replace

        def refuse_folders(src, dst):                                    # Windows: a folder with an open file in it cannot be moved; the file copies (tmp -> destination) go through
            if os.path.isdir(src): raise PermissionError('fichier ouvert')
            return actual(src, dst)
        with mock.patch('dq456_pc.paths.os.replace', side_effect=refuse_folders):
            done = self.migrate()
        self.assertTrue(any('NOT moved' in ph and 'fichier ouvert' in ph for ph in done), done)
        self.assertTrue(os.path.isdir(self.d.old_port_dir) and os.path.isdir(self.d.mobile))                                                            # nothing moved
        self.assertEqual(content(self.sv, 'data1.dat'), b'portage_data1.dat')                                                                           # (the game already reads sauvegardes: copy made before the move)
        done = self.migrate()                                                                                                                           # then the next resume finishes the job
        self.assertTrue(any('old folders moved' in ph for ph in done), done); self.assertFalse(os.path.exists(self.d.old_port_dir))

    def test_a_file_that_cannot_be_placed_stops_the_tidy_up(self):
        """A folder named `data1.dat` occupies the spot: the port's adventure log could not be copied, so the old folder does not move."""
        write(os.path.join(self.d.old_port_dir, 'data1.dat'), b'portage1'); os.makedirs(os.path.join(self.sv, 'data1.dat'))
        done = self.migrate()
        self.assertTrue(any('NOT moved' in ph and 'data1.dat' in ph for ph in done), done); self.assertTrue(os.path.isfile(os.path.join(self.d.old_port_dir, 'data1.dat')))

    def test_dq4_games_phone_copy_is_not_touched(self):
        games = os.path.join(self.t, 'ailleurs', 'DQ4'); d = CH.Folders(self.t, env={'DQ4_GAMES': games})
        for name_str in NAMES: write(os.path.join(games, 'saves', '20261007_190735', name_str), b'tel_' + name_str.encode())
        write(os.path.join(d.saves, 'portage', 'data1.dat'), b'p')
        self.assertEqual(CH.migrate(d, log=lambda *a: None), [])
        self.assertTrue(os.path.isfile(os.path.join(games, 'saves', '20261007_190735', 'data1.dat'))); self.assertTrue(os.path.isfile(os.path.join(d.saves, 'portage', 'data1.dat')))
        self.assertTrue(d.recent_mobile_save().endswith('20261007_190735'))                                                                      # (the game still reads it second)


class WithEngineAndZips(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='un_dossier_zip_'); self.d = CH.Folders(self.t, env={}); self.before = CH.FOLDERS; CH.FOLDERS = self.d

    def tearDown(self): CH.FOLDERS = self.before; shutil.rmtree(self.t, ignore_errors=True)

    def test_copying_phone_files_is_enough(self):
        """The intended gesture: the phone's data1.dat... in `saves\\`, nothing else; the engine reads them (write folder first) and the export puts them flat with the savestates."""
        for name_str in NAMES: write(os.path.join(self.d.saves, name_str), b'tel_' + name_str.encode())
        write(os.path.join(self.d.savestates, 'state_01.dqs'), b'e' * 2000)
        self.assertEqual(sorted(S.effective_files(self.d.portage, None)), sorted(NAMES))
        output = os.path.join(self.t, 'sortie.zip'); self.assertEqual(S.export_saves(self.d.portage, None, output), (6, 1))
        with zipfile.ZipFile(output) as z: self.assertEqual(sorted(z.namelist()), sorted(NAMES + ('savestates/state_01.dqs',)))

    def test_folder_content_is_that_of_zip(self):
        """What the export puts in the .zip is what the folder contains (apart from the backups): the folder is copied from one PC to another the way the .zip is unzipped."""
        for name_str in NAMES: write(os.path.join(self.d.saves, name_str), b'j' + name_str.encode())
        write(os.path.join(self.d.savestates, 'state_02.dqs'), b'e' * 2000); write(os.path.join(self.d.saves, 'before_import_20261101_101010', 'data1.dat'), b'AV')
        output = os.path.join(self.t, 'sortie.zip'); S.export_saves(self.d.portage, None, output)
        with zipfile.ZipFile(output) as z: in_zip = sorted(z.namelist())
        folder = sorted(f.replace(os.sep, '/') for f in all_files(self.d.saves) if not f.startswith('before_'))
        self.assertEqual(in_zip, folder)


if __name__ == '__main__':
    unittest.main(verbosity=1)
