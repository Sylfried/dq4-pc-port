"""All the maps: the sharp sampling of the scenery shows the texels of the DS on every polygon (tools/scan_scenery_sampling.py).

The regression it guards against: moving the sharp sampling to the DS texel coordinate; the polygons whose uv does not vary along an axis and lies exactly on a texel border
(the inner faces of the cave rocks, v = 0.5 / 64: the black bottom row of the texture) were then blended with the next texel over their whole surface, brown instead of black, on
about 250 maps; nothing showed it but a look at a cave. The scan reads the map cache (made from the game's data): skipped without it. The tie of FRAG is read from the program itself.

  python3 tests/test_scenery_sampling_all_maps.py
"""
import glob, os, re, sys, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tools'))
import scan_scenery_sampling as SC
from dq456_pc.window import shaders as SH
from dq456_pc.world.data import MAP_PREFIX

CACHE = os.environ.get('DQ_MAP_CACHE') or os.path.join(ROOT, 'data', 'cache')


def frag_tie():
    m = re.search(r'const float TIE = ([0-9.eE+-]+);', SH.FRAG)
    return float(m.group(1)) if m else 0.0


class Program(unittest.TestCase):
    def test_the_scan_simulates_the_program(self):
        self.assertEqual(SC.TIE, frag_tie())
        self.assertIn('vec2 p = uv * tsize - tshift + TIE; vec2 b = floor(p + 0.5); vec2 w = max(fwidth(p), vec2(1e-4));', SH.FRAG)
        self.assertIn('uv = clamp(b + clamp((p - b) / w, -0.5, 0.5), lo, hi) / tsize;', SH.FRAG)
        self.assertIn('vec2 lo = v_box.xy * tsize - tshift + 0.5, hi = max(v_box.zw * tsize - tshift - 0.5, lo);', SH.FRAG)


@unittest.skipUnless(glob.glob(os.path.join(CACHE, MAP_PREFIX + '*.pkl')), 'no map cache (DQ_MAP_CACHE)')
class AllMaps(unittest.TestCase):
    def test_every_polygon_shows_the_ds_texels(self):
        bad = SC.scan(CACHE, frag_tie(), prefix=MAP_PREFIX)
        self.assertEqual({m: len(b) for m, b in bad.items()}, {}, 'polygons blended over their whole surface')

    def test_the_uv_box_alone_keeps_the_ds_texels(self):
        self.assertNotIn('dab1', SC.scan(CACHE, 0.0, prefix=MAP_PREFIX), 'the uv box alone: a polygon one texel wide or less shows the texel after the border')

    def test_the_scan_sees_the_former_sampling(self):
        bad = SC.scan(CACHE, 0.0, prefix=MAP_PREFIX, boxed=False)                                       # (neither the tie nor the polygon's uv box: the program of that change)
        if os.path.exists(os.path.join(CACHE, MAP_PREFIX + 'dab1.pkl')): self.assertIn('dab1', bad, 'without the tie, the cave rocks of dab1')
        self.assertGreater(len(bad), 100)


if __name__ == '__main__':
    unittest.main()
