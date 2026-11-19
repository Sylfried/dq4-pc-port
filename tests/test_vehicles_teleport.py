"""World map: the boat and the balloon after a Teleportation spell or a Chimera wing (the vehicles must be at the right places).

    DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> python3 tests/test_vehicles_teleport.py

Origin (libdq4core, measured on the real engine): the game moves both vehicles itself when the party lands (`CommonRuraData::getShipTownPos` /
`getBalloonTownPos`: one docking place per destination); the port only draws sprites 10 (boat) and 12 (balloon) where the engine's packets put them.
Ownership is two global flags read by `FieldSystem::initialize`: 317 = boat (`g_Party + 0xc`), 370 = balloon (`g_Party + 0xb`); flags 343 / 344 are
"the party is aboard" (the field then starts on the boat / in the balloon). Positions: `FieldPlayerManager + 0x398` (boat), `+ 0x448` (balloon), Fix32.

The state is imposed (`_saves`) from the first save that is on the world map (no map forced by `Global::startField`): chapter 5, the two vehicles owned and placed next to the hero, Ragnar alone with the spell and a wing.
Checked: after landing, each vehicle is next to the hero (far from where it was) and its sprite moved with it (same offset to the engine position as before)."""
import os, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')

RAGNAR, TELEPORT, WING = 3, 203, 0x72                  # originalPlayer_ slot; action of the spell; item id of the Chimaera wing
FLAGS = 0x25b3d8                                       # global flags (bit n)
BOAT_OWNED, BALLOON_OWNED = 317, 370
RURA_TABLE = 0x23e1b0                                  # GOT entry of the destination table of CommonRuraData: 42 x (bit, chapter)
BOAT, BALLOON = 0x398, 0x448                           # FieldPlayerManager: positions (Fix32 x, y, z)
BTN_MENU, BTN_TALK = 0x800, 0x100


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class VehiclesFollowTheParty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        cls.E = ENGINE
        cls.out = tempfile.mkdtemp(prefix='sv_vehicules_')
        def make():
            e = ENGINE.Engine(APK, SAVES, cls.out)
            for _ in range(3): e.step(0, 0)
            return e
        def on_the_map(e): SV.settle(e); return e.state.part == ENGINE.PART_FIELD
        eng, _ = SV.pick_save(make, on_the_map, 'a save on the world map')
        cls.eng = eng; c = cls.c = eng.core; L = c.LIB_BASE
        SV.force_chapter(eng, 5)
        def flag(n):
            a = L + FLAGS + n // 8; c.mem_w(a, bytes([c.mem(a, 1)[0] | (1 << (n % 8))]))
        flag(BOAT_OWNED); flag(BALLOON_OWNED)
        table = struct.unpack('<Q', c.mem(L + RURA_TABLE, 8))[0]
        for i in range(0x2a):                                                       # "visited" flag of every chapter-5 destination (CommonRuraData::setRuraFlagAll)
            if struct.unpack('<2i', c.mem(table + 8 * i, 8))[1] == 5: flag(i)
        SV.force_party(eng, RAGNAR)
        orig = c.export('_ZN6status9PartyData15originalPlayer_E') + 0x530 * RAGNAR
        c.call(c.export('_ZN6status10HaveAction3addEii'), orig + 0xd0, TELEPORT, 0)
        c.mem_w(orig + 0x58 + 0x26, struct.pack('<2H', 99, 99))                     # MP and max MP (with a max of 0 the spell is announced, then nothing happens)
        bag = orig + 0x88                                                           # status::HaveItem (12 entries of 4 bytes from + 0x14)
        c.mem_w(bag + 0x14 + 4 * 3, bytes([WING, 0, 1, 0]))                        # the 4th item becomes a wing (first page of the list)
        c.call(c.export('_ZN3cmn14CommonRuraData14setRuraFlagAllEv'), c.call(c.export('_ZN3cmn14CommonRuraData12getSingletonEv')))
        mgr = c.call(c.export('_ZN18FieldPlayerManager12getSingletonEv'))
        hx, hy = cls.hero()
        v = c.scratch('vehicles_test', 16)
        for fn, (x, y) in (('_ZN18FieldPlayerManager10setShipPosERN3dss12Fix32Vector3E', (hx - 32, hy)), ('_ZN18FieldPlayerManager13setBalloonPosERN3dss12Fix32Vector3E', (hx + 32, hy))):
            c.mem_w(v, struct.pack('<3i', int(x * 4096), int(y * 4096), 0)); c.call(c.export(fn), mgr, v)
        cls.adv(30)
        # the field reads the vehicles and the destinations when it starts: the imposed state is written as the game's automatic save (bank 4, into the
        # engine's temporary write folder, never DQ_SAVES) and reloaded by a new engine, like a test save
        c.call(c.export('_ZN7profile8SaveLoad8savebankEiNS_8SAVETYPEE'), 4, 3); cls.adv(10)
        eng = cls.eng = ENGINE.Engine(APK, SAVES, cls.out)
        for _ in range(3): eng.step(0, 0)
        assert eng.load_save(5); SV.settle(eng)
        c = cls.c = eng.core
        cls.mgr = c.call(c.export('_ZN18FieldPlayerManager12getSingletonEv'))
        cls.adv(30)

    @classmethod
    def adv(cls, n, decl=0):
        for i in range(n): cls.eng.step(0, decl if i == 0 else 0)

    @classmethod
    def hero(cls): return tuple(cls.eng.state.field['cam'][:2])

    def engine_pos(self, off): return tuple(v / 4096.0 for v in struct.unpack('<2i', self.c.mem(self.mgr + off, 8)))

    def sprite_pos(self, slot):
        p = self.eng.state.sprites.get(slot, {}).get('pos'); return None if p is None else tuple(p[:2])

    def row(self, port, col, text):
        cells = self.eng.ui.f[port]['cells']
        rows = [r for (r, k), t in cells.items() if k == col and t == text]
        self.assertTrue(rows, (port, text, cells)); return rows[0]

    def land(self):
        for k in range(60):
            self.adv(10)
            if self.eng.msg_visible and k % 3 == 2: self.adv(1, BTN_TALK)
        SV.settle(self.eng); self.adv(100)

    def check_followed(self, travel):
        before = {s: (self.engine_pos(o), self.sprite_pos(s)) for s, o in ((10, BOAT), (12, BALLOON))}
        h0 = self.hero(); travel(); h1 = self.hero()
        self.assertGreater(abs(h1[0] - h0[0]) + abs(h1[1] - h0[1]), 200, 'the party did not travel')
        for slot, off in ((10, BOAT), (12, BALLOON)):
            (e0, s0), e1, s1 = before[slot], self.engine_pos(off), self.sprite_pos(slot)
            self.assertLess(max(abs(e1[0] - h1[0]), abs(e1[1] - h1[1])), 96, (slot, e1, h1))                 # docked next to the landing point
            self.assertIsNotNone(s1, slot)
            self.assertAlmostEqual(s1[0] - e1[0], s0[0] - e0[0], delta=1.0); self.assertAlmostEqual(s1[1] - e1[1], s0[1] - e0[1], delta=1.0)     # the sprite moved with it

    def open_menu(self, button):
        self.adv(1, BTN_MENU); self.adv(20)
        self.eng.send_menu(4, 1, button, 0x10); self.adv(30)

    def test_1_teleportation(self):
        def travel():
            self.open_menu(1)                                                                                     # "Magie"
            self.eng.send_menu(5, 1, self.row(5, 1, 'Ragnar'), 0x10); self.adv(25)
            self.eng.send_menu(8, 1, self.row(8, 0, 'Téléportation'), 0x10); self.adv(30)                        # -> the list of destinations
            self.eng.send_menu(8, 1, 0, 0x10); self.adv(30); self.land()
        self.check_followed(travel)

    def test_2_chimera_wing(self):
        def travel():
            self.open_menu(2)                                                                                     # "Items": Ragnar's bag
            self.eng.send_menu(9, 1, self.row(9, 2, 'Aile de \nchimère'), 0x10); self.adv(30)
            self.eng.send_menu(8, 1, self.row(8, 0, 'Utiliser'), 0x10); self.adv(30)
            self.eng.send_menu(8, 1, 1, 0x10); self.adv(30); self.land()
        self.check_followed(travel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
