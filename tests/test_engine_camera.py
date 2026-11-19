"""Town camera with the REAL engine: the player's rotation is the game's own, not a viewer rotation beside it.

On a town field, bits 4 and 5 of the held keys sent to GameUpdate are not A and B but the game's camera buttons (window::NormalControl::checkCamera: 1 = turn left, 2 = right, 3 = back to north);
TownPlayerManager::setCameraRot turns the camera one notch (0x200 out of 65536 per turn: 2.8125 degrees) per engine step, clamped to the place's limits, holds the player during the return to north, and the game itself turns
the walking directions and the sprite rows according to its camera. This is verified on the original game, on the first save that leaves the party free on a town field (the map name does not matter:; with a message open the same bits are A and B, hence the camera buttons are sent on the free field only, see test_entries.py):

  1. a held camera button turns the camera by 2.8125 degrees per step (right: the heading advances toward +X), the other one in the opposite direction; the game keeps the button pending after the step (`Engine.camera_wait`);
  2. `Engine.camera_turn(direction, n)`: exactly n more notches ("Camera speed" setting, wheel-click drag), even after a step that took the button;
  3. both buttons together, a single step: the game brings the camera back to north (heading 0) and holds the player during that time (Global.Flag 4), then releases them;
  4. camera turned, walking up goes in the camera's direction (the game turns the directions: the viewer has nothing to do) and the hero sprite keeps the same row;

Without DQ_APK and DQ_SAVES (folder of the patched APKs and folder of the saves), the real-engine tests are skipped.

    DQ_APK=... DQ_SAVES=... python3 tests/test_engine_camera.py
"""
import math, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _saves as SV
from dq456_pc.core import engine as ENGINE


def spacing(a, b): return (a - b + 180.0) % 360.0 - 180.0


class GameConstants(unittest.TestCase):
    def test_buttons_and_notch(self):
        self.assertEqual((ENGINE.CAM_G, ENGINE.CAM_D), (0x10, 0x20)); self.assertEqual((ENGINE.ROT_CAM_RIGHT, ENGINE.ROT_CAM_LEFT, ENGINE.ROT_CAM_NORTH), (1, 2, 3))
        self.assertAlmostEqual(ENGINE.CAM_STEP, 2.8125)


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'DQ_APK and DQ_SAVES required (real engine)')
class TestRealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix='sv_test_camera_')

        def make():
            m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], tempfile.mkdtemp(dir=cls.folder))
            for _ in range(3): m.step(0, 0)
            return m

        def ready(m):
            """The test needs a free party on a town field (the game only turns the camera there): it does not matter which one."""
            cls.free_state(m)
            return m.state.part == ENGINE.PART_TOWN and not m.msg_visible and not m.flags() & ENGINE.PLAYER_LOCKED_FLAG

        cls.m, cls.slot = SV.pick_save(make, ready, 'a save that leaves the party free on the ground of a town, a dungeon or a tower')

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.folder, ignore_errors=True)

    @staticmethod
    def free_state(m):
        """Closes the arrival message (A key) and leaves the player free: no message, player not locked."""
        for i in range(900):
            if m.msg_visible and i % 12 < 3: m.step(ENGINE.A, ENGINE.A)
            else: m.step(0, 0)
            if i > 150 and not m.msg_visible and not m.flags() & ENGINE.PLAYER_LOCKED_FLAG: break
        for _ in range(20): m.step(0, 0)

    def setUp(self):
        m = self.m
        self.assertEqual(m.state.part, ENGINE.PART_TOWN); self.assertFalse(m.msg_visible); self.assertFalse(m.flags() & ENGINE.PLAYER_LOCKED_FLAG)
        self.return_to_north()

    def cap(self):
        e = self.m.state; return math.degrees(math.atan2(e.cam_target[0] - e.cam_pos[0], e.cam_target[2] - e.cam_pos[2]))

    def step(self, n, held=0, decl=0):
        for _ in range(n): self.m.step(held, decl)

    def return_to_north(self):
        if abs(spacing(self.cap(), 0.0)) > 0.01:
            self.m.step(ENGINE.CAM_G | ENGINE.CAM_D, 0); self.step(40)
        self.assertLess(abs(spacing(self.cap(), 0.0)), 0.01)

    def test_a_button_turns_the_camera_one_notch_per_step(self):
        m = self.m; caps = [self.cap()]
        for _ in range(30): m.step(ENGINE.CAM_D, 0); caps.append(self.cap())
        d = [spacing(b, a) for a, b in zip(caps, caps[1:])]
        self.assertEqual(d[0], 0.0)                                                                  # (the game turns on the step after the button's)
        for v in d[1:]: self.assertAlmostEqual(v, ENGINE.CAM_STEP, delta=0.05)                            # right: the heading advances toward +X
        self.step(3); after = self.cap(); self.step(5); self.assertAlmostEqual(self.cap(), after, places=6)          # button released: the camera stops
        caps = [self.cap()]
        for _ in range(10): m.step(ENGINE.CAM_G, 0); caps.append(self.cap())
        for a, b in list(zip(caps, caps[1:]))[1:]: self.assertAlmostEqual(spacing(b, a), -ENGINE.CAM_STEP, delta=0.05)

    def test_game_keeps_button_pending(self):
        m = self.m
        m.step(ENGINE.CAM_D, 0); self.assertEqual(m.camera_wait(), ENGINE.ROT_CAM_RIGHT)
        m.step(0, 0); self.assertEqual(m.camera_wait(), 0)
        m.step(ENGINE.CAM_G, 0); self.assertEqual(m.camera_wait(), ENGINE.ROT_CAM_LEFT)
        self.step(3)

    def test_n_more_notches(self):
        m = self.m
        for n in (2, 3, 4):
            before = self.cap(); m.step(ENGINE.CAM_D, 0); self.assertEqual(m.camera_wait(), ENGINE.ROT_CAM_RIGHT); m.camera_turn(ENGINE.ROT_CAM_RIGHT, n); self.step(2)
            self.assertAlmostEqual(spacing(self.cap(), before), n * ENGINE.CAM_STEP, delta=0.05, msg=n)       # exactly n notches (the button's notch is one of them)
        before = self.cap(); m.step(ENGINE.CAM_G, 0); m.camera_turn(ENGINE.ROT_CAM_LEFT, 3); self.step(2); self.assertAlmostEqual(spacing(self.cap(), before), -3 * ENGINE.CAM_STEP, delta=0.05)
        before = self.cap(); m.camera_turn(ENGINE.ROT_CAM_RIGHT, 2); self.step(2); self.assertAlmostEqual(spacing(self.cap(), before), 2 * ENGINE.CAM_STEP, delta=0.05)          # (without a prior step: also)

    def test_speed_x2_and_x4_in_continuous_walking(self):
        m = self.m
        for n in (2, 4):
            caps = [self.cap()]
            for _ in range(10):
                m.step(ENGINE.CAM_D, 0); m.camera_turn(ENGINE.ROT_CAM_RIGHT, n); caps.append(self.cap())
            for a, b in list(zip(caps, caps[1:]))[2:]: self.assertAlmostEqual(spacing(b, a), n * ENGINE.CAM_STEP, delta=0.06, msg=n)
            self.return_to_north()

    def test_two_buttons_return_to_north_and_hold_player(self):
        m = self.m
        for _ in range(20): m.step(ENGINE.CAM_D, 0)
        self.step(3); self.assertGreater(abs(spacing(self.cap(), 0.0)), 40.0)
        m.step(ENGINE.CAM_G | ENGINE.CAM_D, 0)                                                              # ONE single step is enough: the game does the rest
        locks = []; caps = []
        for _ in range(40): m.step(0, 0); locks.append(bool(m.flags() & ENGINE.PLAYER_LOCKED_FLAG)); caps.append(abs(spacing(self.cap(), 0.0)))
        self.assertTrue(all(locks[:8])); self.assertFalse(locks[-1])                            # the player is held during the return, then released
        self.assertAlmostEqual(caps[-1], 0.0, places=6); self.assertTrue(all(b <= a + 1e-9 for a, b in zip(caps, caps[1:])))          # return without jerks, by the shortest path, stopping at north
        self.assertEqual(m.camera_wait(), 0)

    def test_walk_relative_to_camera_and_same_sprite_row(self):
        """Camera rotated a quarter turn: "up" makes the hero walk toward the back of the screen (in the direction of the camera), and the sprite always shows the same row: the game takes care of this."""
        m = self.m
        for _ in range(32): m.step(ENGINE.CAM_D, 0)
        self.step(6); cap = self.cap(); self.assertGreater(abs(spacing(cap, 0.0)), 80.0)
        pos = lambda: tuple(float(x) for x in m.state.sprites[0]['pos'])
        p0 = pos(); self.step(18, ENGINE.UP, ENGINE.UP); p1 = pos()
        dx, dz = p1[0] - p0[0], p1[2] - p0[2]
        self.assertGreater(math.hypot(dx, dz), 1.0, 'the hero walked')
        self.assertLess(abs(spacing(math.degrees(math.atan2(dx, dz)), cap)), 12.0)                    # toward the back of the screen
        row = m.state.sprites[0]['dir']; self.step(10)
        self.step(12, ENGINE.UP, ENGINE.UP); self.assertEqual(m.state.sprites[0]['dir'], row)
        self.step(10)


if __name__ == '__main__':
    unittest.main(verbosity=1)
