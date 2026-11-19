"""One history per adventure: loading an adventure log takes its history, writing a log gives it the history being played, a new game starts an empty one, the title screen leaves it.

Checks (fake engine): new game, log loaded / written, log overwritten by another game (the game's unique ID no longer matches), back to the title, index file unreadable, the single history
taken over by the first adventure; with the real engine (DQ_APK, DQ_SAVES): the `loadbank` and `startTitle` hooks, two logs of different games get two histories, the same log loaded again gets its own back.

    python3 tests/test_history_adventures.py
"""
import json, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import language as LG
LG.select_language('fr')
from dq456_pc.core import history as HI


class FakeSensor:
    def __init__(self): self.active = True; self.events = []; self.uid = 7; self.output = []
    def drain(self): s, self.output = self.output, []; return s
    def drain_events(self): s, self.events = self.events, []; return s
    def unique_id(self): return self.uid


class FakeEngine:
    def __init__(self, part=HI.PART_TOWN):
        self.sensor = FakeSensor(); self.core = types.SimpleNamespace(written_saves=[])
        self.state = types.SimpleNamespace(part=part, game_map='x'); self.ui = types.SimpleNamespace(msg={'feed': False}); self.msg_visible = True


def say(h, m, text, t):
    m.sensor.output.append({'text': text, 'kind': 'g', 'val': None, 'cat': HI.CATEGORY_TERRAIN, 'map': 'x', 't': t}); h.do_update(m)


class TestAdventures(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='adv_'); self.addCleanup(shutil.rmtree, self.d, True); self.fav = os.path.join(self.d, 'history_favorites.json')

    def new(self): return HI.History(self.fav, lambda: 1000.0)

    def texts(self, h): return [e.text for e in h.dialogues]

    def test_new_game_then_save_then_load(self):
        h = self.new(); m = FakeEngine()
        say(h, m, 'Premier.', 10); a = h.adventure; self.assertIsNotNone(a)                               # a game began without a log: new adventure
        m.core.written_saves.append(2); m.sensor.uid = 33; h.do_update(m)                                # church: log 2
        m.sensor.events.append(('title',)); m.state.part = 0; h.do_update(m); self.assertIsNone(h.adventure); self.assertEqual(h.dialogues, [])
        h2 = self.new(); m2 = FakeEngine(); m2.sensor.uid = 33; m2.sensor.events.append(('load', 2)); h2.do_update(m2)     # new launch, "Continuer" on log 2
        self.assertEqual((h2.adventure, self.texts(h2)), (a, ['Premier.']))

    def test_two_logs_two_histories(self):
        h = self.new(); m = FakeEngine()
        m.sensor.uid = 1; m.sensor.events.append(('load', 1)); h.do_update(m); say(h, m, 'Partie A.', 10); a = h.adventure
        m.sensor.uid = 2; m.sensor.events.append(('load', 3)); h.do_update(m); self.assertNotEqual(h.adventure, a); self.assertEqual(h.dialogues, [])
        say(h, m, 'Partie B.', 10)
        m.sensor.uid = 1; m.sensor.events.append(('load', 1)); h.do_update(m); self.assertEqual((h.adventure, self.texts(h)), (a, ['Partie A.']))

    def test_saving_into_another_log_links_it(self):
        h = self.new(); m = FakeEngine(); m.sensor.uid = 5
        m.sensor.events.append(('load', 1)); h.do_update(m); say(h, m, 'Avant.', 10); a = h.adventure
        m.core.written_saves += [4, 9]; h.do_update(m)                                                     # auto-save into log 4 (data9.dat: only the number of the last log)
        self.assertEqual(sorted(h.index), ['1', '4'])
        m.sensor.events.append(('load', 4)); h.do_update(m); self.assertEqual((h.adventure, self.texts(h)), (a, ['Avant.']))

    def test_log_overwritten_by_another_game(self):
        h = self.new(); m = FakeEngine(); m.sensor.uid = 5; m.sensor.events.append(('load', 1)); h.do_update(m); say(h, m, 'Ancien.', 10)
        m.sensor.uid = 200; m.sensor.events.append(('load', 1)); h.do_update(m)                          # (saves imported from the phone: another game in log 1)
        self.assertEqual(h.dialogues, [])

    def test_index_unreadable(self):
        os.makedirs(os.path.join(self.d, HI.HISTORY_FOLDER)); p = os.path.join(self.d, HI.HISTORY_FOLDER, HI.INDEX_FILE)
        with open(p, 'w') as f: f.write('{not json')
        h = self.new(); self.assertEqual(h.index, {}); self.assertTrue(os.path.exists(p + '.corrupt'))

    def test_single_history_of_396_taken_over(self):
        with open(os.path.join(self.d, HI.LEGACY_RECENT), 'w', encoding='utf-8') as f:
            json.dump({'version': HI.RECENT_VERSION, 'dialogues': [{'k': 'd', 'id': None, 't': 5, 'name': None, 'text': 'Vieux.'}], 'battles': []}, f)
        h = self.new(); m = FakeEngine(); h.do_update(m)
        self.assertEqual(self.texts(h), ['Vieux.']); self.assertFalse(os.path.exists(os.path.join(self.d, HI.LEGACY_RECENT)))

    def test_favorites_per_adventure(self):
        with open(self.fav, 'w', encoding='utf-8') as f:                                                  # common favorites
            json.dump({'version': HI.VERSION, 'next': 2, 'favorites': [{'k': 'd', 'id': 1, 't': 5, 'name': None, 'text': 'Ancien favori.'}]}, f)
        h = self.new(); m = FakeEngine(); m.sensor.uid = 1; m.sensor.events.append(('load', 1)); h.do_update(m); a = h.adventure
        self.assertEqual([f.text for f in h.favorites], ['Ancien favori.']); self.assertFalse(os.path.exists(self.fav))      # taken over by the first adventure
        say(h, m, 'De A.', 10); h.toggle_favorite(h.dialogues[-1])
        m.sensor.uid = 2; m.sensor.events.append(('load', 2)); h.do_update(m)
        self.assertEqual(h.favorites, []); say(h, m, 'De B.', 10); h.toggle_favorite(h.dialogues[-1])                  # another adventure: its own favorites
        m.sensor.uid = 1; m.sensor.events.append(('load', 1)); h.do_update(m); self.assertEqual((h.adventure, [f.text for f in h.favorites]), (a, ['Ancien favori.', 'De A.']))

    def test_unstarred_favorite_removed_when_the_adventure_changes(self):
        h = self.new(); m = FakeEngine(); say(h, m, 'Un.', 10); h.toggle_favorite(h.dialogues[0]); h.toggle_favorite(h.dialogues[0]); a = h.adventure
        h.new_adventure(); h.set_adventure(a); self.assertEqual(h.favorites, [])                         # (marked, then the adventure was left: applied)

    def test_savestate_switches(self):
        h = self.new(); m = FakeEngine(); say(h, m, 'Un.', 10); a = h.adventure
        h.new_adventure(); say(h, m, 'Deux.', 10)
        h.set_adventure(a); self.assertEqual(self.texts(h), ['Un.'])                                      # (what Game._apply_savestate does with the state's adventure)


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'real engine: DQ_APK and DQ_SAVES')
class RealEngine(unittest.TestCase):
    def test_hooks_and_logs(self):
        from dq456_pc.core import engine as ENGINE
        d = tempfile.mkdtemp(prefix='adv_mo_'); self.addCleanup(shutil.rmtree, d, True)
        eng = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], os.path.join(d, 'sv')); h = HI.History(os.path.join(d, 'fav.json'))
        for _ in range(3): eng.step(0, 0); h.do_update(eng)
        uids = {}
        for slot in (1, 2, 3, 4):
            try: ok = eng.load_save(slot)
            except Exception: ok = False
            if not ok: continue
            eng.step(0, 0); h.do_update(eng)
            uids[slot] = (eng.sensor.unique_id(), h.adventure)
            self.assertEqual(h.index[str(slot)], {'id': h.adventure, 'uid': uids[slot][0]})
        if len(uids) < 2: self.skipTest('fewer than two readable adventure logs')
        slot = sorted(uids)[0]; eng.load_save(slot); eng.step(0, 0); h.do_update(eng); self.assertEqual(h.adventure, uids[slot][1])     # the same log again: its history


if __name__ == '__main__':
    unittest.main()
