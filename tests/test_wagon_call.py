"""Wagon call: the Baron's horn ("Clairon du Baron") calls the wagon on the world map, played with the real engine.

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_wagon_call.py        (about 10 seconds)

Where the call lives (libdq4core, established on the real engine):
* the call is the item **Clairon du Baron** (id 0x9b): "Solo souffle dans le clairon du Baron." (`TownActionBallonHorn` in a town, `FieldPlayerManager::ballonWhistle` on the world
  map); the same call is a script command (`cmd_set_party_call_carriage`), used by the story;
* on the world map it works only if the party is in a **Baron area** (`FieldPlayerManager::checkBarronArea` = a `FieldRectCollManager` rectangle of type 3) **and** the wagon is not
  already with the party (byte +8 of the `FieldParty` object, the one `callCarriage` sets back to 1); otherwise the engine says "Mais il ne se passe rien." (in a town the horn
  does nothing, on any map);
* when it works: after the message, white fade out, `callCarriage` (the wagon is with the party again), `setPartyToFirst` (the members come back around the hero), white fade in.

Save 3's world map has no type 3 rectangle (the area belongs to the end of the story, which no save reaches): the test adds one around the hero and puts the clairon in the hero's bag,
the rest is the game's own code. The port only draws what the engine sends: the white fade (`Engine._fade`) and the sprites.
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
HERO = 1                                               # originalPlayer_ slot of the hero (Solo)
HORN = 0x9b                                            # item id of the Baron's horn
FIELD_PARTY_PTR = 0x23d428                             # GOT entry of the FieldParty object: byte +8 = "the wagon is with the party"
AREA_TYPE = 3                                          # FieldRectCollManager type read by checkBarronArea
BTN_MENU = 0x800
OBJETS, USE = 2, 0                                     # cell of "Items" in the command menu; "Utiliser" in the item's menu


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder>')
class WagonCall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.persistence import savestates as SS
        cls.E, cls.SS = ENGINE, SS
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_wagon_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e):
            SV.settle(e)
            if e.state.part != ENGINE.PART_FIELD: return False
            return cls.wagon_follows(e)
        cls.e, cls.slot = SV.pick_save(make, wanted, 'a save on the world map with the wagon')
        cls.snap = SS.snapshot(cls.e)

    @staticmethod
    def party_object(e):
        c = e.core; return struct.unpack('<Q', c.mem(c.LIB_BASE + FIELD_PARTY_PTR, 8))[0]

    @classmethod
    def wagon_follows(cls, e): return bool(e.core.mem(cls.party_object(e) + 8, 1)[0])

    def play(self, wagon_away, area):
        """The hero uses the clairon from the command menu. -> (texts, highest white fade opacity, wagon follows at the end, state of the engine)."""
        e, c = self.e, self.e.core
        self.SS.apply(e, self.snap)
        orig = c.export('_ZN6status9PartyData15originalPlayer_E') + 0x530 * HERO
        bag = orig + 0x88                                                           # status::HaveItem: 12 entries of 4 bytes from + 0x14
        c.mem_w(bag + 0x14, bytes([HORN, 0, 1, 0]) + bytes(4 * 11))                 # the clairon alone: first item of the list
        if wagon_away: c.mem_w(self.party_object(e) + 8, b'\x00')
        if area:
            rm = c.call(c.export('_ZN20FieldRectCollManager12getSingletonEv'))
            hx, hy = (int(v) for v in e.state.field['cam'][:2])
            n = struct.unpack('<i', c.mem(rm + 0x8c, 4))[0]
            c.mem_w(rm + 0x1c * n, struct.pack('<7i', (hx - 200) * 4096, (hy - 200) * 4096, -4096, (hx + 200) * 4096, (hy + 200) * 4096, 4096, AREA_TYPE))
            c.mem_w(rm + 0x8c, struct.pack('<i', n + 1))
        for _ in range(60): e.step(0, 0)
        e.sensor.drain()
        e.step(0, BTN_MENU)
        for _ in range(60): e.step(0, 0)
        for port, cell in ((4, OBJETS), (9, 0), (8, USE)):
            self.assertIn(port, e.input_menus(), 'the window %d is not there' % port)
            e.send_menu(port, 1, cell, 0x10)
            for _ in range(3): e.step(0, 0)
            e.send_menu(port, 1, -1, 0)
            for _ in range(40): e.step(0, 0)
        texts, white = [], 0.0
        for i in range(1500):
            if e.msg_visible and e.active_menu() is None and i % 6 == 0: e.step(self.E.A, self.E.A)
            else: e.step(0, 0)
            fd = e.state.fade
            if tuple(fd['col']) == (1.0, 1.0, 1.0): white = max(white, fd['a'])
            texts += [s['text'] for s in e.sensor.drain()]
        return ' '.join(texts), white, self.wagon_follows(e)

    def test_called_in_the_baron_area(self):
        text, white, follows = self.play(wagon_away=True, area=True)
        self.assertIn('souffle dans le clairon', text)
        self.assertNotIn('ne se passe rien', text)
        self.assertGreater(white, 0.9, 'no white fade')
        self.assertTrue(follows, 'the wagon is not with the party')
        self.assertEqual(self.e.state.part, self.E.PART_FIELD)
        self.assertIsNone(self.e.active_menu()); self.assertFalse(self.e.msg_visible)

    def test_nothing_outside_the_area(self):
        text, white, follows = self.play(wagon_away=True, area=False)
        self.assertIn('souffle dans le clairon', text)
        self.assertIn('ne se passe rien', text)
        self.assertEqual(white, 0.0); self.assertFalse(follows)

    def test_nothing_when_the_wagon_is_there(self):
        text, white, follows = self.play(wagon_away=False, area=True)
        self.assertIn('ne se passe rien', text)
        self.assertEqual(white, 0.0); self.assertTrue(follows)


if __name__ == '__main__':
    unittest.main()
