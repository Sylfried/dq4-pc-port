"""Test of the pinned versions and of the flushing of translated blocks.

1. **`requirements.txt`**: a single source for the Windows launcher and the CI. Before, `launch_dq4.bat` installed seven modules **without a version** and the CI installed only three (`numpy unicorn soundfile`):
   everything that imports pyglet or Pillow was covered only by `compileall`, and a silent version bump could break a fresh install without breaking anything for someone who already has theirs.
2. **`ctl_flush_tb`**: after installing a hook that rewrites ARM code, the engine must flush the blocks Unicorn has already translated, otherwise the hook has **no effect** on code that has already run. The call was
   in a `try/except: pass`: a version of Unicorn that no longer exposed it would have disabled the settings **silently**. It now goes through `Engine._flush_tb`, which reports it like any missing hook.

    python3 tests/test_pinned_versions.py
No screen, no GL, no APK.
"""
import io, os, re, sys, types, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

MODULES = ('numpy', 'pillow', 'unicorn', 'pyglet', 'UnityPy', 'capstone', 'soundfile')


def requirements():
    with io.open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith('#')]


class Pinned(unittest.TestCase):
    def test_every_module_is_pinned_to_an_exact_version(self):
        pinned = dict(re.match(r'([A-Za-z0-9_.\-]+)==([0-9][0-9A-Za-z.\-]*)$', line).groups() for line in requirements())
        self.assertEqual({k.lower() for k in pinned}, {m.lower() for m in MODULES}, pinned)

    def test_the_launcher_reads_the_file(self):
        with io.open(os.path.join(ROOT, 'launch_dq4.bat'), encoding='utf-8') as f: bat = f.read()
        self.assertIn('-r "requirements.txt"', bat)
        for m in MODULES:                                        # no more hand-written module list in the .bat
            self.assertNotIn('check %s' % m, bat); self.assertNotIn('check-%s' % m, bat)
        self.assertNotRegex(bat, r'pip install[^\r\n]*\bnumpy\b')

    def test_the_ci_reads_the_file_too(self):
        with io.open(os.path.join(ROOT, '.github', 'workflows', 'ci.yml'), encoding='utf-8') as f: ci = f.read()
        self.assertIn('-r requirements.txt', ci)
        self.assertNotRegex(ci, r'pip install[^\r\n]*\bnumpy\b', 'the CI must not have its own list of modules any more')


class FlushTb(unittest.TestCase):
    def test_no_hook_swallows_the_flush_any_more(self):
        import inspect
        from dq4_pc.core import engine as ENGINE
        src = inspect.getsource(ENGINE)
        self.assertEqual(src.count('ctl_flush_tb()'), 1, 'a single call, in `_flush_tb`')
        self.assertNotIn('try: c.uc.ctl_flush_tb()', src)
        self.assertGreaterEqual(src.count('self._flush_tb('), 6, 'the six hooks that rewrite code go through it')

    def test_an_unavailable_flush_is_reported(self):
        """A version of Unicorn without `ctl_flush_tb`: the setting is reported missing instead of disappearing silently."""
        from dq4_pc.core import engine as ENGINE
        def boom(): raise AttributeError('ctl_flush_tb')
        eng = types.SimpleNamespace(core=types.SimpleNamespace(uc=types.SimpleNamespace(ctl_flush_tb=boom)), missing_hooks=[])
        eng._record_missing = types.MethodType(ENGINE.Engine._record_missing, eng)
        ENGINE.Engine._flush_tb(eng, 'encounters')
        self.assertEqual(len(eng.missing_hooks), 1, eng.missing_hooks)
        self.assertIn('encounters', eng.missing_hooks[0]); self.assertIn('ctl_flush_tb', eng.missing_hooks[0])

    def test_nothing_is_reported_when_it_works(self):
        from dq4_pc.core import engine as ENGINE
        calls = []
        eng = types.SimpleNamespace(core=types.SimpleNamespace(uc=types.SimpleNamespace(ctl_flush_tb=lambda: calls.append(1))), missing_hooks=[])
        eng._record_missing = types.MethodType(ENGINE.Engine._record_missing, eng)
        ENGINE.Engine._flush_tb(eng, 'play time')
        self.assertEqual((calls, eng.missing_hooks), ([1], []))


if __name__ == '__main__':
    unittest.main(verbosity=2)
