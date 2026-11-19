"""The bestiary opened the way the game opens it, by the item "Livre des creatures", played with the real engine.

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_bestiary_item.py        (about 10 seconds)

Established (libdq4core): the "Miscellaneous" menu has no bestiary entry (pages: "Quick save", "Heal all", "Equipment", "Formation", "Sort the bag",
"Resultats combats", "Parametres", at chapter 5 too). `TownMenuItemSelectCommand::menuUpdate` calls `Global::startBook` for the item **0x9d** ("Livre des creatures"), when the engine
is in the world-map part (0xe). The test puts the book in the bag of the party's first member (the story gives it, not any save) and uses it: "Solo ouvre le Livre des creatures.", then the bestiary part
(0x10) with the window of type 28 (monsters seen by name, the others "???"), and the back button returns to the world map.
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
HERO = 1                                               # originalPlayer_ slot of the hero (Solo): if the party cannot be read
BOOK = 0x9d                                            # item id of the bestiary book ("Livre des creatures" in the French patch)
BTN_MENU = 0x800
OBJETS, USE = 2, 0                                     # cell of "Items" in the command menu; "Utiliser" in the item's menu
LIST = 28                                              # window type of the bestiary list


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder>')
class BestiaryItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.persistence import savestates as SS
        cls.E, cls.SS = ENGINE, SS
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_book_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e):
            SV.settle(e); return e.state.part == ENGINE.PART_FIELD
        cls.e, cls.slot = SV.pick_save(make, wanted, 'a save on the world map')
        cls.snap = SS.snapshot(cls.e)

    def touch(self, port, cell, button=0x10, frames=40):
        e = self.e
        self.assertIn(port, e.input_menus(), 'the window %d is not there' % port)
        e.send_menu(port, 1, cell, button)
        for _ in range(3): e.step(0, 0)
        e.send_menu(port, 1, -1, 0)
        for _ in range(frames): e.step(0, 0)

    def test_item_opens_the_bestiary_and_back_returns(self):
        e, c = self.e, self.e.core
        self.SS.apply(e, self.snap)
        party = c.export('_ZN6status7g_PartyE'); members = struct.unpack('<%dI' % self.E.PARTY_SLOTS, c.mem(party + self.E.PARTY_MEMBERS, 4 * self.E.PARTY_SLOTS))
        first = next((i for i in members if i), HERO)                                     # (the first member of the party: the one whose bag the menu opens; Ragnar in chapter 1)
        bag = c.export('_ZN6status9PartyData15originalPlayer_E') + 0x530 * first + 0x88       # status::HaveItem: 12 entries of 4 bytes from + 0x14
        c.mem_w(bag + 0x14, bytes([BOOK, 0, 1, 0]) + bytes(4 * 11))
        for _ in range(60): e.step(0, 0)
        e.sensor.drain()
        e.step(0, BTN_MENU)
        for _ in range(60): e.step(0, 0)
        for port, cell in ((4, OBJETS), (9, 0), (8, USE)): self.touch(port, cell)
        texts = []
        for i in range(600):
            if e.msg_visible and e.active_menu() is None and i % 6 == 0: e.step(self.E.A, self.E.A)
            else: e.step(0, 0)
            texts += [s['text'] for s in e.sensor.drain()]
            if e.state.part == self.E.PART_BESTIARY: break
        self.assertEqual(e.state.part, self.E.PART_BESTIARY, texts)
        self.assertIn('ouvre le Livre des', ' '.join(texts))
        for _ in range(60): e.step(0, 0)
        port = next((p for p in e.input_menus() if e.ui.f[p].get('type') == LIST), None)
        self.assertIsNotNone(port, 'window %d (types seen: %s)' % (LIST, [e.ui.f[p].get('type') for p in e.input_menus()]))
        names = [str(v) for (i, j), v in e.ui.f[port]['cells'].items() if j == 1 and i < 12]
        self.assertTrue(names and all(names), names)
        self.assertTrue(any(n != '???' for n in names), 'no monster known: %s' % names)
        self.assertFalse([n for n in names if '<ERR' in n], names)
        e.send_menu(port, 1, -1, 0x20)                                                    # back button
        for _ in range(3): e.step(0, 0)
        e.send_menu(port, 1, -1, 0)
        for _ in range(200): e.step(0, 0)
        self.assertEqual(e.state.part, self.E.PART_FIELD)


if __name__ == '__main__':
    unittest.main()
