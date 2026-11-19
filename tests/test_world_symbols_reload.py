"""Place icons of the world map (packet 29) when the world map is loaded again (packet 27, FieldData::setup).

What the engine does (read in libdq4core.so): `FieldData::setup(field type, ...)` rebuilds the symbol table of the world being loaded (`CWorldMap::setup`: count at FieldData + 0x1a0) and resets the
state of the 114 symbol slots (FieldData + 3 x slot: enabled, 0 = never sent, alpha 31), then sends packet 27 [1]. `FieldData::drawSymbol` then sends each place in its window again with its full data;
the places of the previous world are never hidden one by one. The field type comes from `Global + 8` (copied to `Global + 4` by FieldSystem::initialize): 0 = the main world (95 places), 1 = the
separate world reached by balloon (7 places, 192 x 192 cells)...

1. `State`: packet 27 empties the icons (both 27 [1], loading, and 27 [0], leaving the world map); the engine's packets 29 that follow fill them again;
2. `State`, the rings of the barrier of Nadiria (world 2): `FieldData::setKekaiSymbol` sends, every frame and for each ring (slots 50 and up, kind 19), the symbol (x, y, alpha) then `0x9000 | slot`
   with two more floats (Field.SetSymbolScale, Field.SetSymbolPrio in NativeManager.cmd_field_symbol: bit 12 is tested before bit 14). That second packet is not a "hide": before, the rings were
   hidden as soon as they were sent;
3. (real engine) from the main world to world 1 (separate world reached by balloon), to world 2 (Nadiria) and back, through `Global::startField` with `Global + 8` set: every icon kept by the viewer is
   a place of the world on screen (slot below the table's count, sent by the engine: state 3) or a ring of the barrier, at the position the engine computes; before the fix, the places of the main
   world stayed on screen in the other worlds until the next map load (a battle);
4. (real engine) the barrier follows its guardians: `FieldStage::initialize` sets the number of rings (g_Stage + 0x124) to 4 minus one per guardian beaten (game flags 0x17b, 0x17c, 0x17d,
   0x17f), 0 once flag 0x180 is set; each time the world map is loaded again (coming out of a guardian's dungeon) the outermost ring is gone, until none is left, and no ring of the
   previous load stays on screen.

  DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> python3 tests/test_world_symbols_reload.py
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import savestates as SS

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
NEXT_FIELD_TYPE = 8                                  # Global + 8: the field type the next world map load uses
SYMBOL_TABLE, SYMBOL_COUNT = 0x170, 0x1a0            # FieldData: pointer to the table (10 bytes per place), number of places
GRID_SIZE = 0x198                                    # FieldData: width, height of the world grid (cells)
GAME_FLAG_GOT = 0x23d448                             # lib + this: pointer to the game flags object (the GOT entry FieldStage::initialize reads before GameFlag::check)
GUARDIAN_FLAGS = (0x17b, 0x17c, 0x17d, 0x17f)        # one ring of the barrier of Nadiria less for each of these game flags (FieldStage::initialize)
BARRIER_GONE = 0x180                                 # ... and none at all once this one is set


def send(e, *packets): e.apply(list(packets), lambda: 'ev01')


def icon(i, kind=4, x=10.0, y=20.0): return (29, [i | kind << 8], [x, y, 1.0])


class StatePackets(unittest.TestCase):
    def test_reload_empties_the_icons(self):
        e = ENGINE.State()
        send(e, icon(0), icon(1), icon(9))
        self.assertEqual(sorted(e.symbols), [0, 1, 9])
        send(e, (27, [1], []))
        self.assertEqual(e.symbols, {}, 'the new world has its own places: none of the old ones is kept')
        send(e, icon(0, 10, 5.0, 6.0))
        self.assertEqual(sorted(e.symbols), [0]); self.assertEqual((e.symbols[0]['kind'], e.symbols[0]['x']), (10, 5.0))

    def test_leaving_the_world_map(self):
        e = ENGINE.State(); send(e, icon(3)); send(e, (27, [0], [])); self.assertEqual(e.symbols, {})

    def test_barrier_rings_scale_and_priority(self):
        e = ENGINE.State()
        for k in range(4):
            send(e, (29, [(50 + k) | 19 << 8], [1503.0 - 4 * k, 1547.0 - 8 * k, 0.613, 1.0 + 0.125 * k, -40.0 + k]), (29, [(50 + k) | 0x9000], []))
        for k in range(4):
            s = e.symbols[50 + k]
            self.assertTrue(s['visible'], 'scale and priority do not hide the ring')
            self.assertEqual((s['kind'], s['scale'], s['prio']), (19, 1.0 + 0.125 * k, -40.0 + k))
        send(e, (29, [50 | 19 << 8], [1503.0, 1547.0, 0.3]))
        self.assertEqual((e.symbols[50]['alpha'], e.symbols[50]['scale'], e.symbols[50]['prio']), (0.3, 1.0, -40.0), 'the next frame keeps them (Unity: the transform is kept)')
        send(e, (29, [51 | 0x9000], [2.0, -10.0])); self.assertEqual((e.symbols[51]['scale'], e.symbols[51]['prio']), (2.0, -10.0))      # (floats attached to the packet itself)

    def test_place_defaults(self):
        e = ENGINE.State(); send(e, icon(4))
        self.assertEqual((e.symbols[4]['scale'], e.symbols[4]['prio']), (1.0, ENGINE.SYMBOL_PRIO))

    def test_hide_and_show_unchanged(self):
        e = ENGINE.State(); send(e, icon(2))
        send(e, (29, [0x8000 | 2], [])); self.assertFalse(e.symbols[2]['visible'])
        send(e, (29, [0xc000 | 2], [])); self.assertTrue(e.symbols[2]['visible'])


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import _saves as SV
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_symbols_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e):
            for _ in range(250): e.step(0, 0)
            cls.go(e, 0); return e.state.part == ENGINE.PART_FIELD
        cls.eng, cls.slot = SV.pick_save(make, wanted, 'a readable save (the world map is loaded by force)')

    @staticmethod
    def go(e, field_type):
        c = e.core; g = e._global()
        c.mem_w(g + NEXT_FIELD_TYPE, struct.pack('<i', field_type)); c.call(c.export('_ZN6Global10startFieldEv'), g, label='startField')
        for _ in range(300): e.step(0, 0)

    def table(self):
        """The engine's places: slot -> (state, x, y of the icon's top-left corner as draw_symbol sends it)."""
        e = self.eng; c = e.core; fd = e.fielddata
        p, = struct.unpack('<Q', c.mem(fd + SYMBOL_TABLE, 8)); n, = struct.unpack('<I', c.mem(fd + SYMBOL_COUNT, 4))
        out = {}
        for k in range(n):
            b = c.mem(p + 10 * k, 10); x, y = struct.unpack_from('<hh', b, 4)
            out[k] = (c.mem(fd + 3 * k + 1, 1)[0], x - (b[8] >> 1) - 1, y - b[9])
        return out

    def rings(self):
        """Number of rings of the barrier the engine draws in this world (status::g_Stage + 0x124, read by FieldData::setKekaiSymbol)."""
        c = self.eng.core; return struct.unpack('<i', c.mem(c.export('_ZN6status7g_StageE') + 0x124, 4))[0]

    def check(self, what):
        e = self.eng; t = self.table()
        self.assertEqual(e.state.part, ENGINE.PART_FIELD, what)
        self.assertTrue(e.state.symbols, '%s: some places are on screen' % what)
        rings = sorted(i for i, s in e.state.symbols.items() if i not in t and s['kind'] == 19)
        self.assertEqual(rings, list(range(50, 50 + len(rings))), '%s: rings of the barrier: slots 50 and up' % what)
        for i in rings:
            s = e.state.symbols[i]; k = i - 50
            self.assertTrue(s['visible'], '%s: ring %d shown' % (what, k)); self.assertEqual((s['scale'], s['prio']), (1.0 + 0.125 * k, -40.0 + k), '%s: ring %d' % (what, k))
        for i, s in e.state.symbols.items():
            if i in rings: continue
            self.assertIn(i, t, '%s: icon %d is not a place of this world (%d places)' % (what, i, len(t)))
            if s['visible']:
                self.assertEqual(t[i][0], 3, '%s: icon %d shown by the viewer, not by the engine' % (what, i))
                if s['kind'] not in (19, 20): self.assertEqual((s['x'], s['y']), (float(t[i][1]), float(t[i][2])), '%s: icon %d at the place of this world' % (what, i))
        shown = sorted(k for k, v in t.items() if v[0] == 3)
        self.assertEqual(shown, sorted(i for i, s in e.state.symbols.items() if s['visible'] and i not in rings), '%s: every place the engine shows is shown' % what)
        l, h = struct.unpack('<ii', e.core.mem(e.fielddata + GRID_SIZE, 8))
        self.assertEqual((e.state.world['l'], e.state.world['h']), (l, h), '%s: the grid of this world' % what)
        return len(t), len(rings)

    def test_world_change_and_back(self):
        n_main, _ = self.check('main world')
        self.go(self.eng, 1); n_other, _ = self.check('world 1')
        self.assertLess(n_other, n_main, 'world 1 has fewer places than the main world (the case that left icons behind)')
        self.go(self.eng, 2); n_nadiria, rings = self.check('world 2 (Nadiria)')
        self.assertLess(n_nadiria, n_main); self.assertEqual(rings, self.rings(), 'world 2: every ring of the barrier the engine draws')
        self.go(self.eng, 1); self.check('world 1 again')
        self.go(self.eng, 0); self.assertEqual(self.check('main world again'), (n_main, 0))

    def test_barrier_follows_its_guardians(self):
        e = self.eng; c = e.core
        flags = struct.unpack('<Q', c.mem(c.LIB_BASE + GAME_FLAG_GOT, 8))[0]
        set_flag, check = c.export('_ZN6status8GameFlag3setEi'), c.export('_ZN6status8GameFlag5checkEi')
        snap = SS.snapshot(e)
        try:
            for f in GUARDIAN_FLAGS + (BARRIER_GONE,):
                if c.call(check, flags, f) & 1: self.skipTest('a guardian is already beaten in this save')
            self.go(e, 2); _, rings = self.check('Nadiria, no guardian beaten'); self.assertEqual(rings, 4)
            for n, f in enumerate(GUARDIAN_FLAGS, 1):
                c.call(set_flag, flags, f); self.go(e, 2)
                _, rings = self.check('Nadiria, %d guardian(s) beaten' % n); self.assertEqual(rings, 4 - n)
            c.call(set_flag, flags, BARRIER_GONE); self.go(e, 2); self.assertEqual(self.check('Nadiria, barrier gone')[1], 0)
        finally:
            SS.apply(e, snap)


if __name__ == '__main__':
    unittest.main()
