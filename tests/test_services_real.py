"""The town services played with the real engine, window by window.

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_services_real.py        (about 3 minutes)

Until now the services were only opened by hand (`changeShopMenuPhase`, the one entry point of every service, see the technical notes' "Town services").
Here each one is played through the engine's own windows, in the interior of a real shop map (`mam1f1`, chapter 5 forced), by answering the windows the way
the port's menus do (`Engine.send_menu(port, 1, cell, 0x10)` = confirm that cell, `0x20` = back). What is checked, for every service:

* the windows the engine creates (their type numbers, the first column of `docs/audit/coverage.md`): the table below is what was **measured** on save 3;
* the money moves the right way (buying spends, selling earns, the inn charges) and the engine hands control back (no window, no message) once every window is closed;
* no text of the engine says "ERROR <id>" (an identifier missing from the text banks) and no cell says "<ERR ...>" (an item or spell name that did not resolve).

Window types **59, 61, 63**: not opened by any service played here. 59 and 61 are the `ShopBuyBattle` / `ShopBuyInfoBattle` tables (the engine has no battle
menu class that opens a shop), 63 is the quantity asked when selling a stack: the sale list of this version sells one item per line (`sellPluralSellOK` exists but
the list never asks a quantity). They stay documented as "never opened" (technical notes), not as missing.
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
TOWN = 'mam1f1'                                  # interior of an item shop (any town map would do: the phase is entered by hand)
G_PARTY = '_ZN6status7g_PartyE'
GOLD = 0x2e0                                     # g_Party + 0x2e0 = the party's gold (u32)
PHASE_FN = '_ZN6window13CommandWindow19changeShopMenuPhaseEi'
WM = '_ZN27MaterielMenu_WINDOW_MANAGER12getSingletonEv'
TWS = '_ZN16TownWindowSystem11m_singletonE'
A, B = 0x10, 0x20
SERVICES = {                                     # phase: (what, keys answered one per window, window types the engine must create)
    0: ('inn', ['A'], set()),                    # (the Yes / No window of every service exists from the town's loading: it is never "created" here)
    1: ('church', ['A'] * 6, {54, 56, 66}),
    4: ('item shop, buying', ['#0', 'A', 'A'], {57, 58, 60}),
    'sell': ('item shop, selling', ['#1', 'A', 'A'], {57, 62}),
    18: ('annex item shop (castle)', ['A'] * 8, {57, 58, 60}),
    19: ('castle buys armor', ['A'] * 8, {62}),
    12: ('casino tokens, buying', ['A'], {44}),
    16: ('bank', ['A'] * 2, {57, 64}),
    22: ('coliseum', ['A'], {68}),
    23: ('hostage', ['A'] * 8, {21}),
    24: ('Nene', ['A'] * 10, {70}),
}


class Recorder:
    """`Interface.obs`: every window type the engine creates."""
    def __init__(self): self.types = set()
    def open_menu(self, port, typ): self.types.add(typ)
    def __getattr__(self, name):
        if name.startswith('_'): raise AttributeError(name)
        return lambda *a, **k: None


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder>')
class Services(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.persistence import savestates as SS
        cls.E, cls.SS = ENGINE, SS
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_services_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e):
            for _ in range(250): e.step(0, 0)
            SV.force_chapter(e, 5); e.start_town(TOWN); SV.settle(e, 300, 1500); return e.state.game_map == TOWN
        cls.e, cls.slot = SV.pick_save(make, wanted, 'a readable save (the town is loaded by force at chapter 5)')
        cls.snap = SS.snapshot(cls.e)

    def gold(self): c = self.e.core; return struct.unpack('<I', c.mem(c.export(G_PARTY) + GOLD, 4))[0]

    def set_gold(self, g): c = self.e.core; c.mem_w(c.export(G_PARTY) + GOLD, struct.pack('<I', g))

    def open_phase(self, phase):
        e, c = self.e, self.e.core
        wm = c.call(c.export(WM), label='wm'); c.mem_w(wm + 0x10, struct.pack('<i', 0))
        c.call(c.export(PHASE_FN), c.export(TWS), phase, label='phase')

    def play(self, phase, keys, frames=1800):
        """Opens the service, answers one key per waiting window (a message in the way is turned with A), then closes everything.
        -> (window types created, texts of the engine, cells with an unresolved name, gold before, gold after)."""
        e, E = self.e, self.E
        self.SS.apply(e, self.snap); rec = Recorder(); e.ui.obs = rec
        self.set_gold(30000); before = self.gold()
        texts, bad, k, waiting, release = [], [], 0, 0, None
        self.open_phase(4 if phase == 'sell' else phase)
        for _ in range(frames):
            p = d = 0
            if release is not None: e.send_menu(release, 1, -1, 0); release = None
            port = e.active_menu()
            if port is not None and e.ui.f[port].get('type') == 6:                  # (page counter "1/2": it takes no key, the list under it does, as the window routes it)
                port = next((q for q in e.input_menus() if e.ui.f[q].get('type') != 6), None)
            feed = e.msg_visible and (e.ui.msg.get('feed') or e.message_state()[1] in (3, 5))
            if port is not None or feed:
                waiting += 1
                if waiting % 6 == 0:
                    if port is None: p = d = E.A
                    else:
                        t = keys[k] if k < len(keys) else 'B'; k += 1
                        for cell in e.ui.f[port]['cells'].values():
                            if '<ERR' in str(cell): bad.append(str(cell))
                        if t.startswith('#'): e.send_menu(port, 1, int(t[1:]), A)
                        else: e.send_menu(port, 1, -1, A if t == 'A' else B)
                        release = port
            else: waiting = 0
            e.step(p, d)
            for s in e.sensor.drain(): texts.append(s['text'])
            if k > len(keys) + 6 and port is None and not e.msg_visible and e.state.part == E.PART_TOWN: break
        for _ in range(60): e.step(0, 0)
        return rec.types, texts, bad, before, self.gold()

    def check(self, key):
        what, keys, wanted = SERVICES[key]
        phase = 4 if key == 'sell' else key
        types, texts, bad, before, after = self.play(key, keys)
        self.assertTrue(wanted <= types, '%s (phase %s): windows %s, expected at least %s' % (what, phase, sorted(types), sorted(wanted)))
        self.assertEqual(bad, [], '%s: a name did not resolve' % what)
        self.assertFalse([t for t in texts if 'ERROR ' in t], '%s: %s' % (what, [t for t in texts if 'ERROR ' in t]))
        self.assertTrue(texts, '%s: the engine said nothing' % what)
        self.assertEqual(self.e.state.part, self.E.PART_TOWN, '%s: left the town' % what)
        self.assertIsNone(self.e.active_menu(), '%s: a window is still waiting' % what)
        self.assertFalse(self.e.msg_visible, '%s: a message is still there' % what)
        return before, after

    def test_inn_charges(self):
        before, after = self.check(0); self.assertLess(after, before)

    def test_church(self): self.check(1)

    def test_buying_spends(self):
        before, after = self.check(4); self.assertLess(after, before)

    def test_selling_earns(self):
        before, after = self.check('sell'); self.assertGreater(after, before)

    def test_annex_shop(self): self.check(18)

    def test_castle_buys(self): self.check(19)

    def test_casino_tokens(self): self.check(12)

    def test_bank(self): self.check(16)

    def test_coliseum(self): self.check(22)

    def test_hostage(self): self.check(23)

    def test_nene(self): self.check(24)


if __name__ == '__main__':
    unittest.main(verbosity=2)
