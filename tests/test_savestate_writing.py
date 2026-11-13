"""Test of WRITING a savestate.

**.** `savestates.write` wrote `path + '.tmp'` then `os.replace`: atomic, but — unlike saves and adventure logs (`write_dir.atomic_write`) — without `fsync`, without a retry, and the half-written
`.tmp` stayed next to the savestate when the write failed (full disk, antivirus locking the file: common on Windows). The write now goes through the same function as the rest of the port. The error is still raised: the caller
shows "echec d'enregistrement" and the old savestate stays intact.

**.** The cost of a savestate grew with the engine heap (0.01 s at 2 MB, 0.47 s at 200 MB) because the heap was never given back. being fixed, the heap no longer rises: measurement on
the real engine, after loading then three map round trips, the used heap stays at **2.45 MB** (live 1.71 MB), the savestate takes **0.006 s** and the write 0.010 s. So there is nothing to put in
a worker thread: this test keeps the property that makes the measurement hold — the used heap does not grow from one map change to the next.

    python3 tests/test_savestate_writing.py                 (DQ_APK and DQ_SAVES for the "real engine" part)
No screen, no GL. Saves are opened read-only (the engine writes to a temporary folder).
"""
import os, shutil, sys, tempfile, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dq4_pc.persistence import savestates as SS
from dq4_pc.persistence import write_dir as WD

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
STATE = {'quoi': 'un etat', 'octets': b'\x00' * 4096}


class Writing(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='etats_'); self.p = os.path.join(self.d, 'state_01.dqs')

    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)

    def test_it_writes_and_rereads(self):
        SS.write(self.p, STATE, {'map': 'taf1'})
        info, png = SS.info(self.p)
        self.assertEqual(info['map'], 'taf1'); self.assertEqual(png, b''); self.assertIn('date', info)
        self.assertEqual(SS.read(self.p)[0] if isinstance(SS.read(self.p), tuple) else SS.read(self.p), STATE)

    def test_it_goes_through_the_same_writer_as_the_rest(self):
        """The same function as saves and adventure logs: fsync, two tries, `.tmp` removed."""
        seen = []
        real = WD.atomic_write
        WD.atomic_write = lambda path, raw, **kw: (seen.append((path, len(raw))), real(path, raw, **kw))[1]
        try: SS.write(self.p, STATE, {'map': 'taf1'})
        finally: WD.atomic_write = real
        self.assertEqual(len(seen), 1, 'un seul appel'); self.assertTrue(seen[0][1] > 0)

    def test_a_failure_leaves_no_tmp_and_keeps_the_old_state(self):
        SS.write(self.p, {'old': True}, {'map': 'taf1'})
        with open(self.p, 'rb') as fh: before = fh.read()
        real = os.replace
        os.replace = lambda a, b, *r: (_ for _ in ()).throw(OSError(13, 'verrouille par un autre programme'))
        try:
            with self.assertRaises(OSError): SS.write(self.p, STATE, {'map': 'mlb1a'})
        finally: os.replace = real
        with open(self.p, 'rb') as fh: self.assertEqual(fh.read(), before, 'l\'ancien etat doit rester intact')
        self.assertEqual([f for f in os.listdir(self.d) if f.endswith('.tmp')], [], 'a .tmp must not be left behind')

    def test_it_retries(self):
        """A transient lock (antivirus): the second try succeeds, as for saves."""
        real = os.replace; tries = []
        def once(a, b, *r):
            tries.append(1)
            if len(tries) == 1: raise OSError(13, 'verrouille')
            return real(a, b, *r)
        os.replace = once
        try: SS.write(self.p, STATE, {'map': 'taf1'})
        finally: os.replace = real
        self.assertEqual(len(tries), 2); self.assertTrue(os.path.isfile(self.p))


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class HeapDoesNotGrow(unittest.TestCase):
    def test_the_used_heap_stays_put_across_map_changes(self):
        """What made the savestate grow was the heap that never went back down. Measurement: 2.45 MB, stable."""
        from dq4_pc.core import engine as ENGINE
        import _saves as SV
        m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv295_'))
        for _ in range(3): m.step(0, 0)
        if not SV.load_any(m): self.skipTest('no readable save')
        SV.settle(m)
        used = lambda: m.core.heap_ptr - m.core.HEAP_BASE
        start = used()
        for game_map in ('mlb1a', 'taf1', 'mlb1a', 'taf1'):
            m.start_town(game_map)
            for _ in range(90): m.step(0, 0)
        grown = used() - start
        self.assertLess(grown, 2 << 20, 'the heap in use grew by %.2f MB over four map changes' % (grown / 1e6))
        self.assertLess(used(), 32 << 20, 'tas utilise : %.2f Mo' % (used() / 1e6))
        t0 = time.perf_counter(); SS.snapshot(m); dt = time.perf_counter() - t0
        self.assertLess(dt, 0.25, 'instantane en %.3f s' % dt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
