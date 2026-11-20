"""Battle speed key in battle only, "Return to title screen" on a game loaded onto the world map, vignette 0 by default,
accelerator x4 at most.

    python3 tests/test_battle_speed_key_rules.py
"""
import json, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG
from dq456_pc.window import game as WND


class BattleSpeedKey(unittest.TestCase):
    def press(self, part):
        calls = []
        j = types.SimpleNamespace(debug=None, _ready=True, _window_shortcut=lambda s, m: False, mouse_guard=types.SimpleNamespace(keyboard=lambda m: None), mouse=None, pause=types.SimpleNamespace(opened=False),
                                  _name_entry_in_progress=lambda: False, port_screen=None, license_panel=None, reg=RG.Settings(None), engine=types.SimpleNamespace(state=types.SimpleNamespace(part=part)),
                                  change_battle_speed=lambda *a: calls.append(1))
        WND.Game.on_key_press(j, pyglet.window.key.V, 0); return calls

    def test_only_in_battle(self):
        self.assertEqual(self.press(ENGINE.PART_BATTLE), [1])
        for part in (ENGINE.PART_TOWN, ENGINE.PART_FIELD): self.assertEqual(self.press(part), [], part)


class BackToTitle(unittest.TestCase):
    def possible(self, part, map_name):
        j = types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(part=part), back_to_title_state=None), map_name=map_name)
        return WND.Game.back_to_title_possible(j)

    def test_world_map_after_the_title(self):
        self.assertTrue(self.possible(ENGINE.PART_FIELD, ENGINE.TITLE_MAP))                                  # (game loaded straight onto the world map)
        self.assertFalse(self.possible(ENGINE.PART_TOWN, ENGINE.TITLE_MAP))                                  # the title screen itself
        self.assertTrue(self.possible(ENGINE.PART_TOWN, 'mak1f1')); self.assertFalse(self.possible(ENGINE.PART_BATTLE, 'mak1f1'))


class Halo(unittest.TestCase):
    def test_soft_halo_keeps_the_gradient_without_magenta(self):
        import numpy as np
        from dq456_pc.world import hd as HD
        a = np.zeros((1, 4, 4), np.uint8); a[0, 0] = (255, 0, 255, 60); a[0, 1] = (10, 200, 30, 230); a[0, 2] = (255, 0, 255, 0); a[0, 3] = (255, 0, 255, 100)
        sharp, _ = HD.clean_sheet(a); soft, _ = HD.clean_sheet(a, soft=True)
        self.assertEqual(sharp[0, :, 3].tolist(), [0, 255, 0, 0])
        self.assertEqual(soft[0, :, 3].tolist(), [60, 255, 0, 100]); self.assertEqual(soft[0, 0, :3].tolist(), [10, 200, 30])         # the gradient stays, in the body's color


class SystemClick(unittest.TestCase):
    """click, hold and drag values are Windows' own (GetDoubleClickTime, SM_CXDRAG / SM_CYDRAG); elsewhere the Windows defaults."""
    def test_values_and_drag(self):
        from unittest import mock
        from dq456_pc.window import inputs as EN
        if sys.platform != 'win32': self.assertEqual(EN.system_click(), (0.5, 4, 4))
        with mock.patch.object(EN, 'system_click', lambda: (0.5, 4, 4)):
            self.assertFalse(EN.is_drag(4, -4)); self.assertTrue(EN.is_drag(5, 0)); self.assertTrue(EN.is_drag(0, -5))
        with mock.patch.object(EN, 'system_click', lambda: (0.9, 10, 10)): self.assertFalse(EN.is_drag(8, 8))          # (a player who widened Windows' drag rectangle)


class BarOutline(unittest.TestCase):
    """the dark outline of the rotation bar's icons never fills the gaps between the dashes of the arrows (the stray dark lines seen in a window)."""
    def test_gaps_stay_open(self):
        import numpy as np
        from dq456_pc.menus import hud_mobile as HM
        b = HM.Buttons.__new__(HM.Buttons); b.orig = {}
        a = np.zeros((32, 32, 4), np.uint8); a[15:17, 4:6, 3] = 255; a[15:17, 7:9, 3] = 255                  # two dashes, one transparent column (6) between them
        b.orig['bar_1'] = a; o = b._outline('bar_1')[..., 3] > 0
        self.assertFalse(o[15:17, 6].any())                                                               # the gap stays open
        self.assertTrue(o[14, 4] and o[17, 8] and o[15, 3] and o[16, 9])                                  # the outside is outlined
        self.assertFalse(o[15:17, 4:6].any())                                                             # never over the icon itself


class Settings(unittest.TestCase):
    def load(self, d):
        t = tempfile.mkdtemp(prefix='d284_'); self.addCleanup(shutil.rmtree, t, True); p = os.path.join(t, 'settings.json')
        with open(p, 'w', encoding='utf-8') as f: json.dump(d, f)
        return RG.Settings(p)

    def test_vignette_default_and_migration(self):
        self.assertEqual(RG.DEFAULT['vignette'], 0.0)
        self.assertEqual(self.load({'keys_version': 5, 'vignette': 0.3})['vignette'], 0.0)                 # the old default follows the new one
        self.assertEqual(self.load({'keys_version': 5, 'vignette': 0.5})['vignette'], 0.5)                 # a choice of the player stays
        self.assertEqual(self.load({'keys_version': 6, 'vignette': 0.3})['vignette'], 0.3)                 # (chosen after the migration)

    def test_accelerator_x4(self):
        self.assertEqual(self.load({'keys_version': 6, 'accel_speed': 8.0})['accel_speed'], 4.0)


if __name__ == '__main__':
    unittest.main()
