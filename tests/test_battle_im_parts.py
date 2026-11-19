"""Battle list windows of DQ V / VI (Make_BattleIM) and their parts:
  - MenuParts.ITexture (IntChanger): a member's portrait Menu/face/fNN on its row (Tactics window) and on its battle plate; the placeholder icon of the row (AddIcon 24 of sheet 1,
    never changed by a parameter: blank in DQ VI's sheet, a healslime in DQ V's) is not drawn;
  - MenuPortItem.SetTableForCode is a dictionary: the last registration of a code number wins. The page arrows, registered under code 1, are replaced by row 1's code, so a page 2
    holding a single spell no longer hides them;
  - the interface block of DQ V / VI's MenuTexture sheet is 352 px lower than DQ IV's (sheets.interface_dy);
  - the prize counter's 7 rows (Make_Casino_GiftList with s_shopType 6 or 13) and their prices.

    python3 tests/test_battle_im_parts.py"""
import os, sys, types, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM
from dq456_pc.menus import sheets as SH


def ml_of(t):
    return types.SimpleNamespace(types={'37': t}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0))


def tactics_type():
    """One row of the Tactics window: button (sub 0), portrait (sub 1, material without a sheet), placeholder icon of sheet 1 (sub 2), name; the page arrows (parts 1, 2) under code 1, then row 1's code."""
    quad = [[-1.0, 1.0], [1.0, 1.0], [1.0, -1.0], [-1.0, -1.0]]
    row = {'id': 10, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True,
           'mesh': {'vtx': quad * 3, 'uv': quad * 3, 'sub': {'0': [0, 1, 2], '1': [4, 5, 6], '2': [8, 9, 10]}},
           'mats': [{'sheet': 1, 'part': 7, 'color': [1.0, 1.0, 1.0, 1.0]}, {'sheet': None, 'part': None, 'color': [0.0, 0.0, 0.0, 0.0]}, {'sheet': 0, 'part': 1, 'color': None}]}
    arrow = lambda i: {'id': i, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True, 'mats': []}
    return {'name': 'Make_BattleIM()', 'err': None, 'nodes': [row, arrow(20), arrow(21)],
            'parts': [{'node': 10, 'ib': [{'k': 'button'}, {'k': 'other', 'cls': 'MenuParts.ITexture'}, {'k': 'icon', 'cls': 'MenuParts.IIcon', 'partsNo': 1, 'vtx': 8}]},
                      {'node': 20, 'ib': [{'k': 'button'}]}, {'node': 21, 'ib': [{'k': 'button'}]}],
            'params': [{'id': 0, 'no': 0, 'parts': 0, 'base': 1}],
            'codes': [{'id': 1, 'kind': 'active', 'parts': 1}, {'id': 1, 'kind': 'active', 'parts': 2},
                      {'id': 1, 'kind': 'func', 'fx': {'0': {'d': {'10': {'act': False}}}, '2': {'d': {}}}}], 'builds': []}


class Portrait(unittest.TestCase):
    def test_the_portrait_and_no_placeholder(self):
        w = UM.Window(ml_of(tactics_type()), 37)
        self.assertEqual(w.N[10]['mats'][2]['color'], [0.0, 0.0, 0.0, 0.0])           # (the healslime of DQ V's sheet: not drawn, even before any portrait)
        w.param_int(0, 0, 8)
        self.assertEqual(w.N[10]['mats'][1]['sheet'], 'face:f08')
        self.assertEqual(w.N[10]['mats'][1]['color'], [1.0, 1.0, 1.0, 1.0])
        w.param_int(0, 0, 13); self.assertEqual(w.N[10]['mats'][1]['sheet'], 'face:f13')
        self.assertEqual(w.N[10]['mats'][0]['sheet'], 1)                                # (the button's plate is untouched)

    def test_face_loader(self):
        import tempfile, numpy as np
        d = tempfile.mkdtemp()
        np.savez_compressed(os.path.join(d, UM.FACES), f08=np.zeros((4, 4, 4), np.uint8))
        get = UM.face_loader(d)
        self.assertEqual(get('f08').shape, (4, 4, 4)); self.assertIsNone(get('f99'))
        self.assertIsNone(UM.face_loader(tempfile.mkdtemp())('f08'))                    # (no file: no portrait, nothing breaks)


class LastCodeWins(unittest.TestCase):
    def test_page_arrows_stay(self):
        w = UM.Window(ml_of(tactics_type()), 37)
        w.code(1, 0)                                         # page 2 with a single spell: row 1 hidden...
        self.assertTrue(w.N[20]['act']); self.assertTrue(w.N[21]['act'])          # ...the arrows stay
        self.assertEqual([e['kind'] for e in w.codes[1]], ['func'])


def gift_type():
    """Make_Casino_GiftList as exported (s_shopType 0): frame + prices' text (number 6), 6 rows 58 apart from z -7 (button + text child), back button."""
    nodes = [{'id': 1, 'par': None, 'pos': [-225.0, 0.0, -402.0], 'act': True, 'mats': []},
             {'id': 2, 'par': 1, 'pos': [217.5, 4.0, 22.5], 'act': True, 'mats': [], 'text': {'text': None, 'lineSpacing': 2.46, 'characterSize': 9.945, 'anchor': 2, 'alignment': 2, 'font': 'font'}}]
    parts = [{'node': 1, 'ib': [{'k': 'frame', 'go': 1}, {'k': 'text', 'go': 2, 'variant': 0}]}]
    params = [{'id': 6, 'no': 0, 'parts': 0, 'base': 1}]
    for k in range(6):
        b, t = 10 + 2 * k, 11 + 2 * k
        nodes += [{'id': b, 'par': 1, 'pos': [-131.0, 4.0, -7.0 - 58.0 * k], 'act': True, 'mats': [], 'parts': {'buttonId': k, 'gamepad': 16}},
                  {'id': t, 'par': b, 'pos': [-173.0, 8.0, 13.0 - 58.0 * k], 'act': True, 'mats': [], 'text': {'text': None, 'lineSpacing': 0.8, 'characterSize': 9.945, 'anchor': 3, 'alignment': 0, 'font': 'font'}}]
        parts.append({'node': b, 'ib': [{'k': 'button'}, {'k': 'icon', 'partsNo': 12, 'vtx': 36}, {'k': 'text', 'go': t, 'variant': 0}]})
        params += [{'id': k, 'no': 0, 'parts': k + 1, 'base': 1}, {'id': k, 'no': 1, 'parts': k + 1, 'base': 2}, {'id': k, 'no': 3, 'parts': k + 1, 'base': 0}]
    nodes.append({'id': 50, 'par': 1, 'pos': [187.5, 4.0, -366.0], 'act': True, 'mats': [], 'parts': {'buttonId': -1, 'gamepad': 32}})
    parts.append({'node': 50, 'ib': [{'k': 'button'}]})
    return {'name': 'Make_Casino_GiftList()', 'err': None, 'nodes': nodes, 'parts': parts, 'params': params,
            'codes': [{'id': k, 'kind': 'active', 'parts': k + 1} for k in range(6)], 'builds': []}


class SevenPrizes(unittest.TestCase):
    """MenuPortItem.s_shopType (engine code 14) 6 or 13: Make_Casino_GiftList builds 7 rows 50 apart and the prices go to number 7 (DQ V's prize counter: the prices were missing)."""
    def window(self, shop):
        return UM.Window(types.SimpleNamespace(types={'45': gift_type()}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0)), 45, shop)

    def test_seven_rows(self):
        w = self.window(6)
        rows = [w.N[pt['node']] for pt in w.parts[1:8]]
        self.assertEqual([r['buttonId'] for r in rows], list(range(7)))
        self.assertEqual([r['pos'][2] for r in rows], [-2.0 - 50.0 * k for k in range(7)])
        self.assertEqual(w.N[w.parts[8]['node']]['pos'][2], -366.0)                        # (the back button stays)
        w.param_str(7, 0, ' 10\n 20'); self.assertEqual(w.N[2]['text']['text'], ' 10\n 20')
        self.assertEqual(w.N[2]['pos'][2], 25.5); self.assertAlmostEqual(w.N[2]['text']['lineSpacing'], 2.46 * 2.65 / 3.07)
        w.param_str(6, 1, 'Rouge'); self.assertEqual(w.N[w.parts[7]['ib'][2]['go']]['text']['text'], 'Rouge')
        w.code(6, 0); self.assertFalse(rows[6]['act'])
        self.assertEqual(w.N[w.parts[7]['ib'][2]['go']]['pos'][2], 13.0 - 58.0 * 5 - 5.0)    # (the 7th row's text follows its button)

    def test_other_shops_unchanged(self):
        w = self.window(0)
        self.assertEqual(len(w.parts), 8); self.assertNotIn((7, 0), w.params)
        w.param_str(6, 0, ' 10'); self.assertEqual(w.N[2]['text']['text'], ' 10')


class InterfaceBlock(unittest.TestCase):
    def test_offset(self):
        win = lambda sy: types.SimpleNamespace(ui_g=types.SimpleNamespace(ml=types.SimpleNamespace(hdr={'info': [{}, {}, {}, {'sy': sy}]})))
        self.assertEqual(SH.interface_dy(win(224)), 0)          # DQ IV
        self.assertEqual(SH.interface_dy(win(576)), 352)        # DQ V / VI
        self.assertEqual(SH.interface_dy(types.SimpleNamespace()), 0)


if __name__ == '__main__':
    unittest.main()
