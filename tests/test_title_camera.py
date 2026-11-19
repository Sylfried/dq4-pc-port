"""Title screen camera test (map ev01), no window or engine: `Game._town_camera` is called on a fake object, as in test_town_camera.py.

1. the title has no hero (the engine nevertheless loads sprite 0, hidden): the scene is the original's, fixed horizontal field (fov x 4/3) at the portrait screen 0.5625; the formula "the hero takes a fraction of the
   height" does not apply there (before: zoom of 1.185, logo wider than the portrait area);
2. the same camera, once the window is widened, keeps the middle portrait area 1:1: a scene point projects to the same distance (in pixels) from the center, at the same height, in 1280 x 720 (area 405 x 720)
   and in a 405 x 720 portrait window;
3. the title is CENTERED at any window size: the camera target (the middle of the scene, x = 0) stays in the middle of the image, even if the hero
   sprite keeps a stale position. the camera of ALL maps is the game's (no more common hero zoom, no centering, no leftover from a previous game).

  python3 tests/test_title_camera.py
"""
import os, sys, unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import test_town_camera as T
F = T.F

POS = (0.0, 27.7041015625, -34.181640625)          # title camera read from the engine (frame 400)
TARGET = (0.0, 0.0, 0.0)
POINTS = [np.array(p, float) for p in ((0, 0, 0), (2, 0, 3), (-3, 1, -2), (4, 2, 8), (-4, 0.5, 6))]     # points of the title scene (logo, island, dragon)


def make_view(game_map, sprites, aspect):
    j = T.fake_game(); j.map_name = game_map
    e = T.fake_state(TARGET, TARGET, 10.0); e.cam_pos = POS; e.cam_down = 3.019360065460205; e.cam_far = 150.0; e.sprites = sprites
    return F.Game._town_camera(j, e, aspect)[0]


class TestTitleCamera(unittest.TestCase):
    def test_title_field_of_view_fixed_despite_hidden_hero(self):
        ref = T.unity_ndc(POS, TARGET, 10.0, F.TOWN_NEAR, 150.0, 0.0, F.ASPECT_PORTRAIT, POINTS, bottom=3.019360065460205)
        for sprites in ({}, {0: {'pos': (0.0, 0.0, 0.0)}}):                                  # without a sprite, and with sprite 0 loaded but hidden
            M = make_view('ev01', sprites, F.ASPECT_PORTRAIT)
            worst = float(np.abs(np.array([T.ndc(M, p) for p in POINTS]) - ref).max())
            self.assertLess(worst, 1e-9, sprites)

    def test_portrait_zone_identical_in_wide(self):
        """x of the wide window: (ndc x) x (width / 2) = distance from the center in pixels; y: ndc y x (height / 2). The portrait area of 1280 x 720 is the 405 x 720 portrait window."""
        Mp, Ml = make_view('ev01', {0: {'pos': (0.0, 0.0, 0.0)}}, 405 / 720), make_view('ev01', {0: {'pos': (0.0, 0.0, 0.0)}}, 1280 / 720)
        for p in POINTS:
            xp, yp = T.ndc(Mp, p); xl, yl = T.ndc(Ml, p)
            self.assertAlmostEqual(xp * 405 / 2, xl * 1280 / 2, places=6); self.assertAlmostEqual(yp * 720 / 2, yl * 720 / 2, places=6)

    # ---- the title must be centered, at any window size (the camera is always centered on the hero: the title, having no hero, is exempt)
    ASPECTS = (('portrait 9:16', 405 / 720), ('4:3', 1024 / 768), ('16:10', 1280 / 800), ('16:9', 1280 / 720), ('1430 x 815', 1430 / 815), ('21:9', 2560 / 1080), ('32:9', 32 / 9))

    def hero_view(self, game_map, sprites, aspect):
        j = T.fake_game(); j.map_name = game_map
        e = T.fake_state(TARGET, TARGET, 10.0); e.cam_pos = POS; e.cam_down = 3.019360065460205; e.cam_far = 150.0; e.sprites = sprites
        return F.Game._town_camera(j, e, aspect)[0]

    def test_title_centered_at_any_size(self):
        """The game's target (the origin, in the middle of the logo) is in the middle of the image (NDC x = 0), even with a stale sprite 0 from a previous session 10 u from the target (centering on the hero does not apply to the title)."""
        for sprites in ({}, {0: {'pos': (0.0, 0.0, 0.0)}}, {0: {'pos': (9.0, 0.0, -4.0)}}):
            ref = self.hero_view('ev01', {}, 16 / 9)
            for name_str, asp in self.ASPECTS:
                M = self.hero_view('ev01', sprites, asp)
                self.assertAlmostEqual(T.ndc(M, TARGET)[0], 0.0, places=9, msg='%s heros=%s' % (name_str, sprites))
                self.assertLess(float(np.abs(M - self.hero_view('ev01', {}, asp)).max()), 1e-12, '%s heros=%s' % (name_str, sprites))
            self.assertEqual(ref.shape, (4, 4))

    def test_title_symmetric_left_and_right(self):
        """Two scene points symmetric about the camera's vertical plane (x = +/- a, same depth) give opposite NDC x: nothing leans to one side, at any size."""
        for name_str, asp in self.ASPECTS:
            M = self.hero_view('ev01', {}, asp)
            for a in (1.0, 3.0, 6.0):
                xg, xd = T.ndc(M, np.array([-a, 0.0, 0.0]))[0], T.ndc(M, np.array([a, 0.0, 0.0]))[0]
                self.assertAlmostEqual(xg + xd, 0.0, places=9, msg='%s a=%s' % (name_str, a))


if __name__ == '__main__':
    unittest.main()
