"""Unstarring a favorite only marks it; the removal is applied when the history window is left completely.

Checks: unstar then star again in the same opening = the same favorite (number, place); the mark survives a tab or filter change; leaving the window (Pause.back from the history page,
Pause.shutdown with the history in the stack, closing the game) removes it from the list and the file; an abrupt stop (no clean leave) keeps the favorite.

    python3 tests/test_favorite_removal.py
"""
import json, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq4_pc import language as LG
LG.select_language('fr')
from dq4_pc.core import history as HI
from dq4_pc.menus import pause as PA


class TestDeferredRemoval(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(prefix='favrm_'); self.addCleanup(shutil.rmtree, d, True); self.legacy = os.path.join(d, 'history_favorites.json')
        self.h = self.new(); self.f = self.h.path
        self.a = self.h.add('A.', None, 1); self.b = self.h.add('B.', None, 5000)
        self.h.toggle_favorite(self.a); self.h.toggle_favorite(self.b)

    def new(self):
        h = HI.History(self.legacy, lambda: 1000.0); h.set_adventure('0123456789ab'); return h

    def ids_in_file(self):
        with open(self.f, encoding='utf-8') as f: return [x['id'] for x in json.load(f)['favorites']]

    def test_unstar_then_star_again_keeps_the_same_favorite(self):
        h = self.h
        self.assertFalse(h.toggle_favorite(self.a)); self.assertFalse(h.is_favorite(self.a)); self.assertEqual(self.ids_in_file(), [1, 2])     # marked, still in the file
        self.assertTrue(h.toggle_favorite(self.a)); self.assertTrue(h.is_favorite(self.a)); self.assertEqual(self.a.fav, 1)
        h.apply_removals(); self.assertEqual(([f.fav for f in h.favorites], self.ids_in_file()), ([1, 2], [1, 2]))       # nothing to remove: same order, same numbers

    def test_marked_from_the_favorites_list(self):
        h = self.h; copy = h.entries('dialogues', True)[0]
        h.toggle_favorite(copy); self.assertEqual(len(h.entries('dialogues', True)), 2)                      # still listed in "Favorites only"
        h.apply_removals(); self.assertEqual((self.ids_in_file(), self.a.fav), ([2], None))

    def test_abrupt_stop_keeps_the_favorite(self):
        self.h.toggle_favorite(self.b); self.h.store(True)                                                  # (no apply_removals: the game was killed)
        self.h.removing = set()                                                                          # (the game is killed: nothing more happens to this History)
        self.assertEqual([f.fav for f in self.new().favorites], [1, 2])

    def test_leaving_the_window_from_the_pause_menu(self):
        for stack, action in ((['root', 'history'], 'back'), (['history'], 'back'), (['root', 'history'], 'shutdown')):
            h = self.h; h.toggle_favorite(self.a)
            left = []
            p = types.SimpleNamespace(stack=list(stack), screen_page=stack[-1], opened=True, mini_tex=None, hist=types.SimpleNamespace(leave=lambda: (left.append(1), h.apply_removals())),
                                      J=types.SimpleNamespace(reg=types.SimpleNamespace(store=lambda: None), pause_game=lambda on: None))
            p.shutdown = lambda p=p: PA.Pause.shutdown(p)
            getattr(PA.Pause, action)(p)
            self.assertTrue(left, (stack, action)); self.assertIsNone(self.a.fav, (stack, action)); self.assertEqual(self.ids_in_file(), [2])
            h.toggle_favorite(self.a)                                                                        # (starred again for the next case: new number)

    def test_other_pages_do_not_apply(self):
        self.h.toggle_favorite(self.a); left = []
        p = types.SimpleNamespace(stack=['root', 'display'], screen_page='display', hist=types.SimpleNamespace(leave=lambda: left.append(1)))
        PA.Pause.back(p); self.assertEqual(left, []); self.assertEqual(self.a.fav, 1)


if __name__ == '__main__':
    unittest.main()
