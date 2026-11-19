"""Test of the automatic save of the game: the original game writes NO automatic save when it is closed. It is written by the engine itself, in two places only
(`TownPart::initialize` and `FieldPart::initialize` of libdq4core, depending on the conditions of the game: arrival on the world map, arrival in a dungeon...). The viewer adds nothing: closing the window
(X button, Alt + F4, Quit menu...) saves the settings and the history, period. (The closing code, which forced `AutoSave(true)` and put the player back "to the pixel", is removed.)

    python3 tests/test_autosave.py [--apk <folder of the patched APKs> --saves <folder of the saves>]
(or DQ_APK and DQ_SAVES; without them only parts 1 and 2 run). Part 3 loads the real engine (about 1 minute).

Part 1 (without engine): nothing left in Engine or in Game that forces an automatic save, or that watches the console, the signals, the end of the session.
Part 2 (simulated window): Game.on_close does not touch the engine ; the Quit menu goes through on_close.
Part 3 (real engine): arrival in a town does not write bank 4 ; arrival on the world map writes it (the engine alone) ; closing the window writes nothing ; "Revenir a l'ecran titre" erases it and it does not come back.
"""
import argparse, hashlib, inspect, os, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
pyglet.options['shadow_window'] = False                     # (no display needed: nothing is drawn)
from dq456_pc.core import engine as ENGINE
from dq456_pc.window import game as F

APK = os.environ.get('DQ_APK'); SAVES = os.environ.get('DQ_SAVES'); REST = sys.argv[1:]
if __name__ == '__main__':
    _ap = argparse.ArgumentParser(); _ap.add_argument('--apk'); _ap.add_argument('--saves'); _a, REST = _ap.parse_known_args()
    APK = _a.apk or APK; SAVES = _a.saves or SAVES
PAD_A = 0x10


# ---------------------------------------------------------------------------------------------------------------------------------- 1. the code
class NothingForcesSave(unittest.TestCase):
    def test_engine_no_longer_has_forced_save(self):
        for name_str in ('sauvegarde_auto', 'sauvegarde_auto_possible', 'retour_titre_fait'):
            self.assertFalse(hasattr(ENGINE.Engine, name_str), name_str)
        self.assertNotIn('_Z8AutoSaveb', inspect.getsource(ENGINE))                                    # AutoSave is no longer called by the viewer (the engine calls it by itself)
        self.assertNotIn('retour_titre_fait', inspect.getsource(ENGINE))

    def test_window_no_longer_has_special_closing(self):
        for name_str in ('_sauvegarde_fermeture', '_installer_arret_externe', '_arret_console', '_arret_externe_traiter'):
            self.assertFalse(hasattr(F.Game, name_str), name_str)
        src = _paths.source('window.py')
        for pattern in ('_event_endsession', 'SetConsoleCtrlHandler', '_arret_externe', '_arret_motif', '_auto_faite', 'DQ_SAVE_ON_CLOSE', 'sauvegarde_auto'):
            self.assertNotIn(pattern, src, pattern)

    def test_loop_no_longer_looks_at_other_threads_requests(self):
        self.assertNotIn('_arret', inspect.getsource(F.Game._loop))

    def test_on_close_saves_settings_history_and_closes_sound(self):
        src = inspect.getsource(F.Game.on_close) + inspect.getsource(F.Game._save_on_exit)         # saving is in _save_on_exit, shared with the error safeguard
        self.assertTrue(src.index('self._ready') < src.index('self.reg.store()') < src.index('self.sound.shutdown()'))
        self.assertIn('self.history.store(True)', src); self.assertNotIn('engine', src)
        self.assertIn('self._save_on_exit()', inspect.getsource(F.Game.on_close))

    def test_quit_menu_goes_through_on_close(self):
        src = inspect.getsource(F.Game.quit_game); self.assertIn('self.on_close()', src); self.assertNotIn('self.close()', src)

    def test_returning_to_title_always_clears_bank_4(self):
        src = inspect.getsource(ENGINE.Engine.back_to_title); self.assertIn('killbank', src); self.assertIn('startTitle', src)


# ---------------------------------------------------------------------------------------------------------------------------------- 2. the window (simulated)
class UntouchableEngine:
    """An engine that raises an error at the slightest access: the closing has nothing to ask of it."""
    def __getattr__(self, name_str): raise AssertionError('closing touched the engine: %s' % name_str)


class FakeWindow:
    """What the closing reads from Game ; the real on_close method is bound to it."""
    _dying = False                                                                               # (on_close does not save a second time after a fatal error)
    _save_on_exit = F.Game._save_on_exit

    def __init__(self, ready=True, engine=None):
        self._ready = ready; self._closed = False; self.calls = []; self.engine = engine if engine is not None else UntouchableEngine()
        self.reg = types.SimpleNamespace(store=lambda: self.calls.append('reglages'))
        self.history = types.SimpleNamespace(store=lambda force=False: self.calls.append('history'))
        self.sound = types.SimpleNamespace(shutdown=lambda: self.calls.append('sound'))
    def on_close(self):
        # (the last line of Game.on_close is super().on_close(): the pyglet window, absent here)
        try: F.Game.on_close(self)
        except (TypeError, RuntimeError, AttributeError) as ex:
            if 'super' not in str(ex) and 'argument' not in str(ex) and 'Game' not in str(ex): raise


class SimulatedClosing(unittest.TestCase):
    def test_closing_does_not_touch_engine(self):
        J = FakeWindow(); J.on_close()
        self.assertEqual(J.calls, ['reglages', 'history', 'sound'])                                # everything the closing does ; no save of the game

    def test_during_logos_window_closes_without_writing_anything(self):
        J = FakeWindow(ready=False); J.on_close(); self.assertTrue(J._closed); self.assertEqual(J.calls, [])


# ---------------------------------------------------------------------------------------------------------------------------------- 3. the real engine
def md5(path):
    with open(path, 'rb') as f: return hashlib.md5(f.read()).hexdigest()


@unittest.skipUnless(APK and SAVES, 'real engine: --apk and --saves (or DQ_APK and DQ_SAVES)')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wdir = tempfile.mkdtemp(prefix='sv_auto_'); cls.eng = ENGINE.Engine(APK, SAVES, cls.wdir); cls.c = cls.eng.core
        cls.f5 = os.path.join(cls.wdir, 'data5.dat')

    def step(self, n=1, p=0, d=0):
        for _ in range(n): self.eng.step(p, d); self.eng.ui.damage = []; p = d = 0

    def key_press(self, pad):
        port = self.eng.active_menu(); self.assertIsNotNone(port, 'no engine menu waits for a key')
        self.eng.send_menu(port, 1, -1, pad); self.step(1); self.eng.send_menu(port, 1, -1, 0); self.step(1); self.step(8)

    def status(self):
        """Mask of the valid banks (getCatalogStatus: bits 0 to 2 the adventure logs, 3 the suspend save, 4 the automatic save), after re-reading the files (getCatalogView)."""
        self.c.call(self.c.export('_ZN7profile8SaveLoad14getCatalogViewEv')); return self.c.call(self.c.export('_ZN7profile8SaveLoad16getCatalogStatusEv')) & 0xffffffff

    def load(self, number, expected_part):
        self.assertTrue(self.eng.load_save(number)); self.step(200)
        if self.eng.state.part != expected_part: self.skipTest('save %d of this sample is not in part %d (%d)' % (number, expected_part, self.eng.state.part))

    def test_1_arrival_in_town_engine_does_not_write_autosave(self):
        self.assertFalse(os.path.exists(self.f5))
        self.load(1, ENGINE.PART_TOWN)
        self.assertFalse(os.path.exists(self.f5), 'the engine does not save on arrival in a town (TownPart::initialize: AutoSave(false) refuses)')

    def test_2_arrival_on_world_map_engine_writes_it_alone(self):
        self.load(4, ENGINE.PART_FIELD)
        self.assertTrue(os.path.isfile(self.f5), 'FieldPart::initialize calls AutoSave(false): bank 4 is written without any call from the viewer')
        self.assertEqual(os.path.getsize(self.f5), 0x3c00); self.assertTrue(self.status() & 0x10)         # the "Sauvegarde automatique" cell of the start menu exists

    def test_3_closing_window_writes_nothing(self):
        self.load(4, ENGINE.PART_FIELD)
        before = {f: md5(os.path.join(self.wdir, f)) for f in sorted(os.listdir(self.wdir))}
        J = FakeWindow(engine=self.eng); J.on_close()
        self.assertEqual(J.calls, ['reglages', 'history', 'sound'])
        after = {f: md5(os.path.join(self.wdir, f)) for f in sorted(os.listdir(self.wdir))}
        self.assertEqual(before, after, 'closing the window must not modify any save file')

    def test_4_return_to_title_erases_and_nothing_restores_it(self):
        self.load(4, ENGINE.PART_FIELD); self.eng.back_to_title_state = None
        self.assertTrue(self.status() & 0x10)
        self.assertTrue(self.eng.request_return_to_title()); self.step(150)                                      # the game's Yes / No box
        self.assertEqual(self.eng.back_to_title_state, 'dialog')
        self.key_press(PAD_A)                                                                                   # "Yes": killbank(4) then the fade
        self.assertFalse(self.status() & 0x10)                                                               # bank 4 is erased
        for n in range(1, 140):
            self.step(1)
            if n % 10 == 0 or self.eng.state.game_map == ENGINE.TITLE_MAP: self.assertFalse(self.status() & 0x10, 'image %d (carte %s)' % (n, self.eng.state.game_map))      # fade then title: nothing is written
            if self.eng.state.game_map == ENGINE.TITLE_MAP: break
        self.assertEqual(self.eng.state.game_map, ENGINE.TITLE_MAP); self.assertFalse(self.status() & 0x10)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + REST)
