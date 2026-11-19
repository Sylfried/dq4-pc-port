"""loading a savestate does not touch the engine if the state is unusable (damaged file, other library); the library's fingerprint is recorded.
Without APK: cases with a fake engine. With the APK (DQ_APK): the same test on the real engine.
    python3 tests/test_savestates_order.py"""
import hashlib, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import language as _LANGUAGE; _LANGUAGE.select_language('fr')          # (these tests expect the French texts, whatever the computer's language)
from dq456_pc.persistence import savestates
APK = os.environ.get('DQ_APK', '')


def fake_engine(writes, img=b'bibliotheque'):
    uc = types.SimpleNamespace(mem_write=lambda *a: writes.append(a))
    core = types.SimpleNamespace(uc=uc, LIB_BASE=0x1000, elf=types.SimpleNamespace(img=img), heap_ptr=0, HEAP_BASE=0, DATA_BASE=0, TLS_BASE=0, data_ptr=0, next_file=0, files={})
    return types.SimpleNamespace(core=core, log=lambda *a: None, ui=types.SimpleNamespace(obs=None))


def empty_state(**plus):
    d = {'version': savestates.VERSION, 'lib': [], 'heap': b'', 'heap_ptr': 0, 'data': b'', 'tls': b'', 'data_ptr': 0, 'next_file': 0, 'files': {}, 'python': b'pas un pickle', 'viewer': b''}
    d.update(plus); return d


class WithoutRealEngine(unittest.TestCase):
    def test_fingerprint(self):
        m = fake_engine([], img=b'abc'); self.assertEqual(savestates.lib_fingerprint(m.core), hashlib.sha256(b'abc').hexdigest()[:16])

    def test_other_library_refused_without_writing(self):
        wdir = []; m = fake_engine(wdir)
        with self.assertRaises(ValueError) as cm: savestates.apply(m, empty_state(lib_sha='0' * 16))
        self.assertIn('library', str(cm.exception)); self.assertEqual(wdir, [])

    def test_unreadable_python_does_not_touch_engine(self):
        wdir = []; m = fake_engine(wdir)
        with self.assertRaises(Exception): savestates.apply(m, empty_state(lib_sha=savestates.lib_fingerprint(m.core)))
        self.assertEqual(wdir, [])                                                   # before: the engine memory was already overwritten

    def test_old_state_without_fingerprint_passes_gate_fails_later_no_write(self):
        wdir = []; m = fake_engine(wdir)
        with self.assertRaises(Exception) as cm: savestates.apply(m, empty_state())
        self.assertNotIn('bibliotheque', str(cm.exception)); self.assertEqual(wdir, [])

    def test_version_refused(self):
        wdir = []; m = fake_engine(wdir)
        with self.assertRaises(ValueError): savestates.apply(m, empty_state(version=99))
        self.assertEqual(wdir, [])


@unittest.skipUnless(os.path.exists(os.path.join(APK, 'split_config.arm64_v8a.apk')), 'no game APK')
class WithRealEngine(unittest.TestCase):
    def test_failure_leaves_engine_intact_fingerprint_present(self):
        from dq456_pc.core import engine as ENGINE
        wdir = tempfile.mkdtemp(prefix='sv_test_ordre_'); rdir = tempfile.mkdtemp(prefix='sv_test_ordre_l_')
        try:
            m = ENGINE.Engine(APK, rdir, wdir)
            for _ in range(5): m.step(0, 0)
            d = savestates.snapshot(m); c = m.core
            self.assertEqual(d['lib_sha'], savestates.lib_fingerprint(c)); self.assertEqual(len(d['lib_sha']), 16)
            for _ in range(10): m.step(0, 0)                                          # the engine advances: its memory now differs from the state's
            before = hashlib.sha256(c.mem(c.DATA_BASE, c.DATA_SIZE) + c.mem(c.HEAP_BASE, c.heap_ptr - c.HEAP_BASE)).hexdigest(); ptr = c.heap_ptr
            damaged = dict(d, python=d['python'][:20])                                    # truncated pickle
            with self.assertRaises(Exception): savestates.apply(m, damaged)
            after = hashlib.sha256(c.mem(c.DATA_BASE, c.DATA_SIZE) + c.mem(c.HEAP_BASE, c.heap_ptr - c.HEAP_BASE)).hexdigest()
            self.assertEqual((before, ptr), (after, c.heap_ptr))
            savestates.apply(m, d)                                                        # the healthy state still loads
            self.assertEqual(c.heap_ptr, d['heap_ptr'])
        finally: shutil.rmtree(wdir, True); shutil.rmtree(rdir, True)


if __name__ == '__main__': unittest.main(verbosity=1)
