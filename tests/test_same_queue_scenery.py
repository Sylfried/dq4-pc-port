"""DQ V: transparent scenery in the characters' own render queue is sorted with them by distance; the world map keeps its width through the water's animation steps; DQ VI's title logo.

  python3 tests/test_same_queue_scenery.py

1. Chara.SetPriorityShader(n) puts the characters in queue 3000 + n (a per-map table of the engine: 11 on most maps); FldObject.set_priority puts a transparent object in 3000 + its
   priority. Lower priority: before the characters (they hide it); higher: after (over them); EQUAL (97 maps: smoke, glows, light, mist): Unity sorts the renderers of one transparent queue
   from the farthest to the nearest (camera to the center of the bounds). They were all drawn before the characters: a light shaft closer than the hero passed behind him.
   FieldMixin._same_queue_objects gives one entry per map object (its distance: the bounds of the whole object) plus what no object covers; hidden objects (vertices at zero) are left out.
2. Engine._world_lost / _world_found: when no grid read from memory matches the engine's tiles at a step, the last matching one stays for WORLD_KEPT steps (the screen's edges flashed:
   the map fell back to the engine's 25 columns), then the window draws the engine's tiles; a new world forgets it.
3. pre_game.ortho_logo: DQ VI's title logo enlarged around its own position, as wide as DQ IV's, never wider than the margin of the window; the other games' untouched.
4. Sound.bgm_alive and Engine.BGM_PLAY_FLAG: DQ VI waits for its jingles through bit 0x200 of the global flag, which Unity drops when the track no longer exists.
"""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
from dq456_pc.menus import pre_game as AP
from dq456_pc.core import engine as ENGINE
from dq456_pc import sound as SOUND
try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq456_pc.window.field import FieldMixin
except Exception as ex:          # (pyglet, numpy, unicorn...: the import alone is enough)
    FieldMixin = None


def quad(x, y, z, n=6): return np.tile(np.array([[x, y, z]], np.float32), (n, 1)) + np.arange(n, dtype=np.float32)[:, None] * 0.01


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class SameQueue(unittest.TestCase):
    def window(self):
        shaft, glow, water, wall = ('tr', 11, 7), ('tr', 11, 8), ('tr', 10, 9), 5
        cur = {shaft: np.concatenate([quad(0, 2, -5), quad(0, 2, 20), quad(9, 9, 9)]), glow: quad(3, 1, 0), water: quad(0, 0, 0), wall: quad(0, 50, -5)}
        spans = {1: [(shaft, 0, 6)], 2: [(shaft, 6, 6), (wall, 0, 6)], 3: [(glow, 0, 6)], 4: [(water, 0, 6)]}          # (object 2: its opaque part is far above; shaft[12:18] belongs to no object)
        f = types.SimpleNamespace(objects=types.SimpleNamespace(cur=cur), spans=spans, map_name='dlf1a')
        f._same_queue_objects = FieldMixin._same_queue_objects.__get__(f)
        return f, shaft, glow

    def test_one_entry_per_object_with_its_distance(self):
        f, shaft, glow = self.window(); eye = (0.0, 2.0, -30.0)
        out = sorted(f._same_queue_objects(11, eye))
        self.assertEqual([(k, d, n) for _, k, d, n in out], [(shaft, 0, 6), (glow, 0, 6), (shaft, 12, 6), (shaft, 6, 6)])          # nearest first: the near shaft, the glow, the uncovered range, the far object
        self.assertAlmostEqual(out[0][0], 25.0, delta=0.1)
        far = [x for x in out if x[1:] == (shaft, 6, 6)][0][0]
        self.assertAlmostEqual(far, float(np.linalg.norm(np.array([0.025, 26.025, 7.525]) - np.array(eye))), delta=0.1)          # (the whole object's bounds: its shaft and its wall)

    def test_other_queues_and_hidden_objects_left_out(self):
        f, shaft, glow = self.window()
        self.assertEqual(f._same_queue_objects(12, (0, 0, 0)), [])
        f.objects.cur[glow][:] = 0.0                                                      # (an object the engine hid, before the first call)
        self.assertNotIn(glow, [x[1] for x in f._same_queue_objects(11, (0, 0, 0))])

    def test_ranges_cached_per_map_and_queue(self):
        f, shaft, glow = self.window(); f._same_queue_objects(11, (0, 0, 0)); first = f._same_queue_cache
        f._same_queue_objects(11, (1, 0, 0)); self.assertIs(f._same_queue_cache, first)
        f.map_name = 'dlf1b'; f._same_queue_objects(11, (0, 0, 0)); self.assertIsNot(f._same_queue_cache, first)

    def test_centers_follow_the_groups_that_changed_only(self):
        """The centers are kept from one frame to the next; a group the step changed (`_queue_dirty`, fed by _map_objects and _orient_scenery) has its objects measured again."""
        f, shaft, glow = self.window(); eye = (0.0, 2.0, -30.0)
        before = {x[1:]: x[0] for x in f._same_queue_objects(11, eye)}
        f.objects.cur[glow] += np.array([0.0, 0.0, 40.0], np.float32)                     # moved, but not reported: the kept center stands
        self.assertEqual({x[1:]: x[0] for x in f._same_queue_objects(11, eye)}, before)
        f._queue_dirty.add(glow); after = {x[1:]: x[0] for x in f._same_queue_objects(11, eye)}
        self.assertAlmostEqual(after[(glow, 0, 6)], before[(glow, 0, 6)] + 40.0, delta=0.5); self.assertEqual(after[(shaft, 0, 6)], before[(shaft, 0, 6)])
        f.objects.cur[glow][:] = 0.0; f._queue_dirty.add(glow)                            # hidden since
        self.assertNotIn(glow, [x[1] for x in f._same_queue_objects(11, eye)])


class WorldKept(unittest.TestCase):
    def engine(self):
        m = ENGINE.Engine.__new__(ENGINE.Engine); m.state = types.SimpleNamespace(world=None); return m

    def test_last_matching_world_stays_a_few_steps(self):
        m = self.engine(); ids = np.zeros((4, 4), np.int32)
        m._world_found(ids, 4, 4, (0, 1, 2)); w = m.state.world; self.assertEqual((w['l'], w['h'], m._anim_seen), (4, 4, (0, 1, 2)))
        for n in range(ENGINE.Engine.WORLD_KEPT): m.state.world = None; m._world_lost(); self.assertIs(m.state.world, w, n)
        m._world_lost(); self.assertIsNone(m.state.world)                               # (then the engine's own tiles)
        m._world_lost(); self.assertIsNone(m.state.world)

    def test_a_match_starts_the_count_again_and_keeps_the_seen_steps(self):
        m = self.engine(); ids = np.zeros((4, 4), np.int32)
        m._world_found(ids, 4, 4, (0, 1, 2)); m._world_lost(); m._world_lost()
        m._world_found(ids, 4, 4, None); self.assertEqual(m._anim_seen, (0, 1, 2)); w = m.state.world          # (matched with the steps of the frame before: the last seen ones stay)
        for n in range(ENGINE.Engine.WORLD_KEPT): m._world_lost(); self.assertIs(m.state.world, w)

    def test_nothing_kept_without_a_match(self):
        m = self.engine(); m._world_lost(); self.assertIsNone(m.state.world)


class OrthoLogo(unittest.TestCase):
    LOGO = np.array([[-121.5, -54.5, 0.0], [127.5, -54.5, 0.0], [127.5, 46.5, 0.0], [-121.5, 46.5, 0.0]], np.float32)          # DQ VI's logo panel (packet 22, at (0, 8))

    def test_dq6_as_wide_as_dq4(self):
        half = 128.53125 / 0.5625 * 16 / 9                                              # the window's half width at 16:9, in the layer's units
        out = AP.ortho_logo(self.LOGO, half, 'dq6'); k = AP.ORTHO_LOGO_SCALE['dq6']
        np.testing.assert_allclose(out[:, :2], self.LOGO[:, :2] * k, rtol=1e-6); np.testing.assert_allclose(out[:, 2], self.LOGO[:, 2])
        self.assertAlmostEqual(362.0 / 1280.0 * k, 0.3129 * AP.LOGO_SCALE, delta=0.004)          # "DRAGON QUEST": 362 px of 1280 in the APK; DQ IV's: 31.29 % x 1.5

    def test_never_wider_than_the_window(self):
        out = AP.ortho_logo(self.LOGO, 128.53125, 'dq6')                                # (a portrait window: the logo already takes 97 % of it)
        np.testing.assert_allclose(out, self.LOGO)
        out = AP.ortho_logo(self.LOGO, 150.0, 'dq6'); w = float(out[:, 0].max() - out[:, 0].min())
        self.assertAlmostEqual(w / 300.0, AP.LOGO_WIDTH_MARGIN, places=4)

    def test_other_games_untouched(self):
        for g in ('dq4', 'dq5'): self.assertIs(AP.ortho_logo(self.LOGO, 400.0, g), self.LOGO)
        self.assertIs(AP.ortho_logo(self.LOGO, 400.0, 'dq6', 1.0), self.LOGO)           # (DQ_LOGO_SCALE=1: the APK's)


class JingleFlag(unittest.TestCase):
    def test_flag_only_in_dq6(self):
        self.assertEqual(ENGINE.BGM_PLAY_FLAG, 0x200 if ENGINE.GM.profile().key == 'dq6' else 0)
        self.assertEqual(ENGINE.HUD_HIDDEN_FLAGS & 0x200, 0)                             # (it never hides the buttons)

    def test_track_alive(self):
        s = SOUND.Sound.__new__(SOUND.Sound) if hasattr(SOUND, 'Sound') else None
        if s is None: self.skipTest('no Sound class')
        s.bgm_queue = []; s.bgm = None; s.bgm_request = None; s.ogg = True; s.ok = True
        self.assertFalse(s.bgm_alive())                                                  # nothing asked, nothing playing: the engine's wait ends
        s.bgm_request = 36; self.assertTrue(s.bgm_alive())                               # asked, still being decoded
        s.ok = False; self.assertFalse(s.bgm_alive())                                    # (no audio device: nothing will ever play)
        s.ok = True; s.bgm = object(); s._bgm_finished = lambda: False; self.assertTrue(s.bgm_alive())
        s._bgm_finished = lambda: True; self.assertFalse(s.bgm_alive())                  # the jingle is over
        s.bgm_queue = [1]; self.assertTrue(s.bgm_alive())


if __name__ == '__main__':
    unittest.main(verbosity=1)
