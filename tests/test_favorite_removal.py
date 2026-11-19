"""Unstarring a favorite removes it at once (it used to be only marked, removed when the history window was left).

The bug that made the change: a message starred then unstarred right away stayed among the favorites, even after "Clear all". Checks: unstar = out of the favorites and of the
file at once, the latest element keeping its place with an empty star; "Clear all" then takes it like any other; starred again = a new favorite, at the end; unstarred from
"Favorites only" = out of that list, the selection staying at its place; leaving the window changes nothing more.

    python3 tests/test_favorite_removal.py
"""
import json, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc import language as LG
LG.select_language('fr')
from dq456_pc.core import history as HI
from dq456_pc.menus import ui_history as UH


class TestImmediateRemoval(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(prefix='favrm_'); self.addCleanup(shutil.rmtree, d, True); self.legacy = os.path.join(d, 'history_favorites.json')
        self.h = self.new(); self.f = self.h.path
        self.a = self.h.add('A.', None, 1); self.b = self.h.add('B.', None, 5000)

    def new(self):
        h = HI.History(self.legacy, lambda: 1000.0); h.set_adventure('0123456789ab'); return h

    def ids_in_file(self):
        with open(self.f, encoding='utf-8') as f: return [x['id'] for x in json.load(f)['favorites']]

    def test_star_then_unstar_right_away(self):
        h = self.h
        self.assertTrue(h.toggle_favorite(self.a)); self.assertFalse(h.toggle_favorite(self.a))
        self.assertEqual((h.favorites, self.ids_in_file(), self.a.fav), ([], [], None)); self.assertEqual(h.entries('dialogues', True), [])
        self.assertEqual(h.entries('dialogues'), [self.a, self.b], 'the latest element keeps its place, with an empty star')
        self.assertEqual(h.clear('dialogues'), 2); self.assertEqual((h.dialogues, h.favorites), ([], []), '"Clear all" takes it like the others')
        self.assertEqual(self.new().favorites, [], 'nothing left in the file either')

    def test_star_again_is_a_new_favorite(self):
        h = self.h; h.toggle_favorite(self.a); h.toggle_favorite(self.b); h.toggle_favorite(self.a); h.toggle_favorite(self.a)
        self.assertEqual(([f.text for f in h.favorites], self.ids_in_file()), (['B.', 'A.'], [2, 3]))

    def test_unstar_from_the_favorites_list(self):
        h = self.h; h.toggle_favorite(self.a); h.toggle_favorite(self.b)
        copied = h.entries('dialogues', True)[0]; self.assertFalse(h.toggle_favorite(copied))
        self.assertEqual(([f.text for f in h.entries('dialogues', True)], self.ids_in_file(), self.a.fav), (['B.'], [2], None))

    def test_window_list_follows(self):
        h = self.h; h.toggle_favorite(self.a); h.toggle_favorite(self.b)
        w = types.SimpleNamespace(J=types.SimpleNamespace(history=h), tab=0, favorites_only=True, selected=0, pos=0.0)
        for name_str in ('reload', 'star', 'current_item'): setattr(w, name_str, types.MethodType(getattr(UH.HistoryView, name_str), w))
        w.reload(keep=True); w.selected = 0; self.assertEqual([e.text for e in w.elements], ['A.', 'B.'])
        self.assertFalse(w.star()); self.assertEqual(([e.text for e in w.elements], w.selected), (['B.'], 0), 'out of "Favorites only" at once')


if __name__ == '__main__':
    unittest.main()
