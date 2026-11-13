"""The places a window's code puts its nodes (the ▲ of the field's character list "teleported" onto the 2nd character; in "Miscellaneous", "Formation"
was higher than the other labels). A code of the game (Window.code, kind 'func') moves a node for some of its values and says nothing of it for the others: for those, the node is at its
prefab place again (the game's code sets it each time; the exporter only kept what differs from the prefab). The port left it where the last value had put it:
  - Make_LeftCharaList (type 4), code 4: the ▲ (node 1958) goes down above a short last page (values 2 to 5) and back to the top for a full page (value 1, nothing recorded);
  - Make_NameButton (type 8), codes 0 to 5: a row's label (1597, 1664, 1731...) is raised by 9 units for value 2 (a menu of one-line entries in another layout) and back for value 1.

    python3 tests/test_menu_code_places.py            (DQ_UI_CACHE=<interface cache> for the part on the real layout)"""
import os, sys, types, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM


def window_with_code(values):
    """Synthetic window: node 10 (a text) moved by code 0 for the values given ({value: z or None for "nothing recorded"})."""
    t = {'name': 'Make_Test()', 'err': None, 'nodes': [{'id': 1, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True, 'mats': []},
         {'id': 10, 'par': 1, 'pos': [5.0, 4.0, -50.0], 'act': True, 'mats': [], 'text': {'font': 'font', 'characterSize': 9.945, 'text': None, 'anchor': 4, 'alignment': 1, 'lineSpacing': 0.8}}],
         'parts': [{'node': 1, 'ib': [{'k': 'text', 'go': 10, 'variant': 0}]}], 'params': [{'id': 0, 'no': 0, 'parts': 0, 'base': 0}],
         'codes': [{'id': 0, 'kind': 'func', 'parts': 0, 'fx': {str(v): {'d': ({'10': {'pos': [5.0, 4.0, z]}} if z is not None else {})} for v, z in values.items()}}], 'builds': []}
    return UM.Window(types.SimpleNamespace(types={'99': t}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0)), 99)


class Synthetic(unittest.TestCase):
    def test_back_to_the_prefab_place(self):
        w = window_with_code({1: None, 2: -40.0, 3: -30.0})
        w.code(0, 2); self.assertEqual(w.N[10]['pos'][2], -40.0)
        w.code(0, 3); self.assertEqual(w.N[10]['pos'][2], -30.0)
        w.code(0, 1); self.assertEqual(w.N[10]['pos'][2], -50.0)                      # (nothing recorded for 1: the prefab's place)
        w.code(0, 1); self.assertEqual(w.N[10]['pos'][2], -50.0)

    def test_untouched_before_any_move(self):
        w = window_with_code({1: None, 2: -40.0}); w.code(0, 1); self.assertEqual(w.N[10]['pos'], [5.0, 4.0, -50.0])


CACHE = TR.CACHE
@unittest.skipUnless(os.path.exists(os.path.join(CACHE, 'ui_layout.json')), 'no interface cache (DQ_UI_CACHE)')
class RealLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.ml = UM.PageLayout(os.path.join(CACHE, 'ui_layout.json'))

    def test_list_arrow_back_on_top(self):
        w = UM.Window(self.ml, 4); top = list(w.N[1958]['pos'])
        w.code(4, 3); self.assertLess(w.N[1958]['pos'][2], top[2])                      # (a short page: the ▲ goes down)
        w.code(4, 1); self.assertEqual(w.N[1958]['pos'], top)                         # (a full page: back on top)

    def test_name_button_label_back_in_place(self):
        w = UM.Window(self.ml, 8); place = list(w.N[1731]['pos'])
        w.code(2, 2); self.assertNotEqual(w.N[1731]['pos'], place)
        w.code(2, 1); self.assertEqual(w.N[1731]['pos'], place)                       # ("Alignement" no longer raised)


if __name__ == '__main__':
    unittest.main(verbosity=1)
