"""entering the places of the world map, other than the starting village, with the real engine under the port.

From a save on the world map at chapter 5 (with the nine characters), the hero is put one cell beside each place of the map (the engine's own table,
`FieldData + 0x170`: 95 entries of 10 bytes, [1] kind, [4:6] x, [6:8] y of the anchor (bottom middle), [8] width, [9] height) and walks onto it, from the south, then the north,
the west, the east. Measured: 63 places entered (towns, castles, caves, towers, shrines), 16 entries of the table are not entrances (decorations and the other state
of two places, same position, kinds 0, 1, 5 and 8). The state is put back between two places (savestate).
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_world_entries.py        (about 3 minutes)
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
SET_POSITION = '_ZN18FieldPlayerManager11setPositionERN3dss12Fix32Vector3E'


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class WorldEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        from dq4_pc.persistence import savestates as SS
        E = ENGINE
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_entrees_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e): SV.settle(e, 200, 600); return e.state.part == ENGINE.PART_FIELD and SV.chapter(e) >= 5
        e, _ = SV.pick_save(make, wanted, 'a save on the world map at chapter 5 or later')
        c = e.core; fd = e.fielddata
        table = struct.unpack('<Q', c.mem(fd + 0x170, 8))[0]; n = struct.unpack('<H', c.mem(fd + 0x1a0, 2))[0]
        places = []
        for i in range(n):
            b = c.mem(table + 10 * i, 10); x, y = struct.unpack('<hh', b[4:8])
            if x > 0 and y > 0 and b[1] <= 17: places.append((i, b[1], x, y, b[8], b[9]))
        field_name = e.state.game_map                                               # (on the world map the engine keeps the last map's name: the town's own name arrives with its packet 0)
        snap = SS.snapshot(e); mgr = c.call(c.export('_ZN18FieldPlayerManager12getSingletonEv')); v = c.scratch('entries_test', 16)
        cls.places = places; cls.entered = {}
        for i, kind, x, y, w, h in places:
            for dx, dy, pad in ((0, 16, E.UP), (0, -16 - h, E.DOWN), (-16 - w // 2, -8, E.RIGHT), (16 + w // 2, -8, E.LEFT)):
                SS.apply(e, snap)
                c.mem_w(v, struct.pack('<3i', int((x + dx) * 4096), int((y + dy) * 4096), 0)); c.call(c.export(SET_POSITION), mgr, v)
                for _ in range(5): e.step(0, 0)
                got = None
                for k in range(200):
                    e.step(pad if k < 40 else 0, 0)
                    if e.state.part == E.PART_TOWN and e.state.game_map != field_name: got = e.state.game_map; break
                    if e.msg_visible: e.step(E.A, E.A)
                if got: cls.entered[i] = got; break

    def test_most_places_are_entered(self):
        self.assertGreaterEqual(len(self.entered), 60, (len(self.places), self.entered))

    def test_towns_castles_caves(self):
        maps = set(self.entered.values())
        self.assertGreaterEqual(len(maps), 50, sorted(maps))
        self.assertTrue(any(m.endswith('out') for m in maps), sorted(maps))                        # (towns: their outside map)
        self.assertTrue(all(isinstance(m, str) and m for m in maps))


if __name__ == '__main__':
    unittest.main(verbosity=2)
