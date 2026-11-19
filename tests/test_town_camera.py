"""Test of the towns' camera (without a window or the engine: `Game._town_camera` is called on a fake object). it is the game's, and the player's left / right rotation is too:

1. the port's matrix = Unity's pipeline rewritten separately (SceneCamera.Update: LookAt, pitch - lookDownAdjust, advance by distanceAdjust, Perspective(fov x 4/3, 1/aspect) whose
   [0] and [5] are swapped, s_yOffset) at the original portrait screen (0.5625);
2. it depends ONLY on what the engine sends (position, target, field, offset, free rotation): not on the hero, nor on the frame history (no smoothing, no centering,
   no leftover that slides), nor zoom, nor tilt, nor rotation added by the viewer (did it alongside the game: it "teleported" when a game scene took the camera);
3. the rotation that the player gives with the GAME's camera buttons is in the camera position that the game sends: the view shows it as is (distance, pitch, place of the target on screen unchanged);
   between two engine steps it is interpolated in an arc around the target (`Game._interpolate_camera`), an angle set all at once or a shot change is a cut;
4. the other settings and player gestures on the camera no longer exist (zoom, distance, tilt, centering, acceleration, wheel).

  python3 tests/test_town_camera.py        (Linux without a screen: pyglet in "headless" mode)
"""
import math, os, sys, types, unittest, inspect

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F
from dq456_pc.window import constants as C
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG

ASPECT_16_9 = 16.0 / 9.0


def fake_game(**kw):
    """The bare minimum: if the camera re-read a removed player setting (zoom, angle, distance...) or a viewer rotation state, this fake game would raise AttributeError."""
    j = types.SimpleNamespace(n_loop=0, _view_border=None, map_name=None, engine=types.SimpleNamespace(state=types.SimpleNamespace(part=None, cam_free=False, cam_rot=None)))
    j._rot_camera = lambda e: F.Game._rot_camera(j, e)
    for k, v in kw.items(): setattr(j, k, v)
    return j


def make_view(e, aspect=None, j=None, **kw):
    """-> (matrix, coordinate frame, fake game): the town camera for state `e` (the fake engine is that of `e`)."""
    j = j or fake_game(**kw); j.engine.state = e
    M, rep = F.Game._town_camera(j, e, ASPECT_16_9 if aspect is None else aspect)
    return M, rep, j


def fake_state(target_pos, hero, fov=None, yoff=None, part=None, free=False, rot=None, pos=None):
    target_pos = np.array(target_pos, float)
    return types.SimpleNamespace(cam_pos=target_pos + np.array([0.0, 28.94, -27.0]) if pos is None else np.array(pos, float), cam_target=target_pos, cam_fov=fov, cam_near=None, cam_far=None, cam_yoff=yoff, cam_down=None, cam_free=free, cam_rot=rot,
                                 sprites={0: {'pos': tuple(hero)}} if hero is not None else {}, part=part)


def ndc(M, p):
    c = M @ np.array([p[0], p[1], p[2], 1.0]); return c[0] / c[3], c[1] / c[3]


def unity_ndc(pos, target_pos, fov, near, far, yoff, aspect_cam, pts, bottom=0.2, dist_adj=4.0):
    """SceneCamera.Update (mode with a target) + NativeManager.cmd_camera, after the original code."""
    pos = np.array(pos, float); target_pos = np.array(target_pos, float)
    f0 = target_pos - pos; f0 /= np.linalg.norm(f0)
    ry, rx = math.atan2(f0[0], f0[2]), math.asin(-f0[1]) - math.radians(bottom)                            # Unity euler: heading, pitch downward; eulerAngles.x -= s_lookDownAdjust
    Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    R = Ry @ Rx; pos = pos + R @ np.array([0, 0, 1.0]) * dist_adj                                      # advances by s_distanceAdjust
    V = np.eye(4); V[:3, :3] = R.T; V[:3, 3] = -R.T @ pos; V = np.diag([1, 1, -1, 1.0]) @ V            # Unity's worldToCamera (looks toward -z)
    fv = math.radians(fov * 4.0 / 3.0)
    m11 = 1 / math.tan(fv / 2); m00 = m11 / (1.0 / aspect_cam)                                          # Matrix4x4.Perspective(fov x 4/3, 1 / aspect, near, far)
    P = np.zeros((4, 4)); P[0, 0] = m00; P[1, 1] = m11; P[2, 2] = -(far + near) / (far - near); P[2, 3] = -2 * far * near / (far - near); P[3, 2] = -1
    P[0, 0], P[1, 1] = P[1, 1], P[0, 0]                                                                 # [0] and [5] swapped: fixed horizontal field
    Ty = np.eye(4); Ty[1, 3] = yoff                                                                     # s_yOffset
    out = []
    for p in pts:
        c = Ty @ P @ V @ np.array([*p, 1.0]); out.append((c[0] / c[3], c[1] / c[3]))
    return np.array(out)


class TestTownCamera(unittest.TestCase):
    def test_projection_like_unity(self):
        rng = np.random.default_rng(1); worst = 0.0
        for _ in range(100):
            target_pos = rng.uniform(-30, 30, 3); target_pos[1] = 0
            pos = target_pos + np.array([rng.uniform(-8, 8), 29.0 + rng.uniform(-3, 3), -27.0 + rng.uniform(-3, 3)])
            fov = float(rng.choice([9.5, 10.0])); yoff = float(rng.choice([0.0, 0.05]))
            pts = [target_pos + np.array([dx, dy, dz]) for dx in (-5, 0, 5) for dy in (0, 1.5) for dz in (-6, 0, 6)]
            ref = unity_ndc(pos, target_pos, fov, F.TOWN_NEAR, F.TOWN_FAR, yoff, F.ASPECT_PORTRAIT, pts)
            e = fake_state(target_pos, target_pos, fov, yoff, pos=pos)
            M, _ = F.Game._town_camera(fake_game(), e, F.ASPECT_PORTRAIT)
            worst = max(worst, float(np.abs(np.array([ndc(M, p) for p in pts]) - ref).max()))
        self.assertLess(worst, 1e-9)

    def test_independent_of_hero(self):
        """The hero in the center, at the other end of the map, absent: same image (the game's target, bounded by the map edges, is authoritative; the viewer no longer recenters)."""
        refs = []
        for hero in ((0.0, 0.0, 0.0), (7.0, 0.0, -3.0), (40.0, 5.0, 40.0), None):
            M, _ = F.Game._town_camera(fake_game(), fake_state((5.0, 0.0, 4.0), hero), ASPECT_16_9); refs.append(M)
        for M in refs[1:]: self.assertLess(float(np.abs(M - refs[0]).max()), 1e-12)
        self.assertGreater(abs(ndc(refs[0], (0.0, 0.0, 0.0))[0]), 0.05, "the hero is not recentered when the game's target is elsewhere (edge of the map)")

    def test_without_memory(self):
        """No smoothing, no leftover: the image depends only on the state the engine sent at that moment (walking, stairs, scene cut, return from a scene...)."""
        j = fake_game(); route = [((0.0, 0.0, 0.0), 0.0), ((1.0, 0.0, 0.5), 0.3), ((1.0, 4.0, 0.5), 4.0), ((30.0, 4.0, -9.0), 4.0), ((30.0, 0.0, -9.0), 0.0), ((2.0, 0.0, 2.0), 0.0)]
        for target_pos, y in route:
            e = fake_state((target_pos[0], y, target_pos[2]), (target_pos[0], y, target_pos[2]))
            M1, _ = F.Game._town_camera(j, e, ASPECT_16_9); M2, _ = F.Game._town_camera(fake_game(), e, ASPECT_16_9)
            self.assertLess(float(np.abs(M1 - M2).max()), 1e-12, target_pos)
            self.assertLess(abs(ndc(M1, (target_pos[0], y, target_pos[2]))[0]) + abs(ndc(M1, (target_pos[0], y, target_pos[2]))[1] - ndc(M2, (target_pos[0], y, target_pos[2]))[1]), 1e-6, "the game's target stays where the game puts it")

    def test_height_same_as_game(self):
        """A staircase: the game's target rises by 4 units, the image follows right away (no lag like the old height smoothing)."""
        j = fake_game(); M0, _ = F.Game._town_camera(j, fake_state((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)), ASPECT_16_9)
        e = fake_state((0.0, 4.0, 0.0), (0.0, 4.0, 0.0)); M1, _ = F.Game._town_camera(j, e, ASPECT_16_9)
        self.assertLess(abs(ndc(M1, (0.0, 4.0, 0.0))[1] - ndc(M0, (0.0, 0.0, 0.0))[1]), 1e-9, 'the hero stays where he was on screen, without sliding')

    def test_free_camera_and_offset(self):
        """Free camera of a scene (packet 11, bit 7: position + angles) and vertical offset: what the game commands, nothing more."""
        e = fake_state((0.0, 0.0, 0.0), (9.0, 0.0, 9.0), free=True, rot=(30.0, 20.0, 0.0), pos=(1.0, 12.0, -10.0))
        M, rep = F.Game._town_camera(fake_game(), e, ASPECT_16_9); e2 = fake_state((0.0, 0.0, 0.0), None, free=True, rot=(30.0, 20.0, 0.0), pos=(1.0, 12.0, -10.0))
        M2, _ = F.Game._town_camera(fake_game(), e2, ASPECT_16_9); self.assertLess(float(np.abs(M - M2).max()), 1e-12)
        d = fake_state((3.0, 0.0, 3.0), (3.0, 0.0, 3.0), yoff=0.05); d0 = fake_state((3.0, 0.0, 3.0), (3.0, 0.0, 3.0), yoff=0.0)
        Ma, _ = F.Game._town_camera(fake_game(), d, ASPECT_16_9); Mb, _ = F.Game._town_camera(fake_game(), d0, ASPECT_16_9)
        self.assertAlmostEqual(ndc(Ma, (3.0, 0.0, 3.0))[1] - ndc(Mb, (3.0, 0.0, 3.0))[1], 0.05, places=6)

    def cap(self, rep):
        fw = rep[2]; return math.degrees(math.atan2(fw[0], fw[2]))

    def test_game_rotation_shown_as_is(self):
        """The game's camera turns around its target (the game's camera buttons, or a scene): the game sends the rotated position, the view shows it without adding anything: distance, pitch and place of the target on screen unchanged,
        heading = original heading + rotation (positive toward +X, like the right arrow)."""
        target_pos = np.array((5.0, 0.0, 4.0)); e0 = fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN); M0, rep0, j0 = make_view(e0)
        pos0, fw0 = j0._view_border[0], j0._view_border[3]; d0 = e0.cam_pos - target_pos
        for yaw in (-120.0, -45.0, 30.0, 90.0, 179.0):
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            e = fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN, pos=target_pos + np.array([d0[0] * c + d0[2] * s, d0[1], -d0[0] * s + d0[2] * c]))          # (the position the engine sends after the rotation)
            M, rep, j = make_view(e); pos, fw = j._view_border[0], j._view_border[3]
            self.assertLess(abs(ndc(M, target_pos)[0] - ndc(M0, target_pos)[0]) + abs(ndc(M, target_pos)[1] - ndc(M0, target_pos)[1]), 1e-9, yaw)          # the target stays where the game puts it
            self.assertAlmostEqual(float(np.linalg.norm(pos - target_pos)), float(np.linalg.norm(pos0 - target_pos)), places=9)                 # same distance
            self.assertAlmostEqual(float(pos[1]), float(pos0[1]), places=9); self.assertAlmostEqual(float(fw[1]), float(fw0[1]), places=9)   # same height, same pitch
            spacing = (self.cap(rep) - self.cap(rep0) - yaw + 180.0) % 360.0 - 180.0; self.assertLess(abs(spacing), 1e-6, yaw)             # heading + rotation
        self.assertGreater(self.cap(make_view(fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN, pos=target_pos + np.array([d0[2], d0[1], 0.0 - d0[0]])))[1]) - self.cap(rep0), 0.0)         # (to the right: the heading advances toward +X)

    def test_phone_area_turned_on_its_side(self):
        """16:9 shows up what the portrait phone shows across (and across what it shows up); a portrait 9:16 window shows exactly the phone; other shapes keep that base whole."""
        target_pos = (5.0, 0.0, 4.0); e = fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN)
        def tangents(aspect):
            M = make_view(e, aspect)[0]; P = M[:, :3]                                  # (no offset: rows 0 and 1 = projection scale x rotation)
            return 1 / np.linalg.norm(P[0]) * np.linalg.norm(P[3]), 1 / np.linalg.norm(P[1]) * np.linalg.norm(P[3])
        phone_x = math.tan(math.radians(F.TOWN_FOV_DEFAULT * 4 / 3) / 2); phone_y = phone_x / F.ASPECT_PORTRAIT          # (the towns keep the game's own camera)
        for aspect, x, y in ((16 / 9, phone_y, phone_x), (9 / 16, phone_x, phone_y), (21 / 9, phone_x * 21 / 9, phone_x), (4 / 3, phone_y, phone_y * 0.75), (1.0, phone_y, phone_y)):
            tx, ty = tangents(aspect); self.assertAlmostEqual(tx, x, 9, aspect); self.assertAlmostEqual(ty, y, 9, aspect)

    def test_bestiary_like_the_phone_in_its_column(self):
        """The bestiary (its monster is placed by the engine's camera, 83 units away, for the phone's portrait screen): a point lands in the interface column where the phone shows it,
        the column centered, on the left, or enlarged (window 1920 x 1080: column 450 units, 1.35 px each)."""
        cam, target, pts = (0.0, 0.0, -83.0), (4.1, 0.0, 0.0), [(0.0, 0.0, -41.5), (0.0, 0.7, -41.5), (-0.4, 0.3, -41.5)]
        phone = unity_ndc(cam, target, F.TOWN_FOV_DEFAULT, F.TOWN_NEAR, F.TOWN_FAR, 0.0, F.ASPECT_PORTRAIT, pts)
        for cx, k in ((960.0, 1.0), (225 * 1.35, 1.0), (960.0, 1.25)):
            s_ = 1080 / 800.0 * k
            e = fake_state(target, None, part=ENGINE.PART_BESTIARY, pos=cam)
            M, _, _j = make_view(e, 16 / 9, width=1920, height=1080, ui_k=k, _ui_reference=lambda cx=cx, s_=s_: (cx, 540.0, s_))
            got = np.array([ndc(M, p) for p in pts])
            want = np.c_[(cx + phone[:, 0] * 225 * s_) / 960.0 - 1.0, phone[:, 1] * 400 * s_ / 540.0]
            self.assertLess(float(np.abs(got - want).max()), 1e-9, (cx, k))

    def test_no_viewer_state_in_view(self):
        """Nothing other than what the engine sends changes the view: the fake game has no rotation, no scene weight, no lock (had them), and the view is the same whatever the state of the game."""
        target_pos = (5.0, 0.0, 4.0); ref = make_view(fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN))[0]
        for name in (None, 'mbk1f1', 'srout'): self.assertLess(float(np.abs(make_view(fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN), map_name=name)[0] - ref).max()), 1e-12, name)
        title = make_view(fake_state(target_pos, target_pos, part=ENGINE.PART_TOWN), map_name=C.TITLE_MAP)[0]          # the title screen keeps the phone's whole height; a town in 16:9 shows the phone's width up (16/9 closer)
        self.assertLess(float(np.abs(title[:2] * 16 / 9 - ref[:2]).max()), 1e-9); self.assertLess(float(np.abs(title[2:] - ref[2:]).max()), 1e-12)
        for name_str in ('yaw', 'cam_w', 'cam_jeu', 'cam_bloquee', 'cam_saut', 't_centre', '_sprites_border'): self.assertFalse(hasattr(fake_game(), name_str), name_str)
        src = inspect.getsource(F.Game._town_camera)
        for word in ('self.yaw', 'cam_w', '_lacet_eff', 'perf_counter', 'cam_jeu'): self.assertNotIn(word, src, word)

    def test_world_map_scale(self):
        """(cancels): as on the phone, the two zooms differ. The towns keep the game's own camera (the character panel, 1.152 high at 39.55 units from the target, takes
        14.6 % of the 16:9 window) and the world map its own field (the hero, 33.2 map pixels of the 256 the window shows up: 13 %). The title screen and the bestiary show the phone's whole height."""
        target_pos = np.array((5.0, 0.0, 4.0)); pos = target_pos + np.array([0.0, 28.938, -26.959])
        self.assertAlmostEqual(float(np.linalg.norm(pos - target_pos)), C.TOWN_CAM_DIST, 2)
        def share(part, **kw):
            M, rep, _ = make_view(fake_state(target_pos, target_pos, part=part, pos=pos), **kw)
            return (ndc(M, target_pos + rep[1] * C.SPRITE_H * C.SPRITE_SCALE)[1] - ndc(M, target_pos)[1]) / 2
        self.assertAlmostEqual(share(ENGINE.PART_TOWN), C.TOWN_HERO_SHARE, 3); self.assertAlmostEqual(C.TOWN_HERO_SHARE, 0.146, 3)
        self.assertAlmostEqual(share(ENGINE.PART_BESTIARY) / share(ENGINE.PART_TOWN, map_name=C.TITLE_MAP), 1.0, 9)          # (the bestiary: the phone's whole height, as its interface column)
        self.assertAlmostEqual(share(ENGINE.PART_TOWN, map_name=C.TITLE_MAP) / share(ENGINE.PART_BESTIARY, map_name=C.TITLE_MAP), 1.0, 9)          # (title screen unchanged)
        g = types.SimpleNamespace(mode=0); e = types.SimpleNamespace(field={'cam': (160.0, 320.0)}, field_scale=1.0)
        M, _, _, h = F.Game._field_camera(g, e, 16 / 9)
        self.assertAlmostEqual(h * abs(M[1, 2]) / 2, C.FIELD_HERO_SHARE, 3); self.assertAlmostEqual(C.FIELD_HERO_SHARE, 33.2 / 256, 3)          # the hero on the world map: its own share
        self.assertAlmostEqual(C.TOWN_HERO_SHARE / C.FIELD_HERO_SHARE, 1.126, 3)                                                                  # (the phone's difference, kept)

    # ---- interpolation between two engine steps (Game._interpolate_camera)
    def turn(self, target_pos, d0, deg):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg)); return tuple(np.array(target_pos) + np.array([d0[0] * c + d0[2] * s, d0[1], -d0[0] * s + d0[2] * c]))

    def interp(self, pr_pos, prev_target, pos, target_pos, a):
        j = types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(cam_pos=pos, cam_target=target_pos)))
        return F.Game._interpolate_camera(j, dict(cam_pos=pr_pos, cam_target=prev_target), a)

    def test_rotation_interpolated_along_an_arc(self):
        """One rotation notch (2.8125 degrees) moves the camera by more than CAM_JUMP_TOWN on one coordinate when it is 34 units from its target (ev01, cbout: (0 ; 27.7 ; -34.18)): the old coordinate-by-coordinate interpolation saw a jump there,
        and the rotation stayed at 30 steps per second. In an arc around the target: same distance, intermediate heading."""
        target_pos = (5.0, 0.0, 4.0); d0 = np.array([0.0, 27.7, -34.18]); r0 = math.hypot(d0[0], d0[2])
        for yaw in (0.0, 60.0, 135.0, -100.0):
            p0 = self.turn(target_pos, self.turn((0, 0, 0), d0, yaw), 0.0); p1 = self.turn(target_pos, self.turn((0, 0, 0), d0, yaw), ENGINE.CAM_STEP)
            if yaw == 0.0: self.assertGreater(float(np.abs(np.array(p1) - np.array(p0)).max()), F.CAM_JUMP_TOWN)          # (the case to handle: more than the jump threshold on a single coordinate)
            for a in (0.0, 0.25, 0.5, 1.0):
                r = self.interp(p0, target_pos, p1, target_pos, a); self.assertIsNotNone(r, (yaw, a))
                pos, c = np.array(r[0]), np.array(r[1]); rel = pos - c
                self.assertAlmostEqual(math.hypot(rel[0], rel[2]), r0, places=9); self.assertAlmostEqual(float(rel[1]), float(d0[1]), places=9)       # same distance, same height
                cap = math.degrees(math.atan2(-rel[0], -rel[2])); cap0 = math.degrees(math.atan2(-(p0[0] - target_pos[0]), -(p0[2] - target_pos[2])))
                self.assertAlmostEqual((cap - cap0 + 180.0) % 360.0 - 180.0, a * ENGINE.CAM_STEP, places=6)
            self.assertLess(float(np.abs(np.array(self.interp(p0, target_pos, p1, target_pos, 1.0)[0]) - np.array(p1)).max()), 1e-9)

    def test_height_and_distance_interpolated(self):
        """A scene that raises the camera or brings it closer to its target while it rotates: the height and distance follow halfway (no stair step at 30 steps per second)."""
        target_pos = (5.0, 0.0, 4.0); p0 = (5.0, 20.0, 4.0 - 30.0); p1 = (5.0 + 30.0 * math.sin(math.radians(ENGINE.CAM_STEP)), 24.0, 4.0 - 30.0 * math.cos(math.radians(ENGINE.CAM_STEP)))
        r = self.interp(p0, target_pos, p1, target_pos, 0.5); self.assertIsNotNone(r); rel = np.array(r[0]) - np.array(r[1])
        self.assertAlmostEqual(float(rel[1]), 22.0, places=9); self.assertAlmostEqual(math.hypot(rel[0], rel[2]), 30.0, places=9)
        p2 = (5.0, 20.0, 4.0 - 34.0); r = self.interp(p0, target_pos, p2, target_pos, 0.25); rel = np.array(r[0]) - np.array(r[1])
        self.assertAlmostEqual(math.hypot(rel[0], rel[2]), 31.0, places=9)

    def test_rotation_crossing_180_degrees(self):
        target_pos = (0.0, 0.0, 0.0); p0 = (0.0, 28.94, 26.96 - 0.5); p1 = self.turn(target_pos, p0, -ENGINE.CAM_STEP)       # camera toward -Z of the target, rotating on either side of 180 degrees
        r = self.interp(p0, target_pos, p1, target_pos, 0.5); self.assertIsNotNone(r); rel = np.array(r[0]) - np.array(r[1])
        self.assertAlmostEqual(math.hypot(rel[0], rel[2]), math.hypot(p0[0], p0[2]), places=9)

    def test_walking_target_and_turning_camera(self):
        cib0 = (5.0, 0.0, 4.0); cib1 = (5.3, 0.0, 4.1); d0 = np.array([0.0, 28.94, -26.96])
        p0 = tuple(np.array(cib0) + d0); p1 = self.turn(cib1, d0, ENGINE.CAM_STEP)
        r = self.interp(p0, cib0, p1, cib1, 0.5); self.assertIsNotNone(r)
        self.assertLess(float(np.abs(np.array(r[1]) - (np.array(cib0) + np.array(cib1)) / 2).max()), 1e-12)          # the target is halfway

    def test_nothing_moved_or_cut(self):
        target_pos = (5.0, 0.0, 4.0); d0 = np.array([0.0, 28.94, -26.96]); p0 = tuple(np.array(target_pos) + d0)
        self.assertIsNone(self.interp(p0, target_pos, p0, target_pos, 0.5))                                                      # nothing moved
        self.assertIsNone(self.interp(p0, target_pos, tuple(np.array(p0) + (20.0, 0.0, 0.0)), (25.0, 0.0, 4.0), 0.5))    # the target jumped: map change, scene shot
        self.assertIsNone(self.interp(p0, target_pos, self.turn(target_pos, d0, 90.0), target_pos, 0.5))                              # angle set all at once (game script, 90 degrees in one step): cut
        self.assertIsNone(self.interp(p0, target_pos, p0, None, 0.5)); self.assertIsNone(self.interp(None, target_pos, p0, target_pos, 0.5))
        self.assertIsNotNone(self.interp(p0, target_pos, self.turn(target_pos, d0, 15.0), target_pos, 0.5))                             # up to ~20 degrees per step (speed x4: 11.25): a rotation, interpolated
        self.assertIsNotNone(self.interp(p0, target_pos, self.turn(target_pos, d0, 4 * ENGINE.CAM_STEP), target_pos, 0.5))

    def test_only_rotation_is_left_to_the_player(self):
        """Removed and not coming back: zoom / distance, tilt, centering on the hero, height smoothing, camera acceleration. Back: the left / right rotation and its recentering."""
        src = inspect.getsource(F.Game._town_camera)
        for word in ('self.zoom', 'angle_cam', 'cam_dec', 'cam_res', 'cam_ref_y', 'hauteur_camera'): self.assertNotIn(word, src, word)
        for name_str in ('_maj_distance_clavier', 'regler_zoom', 'set_distance', 'reinitialiser_camera', 'distance_par_defaut', '_zoom_possible', '_suivre_scene', '_ctrl_actif'): self.assertFalse(hasattr(F.Game, name_str), name_str)
        for name_str in ('recenter_camera', '_drivable_camera', '_wheel_press', '_wheel_drag', '_wheel_release', '_axis_state', '_bits_camera', '_camera_after_step', '_camera_forget', '_engine_yaw', '_interpolate_camera'):
            self.assertTrue(hasattr(F.Game, name_str), name_str)
        for name_str in ('_maj_camera', '_camera_menee', '_coupure_camera', '_lacet_eff', '_tourner_dir'): self.assertFalse(hasattr(F.Game, name_str), name_str)          # (the viewer's rotation alongside the game, removed)
        src = inspect.getsource(F.Game._bits_camera) + inspect.getsource(F.Game._camera_after_step)
        for word in ("'accel'", 'accel_speed', 'angle_cam', 'cam_up', 'cam_down'): self.assertNotIn(word, src, word)         # the camera no longer accelerates, and has no more tilt
        for lookup_key in ('distance_camera', 'angle_camera', 'camera_inverser_hb'): self.assertNotIn(lookup_key, RG.DEFAULT, lookup_key)
        for action in ('cam_pres', 'cam_loin'): self.assertNotIn(action, RG.DEFAULT_KEYS, action)
        for lookup_key in ('distance_camera', 'angle_camera', 'camera_inverser_hb'): self.assertIn(lookup_key, RG.OBSOLETE_KEYS, lookup_key)

    def test_wiring_in_loop_and_drawing(self):
        """The wiring that connects the camera to the rest (the real loop cannot be run here): the viewer no longer has a per-frame camera update nor a TownCamera state to read (lock, limit, scene: the game decides),
        no more rotation of the walking nor of the sprite rows (the game sends the directions already relative to its camera); the camera buttons go out with the step's keys, and the wheel click is wired to them."""
        looping = inspect.getsource(F.Game._loop)
        self.assertNotIn('_maj_camera', looping)
        self.assertEqual([n for n, f in inspect.getmembers(F.Game, inspect.isfunction) if 'lg, ld, vr = eng.camera_town()' in inspect.getsource(f)], [], "the game's TownCamera is no longer read to add a rotation to it")
        self.assertEqual([n for n, f in inspect.getmembers(F.Game, inspect.isfunction) if 'phi = ' in inspect.getsource(f) and 'lacet' in inspect.getsource(f)], [], 'no more correction of the sprite rows')
        self.assertNotIn('_tourner_dir', inspect.getsource(F.Game.pad))
        self.assertIn('self._bits_camera()', inspect.getsource(F.Game._entries)); self.assertIn('self._camera_after_step(eng)', inspect.getsource(F.Game.tick))
        self.assertIn('self._wheel_press(x, y)', inspect.getsource(F.Game.on_mouse_press)); self.assertIn('self._wheel_release()', inspect.getsource(F.Game.on_mouse_release))
        self.assertIn('self.wheel.cancel()', inspect.getsource(F.Game.on_deactivate)); self.assertIn('self.wheel.cancel()', inspect.getsource(F.Game.on_mouse_motion))
        self.assertIn('self._interpolate_camera(pr, a)', inspect.getsource(F.Game._interpolate))

    def test_camera_settings(self):
        """By default: Left > left arrow, Right > right arrow, drag direction not inverted; no more camera speed setting. Visible in Commandes (see test_pause_pages)."""
        self.assertEqual(RG.DEFAULT_KEYS['cam_left'], ['LEFT', None]); self.assertEqual(RG.DEFAULT_KEYS['cam_right'], ['RIGHT', None])
        self.assertIs(RG.DEFAULT['camera_invert_lr'], False); self.assertNotIn('camera_invert_lr', RG.OBSOLETE_KEYS)
        self.assertNotIn('vitesse_camera', RG.DEFAULT); self.assertNotIn('vitesse_camera', RG.BOUNDS); self.assertIn('vitesse_camera', RG.OBSOLETE_KEYS)
        self.assertEqual(dict(RG.ACTIONS)['cam_left'], 'settings.camera_left'); self.assertEqual(dict(RG.ACTIONS)['cam_right'], 'settings.camera_right')
        self.assertAlmostEqual(ENGINE.CAM_STEP, 360.0 * 0x200 / 65536.0)          # the reference speed (x1) is the game's: one notch of 2.8125 degrees per step, 84.4 degrees per second

    def test_old_settings_file_readable(self):
        """A reglages.json (distance, angle, camera speed, Page up / Page down keys) reads without error: the drag direction is kept;
        the removed keys (distance, angle, camera speed, up / down inversion) are not rewritten."""
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            ch = os.path.join(d, 'settings.json')
            with open(ch, 'w', encoding='utf-8') as f: json.dump({'distance_camera': 150, 'angle_camera': 12.0, 'vitesse_camera': 3.0, 'camera_invert_lr': True, 'camera_inverser_hb': True, 'vitesse_marche': 2.0, 'keys': {'cam_pres': ['PAGEUP', None], 'up': ['W', None]}, 'keys_version': RG.DEFAULT['keys_version']}, f)
            r = RG.Settings(ch); r.store()
            with open(ch, encoding='utf-8') as f: written_data = json.load(f)
        self.assertNotIn('vitesse_marche', r.v); self.assertEqual(r['keys']['up'][0], 'W')
        self.assertNotIn('vitesse_camera', r.v); self.assertIs(r['camera_invert_lr'], True)
        for lookup_key in ('distance_camera', 'angle_camera', 'camera_inverser_hb', 'vitesse_camera'): self.assertNotIn(lookup_key, written_data, lookup_key)
        self.assertIs(written_data['camera_invert_lr'], True); self.assertNotIn('cam_pres', written_data['keys'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
