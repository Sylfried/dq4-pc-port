"""Dream filter (clouds around the screen): the interludes seen in a dream (save 3, inn of Strattbourg: the
dream at mqout / mqtf3) load the 3D model c2000 (packet 31), which the port could not read (Unity's built-in Plane mesh, shader Custom/FontAlpha8) and did not draw.
  - c2000 is on Unity layer 8, drawn by the interface camera (top view of the XZ plane): a picture over the screen, the white clouds of `white_mask` around a clear middle;
  - the part of its plane that the phone's column shows (x within ±225, z within ±400 of 900 x 1000 units): texture u 0.25 to 0.75, v 0.1 to 0.9;
  - not stretched: the effect's area (the part of the picture that is not opaque) is enlarged until its top and bottom edges touch the window's (portrait: its left and
    right edges); the opaque edge of the picture, then its color (white) beyond the plane, fill the rest;
  - it is read during the preparation (FBX_SCREEN): reading it at the dream made the data pack load then (a visible stall when the dream's scenery loaded).
    python3 tests/test_dream_filter.py            (DQ_APK=<folder of the APKs> for the part on real data)"""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
from dq4_pc.world import fbx as FX
from dq4_pc.world import data as DO

APK = os.environ.get('DQ_APK', '')
PACK = os.path.join(APK, 'split_UnityDataAssetPack.apk')


def overlay(size=(900.0, 1000.0)):
    a = np.zeros((512, 512, 4), np.uint8); a[..., :3] = 255; a[..., 3] = 255; a[160:352, 160:352, 3] = 0
    return {'overlay': True, 'size': size, 'tex': a, 'col': (1.0, 1.0, 1.0, 1.0), 'st': (1.0, 1.0, 0.0, 0.0), 'clips': {}}


class Window(unittest.TestCase):
    def test_phone_column_part_of_the_plane(self):
        m = FX.ScreenOverlay(overlay())
        np.testing.assert_allclose(m.window(), (0.25, 0.1, 0.75, 0.9))
        np.testing.assert_allclose(m.window((45.0, 1.0, 50.0)), (0.0, -0.3, 1.0, 1.3))                  # (a scale given by the engine replaces the prefab's)
        np.testing.assert_allclose(m.window(None, (90.0, 0.0, 0.0)), (0.15, 0.1, 0.65, 0.9))              # (the plane follows the model's position)

    def test_not_stretched(self):
        """one interface unit as wide as high; the effect's area (the transparent middle of the test picture: 192 / 512 of the plane each way, 337.5 x 375 units) takes the whole height of
        a 16:9 window (the rest, left and right, is the picture's white edge then the fill) and the whole width of a portrait window."""
        from dq4_pc.window.helpers import screen_column
        from dq4_pc.window.field import overlay_rects
        m = FX.ScreenOverlay(overlay()); self.assertEqual(m.plane((45.0, 1.0, 50.0)), (450.0, 500.0)); self.assertEqual(m.plane(), (900.0, 1000.0))
        np.testing.assert_allclose(m.area_uv, (0.3125, 0.3125, 0.6875, 0.6875))
        size, pos = m.area(); np.testing.assert_allclose(size, (337.5, 375.0)); np.testing.assert_allclose(pos, (0.0, 0.0, 0.0))
        for W, H in ((1280, 720), (720, 1280)):
            win = m.window(None, pos, column=screen_column(W, H, size)); u0, v0, u1, v1 = win
            X = lambda u: (u - u0) / (u1 - u0) * W; Y = lambda v: (v - v0) / (v1 - v0) * H
            if W > H: self.assertAlmostEqual(Y(0.3125), 0.0, 6); self.assertAlmostEqual(Y(0.6875), H, 6); self.assertGreater(X(0.3125), 0)          # (top and bottom of the area on the window's)
            else: self.assertAlmostEqual(X(0.3125), 0.0, 6); self.assertAlmostEqual(X(0.6875), W, 6); self.assertGreater(Y(0.3125), 0)
            self.assertAlmostEqual((X(1) - X(0)) / (Y(1) - Y(0)), 900 / 1000, 6)                                          # (the plane's own proportions)
            (x0, y0, x1, y1), fills = overlay_rects(win, W, H, m.area_uv)                                                   # only the effect's area is drawn, its edge color fills the rest
            self.assertEqual([side for _, side in fills], ['l', 'r'] if W > H else ['b', 't'])
            if W > H: self.assertEqual((y0, y1), (0.0, H)); self.assertAlmostEqual((x1 - x0) / (y1 - y0), 337.5 / 375, 6)
            else: self.assertEqual((x0, x1), (0.0, W))
        self.assertEqual(overlay_rects((0.0, 0.0, 1.0, 1.0), 450, 800), ((0.0, 0.0, 450.0, 800.0), []))

    def test_feathered_margin(self):
        """around the effect's area, a margin a quarter of its smaller side wide in which the alpha rises from the edge's own to opaque, never back down: no straight line where the scene
        stopped; farther out the edge is blurred, so an irregular edge does not leave streaks."""
        from dq4_pc.window.field import feathered
        m = FX.ScreenOverlay(overlay()); a = m.tex.copy(); a[160:352, 160, 3] = np.linspace(100, 250, 192).astype(np.uint8)          # (a left edge that lets the scene through, more or less)
        out, uv = feathered(a, m.area_uv); k = 48                                                                                   # (192 texels: a margin of 48)
        self.assertEqual(out.shape[:2], (192 + 2 * k, 192 + 2 * k)); np.testing.assert_allclose(uv, (0.3125 - k / 512, 0.3125 - k / 512, 0.6875 + k / 512, 0.6875 + k / 512))
        row = out[k + 50, :k + 1, 3].astype(int)                                                                                    # (from the outer edge to the area's first column)
        self.assertEqual(row[0], 255); self.assertTrue((np.diff(row[::-1]) >= 0).all()); self.assertLessEqual(abs(int(row[k - 1]) - int(a[160 + 50, 160, 3])), 10)
        self.assertTrue((out[0, :, 3] == 255).all() and (out[:, -1, 3] == 255).all())                                              # (the outer border: opaque, like the fill)
        z = np.full((512, 512, 4), 255, np.uint8); z[160:352, 160:352, 3] = 0; z[160:352:2, 160, 3] = 120                           # (a left edge that alternates, texel by texel)
        zo, _ = feathered(z, m.area_uv); mid = zo[k + 50:k + 142, k // 2, 3].astype(int)
        self.assertLess(mid.max() - mid.min(), 6)                                                                                   # (halfway out: no streaks left)
        np.testing.assert_array_equal(out[k:k + 192, k:k + 192, 3], a[160:352, 160:352, 3])                                          # (the picture itself untouched)

    def test_no_clips_and_prepared_at_start(self):
        self.assertEqual(FX.ScreenOverlay(overlay()).clips, {})
        self.assertIn(2000, DO.FBX_SCREEN)


@unittest.skipUnless(os.path.exists(PACK), 'no game data pack (DQ_APK=<folder of the APKs>)')
class RealModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.mkdtemp(prefix='cache_test_dream_')
        cls.d = DO.Data(PACK, cls.cache, log=lambda *a: None)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.cache, ignore_errors=True)

    def test_c2000_is_the_dream_filter(self):
        d = self.d.fbx_model(2000)
        self.assertTrue(d['overlay']); self.assertEqual(d['size'], (900.0, 1000.0))
        a = d['tex']; self.assertEqual(a.shape, (512, 512, 4)); self.assertTrue((a[..., :3] == 255).all())
        self.assertEqual(int(a[256, 256, 3]), 0); self.assertEqual(int(a[0, 0, 3]), 255)                    # (clear middle, white edges)
        m = FX.ScreenOverlay(d); u0, v0, u1, v1 = m.window()
        part = a[int((1 - v1) * 512):int((1 - v0) * 512), int(u0 * 512):int(u1 * 512), 3]
        self.assertEqual(int(part[part.shape[0] // 2, part.shape[1] // 2]), 0); self.assertEqual(int(part[0, 0]), 255)          # (what the screen shows: clouds around, clear middle)
        self.assertTrue(os.path.exists(os.path.join(self.cache, DO.FBX_PREFIX + 'c2000.pkl')))           # (cached: read once)

    def test_preparation_lists_it(self):
        self.assertIn(('fbx', '2000', DO.FBX_PREFIX + 'c2000.pkl'), self.d._elements({'maps': [], 'sheets': [], 'monsters': []}))


if __name__ == '__main__':
    unittest.main(verbosity=1)
