"""Windows wider than 16:9: outside the 16:9 base, a town or dungeon picture fades into the map's background, so the edge of a finite plane (water, lava, floor) laid on the black
background no longer shows as a hard line. 

    python3 tests/test_wide_sides.py          (offscreen OpenGL: pyglet "headless"; skipped without a GL context)"""
import inspect, os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from pyglet import gl
from dq456_pc.window import menu_display as MD
from dq456_pc.window import game as F

W, H = 420, 120          # 3.5:1


def render(width, e, clear=(0.0, 0.0, 0.0)):
    """Draws the side fade over a white frame in a hidden window -> RGBA array (row 0 = bottom), or None without OpenGL."""
    try: win = pyglet.window.Window(width, H, visible=False)
    except Exception: return None
    try:
        win.switch_to(); gl.glClearColor(1, 1, 1, 1); win.clear()
        fake = types.SimpleNamespace(width=width, height=H, WIDE_BASE=MD.MenusMixin.WIDE_BASE, _clear_color=lambda _e: clear)
        MD.MenusMixin._draw_wide_sides(fake, e)
        buf = (gl.GLubyte * (width * H * 4))(); gl.glReadPixels(0, 0, width, H, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, buf)
        return np.frombuffer(buf, np.uint8).reshape(H, width, 4).copy(), fake
    finally: win.close()


class WideSides(unittest.TestCase):
    def test_fades_into_the_background_gradient(self):
        r = render(W, types.SimpleNamespace(top_background=(0.0, 0.0, 1.0), bottom_background=(1.0, 0.0, 0.0)))
        if r is None: self.skipTest('no OpenGL context')
        a, _ = r; base = H * 16 / 9; inner = int((W - base) / 2)
        self.assertEqual(tuple(a[H // 2, W // 2][:3]), (255, 255, 255))                  # the 16:9 base is untouched
        self.assertEqual(tuple(a[H // 2, inner + 1][:3]), (255, 255, 255))               # ... up to its edge
        near = lambda px, want: max(abs(int(x) - y) for x, y in zip(px[:3], want)) <= 2                # (the edge pixel's center is half a pixel inside the gradient: a software renderer rounds it to 1 / 254)
        self.assertTrue(near(a[H - 1, 0], (0, 0, 255)), tuple(a[H - 1, 0][:3])); self.assertTrue(near(a[0, W - 1], (255, 0, 0)), tuple(a[0, W - 1][:3]))      # window edges: the background itself (top / bottom colors)
        row = a[H // 2, :inner, 1].astype(int)
        self.assertTrue(all(x <= y for x, y in zip(row, row[1:])), 'the fade grows steadily toward the edge')

    def test_clear_color_without_gradient(self):
        r = render(W, types.SimpleNamespace(top_background=None, bottom_background=None), clear=(0.0, 0.0, 0.0))
        if r is None: self.skipTest('no OpenGL context')
        a, _ = r
        self.assertEqual(tuple(a[H // 2, 0][:3]), (0, 0, 0)); self.assertEqual(tuple(a[H // 2, W // 2][:3]), (255, 255, 255))

    def test_nothing_at_16_9(self):
        r = render(int(H * 16 / 9), types.SimpleNamespace(top_background=None, bottom_background=None))
        if r is None: self.skipTest('no OpenGL context')
        a, fake = r
        self.assertTrue((a[..., :3] == 255).all()); self.assertIsNone(getattr(fake, 'program_sides', None))

    def test_only_towns_and_dungeons(self):
        line = next(l for l in inspect.getsource(F).splitlines() if '_draw_wide_sides(e)' in l)
        for cond in ('PART_TOWN', 'not field', 'TITLE_MAP', 'EXTENDED_SKIES'): self.assertIn(cond, line)


if __name__ == '__main__':
    unittest.main(verbosity=2)
