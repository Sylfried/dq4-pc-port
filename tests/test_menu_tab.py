"""`TextMesh.tabSize`: a tab `\\t` in a menu text equals `tabSize` spaces, in ALL the cells that carry one (before: magic list only).
Real cases: "Nv." of the party order (type 20, tabSize 8), "x N" of the monster group plates in battle (type 31, tabSize 25). No engine or window; with the game's font (DQ_UI_CACHE: folder of ui_garrir.json / .png), "x2" to "x9" fit in the plate.
    python3 tests/test_menu_tab.py"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.menus import ui_menu as UM
FONT_CACHE = _paths.ui_cache('/tmp/audit_final/interface/uicache')


def type_tab(tab_size, name_str='Make_Test()'):
    """A plate and its text (cell (0, 0), tabSize given); code 0 ("monster plate"): -1 shows the plate, 1 shows the text."""
    square = {'vtx': [[-71.0, 18.0], [71.0, 18.0], [71.0, -18.0], [-71.0, -18.0]], 'uv': [[0, 0], [1, 0], [1, 1], [0, 1]], 'sub': {'0': [0, 1, 2, 0, 2, 3]}}
    return {'name': name_str, 'err': None,
            'nodes': [{'id': 1, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True, 'mats': []},
                      {'id': 10, 'par': 1, 'pos': [0.0, 4.0, 0.0], 'act': True, 'mats': [], 'mesh': square},
                      {'id': 11, 'par': 10, 'pos': [-60.0, 8.0, 8.0], 'act': True, 'text': {'font': 'font', 'characterSize': 10.0, 'text': None, 'tabSize': tab_size}, 'mats': []}],
            'parts': [{'node': 11, 'ib': [{'k': 'text', 'go': 11, 'variant': 0}]}],
            'params': [{'id': 0, 'no': 0, 'parts': 0, 'base': 0}],
            'codes': [{'id': 0, 'kind': 'func', 'fx': {'-1': {'d': {'10': {'act': False}}}, '1': {'d': {'11': {'act': True}}}}}], 'builds': []}


def window(tab_size, name_str='Make_Test()'):
    ml = types.SimpleNamespace(types={'99': type_tab(tab_size, name_str)}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0))
    return UM.Window(ml, 99)


class Tabulate(unittest.TestCase):
    def test_replacement(self):
        self.assertEqual(UM.expand_tabs('a\tb', 8), 'a' + ' ' * 8 + 'b'); self.assertEqual(UM.expand_tabs('\t×2', 25), ' ' * 25 + '×2')
        self.assertEqual(UM.expand_tabs('a\t\tb', 2), 'a    b'); self.assertEqual(UM.expand_tabs('a\tb', 7.6), 'a' + ' ' * 8 + 'b')

    def test_without_tabsize_or_without_tab_unchanged(self):
        for ts in (None, 0, 0.0): self.assertEqual(UM.expand_tabs('a\tb', ts), 'a\tb')
        self.assertEqual(UM.expand_tabs('abc', 8), 'abc'); self.assertEqual(UM.expand_tabs('', 8), ''); self.assertIsNone(UM.expand_tabs(None, 8))


class MenuCells(unittest.TestCase):
    def test_param_str_outside_spell_entries(self):                       # type 20 "Ordre de marche": before, only the magic list (Make_NameButton) was handled
        wnd = window(8); self.assertFalse(wnd.is_name_list)
        wnd.param_str(0, 0, '\tNv.: 5'); self.assertEqual(wnd.N[11]['text']['text'], ' ' * 8 + 'Nv.: 5')

    def test_param_str_spell_entries_unchanged(self):
        wnd = window(8, 'Make_NameButton(test)'); self.assertTrue(wnd.is_name_list)
        wnd.param_str(0, 0, 'Coût en PM:\t  2'); self.assertEqual(wnd.N[11]['text']['text'], 'Coût en PM:' + ' ' * 8 + '  2')

    def test_cell_without_tabsize_keeps_tab(self):
        wnd = window(None); wnd.param_str(0, 0, 'a\tb'); self.assertEqual(wnd.N[11]['text']['text'], 'a\tb')

    def test_group_plate(self):                                       # type 31: "name \n \t×N", tabSize 25
        wnd = window(25); wnd.plate(0, 'Gluant\n\t×2', [0, 0, 0, 0, 0], 1)
        self.assertEqual(wnd.N[11]['text']['text'], 'Gluant\n' + ' ' * 25 + '×2')
        wnd.plate(0, 'Gluant', [0, 0, 0, 0, 0], 1); self.assertEqual(wnd.N[11]['text']['text'], 'Gluant')          # a single monster: no tab, nothing changes


@unittest.skipUnless(os.path.exists(os.path.join(FONT_CACHE, 'ui_garrir.json')), 'game font missing (ui_garrir.json)')
class WithFont(unittest.TestCase):
    def test_times_n_fits_in_plate_up_to_nine(self):
        pol = UM.BitmapFont(os.path.join(FONT_CACHE, 'ui_garrir.json'), os.path.join(FONT_CACHE, 'ui_garrir.png'))
        px = 9.3925 * 0.1                                                  # Make_MonsterName: character of size 9.3925 (1 font px = cs * 0.1 unit), text anchored on the left at x = -74, plate from -71 to +71
        for n in ('\u00d72', '\u00d75', '\u00d79'):                    # (\u00d710 and more: end near x = 79, 8 units beyond the edge, as with the same constants in Unity: assumed)
            end = -74.0 + pol.width_px(UM.expand_tabs('\t' + n, 25)) * px
            self.assertLess(end, 71.0, (n, end))                           # "x N" ends inside the plate (on the left: tab ignored, it ended near -63)


if __name__ == '__main__': unittest.main(verbosity=1)
