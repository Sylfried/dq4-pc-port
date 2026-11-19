"""Diagonal walk on the world map in pixel perfect and the full screen window one row taller than its monitor. Without the engine, without Windows.

    python3 tests/test_pixel_steps_and_overlays.py

1. Walking diagonally stuttered a little, as if it were quick left / down / left / down moves. Measured on the real engine: the hero
   moves (-2, +2) map pixels every step, both axes together (world map), and the same in towns. The port draws between two steps (Game._interpolate) and, in pixel perfect (the default
   "Shader"), rounds the camera and the sprites to whole map pixels, each coordinate on its own: x (fraction going down) and y (fraction going up) did not reach the next pixel at the
   same frame, so the picture moved left, then down, then left... Now the way covered since the step is rounded (symmetric rounding): both axes change at the same frame.
2. In full screen, the Windows screenshot overlay could not be opened any more: `row_above_screen` makes the window and its OpenGL view one row taller, above the monitor; the
   Windows calls are simulated here."""
import inspect, os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.core import engine as ENGINE
from dq456_pc.window import game as F
from dq456_pc.window import helpers as H
from dq456_pc.window.constants import MODE_PP

PREV, CUR = (2485.967, 393.967, 200.0), (2483.967, 395.967, 200.0)          # hero on the world map, two engine steps (measured)


def drawn(mode, alpha, part=ENGINE.PART_FIELD):
    """(x, y) map pixels where the drawing puts the hero at `alpha` (rounded per coordinate in pixel perfect, as Game._draw_sprites and Camera._field_camera do)."""
    e = types.SimpleNamespace(part=part, game_map='field', loading=None, sprites={0: {'pos': CUR}}, cam_pos=None, cam_target=None, field={'cam': CUR[:2]})
    pr = dict(key=(part, 'field'), ret=False, sp={0: PREV}, cam_pos=None, cam_target=None, field=PREV[:2])
    j = types.SimpleNamespace(prev=pr, alpha=alpha, engine=types.SimpleNamespace(state=e), mode=mode)
    j._interpolate_camera = types.MethodType(F.Game._interpolate_camera, j)
    F.Game._interpolate(j)
    x, y = e.sprites[0]['pos'][:2]; cx, cy = e.field['cam']
    return (round(x), round(y)) if mode == MODE_PP else (x, y), (round(cx), round(cy)) if mode == MODE_PP else (cx, cy)


class DiagonalInPixelPerfect(unittest.TestCase):
    ALPHAS = [k / 100.0 for k in range(100)]          # every moment between two steps (a screen faster than 30 Hz, or an uneven frame time, can draw at any of them)

    def test_both_axes_change_at_the_same_frame(self):
        seen = [drawn(MODE_PP, a)[0] for a in self.ALPHAS] + [(round(CUR[0]), round(CUR[1]))]
        for a, (x0, y0), (x1, y1) in zip(self.ALPHAS, seen, seen[1:]):
            self.assertEqual(abs(x1 - x0), abs(y1 - y0), a)                         # never left alone then down alone (before: between 0.23 and 0.27, then 0.73 and 0.77 of the step)
        self.assertEqual(seen[0], (2486, 394)); self.assertEqual(seen[-1], (2484, 396))

    def test_camera_moves_with_the_hero(self):
        for a in self.ALPHAS:
            (hx, hy), (cx, cy) = drawn(MODE_PP, a)
            self.assertEqual((hx - cx, hy - cy), (0, 0), a)                       # no jitter of the hero on the map

    def test_other_shaders_unchanged(self):
        (x, y), _ = drawn(0, 0.3)
        self.assertAlmostEqual(x, PREV[0] - 0.6); self.assertAlmostEqual(y, PREV[1] + 0.6)

    def test_towns_unchanged(self):
        e = types.SimpleNamespace(part=ENGINE.PART_TOWN, game_map='t', loading=None, sprites={0: {'pos': (1.0, 0.0, 1.0)}}, cam_pos=None, cam_target=None, field=None)
        pr = dict(key=(ENGINE.PART_TOWN, 't'), ret=False, sp={0: (0.0, 0.0, 0.0)}, cam_pos=None, cam_target=None, field=None)
        j = types.SimpleNamespace(prev=pr, alpha=0.3, engine=types.SimpleNamespace(state=e), mode=MODE_PP); j._interpolate_camera = types.MethodType(F.Game._interpolate_camera, j)
        F.Game._interpolate(j); self.assertAlmostEqual(e.sprites[0]['pos'][0], 0.3)

    def test_half_pixels_drawn_evenly(self):
        """the drawing puts a position on a whole pixel with whole_pixels, never with round: Python's round takes halves to the even number (2496.5 -> 2496, 2497.5 -> 2498), so a
        camera or a character on a half pixel moved 0, 2, 0, 2 pixels while the other moved 1, 1, 1: the hero shook by one pixel. The world map camera and the sprites use the same rounding."""
        from dq456_pc.window import camera as CAM
        seen = []
        for x in (2496.5, 2497.5, 2498.5, 2499.5):
            fake = types.SimpleNamespace(mode=MODE_PP); e = types.SimpleNamespace(field={'cam': (x, 100.5)}, field_scale=1.0)
            CAM.CameraMixin._field_camera(fake, e, 16 / 9); seen.append(fake._field_view[0] * 16)
        self.assertEqual([b - a for a, b in zip(seen, seen[1:])], [1.0, 1.0, 1.0])
        src = inspect.getsource(F.Game._draw_sprites) if hasattr(F.Game, '_draw_sprites') else open(F.__file__, encoding='utf-8').read()
        self.assertNotIn("round(s['pos'][0]) if pp", src); self.assertNotIn('round(oc[0]) if pp', src)

    def test_symmetric_rounding(self):
        for v in (0.5, 1.5, 2.5, 0.49, 1.0, 0.0):
            self.assertEqual(H.whole_pixels(-v), -H.whole_pixels(v), v)
        self.assertEqual(H.whole_pixels(0.5), 1.0); self.assertEqual(H.whole_pixels(1.5), 2.0); self.assertEqual(H.whole_pixels(0.49), 0.0)


class RowAboveScreen(unittest.TestCase):
    def run_on(self, window, env=None):
        import ctypes
        calls = []
        user32 = types.SimpleNamespace(SetWindowPos=lambda *a: calls.append(tuple(getattr(v, 'value', v) for v in a)) or 1)
        old = sys.platform; sys.platform = 'win32'; ctypes.windll = types.SimpleNamespace(user32=user32)
        saved = os.environ.pop('DQ_FULL_EXACT', None)
        if env: os.environ['DQ_FULL_EXACT'] = env
        try: return H.row_above_screen(window), calls
        finally:
            sys.platform = old; del ctypes.windll; os.environ.pop('DQ_FULL_EXACT', None)
            if saved is not None: os.environ['DQ_FULL_EXACT'] = saved

    def window(self, full=True):
        return types.SimpleNamespace(_hwnd=11, _view_hwnd=22, fullscreen=full, screen=types.SimpleNamespace(x=1920, y=0, width=2560, height=1440))

    def test_one_row_more_above_the_monitor(self):
        ok, calls = self.run_on(self.window())
        self.assertTrue(ok)
        self.assertEqual([c[:6] for c in calls], [(11, None, 1920, -1, 2560, 1441), (22, None, 0, 0, 2560, 1441)])          # window first, then its view (resizing the window resets the view)

    def test_view_keeps_its_row_after_a_resize(self):
        """pyglet puts the view back at the monitor's size at each WM_SIZE (restored after a minimize, shown again): on_resize gives it its row back, and only while the row is in place."""
        w = self.window(); self.run_on(w)
        import ctypes
        calls = []; old = sys.platform; sys.platform = 'win32'; ctypes.windll = types.SimpleNamespace(user32=types.SimpleNamespace(SetWindowPos=lambda *a: calls.append(tuple(getattr(v, 'value', v) for v in a)) or 1))
        try:
            self.assertTrue(H.keep_row_above(w)); self.assertEqual([c[:6] for c in calls], [(22, None, 0, 0, 2560, 1441)])          # (the view only: no WM_SIZE of the window, so no loop)
            w._row_above = False; calls.clear(); self.assertFalse(H.keep_row_above(w)); self.assertEqual(calls, [])
            w._row_above = True; w.fullscreen = False; self.assertFalse(H.keep_row_above(w)); self.assertEqual(calls, [])
        finally: sys.platform = old; del ctypes.windll
        from dq456_pc.window import full_screen as FS
        self.assertIn('keep_row_above(self)', inspect.getsource(FS.FullScreenMixin.on_resize))
        self.assertIn('self._row_above = False', inspect.getsource(FS.FullScreenMixin._apply_full_screen))

    def test_windowed_or_exact_or_not_windows(self):
        self.assertEqual(self.run_on(self.window(False)), (False, []))
        self.assertEqual(self.run_on(self.window(), env='1'), (False, []))
        self.assertFalse(H.row_above_screen(self.window()))                     # (Linux: nothing)

    def test_drawing_keeps_the_monitor_size(self):
        """pyglet (Win32Window) keeps the monitor's size as the drawing size in full screen: the view's extra row is the top one (off screen), the drawing from the bottom covers the monitor."""
        src = open(os.path.join(os.path.dirname(pyglet.__file__), 'window', 'win32', '__init__.py'), encoding='utf-8').read()          # (the module itself only imports on Windows)
        fb = src[src.index('def get_framebuffer_size'):]; fb = fb[:fb.index('def ', 10)]
        size = src[src.index('def _event_size'):]; size = size[:size.index('def ', 10)]
        self.assertIn('return self._width, self._height', fb); self.assertIn('if not self._fullscreen:', size)


if __name__ == '__main__':
    unittest.main(verbosity=2)
