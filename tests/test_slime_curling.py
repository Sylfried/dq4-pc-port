"""Dragon Quest VI's slime curling (SlimeCurlingPort, SlimeCurling__TouchPanel, SlimeCurling__ConvertPosition: core/slime_curling.py), without a window or an engine:

1. the two ports (category 5): type 0 the touch panel, type 1 the converter; closing both ends the mini-game; in DQ V the same category is the Slime Touch;
2. the touch panel: [x, y, touching] in LCD units at each frame (the zero vector's place without a touch), nothing while it is off or while the game's flag bit 16 is up;
3. the converter: the engine's point (three floats in pairs of shorts), its place answered only when it moved;
4. units: a window pixel and a point of the world end in the same place (the phone's screen centered, the window showing its whole height); infinite values;
5. the keys: the rubbing finger stays in its half of the slide's zone and goes back and forth.

    python3 tests/test_slime_curling.py
"""
import os, struct, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import slime_curling as SC

ASPECT = 0.5625


def shorts_of(*fl):
    out = []
    for v in fl:
        lo, hi = struct.unpack('<HH', struct.pack('<f', v)); out += [lo, hi]
    return out


def curling():
    st = SC.new(); SC.add_port(st, 13, SC.TOUCH_PANEL); SC.add_port(st, 14, SC.CONVERT_POSITION); return st


class Ports(unittest.TestCase):
    def test_ports(self):
        st = curling()
        self.assertEqual(SC.port_of(st, SC.TOUCH_PANEL), 13); self.assertEqual(SC.port_of(st, SC.CONVERT_POSITION), 14)
        SC.close_port(st, 13); self.assertTrue(st['live'])
        SC.close_port(st, 14); self.assertFalse(st['live'])

    def test_touch_panel_on_off(self):
        st = curling()
        SC.notice(st, 13, [0]); self.assertFalse(st['touch_on'])
        self.assertIsNone(SC.touch_message(st, 0, True, (0.5, 0.5), ASPECT))
        SC.notice(st, 13, [1]); self.assertTrue(st['touch_on'])


class TouchPanel(unittest.TestCase):
    def test_messages(self):
        st = curling()
        self.assertEqual(SC.touch_message(st, 0, False, (0.3, 0.8), ASPECT), [0, 227, 0])          # no touch: (0, 0) of the screen
        self.assertEqual(SC.touch_message(st, 0, True, (0.5, 0.5), ASPECT), [128, 0, 1])
        self.assertEqual(SC.touch_message(st, 0, True, (0.25, 0.75), ASPECT), [64, -113, 1])          # (y from the middle, downwards)
        self.assertIsNone(SC.touch_message(st, SC.TOUCH_PAUSED, True, (0.5, 0.5), ASPECT))
        self.assertIsNone(SC.touch_message(SC.new(), 0, True, (0.5, 0.5), ASPECT))                     # (no port yet)

    def test_lcd(self):
        self.assertAlmostEqual(SC.lcd_height(ASPECT), 455.111, places=2)
        self.assertEqual(SC.to_lcd(float('inf'), 0.5, ASPECT), (0, 0))
        self.assertEqual(SC.short(70000), 70000 - 65536)


class Converter(unittest.TestCase):
    def test_point_and_answer(self):
        st = curling()
        SC.notice(st, 14, shorts_of(1.5, 0.0, -2.0))
        self.assertEqual(st['point'], (1.5, 0.0, -2.0))
        self.assertEqual(SC.convert_answer(st, (0.5, 0.25), ASPECT), [128, 113]); self.assertIsNone(st['point'])
        SC.notice(st, 14, shorts_of(1.5, 0.0, -2.0))
        self.assertIsNone(SC.convert_answer(st, (0.5, 0.25), ASPECT))                                  # (it has not moved: no answer)
        self.assertEqual(SC.convert_answer(st, (0.6, 0.25), ASPECT), [153, 113])

    def test_window_and_world_agree(self):
        W, H = 1280, 720
        vx, vy = SC.window_to_viewport(W / 2, H / 2, W, H, 1 / ASPECT, ASPECT)
        self.assertAlmostEqual(vx, 0.5); self.assertAlmostEqual(vy, 0.5)
        vx, vy = SC.window_to_viewport(W / 2, 0, W, H, 1 / ASPECT, ASPECT)                            # the bottom of the window = the bottom of the phone's screen (its whole height)
        self.assertAlmostEqual(vy, 0.0)
        vx, vy = SC.window_to_viewport(W / 2 + H * ASPECT / 2, H / 2, W, H, 1 / ASPECT, ASPECT)          # the phone's right edge
        self.assertAlmostEqual(vx, 1.0)


class Keys(unittest.TestCase):
    def test_rubbing(self):
        from dq456_pc.window import slime_curling as WC
        xs = [WC.rub_x(150, -1, k) for k in range(1, 3 * WC.RUB_PERIOD)]
        self.assertTrue(all(150 - 64 <= x < 150 for x in xs))                                        # the left half of the zone (center +- 64)
        self.assertGreater(len(set(xs)), 3)                                                          # the finger moves (the engine counts its sideways moves)
        self.assertTrue(all(150 < WC.rub_x(150, 1, k) <= 150 + 64 for k in range(20)))


class Interface(unittest.TestCase):
    def setUp(self):
        from dq456_pc import games as GM
        from dq456_pc.core import engine as ENGINE
        self.GM, self.ENGINE = GM, ENGINE
        self.old = (ENGINE.ENGINE_V2, GM.profile)
        ENGINE.ENGINE_V2 = True

    def tearDown(self):
        self.ENGINE.ENGINE_V2, self.GM.profile = self.old

    def test_dq6(self):
        self.GM.profile = lambda: self.GM.GAMES['dq6']
        ui = self.ENGINE.Interface()
        ui.apply([(0, [13, 1, 5, 0]), (0, [14, 1, 5, 1]), (13, [0]), (14, shorts_of(0.0, 0.0, -0.0))])
        self.assertTrue(ui.curling['live']); self.assertFalse(ui.curling['touch_on']); self.assertEqual(ui.curling['point'], (0.0, 0.0, -0.0))
        self.assertIsNone(ui.slime_touch)
        ui.apply([(0, [13, 2]), (0, [14, 2])]); self.assertFalse(ui.curling['live'])

    def test_dq5_is_the_slime_touch(self):
        self.GM.profile = lambda: self.GM.GAMES['dq5']
        ui = self.ENGINE.Interface(); ui.apply([(0, [12, 1, 5, 0])])
        self.assertIsNone(ui.curling); self.assertTrue(ui.slime_touch['live'])


if __name__ == '__main__':
    unittest.main()
