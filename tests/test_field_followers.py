"""World map: a character walking with the camera (DQ V's hero behind his father) is drawn at a steady distance from it (dq456_pc/window/field_followers.py).
The engine moves the leader and the follower by whole pixels, each with its own pattern of 2 and 3 pixels per step: the follower's distance to the camera went
27, 27, 27, 27, 27, 28, 28, 28... (measured), a one-pixel tremble, five screen pixels on a large window.

    python3 tests/test_field_followers.py
"""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.window.field_followers import FieldFollowers, WINDOW, MAX_LAG

LEADER = (2, 3, 2, 2, 2, 3)              # pixels per step, measured (the camera follows the leader)
FOLLOWER_REL = (27, 27, 27, 27, 27, 28, 28, 28)          # the follower's distance to the camera, measured


def walk(f, steps, static=(500.0, 500.0)):
    """The leader walks up (y decreases), the camera 2 pixels above him, the follower at the measured distances; a character standing still."""
    y = 900.0; shown = []
    for i in range(steps):
        y -= LEADER[i % len(LEADER)]; cam = (100.97, y - 2.0)
        f.step(cam, {0: (100.97, y, 180.0), 1: (100.97, cam[1] + FOLLOWER_REL[i % len(FOLLOWER_REL)], 200.0), 7: static})
        d = f.offset(1) or (0.0, 0.0)
        shown.append(cam[1] + FOLLOWER_REL[i % len(FOLLOWER_REL)] + d[1] - cam[1])
    return shown, cam, y


class Followers(unittest.TestCase):
    def test_steady_distance_while_walking(self):
        f = FieldFollowers(); shown, _cam, _y = walk(f, 40)
        self.assertLess(max(shown[WINDOW:]) - min(shown[WINDOW:]), 0.01)          # 27.375 at every step
        self.assertAlmostEqual(shown[-1], sum(FOLLOWER_REL) / len(FOLLOWER_REL))
        self.assertIsNone(f.offset(0))                                          # the leader: always at the same distance
        self.assertIsNone(f.offset(7))                                          # a character standing still: its exact place while the camera moves

    def test_stop_settles_on_the_true_place(self):
        f = FieldFollowers(); _shown, cam, y = walk(f, 30)
        last = f.offset(1)
        self.assertIsNotNone(last)
        for _ in range(WINDOW + 1): f.step(cam, {0: (100.97, y, 180.0), 1: (100.97, cam[1] + 27.0, 200.0)})
        self.assertIsNone(f.offset(1))                                          # everything stopped: back on its pixel, without a jump (the average moves step by step)

    def test_never_further_than_max_lag(self):
        f = FieldFollowers(); cam = (0.0, 0.0)
        for i in range(12): f.step((0.0, -3.0 * i), {1: (0.0, -3.0 * i + 30.0, 0.0)})          # walking together
        for i in range(12, 20): f.step((0.0, -3.0 * i), {1: (5.0 * (i - 11), -3.0 * i + 30.0, 0.0)})          # the follower turns: 5 pixels a step to the side
        self.assertLessEqual(abs(f.offset(1)[0]), MAX_LAG)

    def test_left_behind_goes_back_to_its_place(self):
        """a character that stops while the camera goes on (a ship left at the coast): its error is halved at each step, never kept"""
        f = FieldFollowers(); _shown, cam, y = walk(f, 30)
        p = f.pos[1] + (200.0,); e0 = abs(f.offset(1)[1])
        f.step((cam[0], cam[1] - 2.0), {1: p}); e1 = abs(f.offset(1)[1])
        self.assertAlmostEqual(e1, e0 / 2)
        for k in range(10): f.step((cam[0], cam[1] - 4.0 - 2 * k), {1: p})
        self.assertIsNone(f.offset(1))

    def test_jump_and_other_place(self):
        f = FieldFollowers(); _shown, cam, y = walk(f, 30)
        f.step((cam[0] + 400.0, cam[1]), {1: (500.0, 0.0, 0.0)})               # forced move: not smoothed
        self.assertIsNone(f.offset(1))
        walk(f, 30); f.step(None, {})                                            # out of the world map: everything forgotten
        self.assertIsNone(f.offset(1)); self.assertEqual(f.tracks, {})

    def test_between_two_steps(self):
        f = FieldFollowers(); f.prev_err = {1: (0.0, 1.0)}; f.err = {1: (0.0, 0.5)}
        self.assertEqual(f.offset(1, 0.5), (0.0, 0.75))
        f.err = {}; self.assertEqual(f.offset(1, 1.0), (0.0, 0.0))             # (settled: down to its place)


try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq456_pc.window import game as G
    from dq456_pc.core import engine as ENGINE
except Exception: G = None


@unittest.skipIf(G is None, 'window not importable here')
class Drawing(unittest.TestCase):
    def test_offset_added_then_put_back(self):
        st = types.SimpleNamespace(part=ENGINE.PART_FIELD, sprites={1: {'pos': (10.0, 20.0, 200.0)}})
        f = FieldFollowers(); f.err = {1: (0.0, 0.375)}; f.prev_err = {1: (0.0, 0.375)}
        g = types.SimpleNamespace(engine=types.SimpleNamespace(state=st), field_followers=f)
        saved = G.Game._follower_offsets(g, [(st.sprites[1], 'pos', (9.0, 19.0, 200.0), False)], 1.0)          # (an interpolation saved first)
        self.assertEqual(st.sprites[1]['pos'], (10.0, 20.375, 200.0))
        for obj, name, old, attr in reversed(saved): obj[name] = old
        self.assertEqual(st.sprites[1]['pos'], (9.0, 19.0, 200.0), 'the step position back after the drawing')


if __name__ == '__main__':
    unittest.main()
