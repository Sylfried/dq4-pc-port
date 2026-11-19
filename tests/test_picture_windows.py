"""Picture windows: DQ V's Make_Sugoroku_Shop (the shops of the T'n'T boards) and DQ VI's Make_ShopPicture have no part in the exported layout: their code function creates one picture
(MenuParts.CreateFromTexture(name, true, 0.75): 450 x 337.5 at the center of the screen, the top three quarters of the texture). Local suite (imports the menus).

  python3 tests/test_picture_windows.py

1. DQ V: code 0, value 0 = the inn (`yado_pic`), any other value = the shop (`yorozu_pic`); created once (a later code 0 changes nothing); code 1 does nothing;
2. DQ VI: code 0, the value is the index (shop, inn, church; beyond: no picture); code 1 = the opacity, value / 31;
3. Manager.open_menu opens these windows although their type has no node; Render._load_face reads "pic:<name>" from the picture source, "face:<name>" from the portraits.
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper)
from dq456_pc.menus import ui_menu as UI


def window(name):
    w = object.__new__(UI.Window)
    w.N = {}; w.codes = {}; w.parts = []; w.names = False; w.begin = False; w.church = False; w.status = False; w.vals_code = {}
    w.pictures = next(v for k, v in UI.PICTURE_WINDOWS.items() if name.startswith(k)); w.picture_index = name.startswith('Make_ShopPicture(')
    return w


class Pictures(unittest.TestCase):
    def test_dq5_inn_or_shop(self):
        for value, sheet in ((0, 'pic:yado_pic'), (1, 'pic:yorozu_pic'), (7, 'pic:yorozu_pic')):
            w = window('Make_Sugoroku_Shop()'); w.code(0, value)
            self.assertEqual(w.N['picture']['mats'][0]['sheet'], sheet)
        w.code(0, 0); self.assertEqual(w.N['picture']['mats'][0]['sheet'], 'pic:yorozu_pic')          # (created once)
        w.code(1, 10); self.assertEqual(w.N['picture']['mats'][0]['color'][3], 1.0)

    def test_dq6_index_and_opacity(self):
        for value, sheet in ((0, 'pic:yorozu_pic'), (1, 'pic:yado_pic'), (2, 'pic:kyokai_pic')):
            w = window('Make_ShopPicture()'); w.code(0, value)
            self.assertEqual(w.N['picture']['mats'][0]['sheet'], sheet)
        w.code(1, 20); self.assertAlmostEqual(w.N['picture']['mats'][0]['color'][3], 20 / 31.0)
        w.code(1, 31); self.assertEqual(w.N['picture']['mats'][0]['color'][3], 1.0)
        w = window('Make_ShopPicture()'); w.code(0, 3); self.assertNotIn('picture', w.N)
        w.code(1, 20)                                                                                # (no picture: nothing)

    def test_shape(self):
        w = window('Make_ShopPicture()'); w.code(0, 1); n = w.N['picture']
        xs = [v[0] for v in n['vtx']]; ys = [v[1] for v in n['vtx']]
        self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (-225.0, 225.0, -168.75, 168.75))
        self.assertEqual(sorted(set(v[1] for v in n['uv'])), [0.25, 1.0])                            # (the top three quarters)

    def test_open_menu(self):
        ml = types.SimpleNamespace(types={'90': dict(name='Make_Sugoroku_Shop()', nodes=[]), '5': dict(name='Make_Other()', nodes=[])})
        m = object.__new__(UI.Manager); m.ml = ml; m.f = {}; m.shop_type = None
        made = []
        real = UI.Window
        UI.Window = lambda ml_, typ, shop: made.append(typ) or 'window'
        try:
            m.open_menu(3, 90); m.open_menu(4, 5)
        finally: UI.Window = real
        self.assertEqual(made, [90]); self.assertEqual(m.f, {3: 'window'})

    def test_sources(self):
        r = object.__new__(UI.Render); added = []
        r.add_texture = lambda name, arr, clamp=False: added.append((name, arr))
        r.face_source = lambda n: 'F' + n; r.picture_source = lambda n: 'P' + n if n == 'yado_pic' else None
        self.assertTrue(r._load_face('face:f05')); self.assertTrue(r._load_face('pic:yado_pic')); self.assertFalse(r._load_face('pic:none')); self.assertFalse(r._load_face('other'))
        self.assertEqual(added, [('face:f05', 'Ff05'), ('pic:yado_pic', 'Pyado_pic')])


if __name__ == '__main__':
    unittest.main()
