"""Test of the pure logic of the title screen sky in wide format (`dq4_pc/title_sky.py`: without a window, without the engine, without an APK):

1. portrait area (middle 9:16 column): 1280 x 720 -> 405 px wide, centered; 720 x 1280 -> whole window; normalized half-width;
2. texture deformation: G(0) = 0, slope 1 at the edge, slope always between 0.52 and 1.48 (never a flip), overall scale preserved, deterministic, different on the left and on the right,
   and the pattern does not come back identical one tile further (that is the whole point: "the repetitive pattern is too visible");
3. analysis of the "kumo" object (rebuilt here identically: 4 rows of 3 tiles of 11.5, shifted by half a tile): rows, period, exact u, rejection of unexpected structures;
4. bands: no vertex in the portrait area (the original sky stays intact there), continuous join at the edge (u and v of the original sky, at any scroll position), same vertices / colors as the rows,
   same triangle winding direction as the original quadrilaterals, nothing to add in portrait, more bands as the window widens.

5. trial (enlarged sky instead of bands): `screen_zoom` (1 in portrait, 16/9: x 3.16, 21/9: x 4.15, `DQ_SKY_ZOOM` forces a value) and `zoom_matrix` (screen x and y multiplied, depth intact): the whole
   window then shows only the width of the original portrait area, so less than one tile;
6. flat rendering (the default, now DQ_SKY_FLAT=1): the texture at the window height (v from 0.998 to 0.002 over the whole height, at any format), repeated across the width (u extends over `aspect` tiles), wave effect (`stretch_plate`,
   `flat_sliding`) fixed on screen and never flipped, scrolling = shift of u only, color gradient of the original rows (`screen_gradient`), all triangles in the same direction, with no holes.

7. (default): the base sky in the portrait area, bands that continue it exactly, each side's variant of the tile laid over them from the edge (TestBaseSky).

  python3 tests/test_title_sky.py
"""
import math, os, sys, unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.render import title_sky as CT


def matrix(cam, target, fov, aspect, n=1.0, f=200.0, topmost=(0, 1, 0)):
    """Same form as `window.matrix` (rewritten here: no pyglet)."""
    pos = np.array(cam, float); fw = np.array(target, float) - pos; fw /= np.linalg.norm(fw)
    right = np.cross(topmost, fw); right /= np.linalg.norm(right); topmost = np.cross(fw, right)
    th = math.tan(math.radians(fov) / 2)
    M = np.zeros((4, 4))
    M[0, :3] = right / (th * aspect); M[0, 3] = -pos @ right / (th * aspect)
    M[1, :3] = topmost / th; M[1, 3] = -pos @ topmost / th
    k = (f + n) / (f - n)
    M[2, :3] = fw * k; M[2, 3] = -pos @ fw * k - 2 * f * n / (f - n)
    M[3, :3] = fw; M[3, 3] = -pos @ fw
    return M


def camera_title(aspect):
    """Title camera as the port computes it (values read from the engine at frame 400: position (0, 27.70, -34.18), target (0, 0, 0), fov 10, pitch 3.019; SceneCamera.Update)."""
    pos, target_pos = np.array([0.0, 27.7041015625, -34.181640625]), np.zeros(3)
    th_v = math.tan(math.radians(10.0 * 4.0 / 3.0) / 2) / CT.ASPECT_PORTRAIT
    fw = target_pos - pos; fw /= np.linalg.norm(fw)
    yaw = math.atan2(fw[0], fw[2]); tang = math.asin(-fw[1]) - math.radians(3.019360065460205)
    fw = np.array([math.sin(yaw) * math.cos(tang), -math.sin(tang), math.cos(yaw) * math.cos(tang)])
    pos = pos + fw * 4.0
    return matrix(pos, pos + fw * 10, math.degrees(2 * math.atan(th_v)), aspect, n=1.0, f=150.0)


def synthetic_sky():
    """Vertices (positions, uv, colors) of the title sky (object 000_kumo2): 4 rows (y, z, vertex color as in the original), 3 tiles of 11.5 per row split into two quadrilaterals of 5.75,
    u from 0.002 to 0.998 across the tile; two rows out of four are shifted by half a tile (u of 0.502 first)."""
    whitelist, tint = (1.0, 1.0, 1.0, 1.0), (1.0, 0.796, 0.6, 1.0)
    lines = [(-33.56, 10.10, tint, -22.75, 14.03, whitelist, 1), (-22.75, 14.03, whitelist, -11.95, 17.97, whitelist, 0), (-11.95, 17.97, whitelist, -1.14, 21.90, tint, 1), (-1.14, 21.90, tint, 9.67, 25.83, tint, 0)]
    P, U, C = [], [], []
    for yb, zb, cb, yh, zh, ch, dec in lines:
        for k in range(6):
            xg = -12.75 + 5.75 * k; xd = xg + 5.75
            half = (k + dec) % 2
            ug, ud = (0.002, 0.502) if half == 0 else (0.502, 0.998)
            for (x, y, z, u, v, c) in ((xg, yb, zb, ug, 0.998, cb), (xg, yh, zh, ug, 0.002, ch), (xd, yh, zh, ud, 0.002, ch), (xg, yb, zb, ug, 0.998, cb), (xd, yh, zh, ud, 0.002, ch), (xd, yb, zb, ud, 0.998, cb)):
                P.append((x, y, z)); U.append((u, v)); C.append(c)
    return np.array(P, np.float32), np.array(U, np.float32), np.array(C, np.float32)


def ndc_x(M, p):
    c = M @ np.array([p[0], p[1], p[2], 1.0]); return c[0] / c[3]


def area(p):
    """Signed area (in the x, y plane) of a triangle of 3 points."""
    return (p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1])


class TestZonePortrait(unittest.TestCase):
    def test_zone(self):
        x0, w = CT.zone_portrait(1280, 720); self.assertAlmostEqual(w, 405.0); self.assertAlmostEqual(x0, 437.5)
        x0, w = CT.zone_portrait(720, 1280); self.assertEqual((x0, w), (0.0, 720.0))             # portrait window: everything is the area
        x0, w = CT.zone_portrait(1920, 820); self.assertAlmostEqual(w, 461.25); self.assertAlmostEqual(x0 + w / 2, 960.0)
        x0, w = CT.zone_portrait(1920, 400); self.assertAlmostEqual(w, 225.0)

    def test_half_ndc(self):
        self.assertAlmostEqual(CT.half_zone_ndc(16 / 9), 0.5625 / (16 / 9)); self.assertEqual(CT.half_zone_ndc(0.5625), 1.0); self.assertEqual(CT.half_zone_ndc(0.3), 1.0)
        x0, w = CT.zone_portrait(1280, 720); self.assertAlmostEqual(w / 1280, CT.half_zone_ndc(1280 / 720))        # same area in pixels and in screen coordinates (the area is 2 x half of the window width / 2)


class TestDeformation(unittest.TestCase):
    d = np.linspace(0.0, 80.0, 8001)

    def test_seam(self):
        for side in (0, 1):
            G, dv = CT.deformation(self.d, side); self.assertEqual(G[0], 0.0); self.assertEqual(dv[0], 0.0)
            self.assertAlmostEqual(float(G[1] / self.d[1]), 1.0, places=3); self.assertLess(abs(dv[1]), 1e-6)       # slope 1 and zero slide with zero slope at the edge of the area: join with no break

    def test_bounded_slope(self):
        for side in (0, 1):
            G, _ = CT.deformation(self.d, side); p = np.diff(G) / np.diff(self.d)
            self.assertGreater(p.min(), 1 - 0.48 - 0.01); self.assertLess(p.max(), 1 + 0.48 + 0.01)       # never a flip of the pattern, stretch from 0.52 to 1.48 at most

    def test_overall_scale(self):
        for side in (0, 1):
            G, _ = CT.deformation(self.d, side); self.assertLess(abs(G[-1] / self.d[-1] - 1.0), 0.03)       # same scale as the original on average

    def test_deterministic_and_independent_of_array(self):
        a = CT.deformation(np.array([3.0, 17.5, 40.0]), 0); b = CT.deformation(self.d, 0)
        for k in (0, 1): self.assertAlmostEqual(float(a[k][1]), float(np.interp(17.5, self.d, b[k])), places=3)
        self.assertTrue(all(np.array_equal(x, y) for x, y in zip(CT.deformation(self.d, 1), CT.deformation(self.d, 1))))

    def test_different_sides(self):
        (g0, v0), (g1, v1) = CT.deformation(self.d, 0), CT.deformation(self.d, 1)
        self.assertGreater(np.abs(g0 - g1).max(), 0.5); self.assertGreater(np.abs(v0 - v1).max(), 0.02)                                                  # no left / right symmetry

    def test_pattern_does_not_return_identical(self):
        """One tile (11.5) further, the pattern is read at a different texture abscissa: without the stretch G(d + 11.5) - G(d) = 11.5 everywhere (exact repetition)."""
        P = 11.5; i = self.d <= 60.0
        for side in (0, 1):
            G, _ = CT.deformation(self.d, side); spacing = np.interp(self.d[i] + P, self.d, G) - G[i] - P
            self.assertGreater(np.abs(spacing).max(), 1.0)                                                 # difference of more than a tenth of a tile in several places
            self.assertGreater((np.abs(spacing) > 0.4).mean(), 0.5)                                       # and almost everywhere: the pattern is shifted by at least 3% of a tile over more than half of the band


class TestAnalysis(unittest.TestCase):
    def test_rows(self):
        r = CT.analyze(*synthetic_sky())
        self.assertEqual(len(r), 4)
        for ra in r:
            self.assertAlmostEqual(ra.period, 11.5, places=3); self.assertEqual(len(ra.quads), 6); self.assertAlmostEqual(ra.rate, 0.996 / 11.5, places=3)
        self.assertEqual([round(ra.bottom[0], 2) for ra in r], [-33.56, -22.75, -11.95, -1.14])           # sorted from bottom to top
        self.assertAlmostEqual(r[1].topmost[0], r[2].bottom[0], places=2)                                    # contiguous rows

    def test_u_exact(self):
        P, U, C = synthetic_sky(); r = CT.analyze(P, U, C)
        # u(x) = that of the row's quadrilaterals, everywhere in the object, and it repeats beyond
        for ra in r:
            for xg, xd, ug, ud in ra.quads:
                for f in (0.0, 0.25, 0.5, 0.9):
                    x = xg + f * (xd - xg); self.assertAlmostEqual(float(ra.u(x)), ug + f * (ud - ug), places=6)
                    self.assertAlmostEqual(float(ra.u(x + 11.5 * 4)), ug + f * (ud - ug), places=5); self.assertAlmostEqual(float(ra.u(x - 11.5 * 3)), ug + f * (ud - ug), places=5)
        self.assertNotAlmostEqual(float(r[0].u(0.0)), float(r[1].u(0.0)), places=2)                      # rows shifted by half a tile

    def test_colors_and_edges(self):
        r = CT.analyze(*synthetic_sky())
        self.assertEqual(tuple(np.round(r[0].bottom[3], 3)), (1.0, 0.796, 0.6, 1.0)); self.assertEqual(tuple(r[0].topmost[3]), (1.0, 1.0, 1.0, 1.0))
        self.assertAlmostEqual(r[0].bottom[2], 0.998, places=3); self.assertAlmostEqual(r[0].topmost[2], 0.002, places=3)
        self.assertAlmostEqual(r[0].bottom[1], 10.10, places=2); self.assertAlmostEqual(r[0].topmost[1], 14.03, places=2)

    def test_unexpected_structure(self):
        P, U, C = synthetic_sky()
        for args in ((P[:-1], U[:-1], C[:-1]), (P[:0], U[:0], C[:0])):
            with self.assertRaises(ValueError): CT.analyze(*args)
        P2 = P.copy(); P2[1, 0] += 0.5                                                                  # vertex outside the alignment of the quadrilaterals
        with self.assertRaises(ValueError): CT.analyze(P2, U, C)
        U2 = U.copy(); U2[12:, 0] = 0.3                                                                 # non-periodic pattern
        with self.assertRaises(ValueError): CT.analyze(P, U2, C)


class TestBaseSky(unittest.TestCase):
    """(default): the original sky at the height meant for a 16:9 portrait screen, placed in the middle of the 16:9 landscape window, its left and right sides
    extended by continuing the animation smoothly (not a plain copy). The portrait area keeps the original sky (the title camera already has the
    phone's whole height); the bands continue it EXACTLY (no stretch, no slide: the original's own u and v), and each side's variant of the tile (variant_tile) is laid over them with an alpha that
    rises from 0 at the edge of the area: no seam at the edge, the sides no longer repeat the middle."""
    def setUp(self):
        self.P, self.U, self.C = synthetic_sky(); self.sky = CT.WideSky(self.P, self.U, self.C, deform=False)

    def test_bands_continue_the_original_exactly(self):
        asp = 16 / 9; M = camera_title(asp)
        for phi in (0.0, -2.3, -11.0):
            P, U, C = self.sky.bands(M, asp, phi)
            for a, z, ri, xs in self.sky._ref:
                ra = self.sky.rows[ri]; Pb, Ub = P[a:z], U[a:z]
                du = Ub[:, 0] - ra.u(Pb[:, 0] - phi)
                self.assertLess(np.abs(du - np.round(du)).max(), 0.01)                                   # (u of the original at every point, up to whole tiles: the texture repeats; its 1-texel margins aside)
                v0, v1 = sorted((ra.bottom[2], ra.topmost[2])); self.assertTrue(((Ub[:, 1] >= v0 - 1e-6) & (Ub[:, 1] <= v1 + 1e-6)).all())       # (no vertical slide)

    def test_side_layers_rise_from_the_edge(self):
        asp = 16 / 9; M = camera_title(asp); P, U, C = self.sky.bands(M, asp, -1.0)
        layers = self.sky.side_layers(C)
        self.assertEqual(sorted(l[0] for l in layers), [0, 1])
        zb, zh, eb, eh = CT.zone_edges(M, self.sky.rows, CT.half_zone_ndc(asp), self.sky.x_mil)
        for side, a, z, cc in layers:
            x = P[a:z, 0]; d = (zb - x) if side == 0 else (x - zh); al = cc[:, 3] / np.maximum(C[a:z, 3], 1e-9)
            self.assertTrue(np.allclose(al[np.isclose(d, 0.0, atol=1e-4)], 0.0))                       # (at the edge: the original alone)
            self.assertTrue(np.allclose(al[d >= CT.VARIANT_RAMP * self.sky.period], 1.0))               # (beyond the ramp: the variant alone)
            o = np.argsort(d); self.assertTrue((np.diff(al[o]) >= -1e-6).all())                          # (never back down)
            np.testing.assert_allclose(cc[:, :3], C[a:z, :3])                                             # (the rows' colors kept)

    def test_variant_tile(self):
        rng = np.random.default_rng(3); h, w = 64, 64
        yy, xx = np.mgrid[0:h, 0:w]
        T = np.zeros((h, w, 4), np.uint8); T[..., 3] = 255
        T[..., 0] = (127 + 100 * np.sin(2 * np.pi * xx / w) * np.cos(2 * np.pi * yy / h)).astype(np.uint8); T[..., 1] = (rng.random((h, w)) * 255).astype(np.uint8); T[..., 2] = 90
        A, B = (CT.variant_tile(T, s) for s in CT.VARIANT_SEEDS)
        self.assertEqual(A.shape, T.shape); self.assertTrue((A[..., 3] == 255).all())
        self.assertFalse(np.array_equal(A, B)); self.assertGreater(np.abs(A[h // 2].astype(int) - T[h // 2].astype(int)).mean(), 5)   # (different from the tile, and from each other)
        np.testing.assert_allclose(A[0], T[0], atol=2); np.testing.assert_allclose(A[-1], T[-1], atol=2)          # (top and bottom rows: the original's, the sky rows meet there)
        self.assertTrue(np.array_equal(CT.variant_tile(T, 11), A))                                    # (deterministic)
        self.assertLess(abs(A[..., :3].astype(float).std() - T[..., :3].astype(float).std()), 0.25 * T[..., :3].astype(float).std())   # (contrast kept: no washed-out blend)


class TestBands(unittest.TestCase):
    def setUp(self):
        self.P, self.U, self.C = synthetic_sky(); self.sky = CT.WideSky(self.P, self.U, self.C)

    def test_portrait_nothing_to_add(self):
        self.assertIsNone(self.sky.bands(camera_title(0.5625), 0.5625, 0.0)); self.assertIsNone(self.sky.bands(camera_title(0.4), 0.4, 0.0))

    def test_intact_zone(self):
        """No point of the portrait area (|screen x| <= half, within the field) is covered by a band: we project the triangles and test a grid of the area."""
        for asp in (16 / 9, 21 / 9, 32 / 9):
            M = camera_title(asp); half = CT.half_zone_ndc(asp)
            P, U, C = self.sky.bands(M, asp, 0.0)
            self.assertEqual(len(P) % 6, 0)
            ex = M @ np.c_[P, np.ones(len(P))].T; xs = ex[0] / ex[3]; ys = ex[1] / ex[3]
            visible_ones = np.abs(ys) <= 1.0
            self.assertGreater(np.abs(xs[visible_ones]).min(), half - 0.15, 'asp %.2f: band too close to the edge of the area' % asp)           # band vertices: outside the area, to within the margin of the slanted rows
            for ra in self.sky.rows:                                                               # points of the area on the row, from bottom to top: their world abscissa is between the bands
                b = CT.zone_edges(M, self.sky.rows, half, self.sky.x_mil)
                self.assertIsNotNone(b)
                zb, zh, eb, eh = b
                self.assertLess(eb, zb); self.assertLess(zh, eh)
                for t in np.linspace(0, 1, 9):
                    y = ra.bottom[0] + t * (ra.topmost[0] - ra.bottom[0]); z = ra.bottom[1] + t * (ra.topmost[1] - ra.bottom[1])
                    for xn in np.linspace(-half, half, 7):
                        # world abscissa that projects to xn (bisection): must be in [zb, zh]
                        lo, hi = -80.0, 80.0
                        for _ in range(60):
                            mid = (lo + hi) / 2
                            if ndc_x(M, (mid, y, z)) < xn: lo = mid
                            else: hi = mid
                        c = M @ np.array([lo, y, z, 1.0])
                        if abs(c[1] / c[3]) <= 1.0: self.assertTrue(zb - 1e-3 <= lo <= zh + 1e-3, (asp, t, xn, lo, zb, zh))

    def test_seam_at_edge(self):
        """Vertices of each band at the edge of the area: u = that of the original sky at this abscissa (shifted by the object's scrolling), v = that of the row's edge, at any scroll position."""
        asp = 16 / 9; M = camera_title(asp)
        zb, zh, eb, eh = CT.zone_edges(M, self.sky.rows, CT.half_zone_ndc(asp), self.sky.x_mil)
        for phi in (0.0, -0.0192 * 100, -5.77, -11.49):
            P, U, C = self.sky.bands(M, asp, phi)
            for start_idx, end, ri, xs in self.sky._ref:                                                    # each band (row, side) has its own vertices (neighboring rows share a y, z edge)
                ra = self.sky.rows[ri]; Pb, Ub = P[start_idx:end], U[start_idx:end]
                for y, z, v in ((ra.bottom[0], ra.bottom[1], ra.bottom[2]), (ra.topmost[0], ra.topmost[1], ra.topmost[2])):
                    m = np.isclose(Pb[:, 0], xs, atol=1e-3) & np.isclose(Pb[:, 1], y, atol=1e-4) & np.isclose(Pb[:, 2], z, atol=1e-4)
                    self.assertTrue(m.any()); self.assertIn(xs, (zb, zh))
                    self.assertTrue(np.allclose(Ub[m, 0], ra.u(xs - phi), atol=2e-4), (phi, xs, Ub[m, 0][:3], ra.u(xs - phi)))
                    self.assertTrue(np.allclose(Ub[m, 1], v, atol=1e-6))

    def test_scroll_follows_the_object(self):
        """Band positions and colors do not depend on the scrolling; their u depends on it by a constant shift per band (at the edge of the area the texture slides like the object: rate x dx)."""
        asp = 16 / 9; M = camera_title(asp)
        a = self.sky.bands(M, asp, 0.0); b = self.sky.bands(M, asp, -3.0)
        self.assertTrue(np.array_equal(a[0], b[0])); self.assertTrue(np.array_equal(a[2], b[2])); self.assertTrue(np.array_equal(a[1][:, 1], b[1][:, 1]))
        du = b[1][:, 0] - a[1][:, 0]
        for start_idx, end, ri, xs in self.sky._ref:
            self.assertLess(np.ptp(du[start_idx:end]), 1e-5)                                                  # identical shift over the whole band (one row, one side): the texture slides as a block
            att = 3.0 * self.sky.rows[ri].rate                                                      # the object's pattern advances by 3 units: u changes at a rate x 3 (modulo one tile, 0.996: the original u is folded into [0.002 ; 0.998])
            self.assertLess(abs((du[start_idx] - att + 0.498) % 0.996 - 0.498), 0.01)

    def test_colors_like_the_rows(self):
        asp = 16 / 9; P, U, C = self.sky.bands(camera_title(asp), asp, 0.0)
        for ra in self.sky.rows:
            bottom = np.isclose(P[:, 1], ra.bottom[0], atol=1e-4) & np.isclose(P[:, 2], ra.bottom[1], atol=1e-4)
            topmost = np.isclose(P[:, 1], ra.topmost[0], atol=1e-4) & np.isclose(P[:, 2], ra.topmost[1], atol=1e-4)
            self.assertTrue(np.allclose(C[bottom], ra.bottom[3], atol=1e-6)); self.assertTrue(np.allclose(C[topmost], ra.topmost[3], atol=1e-6))

    def test_triangle_winding(self):
        """All the band triangles turn in the same direction as those of the original sky (same visible face)."""
        asp = 21 / 9; P, U, C = self.sky.bands(camera_title(asp), asp, -2.0)
        s0 = {np.sign(area(self.P[i:i + 3, :2])) for i in range(0, len(self.P), 3)}
        s1 = {np.sign(area(P[i:i + 3, :2])) for i in range(0, len(P), 3)}
        self.assertEqual(len(s0), 1); self.assertEqual(s0, s1)

    def test_wider_more_bands(self):
        n = [len(self.sky.bands(camera_title(a), a, 0.0)[0]) for a in (16 / 9, 21 / 9, 32 / 9)]
        self.assertLess(n[0], n[1]); self.assertLess(n[1], n[2])
        a = self.sky.bands(camera_title(16 / 9), 16 / 9, 0.0)
        for t in a: self.assertTrue(np.isfinite(t).all())

    def test_covers_whole_window(self):
        """At each screen abscissa (outside the area) and each visible height, the sky point is covered by a band: the extent of the bands goes beyond the window edge."""
        for asp in (16 / 9, 21 / 9, 32 / 9):
            M = camera_title(asp); P, U, C = self.sky.bands(M, asp, 0.0)
            b = CT.zone_edges(M, self.sky.rows, CT.half_zone_ndc(asp), self.sky.x_mil); zb, zh, eb, eh = b
            self.assertLessEqual(P[:, 0].min(), eb - 0.5 * self.sky.step); self.assertGreaterEqual(P[:, 0].max(), eh + 0.5 * self.sky.step)

    def test_seams_between_rows_intact(self):
        """The vertical slide is zero at the top / bottom edges of each row (they read the texture from v = 0 to 1 like the original: otherwise a visible seam between the rows shifted by half a tile) and acts inside."""
        asp = 21 / 9; P, U, C = self.sky.bands(camera_title(asp), asp, 0.0); interior = 0.0
        for start_idx, end, ri, xs in self.sky._ref:
            ra = self.sky.rows[ri]; Pb, Ub = P[start_idx:end], U[start_idx:end]
            bottom = np.isclose(Pb[:, 1], ra.bottom[0], atol=1e-4) & np.isclose(Pb[:, 2], ra.bottom[1], atol=1e-4)
            topmost = np.isclose(Pb[:, 1], ra.topmost[0], atol=1e-4) & np.isclose(Pb[:, 2], ra.topmost[1], atol=1e-4)
            self.assertTrue(np.allclose(Ub[bottom, 1], ra.bottom[2], atol=1e-5)); self.assertTrue(np.allclose(Ub[topmost, 1], ra.topmost[2], atol=1e-5))
            mil = ~(bottom | topmost); interior = max(interior, float(np.abs(Ub[mil, 1] - np.interp(Pb[mil, 1], [ra.bottom[0], ra.topmost[0]], [ra.bottom[2], ra.topmost[2]])).max()))
        self.assertGreater(interior, 0.015); self.assertLess(interior, 0.04)

    def test_cache_key(self):
        asp = 16 / 9; M = camera_title(asp)
        a = self.sky.bands(M, asp, 0.0); b = self.sky.bands(M, asp, 0.0); self.assertTrue(np.array_equal(a[1], b[1]))
        c = self.sky.bands(camera_title(21 / 9), 21 / 9, 0.0); self.assertNotEqual(len(a[0]), len(c[0]))


class TestScreenZoom(unittest.TestCase):
    def test_zoom_by_format(self):
        self.assertEqual(CT.screen_zoom(9 / 16), 1.0); self.assertEqual(CT.screen_zoom(0.4), 1.0)                  # portrait (or narrower): original sky, nothing to enlarge
        self.assertAlmostEqual(CT.screen_zoom(16 / 9), (16 / 9) / CT.ASPECT_PORTRAIT); self.assertAlmostEqual(CT.screen_zoom(16 / 9), 3.1605, 3)
        self.assertAlmostEqual(CT.screen_zoom(21 / 9), 4.148, 3)
        self.assertLess(CT.screen_zoom(16 / 10), CT.screen_zoom(16 / 9))                                              # the wider the window, the stronger the zoom

    def test_whole_window_fits_in_portrait_zone(self):
        for aspect in (16 / 9, 16 / 10, 21 / 9, 32 / 9):
            z = CT.screen_zoom(aspect); self.assertAlmostEqual(1.0 / z, CT.half_zone_ndc(aspect))              # the enlarged half-window = the original half portrait area: no horizontal repetition

    def test_trial_variable(self):
        old = os.environ.get('DQ_SKY_ZOOM')
        try:
            os.environ['DQ_SKY_ZOOM'] = '2.5'; self.assertEqual(CT.screen_zoom(16 / 9), 2.5)
            os.environ['DQ_SKY_ZOOM'] = '0.3'; self.assertEqual(CT.screen_zoom(16 / 9), 1.0)                  # (never a zoom out)
            os.environ['DQ_SKY_ZOOM'] = 'abc'; self.assertAlmostEqual(CT.screen_zoom(16 / 9), 3.1605, 3)      # unreadable value: normal computation
        finally:
            if old is None: os.environ.pop('DQ_SKY_ZOOM', None)
            else: os.environ['DQ_SKY_ZOOM'] = old

    def test_zoom_matrix(self):
        M = matrix((3.0, 5.0, -20.0), (3.0, 4.0, 0.0), 40.0, 16 / 9); Mz = CT.zoom_matrix(M, 3.0)
        p = np.array([2.0, 3.0, 4.0, 1.0]); h, hz = M @ p, Mz @ p
        self.assertAlmostEqual(hz[0], 3.0 * h[0]); self.assertAlmostEqual(hz[1], 3.0 * h[1])                    # screen x and y multiplied
        self.assertAlmostEqual(hz[2], h[2]); self.assertAlmostEqual(hz[3], h[3])                                # depth and w intact
        self.assertTrue(np.allclose(CT.zoom_matrix(M, 1.0), M))
        self.assertTrue(np.allclose(M, matrix((3.0, 5.0, -20.0), (3.0, 4.0, 0.0), 40.0, 16 / 9)))               # (M is not modified)


class TestFlatSky(unittest.TestCase):
    """Flat rendering: texture at the window height, repetition across the width, wave effect."""
    def test_flat_stretch(self):
        d = np.linspace(0.0, 12.0, 4801); G = CT.stretch_plate(d)
        self.assertAlmostEqual(float(G[0]), 0.0)                                                                  # G(0) = 0: no shift at the left edge
        slope = np.diff(G) / np.diff(d)
        self.assertGreater(slope.min(), 0.51); self.assertLess(slope.max(), 1.49)                                 # like the stretch of the bands: never a flip, 0.52 to 1.48
        self.assertLess(float(np.abs(G - d).max()), 0.75)                                                         # overall scale 1: the wave oscillates around the identity, with no drift
        self.assertAlmostEqual(float(G[-1] - d[-1]), float(G[0] - d[0]), delta=0.75)
        self.assertFalse(np.allclose(G[400:] - G[400], G[:-400] - G[0], atol=1e-3))                               # the pattern does not come back identical one tile further
        self.assertTrue(np.allclose(CT.stretch_plate(np.array([0.3, 1.7])), CT.stretch_plate(np.array([0.3, 1.7]))))    # deterministic

    def test_flat_sliding(self):
        d = np.linspace(0.0, 12.0, 1201); g = CT.flat_sliding(d)
        self.assertLessEqual(float(np.abs(g).max()), sum(a for a, _, _ in CT.SLIDE) + 1e-9)
        self.assertGreater(float(np.abs(g).max()), 0.01)                                                          # (the vertical wave exists)

    def test_texture_height_equals_window_height(self):
        for aspect in (16 / 9, 16 / 10, 21 / 9, 32 / 9, 4 / 3, 1.0, 9 / 16):
            P, U, C = CT.screen_sky(aspect, 0.0)
            self.assertAlmostEqual(float(P[:, 1].min()), -1.0); self.assertAlmostEqual(float(P[:, 1].max()), 1.0)    # the sky covers the whole height
            self.assertAlmostEqual(float(U[:, 1].max()), 0.998, 3); self.assertAlmostEqual(float(U[:, 1].min()), 0.002, 3)   # and the whole height of the texture (no extra zoom)
            self.assertGreaterEqual(float(P[:, 0].max()), 1.0 - 1e-6); self.assertAlmostEqual(float(P[:, 0].min()), -1.0)    # the whole width

    def test_repeat_happens_across_the_width(self):
        for aspect in (16 / 9, 21 / 9, 32 / 9, 4 / 3):
            P, U, C = CT.screen_sky(aspect, 0.0)
            left, right = U[P[:, 0] < -1.0 + 1e-6, 0], U[(P[:, 0] > 1.0 - 1e-6), 0]
            extent = float(right.max() - left.min())
            self.assertAlmostEqual(extent, aspect / CT.TILE_WIDTH, delta=0.8)                                  # ~ `aspect` tiles across the width (square texture), apart from the wave
            self.assertGreater(extent, 0.9 * aspect / CT.TILE_WIDTH - 0.5)
        P, U, C = CT.screen_sky(21 / 9, 0.0); P2, U2, C2 = CT.screen_sky(16 / 9, 0.0)
        self.assertGreater(float(U[:, 0].max() - U[:, 0].min()), float(U2[:, 0].max() - U2[:, 0].min()))          # the wider the window, the more the texture repeats (never stretched)
        P, U, C = CT.screen_sky(9 / 16, 0.0)
        self.assertLess(float(U[:, 0].max() - U[:, 0].min()), 1.0)                                                # portrait: less than one tile

    def test_scroll_shifts_only_u(self):
        P0, U0, C0 = CT.screen_sky(16 / 9, 0.0); P1, U1, C1 = CT.screen_sky(16 / 9, 0.37)
        self.assertTrue(np.array_equal(P0, P1)); self.assertTrue(np.allclose(C0, C1))                              # the wave is fixed on screen
        self.assertTrue(np.allclose(U0[:, 0] - U1[:, 0], 0.37, atol=1e-5)); self.assertTrue(np.array_equal(U0[:, 1], U1[:, 1]))
        P2, U2, _ = CT.screen_sky(16 / 9, 599.0)                                                                  # period 1 tile: (texture in REPEAT) nothing to realign
        self.assertTrue(np.allclose(U0[:, 0] - U2[:, 0], 599.0, atol=1e-3))

    def test_triangles_without_holes_and_same_winding(self):
        for aspect in (16 / 9, 21 / 9, 9 / 16):
            P, U, C = CT.screen_sky(aspect, 0.2)
            self.assertEqual(len(P) % 6, 0); self.assertEqual(P.shape[1], 3); self.assertEqual(U.shape, (len(P), 2)); self.assertEqual(C.shape, (len(P), 4))
            areas = np.array([area(P[i:i + 3]) for i in range(0, len(P), 3)])
            self.assertTrue((areas > 0).all() or (areas < 0).all())                                                # no flipped triangle
            self.assertAlmostEqual(float(np.abs(areas).sum()) / 2.0, (float(P[:, 0].max()) - float(P[:, 0].min())) * 2.0, places=3)   # total area = covered rectangle: no hole or overlap
            self.assertTrue(np.allclose(P[:, 2], CT.BACKGROUND_Z))                                                          # at the back

    def test_tint_gradient_of_original_rows(self):
        cl = CT.WideSky(*synthetic_sky()); M = camera_title(16 / 9)
        y, c = CT.screen_gradient(M, cl.rows, cl.x_mil)
        self.assertTrue((np.diff(y) > 0).all()); self.assertEqual(c.shape, (len(y), 4))                            # screen ordinates strictly increasing
        self.assertGreaterEqual(float(c.min()), 0.0); self.assertLessEqual(float(c.max()), 1.0 + 1e-6)
        green = c[:, 1]
        self.assertAlmostEqual(float(green[0]), 0.8, delta=0.05); self.assertAlmostEqual(float(green[-1]), 0.8, delta=0.05)    # orange at the bottom and top, like the original rows
        self.assertAlmostEqual(float(green.max()), 1.0, delta=1e-3)                                                    # white in the middle
        P, U, C = CT.screen_sky(16 / 9, 0.0, (y, c))
        expected = np.interp(P[:, 1], y, green)
        self.assertLess(float(np.abs(C[:, 1] - expected).max()), 0.03)                                                 # each vertex has the gradient color at its ordinate
        self.assertAlmostEqual(float(C[:, 1].max()), 1.0, delta=1e-3); self.assertLess(float(C[:, 1].min()), 0.85)    # white in the middle, orange at the top of the window
        _, _, C0 = CT.screen_sky(16 / 9, 0.0); self.assertTrue(np.allclose(C0, 1.0))                                  # no gradient: white

    def test_gradient_ignores_what_is_behind_camera(self):
        cl = CT.WideSky(*synthetic_sky()); M = camera_title(16 / 9).copy(); M[3] = [0.0, 0.0, 0.0, -1.0]          # w < 0 everywhere
        y, c = CT.screen_gradient(M, cl.rows, cl.x_mil)
        self.assertEqual(len(y), 2); self.assertTrue(np.allclose(c, 1.0))                                             # fallback: white gradient (never an error)


if __name__ == '__main__':
    unittest.main()
