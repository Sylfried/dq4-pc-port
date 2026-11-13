"""Test of the drawing hold during a map change (scenery setup micro-frames) and of the absorption of loading stalls.

The engine sends the new map's scenery (packet 0) one frame BEFORE its camera (packet 10) and the positions of its characters (packet 13); the fade-in starts at the loading frame.
Without a hold, a frame of the previous scene (camera) / without characters was visible under the few percent of opacity left. `State.loading` holds back the drawing (black + fades only) and suspends the fade-in
until the scene is in place, without changing the fade's duration.

  1. pure rules (`State.apply`, `update_loading`, `tick_fade` on fabricated packets);
  2. absorption of stalls (`Game._absorb_blocking`, fake object);
  3. Windows: window manager transitions (`transitions_dwm`, simulated system);
  4. original engine (if --apk and --saves are given): teleports to town maps: the hold lasts at most LOADING_MAX frames, the 1st frame shown is complete (camera sent, characters
     placed) and the fade-in keeps its full duration.

    python3 tests/test_loading.py [--apk "<folder of the patched APKs>" --saves "<folder of the saves>" [--slot 4]]
The saves are only opened read-only: the engine writes to a temporary folder.
"""
import argparse, os, sys, tempfile, time, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.core import engine as ENGINE
from dq4_pc.window import game as F

ARGS = None
OUTPUT, ENTRY = 0x1000, 0                       # bit 12 of packet 9: fade to the color (exit); otherwise entry


def step(e, packets=()):
    """One engine step as seen from the state (Engine.step): frame, packets, end of the hold, fades."""
    e.image += 1; e.apply(list(packets), lambda: 'carte_b'); e.update_loading(); e.tick_fade()


def do_load(duration=10, camera=True):
    """Packets of a map load: scenery, fade-in, one character created (its position arrives in the next frame)."""
    p = [(0, [], []), (9, [ENTRY | duration], []), (12, [0, 5], [])]
    if camera: p.append((10, [3], [0.0, 10.0, -20.0, 0.0, 0.0, 0.0]))
    return p


def covered_state(duration=10):
    """State after a completed fade to black (screen covered), on any map."""
    e = ENGINE.State(); e.game_map = 'carte_a'
    step(e, [(9, [OUTPUT | duration], [])])
    for _ in range(duration + 2): step(e)
    assert e.fade['a'] == 1.0 and e.fade['n'] == 0
    return e


class Rules(unittest.TestCase):
    def setUp(self):
        self.speed = ENGINE.State.fade_speed; ENGINE.State.fade_speed = 1.0

    def tearDown(self): ENGINE.State.fade_speed = self.speed

    def test_held_until_the_scene_is_complete(self):
        e = covered_state(); d = 10
        step(e, do_load(d, camera=False))
        self.assertIsNotNone(e.loading, 'ecran couvert + chargement : dessin retenu')
        self.assertEqual((e.fade['a'], e.fade['n']), (1.0, d), 'the fade-in waits (it has not moved)')
        step(e, [(10, [3], [0.0, 10.0, -20.0, 0.0, 0.0, 0.0])])
        self.assertIsNotNone(e.loading, 'the camera is there, but the created character is not placed')
        step(e, [(13, [0x2000], [1.0, 0.0, 2.0])])
        self.assertIsNone(e.loading, 'camera recue, personnage place : scene en place')
        self.assertAlmostEqual(e.fade['a'], 1.0 - 1.0 / d, 6, 'the fade-in starts at this frame')

    def test_fade_duration_does_not_change(self):
        d = 12; e = covered_state(d)
        step(e, do_load(d)); waiting = 0
        while e.loading is not None: waiting += 1; step(e, [(13, [0x2000], [1.0, 0.0, 2.0])] if waiting == 1 else [])
        n = 1                                                          # (the frame that lifts the hold already does the 1st step of the fade)
        while e.fade['n'] >= 1: step(e); n += 1
        self.assertEqual(n, d, "the game's fade-in keeps its %d frames after the hold" % d)
        self.assertEqual(e.fade['a'], 0.0)

    def test_camera_and_characters_in_same_packets(self):
        e = covered_state()
        step(e, do_load() + [(13, [0x2000], [1.0, 0.0, 2.0])])
        self.assertIsNotNone(e.loading, 'at least one hold frame (LOAD_MIN)')
        step(e)
        self.assertIsNone(e.loading)

    def test_guardrail(self):
        e = covered_state(); step(e, do_load(camera=False)); n = 0
        while e.loading is not None and n < 50: step(e); n += 1
        self.assertIsNone(e.loading, 'the hold never blocks')
        self.assertLessEqual(n, ENGINE.LOADING_MAX, 'frames held (the loading one included) at most LOAD_MAX')

    def test_character_never_placed(self):
        e = covered_state(); step(e, do_load()); n = 0
        while e.loading is not None and n < 50: step(e); n += 1
        self.assertLessEqual(n, ENGINE.LOADING_PLACEMENT, 'waiting for the positions limited to %d frames' % ENGINE.LOADING_PLACEMENT)

    def test_hidden_character_not_awaited(self):
        e = covered_state(); step(e, do_load() + [(14, [0, 0], [])]); step(e)
        self.assertIsNone(e.loading, 'a hidden character needs no position')

    def test_screen_not_covered(self):
        e = ENGINE.State(); e.game_map = 'carte_a'
        step(e, [(0, [], [])])
        self.assertIsNone(e.loading, 'without a fade, original behaviour')
        e = ENGINE.State(); step(e, [(9, [OUTPUT | 10], [])]); step(e); step(e)
        self.assertLess(e.fade['a'], 0.9)
        step(e, [(0, [], [])])
        self.assertIsNone(e.loading, 'fade to black in progress but not covering yet')

    def test_immediate_entry_fade_without_prior_fade(self):
        e = ENGINE.State(); step(e, [(0, [], []), (9, [ENTRY | 1], [])])
        self.assertIsNone(e.loading, 'one-frame fade: nothing to hold (the screen is not covered)')

    def test_entry_fade_with_loading(self):
        e = ENGINE.State(); step(e, [(0, [], []), (9, [ENTRY | 10], [])])
        self.assertIsNotNone(e.loading, 'the fade-in starts again from opacity 1: the screen is covered')

    def test_world_map_waits_for_its_tiles(self):
        e = covered_state(); e.part = ENGINE.PART_FIELD; e.field = None
        step(e, do_load()); step(e, [(13, [0x2000], [1.0, 0.0, 2.0])])
        self.assertIsNotNone(e.loading, 'world map: waiting for the tiles (packet 28)')
        e.field = {'x0': 0, 'y0': 0, 'cols': 1, 'tiles': [0], 'cam': None}; step(e)
        self.assertIsNone(e.loading)

    def test_two_loads_in_a_row(self):
        e = covered_state(); step(e, do_load()); step(e, [(0, [], []), (9, [ENTRY | 10], [])])
        self.assertIsNotNone(e.loading, 'death then church: the hold starts again with the new loading')
        self.assertEqual(e.loading['n'], 0)
        for _ in range(ENGINE.LOADING_MAX + 1): step(e)
        self.assertIsNone(e.loading)

    def test_state_loaded_from_old_save(self):
        e = ENGINE.State(); d = dict(e.__dict__); d.pop('loading')
        e2 = ENGINE.State.__new__(ENGINE.State); e2.__setstate__(d)
        self.assertIsNone(e2.loading)


class Absorption(unittest.TestCase):
    def fake(self, maps=1):
        return types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(loaded_maps=maps)), t_loop=5.0)

    def test_long_frame_after_loading(self):
        j = self.fake()
        F.Game._absorb_blocking(j, time.perf_counter() - 0.3)
        self.assertIsNone(j.t_loop, 'a 300 ms stall is not caught up by the engine')

    def test_normal_frame(self):
        j = self.fake()
        for _ in range(5): F.Game._absorb_blocking(j, time.perf_counter() - 0.004)
        self.assertEqual(j.t_loop, 5.0)

    def test_slow_machine(self):
        j = self.fake()
        for _ in range(3): F.Game._absorb_blocking(j, time.perf_counter() - 0.10)
        self.assertEqual(j.t_loop, 5.0, '100 ms frames (slow machine) are not stalls: the game does not freeze')

    def test_only_the_first_frames_of_a_map(self):
        j = self.fake()
        for _ in range(3): F.Game._absorb_blocking(j, time.perf_counter())
        F.Game._absorb_blocking(j, time.perf_counter() - 0.3)
        self.assertEqual(j.t_loop, 5.0, 'more than 3 frames after the loading: an ordinary slowdown is still subject to the normal catch-up')
        j.engine.state.loaded_maps = 2
        F.Game._absorb_blocking(j, time.perf_counter() - 0.3)
        self.assertIsNone(j.t_loop, 'new map: the count starts again')


class Interpolation(unittest.TestCase):
    """The frame that lifts the hold of a load is not interpolated from the hold state (previous camera): Game._interpolate on a fake object."""
    def fake(self, retained_before, retained_after):
        e = types.SimpleNamespace(part=0xc, game_map='x', loading={'n': 1} if retained_after else None, sprites={}, cam_pos=(0.0, 10.0, -20.0), cam_target=(0.0, 0.0, 0.0), field=None)
        pr = dict(key=(0xc, 'x'), ret=retained_before, sp={}, cam_pos=(0.5, 10.0, -20.0), cam_target=(0.0, 0.0, 0.0), field=None)
        j = types.SimpleNamespace(prev=pr, alpha=0.5, engine=types.SimpleNamespace(state=e)); j._interpolate_camera = types.MethodType(F.Game._interpolate_camera, j); return j

    def test_no_interpolation_on_lift(self):
        j = self.fake(True, False)
        self.assertEqual(F.Game._interpolate(j), [])
        self.assertEqual(j.engine.state.cam_pos, (0.0, 10.0, -20.0))

    def test_ordinary_interpolation(self):
        j = self.fake(False, False)
        saved = F.Game._interpolate(j)
        self.assertTrue(saved); self.assertAlmostEqual(j.engine.state.cam_pos[0], 0.25, places=3, msg='camera halfway between the two steps')


class DWM(unittest.TestCase):
    """Windows: window opening animation turned off during launch (window.transitions_dwm). Here without Windows: the system is simulated."""
    def with_dwm(self, dwm, window):
        import ctypes
        old = sys.platform; sys.platform = 'win32'; ctypes.windll = types.SimpleNamespace(dwmapi=dwm)
        try: return F.transitions_dwm(window, False), F.transitions_dwm(window, True)
        finally: sys.platform = old; del ctypes.windll

    def test_non_windows_nothing_changes(self):
        self.assertFalse(F.transitions_dwm(types.SimpleNamespace(_hwnd=123), False))

    def test_windows_call(self):
        calls = []
        class Dwm:
            def DwmSetWindowAttribute(self, h, attr, ref, size_value): calls.append((h.value, attr, ref._obj.value, size_value)); return 0
        self.assertEqual(self.with_dwm(Dwm(), types.SimpleNamespace(_hwnd=0x1234)), (True, True))
        self.assertEqual(calls, [(0x1234, 3, 1, 4), (0x1234, 3, 0, 4)], 'DWMWA_TRANSITIONS_FORCEDISABLED: 1 to turn off, 0 to turn back on')

    def test_errors_without_consequence(self):
        class Broken:
            def DwmSetWindowAttribute(self, *a): raise OSError('dwmapi absent')
        class Refused:
            def DwmSetWindowAttribute(self, *a): return 0x80070057
        self.assertEqual(self.with_dwm(Broken(), types.SimpleNamespace(_hwnd=1)), (False, False))
        self.assertEqual(self.with_dwm(Refused(), types.SimpleNamespace(_hwnd=1)), (False, False))
        self.assertEqual(self.with_dwm(Refused(), types.SimpleNamespace()), (False, False), 'no window handle')


@unittest.skipIf(ARGS is None and '--apk' not in sys.argv, 'original engine: --apk and --saves required')
class Engine(unittest.TestCase):
    def test_teleports(self):
        eng = ENGINE.Engine(ARGS.apk, ARGS.saves, tempfile.mkdtemp(prefix='sv_test_chg_'))
        eng.load_save(ARGS.slot)
        for _ in range(100): eng.step(0, 0)
        ENGINE.State.fade_speed = 1.0; seen = 0
        for name_str in ('caf1', 'cbf1', 'cdf1', 'mak1f1', 'maout'):
            before = eng.state.loaded_maps; cam0 = eng.state.cam_pos
            eng.start_town(name_str); k = None; trace = []
            for i in range(40):
                eng.step(0, 0); e = eng.state
                if k is None and e.loaded_maps > before: k = i
                if k is not None: trace.append((i - k, e.loading is not None, e.cam_pos, [s['pos'] for s in e.sprites.values() if s.get('visible', True)], e.fade['a'], e.fade['n']))
            self.assertIsNotNone(k, name_str + ' : carte chargee')
            seen += 1
            retained_list = [t for t in trace if t[1]]
            self.assertTrue(retained_list, name_str + ': the loading was held')
            self.assertLessEqual(len(retained_list), ENGINE.LOADING_MAX, name_str)
            is_first = next(t for t in trace if not t[1])
            self.assertIsNotNone(is_first[2], name_str + ': camera sent at the 1st frame shown')
            if seen == 1: self.assertNotEqual(is_first[2], cam0, name_str + ': it is no longer the camera of the previous map (world map; two towns can have the same starting camera)')
            self.assertTrue(all(p is not None for p in is_first[3]), name_str + ': characters placed at the 1st frame shown')
            for t in retained_list: self.assertEqual(t[4], 1.0, name_str + ': screen covered during the hold')
        self.assertEqual(seen, 5)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apk'); ap.add_argument('--saves'); ap.add_argument('--slot', type=int, default=4)
    ARGS, remainder = ap.parse_known_args()
    if not (ARGS.apk and ARGS.saves): ARGS = None
    unittest.main(argv=[sys.argv[0]] + remainder, verbosity=2)
