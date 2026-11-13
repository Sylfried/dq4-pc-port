"""A savestate recorded by a version that did not yet have a viewer memory fix (widened places window, "Sauv. cloud" removed, "Settings" button)
must not cause them to be lost: savestates.apply reloads the library's original image then replays `Engine.reapply_fixes`.
(Skipped without the APK: DQ_APK; writes go to a temporary folder, never to the user's saves.)

    python3 tests/test_savestate_fixes.py
"""
import os, shutil, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
APK = os.environ.get('DQ_APK', '')


@unittest.skipUnless(os.path.exists(os.path.join(APK, 'split_config.arm64_v8a.apk')), 'no game APK')
class TestOldSavestate(unittest.TestCase):
    def test_fixes_replayed(self):
        from dq4_pc.core import engine as ENGINE; from dq4_pc.persistence import savestates
        wdir = tempfile.mkdtemp(prefix='sv_test_etats_'); rdir = tempfile.mkdtemp(prefix='sv_test_lec_')
        try:
            m = ENGINE.Engine(APK, rdir, wdir)
            for _ in range(5): m.step(0, 0)
            c = m.core; a = c.export('_ZN9FieldData10drawSymbolEv')
            immediate = lambda dec: (struct.unpack('<I', c.mem(a + dec, 4))[0] >> 10) & 0xfff
            self.assertEqual([immediate(d) for d in (0x44, 0x48, 0x4c)], [1600] * 3)      # fresh engine: fix applied
            d = savestates.snapshot(m)
            img = bytes(c.elf.img); P = savestates.PAGE
            old = [(a - c.LIB_BASE + k, 4) for k in (0x44, 0x48, 0x4c)] + [(m.CMP_PARAMS, 4), (ENGINE.G_IS_AMAZON, 1)]       # "old" state: these library bytes are those of the original image
            pages = dict(d['lib'])
            for off, n in old:
                pg = bytearray(pages.get(off // P) or img[(off // P) * P:(off // P + 1) * P]); pg[off % P:off % P + n] = img[off:off + n]; pages[off // P] = bytes(pg)
            d['lib'] = sorted(pages.items())
            self.assertEqual(c.mem(m.L + ENGINE.G_IS_AMAZON, 1), b'\x01')
            savestates.apply(m, d)
            self.assertEqual([immediate(x) for x in (0x44, 0x48, 0x4c)], [1600] * 3)
            self.assertEqual(c.mem(m.L + ENGINE.G_IS_AMAZON, 1), b'\x01')
            w = struct.unpack('<I', c.mem(c.LIB_BASE + m.CMP_PARAMS, 4))[0]
            self.assertEqual((w >> 10) & 0xfff, 0xfff)
            for _ in range(5): m.step(0, 0)                  # the engine still runs
        finally:
            shutil.rmtree(wdir, ignore_errors=True); shutil.rmtree(rdir, ignore_errors=True)


    def test_session_lists_follow_the_state(self):
        """the 3D model animations the engine waits for (setMotionEnd) are those of the loaded state, not of the game before the load; the ending shortcut's wait is dropped."""
        from dq4_pc.core import engine as ENGINE; from dq4_pc.persistence import savestates
        wdir = tempfile.mkdtemp(prefix='sv_test_etats_'); rdir = tempfile.mkdtemp(prefix='sv_test_lec_')
        try:
            m = ENGINE.Engine(APK, rdir, wdir)
            for _ in range(5): m.step(0, 0)
            m.state.fbx[3] = {'id': 103, 'visible': True, 'pos': (0.0, 0.0, 0.0), 'rot': (0.0, 180.0, 0.0), 'scl': (1.0, 1.0, 1.0), 'col': (1.0, 1.0, 1.0, 1.0), 'anim': [(m.frames, 0, False)]}
            m.state.fbx[4] = dict(m.state.fbx[3], anim=[])
            d = savestates.snapshot(m)
            del m.state.fbx[3], m.state.fbx[4]; m.fbx_playing = [7]; m.ending_wait = m.frames + 600
            savestates.apply(m, d)
            self.assertIn(3, m.fbx_playing); self.assertNotIn(4, m.fbx_playing); self.assertNotIn(7, m.fbx_playing); self.assertIsNone(m.ending_wait)
            for _ in range(5): m.step(0, 0)                  # the engine still runs (the title dragon, slot 0, loops: kept, no end message)
        finally:
            shutil.rmtree(wdir, ignore_errors=True); shutil.rmtree(rdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=1)
