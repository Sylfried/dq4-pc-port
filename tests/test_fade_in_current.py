"""A fade-in starts from the plane's CURRENT opacity (Unity's Fade.FadePlane.Command reads the material's alpha): a fade-in on a plane already clear shows nothing.
DQ VI, the end of the prologue: white fade (90 frames), its fade-in (30), then a second fade-in of the front plane when the hero falls from his bed: it was started again from opaque
white, a bright white flash. Until its first fade-in, plane 0 still starts it from opaque (Unity creates it opaque black; an old savestate has no 'known').

    python3 tests/test_fade_in_current.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE


def run(s, frames):
    for _ in range(frames): s.tick_fade()


def fade(s, v): s.apply([(9, [v], [])], lambda: '')


class FadeIn(unittest.TestCase):
    def test_prologue_end_no_white_flash(self):
        s = ENGINE.State(); fade(s, 0x1e); run(s, 30)                         # (the plane's first fade-in: from opaque, as before)
        fade(s, 0x3000 | 90); run(s, 45); self.assertAlmostEqual(s.fade['a'], 0.5, 2); self.assertEqual(s.fade['col'], (1.0, 1.0, 1.0))
        run(s, 45); self.assertEqual(s.fade['a'], 1.0)
        fade(s, 30); self.assertEqual((s.fade['a'], s.fade['n']), (1.0, 30)); run(s, 30); self.assertEqual(s.fade['a'], 0.0)          # white to clear
        fade(s, 0x4000 | 0x1000 | 5); run(s, 5); self.assertEqual(s.background_fade['a'], 1.0)          # the background plane to black (behind the windows)
        fade(s, 33)                                                             # the hero falls from his bed: the front plane is clear
        for _ in range(33): self.assertEqual(s.fade['a'], 0.0, 'no flash'); s.tick_fade()
        self.assertFalse(s.fade_in_progress())

    def test_from_the_current_opacity(self):
        s = ENGINE.State(); fade(s, 0x1e); run(s, 30)
        fade(s, 0x1000 | 20); run(s, 10); a = s.fade['a']; self.assertAlmostEqual(a, 0.5, 2)
        fade(s, 10); self.assertAlmostEqual(s.fade['a'], a); run(s, 5); self.assertAlmostEqual(s.fade['a'], a / 2, 3); run(s, 5); self.assertEqual(s.fade['a'], 0.0)

    def test_first_fade_in_from_opaque(self):
        s = ENGINE.State(); self.assertFalse(s.fade['known']); self.assertTrue(s.background_fade['known'])
        fade(s, 30); self.assertEqual(s.fade['a'], 1.0); self.assertTrue(s.fade['known'])
        old = ENGINE.State(); del old.fade['known']; fade(old, 30); self.assertEqual(old.fade['a'], 1.0, 'an old savestate: as before')

    def test_background_plane_starts_clear(self):
        s = ENGINE.State(); fade(s, 0x4000 | 30); self.assertEqual(s.background_fade['a'], 0.0); self.assertEqual(s.background_fade['n'], 30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
