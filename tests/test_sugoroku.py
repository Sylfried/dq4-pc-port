"""Dragon Quest V's T'n'T board (core/sugoroku.py), without a window or an engine:

1. the arrow window's messages: an arrow's position and turn arrive as an array after their code (MenuPort.Receive), its frame in its code, code 10 = the arrows shown;
2. the interface: the window of type ARROW_TYPE keeps its arrows in DQ V only; the array is not read as a command;
3. an arrow lies on the board (Euler(90, turn, 0)), 1.8 units wide, its tip toward +z at turn 0 and toward -x at turn -90;
4. a click: a point in an arrow's quadrilateral; the key of a direction on the screen; the icon's place in the sheet.

    python3 tests/test_sugoroku.py
"""
import os, struct, sys, unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import sugoroku as SG


def shorts(*floats):
    raw = struct.pack('<%df' % len(floats), *floats)
    return [v - 0x10000 if v & 0x8000 else v for v in struct.unpack('<%dH' % (len(raw) // 2), raw)]


class Messages(unittest.TestCase):
    def test_floats(self):
        self.assertEqual(SG.floats(shorts(1.5, -2.25, 0.0)), [1.5, -2.25, 0.0])

    def test_position_turn_frame(self):
        f = {'visible': True, 'indicators': {}}
        SG.code(f, 1, 0x100); SG.receive(f, shorts(-1.5, 0.75, 8.5))
        SG.code(f, 1, 0x200); SG.receive(f, shorts(-90.0))
        SG.code(f, 1, 0x304)
        self.assertNotIn('arrow_pending', f)
        self.assertEqual(f['arrows'][1], {'pos': (-1.5, 0.75, 8.5), 'turn': -90.0, 'frame': 4})
        self.assertEqual(SG.shown(f), [])                                   # (code 10 not received: no arrow shown)
        f['indicators'][SG.ACTIVE_CODE] = 2
        self.assertEqual(SG.shown(f), [((-1.5, 0.75, 8.5), -90.0, 4)])
        f['visible'] = False; self.assertEqual(SG.shown(f), [])

    def test_other_codes_ignored(self):
        f = {}
        SG.code(f, 10, 3); SG.code(f, 2, 0x100)
        self.assertNotIn('arrow_pending', f); self.assertNotIn('arrows', f)


class Interface(unittest.TestCase):
    def setUp(self):
        from dq456_pc import games as GM
        from dq456_pc.core import engine as ENGINE
        self.GM, self.ENGINE = GM, ENGINE
        self.old = (ENGINE.ENGINE_V2, GM.profile)
        ENGINE.ENGINE_V2 = True

    def tearDown(self):
        self.ENGINE.ENGINE_V2, self.GM.profile = self.old

    def run_window(self, game):
        self.GM.profile = lambda: self.GM.GAMES[game]
        ui = self.ENGINE.Interface()
        ui.apply([(0, [12, 1, 1, SG.ARROW_TYPE]), (12, [12, 0, 0x100]), (12, shorts(0.0, 0.93, 1.25)), (12, [12, 0, 0x200]), (12, shorts(0.0)), (12, [12, 10, 1]), (12, [5])])
        return ui.f[12]

    def test_dq5(self):
        f = self.run_window('dq5')
        self.assertTrue(f['visible'])
        self.assertEqual(SG.shown(f), [((0.0, 0.9300000071525574, 1.25), 0.0, 0)])

    def test_dq6_has_no_board(self):
        f = self.run_window('dq6')
        self.assertNotIn('arrows', f)


class Geometry(unittest.TestCase):
    def test_lies_on_the_board(self):
        q = SG.corners((2.0, 1.0, 3.0), 0.0)
        self.assertTrue(np.allclose(q[:, 1], 1.0))                          # flat: all corners at the arrow's height
        self.assertAlmostEqual(float(np.linalg.norm(q[1] - q[0])), SG.ARROW_SIZE, places=6)
        self.assertTrue(np.allclose(q.mean(0), (2.0, 1.0, 3.0)))

    def test_tip(self):
        self.assertTrue(np.allclose(SG.tip(0.0), (0.0, 0.0, 1.0), atol=1e-9))
        self.assertTrue(np.allclose(SG.tip(-90.0), (-1.0, 0.0, 0.0), atol=1e-9))
        self.assertTrue(np.allclose(SG.tip(90.0), (1.0, 0.0, 0.0), atol=1e-9))

    def test_icon_top_edge_toward_tip(self):
        q = SG.corners((0.0, 0.0, 0.0), 0.0)                                # (top left, top right: the icon's top, toward the tip)
        self.assertGreater((q[0] + q[1])[2], (q[2] + q[3])[2])


class Click(unittest.TestCase):
    def test_inside(self):
        quad = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(SG.inside((5, 5), quad)); self.assertFalse(SG.inside((12, 5), quad)); self.assertTrue(SG.inside((12, 5), quad, 1.5))

    def test_key_of(self):
        self.assertEqual(SG.key_of(0, 5), SG.UP); self.assertEqual(SG.key_of(0, -5), SG.DOWN)
        self.assertEqual(SG.key_of(-5, 1), SG.LEFT); self.assertEqual(SG.key_of(5, -1), SG.RIGHT)

    def test_icon_rect(self):
        info = {'tex': 0, 'ps': 32, 'W': 1024, 'uvsize': 0.03125, 'startV': 0.59375, 'widthNum': 32, 'startNo': 14}
        self.assertEqual(SG.icon_rect(info, 0), (448, 608, 32))
        self.assertEqual(SG.icon_rect(info, 5), (608, 608, 32))
        self.assertEqual(SG.icon_rect(info, 18), (0, 640, 32))


if __name__ == '__main__':
    unittest.main()
