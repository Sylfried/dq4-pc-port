"""The casino monster arena (windows 50, 49, 51, 71) played with the real engine.

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_stadium_real.py        (about 20 seconds)

The arena is a town service (`changeShopMenuPhase` phase 15, in the casino map `hcy1b1`), played here the way the port's menus answer it (`Engine.send_menu`):

* **window 50** "Parier sur lequel ?": three monsters drawn at random, each with its odds ("x 4.3"), and the coins; confirming a cell chooses the monster;
* **window 49** "Parier combien ?": the monster, the coins and two digit columns (tens, units). The columns are driven like the port does (`_step_entry`): the engine takes
  `send_menu(port, 1, n, 0x2)` as "add n to the bet"; confirming any cell then asks for the bet ("Vous voulez placer 3 tickets sur ... ?"). One ticket costs one coin;
* then the battle part (0xd, map `btlcc2`, the three monsters appear) with **window 71** "Quit" over it.

* **leaving the fight**: the "Quit" window is a single back button (gamepad 0x400 = the game's key 0x20, `decl` bit 10). The viewer replaces it by its own back button (`Engine.ignored_types`) that sends
  that key at every step until the engine has switched the window off (`setBattleStadiumAbort(false)`, byte lib+0x24a7d4). The engine then lets the action in progress finish (its messages are turned as usual), asks
  "Attendez ! Si vous partez maintenant, vous perdrez tous les tickets..." with Yes / No; Oui ends the battle (tickets lost), Non switches the window back on and the fight goes on.

Not covered here, because the engine alone cannot do it: the end of the fight and its winnings. Headless, the engine waits for the viewer's battle animations after the first attack; it was played
to the end in the real window (see the viewer notes: the fight, the result, "Felicitations ! Vous avez gagne N jetons !", the window 51 with the coins won, the offer to bet them again, the
Yes / No "faire un autre pari ?", the return to the poster).
"""
import os, re, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
TOWN = 'hcy1b1'                                  # the casino
G_PARTY = '_ZN6status7g_PartyE'
COINS = 0x2e8                                    # g_Party + 0x2e8 = the casino coins (u32)
SET_COINS = '_ZN6status15BasePartyStatus13setCasinoCoinEj'
PHASE_FN = '_ZN6window13CommandWindow19changeShopMenuPhaseEi'
WM = '_ZN27MaterielMenu_WINDOW_MANAGER12getSingletonEv'
TWS = '_ZN16TownWindowSystem11m_singletonE'
A = 0x10
ARENA = 15                                       # phase of the monster arena
SELECT, BET, ABORT = 50, 49, 71
BATTLE_MAP = 'btlcc2'
START = 5000
BACK = 0x400                                     # decl bit 10 = the game's key 0x20 (Global::NativeExec)
G_ENABLE = 0x24a7d4                              # lib + this: the "Quit" window's switch (MenuAPI::setBattleStadiumAbort)


class Recorder:
    """`Interface.obs`: every window type the engine creates."""
    def __init__(self): self.types = set()
    def open_menu(self, port, typ): self.types.add(typ)
    def __getattr__(self, name):
        if name.startswith('_'): raise AttributeError(name)
        return lambda *a, **k: None


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder>')
class MonsterArena(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        from dq4_pc.persistence import savestates as SS
        cls.E, cls.SS = ENGINE, SS
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_stadium_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e):
            for _ in range(250): e.step(0, 0)
            SV.force_chapter(e, 5); e.start_town(TOWN); SV.settle(e, 300, 1500); return e.state.game_map == TOWN
        cls.e, cls.slot = SV.pick_save(make, wanted, 'a readable save (the casino is loaded by force at chapter 5)')
        cls.snap = SS.snapshot(cls.e)

    def setUp(self): self.e.ignored_types = ()                                        # (the engine is shared by the tests: the viewer's filter is only set by those that play the back button)

    def coins(self): c = self.e.core; return struct.unpack('<I', c.mem(c.export(G_PARTY) + COINS, 4))[0]

    def press(self, port, cell, button):
        """One touch on a cell (`button` = the gamepad key sent with it), then released, as the port does."""
        e = self.e
        e.send_menu(port, 1, cell, button)
        for _ in range(3): e.step(0, 0)
        e.send_menu(port, 1, -1, 0)
        for _ in range(5): e.step(0, 0)

    def advance(self, window, limit=1500, texts=None):
        """Turns the messages (A) until the window of that type is the active one. -> its port."""
        e, E = self.e, self.E
        for i in range(limit):
            port = e.active_menu()
            if port is not None and e.ui.f[port].get('type') == window: return port
            feed = e.msg_visible and (e.ui.msg.get('feed') or e.message_state()[1] in (3, 5))
            pad = E.A if (port is None and feed and i % 6 == 0) else 0
            e.step(pad, pad)
            for s in e.sensor.drain():
                if texts is not None: texts.append(s['text'])
        self.fail('the window %d never came (types seen: %s, texts: %s)' % (window, sorted(self.rec.types), (texts or [])[-3:]))

    def start(self):
        e, c = self.e, self.e.core
        self.SS.apply(e, self.snap); self.rec = Recorder(); e.ui.obs = self.rec
        c.call(c.export(SET_COINS), c.export(G_PARTY), START)
        wm = c.call(c.export(WM), label='wm'); c.mem_w(wm + 0x10, struct.pack('<i', 0))
        c.call(c.export(PHASE_FN), c.export(TWS), ARENA, label='phase')
        self.texts = []

    def test_choose_monster_and_bet(self):
        e = self.e; self.start()
        port = self.advance(SELECT, texts=self.texts)
        cells = e.ui.f[port]['cells']
        monsters = [cells[(i, 0)] for i in range(3)]
        odds = [cells[(i, 1)] for i in range(3)]
        self.assertTrue(all(m.strip() for m in monsters), monsters)
        self.assertEqual(len(set(monsters)), 3, 'three different monsters on the poster: %s' % monsters)
        for o in odds: self.assertRegex(o, r'^×\s*\d+\.\d\s*$', 'odds "x n.n" in the window: %r' % o)
        self.assertEqual(cells[(4, 1)].strip(), str(START), 'the window shows the coins')
        self.assertTrue(any('prochain combat' in t for t in self.texts), self.texts)
        self.press(port, 1, A)                                                          # the second monster
        self.texts.clear()
        port = self.advance(BET, texts=self.texts)
        cells = e.ui.f[port]['cells']
        self.assertTrue(any('jeton le ticket' in t and '50 tickets' in t for t in self.texts), self.texts)    # (the price and the limit are the engine's)
        self.assertEqual(cells[(0, 1)], monsters[1], 'the window names the monster chosen')
        self.assertIn(str(START), cells[(0, 2)])
        self.assertEqual((cells[(1, 0)], cells[(2, 0)]), ('0', '0'))
        for _ in range(3): self.press(port, 1, 0x2)                                   # three times "+1"
        self.assertEqual(e.ui.f[port]['cells'][(1, 0)], '3', 'the bet counter shows 3: %s' % e.ui.f[port]['cells'])
        self.assertEqual(self.coins(), START, 'nothing is paid before the bet is confirmed')
        self.texts.clear()
        self.press(port, 3, A)                                                          # "Start the fight"
        self.advance(ABORT, limit=2500, texts=self.texts)
        self.assertTrue(any('3 tickets' in t for t in self.texts), self.texts)
        self.assertEqual(self.coins(), START - 3, 'three tickets = three coins')

    def test_battle_starts_with_abort_window(self):
        e = self.e; self.start()
        port = self.advance(SELECT)
        self.press(port, 0, A)
        port = self.advance(BET)
        self.press(port, 1, 0x2)
        self.press(port, 3, A)
        port = self.advance(ABORT, limit=2500, texts=self.texts)
        self.assertEqual(e.state.part, self.E.PART_BATTLE)
        self.assertEqual(e.state.game_map, BATTLE_MAP)
        self.assertEqual(e.ui.f[port]['cells'][(0, 0)], 'Quitter')
        for _ in range(60): e.step(0, 0)
        appear = [t for t in self.texts if 'appara' in t]
        self.assertEqual(len(appear), 3, 'the three monsters appear: %s' % self.texts)
        self.assertTrue({SELECT, BET, ABORT} <= self.rec.types, sorted(self.rec.types))
        self.assertFalse([t for t in self.texts if re.search(r'ERROR \d+|<ERR', t)], self.texts)

    def test_bet_zero_goes_back_to_the_poster(self):
        """Confirming with no ticket does not start anything: the engine shows the poster again (nothing paid)."""
        e = self.e; self.start()
        port = self.advance(SELECT)
        self.press(port, 0, A)
        port = self.advance(BET)
        self.press(port, 3, A)
        self.texts.clear()
        self.advance(SELECT, texts=self.texts)
        self.assertEqual(self.coins(), START)
        self.assertNotEqual(e.state.part, self.E.PART_BATTLE)
        self.assertTrue(any('prochain combat' in t for t in self.texts), self.texts)

    # ---- leaving the fight
    def fight(self):
        """Arena battle reached, the way the viewer sees it (window 71 has no input). -> port of window 71."""
        e = self.e; self.start()
        port = self.advance(SELECT); self.press(port, 0, A)
        port = self.advance(BET); self.press(port, 1, 0x2); self.press(port, 3, A)
        port = self.advance(ABORT, limit=2500, texts=self.texts); e.ignored_types = (ABORT,)          # (the viewer's setting, from now on)
        return port

    def enable(self): c = self.e.core; return c.mem(self.e.L + G_ENABLE, 1)[0]

    def play(self, port, steps, back=False, texts=None, stop=None):
        """`steps` engine steps: messages turned with A; `back`: the back key at every step while window 71 is shown (what the viewer's button does until the engine switches it off).
        -> steps played (up to `stop(i)` true)."""
        e, E = self.e, self.E
        for i in range(steps):
            p = e.active_menu(); typ = e.ui.f[p].get('type') if p is not None else None
            feed = e.msg_visible and (e.ui.msg.get('feed') or e.message_state()[1] in (3, 5))
            pad = E.A if (p is None and feed and i % 6 == 0) else 0
            decl = pad | (BACK if back and e.ui.f[port]['visible'] and e.state.part == E.PART_BATTLE else 0)
            e.step(pad, decl)
            for s in e.sensor.drain():
                if texts is not None: texts.append(s['text'])
            if stop and stop(i): return i
        return steps

    def request_leave(self):
        """Fight under way, a message on screen, then the back key until the window is off. -> (port of window 71, texts of the fight, steps taken by the engine to switch the window off)."""
        e = self.e; port = self.fight(); texts = []
        self.play(port, 600, texts=texts, stop=lambda i: len(texts) >= 4 and e.msg_visible)
        self.assertEqual(self.enable(), 1, 'the window is on during the fight'); self.assertIsNone(e.active_menu(), 'ignored type: "Quitter" never owns the input')
        self.assertNotIn(port, e.input_menus())
        taken = self.play(port, 60, back=True, texts=texts, stop=lambda i: not e.ui.f[port]['visible'])
        self.assertLess(taken, 40, 'the engine reads the key within a few steps'); self.assertEqual(self.enable(), 0, 'switched off by the engine (setBattleStadiumAbort(false))')
        return port, texts

    def question(self, port, texts):
        """Turns the rest of the action's messages until the Yes / No of "Attendez !". -> its port."""
        e = self.e; yn = []
        self.play(port, 1500, texts=texts, stop=lambda i: yn.append(e.active_menu()) or (yn[-1] is not None and e.ui.f[yn[-1]].get('type') == 1))
        yn = yn[-1]; self.assertIsNotNone(yn, texts[-4:]); self.assertEqual(e.ui.f[yn]['cells'].get((0, 0)), 'Oui'); self.assertEqual(e.ui.f[yn]['cells'].get((1, 0)), 'Non')
        self.assertTrue(any('Attendez' in t and 'tickets' in t for t in texts), texts[-4:])
        self.assertTrue('Attendez' in texts[-1], 'the question comes after the messages of the action in progress: %s' % texts[-3:])
        return yn

    def test_back_key_asks_then_yes_leaves(self):
        e = self.e; port, texts = self.request_leave(); yn = self.question(port, texts)
        self.press(yn, 0, A); after = []
        self.play(port, 1500, texts=after, stop=lambda i: e.state.part != self.E.PART_BATTLE)
        self.assertNotEqual(e.state.part, self.E.PART_BATTLE, 'Oui: the battle ends'); self.assertTrue(any('arr' in t and 'combat' in t for t in after), after)
        self.assertEqual(self.coins(), START - 1, 'the ticket is lost, nothing is won')

    def test_back_key_asks_then_no_goes_on(self):
        e = self.e; port, texts = self.request_leave(); yn = self.question(port, texts)
        self.press(yn, 1, A); after = []
        self.play(port, 600, texts=after, stop=lambda i: e.ui.f[port]['visible'] and any('installez' in t for t in after))
        self.assertTrue(any('installez-vous' in t for t in after), after)
        self.assertTrue(e.ui.f[port]['visible'] and self.enable() == 1, 'Non: the window is switched back on'); self.assertEqual(e.state.part, self.E.PART_BATTLE)
        again = []; self.play(port, 300, texts=again)
        self.assertTrue(any('attaque' in t or 'lance' in t for t in again), 'the fight goes on: %s' % again[:3]); self.assertEqual(self.coins(), START - 1)

    def test_no_request_no_question(self):
        """The window alone does nothing: no key, no question (and without the filter the engine's window used to take the input)."""
        e = self.e; port = self.fight(); texts = []
        self.play(port, 400, texts=texts)
        self.assertFalse([t for t in texts if 'Attendez' in t], texts); self.assertEqual(self.enable(), 1)


if __name__ == '__main__':
    unittest.main()
