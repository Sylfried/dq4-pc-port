"""Scenes composed for the phone's width (core/phone_scenes: DQ VI's prologue cliff and dragon flight): the phone's width in the window, the fading of the orthographic layer toward
the phone's edges, the blurred sides only during the map's camera movement (text of the window's code: the CI has no window).

    python3 tests/test_phone_scenes.py
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
from dq456_pc.core import phone_scenes as PS

HALF = 128.53125          # window/constants.ORTHO_HALF_WIDTH


def source(rel):
    with open(os.path.join(ROOT, 'dq456_pc', rel), encoding='utf-8') as f: return f.read()


class PhoneScenes(unittest.TestCase):
    def test_maps(self):
        self.assertTrue(PS.concerned('dq6', 'e01din2'))
        for game, m in (('dq6', 'e02din1'), ('dq5', 'e01din2'), ('dq4', 'e01din2'), ('dq6', None)): self.assertFalse(PS.concerned(game, m), (game, m))

    def test_column(self):
        self.assertAlmostEqual(PS.column(16 / 9), 0.5625)
        self.assertAlmostEqual(PS.column(1.6), 0.5625)                      # 16:10: the window shows more above and below, the phone's width stays 9/16 of its width
        self.assertAlmostEqual(PS.column(21 / 9), 9 / 21)
        self.assertGreaterEqual(PS.column(9 / 16), 1.0)                     # portrait window: nothing beside the phone

    def test_ortho_fade(self):
        self.assertEqual(PS.ortho_alpha(0.0, HALF), 1.0)
        self.assertEqual(PS.ortho_alpha(-0.6 * HALF, HALF), 1.0)
        self.assertEqual(PS.ortho_alpha(HALF, HALF), 0.0)
        self.assertEqual(PS.ortho_alpha(-1.3 * HALF, HALF), 0.0)
        xs = [HALF * k / 50.0 for k in range(60)]; al = [PS.ortho_alpha(x, HALF) for x in xs]
        self.assertTrue(all(a >= b for a, b in zip(al, al[1:])), 'decreasing toward the edge')
        self.assertLess(PS.ortho_alpha(118.0, HALF), 0.15, 'where the dragon of the second pass vanished: almost transparent')

    def test_window_code(self):
        b = source('window/backdrop.py')
        self.assertIn('PS.concerned(', b); self.assertIn('ob.camera_no or ob.key_view is not None', b); self.assertIn('stretch=False', b)
        s = source('render/screen_blur.py'); self.assertIn('uniform float stretch', s); self.assertIn("self.prog_sides['stretch']", s)
        m = source('window/battle_scene.py'); self.assertIn('PS.ortho_alpha(x, ORTHO_HALF_WIDTH)', m)


if __name__ == '__main__':
    unittest.main(verbosity=2)
