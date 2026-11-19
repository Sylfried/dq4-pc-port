"""priority of the map objects (FMAP): 32-bit integer at +52 (render queue 3000 + priority), flags = 32-bit integer at +48.
Run from the root: python3 tests/test_fld_priority.py"""
import os, struct, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dq456_pc.world import fld


def fmap(objects):
    """A minimal FMAP chunk: 0x20-byte header (tag, size, object count) then 0x50 bytes per object; `objects` = [(flags int32, priority int32)]."""
    body = bytearray()
    for flag32, prio in objects:
        o = bytearray(0x50); struct.pack_into('<ii', o, 48, flag32, prio); struct.pack_into('<hh', o, 64, 3, 4); struct.pack_into('<h', o, 74, 5); body += o
    t = 0x20 + len(body); ent = bytearray(0x20); ent[:4] = b'FMAP'; struct.pack_into('<I', ent, 4, t); struct.pack_into('<I', ent, 8, len(objects))
    return bytes(ent + body)


class ItemPriority(unittest.TestCase):
    def test_priority_at_plus_52_not_high_half_of_flags(self):
        n, objs = fld.map_objs(fmap([(0x40000, 23), (0, 10), (0x40004, 12)]))
        self.assertEqual(n, 3); self.assertEqual([o['prio'] for o in objs], [23, 10, 12])         # before: 4, 0, 4 (the upper half of the flags)

    def test_flags_unchanged(self):
        n, objs = fld.map_objs(fmap([(0x40024, 18), (0x20, 11), (0x0, 10)]))
        self.assertEqual([o['flag'] for o in objs], [0x24, 0x20, 0])                              # billboards (& 36): only the low 16 bits, as before

    def test_other_fields_unchanged(self):
        _, objs = fld.map_objs(fmap([(0, 10)]))
        self.assertEqual((objs[0]['sequence_object'], objs[0]['pmv'], objs[0]['canim']), (3, 4, 5))


class CacheVersion(unittest.TestCase):
    def test_version_13_maps_and_old_ones_purged(self):
        from dq456_pc.world import data as DO
        import inspect
        src = inspect.getsource(DO)
        self.assertEqual(DO.MAP_PREFIX, 'map15_')                                               # map cache version (FSRA colors; event objects and FEAN): a single place writes it
        self.assertNotIn("'carte12_%s", src); self.assertNotIn("'carte13_%s", src)                # neither the old cache (wrong priority) nor the duplicated prefix: everything goes through MAP_PREFIX
        import tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            for f in ('carte9_a.pkl', 'carte10_a.pkl', 'carte11_a.pkl', 'carte12_a.pkl', 'carte13_a.pkl', 'carte14_a.pkl', 'map14_a.pkl', 'map15_a.pkl'): open(os.path.join(d, f), 'wb').close()
            o = DO.Data.__new__(DO.Data); o.cache = d; o.log = lambda *a: None; o._purge_old()
            self.assertEqual(os.listdir(d), ['map15_a.pkl'])
        finally: shutil.rmtree(d, ignore_errors=True)


class FixProblems(unittest.TestCase):
    """DQ V, FldObject.FixProblems (data.FIX_PROBLEMS, applied when a map is read): the transparent groups of the listed objects are drawn with depth writing (c['transz']),
    one material's color is multiplied by its gray; the other games, the other maps and a group shared with an unlisted object are left alone."""
    def setUp(self):
        import numpy as np
        from dq456_pc.world import data as DO
        self.np = np; self.DO = DO

    def map(self):
        np = self.np; one = lambda n: (np.zeros((n, 3), np.float32), np.zeros((n, 2), np.float32), np.ones((n, 4), np.float32))
        return dict(groups={5: one(6), ('tr', 10, 7): one(6), ('tr', 12, 8): one(9), ('tr', 12, 9): one(6), ('tr', 11, 4, 'z'): one(3)},
                    spans={2: [(('tr', 10, 7), 0, 6)], 3: [(5, 0, 6), (('tr', 12, 8), 0, 3)], 6: [(5, 0, 3), (('tr', 12, 8), 3, 3)], 7: [(5, 3, 3), (('tr', 12, 8), 6, 3)], 9: [(('tr', 12, 9), 0, 6), (('tr', 11, 4, 'z'), 0, 3)]})

    def test_transz_groups(self):
        c = self.DO.fix_problems('dq5', 'dlf1g', self.map()); self.assertEqual(c['transz'], {('tr', 10, 7)})
        table = dict(self.DO.FIX_PROBLEMS['dq5']); table['x'] = dict(transz=(3, 9))
        real = self.DO.FIX_PROBLEMS['dq5']; self.DO.FIX_PROBLEMS['dq5'] = table
        try: c = self.DO.fix_problems('dq5', 'x', self.map())
        finally: self.DO.FIX_PROBLEMS['dq5'] = real
        self.assertEqual(c['transz'], {('tr', 12, 9)})          # (('tr', 12, 8) is shared with objects 6 and 7; the 'z' group already writes depth; 5 is opaque)

    def test_color(self):
        c = self.DO.fix_problems('dq5', 'cfout', self.map()); col = c['groups'][('tr', 12, 8)][2]
        self.assertTrue((col[:3] == 1.0).all())                  # (object 3's range)
        self.assertTrue(self.np.allclose(col[3:, :3], 248.0 / 255.0)); self.assertTrue((col[:, 3] == 1.0).all())
        self.assertTrue((c['groups'][5][2] == 1.0).all()); self.assertEqual(c['transz'], set())

    def test_left_alone(self):
        for game, name in (('dq4', 'cfout'), ('dq6', 'ev14'), ('dq5', 'mdout')):
            c = self.DO.fix_problems(game, name, self.map())
            self.assertNotIn('transz', c); self.assertTrue((c['groups'][('tr', 12, 8)][2] == 1.0).all())
        self.assertIsNone(self.DO.fix_problems('dq5', 'ev14', None))

    def test_table(self):
        self.assertEqual(sorted(self.DO.FIX_PROBLEMS), ['dq5'])
        self.assertEqual(self.DO.FIX_PROBLEMS['dq5']['ev14']['transz'], (23, 24, 36, 39, 40, 53, 54, 55)); self.assertEqual(self.DO.FIX_PROBLEMS['dq5']['dlf1g']['transz'], (2,))


if __name__ == '__main__': unittest.main(verbosity=1)
