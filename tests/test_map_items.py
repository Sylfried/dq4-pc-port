"""Test of the pure logic of the maps' animated objects (no window, no engine, no APK): objects' own orientation and the direction of animations (chests, drawers, doors):

1. `data.euler_mat` = FldObject.rotateXZY (0xCD47F0): q = (AngleAxis(ry, up) * AngleAxis(-rz, forward)) * AngleAxis(-rx, right): X applied first, then Z, then Y (heading last).
   Recomputed separately with Unity's quaternion product (the disassembly's one: R = q2 * q3 then R * q1);
2. opening chest (lid: common motion, rotation -60 on X): the lid pivots around the CHEST's hinge, whatever its heading (0, 90, -90, 180, -27 degrees: all the chests of the
   same family open "toward the back of the chest", never sideways), and at the same speed;
3. drawer (common motion with a position key): the displacement is in the object's frame (FldObject.c_pmv_func: MultiplyPoint(TRS(position, rotateXZY(rotation), scale)); an
   ordinary motion (pmv_func) adds the displacement as is;
4. door (rotation around Y only): unchanged (door heading + motion heading);
5. continuous animations (FPMV motions and FSQD mesh sequences): EACH with its own clock (FldObject.fld_motion_update, one FLD_MOTION per animation); linear interpolation of the Euler angles
   COMPONENT BY COMPONENT (pmv_func: rotateXZY of the interpolated rotation, never a quaternion or a shortest path): 0 -> 360 degrees really turns, loops without a jump; the healing beam
   `kifk01a` (rotation 0 -> 180 -> 360 in 800 / 60 s, sequence of 84 / 60 s) turns a full revolution and not 38 degrees before coming back;
6. (if the map cache exists: DQ_MAP_CACHE, otherwise /tmp/uicache_coffres) the REAL objects: the 194 chests, the drawers and doors of all the maps.

  python3 tests/test_map_items.py
"""
import math, os, sys, unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.world.data import euler_mat
from dq456_pc.world import map_objects as OC
from dq456_pc.world.data import MAP_PREFIX           # prefix of the map cache, read from the source: hard-coded, these tests silently skipped after the switch to carte11_


# ---- independent reference: Unity quaternions
def axis_quat(angle_deg, axis):
    a = math.radians(angle_deg) / 2; s = math.sin(a); return np.array([axis[0] * s, axis[1] * s, axis[2] * s, math.cos(a)])      # (x, y, z, w)


def qmul(a, b):
    """Hamilton product a * b (b applied first), (x, y, z, w): formulas from the disassembly."""
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def game_rotate_xzy(rx, ry, rz):
    """FldObject.rotateXZY as read from the disassembly: q1 = AngleAxis(-rx, right), q2 = AngleAxis(ry, up), q3 = AngleAxis(-rz, forward); R = q2 * q3; result = R * q1."""
    q1 = axis_quat(-rx, (1, 0, 0)); q2 = axis_quat(ry, (0, 1, 0)); q3 = axis_quat(-rz, (0, 0, 1))
    return qmat(qmul(qmul(q2, q3), q1))


def ry_mat(deg):
    b = math.radians(deg); return np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])


# ---- tiny maps
def map_object(pos, rot, local_pts, lookup_keys, movement_flag=4, scl=(1.0, 1.0, 1.0), end=10):
    """A one-object map: vertices `local_pts` (model frame) baked at the original position / rotation / scale, a common-animation table with 4 entries whose 2nd (number 2) is
    a two-key motion (frame 0: nothing; frame `end`: `lookup_keys`)."""
    pts = np.array(local_pts, np.float64)
    world = (np.array(pos, np.float64) + (euler_mat(*rot) @ np.diag(scl) @ pts.T).T).astype(np.float32)
    n = len(pts)
    ident = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    def word(last_one): return dict(flag=movement_flag, nkey=2, repeat=1, delay=0, loop_delay=0, end=end, keys=[(0,) + ident, (end,) + last_one])
    words = [word(ident), word(lookup_keys), word(lookup_keys), word(ident)]
    words[0]['end'] = 2; words[0]['keys'] = [(0,) + ident, (2,) + ident]
    obj = dict(i=0, pos=tuple(pos), rot=tuple(rot), scl=tuple(scl), model=1, canim=0, flag=0, sequence_object=-1, pmv=-1, id=0, com=0, uid=0, prio=0, rest='')
    return {'objects': [obj], 'groups': {'k': (world, np.zeros((n, 2), np.float32), np.ones((n, 4), np.float32))}, 'spans': {0: [('k', 0, n)]}, 'var': {},
            'tabs': [[(1, -1, 0), (1, -1, 1), (1, -1, 2), (1, -1, 3)]], 'motions': words, 'sequences': [], 'sequence_entries': [], 'imgobj': {}}


def play(c, no=2, frames=20):
    oc = OC.MapObjects(c)
    oc.common_anim(0, no)
    for _ in range(frames): oc.tick()
    return oc.cur['k'].astype(np.float64)


# chest lid: hinge along the local X axis (at the foot of the model: origin = hinge), extends toward the front of the chest (local -Z), some thickness (Y)
LID = [(-0.4, 0, 0), (0.4, 0, 0), (-0.4, 0, -0.6), (0.4, 0, -0.6), (-0.4, 0.1, -0.3)]
OPENED = ((0.0, 0.0, 0.0), (-60.0, 0.0, 0.0), (1.0, 1.0, 1.0))                  # opening key of the game's 194 chests: rotation X = -60


class TestGameRotation(unittest.TestCase):
    def test_rotation_order_like_game(self):
        rng = np.random.RandomState(7)
        for _ in range(50):
            rx, ry, rz = rng.uniform(-180, 180, 3)
            np.testing.assert_allclose(euler_mat(rx, ry, rz), game_rotate_xzy(rx, ry, rz), atol=1e-9)

    def test_x_first_in_the_object_frame(self):
        """The X tilt (lid) is done in the object's frame, then the heading rotates it: Ry . Rx."""
        for cap in (0, 90, -90, 180, -27, 133):
            np.testing.assert_allclose(euler_mat(-60, cap, 0), euler_mat(0, cap, 0) @ euler_mat(-60, 0, 0), atol=1e-9)

    def test_simple_rotations_unchanged(self):
        for cap in (0, 45, 90, -90, 180):
            np.testing.assert_allclose(euler_mat(0, cap, 0), ry_mat(cap), atol=1e-12)
        r = euler_mat(-60, 0, 0) @ np.array([0, 0, -1.0])                           # key -60: the front edge of the lid rises and moves back
        self.assertAlmostEqual(r[1], math.sin(math.radians(60))); self.assertAlmostEqual(r[2], -0.5); self.assertAlmostEqual(r[0], 0.0)


class TestChest(unittest.TestCase):
    def test_opening_follows_chest_heading(self):
        """Whatever the heading, the finished lid = that of the heading-0 chest, rotated by the heading (around the hinge)."""
        pos = (3.0, 0.5, -2.0)
        ref = play(map_object(pos, (0, 0, 0), LID, OPENED)) - np.array(pos)
        self.assertGreater(ref[2][1], 0.4)                                          # chest with heading 0: the front edge lifts (0.6 x sin 60 = 0.52)
        for cap in (90, -90, 180, -27, 133):
            finished = play(map_object(pos, (0, cap, 0), LID, OPENED)) - np.array(pos)
            expected = (ry_mat(cap) @ ref.T).T
            np.testing.assert_allclose(finished, expected, atol=1e-5, err_msg='cap %d' % cap)

    def test_hinge_stays_put_and_lid_never_rolls(self):
        pos = (0.0, 0.5, 0.0)
        for cap in (0, 90, -90, 180, -27):
            c = map_object(pos, (0, cap, 0), LID, OPENED); before = c['groups']['k'][0].astype(np.float64).copy()
            finished = play(c)
            np.testing.assert_allclose(finished[:2], before[:2], atol=1e-6)               # the two hinge vertices do not move
            front_f = ry_mat(cap) @ np.array([0, 0, -1.0])                           # the front of the chest (hinge axis toward the front)
            d = (finished[2] - finished[0]); d = d / np.linalg.norm(d)                       # hinge axis -> front edge of the open lid: in the vertical plane of the front of the chest
            lateral = ry_mat(cap) @ np.array([1.0, 0, 0])                            # hinge axis: the lateral displacement must stay zero (opening "like a book", no roll)
            self.assertAlmostEqual(float(d @ lateral), 0.0, places=5, msg='cap %d' % cap)
            self.assertGreater(float(d @ front_f), 0.0)

    def test_mid_travel_same_speed_at_all_headings(self):
        pos = (0.0, 0.5, 0.0)
        ref0 = None
        for cap in (0, 90, 180):
            oc = OC.MapObjects(map_object(pos, (0, cap, 0), LID, OPENED)); oc.common_anim(0, 2)
            for _ in range(3): oc.tick()                                             # 3 game frames = 6 / 60 s out of 10
            p = (ry_mat(cap).T @ (oc.cur['k'].astype(np.float64)[2] - np.array(pos)))
            if ref0 is None: ref0 = p
            np.testing.assert_allclose(p, ref0, atol=1e-5)
            self.assertTrue(0.05 < p[1] < 0.5)                                       # between closed and open


class TestMovements(unittest.TestCase):
    DRAWER_KEYFRAME = ((0.0, 0.0, -0.5), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))             # the drawer slides out by 0.5 toward the front of the furniture

    def test_common_movement_in_item_reference_frame(self):
        pos = (1.0, 0.0, 1.0); pts = [(0, 0, 0), (0.2, 0.1, 0)]
        for cap in (0, 90, -90, 180, -27):
            c = map_object(pos, (0, cap, 0), pts, self.DRAWER_KEYFRAME); before = c['groups']['k'][0].astype(np.float64).copy()
            finished = play(c)
            np.testing.assert_allclose(finished - before, np.tile(ry_mat(cap) @ np.array([0, 0, -0.5]), (2, 1)), atol=1e-5, err_msg='cap %d' % cap)

    def test_common_movement_with_scale(self):
        pos = (0.0, 0.0, 0.0); pts = [(0, 0, 0)]
        c = map_object(pos, (0, 90, 0), pts, self.DRAWER_KEYFRAME, scl=(2.0, 1.0, 3.0)); before = c['groups']['k'][0].astype(np.float64).copy()
        finished = play(c)
        np.testing.assert_allclose(finished - before, [(-0.5 * 3.0, 0, 0)], atol=1e-5)    # MultiplyPoint(TRS): the object's scale also applies to the displacement (z x 3, rotated by 90 degrees)

    def test_ordinary_movement_displacement_as_is(self):
        pos = (0.0, 0.0, 0.0); pts = [(0, 0, 0)]
        c = map_object(pos, (0, 90, 0), pts, self.DRAWER_KEYFRAME, movement_flag=0); before = c['groups']['k'][0].astype(np.float64).copy()
        finished = play(c)
        np.testing.assert_allclose(finished - before, [(0, 0, -0.5)], atol=1e-5)          # pmv_func: object position + key, no rotation

    def test_engine_order_position_and_heading(self):
        """SetMapObjPos / SetMapObjRot (packets 3 and 4) then common motion: the motion's base is the object's CURRENT position and heading (c_pmv_func reads the object's fields)."""
        pts = [(0, 0, 0)]
        c = map_object((0.0, 0.0, 0.0), (0, 0, 0), pts, self.DRAWER_KEYFRAME); oc = OC.MapObjects(c)
        oc.position(0, (5.0, 0.0, 5.0)); oc.rotation(0, (0.0, 90.0)); oc.common_anim(0, 2)
        for _ in range(20): oc.tick()
        np.testing.assert_allclose(oc.cur['k'].astype(np.float64)[0], (5.0 - 0.5, 0.0, 5.0), atol=1e-5)

    def test_door_around_y_unchanged(self):
        pts = [(0, 0, 0), (0.0, 0.0, 1.0), (0.0, 1.0, 1.0)]
        for cap in (0, 90, -90, 180):
            c = map_object((0, 0, 0), (0, cap, 0), pts, ((0, 0, 0), (0, -90, 0), (1, 1, 1))); finished = play(c)
            np.testing.assert_allclose(finished, np.array([ry_mat(cap - 90) @ np.array(p, float) for p in pts]), atol=1e-5)


# ---- continuous animations: one clock per animation
def auto_map_object(local_pts, lookup_keys, end, repeat=-1, delay=0, loop_delay=0, seq_end=None, common=False, pos=(0.0, 0.0, 0.0)):
    """A map of a rotating object: FPMV motion with keys (frame, rotation) played continuously (or started by SetCommonAnimation 1 if `common`), plus, if `seq_end`, a mesh sequence
    with its own duration (two vertex frames: the object and the same one shifted by 0.5 in height)."""
    pts = np.array(local_pts, np.float64); n = len(pts); world = (np.array(pos, np.float64) + pts).astype(np.float32)
    word = dict(flag=0, nkey=len(lookup_keys), repeat=repeat, delay=delay, loop_delay=loop_delay, end=end, keys=[(f, (0.0, 0.0, 0.0), tuple(float(v) for v in r), (1.0, 1.0, 1.0)) for f, r in lookup_keys])
    obj = dict(i=0, pos=tuple(pos), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0), model=1, canim=0 if common else -1, flag=0, sequence_object=-1, pmv=-1 if common else 0, id=0, com=0, uid=0, prio=0, rest='')
    c = {'objects': [obj], 'groups': {'k': (world, np.zeros((n, 2), np.float32), np.ones((n, 4), np.float32))}, 'spans': {0: [('k', 0, n)]}, 'var': {}, 'tabs': [], 'motions': [word],
         'sequences': [], 'sequence_entries': [], 'imgobj': {}}
    if seq_end:
        c['sequences'] = [dict(flag=0, nkey=4, repeat=-1, delay=0, loop_delay=0, end=seq_end, keys=[(0, 0), (seq_end // 2, 1), (seq_end, 0), (seq_end, 2)])]     # (last key = terminator, as in the data)
        c['sequence_entries'] = [(0, 0, 0, 0, 0, -1, 0, -1)]                              # (object, sequence, group, start delay, delay between two loops, number of loops, _, original number of loops)
        c['imgobj'] = {0: [{'pos': np.stack([world, world + np.array([0.0, 0.5, 0.0], np.float32)]), 'uv': None, 'col': None}]}
        if common: c['tabs'] = [[(1, 0, 0)]]
        else: obj['sequence_object'] = 0
    elif common: c['tabs'] = [[(1, -1, 0)]]
    return c


def turn(c, ticks, common=False):
    oc = OC.MapObjects(c)
    if common: oc.common_anim(0, 1)
    for _ in range(ticks): oc.tick()
    return oc


def map_vertices(oc): return oc.cur['k'].astype(np.float64)


PTS = [(1.0, 0.0, 0.0), (0.0, 0.0, 2.0), (-0.5, 1.0, 0.0)]


class TestClocks(unittest.TestCase):
    """An animation's ExampleCounter (FldObject.fld_motion_update): start delay, loops, delay between two loops, hold on the last key."""

    def advance_time(self, delay, loop_delay, rep, end, n):
        h = OC._clock(delay, loop_delay, rep, end); suite = []
        for _ in range(n): OC._advance(h); suite.append(h['time'])
        return h, suite

    def test_endless_loop(self):
        h, t = self.advance_time(0, 0, -1, 10, 12)
        self.assertEqual(t, [2, 4, 6, 8, 10, 2, 4, 6, 8, 10, 2, 4])               # at the exact end we stay on the last key; beyond it, back to the start by the remainder of the overshoot
        self.assertFalse(h['finished'])

    def test_overshoot_kept(self):
        h, t = self.advance_time(0, 0, -1, 9, 7)
        self.assertEqual(t, [2, 4, 6, 8, 1, 3, 5])                                 # 10 > 9 : 10 - 9 = 1

    def test_initial_delay(self):
        h, t = self.advance_time(5, 0, -1, 10, 6)
        self.assertEqual(t, [0, 0, 0, 2, 4, 6])                                    # delay 5: 3 frames at frame 0 (5, 3, 1 >= 1), then time advances

    def test_finite_turn_count_then_stop_on_last_key(self):
        h, t = self.advance_time(0, 0, 2, 6, 12)
        self.assertEqual(t[:9], [2, 4, 6, 2, 4, 6, 6, 6, 6]); self.assertTrue(h['finished'])      # 2 loops then hold at the end

    def test_delay_between_two_turns(self):
        h, t = self.advance_time(0, 4, -1, 4, 8)
        self.assertEqual(t, [2, 4, 2, 0, 0, 2, 4, 2])                              # 2, 4, (6 > 4: remainder 2), delay of 4: 2 frames at 0

    def test_two_independent_clocks(self):
        a = OC._clock(0, 0, -1, 84); b = OC._clock(0, 0, -1, 800)
        for _ in range(100): OC._advance(a); OC._advance(b)
        self.assertEqual(b['time'], 200); self.assertEqual(a['time'], 32)


class TestRotationsEuler(unittest.TestCase):
    """Interpolation of a motion's rotations: Euler angles, linear, component by component (pmv_func: rotateXZY(interpolated rotation)); one game frame = 2 / 60 s."""

    def check(self, c, ticks, expected_euler, msg=''):
        oc = turn(c, ticks)
        np.testing.assert_allclose(map_vertices(oc), (euler_mat(*expected_euler) @ np.array(PTS).T).T, atol=1e-5, err_msg=msg)

    def test_0_to_360_turns_continuously(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (400, (0, 360, 0))], 400)
        for k in range(0, 201, 5): self.check(c, k, (0, 1.8 * k, 0), 'tick %d' % k)       # 400 / 60 s = 200 frames: 1.8 degrees per frame, with no going back at all
        oc = turn(c, 100); np.testing.assert_allclose(map_vertices(oc), np.array(PTS) * [-1, 1, -1], atol=1e-5)     # at mid-course: exact half-turn (not a zero rotation)

    def test_loop_after_one_turn(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (400, (0, 360, 0))], 400)
        for k in (0, 1, 7, 50, 133):
            np.testing.assert_allclose(map_vertices(turn(c, 200 + k)), map_vertices(turn(c, k)), atol=1e-5)      # the second loop exactly repeats the first
        np.testing.assert_allclose(map_vertices(turn(c, 400 + 33)), map_vertices(turn(c, 33)), atol=1e-5)

    def test_four_quarter_turns(self):
        lookup_keys = [(0, (0, 0, 0)), (100, (0, 90, 0)), (200, (0, 180, 0)), (300, (0, 270, 0)), (400, (0, 360, 0))]
        c = auto_map_object(PTS, lookup_keys, 400)
        for tick, ang in ((25, 45), (50, 90), (75, 135), (100, 180), (125, 225), (150, 270), (175, 315), (200, 360)): self.check(c, tick, (0, ang, 0), 'tick %d' % tick)

    def test_negative_angles(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (100, (0, -90, 0)), (400, (0, -360, 0))], 400)
        for tick, ang in ((25, -45), (50, -90), (125, -225), (200, -360)): self.check(c, tick, (0, ang, 0), 'tick %d' % tick)

    def test_no_shortest_path(self):
        """0 -> 270 degrees: the game passes through 135 at mid-course; a quaternion slerp would go backward to -45."""
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (400, (0, 270, 0))], 400)
        self.check(c, 100, (0, 135, 0))
        oc = turn(c, 100); self.assertFalse(np.allclose(map_vertices(oc), (euler_mat(0, -45, 0) @ np.array(PTS).T).T, atol=1e-3))

    def test_component_by_component(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (400, (60, 120, 90))], 400)
        self.check(c, 50, (15, 30, 22.5)); self.check(c, 100, (30, 60, 45))      # Quaternion.Euler(lerp(x), lerp(y), lerp(z)), not the rotation of the intermediate quaternion

    def test_holds_last_keyframe_when_turns_are_finished(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (100, (0, 90, 0))], 100, repeat=2)
        self.check(c, 25, (0, 45, 0)); self.check(c, 50, (0, 90, 0)); self.check(c, 60, (0, 18, 0)); self.check(c, 300, (0, 90, 0))   # 120 > 100: 2nd loop at 20 / 100 (18 degrees), then 90 forever

    def test_a_non_looping_animation_does_not_restart(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (100, (0, 90, 0))], 100, repeat=1)
        self.check(c, 50, (0, 90, 0)); self.check(c, 500, (0, 90, 0))


class TestOneClockPerAnimation(unittest.TestCase):
    """Cause of the healing beam that "turned 5 degrees then came back": the object's motion (800 / 60 s) and mesh sequence (84 / 60 s) shared ONE clock that looped at 84."""

    KEYFRAMES = [(0, (0, 0, 0)), (400, (0, 180, 0)), (800, (0, 360, 0))]

    def test_sequence_does_not_shorten_movement(self):
        c = auto_map_object(PTS, self.KEYFRAMES, 800, seq_end=84)
        oc = turn(c, 100); st = oc.state[0]
        self.assertEqual(st['motion_time'], 200); self.assertEqual(st['sequence_time'], 32)           # each with its own time (before: 32 for both)
        self.assertEqual(oc.auto[0]['motion_clock']['end'], 800); self.assertEqual(oc.auto[0]['sequence_clock']['end'], 84)
        without = auto_map_object(PTS, self.KEYFRAMES, 800); ref = turn(without, 100)
        topmost = map_vertices(oc)[:, 1] - map_vertices(ref)[:, 1]
        np.testing.assert_allclose(map_vertices(oc)[:, [0, 2]], map_vertices(ref)[:, [0, 2]], atol=1e-5)       # the same rotation (90 degrees), with or without a sequence
        self.assertTrue(np.all(np.abs(topmost) <= 0.5 + 1e-6))                           # the sequence only moves the vertices from one frame to the next

    def test_a_full_turn_despite_the_short_sequence(self):
        c = auto_map_object(PTS, self.KEYFRAMES, 800, seq_end=84); without = auto_map_object(PTS, self.KEYFRAMES, 800)
        for k in (0, 10, 50, 100, 150, 200, 250, 399):
            a = map_vertices(turn(c, k)); b = map_vertices(turn(without, k))
            np.testing.assert_allclose(a[:, [0, 2]], b[:, [0, 2]], atol=1e-5, err_msg='tick %d' % k)
            np.testing.assert_allclose(b, (euler_mat(0, 0.9 * k, 0) @ np.array(PTS).T).T, atol=1e-5)          # 800 / 60 s = 400 frames: 0.9 degrees per frame

    def test_shared_animation_one_clock_per_animation(self):
        c = auto_map_object(PTS, [(0, (0, 0, 0)), (800, (0, 360, 0))], 800, seq_end=84, common=True)
        c['motions'][0]['repeat'] = -1; oc = turn(c, 100, common=True)
        self.assertEqual(oc.state[0]['motion_time'], 200); self.assertEqual(oc.state[0]['sequence_time'], 32)
        without = turn(auto_map_object(PTS, [(0, (0, 0, 0)), (800, (0, 360, 0))], 800, common=True), 100, common=True)
        np.testing.assert_allclose(map_vertices(oc)[:, [0, 2]], map_vertices(without)[:, [0, 2]], atol=1e-5)

    def test_state_stored_by_old_version(self):
        """A savestate from before the fix (a single clock: `clock`, flat `auto` entries) reloads and continues without error."""
        c = auto_map_object(PTS, self.KEYFRAMES, 800, seq_end=84); oc = OC.MapObjects(c); sq, eng = oc.auto[0]['sequence'], oc.auto[0]['motion']
        auto_old = {0: dict(sequence=sq, motion=eng, delay=0, loop_delay=0, loops=-1, end=84, time=40, finished=False)}
        old_state = {0: {'model': 1, 'off': False, 'alpha': 31, 'pos': None, 'rot': None, 'motion': eng, 'sequence': sq, 'time': 40}}
        oc.restore(old_state, auto_old)
        self.assertEqual(oc.auto[0]['sequence_clock']['time'], 40); self.assertEqual(oc.auto[0]['motion_clock']['time'], 40)
        oc.tick(); self.assertEqual(oc.state[0]['motion_time'], 42); self.assertEqual(oc.state[0]['sequence_time'], 42)
        for _ in range(50): oc.tick()
        self.assertEqual(oc.state[0]['motion_time'], 142); self.assertEqual(oc.state[0]['sequence_time'], 142 - 84)         # from then on, each loops at its own duration


def expected_clock(end, ticks):
    t = 0
    for _ in range(ticks):
        t += OC.STEP
        if t > end: t -= end
    return t


def real_maps():
    """Maps from the user's cache (`MAP_PREFIX`*.pkl): `DQ_MAP_CACHE`, otherwise /tmp/uicache_coffres; empty if the cache does not exist (the tests below are then skipped)."""
    import glob
    return sorted(glob.glob(os.path.join(os.environ.get('DQ_MAP_CACHE', '/tmp/uicache_coffres'), MAP_PREFIX + '*.pkl')))


@unittest.skipUnless(real_maps(), 'no map cache (%s*.pkl)' % MAP_PREFIX)
class TestRealMaps(unittest.TestCase):
    """The game's real objects: all the chests (model `tbox02` = the lid, `tbox01` = the body), drawers (`hikidashi1b`) and doors of all the maps, played end to end."""

    @staticmethod
    def load(f):
        import pickle
        with open(f, 'rb') as fh: return pickle.load(fh)

    @staticmethod
    def vertices(c, oc, i):
        return np.concatenate([oc.cur[key][d:d + n] for key, d, n in c['spans'][i]]).astype(np.float64)

    def objects(self, pattern):
        """[(map, c, i)] of the objects whose model name ends with `pattern` and that have common animations."""
        res = []
        for f in real_maps():
            c = self.load(f)
            for i, o in enumerate(c['objects']):
                if c['names'].get(i, '').endswith(pattern) and 0 <= o['canim'] < len(c['tabs']) and i in c['spans']: res.append((os.path.basename(f), c, i))
        return res

    def test_all_chests_open_around_their_hinge(self):
        chests = self.objects('tbox02'); self.assertGreater(len(chests), 150)
        caps = set()
        for name_str, c, i in chests:
            o = c['objects'][i]; pos = np.array(o['pos'], np.float64); R = euler_mat(*o['rot']); caps.add(round(o['rot'][1]))
            oc = OC.MapObjects(c); closed = self.vertices(c, oc, i)
            oc.common_anim(i, 2)                                                    # SetCommonAnimation 2 = opening (TownFurnitureObject::openObject), 4 = closing
            for _ in range(20): oc.tick()
            opened = self.vertices(c, oc, i); msg = '%s objet %d cap %s' % (name_str, i, o['rot'])
            np.testing.assert_allclose(np.linalg.norm(opened - pos, axis=1), np.linalg.norm(closed - pos, axis=1), atol=1e-4, err_msg=msg)       # rigid rotation around the model origin (the hinge)
            axis = R @ np.array([1.0, 0.0, 0.0])                                      # the hinge is the chest's X axis
            np.testing.assert_allclose((opened - closed) @ axis, 0.0, atol=1e-4, err_msg=msg)       # no movement along the hinge: the lid never rolls sideways
            topmost = np.argmax(opened[:, 1]); self.assertGreater(opened[topmost, 1] - closed[:, 1].max(), 0.1, msg)    # the free edge rises...
            dec = (opened[topmost] - closed[topmost]) @ (R @ np.array([0.0, 0.0, 1.0]))     # ... and moves back toward the rear of the chest (model +Z, the front is -Z)
            self.assertGreater(dec, 0.1, msg)
        self.assertTrue({90, -90, 180, -180, -27} <= caps or len(caps) > 1, caps)    # non-zero headings exist in the data (ss5b1b, hcy1b1, tcf1, mdi1f1...)

    def test_chests_reclose_to_initial_state(self):
        for name_str, c, i in self.objects('tbox02')[:40]:
            oc = OC.MapObjects(c); closed = self.vertices(c, oc, i)
            oc.common_anim(i, 2)
            for _ in range(20): oc.tick()
            oc.common_anim(i, 4)                                                    # closing
            for _ in range(20): oc.tick()
            np.testing.assert_allclose(self.vertices(c, oc, i), closed, atol=1e-4, err_msg='%s objet %d' % (name_str, i))

    def test_drawers_come_out_toward_the_front_of_the_furniture(self):
        drawers = self.objects('hikidashi1b'); self.assertGreater(len(drawers), 10)
        was_seen = set()
        for name_str, c, i in drawers:
            o = c['objects'][i]; oc = OC.MapObjects(c); closed = self.vertices(c, oc, i)
            oc.common_anim(i, 2)
            for _ in range(20): oc.tick()
            dep = self.vertices(c, oc, i) - closed
            lookup_key = np.array(c['motions'][c['tabs'][o['canim']][1][2]]['keys'][-1][1], np.float64)       # arrival key of animation 2: a drawer slides out toward the front (-Z) of its furniture, by 0.25 (or 1) depending on the model
            self.assertEqual((lookup_key[0], lookup_key[1]), (0.0, 0.0)); self.assertLess(lookup_key[2], 0.0)
            expected = euler_mat(*o['rot']) @ (np.array(o['scl'], np.float64) * lookup_key)  # rotated by the furniture's heading (object frame)
            np.testing.assert_allclose(dep, np.tile(expected, (len(dep), 1)), atol=1e-4, err_msg='%s objet %d cap %s' % (name_str, i, o['rot']))
            was_seen.add(round(o['rot'][1]))
        self.assertGreater(len(was_seen), 1)                                               # drawers with different headings (0, 90, -90, -6, -2)

    def test_doors_opened_around_vertical_hinge(self):
        for pattern in ('door01', 'wdoor04'):
            for name_str, c, i in self.objects(pattern)[:60]:
                o = c['objects'][i]; pos = np.array(o['pos'], np.float64); oc = OC.MapObjects(c); closed = self.vertices(c, oc, i)
                oc.common_anim(i, 2)
                for _ in range(20): oc.tick()
                opened = self.vertices(c, oc, i); msg = '%s objet %d' % (name_str, i)
                np.testing.assert_allclose(opened[:, 1], closed[:, 1], atol=1e-4, err_msg=msg)            # the door turns around the vertical: no height changes
                np.testing.assert_allclose(np.hypot(opened[:, 0] - pos[0], opened[:, 2] - pos[2]), np.hypot(closed[:, 0] - pos[0], closed[:, 2] - pos[2]), atol=1e-4, err_msg=msg)


@unittest.skipUnless(real_maps(), 'no map cache (%s*.pkl)' % MAP_PREFIX)
class TestRealContinuousAnimations(unittest.TestCase):
    """The real maps: healing beam (`kifk01a`, maps cmf1c, dmb2, tab1a) and all the continuous animations."""

    @staticmethod
    def load(name_str):
        import pickle
        for f in real_maps():
            if os.path.basename(f) == MAP_PREFIX + '%s.pkl' % name_str:
                with open(f, 'rb') as fh: return pickle.load(fh)
        return None

    def test_healing_ray_turns_a_full_circle(self):
        was_seen = 0
        for name_str in ('cmf1c', 'dmb2', 'tab1a'):
            c = self.load(name_str)
            if c is None: continue
            io = [i for i, n in c['names'].items() if n.endswith('kifk01a')]; self.assertEqual(len(io), 1, name_str); io = io[0]
            o = c['objects'][io]; eng = c['motions'][o['pmv']]
            self.assertEqual((eng['repeat'], eng['end'], [k[2][1] for k in eng['keys']]), (-1, 800, [0.0, 180.0, 360.0]), name_str)       # data: 0 -> 180 -> 360 in 800 / 60 s, endless
            without = dict(c, imgobj={k: v for k, v in c['imgobj'].items() if k != io})                   # motion only (without the mesh sequence) to measure the rotation
            ref = OC.MapObjects(without); pos0 = np.array(o['pos'], np.float64)
            def pts(oc): return np.concatenate([oc.cur[key][d:d + n] for key, d, n in c['spans'][io]]).astype(np.float64)
            initial = pts(ref)
            for k in (50, 100, 150, 200, 300, 399):
                for _ in range(k - getattr(ref, '_k', 0)): ref.tick()
                ref._k = k
                att = pos0 + (euler_mat(0, 0.9 * k, 0) @ (initial - pos0).T).T                           # 0.9 degrees per frame: 45 degrees at 50 frames, 90 at 100, 180 at 200
                np.testing.assert_allclose(pts(ref), att, atol=2e-4, err_msg='%s tick %d' % (name_str, k))
            actual = OC.MapObjects(c)
            for _ in range(100): actual.tick()
            st = actual.state[io]; self.assertEqual((st['motion_time'], st['sequence_time']), (200, expected_clock(84, 100)), name_str)         # sequence of 84: its own clock
            was_seen += 1
        self.assertGreater(was_seen, 0)

    def test_clocks_of_all_continuous_animations(self):
        """For all the maps: each continuous motion and sequence (no delay) has its time = (2 x frames) wrapped to ITS duration."""
        n_doubles = 0
        for f in real_maps():
            c = self.load(os.path.basename(f)[len(MAP_PREFIX):-4])
            if os.path.basename(f).startswith(MAP_PREFIX + 'btl_'): continue
            oc = OC.MapObjects(c)
            for _ in range(137): oc.tick()
            for i, a in oc.auto.items():
                for h, lookup_key in ((a['sequence_clock'], 'sequence_time'), (a['motion_clock'], 'motion_time')):
                    if h is None or h['loops'] != -1 or h['loop_delay']: continue
                    if h['end'] == 0: continue
                    d0 = (c['sequence_entries'][c['objects'][i]['sequence_object']][3] if lookup_key == 'sequence_time' else a['motion']['delay'])
                    if d0: continue
                    self.assertEqual(oc.state[i][lookup_key], expected_clock(h['end'], 137), '%s objet %d %s' % (os.path.basename(f), i, lookup_key))
                if a['sequence_clock'] and a['motion_clock']: n_doubles += 1
        self.assertGreater(n_doubles, 20)                                                   # dozens of objects have both animations (torches, birds, waterfalls, healing beams...)


if __name__ == '__main__':
    unittest.main(verbosity=2)
