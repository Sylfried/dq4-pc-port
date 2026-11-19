"""Tests of the 3D model animation (dq456_pc/fbx.py): Hermite curves, player loop, rotation blending.

  python3 tests/test_fbx_anim.py

1. a rotation from 0 to 360 degrees (clip with quaternion keys every 90 degrees, like the game's models: `m_EulerCurves` is empty, the rotations are quaternions) turns CONTINUOUSLY, neither by just a few
   degrees, nor backwards;
2. the time of a looping clip is wrapped modulo its duration (WrapMode.Loop): two turns = one turn; a clip that is not a loop stays on its last frame;
3. the fade between two clips blends the rotations on the same side of the sphere: q and -q are the same rotation, their average must neither cancel out nor make the bone do a half-turn;
   a blend of close rotations (the title dragon case) remains the plain weighted average, unchanged.
"""
import math, os, sys, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.world import fbx as F


def quat_y(deg):
    """Quaternion (x, y, z, w) of a rotation of `deg` degrees around Y."""
    a = math.radians(deg) / 2; return (0.0, math.sin(a), 0.0, math.cos(a))


def quat_curve(degrees_per_key, dt):
    """4-component rotation curve: one quaternion every `dt` seconds, linear tangents (slope from one key to the next), like the resampled keys of the Unity import."""
    t = [dt * k for k in range(len(degrees_per_key))]; v = np.array([quat_y(a) for a in degrees_per_key])
    slope = (v[1:] - v[:-1]) / dt
    sor = np.vstack([slope, slope[-1:]]); ent = np.vstack([slope[:1], slope])
    return F.Curve(t, v, ent, sor)


def one_bone_model(clips):
    """Minimal FbxModel (one bone, no mesh): only `local` is used."""
    m = F.FbxModel.__new__(F.FbxModel)
    m.p0 = np.zeros((1, 3)); m.q0 = np.array([[0.0, 0.0, 0.0, 1.0]]); m.s0 = np.ones((1, 3)); m.clips = clips
    return m


def angle_y(q):
    """Rotation around Y (degrees, between -180 and 180) of a normalized quaternion."""
    q = np.asarray(q, float); q = q / np.linalg.norm(q)
    if q[3] < 0: q = -q
    return math.degrees(2 * math.atan2(q[1], q[3]))


class TestCurves(unittest.TestCase):
    def test_values_at_keyframes(self):
        c = F.Curve([0.0, 1.0, 2.0], [0.0, 10.0, 0.0], [0.0] * 3, [0.0] * 3)
        self.assertEqual((c.value(0.0), c.value(1.0), c.value(2.0)), (0.0, 10.0, 0.0))
        self.assertAlmostEqual(c.value(0.5), 5.0); self.assertAlmostEqual(c.value(1.5), 5.0)       # Hermite with zero slopes: midpoint = average
        self.assertEqual(c.value(-1.0), 0.0); self.assertEqual(c.value(9.0), 0.0)                  # outside the keys: keep the first / last value

    def test_rotation_from_0_to_360_degrees_continuous(self):
        """TzKeys every 90 degrees: the bone's angle grows steadily from 0 to 360 (= 0), without ever going back."""
        c = quat_curve([0, 90, 180, 270, 360], 1.0)
        prev = -1.0
        for k in range(0, 41):
            t = k / 10.0; a = angle_y(c.value(t))
            expected = (90.0 * t) % 360
            was_seen = a % 360
            self.assertAlmostEqual(math.sin(math.radians(was_seen)), math.sin(math.radians(expected)), delta=0.03, msg='t=%.1f' % t)      # nlerp between two 90-degree keys: error < 1 degree
            self.assertAlmostEqual(math.cos(math.radians(was_seen)), math.cos(math.radians(expected)), delta=0.03, msg='t=%.1f' % t)
            if t < 4.0:
                self.assertGreater(was_seen, prev - 1e-9, 't=%.1f : retour en arriere' % t); prev = was_seen      # strictly increasing over the turn


class TestPlayer(unittest.TestCase):
    CLIPS = {'Take 001': {'dur': 2.0, 'wrap': F.LOOP}, 'Take 002': {'dur': 1.0, 'wrap': 1}}

    def test_loop_modulo_duration(self):
        l = F.AnimPlayer(self.CLIPS); l.play(0, True, 0)
        for t in (0.0, 0.4, 1.3, 1.99):
            a = l.poses(t * F.ENGINE_FPS)[0][1]; b = l.poses((t + 2.0) * F.ENGINE_FPS)[0][1]; c = l.poses((t + 6.0) * F.ENGINE_FPS)[0][1]
            self.assertAlmostEqual(a, t, places=6); self.assertAlmostEqual(b, t, places=6); self.assertAlmostEqual(c, t, places=6)      # 1, 2 or 4 turns later: same instant of the clip

    def test_a_non_looping_clip_stays_on_its_last_frame(self):
        l = F.AnimPlayer(self.CLIPS); l.play(1, True, 0)
        self.assertAlmostEqual(l.poses(0.5 * F.ENGINE_FPS)[0][1], 0.5, places=6)
        for t in (1.0, 1.5, 10.0): self.assertAlmostEqual(l.poses(t * F.ENGINE_FPS)[0][1], 1.0, places=6)

    def test_fade_from_loop_increasing_weights(self):
        l = F.AnimPlayer(self.CLIPS); l.play(0, True, 0); l.play(1, False, 30)             # 1 s later: 0.3 s fade to "Take 002"
        p = l.poses(30 + 0.15 * F.ENGINE_FPS)
        self.assertEqual([x[0] for x in p], ['Take 001', 'Take 002']); self.assertAlmostEqual(p[0][2], 0.5); self.assertAlmostEqual(p[1][2], 0.5)


class TestBlendRotations(unittest.TestCase):
    def model(self, qa, qb):
        z = [(0.0, 0.0, 0.0, 0.0)] * 2
        ca = F.Curve([0.0, 1.0], [qa, qa], z, z); cb = F.Curve([0.0, 1.0], [qb, qb], z, z)
        return one_bone_model({'A': {'dur': 1.0, 'wrap': 1, 'curves': [(0, 'rot', ca)]}, 'B': {'dur': 1.0, 'wrap': 1, 'curves': [(0, 'rot', cb)]}})

    def test_q_and_minus_q_same_rotation(self):
        """A = +10 degrees, B = -(-10 degrees) (same rotation as -10, but on the other side of the sphere): at mid-fade, 0 degrees; before: 180 degrees."""
        m = self.model(quat_y(10), tuple(-x for x in quat_y(-10)))
        q = m.local([('A', 0.0, 0.5), ('B', 0.0, 0.5)])[1][0]
        self.assertAlmostEqual(angle_y(q), 0.0, places=6)
        q = m.local([('A', 0.0, 0.25), ('B', 0.0, 0.75)])[1][0]
        self.assertAlmostEqual(angle_y(q), -5.0, delta=0.05)

    def test_same_opposite_rotation_does_not_cancel(self):
        m = self.model(quat_y(40), tuple(-x for x in quat_y(40)))
        q = m.local([('A', 0.0, 0.5), ('B', 0.0, 0.5)])[1][0]
        self.assertAlmostEqual(float(np.linalg.norm(q)), 1.0, places=6); self.assertAlmostEqual(angle_y(q), 40.0, places=6)     # before: zero quaternion

    def test_close_rotations_unchanged(self):
        """On the same side of the sphere: weighted average of the components, as before."""
        qa, qb = quat_y(20), quat_y(80); m = self.model(qa, qb)
        q = m.local([('A', 0.0, 0.3), ('B', 0.0, 0.7)])[1][0]
        np.testing.assert_allclose(q, 0.3 * np.array(qa) + 0.7 * np.array(qb), atol=1e-12)

    def test_a_single_unchanged_pose(self):
        m = self.model(quat_y(20), tuple(-x for x in quat_y(80)))
        np.testing.assert_array_equal(m.local([('B', 0.0, 1.0)])[1][0], np.array([-x for x in quat_y(80)]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
