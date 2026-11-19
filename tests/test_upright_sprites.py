"""Town sprites always upright on screen ("when my character goes up or down, the NPC sprites lean", without a window or the engine: `Game._town_camera` and `Game._town_panel` are called on a fake object):

1. the 4 corners of an NPC's panel, projected by the viewer's REAL matrix, give a rectangle with vertical left / right edges (bottom -> top deviation < 0.01 px) and a constant width / height
   ratio, at any screen position (top, bottom, left, right, corners, center) and in all camera states: fov, s_yOffset, height
   (mound: the camera rises with the ground), SetScale scale;
2. the edge correction touches NEITHER the depth (z-buffer, overlaps) NOR the on-screen position and height: same corner depths, same panel bottom, same top, as with the original panel;
   at the image center nothing changes (top center = original top center, same average width); elsewhere the WIDTH changes by construction (constant ratio 0.738 instead of 0.65 at the top to 0.81
   at the bottom of the screen for the original panel);
3. safeguard: the ORIGINAL panel (correction off) does lean by more than 8 degrees near the edges, so test 1 checks something;
4. tilt trial: with `inc` > 0 the panel is sheared toward the world vertical, feet fixed, size, depth and bottom position unchanged; its edge leans by atan(inc x tan(angle of a
   world vertical at the foot)); inc = 1: parallel to the walls; 0 BY DEFAULT ("put the NPC display back like the mobile version ... they stretch near the edge": a shear of 0.5 deformed the
   sprites; `Game._sprite_tilt`, variable DQ_SPRITE_TILT to try it): the edge correction alone (without shear) gives exactly vertical edges and the constant ratio (it is no longer the default: DQ_EDGE_CORRECTION=100);
5. finding (cause of the impression, see `Game._town_panel`): the WORLD VERTICALS (walls, doors) lean on screen depending on their position (vanishing point below the image, camera at 47 degrees), much more in 16/9 than
   on the original portrait, and this angle changes by several degrees when the hero goes up or down (the NPC changes height on screen) while the sprite itself stays at 0: the sprite seems to lean RELATIVE TO the neighboring walls.

6. ("go back to the raw NPC position, exactly as in the game ... with the new camera system they must not align if the camera is raised or lowered"): by default the panel is the game's (edge correction
   zero) and its coordinate frame (`Game._sprite_reference`) is that of the GAME's camera: Up / Down does not change it (identical corners in the world), Left / Right turn it face-on with the game's tilt;

  python3 tests/test_upright_sprites.py        (Linux without a screen: pyglet in "headless" mode)
"""
import itertools, math, os, sys, types, unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F
import test_town_camera as TC

ASPECT = 16.0 / 9.0
WIDTH, UP = 1280.0, 720.0
TARGET = np.array([20.0, 0.0, 30.0])
POSITIONS = list(itertools.product((-9.0, -4.5, 0.0, 4.5, 9.0), (-5.0, -2.0, 0.0, 3.0, 6.0, 9.0)))          # offset (x, z) of the NPC relative to the hero, in town units: from the bottom corner to a top corner of the screen
SAVESTATES = {'defaut': {}, 'yoff 0,05': dict(yoff=0.05), 'fov 10': dict(fov=10.0), 'fov 40': dict(fov=40.0), 'heros decale (5, -4)': dict(dec=(5.0, -4.0)), 'heros en hauteur': dict(hy=0.5), 'echelle 0,738': dict(k=0.738)}          # (no more yaw, angle or zoom: the camera is the game's)


def px(M, P):
    v = M @ np.array([P[0], P[1], P[2], 1.0]); return np.array([(v[0] / v[3] * 0.5 + 0.5) * WIDTH, (1.0 - (v[1] / v[3] * 0.5 + 0.5)) * UP])


def angle(bottom, topmost):
    """Tilt (degrees) of an edge on screen relative to the vertical; + = the top goes toward the right."""
    return math.degrees(math.atan2(topmost[0] - bottom[0], bottom[1] - topmost[1]))


def fake_game():
    j = TC.fake_game(); j.fixed_test = True          # fixed_test: one 1/60 s step per call, no clock
    return j


def mound_profile(topmost=0.5, climb_step=8, plateau=30):
    """Ground height under the hero, per engine step: ramp of `topmost` units over `climb_step` steps, plateau, symmetrical descent (the prologue village mound, map mlout1: +0.5 u in ~8 steps)."""
    mont = [topmost * (i + 1) / climb_step for i in range(climb_step)]
    return [0.0] * 10 + mont + [topmost] * plateau + mont[::-1][1:] + [0.0] * 3


def panel(j, e, foot, t, k=1.0, inc=0.0, lr=False):
    """(M, panel corners in the WORLD, camera coordinate frame, camera position) of an NPC whose feet are at `foot`, as `Game._draw` does (see the sprite loop)."""
    M, cam3d = F.Game._town_camera(j, e, ASPECT)
    r_, u_, f_ = cam3d; w, h = F.SPRITE_L * F.SPRITE_SCALE * k, F.SPRITE_H * F.SPRITE_SCALE * k
    zb, zh = 0.185 / 0.48 * w, (0.65 - 0.185) / 0.48 * w
    C = j._view_border[0]
    return M, F.Game._town_panel(j, np.array(foot, float), r_, u_, f_, w, h, zb, zb + zh, t, C, inc, lr), cam3d, C


def shape(M, q):
    """Tilt of the left and right edges (degrees), width / height ratio and corners in pixels (bottom left, bottom right, top right, top left)."""
    A, B, Cc, D = (px(M, p) for p in q)
    topmost = 0.5 * ((A[1] - D[1]) + (B[1] - Cc[1])); wid = 0.5 * ((B[0] - A[0]) + (Cc[0] - D[0]))
    return angle(A, D), angle(B, Cc), wid / topmost, (A, B, Cc, D)


def scenario(name_str, dx, dz, t, inc=0.0, lr=False):
    kw = SAVESTATES[name_str]; hero = TARGET + np.array([kw.get('dec', (0.0, 0.0))[0], kw.get('hy', 0.0), kw.get('dec', (0.0, 0.0))[1]])
    e = TC.fake_state(TARGET, hero, fov=kw.get('fov'), yoff=kw.get('yoff')); j = fake_game()
    for _ in range(3): F.Game._town_camera(j, e, ASPECT)                       # (the rest of the centering fades out: same state as after a few frames)
    return panel(j, e, hero + np.array([dx, 0.0, dz]), t, kw.get('k', 1.0), inc, lr), hero


class TestStraightSprites(unittest.TestCase):
    def test_vertical_edges_everywhere(self):
        worst = 0.0; r_min, r_max = 9.0, 0.0
        for name_str, (dx, dz) in itertools.product(SAVESTATES, POSITIONS):
            (M, q, _, _), _ = scenario(name_str, dx, dz, 1.0)
            g, d, ratio, (A, B, Cc, D) = shape(M, q)
            worst = max(worst, abs(D[0] - A[0]), abs(Cc[0] - B[0]), abs(A[1] - B[1]), abs(D[1] - Cc[1]))             # left / right edges vertical AND bottom / top edges horizontal (deviation in pixels)
            r_min, r_max = min(r_min, ratio), max(r_max, ratio)
        self.assertLess(worst, 0.01, 'the panel must be an upright rectangle on screen, at any position and for any camera')
        self.assertGreater(r_min, 0.730); self.assertLess(r_max, 0.745)                                              # constant proportion to +- 1% (0.72 x the height at the image center: 0.738 measured)

    def test_default_state_is_raw_panel(self):
        """("go back to the raw NPC position, exactly as in the game"): by default the edge correction is zero, and so is the shear: the panel is the game's, with no on-screen reconstruction.
        The old full correction (vertical edges, constant ratio) remains available through DQ_EDGE_CORRECTION / --edge-correction."""
        old = os.environ.pop('DQ_SPRITE_TILT', None); old_b = os.environ.pop('DQ_EDGE_CORRECTION', None)
        try:
            j0 = fake_game(); j0.args = types.SimpleNamespace(edge_correction=None); j0.SPRITE_TILT_DEFAULT = F.Game.SPRITE_TILT_DEFAULT
            self.assertEqual(F.EDGE_CORRECTION_DEFAULT, 0.0)
            self.assertEqual((F.Game._edge_correction(j0), F.Game._sprite_tilt(j0)), (0.0, 0.0))
            for val, att in (('100', 1.0), ('0', 0.0), ('40', 0.4), ('250', 1.0), ('-5', 0.0), ('abc', 0.0), ('', 0.0)):
                os.environ['DQ_EDGE_CORRECTION'] = val; self.assertAlmostEqual(F.Game._edge_correction(j0), att, 9, repr(val))
            os.environ.pop('DQ_EDGE_CORRECTION', None)
            j0.args = types.SimpleNamespace(edge_correction=100.0); self.assertEqual(F.Game._edge_correction(j0), 1.0)          # the command-line option wins
            # default panel (t = 0) = original panel: same corners as the direct computation of the offsets along the game camera's axis
            (M, q, cam3d, C), hero = scenario('defaut', 6.0, 3.0, 0.0)
            r_, u_, f_ = cam3d; w, h = F.SPRITE_L * F.SPRITE_SCALE, F.SPRITE_H * F.SPRITE_SCALE; zb, zt = 0.185 / 0.48 * w, 0.65 / 0.48 * w
            p = hero + np.array([6.0, 0.0, 3.0]); a, b = p - r_ * (w / 2), p + r_ * (w / 2)
            for x, y in zip(q, (a - f_ * zb, b - f_ * zb, b + u_ * h - f_ * zt, a + u_ * h - f_ * zt)): self.assertTrue(np.allclose(x, y))
        finally:
            for k, v in (('DQ_SPRITE_TILT', old), ('DQ_EDGE_CORRECTION', old_b)):
                if v is not None: os.environ[k] = v

    def test_left_right_option(self):
        """(always on in the game's drawing, Game._draw: `lr` True): the game's panel, with its top slid back sideways: the axis of the sprite stands vertical on screen at the left and right edges
        (top center above bottom center), while the heights, the depths, the bottom and the top widths and the vertical position stay the game's. At the center: no change."""
        for name_str, (dx, dz) in itertools.product(SAVESTATES, POSITIONS):
            (M, q, cam3d, C), _ = scenario(name_str, dx, dz, 0.0, 0.0, True); (_, q0, _, _), _ = scenario(name_str, dx, dz, 0.0)
            A, B, Cc, D = (px(M, x) for x in q); A0, B0, C0, D0 = (px(M, x) for x in q0)
            self.assertAlmostEqual((A[0] + B[0]) / 2, (Cc[0] + D[0]) / 2, delta=0.01)                                    # (vertical axis)
            for a, b in ((A, A0), (B, B0), (Cc, C0), (D, D0)): self.assertAlmostEqual(a[1], b[1], delta=0.01)          # (same heights on screen)
            self.assertAlmostEqual(Cc[0] - D[0], C0[0] - D0[0], delta=0.01); self.assertTrue(np.allclose(q[0], q0[0]) and np.allclose(q[1], q0[1]))
            r_, u_, f_ = cam3d
            for x, x0 in zip(q, q0): self.assertAlmostEqual(float((x - C) @ f_), float((x0 - C) @ f_), 9)              # (same depths)
        (M, q, _, _), _ = scenario('defaut', 0.0, 0.0, 0.0, 0.0, True); (_, q0, _, _), _ = scenario('defaut', 0.0, 0.0, 0.0)
        self.assertTrue(all(np.allclose(a, b, atol=1e-6) for a, b in zip(q, q0)))
        (M, q, _, _), _ = scenario('defaut', 9.0, 3.0, 0.0); g, d, _, _ = shape(M, q); self.assertGreater(abs(g), 3.0)                      # (without the option, the game's lean at the edge)

    def test_full_correction_state_vertical_edges_no_shear(self):
        """The full edge correction (DQ_EDGE_CORRECTION=100) always gives a straight rectangle on screen, at any camera."""
        worst = 0.0
        for name_str, (dx, dz) in itertools.product(SAVESTATES, POSITIONS):
            (M, q, _, _), _ = scenario(name_str, dx, dz, 1.0, 0.0); g, d, ratio, (A, B, Cc, D) = shape(M, q)
            worst = max(worst, abs(D[0] - A[0]), abs(Cc[0] - B[0]), abs(A[1] - B[1]), abs(D[1] - Cc[1])); self.assertAlmostEqual(ratio, 0.738, delta=0.008)
        self.assertLess(worst, 0.01)

    def test_mound_climb_and_descent(self):
        """Mound camera: the camera height follows the ground (CAM_Y_RELIEF) or lags (stairs); at each frame, an NPC at the left edge, the right edge and the top stays upright."""
        worst = 0.0; j = fake_game(); y_prev = None
        height_profile = mound_profile(0.5) + [0.5 + 0.1 * i for i in range(30)] + [3.5] * 20 + [3.5 - 0.1 * i for i in range(30)]          # mound, then a 3 u staircase climb and its descent
        for hy in height_profile:
            h = 0.047 + hy; hero = np.array([20.0, h, 30.0]); e = TC.fake_state((20.0, h - 0.047, 30.0), hero)
            for dx, dz in ((-9.0, 0.0), (9.0, -4.0), (0.0, 8.0), (-9.0, 9.0)):
                M, q, _, _ = panel(j, e, hero + np.array([dx, 0.0, dz]), 1.0)
                A, B, Cc, D = shape(M, q)[3]; worst = max(worst, abs(D[0] - A[0]), abs(Cc[0] - B[0]))
        self.assertLess(worst, 0.01)

    def test_depth_and_center_unchanged(self):
        """z-buffer (depth of each corner along the camera axis) and on-screen height unchanged; panel bottom identical; at the image center, top identical and average width identical."""
        center_pos = 0
        for name_str, (dx, dz) in itertools.product(('defaut', 'fov 40', 'heros en hauteur', 'echelle 0,738'), POSITIONS):
            (M, new_corners, cam3d, C), _ = scenario(name_str, dx, dz, 1.0); (_, ori, _, _), _ = scenario(name_str, dx, dz, 0.0)
            f_ = cam3d[2]
            for a, b in zip(new_corners, ori): self.assertAlmostEqual(float((a - C) @ f_), float((b - C) @ f_), 8, '%s (%s, %s) : profondeur d\'un coin' % (name_str, dx, dz))
            An, Bn, Cn, Dn = (px(M, p) for p in new_corners); Ao, Bo, Co, Do = (px(M, p) for p in ori)
            for a, b in ((An[1], Ao[1]), (Bn[1], Bo[1]), (Cn[1], Co[1]), (Dn[1], Do[1])): self.assertAlmostEqual(a, b, 6, '%s (%s, %s) : ordonnee a l\'ecran' % (name_str, dx, dz))
            self.assertAlmostEqual(0.5 * (An[0] + Bn[0]), 0.5 * (Ao[0] + Bo[0]), 6, 'bottom center unchanged')
            if dx == 0.0 and dz == 0.0:                                          # at the image center (the camera is centered on the hero: an NPC at the hero's feet is at the center, whatever the camera)
                center_pos += 1
                self.assertAlmostEqual(0.5 * (Cn[0] + Dn[0]), 0.5 * (Co[0] + Do[0]), 6, 'center of the picture: the top does not move')
                self.assertAlmostEqual(0.5 * ((Bn[0] - An[0]) + (Cn[0] - Dn[0])), 0.5 * ((Bo[0] - Ao[0]) + (Co[0] - Do[0])), delta=0.01 * (Bo[0] - Ao[0]), msg='centre de l\'image : largeur moyenne identique')
        self.assertEqual(center_pos, 4, 'un cas central par camera verifiee')

    def test_original_tilted_guard_rail(self):
        """Without the correction (original panel) the sprite leans by more than 8 degrees near the left / right edges of the 16/9: so test 1 does measure something; at the center it stays upright to within 1 degree."""
        (M, q, _, _), _ = scenario('defaut', 9.0, 0.0, 0.0); g, d, _, _ = shape(M, q); self.assertGreater(min(abs(g), abs(d)), 8.0)
        (M, q, _, _), _ = scenario('defaut', -9.0, 0.0, 0.0); g, d, _, _ = shape(M, q); self.assertGreater(min(abs(g), abs(d)), 8.0)
        (M, q, _, _), _ = scenario('defaut', 0.0, 0.0, 0.0); g, d, _, _ = shape(M, q); self.assertLess(max(abs(g), abs(d)), 1.0)

    @staticmethod
    def world_vertical(M, foot, h=1.44):
        return angle(px(M, foot), px(M, foot + np.array([0.0, h, 0.0])))

    def test_finding_world_verticals(self):
        """Cause of the impression: a world vertical (wall edge, door) 9 u from the hero leans on screen by 11 to 19 degrees depending on the screen height where it is (16/9, camera at 47 degrees), versus
        4 to 6.5 degrees on the original portrait; when the hero goes up or down the angle changes by more than 5 degrees, while the sprite stays at 0. (It is the perspective of the scenery, not the panel: see test 1.)"""
        def sweep(aspect):
            global WIDTH, UP
            WIDTH, UP = (1280.0, 720.0) if aspect > 1 else (450.0, 800.0)
            try:
                dx = -9.0 if aspect > 1 else -3.0; e = TC.fake_state(TARGET, TARGET); j = fake_game(); M, _ = F.Game._town_camera(j, e, aspect)
                return [self.world_vertical(M, TARGET + np.array([dx, 0.0, dz])) for dz in (-5.0, 9.0)]            # bottom of the screen, top of the screen
            finally: WIDTH, UP = 1280.0, 720.0
        bottom, topmost = sweep(16.0 / 9.0)
        self.assertLess(bottom, -17.0); self.assertGreater(topmost, -12.0); self.assertGreater(abs(bottom) - abs(topmost), 5.0)
        bottom, topmost = sweep(0.5625)
        self.assertLess(abs(bottom), 7.0); self.assertLess(abs(bottom) - abs(topmost), 3.0)

    def test_tilt_toward_world_vertical(self):
        """trial: with `inc`, the sprite's edge leans by atan(inc x tan(angle of the world vertical at the foot)) (to within 0.05 degree); inc = 1: parallel to the walls; the sprite and the wall then differ only by (1 - inc)
        times the initial gap; direction: the sprite leans to the same side as the wall; at the image center (straight world vertical) nothing changes; the left and right edges stay parallel."""
        worst = 0.0; read_value = 0
        for name_str, (dx, dz), inc in itertools.product(('defaut', 'fov 40', 'heros en hauteur', 'echelle 0,738'), POSITIONS, (0.3, 0.5, 0.7, 1.0)):
            (M, q, cam3d, C), hero = scenario(name_str, dx, dz, 1.0, inc); (_, q0, _, _), _ = scenario(name_str, dx, dz, 1.0, 0.0)
            g, d, _, (A, B, Cc, D) = shape(M, q); g0, d0, _, _ = shape(M, q0)
            foot_bottom = 0.5 * (np.array(q[0]) + np.array(q[1]))                              # middle of the bottom of the panel
            wall = self.world_vertical(M, foot_bottom)
            expected = math.degrees(math.atan(inc * math.tan(math.radians(wall))))
            worst = max(worst, abs(g - expected), abs(d - expected)); read_value += 1
            self.assertAlmostEqual(g, d, 5, '%s (%s, %s) tilt %s: the two edges are parallel' % (name_str, dx, dz, inc))
            self.assertAlmostEqual(g0, 0.0, 5)
            if abs(wall) > 2.0: self.assertGreater(g * wall, 0.0, '%s (%s, %s): same direction as the wall' % (name_str, dx, dz))
            if inc == 1.0: self.assertAlmostEqual(g, wall, delta=0.05, msg='inc = 1 : parallele au mur')
            if dx == 0.0 and dz == 0.0 and name_str == 'defaut': self.assertLess(abs(g), 0.5, 'au centre de l\'image rien ne change')
        self.assertLess(worst, 0.05); self.assertEqual(read_value, 4 * len(POSITIONS) * 4)

    def test_tilt_changes_neither_size_nor_depth(self):
        """Pure shear, feet fixed: panel bottom, on-screen height and width, depth of each corner (z-buffer) = those of `inc` = 0."""
        for name_str, (dx, dz), inc in itertools.product(('defaut', 'fov 40', 'heros en hauteur', 'echelle 0,738'), POSITIONS, (0.5, 1.0)):
            (M, a, cam3d, C), _ = scenario(name_str, dx, dz, 1.0, inc); (_, b, _, _), _ = scenario(name_str, dx, dz, 1.0, 0.0); f_ = cam3d[2]
            for u, v in zip(a, b): self.assertAlmostEqual(float((u - C) @ f_), float((v - C) @ f_), 8, '%s (%s, %s) inc %s : profondeur d\'un coin' % (name_str, dx, dz, inc))
            Pa = [px(M, p) for p in a]; Pb = [px(M, p) for p in b]
            for i in range(4): self.assertAlmostEqual(Pa[i][1], Pb[i][1], 6, 'on-screen y of corner %d' % i)
            for i in (0, 1): self.assertAlmostEqual(Pa[i][0], Pb[i][0], 6, 'the feet do not move')
            self.assertAlmostEqual(Pa[1][0] - Pa[0][0], Pb[1][0] - Pb[0][0], 6, 'width of the bottom')
            self.assertAlmostEqual(Pa[2][0] - Pa[3][0], Pb[2][0] - Pb[3][0], 6, 'width of the top')

    def test_climb_and_descent_minus_offset_with_wall(self):
        """Finding: an NPC at the left edge, when the hero goes up or down, changes height on screen and the sprite / wall gap varies by several degrees; with inc = 0.5 the variation is halved (to within 5%)."""
        def spacings(inc):
            out = []
            for dz in (-5.0, 0.0, 4.0, 9.0):                                                  # the NPC at the left edge, at different screen heights (= the hero going up or down)
                (M, q, _, _), _ = scenario('defaut', -9.0, dz, 1.0, inc); g = shape(M, q)[0]
                wall = self.world_vertical(M, 0.5 * (np.array(q[0]) + np.array(q[1]))); out.append(wall - g)
            return out
        e0, e5 = spacings(0.0), spacings(0.5)
        self.assertGreater(max(e0) - min(e0), 5.0, 'finding: without tilt, the sprite / wall gap varies by more than 5 degrees')
        self.assertGreater(max(abs(x) for x in e0), 15.0)
        for a, b in zip(e0, e5): self.assertAlmostEqual(b, a * 0.5, delta=0.05 * abs(a) + 0.7)
        self.assertLess(max(e5) - min(e5), 0.55 * (max(e0) - min(e0)))

    def test_setting_by_environment_variable(self):
        """DQ_SPRITE_TILT: 0 to 100 (%); absent, empty or unreadable: 0% (default); clamped."""
        j = TC.fake_game(); j.SPRITE_TILT_DEFAULT = F.Game.SPRITE_TILT_DEFAULT; old = os.environ.pop('DQ_SPRITE_TILT', None)
        try:
            self.assertEqual(F.Game._sprite_tilt(j), 0.0); self.assertEqual(F.Game.SPRITE_TILT_DEFAULT, 0.0)
            for val, att in (('0', 0.0), ('100', 1.0), ('30', 0.3), ('70.5', 0.705), ('250', 1.0), ('-5', 0.0), ('', 0.0), ('  ', 0.0), ('abc', 0.0)):
                os.environ['DQ_SPRITE_TILT'] = val; self.assertAlmostEqual(F.Game._sprite_tilt(j), att, 9, repr(val))
        finally:
            os.environ.pop('DQ_SPRITE_TILT', None)
            if old is not None: os.environ['DQ_SPRITE_TILT'] = old

    def test_unknown_camera_or_correction_cut(self):
        """Without a camera (C unknown) or with the edge correction off (t = 0): the original panel, even with `inc`."""
        (M, q, cam3d, C), hero = scenario('defaut', 6.0, 3.0, 0.0, 0.8); (_, q0, _, _), _ = scenario('defaut', 6.0, 3.0, 0.0, 0.0)
        for a, b in zip(q, q0): self.assertTrue(np.allclose(a, b))
        r_, u_, f_ = cam3d; w, h = F.SPRITE_L * F.SPRITE_SCALE, F.SPRITE_H * F.SPRITE_SCALE; zb, zh = 0.185 / 0.48 * w, (0.65 - 0.185) / 0.48 * w
        j = TC.fake_game(); a = F.Game._town_panel(j, hero, r_, u_, f_, w, h, zb, zb + zh, 1.0, None, 0.8); b = F.Game._town_panel(j, hero, r_, u_, f_, w, h, zb, zb + zh, 0.0, None, 0.0)
        for x, y in zip(a, b): self.assertTrue(np.allclose(x, y))


def sprites_ref_frame(j, e, corr=0.0):
    """(M, view coordinate frame, sprite coordinate frame chosen by `Game._sprite_reference`, viewer camera position) for camera state `j`."""
    M, cam3d = F.Game._town_camera(j, e, ASPECT)
    return M, cam3d, F.Game._sprite_reference(j, cam3d, corr), j._view_border[0]


def pitch(fw):
    """Tilt (degrees, downward) of a forward axis."""
    return math.degrees(math.asin(-fw[1]))


class TestSpritesLikeTheGame(unittest.TestCase):
    """an NPC's panel keeps the tilt of the GAME's camera: raising or lowering the camera (Up / Down) does not change it, the rotation around the hero (Left / Right) follows it."""

    def borders(self, **kw):
        hero = TARGET + np.array([0.0, kw.get('hy', 0.0), 0.0]); e = TC.fake_state(TARGET, hero, fov=kw.get('fov'), yoff=kw.get('yoff')); j = fake_game()
        for _ in range(3): F.Game._town_camera(j, e, ASPECT)
        return j, e, hero

    def test_without_tilt_or_rotation_game_reference_frame(self):
        """The game's camera as is: the sprite coordinate frame is the view's AND `_game_border`'s (the game's camera: the view no longer adds zoom, rotation or tilt)."""
        j, e, _ = self.borders(); M, cam3d, rep, _ = sprites_ref_frame(j, e)
        _, dr, ha, fw = F.Game._game_border(j, e)
        for a, b in zip(rep, cam3d): self.assertTrue(np.allclose(a, b))
        for a, b in zip(rep, (dr, ha, fw)): self.assertTrue(np.allclose(a, b, atol=1e-9))

    def test_panel_tilt_in_world_matches_game(self):
        """The original panel is almost vertical in the world (the top leans 36 degrees toward the camera); this slope (angle of the bottom -> top edge with the vertical) is the same at any hero height."""
        w, h = F.SPRITE_L * F.SPRITE_SCALE, F.SPRITE_H * F.SPRITE_SCALE; zb, zt = 0.185 / 0.48 * w, 0.65 / 0.48 * w; slopes = []
        for hy in (0.0, 0.5, 3.0):
            j, e, hero = self.borders(hy=hy); _, _, r, _ = sprites_ref_frame(j, e)
            a, b, c, d = F.Game._town_panel(j, hero, *r, w, h, zb, zt, 0.0, None); mid_bottom, mid_top = 0.5 * (a + b), 0.5 * (c + d); v = mid_top - mid_bottom
            slopes.append(math.degrees(math.atan2(math.hypot(v[0], v[2]), v[1])))
        for x in slopes: self.assertAlmostEqual(x, slopes[0], 6)
        self.assertLess(slopes[0], 40.0)

    def test_edge_correction_and_settings_keep_view_reference(self):
        """Edge correction > 0 (trial): the view's coordinate frame (the on-screen reconstruction needs it); DQ_SPRITES_IN_VIEW: the old alignment; without a camera: nothing."""
        j, e, _ = self.borders(); _, v, r0, _ = sprites_ref_frame(j, e, 0.0); _, _, r1, _ = sprites_ref_frame(j, e, 0.5)
        [self.assertTrue(np.allclose(a, b, atol=1e-9)) for a, b in zip(r0, v)]; [self.assertTrue(np.allclose(a, b)) for a, b in zip(r1, v)]          # (the view is the game's camera: same coordinate frame with or without correction)
        old = os.environ.get('DQ_SPRITES_IN_VIEW'); os.environ['DQ_SPRITES_IN_VIEW'] = '1'
        try: [self.assertTrue(np.allclose(a, b)) for a, b in zip(F.Game._sprite_reference(j, v, 0.0), v)]
        finally:
            if old is None: os.environ.pop('DQ_SPRITES_IN_VIEW', None)
            else: os.environ['DQ_SPRITES_IN_VIEW'] = old
        self.assertIsNone(F.Game._sprite_reference(j, None, 0.0))

    def test_free_scene_camera_and_minigame_unchanged(self):
        """Free camera (position and angles set by the script): the sprite coordinate frame is the view's; without a camera call, falls back to the view."""
        j = fake_game(); j._rot_camera = lambda e: F.Game._rot_camera(j, e)
        e = TC.fake_state(TARGET, TARGET, free=True); e.cam_rot = (45.0, 0.0, 0.0)
        M, cam3d = F.Game._town_camera(j, e, ASPECT); rep = F.Game._sprite_reference(j, cam3d, 0.0)
        for a, b in zip(rep, cam3d): self.assertTrue(np.allclose(a, b))
        jv = types.SimpleNamespace(); r = F.Game._sprite_reference(jv, cam3d, 0.0)
        for a, b in zip(r, cam3d): self.assertTrue(np.allclose(a, b))


if __name__ == '__main__':
    unittest.main(verbosity=2)
