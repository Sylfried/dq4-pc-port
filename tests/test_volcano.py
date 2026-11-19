"""Dragon Quest V's volcano on the world map (Unity's Volcano component over the mountain's icon: world/volcano.py), without a window or the game:

1. the crater sits at (4, 7) from the icon's corner, opaque;
2. the three puffs: steps 0, 8 and 16 at the start, + 2 every 4th frame, back to 0 after 22; each one rises and grows with its step, its alpha falls from 1 to 0 in 31sts.

    python3 tests/test_volcano.py
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.world import volcano as VO


class Volcano(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(VO.smoke_steps(0), [0, 8, 16])
        self.assertEqual(VO.smoke_steps(3), [0, 8, 16])
        self.assertEqual(VO.smoke_steps(4), [2, 10, 18])
        self.assertEqual(VO.smoke_steps(4 * 12), [0, 8, 16])                  # (24 steps of 2 = one full cycle every 48 frames)
        self.assertEqual(VO.smoke_steps(4 * 4), [8, 16, 0])

    def test_quads(self):
        q = VO.quads(0, (32, 32), (32, 32))
        self.assertEqual(q[0], (4.0, 7.0, 32, 32, 1.0, VO.CRATER))
        x, z, w, h, a, kind = q[1]
        self.assertEqual((x, z, w, h, a, kind), (4.0, 16.0, 32.0, 32.0, 1.0, VO.SMOKE))               # step 0: at the bottom, its own size, opaque
        x, z, w, h, a, kind = q[3]                                                                  # step 16
        s = 16 / 6.0
        self.assertAlmostEqual(x, 4 - s); self.assertAlmostEqual(z, 32 + s); self.assertAlmostEqual(w, 32 + 2 * s)
        self.assertAlmostEqual(a, (31 * 8 // 24) / 31.0)
        self.assertGreater(VO.quads(0, (32, 32), (32, 32))[3][1], VO.quads(0, (32, 32), (32, 32))[2][1])          # the later puff is higher up the map


if __name__ == '__main__':
    unittest.main()
