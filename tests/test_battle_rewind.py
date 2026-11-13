"""Battle rewind of the history: the battle messages are kept with their battle, then replayed at their pace with only a speed button and a back button.

Checks: recording (the Sensor's battle records go to the battle that ends, a battle whose start was not seen keeps nothing, caps), file round trip and favorite copy, the replay schedule
(gaps cut, speeds Normal / Fast / Very fast, Manual waits for a key, Enter completes then advances), the window (Space or a click on a battle opens it, a battle without messages
shows a notice, Esc / right click / back button close it, V cycles the speed, nothing else reacts, the list is frozen meanwhile, leaving the window closes it).

    python3 tests/test_battle_rewind.py
"""
import os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq4_pc import language as LG
LG.select_language('fr')
from dq4_pc.core import history as HI
from dq4_pc.menus import battle_rewind as BR
from dq4_pc.menus import ui_history as UH
from dq4_pc.persistence import settings as RG


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def record(text, t, cat=HI.CATEGORY_BATTLE):
    return {'text': text, 'kind': 'g', 'val': None, 'cat': cat, 'map': 'x', 't': t}


def battle(t=900):
    return {'t': t, 'outcome': 'victory', 'gold': 3, 'xp': 4, 'enemies': [{'name': 'Gluant', 'total': 1, 'defeated': 1}]}


class FakeEngine:
    def __init__(self):
        self.out = []; self.ends = []
        self.sensor = types.SimpleNamespace(active=True, drain=self._drain)
        self.battle_sensor = types.SimpleNamespace(tracking=None, do_update=self._ends)
        self.state = types.SimpleNamespace(part=HI.PART_BATTLE, game_map='x'); self.ui = types.SimpleNamespace(msg={'feed': False}); self.msg_visible = True
    def _drain(self): s, self.out = self.out, []; return s
    def _ends(self, eng): s, self.ends = self.ends, []; return s


class TestRecording(unittest.TestCase):
    def test_messages_go_to_the_battle(self):
        h = HI.History(None, Clock()); m = FakeEngine(); m.battle_sensor.tracking = object()
        m.out += [record('Un gluant apparaît !', 1000), record('Ragnar attaque !', 1030)]; h.do_update(m)
        m.out += [record('Le gluant est vaincu !', 1100)]; m.ends.append(battle()); m.battle_sensor.tracking = None; h.do_update(m)
        self.assertEqual(h.battles[-1].log, [[0, None, 'Un gluant apparaît !'], [30, None, 'Ragnar attaque !'], [100, None, 'Le gluant est vaincu !']])
        self.assertEqual(h.dialogues, [])
        m.ends.append(battle(2000)); h.do_update(m); self.assertEqual(h.battles[-1].log, [])            # (the next battle does not take the previous messages)

    def test_messages_without_a_tracked_battle_are_dropped(self):
        h = HI.History(None, Clock()); m = FakeEngine()                                                   # (savestate loaded mid-battle: no battle tracked)
        m.out += [record('Ragnar attaque !', 10)]; h.do_update(m)
        m.battle_sensor.tracking = object(); m.out += [record('Un gluant apparaît !', 50)]; h.do_update(m)
        m.ends.append(battle()); h.do_update(m); self.assertEqual([x[2] for x in h.battles[-1].log], ['Un gluant apparaît !'])

    def test_caps(self):
        log = HI.battle_log([record('m%d' % i, i) for i in range(HI.MAX_LOG + 10)] + [record('x' * 999, 5000)])
        self.assertEqual((len(log), log[-1][2]), (HI.MAX_LOG, 'm%d' % (HI.MAX_LOG - 1)))
        self.assertEqual(len(HI.battle_log([record('y' * 999, 1)])[0][2]), HI.MAX_LOG_TEXT)

    def test_file_round_trip_and_favorite(self):
        d = tempfile.mkdtemp(prefix='rw_'); self.addCleanup(shutil.rmtree, d, True); f = os.path.join(d, 'history_favorites.json')
        h = HI.History(f, Clock()); h.set_adventure('0123456789ab'); e = h.add_battle(battle(), [record('A.', 10), record('B.', 40)]); h.toggle_favorite(e); h.store(True)
        h2 = HI.History(f, Clock()); h2.set_adventure('0123456789ab')
        self.assertEqual(h2.battles[0].log, [[0, None, 'A.'], [30, None, 'B.']]); self.assertEqual(h2.favorites[0].log, [[0, None, 'A.'], [30, None, 'B.']])
        old = {'k': 'c', 'id': None, 't': 1, 'enemies': [], 'outcome': 'victory'}                        # (battle: no log)
        self.assertEqual(HI.Element.from_dict(old, 1, recent=True).log, [])
        self.assertIsNone(HI.Element.from_dict(dict(old, log=[[1, None]]), 1, recent=True))


def run(r, c, seconds, speed=1.0):
    """Displayed frames of 1/60 s for `seconds` (the replay caps one tick at 0.25 s: a frozen window does not jump ahead)."""
    for _ in range(int(round(seconds * 60))): c.t += 1 / 60.0; r.tick(speed)


def element(log):
    e = HI.Element(1, HI.BATTLE_TYPE, 900); e.log = log; return e


class TestReplay(unittest.TestCase):
    def test_schedule_cuts_long_waits(self):
        self.assertEqual(BR.schedule([[0, None, 'a'], [30, None, 'b'], [5000, None, 'c']]), [BR.FIRST_DELAY, BR.FIRST_DELAY + 30, BR.FIRST_DELAY + 30 + BR.MAX_GAP])

    def test_speeds(self):
        for speed, frames in ((1.0, 60), (2.0, 120), (3.0, 180)):
            c = Clock(); r = BR.Replay(element([[0, None, 'a']]), c); run(r, c, 1.0, speed); self.assertAlmostEqual(r.t, frames, 3)
        c = Clock(); r = BR.Replay(element([[0, None, 'a']]), c); c.t += 5.0; r.tick(1.0); self.assertAlmostEqual(r.t, 15.0)                     # (a 5 s freeze counts as 0.25 s)

    def test_typing_and_order(self):
        c = Clock(); r = BR.Replay(element([[0, None, 'Bonjour'], [20, None, 'Suite']]), c)
        self.assertEqual(r.shown(), [])
        run(r, c, (BR.FIRST_DELAY + 3) / 60.0); self.assertEqual(r.shown(), [(None, 'Bonjour', 3)])
        run(r, c, 0.4); self.assertEqual([n for _, _, n in r.shown()], [7, 5]); self.assertFalse(r.finished())
        run(r, c, 1.0); self.assertTrue(r.finished())

    def test_manual_waits_for_a_key(self):
        c = Clock(); r = BR.Replay(element([[0, None, 'A'], [10, None, 'B']]), c)
        run(r, c, 2.0, 0.0)
        self.assertEqual([t for _, t, _ in r.shown()], ['A'])                                              # Manuel: B waits
        r.advance(0.0); self.assertEqual([t for _, t, _ in r.shown()], ['A', 'B'])

    def test_advance_completes_then_skips(self):
        c = Clock(); r = BR.Replay(element([[0, None, 'Long message'], [100, None, 'B']]), c)
        run(r, c, (BR.FIRST_DELAY + 1) / 60.0); r.advance(1.0); self.assertEqual(r.shown()[0][2], len('Long message'))      # first press: the message in full
        r.advance(1.0); self.assertEqual(len(r.shown()), 2)                                                # second press: the next one starts now


class FakeReg(dict):
    def __init__(self): super().__init__(battle_speed=1.0, keys={'battle_speed': ['V', None]}, history_favorites_only=False); self.stored = 0
    def action_of(self, symbol): return RG.Settings(None).action_of(symbol)
    def store(self): self.stored += 1


def view(battles):
    h = HI.History(None, Clock())
    for log in battles: h.add_battle(battle(), [record(t, i * 30) for i, t in enumerate(log)])
    calls = []
    P = types.SimpleNamespace(mouse_mode=False, mouse_pos=None, back=lambda: calls.append('back'), shutdown=lambda: calls.append('shutdown'), _repeat=lambda *a: None)
    P.J = types.SimpleNamespace(history=h, reg=FakeReg(), height=720)
    v = UH.HistoryView(P); v.clock = Clock(); v.enter(UH.O_BATTLES); v.calls = calls
    return v


class TestWindow(unittest.TestCase):
    def test_space_opens_and_keys(self):
        K = pyglet.window.key; v = view([['A !', 'B !']])
        v.key_press(K.SPACE); self.assertIsNotNone(v.rewind)
        v.key_press(K.V); self.assertEqual(v.J.reg['battle_speed'], 2.0)                                # same cycle as in battle
        v.key_press(K.RETURN); self.assertIsNotNone(v.rewind); self.assertEqual(v.J.history.favorites, [])  # Enter advances, never stars here
        v.key_press(K.LEFT); v.key_press(K.F); self.assertEqual((v.tab, v.favorites_only), (UH.O_BATTLES, False))       # nothing else reacts
        v.move_by(-1); v.wheel(3.0); self.assertIsNotNone(v.rewind)
        v.key_press(K.ESCAPE); self.assertIsNone(v.rewind); self.assertEqual(v.calls, [])                   # back to the list, the window stays open

    def test_only_the_play_button_opens(self):
        M = pyglet.window.mouse; v = view([['A !'], ['B !']])
        v.zones = [(0, 0, 100, 50, 0), (0, 60, 100, 110, 1)]; v.play_zones = [(120, 60, 140, 80, 1)]
        v.click(10, 70, M.LEFT); v.release(10, 70, M.LEFT); self.assertIsNone(v.rewind); self.assertEqual(v.selected, 1)       # a click on the battle: selected, not replayed
        v.click(130, 70, M.LEFT); self.assertEqual(v.rewind.e, v.elements[1])                                 # the play button
        v.rewind_zones = {'speed': (0, 0, 10, 10), 'quit': (20, 0, 30, 10)}
        v.click(5, 5, M.LEFT); self.assertEqual(v.J.reg['battle_speed'], 2.0)
        v.click(500, 500, M.LEFT); self.assertIsNotNone(v.rewind)                                            # elsewhere: next message
        v.click(25, 5, M.LEFT); self.assertIsNone(v.rewind); self.assertEqual(v.selected, 1)
        v.click(130, 70, M.LEFT); v.click(500, 500, M.RIGHT); self.assertIsNone(v.rewind); self.assertEqual(v.calls, [])

    def test_dialogues_tab_and_space(self):
        K = pyglet.window.key; v = view([['A !']]); v.change_tab(UH.O_DIALOGUES); v.J.history.add('Bonjour.', None, 1); v.reload()
        v.key_press(K.SPACE); self.assertIsNone(v.rewind); self.assertEqual(len(v.J.history.favorites), 1)          # (dialogues: Space still stars)

    def test_battle_without_messages(self):
        K = pyglet.window.key; v = view([[]])
        v.key_press(K.SPACE); self.assertIsNone(v.rewind); self.assertEqual(v.notice[0], UH.NO_REWIND)

    def test_frozen_list_and_leave(self):
        K = pyglet.window.key; v = view([['A !']]); v.key_press(K.SPACE)
        v.J.history.add_battle(battle(5000), [record('Nouveau', 1)]); self.assertFalse(v.follow_game()); self.assertEqual(len(v.elements), 1)
        v.leave(); self.assertIsNone(v.rewind)


if __name__ == '__main__':
    unittest.main()
