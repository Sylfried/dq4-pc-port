"""Every battle message box has the same size and follows the same position / size rule (set in the interface editor) as the box describing the actions.

The battle start message (type 1, "X apparaît !") had the original 459-unit frame where the action messages (types 2 / 3, enlarged by full_text) have 510; the 4-line message (type 4) too.
`ui_menu.same_box` gives them the actions' frame, place and end-of-page cursor; their own text canvas goes to the top-left corner of the actions' canvas; a 4-line canvas raises the top of the
frame only. Checked on synthetic types, then (if the interface cache exists: DQ_UI_CACHE, otherwise /tmp/uicache4) on the real layout.

  python3 tests/test_battle_message_boxes.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.menus import ui_menu as UM

CACHE = _paths.ui_cache('/tmp/uicache4')


def box(w, h, cw, ch, x0=6.0, top_margin=12.0, win=(-225.0, 10.0, -362.0)):
    """A message type: frame w x h (a 9-slice: rows at 0, 8, h - 8, h), canvas cw x ch from (x0, h - top_margin - ch)."""
    rows = (0.0, 8.0, h - 8.0, h); cols = (0.0, 8.0, w - 8.0, w)
    z1 = h - top_margin; z0 = z1 - ch
    return {'win': list(win), 'frame_mesh': {'vtx': [[x, z] for z in rows for x in cols], 'uv': [], 'tris': []},
            'canvas': {'vtx': [[x0, 0.0, z0], [x0 + cw, 0.0, z0], [x0 + cw, 0.0, z1], [x0, 0.0, z1]], 'uv': [[0, ch / 512], [cw / 512, ch / 512], [cw / 512, 0], [0, 0]], 'tris': []},
            'feed_local': [w / 2, 8.0, 15.5], 'scale': 1.0}


def extent(t):
    v = t['frame_mesh']['vtx']; return (min(p[0] for p in v), max(p[0] for p in v), min(p[1] for p in v), max(p[1] for p in v))


class SameBox(unittest.TestCase):
    def test_start_message_takes_the_actions_box(self):
        ref = box(510.0, 135.6, 490.0, 105.0, x0=6.7, top_margin=13.4, win=(-250.5, 10.0, -296.0)); start = box(459.0, 126.0, 441.0, 102.0)
        t = UM.same_box(start, ref)
        self.assertEqual(extent(t), extent(ref)); self.assertEqual(t['win'], ref['win']); self.assertEqual(t['feed_local'], ref['feed_local'])
        cv = t['canvas']['vtx']; rc = ref['canvas']['vtx']
        self.assertAlmostEqual(min(p[0] for p in cv), min(p[0] for p in rc)); self.assertAlmostEqual(max(p[2] for p in cv), max(p[2] for p in rc))           # (text at the same top-left corner)
        self.assertAlmostEqual(max(p[0] for p in cv) - min(p[0] for p in cv), 441.0); self.assertAlmostEqual(max(p[2] for p in cv) - min(p[2] for p in cv), 102.0)          # (its own canvas: size kept)
        self.assertEqual(t['canvas']['uv'], start['canvas']['uv'])
        self.assertEqual(extent(start), (0.0, 459.0, 0.0, 126.0))                                                                              # (the source is not changed)

    def test_four_lines_raise_the_top_only(self):
        ref = box(510.0, 135.6, 490.0, 105.0, x0=6.7, top_margin=13.4, win=(-250.5, 10.0, -296.0)); four = box(459.0, 188.0, 441.0, 139.0)
        t = UM.same_box(four, ref); x0, x1, z0, z1 = extent(t)
        self.assertEqual((x0, x1, z0), (0.0, 510.0, 0.0)); self.assertAlmostEqual(z1, 135.6 + 34.0)                                          # (same width, same bottom edge, one line higher)
        cv = t['canvas']['vtx']; self.assertAlmostEqual(max(p[2] for p in cv), 122.2 + 34.0); self.assertAlmostEqual(min(p[2] for p in cv), 122.2 + 34.0 - 139.0)


@unittest.skipUnless(os.path.exists(os.path.join(CACHE, 'ui_layout.json')), "cache d'interface absent")
class RealLayout(unittest.TestCase):
    def test_every_battle_box_alike(self):
        ts = UM.PageLayout(os.path.join(CACHE, 'ui_layout.json')).message['types']
        for i in (1, 3, 4): self.assertEqual(ts[i]['win'], ts[2]['win'], i); self.assertEqual(ts[i]['feed_local'], ts[2]['feed_local'], i)
        for i in (1, 3): self.assertEqual(extent(ts[i]), extent(ts[2]), i)
        x0, x1, z0, z1 = extent(ts[4]); e2 = extent(ts[2]); self.assertEqual((x0, x1, z0), e2[:3]); self.assertGreater(z1, e2[3])                # (4 lines: taller, same width and bottom)
        self.assertAlmostEqual(e2[1] - e2[0], 510.0, places=1)
        self.assertNotEqual(extent(ts[0]), e2)                                                                                                   # (the field window keeps its own frame)


if __name__ == '__main__':
    unittest.main(verbosity=1)
