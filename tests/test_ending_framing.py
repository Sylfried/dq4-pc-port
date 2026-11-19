"""Framing of the ending's `mqout` scene: the balloon the old man and the pink-haired girl look at hangs above the wall; in 16:9 the window shows the phone's short side up (12.7 degrees
instead of 22.5) so it fell out of the top of the screen. During the ending (chapter 9) the town camera of that map is raised and widened a little (CameraMixin._ending_framing); nothing changes elsewhere
(other maps, normal play, an fov sent by the engine), and the correction fades out as the window gets taller (it already shows the whole phone height). Without window or engine."""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.window.camera import CameraMixin
from dq456_pc.window.constants import ENDING_FRAMING, TOWN_FOV_DEFAULT


def view(map_name='mqout', chapter=9):
    return types.SimpleNamespace(map_name=map_name, engine=types.SimpleNamespace(story_chapter=lambda: chapter))


def framing(w, e=None, aspect=16 / 9):
    return CameraMixin._ending_framing(w, e or types.SimpleNamespace(cam_fov=None), aspect)


class EndingFraming(unittest.TestCase):
    def test_16_9_during_the_ending(self):
        self.assertEqual(framing(view()), ENDING_FRAMING['mqout'])

    def test_wider_window_same_correction(self):
        self.assertEqual(framing(view(), aspect=21 / 9), ENDING_FRAMING['mqout'])

    def test_nothing_elsewhere(self):
        self.assertEqual(framing(view('caf1')), (0.0, None))
        self.assertEqual(framing(view(chapter=6)), (0.0, None))
        self.assertEqual(framing(view(chapter=5)), (0.0, None))

    def test_engine_fov_wins(self):
        self.assertEqual(framing(view(), types.SimpleNamespace(cam_fov=12.0)), (0.0, None))

    def test_portrait_window_untouched(self):
        up, fov = framing(view(), aspect=9 / 16)
        self.assertEqual(up, 0.0); self.assertAlmostEqual(fov, TOWN_FOV_DEFAULT)

    def test_gradual_in_between(self):
        up, fov = framing(view(), aspect=4 / 3)          # 4:3 shows 1.33 phone short sides up: about half of the correction
        self.assertTrue(0.0 < up < ENDING_FRAMING['mqout'][0]); self.assertTrue(TOWN_FOV_DEFAULT < fov < ENDING_FRAMING['mqout'][1])


if __name__ == '__main__':
    unittest.main()
