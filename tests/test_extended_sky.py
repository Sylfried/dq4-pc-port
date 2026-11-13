"""Test of the sky copies of `dpout` and `ev09` (sky extended on both sides; pure logic: no window, no engine, no APK):

1. `title_sky.cloned_positions`: a numeric `dx` shifts x (title screen sky copies, as before); `('mirror', xe)` is a reflection across the plane x = xe (the edge points do not move, y and z untouched, reflection
   applied twice = identity), the original array is not modified, float32 preserved;
2. mirrored copy of a sky plane: it touches the original along its edge (no gap, no overlap) and the extended plane (left copy + original + right copy) covers three times its width, at the same depth;
3. `EXTENDED_SKIES`: `dpout` (plane `dpoutenk`) and `ev09` (plane `e9km1`); the title screen keeps its own treatment.

  python3 tests/test_extended_sky.py
"""
import os, sys, unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.render import title_sky as CT


def plan(xmin=-9.1, xmax=17.9, y0=0.0, y1=10.0, z=2.4):
    """Typical sky plane (two triangles; not the real geometry, only its shape: a vertical rectangle)."""
    return np.array([[xmin, y0, z], [xmin, y1, z], [xmax, y1, z], [xmin, y0, z], [xmax, y1, z], [xmax, y0, z]], np.float32)


class ClonePositions(unittest.TestCase):
    def test_offset_by_a_number(self):
        p = plan(); q = CT.cloned_positions(p, 5.0)
        np.testing.assert_allclose(q[:, 0], p[:, 0] + 5.0, atol=1e-6)
        np.testing.assert_array_equal(q[:, 1:], p[:, 1:])

    def test_mirror_keeps_edge(self):
        p = plan(); xe = float(p[:, 0].min()); q = CT.cloned_positions(p, ('mirror', xe))
        np.testing.assert_allclose(q[p[:, 0] == xe, 0], xe, atol=1e-6)         # the edge points do not move
        np.testing.assert_allclose(q[:, 0], 2 * xe - p[:, 0], atol=1e-5)
        np.testing.assert_array_equal(q[:, 1:], p[:, 1:])

    def test_mirror_twice_gives_origin(self):
        p = plan(); xe = 3.7
        np.testing.assert_allclose(CT.cloned_positions(CT.cloned_positions(p, ('mirror', xe)), ('mirror', xe)), p, atol=1e-5)

    def test_intact_origin_and_float32(self):
        p = plan(); copied = p.copy()
        for dx in (4.0, ('mirror', 1.0)):
            q = CT.cloned_positions(p, dx); self.assertEqual(q.dtype, np.float32)
            np.testing.assert_array_equal(p, copied)


class ExtendedPlane(unittest.TestCase):
    def test_three_widths_without_gap_or_overlap(self):
        p = plan(); xmin, xmax = float(p[:, 0].min()), float(p[:, 0].max()); wid = xmax - xmin
        g = CT.cloned_positions(p, ('mirror', xmin)); d = CT.cloned_positions(p, ('mirror', xmax))
        self.assertAlmostEqual(float(g[:, 0].max()), xmin, places=4)                  # the left copy ends where the original begins
        self.assertAlmostEqual(float(d[:, 0].min()), xmax, places=4)                  # the right copy begins where it ends
        self.assertAlmostEqual(float(g[:, 0].min()), xmin - wid, places=4)
        self.assertAlmostEqual(float(d[:, 0].max()), xmax + wid, places=4)
        np.testing.assert_array_equal(g[:, 2], p[:, 2]); np.testing.assert_array_equal(d[:, 2], p[:, 2])       # same depth: no tilted plane


class MovingPlane(unittest.TestCase):
    """The sky plane of `ev09` SCROLLS (FPMV movement: from +9.0 to 0.0 in 900 steps, looping). The copies must follow it."""

    def test_the_copies_follow_the_plane(self):
        p = plan()
        for d in (0.0, 1.5, 4.0, 9.0, -3.0):
            moved = p.copy(); moved[:, 0] += d
            xmin, xmax = float(moved[:, 0].min()), float(moved[:, 0].max())
            g = CT.cloned_positions(moved, ('mirror', 'min')); dr = CT.cloned_positions(moved, ('mirror', 'max'))
            self.assertAlmostEqual(float(g[:, 0].max()), xmin, places=4, msg='offset %s: the left copy still touches the original' % d)
            self.assertAlmostEqual(float(dr[:, 0].min()), xmax, places=4, msg='offset %s: the right copy too' % d)

    def test_a_frozen_axis_would_tear_the_sky(self):
        """The cause, kept in memory: with the axis frozen at load, the gap equals 2 times the displacement."""
        p = plan(); frozen = float(p[:, 0].min())
        moved = p.copy(); moved[:, 0] += 4.0
        bad = CT.cloned_positions(moved, ('mirror', frozen))                          # old behaviour: the x coordinate, not the side
        self.assertAlmostEqual(float(moved[:, 0].min()) - float(bad[:, 0].max()), 8.0, places=4)      # un trou de 2 d
        good = CT.cloned_positions(moved, ('mirror', 'min'))
        self.assertAlmostEqual(float(moved[:, 0].min()) - float(good[:, 0].max()), 0.0, places=4)     # plus de trou

    def test_the_side_is_read_on_the_current_vertices(self):
        p = plan()
        for side, edge in (('min', float(p[:, 0].min())), ('max', float(p[:, 0].max()))):
            q = CT.cloned_positions(p, ('mirror', side))
            np.testing.assert_allclose(q[:, 0], 2.0 * edge - p[:, 0], atol=1e-5)
            np.testing.assert_array_equal(q[:, 1:], p[:, 1:])

    def test_a_number_still_means_an_axis(self):
        p = plan()
        np.testing.assert_allclose(CT.cloned_positions(p, ('mirror', 3.0))[:, 0], 6.0 - p[:, 0], atol=1e-5)

    def test_the_viewer_asks_for_the_side(self):
        import ast
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dq4_pc', 'window', 'title_screen.py')
        src = open(path, encoding='utf-8').read()                       # (read as text: importing the module needs a display, the CI has none)
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == '_extended_sky']
        self.assertEqual(len(fn), 1); self.assertIn("('mirror', side)", ast.get_source_segment(src, fn[0]))


class Constants(unittest.TestCase):
    def test_maps_and_planes(self):
        from dq4_pc.window import constants as C
        self.assertEqual(C.EXTENDED_SKIES['dpout'], ('dpoutenk',))
        self.assertEqual(C.EXTENDED_SKIES['ev09'], ('e9km1',))
        self.assertNotIn(C.TITLE_MAP, C.EXTENDED_SKIES)             # the title has its own sky (`_title_sky`)


if __name__ == '__main__':
    unittest.main(verbosity=2)
