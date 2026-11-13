"""The martial colosseum of chapter 2 (window 68, phase 22) played with the real engine and a real chapter 2 save (Alina's party).

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_colosseum_real.py        (a few seconds)

The colosseum is made of three maps: the lobby `cccf1a` (the registration desk on the left, the stairs for the spectators), the basements, and the arena `cccf2` (the fighters wait there, the
opponent is announced by the script). What is established here, with the original engine:

* **registration** (`cccf1a`): the clerk at the desk answers "Vous ne pouvez pas participer au tournoi si votre nom n'est pas inscrit. Vous devez d'abord obtenir la permission du roi Norbert."
  until the story flag `cmd_set_flag` kind 0 number 102 is set (the king's permission, given by the chapter 2 scenario); then "Vous etes la tsarine Alina, n'est-ce pas ? Bonne chance pour le tournoi."
  and the script sets the flag kind 1 number 1 (registered). The flags were found by bisection (setting kind 0 numbers 0..1023, then halving: only 102 changes the clerk's answer);
* **the announcement** (`cmd_menu_colosseum`, `__cmd_menu_colosseum::initialize` stores its argument in `MaterielMenuPlayerControl + 0x18`, then `changeShopMenuPhase(22)`):
  the HP window (type 68), the offer "Princesse Alina. Voulez-vous utiliser quelques-unes de vos herbes medicinales pour vous soigner avant le prochain combat ?" with Yes / No (window 1),
  "Mais vous semblez deja etre en parfaite sante, Votre Grandeur." when Alina is at full health and the answer is Oui, then "Le prochain adversaire de la princesse Alina est <name> !".
  The five opponents are the arguments 1 (Aubert le Vif), 2 (Maggie Magie), 3 (le Chevalier Samson), 4 (l'Abomihomme des neiges) and 0 (Attila le Deux, the last one).

With a chapter 1 party the same call crashed in `MaterielMenu_MARTIAL_COLOSSEUM::checkHaveYakusou` (member -1): that was an artefact of the forced chapter, not a defect.

Not covered: the fight itself. It is started by the arena script (`cccf2`, object 8) after the announcement; no headless way was found to start that script (the lobby's door to the basements and the
chain of maps are not walked here), so the fight with Alina is **not played**; the injured case (Oui with herbs in the bag) is not played either.
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
LOBBY, ARENA = 'cccf1a', 'cccf2'
A, TALK = 0x10, 0x100
UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8                 # (pad bits; in a town UP = +z)
PHASE_FN = '_ZN6window13CommandWindow19changeShopMenuPhaseEi'
WM = '_ZN27MaterielMenu_WINDOW_MANAGER12getSingletonEv'
TWS = '_ZN16TownWindowSystem11m_singletonE'
PLAYER_CONTROL = '_ZN25MaterielMenuPlayerControl12getSingletonEv'
SET_FLAG, GET_FLAG = '_Z12cmd_set_flagP16CommandParameter', '_Z12cmd_get_flagP16CommandParameter'
KING_PERMISSION, REGISTERED = (0, 102), (1, 1)     # (kind, number)
OPPONENTS = {1: 'Aubert le Vif', 2: 'Maggie Magie', 3: 'Chevalier', 4: 'Abomihomme', 0: 'Attila le Deux'}
WINDOW_HP, WINDOW_YES_NO = 68, 1


class Recorder:
    """`Interface.obs`: every window type the engine creates."""
    def __init__(self): self.types = set()
    def open_menu(self, port, typ): self.types.add(typ)
    def __getattr__(self, name):
        if name.startswith('_'): raise AttributeError(name)
        return lambda *a, **k: None


def clean(text): return text.replace(';', '').replace('\xa0', ' ').strip()          # (";" = break mark of the patch texts, see core/history.without_marks)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder>')
class MartialColosseum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        from dq4_pc.persistence import savestates as SS
        cls.E, cls.SS = ENGINE, SS

        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_colosseum_'))
            for _ in range(3): e.step(0, 0)
            return e

        def wanted(e):
            for _ in range(250): e.step(0, 0)
            if SV.chapter(e) != 2: return False                                              # (Alina's party comes from the save: it cannot be forced)
            e.start_town(LOBBY); SV.settle(e, 300, 1500); return e.state.game_map == LOBBY
        cls.e, cls.slot = SV.pick_save(make, wanted, 'a save at chapter 2 (Alina, Kiryl, Borya)')
        e = cls.e
        cls.hold(LEFT, 22); cls.hold(DOWN, 10); cls.hold(LEFT, 9); cls.hold(UP, 2)          # to the clerk's desk, facing her (measured from the arrival point of the lobby)
        cls.desk = SS.snapshot(e)
        e.start_town(ARENA); SV.settle(e, 300, 1500)
        cls.arena = SS.snapshot(e)
        c = e.core; cls.buf = c.malloc(64)

    @classmethod
    def hold(cls, bit, n):
        for _ in range(n): cls.e.step(bit, 0)
        for _ in range(6): cls.e.step(0, 0)

    def flag(self, kind_number, value=1):
        c = self.e.core; c.mem_w(self.buf, struct.pack('<8i', 0, kind_number[0], kind_number[1], value, 0, 0, 0, 0)); c.call(c.export(SET_FLAG), self.buf)

    def is_set(self, kind_number):
        c = self.e.core; c.mem_w(self.buf, struct.pack('<8i', 0, kind_number[0], kind_number[1], 1, 0, 0, 0, 0)); return bool(c.call(c.export(GET_FLAG), self.buf) & 1)

    def setUp(self): self.e.ignored_types = (); self.rec = Recorder(); self.e.ui.obs = self.rec

    # -- registration
    def talk_to_clerk(self, permission):
        e = self.e
        self.SS.apply(e, self.desk); self.rec = Recorder(); e.ui.obs = self.rec
        for _ in range(3): e.step(0, 0)
        if permission: self.flag(KING_PERMISSION)
        self.assertFalse(self.is_set(REGISTERED), 'nobody is registered yet')
        texts = []
        e.sensor.drain(); e.step(0, TALK)
        for i in range(500):
            feed = e.msg_visible and (e.ui.msg.get('feed') or e.message_state()[1] in (3, 5))
            pad = A if (feed and e.active_menu() is None and i % 6 == 0) else 0
            e.step(pad, pad)
            texts += [clean(s['text']) for s in e.sensor.drain()]
        return texts

    def test_clerk_wants_the_kings_permission(self):
        texts = self.talk_to_clerk(False)
        self.assertTrue(any('la permission du roi Norbert' in t for t in texts), texts)
        self.assertFalse(any('tsarine Alina' in t for t in texts), texts)
        self.assertFalse(self.is_set(REGISTERED), 'without the permission nobody is registered')

    def test_clerk_registers_alina(self):
        texts = self.talk_to_clerk(True)
        self.assertTrue(any("Vous êtes la tsarine Alina, n'est-ce pas ?" in t and 'Bonne chance pour le tournoi' in t for t in texts), texts)
        self.assertFalse(any('permission du roi' in t for t in texts), texts)
        self.assertTrue(self.is_set(REGISTERED), 'the script sets the "registered" flag')
        self.assertFalse([t for t in texts if 'ERROR ' in t], texts)

    # -- announcement of the next opponent
    def announce(self, argument, answer):
        """The script's `cmd_menu_colosseum <argument>`; the offer of herbs is answered with the cell `answer` (0 = Oui, 1 = Non). -> (texts, windows seen as [(type, cells)], types created)."""
        e, c = self.e, self.e.core
        self.SS.apply(e, self.arena); self.rec = Recorder(); e.ui.obs = self.rec
        for _ in range(3): e.step(0, 0)
        pc = c.call(c.export(PLAYER_CONTROL), label='pc'); c.mem_w(pc + 0x18, struct.pack('<i', argument))
        wm = c.call(c.export(WM), label='wm'); c.mem_w(wm + 0x10, struct.pack('<i', 0))
        c.call(c.export(PHASE_FN), c.export(TWS), 22, label='phase')
        texts, windows, waiting, release, idle = [], [], 0, None, 0
        for i in range(2500):
            p = d = 0
            if release is not None: e.send_menu(release, 1, -1, 0); release = None
            port = e.active_menu()
            feed = e.msg_visible and (e.ui.msg.get('feed') or e.message_state()[1] in (3, 5))
            if port is not None or feed:
                waiting += 1
                if waiting % 6 == 0:
                    if port is None: p = d = A
                    else:
                        windows.append((e.ui.f[port].get('type'), {k: str(v) for k, v in e.ui.f[port]['cells'].items()}))
                        e.send_menu(port, 1, answer, A); release = port
            else: waiting = 0
            e.step(p, d)
            texts += [clean(s['text']) for s in e.sensor.drain()]
            idle = idle + 1 if (port is None and not e.msg_visible) else 0
            if i > 200 and idle > 400: break
        return texts, windows, self.rec.types

    def test_the_five_opponents(self):
        seen = {}
        for argument, name in OPPONENTS.items():
            texts, windows, types = self.announce(argument, 1)
            self.assertIn(WINDOW_HP, types, 'argument %d: the HP window of the colosseum' % argument)
            self.assertTrue(any('Voulez-vous utiliser quelques-unes de vos herbes médicinales pour vous soigner avant le prochain combat ?' in t for t in texts), (argument, texts))
            self.assertIn((WINDOW_YES_NO, {'(0, 0)': 'Oui', '(1, 0)': 'Non'}), [(t, {str(k): v for k, v in cells.items()}) for t, cells in windows], (argument, windows))
            line = [t for t in texts if 'Le prochain adversaire de la princesse Alina est' in t]
            self.assertEqual(len(line), 1, (argument, texts))
            self.assertIn(name, line[0], 'argument %d announces %s' % (argument, name))
            seen[argument] = line[0]
            self.assertFalse([t for t in texts if 'ERROR ' in t], (argument, texts))
            self.assertEqual(self.e.state.part, self.E.PART_TOWN, 'argument %d: the service gave control back' % argument)
            self.assertIsNone(self.e.active_menu(), 'argument %d: a window is still waiting' % argument)
            self.assertFalse(self.e.msg_visible, 'argument %d: a message is still there' % argument)
        self.assertEqual(len(set(seen.values())), 5, 'five different opponents: %s' % seen)

    def test_herbs_when_already_in_perfect_health(self):
        texts, windows, types = self.announce(1, 0)                                          # "Yes" with Alina at full health
        self.assertTrue(any('Mais vous semblez déjà être en parfaite santé, Votre Grandeur.' in t for t in texts), texts)
        k = [i for i, t in enumerate(texts) if 'parfaite santé' in t][0]
        self.assertTrue(any('Le prochain adversaire de la princesse Alina est Aubert le Vif' in t for t in texts[k:]), 'the announcement follows: %s' % texts)
        self.assertFalse([t for t in texts if 'ERROR ' in t], texts)
        self.assertEqual(self.e.state.part, self.E.PART_TOWN)


if __name__ == '__main__':
    unittest.main(verbosity=2)
