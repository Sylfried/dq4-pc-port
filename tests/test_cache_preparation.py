"""Test of the map cache preparation process: it exits cleanly, and no test hard-codes the cache prefix.

1. **Exit code.** `Game._launch_preparation` launches `python -m dq4_pc.world.data <apk> <cache>` with `stdin=subprocess.PIPE` at every startup. The module's `__main__` reads standard input in a `daemon` thread
   to know when the game stops. When the preparation finishes before the game (cache already complete: the usual case), the interpreter shut down while that thread held the lock of the buffered
   reader: `Fatal Python error: _enter_buffered_busy` and code 134 (SIGABRT) — on Windows, a "python.exe has stopped working" window at every launch.

2. **Cache prefix.** It goes up with each format change (`carte10_` -> `carte11_`). Four test files had hard-coded it and have been **silently skipping** ever since: the 194 real chests,
   drawers and doors were no longer checked, and two files failed. The prefix is now read from `world/data.MAP_PREFIX`; this test refuses to let it come back hard-coded.

    python3 tests/test_cache_preparation.py
Without a screen, without GL, without an APK (case 1 launches the module with an empty APK folder: it exits without preparing anything).
"""
import glob, os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from dq4_pc.world.data import MAP_PREFIX


class Exit(unittest.TestCase):
    def test_leaves_without_aborting_with_the_pipe_still_open(self):
        """As the game launches it: standard input as a pipe **kept open** (that is the condition of the defect; `subprocess.run` would close it right away and the abort would not happen).
        Before: code -6 (SIGABRT) and `Fatal Python error: _enter_buffered_busy` on standard error, measured in 1.2 s."""
        p = subprocess.Popen([sys.executable, '-m', 'dq4_pc.world.data', tempfile.mkdtemp(prefix='apk_vide_'), tempfile.mkdtemp(prefix='cache_')],
                             cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try: code = p.wait(timeout=300)
        except subprocess.TimeoutExpired: p.kill(); self.fail('the preparation process does not end')
        err = p.stderr.read().decode('utf-8', 'replace')
        self.assertNotIn('_enter_buffered_busy', err, err[-800:])
        self.assertGreaterEqual(code, 0, 'killed by signal %d: %s' % (-code, err[-800:]))
        self.assertEqual(code, 0, err[-800:])

    def test_the_exit_is_guarded(self):
        """The exit is in a `finally`: a preparation that raises must not reopen the door to the abort."""
        import inspect
        from dq4_pc.world import data as DO
        tail = inspect.getsource(DO).split("if __name__ == '__main__':")[1]
        self.assertIn('finally:', tail); self.assertIn('os._exit(0)', tail)
        self.assertLess(tail.index('finally:'), tail.index('os._exit(0)'))
        self.assertIn('flush()', tail.split('finally:')[1].split('os._exit')[0], 'the output must be flushed before os._exit')


class Prefix(unittest.TestCase):
    OTHER = re.compile(r"""['\"](?:carte|map)(\d+)_""")

    def test_no_test_writes_the_prefix_by_hand(self):
        """Only the tests of the PURGE of old caches may name a `map<n>_` or `carte<n>_`: they precisely check that it disappears."""
        purge = {'test_fld_priority.py', 'test_map_textures.py', 'test_paths.py', 'test_window_language.py'}
        version = MAP_PREFIX.strip('_').replace('map', '')
        wrong = []
        for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_*.py'))):
            if os.path.basename(f) in purge: continue
            with open(f, encoding='utf-8') as fh: src = fh.read()
            for n in set(self.OTHER.findall(src)): wrong.append('%s : map%s_' % (os.path.basename(f), n))
        self.assertEqual(wrong, [], 'hard-coded prefix (the current one is map%s_, see world/data.MAP_PREFIX): %s' % (version, wrong))

    def test_the_module_keeps_one_source(self):
        from dq4_pc.world import data as DO
        self.assertTrue(MAP_PREFIX.startswith('map') and MAP_PREFIX.endswith('_'), MAP_PREFIX)
        self.assertIs(DO.MAP_PREFIX, MAP_PREFIX)


if __name__ == '__main__':
    unittest.main(verbosity=2)
