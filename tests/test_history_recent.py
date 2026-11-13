"""Latest dialogues and battles kept from one session to the next: `History` writes them to `history_recent.json` (next to the favorites file) and reads them back at launch.

Checks: write and re-read in the same order with their stars; 100 per category (the oldest drop out, a favorite never: it is a copy); a star whose favorite no longer exists is dropped;
unreadable file set aside (.corrupt) and empty history; invalid elements ignored; grouped writes; duplicate filter only inside one session; dialogues stored by key when the game
files give the text back exactly (no text in the file), text requested again from the engine at the next launch.

    python3 tests/test_history_recent.py
"""
import json, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc import language as LG
LG.select_language('fr')
from dq4_pc.core import history as HI


ADVENTURE = '0123456789ab'          # (one history per adventure; the history of an adventure is what kept)


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class FakeSensor:
    """`files` = {message number: text of the game files}."""
    def __init__(self, files): self.active = True; self.files = files; self.output = []
    def drain(self): s, self.output = self.output, []; return s
    def model(self, mid): return self.files.get(mid)


def fake_engine(cap):
    return types.SimpleNamespace(sensor=cap, state=types.SimpleNamespace(part=HI.PART_TOWN, game_map='x'), ui=types.SimpleNamespace(msg={'feed': False}), msg_visible=True)


def battle(t, gold=3):
    return {'t': t, 'outcome': 'victory', 'gold': gold, 'xp': 4, 'enemies': [{'name': 'Gluant', 'total': 1, 'defeated': 1}]}


class TestRecent(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='recent_'); self.addCleanup(shutil.rmtree, self.d, True)
        self.fav = os.path.join(self.d, 'history_favorites.json'); self.recent = os.path.join(self.d, HI.HISTORY_FOLDER, ADVENTURE + '.json')

    def new(self, clock=None):
        h = HI.History(self.fav, clock or Clock()); h.set_adventure(ADVENTURE); return h

    def test_written_and_read_back_in_order_with_stars(self):
        h = self.new(); a = h.add('Premier.', 'Alena', 100); h.add('Second.', None, 5000); c = h.add_battle(battle(900))
        h.toggle_favorite(a); h.toggle_favorite(c); h.store(True)
        h2 = self.new()
        self.assertEqual([(e.name_str, e.text, e.fav) for e in h2.dialogues], [('Alena', 'Premier.', 1), (None, 'Second.', None)])
        self.assertEqual([(e.t, e.gold, e.fav) for e in h2.battles], [(900, 3, 2)])
        self.assertFalse(h2.toggle_favorite(h2.dialogues[0])); h2.apply_removals(); self.assertEqual([f.type for f in h2.favorites], ['c'])      # the star read back is the real favorite: removing it works

    def test_hundred_per_category_favorite_kept(self):
        h = self.new(); first = h.add('Garde-moi.', None, 1); h.toggle_favorite(first)
        for i in range(HI.MAX_DIALOGUES): h.add('m%d' % i, None, 1000 * (i + 1))
        for i in range(HI.MAX_BATTLES + 7): h.add_battle(battle(i, gold=i))
        self.assertEqual((len(h.dialogues), h.dialogues[0].text, len(h.battles), h.battles[0].gold), (100, 'm0', 100, 7))
        h.store(True); h2 = self.new()
        self.assertEqual((len(h2.dialogues), h2.dialogues[0].text, h2.dialogues[-1].text, len(h2.battles)), (100, 'm0', 'm99', 100))
        self.assertEqual([f.text for f in h2.entries('dialogues', True)], ['Garde-moi.'])                  # dropped out of the latest 100, still a favorite

    def test_star_without_favorite_dropped(self):
        h = self.new(); h.toggle_favorite(h.add('A.', None, 1)); h.store(True)
        os.remove(os.path.join(self.d, HI.HISTORY_FOLDER, ADVENTURE + '.favorites.json'))
        self.assertIsNone(self.new().dialogues[0].fav)

    def test_unreadable_file(self):
        for content in ('{not json', '[1]', json.dumps({'version': 99, 'dialogues': [], 'battles': []}), json.dumps({'version': HI.RECENT_VERSION, 'dialogues': 'x', 'battles': []})):
            os.makedirs(os.path.dirname(self.recent), exist_ok=True)
            with open(self.recent, 'w', encoding='utf-8') as f: f.write(content)
            h = self.new()
            self.assertEqual((h.dialogues, h.battles), ([], []), content); self.assertTrue(os.path.exists(self.recent + '.corrupt')); self.assertFalse(os.path.exists(self.recent))
            os.remove(self.recent + '.corrupt')
            self.assertIsNotNone(h.add('Neuf.', None, 1))                                                  # the game goes on normally

    def test_invalid_elements_ignored(self):
        good = {'k': 'd', 'id': None, 't': 5, 'name': None, 'text': 'Bon.'}
        bad = [{'k': 'd', 'id': None, 't': -1, 'text': 'a'}, {'k': 'c', 'id': None, 't': 1, 'enemies': [], 'outcome': 'nul'}, {'k': 'd', 'id': 'x', 't': 1, 'text': 'a'}, 'x', None,
               {'k': 'c', 'id': None, 't': 1, 'enemies': [], 'outcome': 'victory'}]                    # (a battle in the dialogues list: wrong list)
        os.makedirs(os.path.dirname(self.recent), exist_ok=True)
        with open(self.recent, 'w', encoding='utf-8') as f: json.dump({'version': HI.RECENT_VERSION, 'dialogues': bad + [good], 'battles': [good]}, f)
        h = self.new()
        self.assertEqual(([e.text for e in h.dialogues], h.battles), (['Bon.'], [])); self.assertFalse(os.path.exists(self.recent + '.corrupt'))

    def test_grouped_writes(self):
        clock = Clock(); h = self.new(clock)
        h.add('A.', None, 1); self.assertTrue(h.store())                                                  # first write
        h.add('B.', None, 5000); self.assertFalse(h.store()); self.assertEqual(len(self.new().dialogues), 1)        # grouped
        clock.t += HI.STORAGE_DELAY + 1; self.assertTrue(h.store()); self.assertEqual(len(self.new().dialogues), 2)
        self.assertFalse(os.path.exists(os.path.join(self.d, HI.HISTORY_FOLDER, ADVENTURE + '.favorites.json')))      # no favorite: the favorites file is not written

    def test_duplicate_filter_only_in_one_session(self):
        h = self.new(); h.add('Bonjour.', None, 100); self.assertIsNone(h.add('Bonjour.', None, 150)); h.store(True)
        h2 = self.new(); self.assertIsNotNone(h2.add('Bonjour.', None, 120))                             # new session, same game time (the save was loaded again): kept
        self.assertEqual([e.text for e in h2.dialogues], ['Bonjour.', 'Bonjour.'])

    def test_stored_by_key_and_text_requested_again(self):
        cap = FakeSensor({802199: 'Il était une fois.\n', 802200: 'Different text.'}); h = self.new(); h._cap = cap
        h.add('Il était une fois.', None, 10, mid=802199); h.add('Built by the program.', None, 20, mid=802200); h.store(True)
        with open(self.recent, encoding='utf-8') as f: saved = json.load(f)['dialogues']
        self.assertEqual([('text' in x, x.get('mid')) for x in saved], [(False, 802199), (True, None)])     # the first by key (no text), the second with its text
        cap.files[802199] = 'Il était une fois, corrigé.\n'                                                # the patch changed the text
        h2 = self.new(); self.assertEqual(h2.dialogues[0].text, '')                                      # (waiting for the engine)
        h2.do_update(fake_engine(cap)); self.assertEqual([e.text for e in h2.dialogues], ['Il était une fois, corrigé.', 'Built by the program.'])
        h2.toggle_favorite(h2.dialogues[0]); self.assertTrue(h2.favorites[0].linked)                      # a favorite made from it is stored by key too


if __name__ == '__main__':
    unittest.main()
