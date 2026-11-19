"""Flat decals laid on the ground (stone paths, flowers, grass, dirt patches...): height above the ground in the game's DATA (maps extracted by `data.py`, cache `carte11_*.pkl`).

Finding (investigation, "the stones float"): the game's scenery shaders (`Custom/fld_normal`, `fld_atest`, `fld_trans`) have NO depth `Offset`; the designers separate the layers
through geometry: each decal layer is laid 0.125 unit (1/8) above the one below (village `maout`: grass y = -0.25, dirt and stones y = -0.125). This test guards that measurement:
if the extraction (sign of y, matrices, cache) changed, the rule would no longer show and it would fail. It does NOT test the rendering.

    DQ_MAP_CACHE=<folder of the cache maps> python3 tests/test_ground_decals.py
"""
import os, pickle, sys, unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.world.data import MAP_PREFIX           # prefix of the map cache, read from the source: hard-coded, this test silently skipped itself after the switch to carte11_

CACHE = os.environ.get('DQ_MAP_CACHE', '')
STEP = 0.125            # overlay unit of the scenery layers


def heights_above_ground(c):
    """For each CUT-OUT flat triangle (alpha < 250 somewhere in its texture) outside transparent groups ('tr'): height above the HIGHEST OPAQUE ground triangle (texture with no alpha < 250)
    beneath it (same x, z). -> (list of heights, number of decals with no ground below, number of decals facing down)."""
    g, T = c['groups'], c['textures']
    tris, cut, tr = [], [], []
    for k, (pos, uv, col) in g.items():
        t = T.get(k)
        if t is None: continue
        P = np.asarray(pos).reshape(-1, 3, 3); tris.append(P)
        cut += [bool((t[..., 3] < 250).any())] * len(P); tr += [isinstance(k, tuple) and k[0] == 'tr'] * len(P)
    P = np.concatenate(tris); cut = np.array(cut); tr = np.array(tr)
    flat = (P[..., 1].max(1) - P[..., 1].min(1)) < 1e-3
    A = (P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 2] - P[:, 0, 2]) - (P[:, 2, 0] - P[:, 0, 0]) * (P[:, 1, 2] - P[:, 0, 2])          # < 0: clockwise seen from above = front face in Unity (Cull Back)
    dec = np.nonzero(flat & cut & ~tr)[0]
    ax, az, bx, bz, cx, cz = P[:, 0, 0], P[:, 0, 2], P[:, 1, 0], P[:, 1, 2], P[:, 2, 0], P[:, 2, 2]
    det = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz); ok = np.abs(det) > 1e-9; ds = np.where(ok, det, 1.0)
    h, without = [], 0
    for d in dec:
        q = P[d].mean(0)
        l0 = ((bz - cz) * (q[0] - cx) + (cx - bx) * (q[2] - cz)) / ds; l1 = ((cz - az) * (q[0] - cx) + (ax - cx) * (q[2] - cz)) / ds; l2 = 1 - l0 - l1
        m = ok & (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6); m[d] = False
        y = l0 * P[:, 0, 1] + l1 * P[:, 1, 1] + l2 * P[:, 2, 1]
        below = m & (y <= q[1] + 1e-4) & ~cut
        if below.any(): h.append(float(q[1] - y[below].max()))
        else: without += 1
    return np.array(h), without, int((A[dec] > 1e-9).sum())


@unittest.skipUnless(os.path.exists(os.path.join(CACHE, MAP_PREFIX + 'maout.pkl')), 'DQ_MAP_CACHE (%smaout.pkl) absent' % MAP_PREFIX)
class GroundDecals(unittest.TestCase):
    def game_map(self, name_str):
        with open(os.path.join(CACHE, MAP_PREFIX + '%s.pkl' % name_str), 'rb') as f: return pickle.load(f)

    def test_maout_stones_one_eighth_above_grass(self):
        c = self.game_map('maout'); h, without, bottom = heights_above_ground(c)
        self.assertGreater(len(h), 300)
        self.assertGreater(np.mean(np.abs(h - STEP) < 0.002), 0.25)                        # the most frequent layer: exactly 0.125 (stones, dirt, flowers on the grass)
        mult = np.abs(h / STEP - np.round(h / STEP)) * STEP < 0.002
        self.assertGreater(np.mean(mult & (h > 0.01)), 0.5)                                # most decals are at a multiple of 0.125 above the ground
        self.assertLess(np.mean(h < 0.02), 0.03)                                           # almost no decal coplanar with the ground (the game has no depth offset)
        self.assertEqual(bottom, 0)                                                           # all facing up: Unity's Cull Back hides no decal

    def test_path_stones(self):
        """Object `020_mast1` (village paving: stones `maisiyk1..4`, dirt `sn02` / `najimi02`, pond `r_mizu02`, 32 x 32 or 64 x 64 textures): all its flat surfaces are at y = -0.125;
        the grass `masiba` (object `018_maoutsb1`) below: y = -0.25."""
        c = self.game_map('maout'); g = c['groups']
        def slices(name_str): return [(key, np.asarray(g[key][0])[start_idx:start_idx + n]) for i, pl in c['spans'].items() if c['names'].get(i) == name_str for key, start_idx, n in pl]      # (group, vertices of THIS object)
        slabs = slices('020_mast1'); grass = slices('018_maoutsb1')
        self.assertGreaterEqual(len(slabs), 7, [k for k, _ in slabs]); self.assertEqual(len(grass), 3)
        for k, V in slabs: self.assertLess(np.abs(V[:, 1] + 0.125).max(), 1e-3, k)         # all the object's vertices at -0.125 (flat surfaces)
        for k, V in grass: self.assertLess(np.abs(V[:, 1] + 0.25).max(), 1e-3, k)

if __name__ == '__main__':
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    unittest.main()
