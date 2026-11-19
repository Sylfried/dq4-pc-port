"""Tests for the audit's "maps, NPCs, switches" mission (no window, no engine, no APK):

1. a town character that receives a pose (packet 13, bit 0x4000) without ever having received a position is at the ORIGIN (0, 0, 0): the engine only sends a position if it changes
   (its record of the character is (0, 0, 0): reread from the engine's memory on mqtf3, mom2f1 and msm1f1, slot 8: Fix32 at 0x1026a688 + 0x1c0 x (slot - 8));

  python3 tests/test_maps_npcs.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE


def map_name(): return 'carte_test'


class TestSpritesAtOrigin(unittest.TestCase):
    def setUp(self): self.e = ENGINE.State()

    def apply(self, *packets): self.e.apply(list(packets), map_name)

    def test_pose_without_position(self):
        self.e.image = 153; self.apply((12, [8, 157], []))
        self.assertIsNone(self.e.sprites[8]['pos'])                  # loaded, not yet placed: nothing to draw
        self.e.image = 154; self.apply((13, [0x4008, 0 | (0 << 8)], []))      # 1st placement, 1 frame later: the other characters' position arrives at this frame or the next, nothing is drawn yet
        self.assertIsNone(self.e.sprites[8]['pos'])
        self.e.image = 159; self.apply((13, [0x4008, 1 | (2 << 8)], []))      # pose 1, heading 2, still no position: the character is at the origin
        s = self.e.sprites[8]
        self.assertEqual((s['pose'], s['dir']), (1, 2))
        self.assertEqual(tuple(s['pos']), (0.0, 0.0, 0.0))

    def test_received_position_kept(self):
        self.apply((12, [9, 21], []))
        self.apply((13, [0x6009, 0 | (3 << 8)], [3.5, 0.25, -2.0]))     # position + pose in the same packet
        self.assertEqual(tuple(self.e.sprites[9]['pos']), (3.5, 0.25, -2.0))
        self.apply((13, [0x4009, 1 | (3 << 8)], []))             # pose only afterward: the position does not move
        self.assertEqual(tuple(self.e.sprites[9]['pos']), (3.5, 0.25, -2.0))

    def test_position_before_pose_in_same_frame(self):
        self.apply((12, [10, 5], []), (13, [0x400a, 2 << 8], []), (13, [0x200a], [1.0, 0.0, 4.0]))
        self.assertEqual(tuple(self.e.sprites[10]['pos']), (1.0, 0.0, 4.0))

    def test_color_alone_does_not_place(self):
        self.apply((12, [11, 5], []), (13, [0x100b], [1.0, 1.0, 1.0, 0.0]))
        self.assertIsNone(self.e.sprites[11]['pos'])                 # (the color is not proof of position: only the pose is)


if __name__ == '__main__':
    unittest.main(verbosity=1)
