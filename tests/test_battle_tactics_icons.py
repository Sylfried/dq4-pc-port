"""Battle tactics window: the icons of a row come with its code (MenuPortItemTable.<Sub_BattleTactics>b__0), not only the name's place: the "Équipe" row
showed the portrait left in the prefab (the hero, Maya...) instead of the wagon, DQ V / VI a placeholder or nothing.

    python3 tests/test_battle_tactics_icons.py
"""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq456_pc.menus import ui_menu as UM
except Exception as ex: UM = None

INFO = {1: dict(startNo=0, widthNum=32, uvsize=0.03125, startV=0.1875), 2: dict(startNo=0, widthNum=10, uvsize=0.09375, startV=0.5625),
        3: dict(startNo=0, widthNum=32, uvsize=0.03125, startV=0.21875)}


def window(game, face_kind='icon'):
    """A row like DQ IV's (IBase 1 the portrait, 2 and 3 the AddIcon icons, vertices 36, 40, 44) or DQ V's (IBase 1 an ITexture)."""
    face = dict(k='icon', partsNo=2, vtx=36) if face_kind == 'icon' else dict(k='other', cls='MenuParts.ITexture')
    ib = [dict(k='button'), face, dict(k='icon', partsNo=1, vtx=40), dict(k='icon', partsNo=3, vtx=44)]
    node = dict(id=1880, uv=[[0.0, 0.0]] * 48, sub={'0': list(range(36)), '1': list(range(36, 48))}, state=0,
                mats=[dict(sheet=1, color=None), dict(sheet=0, color=[0.0, 0.0, 0.0, 0.0], shown_color=None)])
    w = types.SimpleNamespace(parts=[dict(node=1505, ib=[]), dict(node=1880, ib=ib)], N={1880: node}, ml=types.SimpleNamespace(info=INFO), faces=[])
    w._face = lambda j, v: w.faces.append((j, v))
    entry = dict(kind='func', method='MenuPortItemTable.<>c__DisplayClass86_0.<Sub_BattleTactics>b__0()', fx={'0': {'d': {'1880': {'act': False}}}})
    return w, node, entry


@unittest.skipIf(UM is None, 'menus not importable here')
class TacticsRow(unittest.TestCase):
    def setUp(self):
        self.gm = UM.GM; self.addCleanup(setattr, UM, 'GM', self.gm)

    def game(self, key): UM.GM = types.SimpleNamespace(profile=lambda: types.SimpleNamespace(key=key))

    def test_dq4_party_row_shows_the_wagon(self):
        self.game('dq4'); w, node, e = window('dq4')
        UM.Window._tactics_row(w, e, 2)
        self.assertEqual(node['uv'][40], list(UM.uv_icon(INFO[1], 22, 0)[0]))           # the wagon, small icons row
        self.assertEqual(node['uv'][36], list(UM.uv_icon(INFO[2], 18, 0)[0]))           # an empty portrait cell
        self.assertEqual(node['state'], 0)

    def test_dq4_member_row_and_code_4(self):
        self.game('dq4'); w, node, e = window('dq4'); node['uv'][36] = [9.0, 9.0]
        UM.Window._tactics_row(w, e, 1)
        self.assertEqual(node['uv'][36], [9.0, 9.0])                                    # the portrait is the engine's
        self.assertEqual(node['uv'][40], list(UM.uv_icon(INFO[1], 24, 0)[0]))
        UM.Window._tactics_row(w, e, 4); self.assertEqual(node['state'], 4)

    def test_dq5_party_row(self):
        self.game('dq5'); w, node, e = window('dq5', 'texture')
        UM.Window._tactics_row(w, e, 2)
        self.assertEqual(w.faces, [(1, 0)])                                              # no portrait (the games have no f00)
        self.assertEqual(node['uv'][40], list(UM.uv_icon(INFO[1], 92, 0)[0]))
        self.assertIsNone(node['mats'][1]['color'])                                      # the cell hidden as a placeholder shown again

    def test_other_windows_untouched(self):
        self.game('dq4'); w, node, e = window('dq4'); e['method'] = 'MenuPortItemTable.<>c__DisplayClass12_0.<Sub_Other>b__0()'
        before = [list(uv) for uv in node['uv']]
        UM.Window.code(types.SimpleNamespace(vals_code={}, church=False, status=False, names=False, begin=False, codes={2: [e]}, N=w.N, parts=w.parts, _mask_code=lambda e, c: None), 2, 7)
        self.assertEqual(node['uv'], before)


if __name__ == '__main__':
    unittest.main()
