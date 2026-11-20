"""Test (no window or engine) of the history: dq456_pc/core/history.py (pure data, favorites, pages of a message, engine hook with a fake emulator) and ui_history.py (tabs, H key, star, scrolling).

    python3 tests/test_message_history.py

Checks: text cleaning (the "*:" of unnamed lines is kept), line breaking, duplicates, size limits, battle formatting, favorites (only these are kept: file written immediately,
re-read on opening, removal via the star, corrupted file / invalid entries / unknown version), pages of a message (marked when the player has read them), battle messages never filed under the dialogues,
finished battles received from the BattleSensor, `TextBuffer::cat` hook (name shown or not, battle), tabs ("Dialogue", "Battles": no more "Favoris" tab), "Favorites only" checkbox (keyboard, mouse, kept from one tab to the other,
favorites from previous sessions), H key as a cycle (Dialogues -> Combats -> closed), star with keyboard and mouse, scrolling; up / down message by message (scrolling by the minimum needed), PgUp / PgDn and L / R: 3 messages, nothing grayed out on the selected message.
Single box size (the game's dialogue box: 1, 2 or 3 lines, dialogue or battle; one extra page beyond 3 lines).
`fill(h)` puts about thirty varied elements into a History (screenshots).
"""
import inspect, json, os, shutil, struct, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
pyglet.options['shadow_window'] = False                     # (no display needed: nothing is drawn)
from dq456_pc import language as LG
LG.select_language('fr')          # (the expectations of this test are in French, whatever the language of the computer)
from dq456_pc.core import history as HI
from dq456_pc.persistence import settings as RG
from dq456_pc.menus import ui_history as UH


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


ADVENTURE = '0123456789ab'          # (one history per adventure; these tests play a single one)


def new(path=None, clock=None):
    h = HI.History(path, clock or Clock()); h.set_adventure(ADVENTURE); return h


def battle(t=500, outcome='victory', enemies=None, gold=21, xp=38, objects=None):
    d = {'t': t, 'outcome': outcome, 'gold': gold, 'xp': xp, 'enemies': enemies if enemies is not None else [{'name': 'Gluant', 'total': 3, 'defeated': 3}]}
    if objects is not None: d['objects'] = objects
    return d


class TestText(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(HI.clean('*: Bonjour, voyageur.\n'), '*: Bonjour, voyageur.')                      # the "*:" is the game's text: kept
        self.assertEqual(HI.clean('Texte @c1rouge@c0 et suite\r\n\n\n\nFin   \n'), 'Texte rouge et suite\n\nFin')
        self.assertEqual(HI.clean('A\x01BC\x7f'), 'ABC')
        self.assertEqual(HI.clean('Que faites-vous ?'), 'Que faites-vous ?')                         # the non-breaking space (French typography) is kept
        self.assertEqual(HI.clean('   \n  '), '')
        self.assertEqual(HI.clean(None), '')
        self.assertEqual(len(HI.clean('x' * 5000)), HI.MAX_TEXT)

    def test_patch_semicolon_removed(self):
        """the ";" in the patch's item names (break mark, always after a space) is not displayed in the history; the space before it remains."""
        self.assertEqual(HI.clean("Ragnar obtient l'herbe ;médicinale."), "Ragnar obtient l'herbe médicinale.")
        self.assertEqual(HI.clean('Un bâton de ;cyprès et une épée de ;cuivre !\n;Fin'), 'Un bâton de cyprès et une épée de cuivre !\nFin')
        self.assertEqual(HI.clean(';'), '')
        h = HI.History(None); h.add("Il trouve l'herbe ;médicinale.", 'Mar;chand', 10)
        e = h.dialogues[-1]; self.assertEqual((e.name_str, e.text), ('Marchand', "Il trouve l'herbe médicinale."))
        f = HI.Element.from_dict({'k': HI.TYPE_DIALOGUE, 'id': 1, 't': 5, 'name': None, 'text': "l'herbe ;médicinale"}, 1)
        self.assertEqual(f.text, "l'herbe médicinale")                                          # a favorite saved before the fix is reread without ";" (and is still recognized)

    def test_wrap(self):
        mes = len
        self.assertEqual(HI.wrap_text('un deux trois quatre', 9, mes), ['un deux', 'trois', 'quatre'])
        self.assertEqual(HI.wrap_text('ligne un\nligne deux', 80, mes), ['ligne un', 'ligne deux'])        # the text's line breaks are kept
        self.assertEqual(HI.wrap_text('a\n\nb', 80, mes), ['a', '', 'b'])
        self.assertEqual(HI.wrap_text('abcdefghij', 4, mes), ['abcd', 'efgh', 'ij'])                          # word wider than the line
        self.assertEqual(HI.wrap_text('', 10, mes), [''])
        self.assertEqual(HI.wrap_text('Que faites-vous ? Allez', 14, mes), ['Que', 'faites-vous ?', 'Allez'])      # never cut at the non-breaking space
        for t in ('Je suis sûr que vous avez tous entendu les rumeurs', 'a b c d e f g h'):
            for wid in (5, 12, 30):
                self.assertTrue(all(len(l) <= wid or ' ' not in l for l in HI.wrap_text(t, wid, mes)))


class TestDialogues(unittest.TestCase):
    def test_with_and_without_name(self):
        h = new()
        a = h.add('Repos, soldats.', 'Roi Bastien', 100); b = h.add('*: Bonjour, voyageur !', None, 400); c = h.add('Voici l\'histoire.', '   ', 800)
        self.assertEqual([(e.name_str, e.text) for e in h.dialogues], [('Roi Bastien', 'Repos, soldats.'), (None, '*: Bonjour, voyageur !'), (None, 'Voici l\'histoire.')])
        self.assertTrue(all(e.type == HI.TYPE_DIALOGUE and e.fav is None for e in (a, b, c)))
        self.assertEqual(len({a.n, b.n, c.n}), 3)                                                                 # distinct sequence numbers
        self.assertEqual(h.entries('dialogues'), h.dialogues); self.assertIsNot(h.entries('dialogues'), h.dialogues); self.assertEqual(h.entries('inconnu'), [])

    def test_empty_and_duplicates(self):
        h = new()
        self.assertIsNone(h.add('   ', 'X', 1)); self.assertIsNone(h.add(None, None, 1)); self.assertEqual(h.dialogues, [])
        self.assertIsNotNone(h.add('Bonjour.', 'Alena', 1000))
        self.assertIsNone(h.add('Bonjour.', 'Alena', 1000 + HI.TIME_MARGIN))                                      # the engine displayed the message again
        self.assertIsNotNone(h.add('Bonjour.', 'Alena', 1000 + HI.TIME_MARGIN + 1))                               # later: another dialogue
        self.assertIsNotNone(h.add('Bonjour.', 'Ragnar', 1000 + HI.TIME_MARGIN + 2))                              # another displayed name: another dialogue
        self.assertIsNotNone(h.add('Bonjour.', None, 1000 + HI.TIME_MARGIN + 3))
        self.assertEqual(len(h.dialogues), 4)

    def test_bounds(self):
        h = new()
        for i in range(HI.MAX_DIALOGUES + 25): h.add('Message %d' % i, None, i * 1000)
        self.assertEqual(len(h.dialogues), HI.MAX_DIALOGUES); self.assertEqual(h.dialogues[0].text, 'Message 25'); self.assertEqual(h.dialogues[-1].text, 'Message %d' % (HI.MAX_DIALOGUES + 24))
        self.assertEqual(len(h.add('x' * 9000, 'N' * 300, 10 ** 9).name_str), 60)


class TestBattles(unittest.TestCase):
    def test_lines(self):
        e = HI.battle_element(1, battle(enemies=[{'name': 'Gluant', 'total': 3, 'defeated': 3}, {'name': 'Chauve-souris', 'total': 1, 'defeated': 1}, {'name': 'Golem', 'total': 2, 'defeated': 1}]))
        self.assertEqual(HI.battle_lines(e), ['Gluant ×3', 'Chauve-souris', 'Golem ×2 : 1 vaincu, 1 resté', 'Or : 21\u00a0\u00a0\u00a0\u00a0\u00a0Expérience : 38'])
        e2 = HI.battle_element(2, battle(outcome='escape', enemies=[{'name': 'Golem', 'total': 4, 'defeated': 2}]))
        self.assertEqual(HI.battle_lines(e2), ['Golem ×4 : 2 vaincus, 2 restés'])                              # no gold or experience without victory
        self.assertEqual(HI.battle_lines(HI.battle_element(3, battle(enemies=[]))), [LG.tr('history.unknown_enemies'), 'Or : 21\u00a0\u00a0\u00a0\u00a0\u00a0Expérience : 38'])

    def test_battle_element(self):
        e = HI.battle_element(7, battle(t=1234)); self.assertEqual((e.n, e.type, e.t, e.outcome, e.gold, e.xp, e.fav), (7, HI.BATTLE_TYPE, 1234, 'victory', 21, 38, None))
        for bad in (None, {}, {'outcome': 'nul'}, battle(outcome='nul'), {'t': 1, 'outcome': 'victory', 'gold': 1, 'xp': 1}, battle(enemies=[{'name': 'X'}])): self.assertIsNone(HI.battle_element(1, bad))
        self.assertEqual(HI.battle_element(1, battle(gold=-5, xp=-1)).gold, 0)
        self.assertEqual(len(HI.battle_element(1, battle(enemies=[{'name': 'M%d' % i, 'total': 1, 'defeated': 1} for i in range(30)])).enemies), 12)

    def test_add_and_bounds(self):
        h = new()
        self.assertIsNone(h.add_battle({'outcome': 'x'})); self.assertEqual(h.battles, [])
        for i in range(HI.MAX_BATTLES + 5): h.add_battle(battle(t=i))
        self.assertEqual((len(h.battles), h.battles[0].t, h.battles[-1].t), (HI.MAX_BATTLES, 5, HI.MAX_BATTLES + 4))
        self.assertEqual(h.entries('battles')[-1].t, HI.MAX_BATTLES + 4); self.assertEqual(h.dialogues, [])


class TestFavorites(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='fav_'); self.legacy = os.path.join(self.folder, 'favoris.json')
        self.f = os.path.join(self.folder, HI.HISTORY_FOLDER, ADVENTURE + '.favorites.json'); os.makedirs(os.path.dirname(self.f))      # (the favorites of the adventure being played)

    def read(self):
        with open(self.f, encoding='utf-8') as fo: return json.load(fo)['favorites']

    def filled(self, h):
        d = h.add('Voici l\'histoire.', 'Alena', 100); h.add('Autre.', None, 5000); c = h.add_battle(battle(t=900)); return d, c

    def test_remove_and_clear(self):
        """an element deleted leaves the history with its favorite and its replay file (from either side); emptying keeps the favorites (solid stars) and drops the rest with its replays."""
        h = new(self.legacy); d, c = self.filled(h); other = h.add_battle(battle(t=950))
        rp = os.path.join(self.folder, HI.HISTORY_FOLDER, ADVENTURE); os.makedirs(rp, exist_ok=True)
        for e, name in ((c, 'c1.dqs'), (other, 'c2.dqs')): e.replay = ADVENTURE + '/' + name; open(os.path.join(rp, name), 'wb').close()
        h.toggle_favorite(c); fav = h.favorites[0]
        self.assertTrue(h.remove(fav)); self.assertNotIn(c, h.battles); self.assertEqual(h.favorites, []); self.assertFalse(os.path.exists(os.path.join(rp, 'c1.dqs')))      # (from "Favorites only")
        self.assertFalse(h.remove(fav))
        h.toggle_favorite(d); n = h.clear()
        self.assertEqual((n, h.dialogues, h.battles, [f.text for f in h.favorites]), (2, [d], [], ["Voici l'histoire."])); self.assertFalse(os.path.exists(os.path.join(rp, 'c2.dqs')))
        self.assertEqual(h.clear(), 0)
        self.assertTrue(h.remove(d)); self.assertEqual((h.dialogues, h.favorites), ([], []))
        d2, c2 = self.filled(h); self.assertEqual(h.clear('battles'), 1); self.assertEqual((len(h.dialogues), h.battles), (2, []))           # one kind only
        self.assertEqual(h.clear('dialogues'), 2); self.assertEqual(h.dialogues, [])
        self.assertEqual(self.read(), [])                                                                           # (written at once)

    def test_immediate_write_and_reread(self):
        h = new(self.legacy); d, c = self.filled(h)
        self.assertFalse(os.path.exists(self.f))                                                                  # nothing is written as long as there is no favorite
        self.assertTrue(h.toggle_favorite(d)); self.assertTrue(os.path.exists(self.f))                           # written right away
        self.assertEqual(d.fav, 1); self.assertEqual(len(h.favorites), 1); self.assertFalse(os.path.exists(self.f + '.tmp'))
        self.assertTrue(h.toggle_favorite(c)); self.assertEqual((c.fav, len(h.favorites), h.next_id), (2, 2, 3))
        h2 = new(self.legacy)                                                                                      # new session: the latest dialogues and battles and the favorites remain
        self.assertEqual(([(e.text, e.fav) for e in h2.dialogues], [e.fav for e in h2.battles], h2.next_id), ([("Voici l'histoire.", 1), ('Autre.', None)], [2], 3))
        self.assertEqual([(e.type, e.fav) for e in h2.favorites], [('d', 1), ('c', 2)])
        self.assertEqual((h2.favorites[0].name_str, h2.favorites[0].text), ('Alena', 'Voici l\'histoire.'))
        self.assertEqual((h2.favorites[1].enemies, h2.favorites[1].gold, h2.favorites[1].xp, h2.favorites[1].outcome), ([{'name': 'Gluant', 'total': 3, 'defeated': 3, 'fled': 0, 'vanished': 0}], 21, 38, 'victory'))
        self.assertEqual(h2.entries('favorites'), h2.favorites)
        self.assertEqual([f.fav for f in h2.entries('dialogues', True)], [f.fav for f in h2.favorites if f.type == 'd'])          # "Favorites only": the file's favorites, of the list's type (also those of a previous session)
        self.assertEqual([f.type for f in h2.entries('battles', True)], ['c'] * len([f for f in h2.favorites if f.type == 'c'])); self.assertEqual(h2.entries('dialogues'), h2.dialogues)
        every = h2.favorites + h2.dialogues + h2.battles; self.assertEqual(len({e.n for e in every}), len(every))

    def test_complete_battle_favorite_round_trip_and_old_format(self):
        """the monsters that fled, the vanished ones and the items are kept in the favorites file; a favorite (no fled, no vanished, no items) is reread as is."""
        h = new(self.legacy)
        c = h.add_battle(battle(t=900, enemies=[{'name': 'Gluant', 'total': 3, 'defeated': 1, 'fled': 1, 'vanished': 1}], objects=[{'name': 'herbe ;médicinale'}, {'name': 'pierre de vie'}]))
        self.assertEqual(c.objects, [{'name': 'herbe médicinale'}, {'name': 'pierre de vie'}]); h.toggle_favorite(c)
        self.assertEqual(self.read()[0]['objects'], c.objects); self.assertEqual(self.read()[0]['enemies'][0]['fled'], 1)
        f = new(self.legacy).favorites[0]; self.assertEqual((f.enemies, f.objects), (c.enemies, c.objects)); self.assertEqual(f.lookup_key(), c.lookup_key())
        self.assertIsNot(h.favorites[0].objects, c.objects)                                                            # (independent copy)
        old = {'version': HI.VERSION, 'next': 2, 'favorites': [{'k': 'c', 'id': 1, 't': 5, 'enemies': [{'name': 'Gluant', 'total': 3, 'defeated': 2}], 'gold': 4, 'xp': 5, 'outcome': 'victory'}]}
        with open(self.f, 'w', encoding='utf-8') as fo: json.dump(old, fo)
        a = new(self.legacy).favorites; self.assertEqual(len(a), 1); self.assertEqual((a[0].enemies, a[0].objects), ([{'name': 'Gluant', 'total': 3, 'defeated': 2, 'fled': 0, 'vanished': 0}], []))
        for bad in ({'objects': 'x'}, {'objects': [{'x': 1}]}, {'objects': [{'name': 3}]}, {'enemies': [{'name': 'G', 'total': 1, 'defeated': 0, 'fled': -1}]}):
            d = dict(old['favorites'][0]); d.update(bad); old['favorites'] = [d]
            with open(self.f, 'w', encoding='utf-8') as fo: json.dump(old, fo)
            self.assertEqual(new(self.legacy).favorites, [], bad)                                                   # (invalid favorite: ignored)

    def test_battle_key_accounts_for_detail(self):
        h = new(); a = h.add_battle(battle(enemies=[{'name': 'G', 'total': 2, 'defeated': 1, 'fled': 1, 'vanished': 0}])); b = h.add_battle(battle(enemies=[{'name': 'G', 'total': 2, 'defeated': 1, 'fled': 0, 'vanished': 1}]))
        c = h.add_battle(battle(enemies=[{'name': 'G', 'total': 2, 'defeated': 1, 'fled': 1, 'vanished': 0}], objects=[{'name': 'x'}]))
        self.assertEqual(len({a.lookup_key(), b.lookup_key(), c.lookup_key()}), 3)

    def test_independent_copy(self):
        h = new(self.legacy); d, _ = self.filled(h); h.toggle_favorite(d)
        self.assertIsNot(h.favorites[0], d); self.assertEqual(h.favorites[0].fav, 1)
        h.dialogues.clear()                                                                                       # the session list is emptied: the favorite remains
        self.assertEqual(len(h.favorites), 1)

    def test_removal(self):
        h = new(self.legacy); d, c = self.filled(h); h.toggle_favorite(d); h.toggle_favorite(c)
        self.assertFalse(h.toggle_favorite(d)); self.assertFalse(h.is_favorite(d))                             # second press on the star: removed at once
        self.assertIsNone(d.fav); self.assertEqual([e.fav for e in h.favorites], [2]); self.assertEqual(c.fav, 2)
        self.assertEqual([e['id'] for e in self.read()], [2])
        h2 = new(self.legacy); self.assertEqual([e.fav for e in h2.favorites], [2])

    def test_removal_from_the_favorites_tab(self):
        h = new(self.legacy); d, _ = self.filled(h); h.toggle_favorite(d)
        copied = h.favorites[0]; self.assertFalse(h.toggle_favorite(copied))                                        # "unstar" the favorite itself
        self.assertEqual(h.favorites, []); self.assertIsNone(d.fav)                                                  # the session's item loses its star too
        self.assertEqual(self.read(), [])

    def test_numbers_never_reused(self):
        h = new(self.legacy); d, c = self.filled(h); h.toggle_favorite(d); h.toggle_favorite(c); h.remove_favorite(2)
        h2 = new(self.legacy); self.assertEqual(h2.next_id, 3)
        e = h2.add('Neuf.', None, 10); h2.toggle_favorite(e); self.assertEqual(e.fav, 3)

    def test_without_file(self):
        h = new(None); d, _ = self.filled(h)
        self.assertTrue(h.toggle_favorite(d)); self.assertEqual(len(h.favorites), 1); self.assertFalse(h.toggle_favorite(None))      # no path: everything stays in memory, no error
        self.assertIsNone(h.error)

    def test_bounds(self):
        h = new(None)
        for i in range(HI.MAX_FAVORITES + 3): h.toggle_favorite(h.add('m%d' % i, None, i * 1000))
        self.assertEqual((len(h.favorites), h.favorites[0].text), (HI.MAX_FAVORITES, 'm3'))

    def test_corrupted_file(self):
        for content in ('{not json', '[1, 2]', json.dumps({'version': 1, 'parties': {}}), json.dumps({'version': HI.VERSION, 'favorites': 'x'}), ''):
            with open(self.f, 'w', encoding='utf-8') as fo: fo.write(content)
            h = new(self.legacy)
            self.assertEqual((h.favorites, h.next_id), ([], 1), content); self.assertTrue(os.path.exists(self.f + '.corrupt')); self.assertFalse(os.path.exists(self.f))
            os.remove(self.f + '.corrupt')

    def test_invalid_entries_ignored(self):
        good_entries = [{'k': 'd', 'id': 1, 't': 10, 'name': 'Alena', 'text': 'Bonjour.'}, {'k': 'c', 'id': 4, 't': 20, 'enemies': [{'name': 'Gluant', 'total': 2, 'defeated': 1}], 'gold': 3, 'xp': 4, 'outcome': 'escape'}]
        bad = [{'k': 'd', 'id': 2, 't': 10, 'text': ''}, {'k': 'd', 'id': 'x', 't': 10, 'text': 'a'}, {'k': 'd', 'id': 3, 't': -1, 'text': 'a'}, {'k': 'z', 'id': 5, 't': 1},
                   {'k': 'c', 'id': 6, 't': 1, 'enemies': [{'name': 'X', 'total': -1, 'defeated': 0}], 'outcome': 'victory'}, {'k': 'c', 'id': 7, 't': 1, 'enemies': [], 'outcome': 'nul'},
                   {'k': 'd', 'id': 1, 't': 99, 'text': 'doublon d\'identifiant'}, {'k': 'd', 'id': True, 't': 1, 'text': 'a'}, {'k': 'd', 'id': 8, 't': 1, 'name': 5, 'text': 'a'}, 'text', None, 12]
        with open(self.f, 'w', encoding='utf-8') as fo: json.dump({'version': HI.VERSION, 'next': 2, 'favorites': bad[:4] + good_entries[:1] + bad[4:] + good_entries[1:]}, fo)
        h = new(self.legacy)
        self.assertEqual([(e.type, e.fav) for e in h.favorites], [('d', 1), ('c', 4)])
        self.assertEqual((h.favorites[1].outcome, h.favorites[1].enemies), ('escape', [{'name': 'Gluant', 'total': 2, 'defeated': 1, 'fled': 0, 'vanished': 0}]))
        self.assertEqual(h.next_id, 5)                                                                            # never a number already taken
        self.assertFalse(os.path.exists(self.f + '.corrupt'))                                                    # the file is kept: only the invalid entries are ignored

    def test_grouped_writes(self):
        clock = Clock(); h = new(self.legacy, clock); d, _ = self.filled(h); h.toggle_favorite(d)
        h._dirty = True; self.assertFalse(h.store())                                                         # too early: grouped
        clock.t += HI.STORAGE_DELAY + 1; self.assertTrue(h.store()); self.assertFalse(h.store(True))        # (nothing left to write)
        h._dirty = True; self.assertTrue(h.store(True))                                                      # closing forces the write

    def test_write_error_without_stop(self):
        h = new(os.path.join(self.folder, 'fichier.json', 'sous', 'x.json')); open(os.path.join(self.folder, 'fichier.json'), 'w').close()      # a file instead of a folder
        d = h.add('Bonjour.', None, 1); self.assertTrue(h.toggle_favorite(d)); self.assertIsNotNone(h.error); self.assertEqual(len(h.favorites), 1)


class FakeEngine:
    """Minimal engine for History.do_update: sensor (output, active), state, ui.msg['feed'], msg_visible, battle_sensor."""
    def __init__(self, part=HI.PART_TOWN):
        self.output = []
        self.sensor = types.SimpleNamespace(active=True, drain=self._clear)
        self.state = types.SimpleNamespace(part=part, game_map='mak1f1'); self.ui = types.SimpleNamespace(msg={'feed': False}); self.msg_visible = True

    def _clear(self):
        r, self.output = self.output, []
        return r


def page(text, t=500, category=None, name_str=None):
    return {'text': text, 'kind': 'n' if name_str else 'g', 'val': name_str, 'cat': category or HI.CATEGORY_TERRAIN, 'map': 'mak1f1', 't': t}


class TestPagesMessage(unittest.TestCase):
    """The engine prepares all the pages of a message at once: the history must only note the next page once the previous one has been read (end-of-page cursor off) or the window closed."""

    def texts(self, h): return [e.text for e in h.dialogues]

    def test_names_and_no_name(self):
        h = new(); m = FakeEngine(); m.output += [page('Repos, soldats.', name_str='Roi Bastien', t=100), page('*: Bonjour.', t=900)]
        h.do_update(m); self.assertEqual([(e.name_str, e.text) for e in h.dialogues], [('Roi Bastien', 'Repos, soldats.'), (None, '*: Bonjour.')])

    def test_next_page_noted_after_read(self):
        h = new(); m = FakeEngine(); m.output += [page('Page 1.'), page('Page 2.')]
        h.do_update(m); self.assertEqual(self.texts(h), ['Page 1.'])                                                    # page 2 has not been read yet
        m.ui.msg['feed'] = True; h.do_update(m); self.assertEqual(self.texts(h), ['Page 1.'])                           # end of page 1: cursor on
        m.ui.msg['feed'] = False; h.do_update(m); self.assertEqual(self.texts(h), ['Page 1.', 'Page 2.'])               # the player turns the page

    def test_three_pages_one_by_one(self):
        h = new(); m = FakeEngine(); m.output += [page('A.'), page('B.'), page('C.')]
        h.do_update(m); self.assertEqual(self.texts(h), ['A.'])
        for expected in (['A.', 'B.'], ['A.', 'B.', 'C.']):
            m.ui.msg['feed'] = True; h.do_update(m); m.ui.msg['feed'] = False; h.do_update(m); self.assertEqual(self.texts(h), expected)

    def test_window_closing_releases_the_rest(self):
        h = new(); m = FakeEngine(); m.output += [page('A.'), page('B.')]
        h.do_update(m); h.do_update(m); self.assertEqual(self.texts(h), ['A.'])
        m.msg_visible = False; h.do_update(m); self.assertEqual(self.texts(h), ['A.', 'B.'])

    def test_not_yet_opened_window_does_not_release(self):
        h = new(); m = FakeEngine(); m.msg_visible = False                                                      # the window opens one frame after the text
        m.output += [page('A.'), page('B.')]; h.do_update(m); h.do_update(m); self.assertEqual(self.texts(h), ['A.'])
        m.msg_visible = True; h.do_update(m); h.do_update(m); self.assertEqual(self.texts(h), ['A.'])

    def test_never_opened_window_still_gets_released(self):
        h = new(); m = FakeEngine(); m.msg_visible = False; m.output += [page('A.'), page('B.')]; h.do_update(m)
        for _ in range(HI.WINDOW_WAIT + 2): h.do_update(m)
        self.assertEqual(self.texts(h), ['A.', 'B.'])

    def test_new_message_releases_remaining_pages_in_order(self):
        h = new(); m = FakeEngine(); m.output += [page('A.'), page('B.')]; h.do_update(m)
        m.output += [page('Autre.', t=900)]; h.do_update(m); self.assertEqual(self.texts(h), ['A.', 'B.', 'Autre.'])

    def test_battle_never_retained(self):
        h = new(); m = FakeEngine(HI.PART_BATTLE)
        m.output += [page('Le monstre attaque !', category=HI.CATEGORY_BATTLE), page('Ragnar subit 3 points.', category=HI.CATEGORY_BATTLE)]; h.do_update(m)
        self.assertEqual((h.dialogues, h.battles), ([], []))                                                       # neither in dialogues nor in battles (these come from the BattleSensor)

    def test_distinct_messages_same_frame_not_retained(self):
        h = new(); m = FakeEngine(); m.output += [page('A.'), page('B.', name_str='Alena')]; h.do_update(m)
        self.assertEqual(self.texts(h), ['A.', 'B.'])                                                              # different names: two messages, not two pages

    def test_outside_game_nothing_retained(self):
        h = new(); m = FakeEngine(part=0); m.output += [page('Titre.')]; h.do_update(m); self.assertEqual(h.dialogues, [])

    def test_without_sensor_or_battle(self):
        h = new(); h.do_update(types.SimpleNamespace()); self.assertIsNone(h.error)                                  # (viewer without a message engine: nothing breaks)

    def test_finished_battles_of_sensor(self):
        h = new(); m = FakeEngine(); batches = [[battle(t=1), battle(t=2, outcome='escape', enemies=[{'name': 'Golem', 'total': 1, 'defeated': 0}])], [], [{'outcome': 'invalide'}, battle(t=3)]]
        m.battle_sensor = types.SimpleNamespace(do_update=lambda eng: batches.pop(0))
        for _ in range(3): h.do_update(m)
        self.assertEqual([(c.t, c.outcome) for c in h.battles], [(1, 'victory'), (2, 'escape'), (3, 'victory')]); self.assertEqual(h.dialogues, [])

    def test_an_error_does_not_stop_the_game(self):
        h = new(); m = FakeEngine(); m.battle_sensor = types.SimpleNamespace(do_update=lambda eng: 1 / 0)
        h.do_update(m); h.do_update(m); self.assertIsNotNone(h.error)


class FakeCore:
    """Fake emulator for Sensor._cat: registers, C strings, memory and function names."""
    XREG = list(range(100, 131)); LIB_BASE = 0

    def __init__(self, strings, memory, names): self.strings, self.memory, self.names = strings, memory, names; self.regs = {}
    def read_cstr(self, a): return self.strings[a]
    def mem(self, a, n): return self.memory[a][:n]
    def where(self, a): return self.names.get(a, '?+0')


class TestSensor(unittest.TestCase):
    """The TextBuffer::cat hook: text, name the game displays (2nd argument), battle or field, game time."""

    def sensor(self, text, name_str, part=HI.PART_TOWN, stack=('Foo::bar',), clock=777):
        names, memory, fp = {0x1000: stack[0] + '+8'}, {0x9000 + 4: struct.pack('<2I', clock, 66)}, 0x2000
        for i, n in enumerate(stack[1:]):                                       # chain of frame pointers
            memory[fp] = struct.pack('<QQ', fp + 0x100, 0x1100 + i); names[0x1100 + i] = n + '+4'; fp += 0x100
        memory[fp] = struct.pack('<QQ', 0, 0)
        c = FakeCore({0x10: text.encode('utf-8'), 0x20: name_str.encode('utf-8')} if name_str is not None else {0x10: text.encode('utf-8')}, memory, names)
        regs = {c.XREG[1]: 0x10 if text is not None else 0, c.XREG[2]: 0x20 if name_str is not None else 0, c.XREG[30]: 0x1000, c.XREG[29]: 0x2000}
        cap = HI.Sensor.__new__(HI.Sensor); cap.active = True; cap.output = []; cap.c = c; cap.g_game = 0x9000
        cap.m = types.SimpleNamespace(state=types.SimpleNamespace(part=part, game_map='caf1'))
        uc = types.SimpleNamespace(reg_read=lambda r: regs[r]); cap._cat(uc, 0, 0, None)
        return cap.drain()

    def test_displayed_name(self):
        (r,) = self.sensor('Repos, soldats.', 'Roi Bastien')
        self.assertEqual((r['text'], r['kind'], r['val'], r['cat'], r['map'], r['t']), ('Repos, soldats.', 'n', 'Roi Bastien', 't', 'caf1', 777))

    def test_without_name(self):
        for name_str in (None, '', '  '):
            (r,) = self.sensor('*: Bonjour.', name_str); self.assertEqual((r['kind'], r['val'], r['cat']), ('g', None, 't'))

    def test_empty_ignored(self):
        self.assertEqual(self.sensor('   ', 'Alena'), [])

    def test_battle_by_part_or_stack(self):
        self.assertEqual(self.sensor('Le gluant attaque !', None, part=HI.PART_BATTLE)[0]['cat'], 'c')
        self.assertEqual(self.sensor('Texte.', None, stack=('Foo::bar', 'BattleRoot::exec', 'main'))[0]['cat'], 'c')          # battle message launched from a battle menu
        self.assertEqual(self.sensor('Texte.', None, stack=('Foo::bar', 'Scene::exec', 'main'))[0]['cat'], 't')

    def test_field(self):
        (r,) = self.sensor('Texte.', None, part=HI.PART_FIELD); self.assertEqual(r['map'], 'world')

    def test_end_to_end_in_history(self):
        h = new(); m = FakeEngine()
        m.output += self.sensor('Repos, soldats.', 'Roi Bastien') + self.sensor('Le gluant attaque !', None, part=HI.PART_BATTLE); h.do_update(m)
        self.assertEqual([(e.name_str, e.text) for e in h.dialogues], [('Roi Bastien', 'Repos, soldats.')])


class TestKey(unittest.TestCase):
    def test_no_history_key(self):
        """No more History key (the history is a line of the Esc menu): H belongs to no action, the gamepads neither."""
        reg = RG.Settings(None)
        self.assertNotIn('history', reg['keys']); self.assertIsNone(reg.action_of(pyglet.window.key.H)); self.assertNotIn('history', dict(RG.ACTIONS))


def fill(h):
    """About thirty varied items (dialogues with or without a displayed name, battles): screenshots. The dialogues are in h.dialogues, the battles in h.combats."""
    L = [(None, 'Voici l\'histoire des gardes du palais d\'un petit royaume appelé Bastione.'), (None, 'Parmi ces gardes se trouve un courageux soldat, répondant au nom de Ragnar McRyan.'),
         ('Roi Bastien', 'Repos, soldats.'), ('Roi Bastien', 'J\'imagine que vous savez ce dont je veux vous parler.'),
         ('Roi Bastien', 'Je suis sûr que vous avez tous entendu les rumeurs à propos des récentes disparitions d\'enfants.'),
         ('Roi Bastien', 'Gardes, découvrez ce qui se trame et revenez me faire un rapport. Allez, mes braves !'),
         (None, '*: Messire, je vous en supplie ! Ramenez-moi mon enfant sain et sauf !'), (None, '*: Ne vous épuisez pas, Ragnar. Si vous êtes blessé au combat, revenez vous reposer à l\'auberge.'),
         (None, 'Ragnar examine les étagères.\nIl ne semble y avoir aucun livre particulièrement intéressant.'), (None, 'Ragnar ouvre le coffre.\nIl y a une Potion à l\'intérieur !'),
         ('Aubergiste', 'Bienvenue ! Que puis-je pour vous ?'), ('Aubergiste', 'Merci, et à bientôt !'), ('Alena', 'Hé, attendez-moi ! Je viens avec vous !'),
         (None, '*: Cette grotte est dangereuse, vous savez. Des monstres rôdent dans les profondeurs.'), (None, 'Ragnar fouille la jarre.\nIl a trouvé 12 pièces d\'or !'),
         ('Prêtre', 'Que la Déesse veille sur vous, mon enfant. Souhaitez-vous sauvegarder votre aventure ?'), (None, 'Ragnar a trouvé une Herbe médicinale.'),
         (None, '*: On dit qu\'il y a un trésor au fond de la grotte, mais personne n\'en est jamais revenu.'), (None, '*: Bonjour, voyageur !'),
         ('Roi Bastien', 'Les enfants ont disparu en une seule nuit, sans qu\'un seul garde ait rien vu. Fouillez le village, interrogez chaque habitant et n\'oubliez pas la forêt.'),
         (None, 'Ragnar a trouvé une Potion.\nRagnar a trouvé une Herbe médicinale.\nRagnar a trouvé 25 pièces d\'or.')]
    t = 400
    for i, (name_str, text) in enumerate(L): t += 300 if i % 5 else 1800; h.add(text, name_str, t)
    for i, (entry, g, x, outcome) in enumerate([([('Gluant', 3, 3)], 21, 38, 'victory'), ([('Chauve-souris', 2, 2), ('Gluant', 1, 1)], 14, 25, 'victory'), ([('Golem', 2, 1)], 0, 0, 'escape'),
                                           ([('Glacyclone', 4, 4), ('Mage-fantôme', 1, 1)], 96, 210, 'victory'), ([('Dragon bleu', 1, 0)], 0, 0, 'defeat'),
                                           ([('Gluant', 3, 3), ('Chauve-souris', 2, 2), ('Golem', 1, 1), ('Mage-fantôme', 2, 2), ('Glacyclone', 4, 4), ('Dragon bleu', 1, 1)], 250, 480, 'victory')]):
        h.add_battle(battle(t=600 + 4000 * i, outcome=outcome, enemies=[{'name': n, 'total': a, 'defeated': b} for n, a, b in entry], gold=g, xp=x))
    for e in (h.dialogues[2], h.dialogues[10], h.battles[3]): h.toggle_favorite(e)


def make_view(n=20, hv=500.0, battles=0):
    h = new(None)
    for i in range(n): h.add('m%d' % i, 'Perso %d' % i if i % 2 else None, 200 + 5000 * i)
    for i in range(battles): h.add_battle(battle(t=100 + i))
    calls = []
    P = types.SimpleNamespace(mouse_mode=False, mouse_pos=None, back=lambda: calls.append('retour'), shutdown=lambda: calls.append('fermer'), _repeat=lambda *a: calls.append(('repeter',) + a))
    P.J = types.SimpleNamespace(history=h, reg=RG.Settings(None), height=720)
    v = UH.HistoryView(P); v.enter(); v.calls = calls; v.hv0 = hv; place(v)
    return v


def place(v, hv=None):
    """What draw_all() does at each frame, without font or GL: stacks the items of v (126-pixel boxes, 32-pixel tab for a dialogue with a name, drawing gaps at scale 1) and updates the scrolling geometry
    (content height, reference point, active item). To be called after each action that changes the list or the position."""
    if hv is not None: v.hv0 = hv
    ent = [(1, e.type == HI.TYPE_DIALOGUE and bool(e.name_str)) for e in v.elements]
    boxes, starts, ends, hc = UH.arrange(ent, 126.0, 32.0, UH.ELEMENT_SPACING, UH.PAGE_SPACING, UH.ENTRIES_MARGIN)
    v._geometry(starts, ends, hc, v.hv0, 28.0, 1.0)
    return boxes


def keystroke(v, *key_list):
    """Keys, with a frame drawn in between."""
    for t in key_list: v.key_press(t); place(v)


class TestBox(unittest.TestCase):
    """Size of the history boxes: the game's dialogue box (3 lines) for a dialogue, whether the text is 1, 2 or 3 lines long (beyond that: one more page); a battle grows with its text."""
    @staticmethod
    def mes(t): return 9.0 * len(t)                                            # width of a string (units): 9 per character

    def boxes_view(self, elements, topmost=900.0):
        """Boxes computed as draw_all() places them (no GL): simulated system font (P._label), scale 1, list window of `topmost` pixels. -> (view, box, boxes from the oldest at the top to the most recent at the bottom,
        each (item, box, number of boxes, top, frame top, tab top, text rows))."""
        v = make_view(0); v.elements = elements; v._layout = None
        v.P._label = lambda t, size_value: types.SimpleNamespace(content_width=self.mes(t) / 0.9)
        B = UH.Box(); bs = v._measure(None, B, 1.0, 1.0, 20.0, topmost)
        return v, B, [(i, p, num, h, hb, hn, r) for (i, p, num, h, hn, hb, r) in bs]

    @staticmethod
    def dialogue(n, text, name_str=None): return HI.Element(n, HI.TYPE_DIALOGUE, 0, name_str=name_str, text=text)

    def test_game_dimensions(self):
        B = UH.Box(); self.assertEqual((B.WIDTH, B.UP, B.LINES, B.STEP), (452.0, 126.0, 3, 28.0)); self.assertEqual((B.TAB_L, B.TAB_H), (246.0, 32.0))
        self.assertEqual([B.base(i) for i in range(3)], [B.BASE_1, B.BASE_1 + 28.0, B.BASE_1 + 56.0])
        self.assertLess(B.base(2), B.UP)                                         # the 3rd line fits in the frame
        self.assertGreater(B.text_width(), 400)

    def test_dimensions_read_from_page_layout(self):
        import test_dialogue_name as N
        B = UH.Box.from_ml(N.fake_ml()); self.assertEqual((B.WIDTH, B.UP, B.TAB_L, B.TAB_H, B.x0, B.z0, B.win), (452.0, 126.0, 246.0, 32.0, -223.0, -251.0, (0.0, 10.0, 86.0)))
        self.assertEqual((UH.Box.from_ml(None).WIDTH, UH.Box.from_ml(object()).UP), (452.0, 126.0))               # (layout missing or unusable: measured values)

    def test_dimensions_of_real_borders(self):
        import test_dialogue_name as N; from dq456_pc.menus import ui_menu as UM
        l, c = os.path.join(N.CACHE, 'ui_layout.json'), os.path.join(N.CACHE, 'ui_frameData.bin')
        if not (os.path.exists(l) and os.path.exists(c)): self.skipTest('cache d\'interface absent')
        B = UH.Box.from_ml(UM.PageLayout(l, c)); d = UH.Box()
        self.assertEqual((B.WIDTH, B.UP, B.TAB_L, B.TAB_H), (d.WIDTH, d.UP, d.TAB_L, d.TAB_H)); self.assertEqual(B.text_scale, UH.TEXT_SCALE)

    def test_game_box_scale(self):
        """Same scale as the game windows on screen: H / 800 x UI_ZOOM (window.py); reduced if the viewer's window is too narrow."""
        src = _paths.source('window.py')
        import re; zoom = float(re.search(r'^UI_ZOOM = ([0-9.]+)', src, re.M).group(1)); self.assertEqual(UH.BOX_SCALE, zoom)
        B = UH.Box(); self.assertAlmostEqual(B.scale_factor(720, 1280, 0.8), 720 / 800 * zoom); self.assertLess(B.scale_factor(720, 500, 0.8), 720 / 800 * zoom)

    def test_same_border_for_one_two_three_lines(self):
        els = [self.dialogue(1, 'Oui.'), self.dialogue(2, 'Une ligne.\nDeux lignes.'), self.dialogue(3, 'Une.\nDeux.\nTrois.'), self.dialogue(4, 'Bonjour !', 'Alena'),
               self.dialogue(5, 'Une.\nDeux.\nTrois.', 'Roi Bastien')]
        v, B, blocks = self.boxes_view(els)
        self.assertEqual(len(blocks), 5); self.assertEqual({b[4] for b in blocks}, {B.UP * 1.0})               # frame height: a single value
        self.assertEqual([len(b[6]) for b in blocks], [1, 2, 3, 1, 3])                                  # (the text itself keeps its lines)
        self.assertEqual([b[5] for b in blocks], [0.0, 0.0, 0.0, B.TAB_H, B.TAB_H])               # the name tab is added on top, only with a name

    def test_text_over_three_lines_one_more_page(self):
        long = self.dialogue(1, 'a\nb\nc\nd\ne\nf\ng', 'Alena'); v, B, blocks = self.boxes_view([long])
        self.assertEqual(len(blocks), 3); self.assertEqual({b[4] for b in blocks}, {B.UP * 1.0}); self.assertEqual([b[6] for b in blocks], [['a', 'b', 'c'], ['d', 'e', 'f'], ['g']])
        self.assertEqual([b[5] for b in blocks], [B.TAB_H, 0.0, 0.0])                                 # the name is only on the first page
        self.assertEqual({(b[0], b[2]) for b in blocks}, {(0, 3)})

    def test_dialogue_cut_to_box_width(self):
        B = UH.Box(); word = 'mot '; text = (word * 60).strip(); r = UH.rows_of(self.dialogue(1, text), self.mes, B.text_width())
        self.assertTrue(all(self.mes(l) <= B.text_width() for l in r)); self.assertEqual(' '.join(r), text)

    def battle(self, enemies, outcome='victory', objects=None):
        return HI.Element(1, HI.BATTLE_TYPE, 0, enemies=[dict(name=n, total=a, defeated=v, fled=f, vanished=d) for n, a, v, f, d in [(x + (0, 0))[:5] for x in enemies]], gold=21, xp=38, outcome=outcome, objects=objects)

    def test_battle_grows_with_its_text(self):
        """a battle is no longer cut into 3-line pages: its box has as many lines as its text (header included), at least 3, and the game's frame stretches accordingly."""
        B = UH.Box()
        for entry, lines in (([('Gluant', 3, 3)], 3), ([('Chauve-souris', 2, 2), ('Gluant', 1, 1)], 4), ([('Glacyclone', 4, 4), ('Mage-fantôme', 1, 1), ('Golem', 1, 1)], 5)):
            e = self.battle(entry); v, B, blocks = self.boxes_view([e]); self.assertEqual(len(blocks), 1, entry)                        # a single box
            self.assertEqual(len(blocks[0][6]), len(entry) + 1)                                                                     # one row per species + the gold and experience
            self.assertEqual(blocks[0][4], B.top_for(lines) * 1.0); self.assertEqual(UH.box_lines(blocks[0][6], True, True), lines)
        self.assertEqual(B.top_for(3), B.UP); self.assertEqual(B.top_for(1), B.UP); self.assertEqual(B.top_for(5), B.UP + 2 * B.STEP)

    def test_detailed_battle_row_per_species_then_gains_then_items(self):
        B = UH.Box(); e = self.battle([('Gluant', 3, 1, 1, 1), ('Golem', 1, 0, 0, 0), ('Dragon', 1, 1, 0, 0)], objects=[{'name': 'herbe médicinale'}, {'name': 'pierre de vie'}])
        self.assertEqual(UH.rows_of(e, lambda t: 6.0 * len(t), B.text_width()), ['Gluant ×3 : 1 vaincu, 1 enfui, 1 disparu', 'Golem : resté', 'Dragon', 'Or : 21\u00a0\u00a0\u00a0\u00a0\u00a0Expérience : 38',
                                                                       'Objets : herbe médicinale, pierre de vie'])

    def test_battle_defeat_or_escape_without_gain(self):
        B = UH.Box(); e = self.battle([('Golem', 2, 1)], 'escape'); self.assertEqual(UH.rows_of(e, self.mes, B.text_width()), ['Golem ×2 : 1 vaincu, 1 resté'])
        e = self.battle([('Golem', 2, 0, 1, 0)], 'defeat', objects=[{'name': 'x'}]); self.assertEqual(UH.rows_of(e, self.mes, B.text_width()), ['Golem ×2 : 1 enfui, 1 resté'])   # no gold, experience or items without victory

    def test_battle_too_long_continues_in_next_box(self):
        entry = [('Monstre numéro %d' % i, 3, 3) for i in range(20)]; e = self.battle(entry)
        v, B, blocks = self.boxes_view([e]); self.assertGreater(len(blocks), 1)
        pages = [b[6] for b in blocks]; self.assertEqual(len(pages[0]) + 1, UH.MAX_BATTLE_LINES); self.assertTrue(all(len(p) <= UH.MAX_BATTLE_LINES for p in pages[1:]))
        self.assertEqual(blocks[0][4], B.top_for(UH.MAX_BATTLE_LINES)); self.assertEqual(sum(len(p) for p in pages), 21)           # (20 species + the gold and experience)
        self.assertEqual(blocks[-1][4], B.top_for(UH.box_lines(pages[-1], False, True)))                                    # the last box has the height of its text, no more

    def test_dialogue_keeps_game_box(self):
        v, B, blocks = self.boxes_view([self.dialogue(1, 'Oui.'), self.battle([('Gluant', 3, 3), ('Golem', 2, 2), ('Dragon', 1, 1)]), self.dialogue(3, 'Une.\nDeux.\nTrois.')])
        self.assertEqual([b[4] for b in blocks], [B.UP, B.top_for(5), B.UP])

    def test_arrange_different_heights(self):
        boxes, starts, ends, hc = UH.arrange([(1, False), (2, True, [200.0, 130.0]), (1, False, [300.0])], 100.0, 30.0, 10.0, 5.0, 8.0)
        self.assertEqual([(b[0], b[1], b[3], b[4], b[5]) for b in boxes], [(0, 0, 8.0, 0.0, 100.0), (1, 0, 118.0, 30.0, 200.0), (1, 1, 353.0, 0.0, 130.0), (2, 0, 493.0, 0.0, 300.0)])
        self.assertEqual((starts, ends, hc), ([8.0, 118.0, 493.0], [108.0, 483.0, 793.0], 801.0))

    def test_stretch_border(self):
        """Nine-piece frame (corners of 12 units): only the vertices of the upper half move up; the original layout is not modified."""
        vtx = [[-223.0, -251.0], [-211.0, -251.0], [-211.0, -239.0], [-223.0, -239.0], [-211.0, -137.0], [-223.0, -137.0], [-211.0, -125.0], [-223.0, -125.0], [229.0, -125.0]]
        copied = [list(v) for v in vtx]; r = UH.stretch_border(vtx, 56.0); self.assertEqual(vtx, copied)
        self.assertEqual([v[1] for v in r], [-251.0, -251.0, -239.0, -239.0, -81.0, -81.0, -69.0, -69.0, -69.0]); self.assertEqual([v[0] for v in r], [v[0] for v in vtx])
        self.assertEqual(UH.stretch_border(vtx, 0.0), vtx); self.assertEqual(UH.stretch_border([], 5.0), [])

    def test_stretched_game_border(self):
        """With the real layout: the frame of a 5-line battle is 2 lines taller (56 units), its corners keep their size, a dialogue's frame is untouched."""
        import test_dialogue_name as N; from dq456_pc.menus import ui_menu as UM
        l, c = os.path.join(N.CACHE, 'ui_layout.json'), os.path.join(N.CACHE, 'ui_frameData.bin')
        if not (os.path.exists(l) and os.path.exists(c)): self.skipTest('cache d\'interface absent')
        ml = UM.PageLayout(l, c); v = make_view(0); v.J.ui_render = types.SimpleNamespace(ml=ml)
        f0 = v._box_window(False); f2 = v._box_window(False, 2); self.assertIsNot(f0, f2)
        h = lambda f: max(x[1] for x in f.N['frame']['vtx']) - min(x[1] for x in f.N['frame']['vtx'])
        self.assertEqual(h(f0), 126.0); self.assertEqual(h(f2), 126.0 + 2 * UH.Box.STEP)
        bottoms = lambda f: sorted(x[1] for x in f.N['frame']['vtx'] if x[1] < -200); self.assertEqual(bottoms(f0), bottoms(f2))        # the bottom does not move
        self.assertEqual(len(f0.N['frame']['vtx']), len(f2.N['frame']['vtx'])); self.assertIs(v._box_window(False, 2), f2)       # (kept)
        vt = ml.message['types'][0]['frame_mesh']['vtx']; self.assertEqual(max(x[1] for x in vt) - min(x[1] for x in vt), 126.0)                    # (the original layout was not modified)

    def test_battle_without_known_enemy(self):
        B = UH.Box(); e = self.battle([], 'defeat'); self.assertEqual(UH.rows_of(e, self.mes, B.text_width()), [LG.tr('history.unknown_enemies')])

    def test_a_single_column_the_whole_list(self):
        """The whole list is laid out at once, from the oldest (at the top) to the most recent (at the bottom), with no gap or overlap, WHATEVER the window height: no more pages, no more "last visible item"."""
        els = [self.dialogue(i, 'Texte %d.' % i, 'Alena' if i % 2 else None) for i in range(10)]
        for topmost in (200.0, 500.0, 5000.0):
            v, B, blocks = self.boxes_view(els, topmost=topmost)
            self.assertEqual(len(blocks), 10); self.assertEqual([b[0] for b in blocks], list(range(10)))             # the oldest on top
            ys = [b[3] for b in blocks]; self.assertEqual(ys, sorted(ys)); self.assertEqual(ys[0], UH.ENTRIES_MARGIN)
            for a, b in zip(blocks, blocks[1:]): self.assertAlmostEqual(b[3] - (a[3] + a[4] + a[5]), UH.ELEMENT_SPACING)           # same gap everywhere
        self.assertAlmostEqual(v.hc, blocks[-1][3] + blocks[-1][4] + blocks[-1][5] + UH.ENTRIES_MARGIN)                   # content height: margins included

    def test_position_does_not_change_layout(self):
        """No notch: the scroll position only moves the content, the boxes do not move relative to each other."""
        els = [self.dialogue(i, 'Texte %d.' % i, 'Alena' if i % 2 else None) for i in range(30)]
        v, B, before = self.boxes_view(els, topmost=500.0)
        for pos in (0.0, 1.0, 37.5, 1234.0, 1e9): v.pos = pos; after = v._measure(None, B, 1.0, 1.0, 20.0, 500.0); self.assertEqual(after, v._layout[1]); self.assertEqual([b[3] for b in after], [b[3] for b in before])

    def test_arrange_is_pure(self):
        b, d, f, h = UH.arrange([(1, False), (3, True), (1, True)], 100.0, 30.0, 10.0, 2.0, 5.0)
        self.assertEqual([(x[0], x[1], x[2], x[3], x[4], x[5]) for x in b], [(0, 0, 1, 5.0, 0.0, 100.0), (1, 0, 3, 115.0, 30.0, 100.0), (1, 1, 3, 247.0, 0.0, 100.0), (1, 2, 3, 349.0, 0.0, 100.0), (2, 0, 1, 459.0, 30.0, 100.0)])
        self.assertEqual((d, f, h), ([5.0, 115.0, 459.0], [105.0, 449.0, 589.0], 594.0))
        self.assertEqual(UH.arrange([], 100.0, 30.0, 10.0, 2.0, 5.0), ([], [], [], 0.0))

    GEO = dict(zip(('b', 'd', 'f', 'hc'), UH.arrange([(1, False)] * 5, 100.0, 30.0, 10.0, 2.0, 5.0)))          # 5 messages of 100: starts 5, 115, 225, 335, 445; ends 105, ..., 545; height 550

    def test_offset_to_see_minimum(self):
        """Message already fully visible: nothing moves. Cut at the top or bottom, or outside the window: the view scrolls only by what is missing (the message's edge reaches the window's edge). First and last: with the list margin."""
        g = self.GEO; d, f, hc, hv = g['d'], g['f'], g['hc'], 250.0                 # window of 250: at scroll offset 0, it shows 300 to 550 from the top of the content
        see = lambda scroll_offset, i: UH.offset_to_see(d, f, hc, hv, scroll_offset, i)
        self.assertEqual([UH.extent(d, f, hc, i) for i in (0, 1, 4)], [(0.0, 105.0), (115.0, 215.0), (445.0, 550.0)])      # (the first goes up to the top of the content, the last down to the bottom)
        self.assertEqual((see(0.0, 4), see(0.0, 3)), (0.0, 0.0))                      # fully visible: unchanged
        self.assertEqual(see(0.0, 2), 75.0)                                            # 225 to 325: cut at the top (the window starts at 300): must go up by exactly 75
        self.assertEqual((see(0.0, 1), see(0.0, 0)), (185.0, 300.0))                  # outside the window: its top edge at the top of the window; the first: up to the top of the content (margin included)
        self.assertEqual((see(300.0, 0), see(300.0, 1)), (300.0, 300.0))              # window at the top (0 to 250): the first two are already in it
        self.assertEqual((see(300.0, 2), see(300.0, 3), see(300.0, 4)), (225.0, 115.0, 0.0))      # cut or outside the window at the bottom: its bottom edge reaches the bottom of the window (the last: down to the bottom of the content)
        self.assertEqual((see(100.0, 4), see(100.0, 3), see(100.0, 2), see(100.0, 1)), (0.0, 100.0, 100.0, 185.0))

    def test_offset_to_see_bounds_and_large_message(self):
        g = self.GEO; d, f, hc = g['d'], g['f'], g['hc']
        for scroll_offset in (0.0, 40.0, 150.0, 300.0):
            for i in range(5):
                n = UH.offset_to_see(d, f, hc, 250.0, scroll_offset, i); self.assertTrue(0.0 <= n <= hc - 250.0, (scroll_offset, i, n))
                top = hc - n - 250.0; topmost, bottom = UH.extent(d, f, hc, i); self.assertTrue(topmost >= top - 0.5 and bottom <= top + 250.5, (scroll_offset, i))         # still fully visible
        self.assertEqual(UH.offset_to_see(d, f, hc, 90.0, 0.0, 2), hc - 90.0 - d[2])          # a message taller than the window (100 > 90): its start at the top of the window
        c = dict(zip(('b', 'd', 'f', 'hc'), UH.arrange([(1, False)] * 2, 100.0, 30.0, 10.0, 2.0, 5.0)))
        self.assertEqual([UH.offset_to_see(c['d'], c['f'], c['hc'], 250.0, 0.0, i) for i in (0, 1)], [0.0, 0.0])      # list shorter than the window: nothing to scroll

    def test_visible_elements(self):
        g = self.GEO; d, f, hc = g['d'], g['f'], g['hc']
        self.assertEqual(UH.visible_elements(d, f, hc, 250.0, 0.0, True), [3, 4]); self.assertEqual(UH.visible_elements(d, f, hc, 250.0, 0.0, False), [2, 3, 4])      # item 2 (225 to 325) is cut: only partly visible
        self.assertEqual(UH.visible_elements(d, f, hc, 250.0, 300.0, True), [0, 1]); self.assertEqual(UH.visible_elements(d, f, hc, 1000.0, 0.0, True), [0, 1, 2, 3, 4])
        self.assertEqual(UH.visible_elements([], [], 0.0, 250.0, 0.0, True), [])

    def test_page_without_text(self):
        self.assertEqual(UH.paginate([], False), [[]]); self.assertEqual(UH.paginate([], True), [[]]); self.assertEqual(UH.paginate(['a', 'b', 'c'], True), [['a', 'b'], ['c']]); self.assertEqual(UH.paginate(['a', 'b', 'c'], False), [['a', 'b', 'c']])


class TestView(unittest.TestCase):
    """Tabs, H key, star and scrolling (no drawing: the scrolling geometry is simulated by `place`, as draw_all() updates it at each frame)."""

    @staticmethod
    def geom(v):
        """(starts, ends) of the items of v as arrange() places them."""
        ent = [(1, e.type == HI.TYPE_DIALOGUE and bool(e.name_str)) for e in v.elements]
        return UH.arrange(ent, 126.0, 32.0, UH.ELEMENT_SPACING, UH.PAGE_SPACING, UH.ENTRIES_MARGIN)[1:3]

    def test_opening_at_bottom(self):
        v = make_view(); self.assertEqual((v.tab, v.pos, v.selected, len(v.elements)), (UH.O_DIALOGUES, 0.0, 19, 20))        # all the way down: the most recent visible, and active
        self.assertGreater(v.span(), 0); self.assertEqual(v.scroll_offset(), 0.0)

    @staticmethod
    def fully_visible(v, i):
        """Is message i entirely inside the list window?"""
        topmost, bottom = UH.extent(v.starts, v.ends, v.hc, i); top = v.hc - v.scroll_offset() - v.hv
        return topmost >= top - 0.5 and bottom <= top + v.hv + 0.5

    def test_arrows_message_by_message(self):
        """Up / down: the previous / next message, one at a time (never a line or a page); the view only scrolls if that message is not fully visible, by the minimum necessary (its edge reaches the window's edge)."""
        K = pyglet.window.key; v = make_view(); self.assertTrue(self.fully_visible(v, 19)); scrolled = 0
        for i in range(18, -1, -1):
            before, vis = v.scroll_offset(), self.fully_visible(v, i); keystroke(v, K.W)
            self.assertEqual(v.selected, i); self.assertTrue(self.fully_visible(v, i), i)                                  # the chosen message is always fully visible
            if vis: self.assertEqual(v.scroll_offset(), before, 'already fully visible: the view does not move (%d)' % i)
            else:
                scrolled += 1; topmost, bottom = UH.extent(v.starts, v.ends, v.hc, i); self.assertAlmostEqual(topmost, v.hc - v.scroll_offset() - v.hv, places=6)      # its top edge is exactly at the top of the window: not one pixel more
        self.assertGreater(scrolled, 0); self.assertLess(scrolled, 19)                                          # (the view scrolled only at times)
        keystroke(v, K.W); self.assertEqual(v.selected, 0)                                                              # stop at the top
        for i in range(1, 20):
            before, vis = v.scroll_offset(), self.fully_visible(v, i); keystroke(v, K.S)
            self.assertEqual(v.selected, i); self.assertTrue(self.fully_visible(v, i), i)
            if vis: self.assertEqual(v.scroll_offset(), before)
            else: topmost, bottom = UH.extent(v.starts, v.ends, v.hc, i); self.assertAlmostEqual(bottom, v.hc - v.scroll_offset(), places=6)           # its bottom edge is exactly at the bottom of the window
        self.assertEqual((v.pos, v.selected), (0.0, 19)); self.assertIn(('repeter', K.S, 'v', 1), v.calls)         # (repeat of the held key: Pause.do_update)
        keystroke(v, K.S); self.assertEqual((v.pos, v.selected), (0.0, 19))                                              # stop at the bottom

    def test_arrow_on_cut_message_shows_it_in_full(self):
        """A message cut by the top of the window: a single press on Up chooses it AND scrolls by exactly what is missing; a message cut by the bottom, likewise with Down."""
        K = pyglet.window.key; v = make_view(n=40, hv=500.0); v.selected = 30; v.pos = 700.0; place(v)
        seen = [i for i in range(40) if self.fully_visible(v, i)]; first, last = seen[0], seen[-1]
        self.assertGreater(first, 0); v.selected = first; before = v.scroll_offset()                                       # the message just above the first fully visible one is cut (or just outside the window)
        keystroke(v, K.W); self.assertEqual(v.selected, first - 1); self.assertTrue(self.fully_visible(v, first - 1)); self.assertGreater(v.scroll_offset(), before); self.assertLess(v.scroll_offset() - before, 126.0 + 32.0 + UH.ELEMENT_SPACING + 1)
        v.selected = last; place(v); before = v.scroll_offset(); keystroke(v, K.S)
        self.assertEqual(v.selected, last + 1); self.assertTrue(self.fully_visible(v, last + 1))

    def test_pages_start_end(self):
        K = pyglet.window.key; v = make_view(hv=500.0)
        self.assertEqual(v.selected, 19)
        keystroke(v, K.PAGEUP); self.assertEqual(v.selected, 16); self.assertTrue(self.fully_visible(v, 16))                    # 3 messages per press, not a window page
        keystroke(v, K.PAGEUP); self.assertEqual(v.selected, 13); self.assertTrue(self.fully_visible(v, 13))
        keystroke(v, K.PAGEDOWN); self.assertEqual(v.selected, 16); keystroke(v, K.PAGEDOWN, K.PAGEDOWN); self.assertEqual((v.selected, v.pos), (19, 0.0))      # (butee en bas)
        keystroke(v, K.HOME); keystroke(v, K.PAGEUP); self.assertEqual(v.selected, 0); keystroke(v, K.PAGEDOWN); self.assertEqual(v.selected, 3)       # (stop at the top, then 3 lower)
        self.assertTrue(self.fully_visible(v, 3))
        keystroke(v, K.HOME); self.assertEqual((v.pos, v.selected), (v.span(), 0)); keystroke(v, K.W); self.assertEqual((v.pos, v.selected), (v.span(), 0))      # stop at the top: the first message
        keystroke(v, K.END); self.assertEqual((v.pos, v.selected), (0.0, 19))

    def test_game_actions_for_pages(self):
        """The game's "Page precedente / suivante" keys (L / R: R and T by default, PAGE_UP / PAGE_DOWN) skip the same 3 messages."""
        K = pyglet.window.key; v = make_view(); v.key_press(getattr(K, RG.DEFAULT_KEYS['L'][0])); self.assertEqual(v.selected, 16); v.key_press(getattr(K, RG.DEFAULT_KEYS['R'][0])); self.assertEqual(v.selected, 19)

    def test_wheel(self):
        v = make_view(); step = 28.0 * UH.WHEEL_STEP
        v.wheel(1); self.assertEqual(v.pos, step)                                                              # wheel up: the oldest, a fine constant step
        v.wheel(1); self.assertEqual(v.pos, 2 * step); v.wheel(-1); v.wheel(-1); self.assertEqual(v.pos, 0.0)
        v.wheel(-1); self.assertEqual(v.pos, 0.0)                                                              # stop at the bottom
        v.scroll_by(10 ** 9); self.assertEqual(v.pos, v.span()); v.scroll_by(-10 ** 9); self.assertEqual(v.pos, 0.0)   # (never beyond the list)
        v.wheel(3.0); self.assertEqual(v.pos, 3 * step)                                                         # touchpad: proportional to the movement

    def test_scroll_bar(self):
        M = pyglet.window.mouse; v = make_view(); p = v.span(); step = 28.0
        v.bar = dict(x0=0, x1=10, y0=0, y1=500, ptop=480, pbot=20, th=40, thumb=(20, 60), n=v.hc, visible=v.hv, base=0)               # thumb at the bottom (position 0)
        v.click(5, 495, M.LEFT); self.assertEqual(v.pos, step)                                                    # up arrow: one line
        v.click(5, 10, M.LEFT); self.assertEqual(v.pos, 0.0)                                                     # down arrow
        v.bar['thumb'] = (400, 440); v.click(5, 470, M.LEFT); self.assertEqual(v.pos, v.page_px())          # track above the thumb: one page
        v.click(5, 100, M.LEFT); self.assertEqual(v.pos, 0.0)
        v.bar['thumb'] = (20, 60); v.click(5, 40, M.LEFT); self.assertEqual(v.dragging_bar, 20)                 # thumb grabbed: it moves with no notch
        v.drag_to(5, 500); self.assertAlmostEqual(v.pos, p, places=6)                                           # dragged all the way up: the oldest
        v.drag_to(5, 0); self.assertEqual(v.pos, 0.0)
        v.drag_to(5, 20 + 20 + 440 / 2.0 - 20 + 0); self.assertGreater(v.pos, 0.0); self.assertLess(v.pos, p)  # middle: intermediate position, proportional
        v.release(5, 0, M.LEFT); self.assertIsNone(v.dragging_bar)

    def test_sliding_in_the_list(self):
        """The content follows the pointer, pixel by pixel (no steps)."""
        v = make_view(); v.drag = [300, v.scroll_offset(), False]
        v.drag_to(5, 301); self.assertEqual(v.pos, 0.0)                                                         # below the tolerance: not a drag
        v.drag_to(5, 300 - 160); self.assertEqual(v.pos, 160.0)                                                 # the pointer goes down by 160: the content goes down by 160 (older ones come into view)
        v.drag_to(5, 300 - 161); self.assertEqual(v.pos, 161.0)                                                 # one more pixel: one more pixel (no steps)
        v.drag_to(5, 300 + 50); self.assertEqual(v.pos, 0.0)                                                    # the pointer goes back up beyond its starting point: stop at the bottom
        v.release(5, 0, 1); self.assertIsNone(v.drag)

    def test_chosen_message_always_visible_after_key(self):
        """After any key of the list, the chosen message (target of the Enter key) is fully visible (if the window can contain it)."""
        K = pyglet.window.key; v = make_view(n=40, hv=500.0)
        for t in (K.W, K.W, K.PAGEUP, K.S, K.PAGEUP, K.PAGEUP, K.W, K.PAGEDOWN, K.S, K.S, K.HOME, K.S, K.END, K.W):
            keystroke(v, t); self.assertTrue(self.fully_visible(v, v.selected), (t, v.selected, v.pos))
            self.assertTrue(0 <= v.selected < 40)

    def test_all_messages_on_the_keyboard(self):
        """Whatever the length of the list and the height of the window, presses on Up go through ALL the messages one by one (from the last to the first), then Down goes through them again (including a list shorter than the window: the view does not move)."""
        K = pyglet.window.key
        for n, hv in ((1, 500.0), (2, 500.0), (3, 500.0), (5, 500.0), (7, 500.0), (20, 500.0), (4, 1000.0), (8, 900.0), (3, 120.0), (40, 300.0), (6, 1300.0), (5, 90.0)):
            v = make_view(n=n, hv=hv); seen = [v.selected]
            for _ in range(n + 5): keystroke(v, K.W); seen.append(v.selected)
            self.assertEqual(seen[:n], list(range(n - 1, -1, -1)), (n, hv)); self.assertEqual(v.selected, 0)                  # one by one, without skipping a single one
            seen = [v.selected]
            for _ in range(n + 5): keystroke(v, K.S); seen.append(v.selected)
            self.assertEqual(seen[:n], list(range(n)), (n, hv)); self.assertEqual(v.selected, n - 1)
            if hv >= 160.0: self.assertEqual(v.pos, 0.0)                                                          # (window shorter than a message: the last one is shown from its start)
            if v.span() == 0: self.assertEqual(v.scroll_offset(), 0.0)

    def test_short_entries_glued_to_bottom(self):
        """List shorter than the window: nothing to scroll (the wheel does nothing), the drawing sticks it to the bottom of the window (hc < hv); Up / Down move the chosen message without moving the view."""
        K = pyglet.window.key; v = make_view(n=3, hv=900.0); self.assertLess(v.hc, v.hv); self.assertEqual(v.span(), 0.0)
        v.wheel(1); v.scroll_by(500); place(v); self.assertEqual((v.pos, v.selected), (0.0, 2))
        keystroke(v, K.W); self.assertEqual(v.selected, 1); keystroke(v, K.W, K.W, K.W); self.assertEqual(v.selected, 0)
        self.assertEqual((v.scroll_offset(), v.pos), (0.0, 0.0))                                                           # ... and the view has not moved

    def test_click_chooses_mouse_scroll_changes_nothing(self):
        M = pyglet.window.mouse; K = pyglet.window.key; v = make_view(n=40, hv=500.0); v.zones = [(0, 0, 10, 10, 5)]
        v.click(5, 5, M.LEFT); place(v); self.assertEqual(v.selected, 5)                                              # a click chooses the message
        v.release(5, 5, M.LEFT); v.wheel(1); place(v); self.assertEqual(v.selected, 5)                              # the wheel scrolls, the chosen message stays the same
        v.selected = 39; v.pos = 0.0; v.wheel(5); v.wheel(5); v.wheel(5); place(v); self.assertEqual(v.selected, 39); self.assertFalse(self.fully_visible(v, 39))      # ... even if it leaves the window
        keystroke(v, K.W); self.assertTrue(self.fully_visible(v, v.selected)); self.assertLess(v.selected, 39)                        # by keyboard: the nearest visible message replaces the message that left (the last of the window) ...
        last = v.selected; self.assertEqual(last, [i for i in range(40) if self.fully_visible(v, i) or v.selected == i][-1]); keystroke(v, K.W); self.assertEqual(v.selected, last - 1)      # ... without advancing one more rank; the next press advances

    def test_no_graying_on_chosen_message(self):
        """Exception to the menus' general rule: neither lightened nor grayed on hover or choice (mouse or keyboard), only the small arrow marks the chosen message. The box is drawn the same way whether chosen or not."""
        import inspect; from dq456_pc.menus import hud_mobile as HM
        self.assertNotIn('choisi', inspect.signature(UH.HistoryView._draw_box).parameters)
        drawings = []; v = make_view(); B = UH.Box(); orig = (pyglet.shapes.Rectangle, HM.border)
        class Fake:
            def __init__(self, *a, **k): drawings.append(('rectangle', a, k)); self.opacity = 255
            def draw(self): drawings.append('draw')
        pyglet.shapes.Rectangle = Fake; HM.border = lambda *a, **k: drawings.append('frame')
        try:
            v._draw_box(B, 10.0, 20.0, 1.0, 1.0, None, None, 20.0)
            self.assertEqual(drawings, ['frame'])                                                                 # the frame alone: no translucent white rectangle over it
            for mouse in (False, True): v.P.mouse_mode = mouse; drawings.clear(); v._draw_box(B, 10.0, 20.0, 1.0, 1.0, None, None, 20.0); self.assertEqual(drawings, ['frame'])
        finally: pyglet.shapes.Rectangle, HM.border = orig

    def test_go_to_centers_the_item(self):
        v = make_view(n=40, hv=500.0); d, f = self.geom(v); v.go_to(10); place(v)
        self.assertEqual(v.selected, 10); middle = v.hc - (d[10] + f[10]) / 2.0 - v.scroll_offset(); self.assertAlmostEqual(middle, v.hv / 2.0, places=6)    # in the middle of the window
        v.go_to(0); place(v); self.assertEqual((v.selected, v.pos), (0, v.span()))                                  # (bounded: never beyond the top of the list)
        v.go_to(39); place(v); self.assertEqual((v.selected, v.pos), (39, 0.0))

    def test_resizing_keeps_the_spot(self):
        v = make_view(n=40, hv=500.0); v.pos = 400.0; ent = [(1, False)] * 40
        b, d, f, hc = UH.arrange(ent, 252.0, 64.0, 24.0, 8.0, 12.0); v._geometry(d, f, hc, 1000.0, 56.0, 2.0)
        self.assertAlmostEqual(v.pos, 800.0)                                                                    # double scale: the position too (same place in the list)

    def test_tabs(self):
        K = pyglet.window.key; v = make_view(n=6, battles=3)
        self.assertEqual((len(v.elements), v.elements[0].type), (6, 'd'))
        self.assertEqual([n for n, _ in UH.TABS], ['interface.dialogue', 'history.battles'])                                   # no more "Favoris" tab: it is a checkbox
        v.key_press(K.RIGHT); self.assertEqual((v.tab, len(v.elements), v.elements[0].type, v.selected), (UH.O_BATTLES, 3, 'c', 2))
        v.key_press(K.RIGHT); self.assertEqual((v.tab, len(v.elements)), (UH.O_DIALOGUES, 6))                    # back to the first
        v.key_press(K.LEFT); self.assertEqual(v.tab, UH.O_BATTLES)
        v.key_press(K.D); v.key_press(K.A); self.assertEqual(v.tab, UH.O_BATTLES)                               # the movement keys (right, left) go through the messages only, never the tabs

    def test_h_key_does_nothing(self):
        """No more History key: H changes neither the tab nor closes the window."""
        K = pyglet.window.key; v = make_view(n=3, battles=2)
        self.assertTrue(v.key_press(K.H)); self.assertEqual(v.tab, UH.O_DIALOGUES); self.assertNotIn('fermer', v.calls)

    def test_closing(self):
        K = pyglet.window.key; v = make_view()
        v.key_press(K.ESCAPE); v.key_press(K.BACKSPACE); self.assertEqual(v.calls.count('retour'), 2)
        self.assertTrue(v.key_press(K.F5))                                                                        # every key is consumed: nothing reaches the game

    def test_empty_entries(self):
        v = make_view(n=0); K = pyglet.window.key
        for t in (K.W, K.S, K.PAGEUP, K.PAGEDOWN, K.HOME, K.END, K.RIGHT, K.LEFT, K.RETURN): v.key_press(t)
        v.wheel(1); v.scroll_by(-3); place(v)
        self.assertEqual((v.elements, v.selected, v.pos), ([], 0, 0.0)); self.assertFalse(v.star()); self.assertIsNone(v.current_item())
        v2 = make_view(); v2.J.history = None; v2.enter(); self.assertEqual(v2.elements, [])                       # no history at all (game launched without)
        self.assertFalse(v2.star())

    def test_star_with_keyboard(self):
        K = pyglet.window.key; v = make_view(n=4); h = v.J.history
        self.assertEqual(v.selected, 3); self.assertTrue(v.star() is True); self.assertEqual((v.elements[3].fav, len(h.favorites)), (1, 1))       # the active item at opening: the most recent
        v.key_press(K.RETURN); self.assertFalse(h.is_favorite(v.elements[3])); v.leave(); self.assertIsNone(v.elements[3].fav); self.assertEqual(h.favorites, [])      # Enter: toggles (removed when the window is left)
        v.go_to(2); place(v); v.key_press(K.RETURN)                                                                   # (an item chosen by a click or from the list: active until the next scroll)
        v.go_to(3); place(v); v.key_press(K.RETURN); self.assertEqual(sorted(e.fav for e in h.dialogues if e.fav), [2, 3])

    def test_trash_with_keyboard_and_mouse(self):
        """Suppr deletes the selected element; the trash of a row deletes its element; the selection stays near (the next older one)."""
        K = pyglet.window.key; M = pyglet.window.mouse; v = make_view(n=4); h = v.J.history
        v.key_press(K.DELETE); place(v); self.assertEqual([e.text for e in h.dialogues], ['m0', 'm1', 'm2']); self.assertEqual(v.selected, 2)
        v.trash_zones = [(100, 100, 120, 120, 0)]; v.click(110, 110, M.LEFT); place(v)
        self.assertEqual([e.text for e in h.dialogues], ['m1', 'm2']); self.assertEqual(v.selected, 0)
        h.toggle_favorite(v.elements[0]); self.assertFalse(v.delete(0)); self.assertEqual(len(h.dialogues), 2)                       # a favorite's trash is grayed, it deletes nothing

    def test_clear_three_choices(self):
        """"Clear all" offers three choices with no Yes / No: the dialogues, the battles, or both; the favorites stay. The open tab's choice is preselected."""
        M = pyglet.window.mouse; v = make_view(n=4, battles=2); h = v.J.history; v.P.popup = None
        h.toggle_favorite(h.dialogues[1]); v.clear_zone = (10, 10, 50, 30); v.click(20, 20, M.LEFT)
        pp = v.P.popup; self.assertEqual((pp['choice'], len(pp['buttons']), 'yes' in pp, len(h.dialogues), len(h.battles)), (UH.O_DIALOGUES, 3, False, 4, 2))      # nothing deleted before the choice
        self.assertEqual([c for c, _ in pp['buttons']], ['history.clear_dialogues', 'history.clear_battles', 'history.clear_all'])
        pp['buttons'][1][1](); self.assertEqual((len(h.dialogues), h.battles), (4, []))
        pp['buttons'][0][1](); self.assertEqual(([e.text for e in h.dialogues], len(h.favorites)), (['m1'], 1))

    def test_star_with_mouse(self):
        M = pyglet.window.mouse; v = make_view(n=4); h = v.J.history
        v.star_zones = [(100, 100, 120, 120, 1), (100, 200, 120, 220, 3)]
        v.click(110, 210, M.LEFT); self.assertEqual((v.selected, h.dialogues[3].fav, h.dialogues[1].fav), (3, 1, None))
        v.click(110, 110, M.LEFT); self.assertEqual((v.selected, h.dialogues[1].fav), (1, 2))
        v.click(110, 210, M.LEFT); self.assertFalse(h.is_favorite(h.dialogues[3])); v.leave(); self.assertIsNone(h.dialogues[3].fav); self.assertEqual(len(h.favorites), 1)
        self.assertTrue(v.P.mouse_mode)

    def test_tab_click_and_back(self):
        M = pyglet.window.mouse; v = make_view(n=3, battles=2)
        v.tab_zones = [(0, 0, 10, 10, 0), (20, 0, 30, 10, 1)]
        v.click(25, 5, M.LEFT); self.assertEqual((v.tab, len(v.elements)), (UH.O_BATTLES, 2))
        v.click(5, 5, M.LEFT); self.assertEqual(v.tab, UH.O_DIALOGUES)
        v.click(500, 500, M.RIGHT); self.assertEqual(v.calls[-1], 'retour')                                      # right click: back
        v.zone_ret = (60, 0, 70, 10); v.click(65, 5, M.LEFT); self.assertEqual(v.calls.count('retour'), 2)

    def test_favorites_only_filter(self):
        """"Favorites only" checkbox: keeps, in the open tab, only its favorites; an unstarred item leaves the filtered list at once (the session's item keeps an empty star); the checkbox stays checked when the tab changes."""
        K = pyglet.window.key; v = make_view(n=3, battles=2); h = v.J.history
        self.assertFalse(v.favorites_only)
        v.star(0); v.star(2); v.change_tab(UH.O_BATTLES); v.star(1); v.change_tab(UH.O_DIALOGUES)       # two dialogues and one battle as favorites
        self.assertEqual(len(v.elements), 3)                                                                      # (checkbox unchecked: the whole session)
        self.assertTrue(v.toggle_filter())
        self.assertEqual([(e.type, e.fav) for e in v.elements], [('d', 1), ('d', 2)]); self.assertEqual((v.selected, v.pos), (1, 0.0))      # the tab's favorites, in the order they were added
        v.change_tab(UH.O_BATTLES)                                                                            # the filter is kept from one tab to the other
        self.assertTrue(v.favorites_only); self.assertEqual([(e.type, e.fav) for e in v.elements], [('c', 3)])
        v.change_tab(UH.O_DIALOGUES); v.key_press(K.RETURN)                                                       # star removed: out of the filtered list at once
        self.assertEqual([e.fav for e in v.elements], [1]); self.assertEqual(v.selected, 0); self.assertEqual([f.fav for f in h.favorites], [1, 3])
        self.assertIsNone(h.dialogues[2].fav)                                                                     # (the session's item loses its star)
        v.go_to(0); v.key_press(K.RETURN); self.assertEqual((v.elements, v.selected), ([], 0)); self.assertEqual([f.type for f in h.favorites], ['c'])
        v.key_press(K.RETURN); self.assertFalse(v.star())                                                           # empty list: nothing to toggle
        self.assertFalse(v.toggle_filter()); self.assertEqual(len(v.elements), 3)                                # checkbox unchecked: the whole session again

    def test_filter_by_keyboard_mouse_and_map_key(self):
        K = pyglet.window.key; M = pyglet.window.mouse; v = make_view(n=4)
        v.star(1); v.key_press(K.F); self.assertTrue(v.favorites_only); self.assertEqual(len(v.elements), 1)       # F: checks
        v.key_press(K.F); self.assertFalse(v.favorites_only); self.assertEqual(len(v.elements), 4)                   # F: unchecks
        v.key_press(K.M); self.assertTrue(v.favorites_only)                                                           # the Map key (M) does the same
        v.filter_zone = (100, 100, 200, 130); v.click(150, 115, M.LEFT); self.assertFalse(v.favorites_only)         # click on the checkbox: unchecks
        v.click(150, 115, M.LEFT); self.assertTrue(v.favorites_only); self.assertEqual(len(v.elements), 1); self.assertTrue(v.P.mouse_mode)
        v.click(300, 115, M.LEFT); self.assertTrue(v.favorites_only)                                                # (next to the checkbox: nothing)
        self.assertTrue(v.key_press(K.F))                                                                             # (the key is consumed: nothing reaches the game)

    def test_filter_keeps_chosen_element_and_scrolls(self):
        K = pyglet.window.key; v = make_view(n=30, hv=500.0)
        for i in (3, 10, 11, 12, 20, 25, 26): v.star(i)
        v.go_to(11); place(v); v.key_press(K.F); place(v)
        self.assertEqual(len(v.elements), 7); self.assertEqual(v.current_item().text, 'm11')                         # the chosen item, if it is a favorite, stays chosen (the view recenters on it)
        keystroke(v, K.HOME); self.assertEqual((v.selected, v.pos), (0, v.span())); keystroke(v, K.END); self.assertEqual((v.selected, v.pos), (6, 0.0))
        v.scroll_by(10 ** 9); place(v); self.assertEqual(v.pos, v.span()); v.scroll_by(-10 ** 9); place(v); self.assertEqual((v.pos, v.selected), (0.0, 6))      # wheel and drag bounded to the filtered list (the chosen message does not change)
        keystroke(v, K.PAGEUP); self.assertEqual(v.selected, 3); self.assertTrue(self.fully_visible(v, 3))                  # (liste filtree a 7 : 6 - 3 = 3)
        before = v.current_item().text; v.key_press(K.F); place(v); self.assertEqual((len(v.elements), v.current_item().text), (30, before))                 # unchecked: the full list, the active item (a favorite) stays active
        v.go_to(7); place(v); v.key_press(K.F); place(v); self.assertEqual((v.selected, v.current_item().text), (6, 'm26'))      # the chosen item is not a favorite: the selection lands on the most recent of the filtered list

    def test_favorites_from_previous_sessions(self):
        """A favorite whose element has dropped out of the latest 100: only the "Favorites only" checkbox shows it, with its star."""
        d = tempfile.mkdtemp(prefix='fav_'); self.addCleanup(shutil.rmtree, d, True); f = os.path.join(d, 'fav.json'); h = new(f)
        h.add('Hier.', 'Alena', 100); h.add_battle(battle(t=50)); h.toggle_favorite(h.dialogues[0]); h.toggle_favorite(h.battles[0])
        for i in range(HI.MAX_DIALOGUES): h.add('Plus tard %d.' % i, None, 1000 + i * 1000)
        for i in range(HI.MAX_BATTLES): h.add_battle(battle(t=1000 + i, gold=i))
        h.store(True)
        P = types.SimpleNamespace(mouse_mode=False, mouse_pos=None, back=lambda: None, shutdown=lambda: None, _repeat=lambda *a: None)
        P.J = types.SimpleNamespace(history=new(f), reg=RG.Settings(None), height=720)                    # new session: reads the file
        v = UH.HistoryView(P); v.enter()
        self.assertEqual((len(v.elements), v.current_item().text, any(e.fav for e in v.elements)), (HI.MAX_DIALOGUES, 'Plus tard %d.' % (HI.MAX_DIALOGUES - 1), False))
        v.key_press(pyglet.window.key.F); self.assertEqual([(e.name_str, e.text, e.fav) for e in v.elements], [('Alena', 'Hier.', 1)])
        v.change_tab(UH.O_BATTLES); self.assertEqual([(e.type, e.fav) for e in v.elements], [('c', 2)])
        v.key_press(pyglet.window.key.RETURN); self.assertEqual(v.elements, [])                                                    # star removed: out of the list at once
        self.assertEqual([e.type for e in P.J.history.favorites], ['d'])

    def test_empty_with_the_filter(self):
        v = make_view(n=2); self.assertIn('Aucun dialogue', LG.tr(UH.EMPTY_MESSAGES['dialogues'])); v.toggle_filter()
        self.assertEqual(v.elements, []); self.assertIn(LG.tr('history.favorites_only'), LG.tr(UH.EMPTY_FAVORITES['dialogues'])); self.assertIn(LG.tr('history.favorites_only'), LG.tr(UH.EMPTY_FAVORITES['battles']))
        self.assertEqual(set(UH.EMPTY_FAVORITES), {c for _, c in UH.TABS}); self.assertEqual(set(UH.EMPTY_MESSAGES), {c for _, c in UH.TABS})

    def test_reload_on_each_opening(self):
        v = make_view(n=2); v.J.history.add('Nouveau.', None, 10 ** 6); v.enter()
        self.assertEqual((len(v.elements), v.selected, v.pos), (3, 2, 0.0)); v.enter(UH.O_BATTLES); self.assertEqual(v.tab, UH.O_BATTLES); v.enter(99); self.assertEqual(v.tab, UH.O_DIALOGUES)
        v.star(0); v.toggle_filter(); v.enter(); self.assertTrue(v.favorites_only); self.assertEqual(len(v.elements), 1)                         # "Favorites only" stays checked when the window is reopened

    def test_play_time_and_next_tabs(self):
        self.assertEqual(UH.game_time(60 * (3600 + 5 * 60 + 12)), '1:05:12'); self.assertEqual(UH.game_time(-5), '0:00:00')
        self.assertFalse(hasattr(UH, 'next_key'))
        self.assertEqual((UH.next_tab(1), UH.next_tab(0, -1)), (0, 1))


class TestFollowTheGame(unittest.TestCase):
    """the game no longer stops behind the history (no pause in any menu): what it writes there while the window is open is added to the list (`follow_game`, called at each frame by Pause.do_update)."""
    def test_nothing_new_nothing_changes(self):
        v = make_view(n=5); selected, els = v.selected, list(v.elements); self.assertFalse(v.follow_game()); self.assertEqual((v.selected, v.elements), (selected, els))

    def test_at_bottom_new_message_added_and_choice_follows_last(self):
        v = make_view(n=5); self.assertEqual(v.selected, 4)
        v.J.history.add('Neuf.', 'Alena', 10 ** 6); self.assertTrue(v.follow_game()); place(v)
        self.assertEqual((len(v.elements), v.selected, v.pos), (6, 5, 0.0)); self.assertEqual(v.elements[-1].text, 'Neuf.')
        self.assertFalse(v.follow_game())                                                                              # (then nothing more to do)

    def test_at_bottom_choice_elsewhere_does_not_jump(self):
        v = make_view(n=8); v.selected = 3; cur = v.current_item(); self.assertEqual(v.scroll_offset(), 0.0)
        for i in range(2): v.J.history.add('Neuf %d.' % i, None, 10 ** 6 + i * 5000)
        self.assertTrue(v.follow_game()); self.assertEqual(len(v.elements), 10); self.assertIs(v.current_item(), cur); self.assertEqual(v.selected, 3)    # the chosen message stays the same

    def test_reading_higher_up_list_stays_then_updates_at_bottom(self):
        v = make_view(n=20); v.pos = 400.0; place(v); self.assertGreater(v.scroll_offset(), 0.5); before = list(v.elements); selected = v.selected
        v.J.history.add('Neuf.', None, 10 ** 6)
        self.assertFalse(v.follow_game()); self.assertEqual((v.elements, v.selected), (before, selected))                       # the reading does not skip
        v.pos = 0.0; place(v); self.assertTrue(v.follow_game()); self.assertEqual(len(v.elements), 21)                  # back at the bottom: update

    def test_not_during_sliding(self):
        v = make_view(n=5); v.J.history.add('Neuf.', None, 10 ** 6)
        v.drag = [0.0, 0.0, True]; self.assertFalse(v.follow_game()); v.drag = None; v.dragging_bar = 1.0; self.assertFalse(v.follow_game())
        v.dragging_bar = None; self.assertTrue(v.follow_game())

    def test_battles_tab(self):
        v = make_view(n=3, battles=2); v.change_tab(UH.O_BATTLES); place(v); self.assertEqual(len(v.elements), 2)
        v.J.history.add('Neuf.', None, 10 ** 6); self.assertFalse(v.follow_game())                              # a dialogue does not change the battles tab
        v.J.history.add_battle(battle(t=500)); self.assertTrue(v.follow_game()); self.assertEqual((len(v.elements), v.selected), (3, 2))

    def test_full_entries_oldest_leaves_last_enters(self):
        v = make_view(n=5); h = v.J.history; h.dialogues.pop(0); h.add('Neuf.', None, 10 ** 6)                              # (same length: the history's limit)
        self.assertEqual(len(h.dialogues), len(v.elements)); self.assertTrue(v.follow_game()); self.assertEqual(v.elements[-1].text, 'Neuf.')

    def test_favorites_only_does_not_change_with_game(self):
        v = make_view(n=5); v.star(1); v.toggle_filter(); place(v); self.assertEqual(len(v.elements), 1)
        v.J.history.add('Neuf.', None, 10 ** 6); self.assertFalse(v.follow_game()); self.assertEqual(len(v.elements), 1)

    def test_without_history(self):
        v = make_view(n=2); v.J.history = None; self.assertFalse(v.follow_game())

    def test_pause_update_runs_every_frame_on_history_page(self):
        from dq456_pc.menus import pause as PA
        src = inspect.getsource(PA.Pause.do_update)
        self.assertIn("self.hist.follow_game()", src)                          # only when the history is accessible (otherwise the page closes)
        self.assertIn("if self.screen_page == 'history':", src)


class TestPersistence(unittest.TestCase):
    """Point 2: the favorites (history_favorites.json) AND the state of the "Favorites only" checkbox (setting history_favorites_only in settings.json) survive closing and a new launch. Temporary files only."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='persist_'); self.addCleanup(shutil.rmtree, self.d, True)
        self.fav = os.path.join(self.d, 'history_favorites.json'); self.rg = os.path.join(self.d, 'settings.json')

    def session(self):
        """A game "session": History (favorites file), Settings (settings.json) and the history window, as window.py creates them."""
        P = types.SimpleNamespace(mouse_mode=False, mouse_pos=None, back=lambda: None, shutdown=lambda: None, _repeat=lambda *a: None)
        P.J = types.SimpleNamespace(history=new(self.fav), reg=RG.Settings(self.rg), height=720)
        v = UH.HistoryView(P); v.enter(); v.hv0 = 500.0; place(v); return v

    @staticmethod
    def shutdown(v):
        """Closing the viewer (Window.on_close): settings and favorites written."""
        v.J.reg.store(); v.J.history.store(True)

    def test_key_and_default_value(self):
        self.assertIs(RG.DEFAULT['history_favorites_only'], False); self.assertIn('history_favorites_only', RG.SOUND_TEXT_BOOLEANS)           # (unchecked by default; an invalid value goes back to it)
        self.assertIs(RG.Settings(None)['history_favorites_only'], False)
        src = _paths.source('pause.py')
        self.assertNotIn('history_favorites_only', src)                                                         # no line in the Pause menu: the checkbox is in the window itself

    def test_state_stored_on_each_change(self):
        v = self.session(); self.assertFalse(v.favorites_only); self.assertFalse(os.path.exists(self.rg))
        v.key_press(pyglet.window.key.F)                                                                              # checked: written right away, without waiting for closing
        with open(self.rg, encoding='utf-8') as f: self.assertIs(json.load(f)['history_favorites_only'], True)
        v.toggle_filter()
        with open(self.rg, encoding='utf-8') as f: self.assertIs(json.load(f)['history_favorites_only'], False)

    def test_round_trip_settings(self):
        for state in (True, False):
            r = RG.Settings(self.rg); r['vignette'] = 0.8; r['history_favorites_only'] = state; r.store()
            r2 = RG.Settings(self.rg); self.assertIs(r2['history_favorites_only'], state); self.assertEqual(r2['vignette'], 0.8)             # (the other settings do not change)

    def test_invalid_or_absent_values(self):
        for raw_value in ('"oui"', '1', '0', 'null', '[true]', '{"a": 1}'):
            with open(self.rg, 'w', encoding='utf-8') as f: f.write('{"history_favorites_only": %s, "vignette": 0.5}' % raw_value)
            r = RG.Settings(self.rg); self.assertIs(r['history_favorites_only'], False, raw_value); self.assertEqual(r['vignette'], 0.5)
        with open(self.rg, 'w', encoding='utf-8') as f: f.write('{"vignette": 0.5}')                              # file from before this key: unchecked
        self.assertIs(RG.Settings(self.rg)['history_favorites_only'], False)
        with open(self.rg, 'w', encoding='utf-8') as f: f.write('not json')                                  # unreadable: default values, without error
        self.assertIs(RG.Settings(self.rg)['history_favorites_only'], False)

    def test_two_sessions_favorites_and_checkbox(self):
        """Session 1: a dialogue and a battle as favorites, checkbox checked, close. Session 2 (new objects, same files): the checkbox is checked when the window opens and the favorites are in the list, with their star."""
        v = self.session(); h = v.J.history
        h.add('Un dialogue.', 'Alena', 100); h.add('Un autre.', None, 900); h.add_battle(battle(t=50)); v.enter()
        v.star(0); v.change_tab(UH.O_BATTLES); v.star(0); v.change_tab(UH.O_DIALOGUES); v.key_press(pyglet.window.key.F); self.assertTrue(v.favorites_only)
        self.shutdown(v)
        v2 = self.session()                                                                                       # new launch
        self.assertTrue(v2.favorites_only); self.assertEqual([(e.name_str, e.text, e.fav is not None) for e in v2.elements], [('Alena', 'Un dialogue.', True)])
        v2.change_tab(UH.O_BATTLES); self.assertEqual([(e.type, e.outcome, e.fav is not None) for e in v2.elements], [('c', 'victory', True)])
        v2.key_press(pyglet.window.key.F); self.assertEqual([(e.type, e.fav is not None) for e in v2.elements], [('c', True)])                  # unchecked: the latest battles of the previous session
        v2.change_tab(UH.O_DIALOGUES); self.assertEqual([(e.text, e.fav is not None) for e in v2.elements], [('Un dialogue.', True), ('Un autre.', False)])
        self.shutdown(v2)
        v3 = self.session(); self.assertFalse(v3.favorites_only)                                                   # ... and the unchecked checkbox is kept too
        v3.key_press(pyglet.window.key.F); self.assertEqual(len(v3.elements), 1)                                       # the favorites are still there

    def test_favorites_survive_without_clean_close(self):
        """The favorites are written at the moment of the star: an abrupt close (without on_close) does not lose them."""
        v = self.session(); v.J.history.add('Garde-moi.', 'Roi', 10); v.enter(); v.star(0)
        h2 = new(self.fav); self.assertEqual([(e.name_str, e.text) for e in h2.entries('dialogues', True)], [('Roi', 'Garde-moi.')])

    def test_write_error_does_not_prevent_checking(self):
        v = self.session()
        def breaks(): raise OSError('disque plein')
        v.J.reg.store = breaks
        self.assertTrue(v.toggle_filter()); self.assertTrue(v.favorites_only)
        v.J.reg = None; self.assertFalse(v.toggle_filter())                                                       # (no settings at all: the checkbox works anyway)
        v.enter(); self.assertFalse(v.favorites_only)

    def test_window_rereads_state_on_opening(self):
        v = self.session(); v.J.reg['history_favorites_only'] = True; v.enter(); self.assertTrue(v.favorites_only)


class TestPause(unittest.TestCase):
    """The history in the Pause menu: root entry, opening by the key (direct page), H key cycle, back, line of the "Controls" page."""
    def game(self):
        from dq456_pc.menus import pause as PA
        h = new(None); h.add('Bonjour.', 'Alena', 200); h.add_battle(battle())
        self.pauses = []
        J = types.SimpleNamespace(reg=RG.Settings(None), history=h, width=1280, height=720, mouse=None, args=types.SimpleNamespace(cache='/inexistant'),
                                  pause_game=lambda yes: self.pauses.append(yes), sound=types.SimpleNamespace(active=True, listening=False))
        J.reg.store = lambda: None; J.set_fade = lambda v: None; J.set_battle_speed = lambda v: None; J.apply_text = lambda: None          # (the Display page holds the "Text scrolling" section)
        return J, PA.Pause(J)

    def test_h_does_nothing_camera_keys_change_tab(self):
        """No more History key: H does nothing in the history; the camera keys change its tab."""
        K = pyglet.window.key; J, p = self.game()
        p.open_history()
        self.assertTrue(p.opened); self.assertEqual((p.stack, p.hist.tab, self.pauses), (['root', 'history'], UH.O_DIALOGUES, [True]))
        self.assertTrue(p.key_press(K.H, 0)); self.assertTrue(p.opened); self.assertEqual(p.hist.tab, UH.O_DIALOGUES)
        p.key_press(K.RIGHT, 0); self.assertEqual((p.hist.tab, p.hist.elements[0].type), (UH.O_BATTLES, 'c'))

    def test_clear_question_over_the_history(self):
        """the choices of "Clear all" are answered on the history page itself: Backspace closes them, not the menu (Esc closes everything); the battles' tab preselects "Clear the battles";
        the movement keys go through the three choices (in a loop), Enter chooses."""
        K = pyglet.window.key; J, p = self.game(); p.open_menu('history'); p.hist.change_tab(UH.O_BATTLES)
        p.hist.ask_clear(); p.key_press(K.BACKSPACE, 0); self.assertTrue(p.opened); self.assertIsNone(p.popup)
        p.hist.ask_clear(); self.assertEqual(p.popup['choice'], 1)
        p._popup_key(None, 'down'); p._popup_key(None, 'down'); self.assertEqual(p.popup['choice'], 0); p._popup_key(None, 'up'); self.assertEqual(p.popup['choice'], 2)
        p.key_press(K.RETURN, 0); self.assertIsNone(p.popup); self.assertEqual((J.history.battles, J.history.dialogues), ([], []))

    def test_view_put_back_after_a_replay(self):
        """a battle replay closes the menu for a moment (the history is not left: no favorite removed) and opens it again exactly as it was: pages, lines, tab, element, scroll."""
        J, p = self.game(); left = []; p.hist.leave = lambda: left.append(1)
        p.open_menu(); p.selected['root'] = 1; next(x for x in p._entries() if x['l'] == 'menu.history')['ok'](); p.hist.change_tab(UH.O_BATTLES); p.hist.pos = 37.0
        view = p.view_state(); p.shutdown(leaving=False)
        self.assertFalse(p.opened); self.assertEqual(left, [])
        p.restore_view(view)
        self.assertEqual((p.opened, p.stack, p.selected.get('root'), p.hist.tab, p.hist.selected, p.hist.pos), (True, ['root', 'history'], 1, UH.O_BATTLES, 0, 37.0))
        p.shutdown(); self.assertEqual(left, [1])                                                              # (really left afterwards: the favorites rule applies as before)
        self.assertIsNone(p.view_state())

    def test_esc_and_other_keys(self):
        K = pyglet.window.key; J, p = self.game()
        p.open_menu('history'); p.key_press(K.ESCAPE, 0); self.assertFalse(p.opened)                                  # Esc: back = close (single page of the stack)
        p.open_menu('history'); p.key_press(K.B, 0); self.assertTrue(p.opened)                                        # (B is "Cancel" only if it is the configured key: here B is not assigned)

    def test_menu_entry(self):
        K = pyglet.window.key; J, p = self.game()
        p.open_menu(); e = next(x for x in p._entries() if x['l'] == 'menu.history')
        e['ok'](); self.assertEqual(p.screen_page, 'history'); self.assertEqual(len(p.hist.elements), 1)
        p.key_press(K.BACKSPACE, 0); self.assertEqual(p.screen_page, 'root'); self.assertTrue(p.opened)                  # back to the Pause menu, not to the game
        self.assertEqual(p._entries_history(), [])
        e['ok'](); p.key_press(K.H, 0); self.assertTrue(p.opened); self.assertEqual(p.screen_page, 'history')            # (H: no more History key)

    def test_commands_line(self):
        J, p = self.game(); p.open_menu('controls')
        self.assertFalse([x for x in p._entries() if x.get('act') == 'history'])          # (no more History key to choose)

    def test_neither_click_nor_wheel_breaks(self):
        M = pyglet.window.mouse; J, p = self.game(); p.open_menu('history')
        p.hovered(100, 100); p.click(100, 100, M.LEFT); p.drag_to(100, 120); p.release(100, 120, M.LEFT); p.wheel(1); p.output()
        p.click(100, 100, M.RIGHT); self.assertFalse(p.opened)                                                      # right click: back, as in the other pages


class TestEmptyMessage(unittest.TestCase):
    """the empty-list message (especially the long "no favorite dialogue" one) was drawn on a single line and overflowed the frame: it is cut at spaces."""
    wid = staticmethod(lambda t: 10.0 * len(t))                      # test font: 10 units per character

    def test_no_line_exceeds(self):
        for msg in list(UH.EMPTY_MESSAGES.values()) + list(UH.EMPTY_FAVORITES.values()):
            for limit in (200.0, 400.0, 800.0, 1600.0):
                ls = UH.wrap_words(msg, self.wid, limit)
                self.assertEqual(' '.join(ls).split(), msg.split())                                       # no word lost or changed
                for l in ls: self.assertLessEqual(self.wid(l), max(limit, max(self.wid(m) for m in msg.split())), (limit, l))

    def test_short_message_stays_on_one_line(self):
        self.assertEqual(UH.wrap_words(UH.EMPTY_MESSAGES['dialogues'], self.wid, 10000.0), [UH.EMPTY_MESSAGES['dialogues']])
        self.assertEqual(UH.wrap_words('', self.wid, 100.0), [''])

    def test_long_message_is_cut(self):
        ls = UH.wrap_words(LG.tr(UH.EMPTY_FAVORITES['dialogues']), self.wid, 600.0); self.assertGreater(len(ls), 1)

    def test_too_wide_word_stays_alone(self):
        self.assertEqual(UH.wrap_words('a ABCDEFGHIJ b', self.wid, 50.0), ['a', 'ABCDEFGHIJ', 'b'])

    def test_drawing_cuts_the_message(self):
        src = _paths.source('ui_history.py')
        self.assertIn('wrap_words(msg,', src)                                                              # the empty list goes through the wrapping (no longer a single line)


if __name__ == '__main__':
    unittest.main(verbosity=1)
