"""Test of the migration from the old layout: it no longer repeats when a name is already taken.

**.** When `etat_01.dqs` and `state_01.dqs` exist side by side (or 300 cache files with the same name), `english_names` does not rename, overwrites nothing (good), but the step was never recorded in
`resume.json`: the same sentence came back **at every launch** — and even **twice per launch**, because `launch_dq4.bat` calls `python -m dq456_pc.paths` and `main` calls `migrate` again.
Now a name already taken records the step as done (that name will stay taken: repeating it teaches nothing) and the conflicts fit in ONE sentence; only a rename that FAILS (locked folder, permissions) leaves the step
open and is retried. Nothing is ever overwritten or deleted: the old file stays where it is, and this is said once.

**.** `launch_dq4.bat` hard-coded `data\\cache` for the menu layout although it itself recommends `DQ_DATA`: with a data folder of one's own, either it announced "menus simples"
wrongly, or the layout was never redone. The folder now comes from `python -m dq456_pc.paths --cache`.

    python3 tests/test_migration_repeats.py
No screen, no GL, no APK (everything happens in temporary folders).
"""
import io, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from dq456_pc import paths as CH


class Conflict(unittest.TestCase):
    """Audit scenario S6: one savestate under its old name and one under the new name."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='reprise_')
        self.d = CH.Folders(self.root)
        os.makedirs(self.d.savestates, exist_ok=True)
        for name_str in ('etat_01.dqs', 'state_01.dqs'):
            with open(os.path.join(self.d.savestates, name_str), 'wb') as f: f.write(name_str.encode())

    def tearDown(self): shutil.rmtree(self.root, ignore_errors=True)

    def test_said_once_then_never_again(self):
        first = CH.migrate(self.d, log=lambda *a: None)
        self.assertTrue(any('already exists' in line or 'kept where they are' in line for line in first), first)
        for run in range(2, 5):
            self.assertEqual(CH.migrate(self.d, log=lambda *a: None), [], 'launch %d: the resume speaks again' % run)

    def test_the_stage_is_noted(self):
        CH.migrate(self.d, log=lambda *a: None)
        with open(self.d.resume_file, encoding='utf-8') as f: stages = json.load(f)['stages']
        self.assertIn(CH.ENGLISH_STAGE, stages, stages)

    def test_nothing_is_lost(self):
        CH.migrate(self.d, log=lambda *a: None)
        for name_str in ('etat_01.dqs', 'state_01.dqs'):
            p = os.path.join(self.d.savestates, name_str)
            self.assertTrue(os.path.isfile(p), name_str)
            with open(p, 'rb') as f: self.assertEqual(f.read(), name_str.encode(), 'contenu ecrase : ' + name_str)

    def test_one_sentence_for_many_conflicts(self):
        """Scenario S9: 300 names already taken do not make 300 console lines."""
        for i in range(300):
            for prefix in ('etat_', 'state_'):
                with open(os.path.join(self.d.savestates, '%s%02d.dqs' % (prefix, i % 100)), 'wb') as f: f.write(b'x')
        lines = CH.migrate(self.d, log=lambda *a: None)
        self.assertLessEqual(len(lines), 3, lines)
        self.assertTrue(any(re.search(r'\d+ old file\(s\) kept', line) for line in lines), lines)


class LockedFolder(unittest.TestCase):
    def test_a_failed_rename_is_retried(self):
        """A FAILURE (locked folder, permissions) is not a name already taken: the step stays open and the rename is retried at the next startup."""
        root = tempfile.mkdtemp(prefix='reprise_bloquee_')
        try:
            d = CH.Folders(root); os.makedirs(d.data, exist_ok=True)
            os.makedirs(os.path.join(d.data, 'etats'), exist_ok=True)
            real = os.replace
            def refuse(a, b, *rest):
                if 'savestates' in str(b): raise OSError(13, 'Permission denied')
                return real(a, b, *rest)
            os.replace = refuse
            try: CH.migrate(d, log=lambda *a: None)
            finally: os.replace = real
            self.assertNotIn(CH.ENGLISH_STAGE, CH._read_resume(d), 'a failure must not close the step')
        finally: shutil.rmtree(root, ignore_errors=True)


class CacheFolderForTheBat(unittest.TestCase):
    def test_paths_prints_the_cache_folder(self):
        root = tempfile.mkdtemp(prefix='donnees_a_moi_')
        try:
            env = dict(os.environ, DQ_DATA=root); env.pop('DQ4_DONNEES', None)
            out = subprocess.run([sys.executable, '-m', 'dq456_pc.paths', '--cache'], cwd=ROOT, capture_output=True, timeout=120, env=env)
            printed = out.stdout.decode('utf-8', 'replace').strip().splitlines()
            self.assertEqual(len(printed), 1, 'a single line, read by a CMD `for /f`: %r' % printed)
            self.assertTrue(os.path.normcase(printed[0]).startswith(os.path.normcase(root)), (printed, root))
            self.assertEqual(out.stderr, b'')
        finally: shutil.rmtree(root, ignore_errors=True)

    def test_the_bat_no_longer_writes_the_cache_folder_by_hand(self):
        with io.open(os.path.join(ROOT, 'tools', 'launch_game.bat'), encoding='utf-8') as f: bat = f.read()
        block = bat.split('--- 2b.')[1].split('--- 3.')[0]
        self.assertIn('dq456_pc.paths --cache', block)
        self.assertNotIn('data\\cache\\ui_layout.json', block)
        self.assertNotIn('data\\cache\\il2cpp', block)
        self.assertNotIn("open('data/cache", block)


if __name__ == '__main__':
    unittest.main(verbosity=2)
