"""packet 15 (cmd_chara_shadow): bit 12 = shadow position (3 floats), bit 13 = opacity (1 float), bit 14 = shadow position on the world map (SetFieldShadowPosition, 3 floats).
The floats follow one another in this order: reading bit 14 without having removed that of bit 13 gave an offset. The balloon (packet 0x440c, [2495.97 ; 383.97 ; -1] for a sprite at (2496 ; 352)) has its shadow 32 pixels further south.
Without window or engine (unicorn alone for the import):    python3 tests/test_balloon_shadow.py"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE


def state_with(slot=12):
    e = ENGINE.State(); e.sprites[slot] = {'id': 4279, 'pos': (2496.0, 352.0, 20.0), 'col': (1, 1, 1, 1), 'pose': 0, 'dir': 0}
    return e


def packet(e, v, fl, slot=12):
    e.apply([(15, [v | slot], list(fl))], lambda *a: None); return e.sprites[slot]


class ShadowPacket(unittest.TestCase):
    def test_balloon(self):                                            # 0x440c: bits 10 (separate) and 14 (position on the map)
        s = packet(state_with(), 0x4400, [2495.97, 383.97, -1.0])
        self.assertEqual(s['shadow_field'], (2495.97, 383.97, -1.0)); self.assertTrue(s['shadow_separate']); self.assertNotIn('shadow_pos', s); self.assertNotIn('shadow_alpha', s)
        self.assertAlmostEqual(s['shadow_field'][1] - s['pos'][1], 32.0, delta=0.1)       # 2 tiles of 16 pixels to the south

    def test_opacity_then_position_on_map(self):               # bit 13: a float that must be removed before those of bit 14
        s = packet(state_with(), 0x6000, [0.5, 100.0, 200.0, -1.0])
        self.assertEqual((s['shadow_alpha'], s['shadow_field']), (0.5, (100.0, 200.0, -1.0)))

    def test_complete_order(self):                                     # bits 12, 13, 14
        s = packet(state_with(), 0x7000, [1.0, 2.0, 3.0, 0.25, 10.0, 20.0, 30.0])
        self.assertEqual((s['shadow_pos'], s['shadow_alpha'], s['shadow_field']), ((1.0, 2.0, 3.0), 0.25, (10.0, 20.0, 30.0)))

    def test_without_bit_14_nothing_changes(self):
        s = packet(state_with(), 0x2000, [0.5]); self.assertEqual(s['shadow_alpha'], 0.5); self.assertNotIn('shadow_field', s)
        s = packet(state_with(), 0x1000, [1.0, 2.0, 3.0]); self.assertEqual(s['shadow_pos'], (1.0, 2.0, 3.0)); self.assertNotIn('shadow_field', s)
        s = packet(state_with(), 0x100, []); self.assertTrue(s['shadow']); self.assertNotIn('shadow_field', s)

    def test_missing_floats(self):                               # truncated packet: no error, no invented position
        s = packet(state_with(), 0x4000, [1.0, 2.0]); self.assertNotIn('shadow_field', s)


if __name__ == '__main__': unittest.main(verbosity=1)
