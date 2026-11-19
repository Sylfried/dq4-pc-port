"""Checks, on every polygon of every map of the cache, that the sharp sampling of the scenery (window/shaders.py FRAG, soft sharp mode: DS texel coordinate t = uv * size - 0.5 + TIE,
pure texels with a one-screen-pixel blend at their borders) shows the texels it means to show: those of the DS, texel floor(t) (the smooth mode, bilinear, is the original game's own
filtering and needs no check). Inside a texel the two agree; only the one-pixel band at the borders blends. A polygon whose uv does not vary along an axis has no band of its own:
fwidth is 0, and if its uv lies exactly on a border, the whole polygon is the blend (the inner faces of the cave rocks, v = 0.5 / 64: brown instead of black before the tie).
A polygon is reported when ALL its sample points are in a blend band and the blend changes the color. Used by tests/test_scenery_sampling_all_maps.py; by hand: python3 tools/scan_scenery_sampling.py <cache folder> [tie]."""
import glob, os, pickle, sys
import numpy as np

TIE = 1e-3                    # as FRAG
POINTS = np.array([[0.3571, 0.3389, 0.304], [0.6283, 0.2049, 0.1668], [0.1871, 0.6413, 0.1716], [0.1547, 0.2219, 0.6234]], np.float64)          # barycentric sample points inside each polygon
# (not simple fractions: the vertices of the DS polygons are on whole texels, and points like 2/3 a + 1/6 b + 1/6 c fall exactly on texel borders, where any sharp sampling blends over a pixel)
THRESHOLD = 8.0               # mean difference (0-255, RGB) above which a polygon lying entirely in a blend band is reported (two texels of nearly the same color: harmless)


def texel(t, ix, iy):
    """RGB of texels (ix, iy) (iy counted from the bottom, as uv: GL rows are the image's rows bottom first), Repeat."""
    h, w = t.shape[:2]
    return t[(h - 1 - np.mod(iy, h)), np.mod(ix, w), :3].astype(np.float64)


def ds_nearest(t, uv):
    """Texel that the DS shows at uv: floor of its texel coordinate."""
    size = np.array(t.shape[1::-1], np.float64); i = np.floor(uv * size - 0.5 + 1e-9).astype(int)
    return texel(t, i[:, 0], i[:, 1])


def original(t, uv):
    """Bilinear filtering of the original at uv (N x 2)."""
    h, w = t.shape[:2]; x = uv[:, 0] * w - 0.5; y = uv[:, 1] * h - 0.5
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    return ((texel(t, x0, y0) * (1 - fx) + texel(t, x0 + 1, y0) * fx) * (1 - fy) + (texel(t, x0, y0 + 1) * (1 - fx) + texel(t, x0 + 1, y0 + 1) * fx) * fy)


def sharp(t, uv, varies, tie=TIE, footprint=0.2, box=None):
    """Color shown by the soft sharp sampling of FRAG (crisp 0.5 to 1.5) at uv (N x 2): p = uv * size - 0.5 + tie, nearest texel border b, blend over one screen pixel around it
    (`footprint`: texels per screen pixel, magnified scenery; along an axis where the polygon's uv does not vary (`varies` False), fwidth is 0: FRAG's floor of 1e-4), kept between
    the centers of the polygon's first and last texel (`box`: its uv min and max, N x 4, as v_box), then GL_LINEAR."""
    size = np.array(t.shape[1::-1], np.float64)
    p = uv * size - 0.5 + tie; b = np.floor(p + 0.5); w = np.where(varies, footprint, 1e-4)
    x = b + np.clip((p - b) / w, -0.5, 0.5)                         # (FRAG: uv = clamp(b + clamp(...), lo, hi) / tsize)
    if box is not None:
        lo = box[:, :2] * size - 0.5 + 0.5; hi = np.maximum(box[:, 2:] * size - 0.5 - 0.5, lo); x = np.minimum(np.maximum(x, lo), hi)
    return original(t, x / size), np.any((np.abs(p - b) < w / 2) & ~varies, axis=1)          # (color, the point is in the blend band of an axis along which the polygon's uv does not vary)


def scan_map(d, tie=TIE, threshold=THRESHOLD, boxed=True):
    """-> [(group key, polygon number, difference)] of the polygons of a map (cache dict: 'groups', 'textures') where the sharp sampling does not show the DS texels (`boxed` False:
    without the polygon's uv box, the program before it)."""
    out = []
    for k, (p, uv, col) in d['groups'].items():
        t = d['textures'].get(k)
        if t is None or len(uv) < 3 or t.ndim != 3: continue
        U = uv.reshape(-1, 3, 2).astype(np.float64); A = col.reshape(-1, 3, 4)[:, :, 3].mean(axis=1)
        flat = ~(np.ptp(U, axis=1) > 1e-6).all(axis=1)                   # polygons whose uv does not vary along an axis (the others have a one-pixel band along their texel borders, by design)
        if not flat.any(): continue
        idx = np.nonzero(flat)[0]; U, A = U[idx], A[idx]
        S = np.einsum('pk,nkc->npc', POINTS, U).reshape(-1, 2)            # (polygons x points, 2)
        V = np.repeat(np.ptp(U, axis=1) > 1e-6, len(POINTS), axis=0)       # (the polygon's uv varies along u, v)
        B = np.repeat(np.concatenate([U.min(axis=1), U.max(axis=1)], axis=1), len(POINTS), axis=0)          # (each polygon's uv box, as the geometry shader)
        c, band = sharp(t, S, V, tie, box=B if boxed else None)
        diff = np.abs(ds_nearest(t, S) - c).mean(axis=1).reshape(len(U), len(POINTS)).mean(axis=1)
        whole = band.reshape(len(U), len(POINTS)).all(axis=1)             # the whole polygon in a blend band
        out += [(k, int(idx[j]), float(diff[j])) for j in np.nonzero(whole & (diff > threshold) & (A > 0.05))[0]]
    return out


def scan(cache, tie=TIE, threshold=THRESHOLD, prefix='map15_', boxed=True):
    """{map name: polygons reported} for every map of the cache folder."""
    res = {}
    for f in sorted(glob.glob(os.path.join(cache, prefix + '*.pkl'))):
        try:
            with open(f, 'rb') as fh: d = pickle.load(fh)
        except Exception: continue
        bad = scan_map(d, tie, threshold, boxed)
        if bad: res[os.path.basename(f)[len(prefix):-4]] = bad
    return res


if __name__ == '__main__':
    r = scan(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else TIE)
    print('%d maps with polygons whose sharp sampling does not show the DS texels' % len(r))
    for m, b in sorted(r.items(), key=lambda x: -len(x[1]))[:40]: print('%-14s %5d polygons, worst %.0f' % (m, len(b), max(x[2] for x in b)))
