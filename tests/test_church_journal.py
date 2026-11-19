"""The church's list of adventure logs writes the "current" log in cyan (MaterielMenu_SAVE + 0x24, set by the start menu when it loads a log, by the church when it writes one). It stayed on
log 1 when the game was not loaded by the start menu: a log loaded by the viewer (load_save), the quick save's "Resume" (the engine leaves the value as it is), a savestate of another moment.
Engine._journal_hooks: load_save sets it, a quick save remembers its log (kept by the window in the settings) and its "Resume" gives it back, a savestate keeps the log chosen in the session.

1. Without APK: the setting (default, values from a file).
2. Real engine (DQ_APK, DQ_SAVES): load_save, the savestate, the quick save's log.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_church_journal.py        (about a minute)
"""
import json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class Setting(unittest.TestCase):
    def read(self, v):
        f = os.path.join(tempfile.mkdtemp(prefix='journal_'), 'settings.json')
        with open(f, 'w', encoding='utf-8') as fh: json.dump({'keys_version': RG.DEFAULT['keys_version'], 'quick_save_journal': v}, fh)
        return RG.Settings(f)['quick_save_journal']

    def test_default_and_values(self):
        self.assertIsNone(RG.Settings(None)['quick_save_journal'])
        for v in (0, 1, 2): self.assertEqual(self.read(v), v)
        for v in (3, -1, 'x', True, [1]): self.assertIsNone(self.read(v), v)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def setUp(self):
        self.m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='journal_'))
        for _ in range(3): self.m.step(0, 0)
        self.assertEqual(self.m.journal(), 0); self.assertFalse(self.m.journal_chosen)

    def test_load_save_and_savestate(self):
        from dq456_pc.persistence import savestates as SS
        if not os.path.exists(os.path.join(SAVES, 'data1.dat')): self.skipTest('no data1.dat')
        self.assertTrue(self.m.load_save(1)); self.assertEqual(self.m.journal(), 0); self.assertTrue(self.m.journal_chosen)
        for _ in range(30): self.m.step(0, 0)
        snap = SS.snapshot(self.m)
        self.m.set_journal(1); SS.apply(self.m, snap); self.assertEqual(self.m.journal(), 1)             # (the log chosen in the session stays)
        self.m.journal_chosen = False; SS.apply(self.m, snap); self.assertEqual(self.m.journal(), 0)    # (none chosen yet: the savestate's own)

    def test_quick_save_log(self):
        seen = []; self.m.on_quick_save = seen.append; self.m.set_journal(2)
        c = self.m.core; c.call(c.export('_ZN7profile8SaveLoad8savebankEiNS_8SAVETYPEE'), ENGINE.QUICK_SAVE_BANK, 3)
        self.assertEqual(seen, [2]); self.assertEqual(self.m.quick_journal, 2)
        self.m.set_journal(0); self.assertTrue(self.m.load_save(ENGINE.QUICK_SAVE_BANK + 1)); self.assertEqual(self.m.journal(), 2)


if __name__ == '__main__':
    unittest.main()
