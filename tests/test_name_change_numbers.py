"""DQ VI's name change buttons (Make_ChangeName_Select, Sub_ChangeNameButton): the level text's int function writes the number itself (nothing below 1); the other texts' int function is
their color, as everywhere else. Local suite (imports the menus).

  python3 tests/test_name_change_numbers.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper)
from dq456_pc.menus import ui_menu as UI


def window():
    w = object.__new__(UI.Window)
    w.N = {10: dict(text=dict(text='?'), tcol=0), 11: dict(text=dict(text='Rek'), tcol=0)}
    w.parts = [dict(node=1, ib=[dict(k='text', go=10, int='MenuPortItemTable.<>c__DisplayClass182_0.<Sub_ChangeNameButton>b__0()'), dict(k='text', go=11, int='MenuParts.IText.<>c__DisplayClass3_1.<.ctor>b__1()')])]
    w.params = {(0, 3): dict(parts=0, base=0), (0, 1): dict(parts=0, base=1)}
    return w


class Numbers(unittest.TestCase):
    def test_level_number(self):
        w = window()
        w.param_int(0, 3, 12); self.assertEqual(w.N[10]['text']['text'], '12'); self.assertEqual(w.N[10]['tcol'], 0)
        w.param_int(0, 3, 0); self.assertEqual(w.N[10]['text']['text'], '')

    def test_other_texts_keep_the_color(self):
        w = window()
        w.param_int(0, 1, 3); self.assertEqual(w.N[11]['tcol'], 3); self.assertEqual(w.N[11]['text']['text'], 'Rek')


if __name__ == '__main__':
    unittest.main()
