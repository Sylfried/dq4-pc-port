"""The games of the port (games.py): one profile per game, chosen by DQ_GAME or `python -m dq456_pc --game X` before anything else is imported.
The three games run; a game this version would not run only has its files checked (main.NOT_PLAYABLE, exit code 3: the launcher keeps the console open, without an error message).
A game whose APK is not a readable APK stops with exit code 1, naming its folder.

    python3 tests/test_games.py"""
import os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)
from dq456_pc import games as GM


class Profiles(unittest.TestCase):
    def test_the_three_games(self):
        self.assertEqual(sorted(GM.GAMES), ['dq4', 'dq5', 'dq6'])
        for key, p in GM.GAMES.items():
            self.assertEqual(p.key, key)
            self.assertEqual(p.library, 'lib/arm64-v8a/lib%score.so' % key)
            self.assertTrue(p.name.startswith('Dragon Quest '))
        self.assertTrue(all(p.playable for p in GM.GAMES.values()))
        self.assertEqual([GM.GAMES[k].title_map for k in ('dq4', 'dq5', 'dq6')], ['ev01', 'ev17', 'e02din1'])

    def test_choice(self):
        self.assertEqual(GM.profile(env={}).key, 'dq4')
        self.assertEqual(GM.profile(env={'DQ_GAME': ' DQ6 '}).key, 'dq6')
        self.assertEqual(GM.profile('dq5', env={'DQ_GAME': 'dq6'}).key, 'dq5')
        with self.assertRaises(ValueError): GM.profile('dq7', env={})

    def test_game_from_argv(self):
        self.assertIsNone(GM.game_from_argv(['--slot', '2']))
        self.assertEqual(GM.game_from_argv(['--no-logos', '--game', 'dq5']), 'dq5')
        self.assertEqual(GM.game_from_argv(['--game=dq6', '--slot', '1']), 'dq6')

    def test_the_engine_library_follows_the_game(self):
        with open(os.path.join(ROOT, 'dq456_pc', 'core', 'engine.py'), encoding='utf-8') as f: src = f.read()
        self.assertIn('LIB_APK = GM.profile().library', src)


def import_environment():
    """The extra environment with which `dq456_pc.main` (pyglet) can be imported here: none (a display, or xvfb), else PYGLET_HEADLESS=1; None if neither works."""
    for extra in ({}, {'PYGLET_HEADLESS': '1'}):
        r = subprocess.run([sys.executable, '-c', 'import dq456_pc.main'], cwd=ROOT, capture_output=True, timeout=120, env=dict(os.environ, **extra))
        if r.returncode == 0: return extra
    return None


class Launch(unittest.TestCase):
    """`python -m dq456_pc --game X` in a separate process, with a data folder of its own (DQ_DATA)."""
    @classmethod
    def setUpClass(cls):
        cls.extra = import_environment()
        if cls.extra is None: raise unittest.SkipTest('dq456_pc.main cannot be imported here (pyglet without a display)')

    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='games_'); self.data = os.path.join(self.t, 'data')
        self.env = dict(os.environ, DQ_DATA=self.data, **self.extra); self.env.pop('DQ_GAME', None); self.env.pop('DQ4_DONNEES', None); self.env.pop('DQ4_GAMES', None); self.env.pop('DQ4_JEUX', None)

    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def run_port(self, *args, env=None):
        return subprocess.run([sys.executable, '-m', 'dq456_pc'] + list(args), cwd=ROOT, capture_output=True, timeout=180, env=env or self.env)

    def test_dq_game_chooses_the_game(self):
        """DQ_GAME=dq6 runs Dragon Quest VI: with an unreadable base.apk, it stops on its own APK folder (not DQ IV's)."""
        folder = os.path.join(self.data, 'apk', 'dq6', 'fr'); os.makedirs(folder)
        with open(os.path.join(folder, 'base.apk'), 'wb') as f: f.write(b'x')
        r = self.run_port(env=dict(self.env, DQ_GAME='dq6'))
        out = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
        self.assertNotEqual(r.returncode, 0, out); self.assertIn(os.path.join('apk', 'dq6'), out)

    def test_missing_apk_files_name_the_game_folder(self):
        r = self.run_port('--game', 'dq6')
        out = r.stdout.decode('utf-8', 'replace')
        self.assertEqual(r.returncode, 1, out)
        self.assertIn('The APK files of Dragon Quest VI were not found', out); self.assertIn(os.path.join('apk', 'dq6', 'fr'), out)
        self.assertTrue(os.path.isdir(os.path.join(self.data, 'apk', 'dq6', 'en')))           # (the two folders are made ready for the player)
        self.assertFalse(os.path.exists(os.path.join(self.data, 'apk', 'dq4')))

    def test_unknown_game(self):
        r = self.run_port('--game', 'dq7')
        self.assertEqual(r.returncode, 2); self.assertIn('unknown game "dq7"', r.stdout.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main(verbosity=1)
