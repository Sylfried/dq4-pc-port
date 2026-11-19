"""Seams of the town and battle scenery in the sharp modes ("None" and pixel perfect).

The scenery uv are texel CENTERS: each polygon of ground maps its texture from (0.5 / size) to (size - 0.5) / size (the DS data, adapted to the bilinear filtering of the
mobile game). Sampled sharp, as is, every polygon showed only half a texel along its edges: thin strips at each seam of the ground (Bastione castle courtyard). The fragment
program now works on the DS texel coordinate (uv * size - tshift, tshift = half an original texel): the polygon edges fall on texel borders and every texel is whole.

Each triangle's uv box (geometry shader, flat): the sample never leaves the polygon's own texels. A polygon whose edge lies on a texel border (the bed sheet: two mirrored halves
whose texel row 0 meets in the middle) blended the texel beyond it (the opposite edge of the texture, through Repeat) over one screen pixel: a thin line in the middle of every bed.

A point exactly on a texel border goes to the texel after it (TIE): polygons whose uv does not vary (the inner faces of the cave rocks, v = 0.5 / 64 everywhere: the black
bottom row) lie exactly on a border, and the soft sampling blended the two texels over the whole polygon (brown instead of black: the cave dab1 and about 250 other maps).

  python3 tests/test_scenery_texel_centers.py
"""
import os, sys, types, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.window import shaders as SH

N = 32                       # texture size (texels)
PIXELS = 32 * 6              # screen pixels across the polygon (texels magnified 6 times, as on a 1920 x 1200 screen)


def strict_texels(shift):
    """Texel index sampled at each pixel center across one polygon, with the strict nearest of FRAG (crisp > 1.5)."""
    x = (np.arange(PIXELS) + 0.5) / PIXELS
    uv = (0.5 + x * (N - 1)) / N                                   # uv interpolated from the first texel center to the last
    return np.floor(uv * N - shift).astype(int)


class Sampling(unittest.TestCase):
    def test_without_shift_half_texels_at_the_edges(self):
        widths = np.bincount(strict_texels(0.0))
        self.assertLess(widths[0], widths[1] * 0.75, 'half a texel at the edge: the seam lines')

    def test_with_shift_whole_texels(self):
        t = strict_texels(0.5); widths = np.bincount(t)
        self.assertEqual(t[0], 0)
        inner = widths[:-1]
        self.assertLessEqual(inner.max() - inner.min(), 1, 'every texel as wide as the others (to one pixel)')

    def test_program(self):
        self.assertIn('uniform vec2 tshift', SH.FRAG)
        self.assertIn('floor(uv * tsize - tshift + TIE)', SH.FRAG)
        self.assertIn('vec2 p = uv * tsize - tshift + TIE', SH.FRAG)
        self.assertIn('const float TIE = 1e-3', SH.FRAG)


def soft_weights(uv, size, shift, tie, w=1e-4):
    """Bilinear weights {texel: weight} that the soft sampling of FRAG (crisp 0.5 to 1.5) gives at one pixel; w = fwidth of the texel coordinate (1e-4: uv constant over the polygon)."""
    p = uv * size - shift + tie; b = np.floor(p + 0.5); x = b + np.clip((p - b) / w, -0.5, 0.5) - 0.5        # texel space of GL_LINEAR (texel centers on integers)
    i = int(np.floor(x)); f = x - i
    return {k % size: wt for k, wt in ((i, 1.0 - f), (i + 1, f)) if wt > 1e-9}


def boxed_weights(uv, size, shift, tie, box, w):
    """soft_weights with the polygon's uv box (lo, hi in uv): the sample is kept between the centers of the polygon's first and last texel (FRAG, v_box)."""
    p = uv * size - shift + tie; b = np.floor(p + 0.5); s = b + np.clip((p - b) / w, -0.5, 0.5)
    lo = box[0] * size - shift + 0.5; hi = max(box[1] * size - shift - 0.5, lo); x = min(max(s, lo), hi) - 0.5
    i = int(np.floor(x)); f = x - i
    return {k % size: wt for k, wt in ((i, 1.0 - f), (i + 1, f)) if wt > 1e-9}


class PolygonEdges(unittest.TestCase):
    def test_edge_on_a_border_is_not_blended(self):
        bed = (0.5 / 32, 20.5 / 32); near = 0.55 / 32                     # (the bed sheet: v from texel center 0 to 20; a pixel just inside the middle line)
        self.assertIn(31, soft_weights(near, 32, 0.5, 1e-3, w=0.4), 'before: the texel beyond the edge (row 31, through Repeat) blended in')
        self.assertEqual(boxed_weights(near, 32, 0.5, 1e-3, bed, 0.4), {0: 1.0})
        far = 20.45 / 32; self.assertEqual(boxed_weights(far, 32, 0.5, 1e-3, bed, 0.4), {19: 1.0}, 'the other edge: the last texel, not the one after')

    def test_inner_borders_still_softened(self):
        bed = (0.5 / 32, 20.5 / 32); mid = 10.5 / 32
        self.assertEqual(boxed_weights(mid, 32, 0.5, 1e-3, bed, 0.4), soft_weights(mid, 32, 0.5, 1e-3, w=0.4))
        self.assertEqual(len(boxed_weights(mid, 32, 0.5, 1e-3, bed, 0.4)), 2)

    def test_constant_uv_texel_after(self):
        self.assertEqual(boxed_weights(0.5 / 64, 64, 0.5, 1e-3, (0.5 / 64, 0.5 / 64), 1e-4), {0: 1.0})
        self.assertEqual(boxed_weights(10.5 / 64, 64, 0.5, 1e-3, (10.5 / 64, 10.5 / 64), 1e-4), {10: 1.0})

    def test_programs(self):
        self.assertIn('layout(triangles) in', SH.GEOMETRY); self.assertIn('flat out vec4 v_box', SH.GEOMETRY); self.assertIn('flat in vec4 v_box', SH.FRAG)
        self.assertIn('clamp(floor(uv * tsize - tshift + TIE) + 0.5, lo, hi)', SH.FRAG)
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dq456_pc', 'window', 'game.py'), encoding='utf-8').read()
        self.assertIn("Shader(GEOMETRY, 'geometry')", src)


class ConstantUv(unittest.TestCase):
    TIE = 1e-3

    def test_border_goes_to_the_texel_after_it(self):
        self.assertEqual(soft_weights(0.5 / 64, 64, 0.5, self.TIE), {0: 1.0}, 'v = 0.5 / 64 on the whole polygon: texel 0 alone, as the original samples it')
        self.assertEqual(soft_weights(10.5 / 64, 64, 0.5, self.TIE), {10: 1.0})

    def test_without_tie_half_and_half(self):
        self.assertEqual(soft_weights(0.5 / 64, 64, 0.5, 0.0), {63: 0.5, 0: 0.5}, 'the former sampling: texel 0 mixed with the opposite edge of the texture (Repeat)')

    def test_strict(self):
        for t in (0, 5, 63):
            self.assertEqual(np.floor((t + 0.5) / 64 * 64 - 0.5 + self.TIE), t)
            self.assertEqual(np.floor((t + 0.5) / 64 * 64 - 0.5 - 1e-6 + self.TIE), t, 'an interpolation error below the tie stays on the same texel')

    def test_ordinary_pixels_unchanged(self):
        self.assertEqual(soft_weights(3.2 / 64, 64, 0.5, self.TIE, w=0.2), soft_weights(3.2 / 64, 64, 0.5, 0.0, w=0.2), 'inside a texel: pure texel either way')


class Shift(unittest.TestCase):
    def test_half_original_texel(self):
        try: from dq456_pc.window.field import FieldMixin
        except Exception as ex: self.skipTest('window modules need pyglet: %s' % ex)
        f = types.SimpleNamespace(scenery_arr={'k': np.zeros((32, 64, 4), np.uint8)})
        sh = lambda key, w, h: FieldMixin._texel_center_shift(f, key, types.SimpleNamespace(width=w, height=h))
        self.assertEqual(sh('k', 64, 32), (0.5, 0.5))
        self.assertEqual(sh('k', 256, 128), (2.0, 2.0), 'softened battle texture enlarged 4 times: half an original texel = 2 of its texels')
        self.assertEqual(sh('other', 16, 16), (0.5, 0.5))


if __name__ == '__main__':
    unittest.main()
