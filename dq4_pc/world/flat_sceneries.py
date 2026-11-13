"""Flat sceneries stacked at the same height (flower beds on another border, path on lawn...): fix for z-fighting flicker.

Two horizontal triangles at the same height have the same depth to within rounding: the depth test gives one or the other pixel by pixel, and the result changes with every
camera movement (the flowers "flicker"). When a map is loaded, every flat triangle that overlaps another one already drawn at its height is raised very slightly (3 thousandths of a town unit, i.e. less than a tenth of a pixel)
for each triangle stacked below it; the last one drawn always wins. The texture groups are copied: the map cache stays intact.
"""
import numpy as np

STEP = 0.003            # height added per stacked triangle (town units)
TOL_Y = 0.0015         # two flat triangles whose height differs by less than this are considered coplanar
FLAT_TOLERANCE = 1e-3        # a triangle is flat if its three vertices have the same height to within this


def _overlaps(a, b):
    """Do the two triangles (3 x 2, xz plane) have an intersection of nonzero area? Separating axis on each edge."""
    for t in (a, b):
        for i in range(3):
            x0, z0 = t[i]; x1, z1 = t[(i + 1) % 3]
            ax, az = -(z1 - z0), x1 - x0
            pa = [p[0] * ax + p[1] * az for p in a]; pb = [p[0] * ax + p[1] * az for p in b]
            if max(pa) <= min(pb) + 1e-6 or max(pb) <= min(pa) + 1e-6: return False
    return True


def shift(c, log=None):
    """Raises the overlapping flat triangles of `c['groups']` (replaced by a new dictionary of groups; the map cache is not touched). -> number of triangles raised."""
    groups, textures = c['groups'], c['textures']
    raw_value = []                                        # (drawing order, key, triangles T (n, 3, 3), flat indices, heights, cut-out?)
    scenery_top = set()
    for order, (lookup_key, (pos, uv, col)) in enumerate(groups.items()):
        if lookup_key not in textures or len(pos) % 3: continue
        T = np.asarray(pos).reshape(-1, 3, 3)
        idx = np.nonzero((T[..., 1].max(1) - T[..., 1].min(1)) < FLAT_TOLERANCE)[0]
        if not len(idx): continue
        tex = textures[lookup_key]; sliced = bool(tex.ndim == 3 and tex.shape[2] == 4 and (tex[..., 3] < 250).any()) or (isinstance(lookup_key, tuple) and lookup_key[0] == 'tr')
        ys = T[idx, :, 1].mean(1); bucket = np.round(ys / (2 * TOL_Y)).astype(int)
        if sliced: scenery_top.update(bucket.tolist())
        raw_value.append((order, lookup_key, T, idx, ys, bucket, sliced))
    if not scenery_top: return 0
    nearby = np.array(sorted(scenery_top | {h - 1 for h in scenery_top} | {h + 1 for h in scenery_top}))
    flat_items = []                                       # (drawing order, key, triangle index, height, xz triangle, cut-out?): only the triangles at a height where a cut-out triangle is
    for order, lookup_key, T, idx, ys, bucket, sliced in raw_value:
        guard = np.nonzero(np.isin(bucket, nearby))[0]
        for j in guard: flat_items.append((order, lookup_key, int(idx[j]), float(ys[j]), T[idx[j]][:, [0, 2]].astype(float), sliced))
    if len(flat_items) < 2: return 0
    buckets = {}                                       # rounded height -> triangles (the neighboring buckets are also examined: a bucket boundary can separate two close heights)
    for k, p in enumerate(flat_items): buckets.setdefault(int(round(p[3] / (2 * TOL_Y))), []).append(k)
    box = np.array([[p[3], p[4][:, 0].min(), p[4][:, 0].max(), p[4][:, 1].min(), p[4][:, 1].max()] for p in flat_items])        # height, x min / max, z min / max of each triangle
    under = {}                                        # triangle -> triangles drawn before it, at the same height, that it overlaps (at least one of the two is cut-out: two solid, opaque triangles do not visibly flicker)
    for sx, entries in buckets.items():
        deco = [k for k in entries if flat_items[k][5]]
        if not deco: continue
        neighbors = np.array([m for sy in (sx - 1, sx, sx + 1) for m in buckets.get(sy, ())]); B = box[neighbors]
        for d in deco:
            y, x0, x1, z0, z1 = box[d]
            ok = (np.abs(B[:, 0] - y) <= TOL_Y) & (B[:, 2] >= x0) & (B[:, 1] <= x1) & (B[:, 4] >= z0) & (B[:, 3] <= z1) & (neighbors != d)
            for m in neighbors[ok]:
                a, b = flat_items[d], flat_items[int(m)]
                if not _overlaps(a[4], b[4]): continue
                below, above = (int(m), d) if (b[0], b[2]) < (a[0], a[2]) else (d, int(m))
                under.setdefault(above, set()).add(below)
    if not under: return 0
    level = {}
    for k in sorted(under, key=lambda k: (flat_items[k][0], flat_items[k][2])):            # in drawing order: a triangle's level follows that of the triangles below it
        level[k] = 1 + max(level.get(m, 0) for m in under[k])
    new_ones = {}
    for k, n in level.items():
        a = flat_items[k]; lookup_key = a[1]
        if lookup_key not in new_ones: new_ones[lookup_key] = np.array(groups[lookup_key][0], np.float32, copy=True).reshape(-1, 3, 3)
        new_ones[lookup_key][a[2], :, 1] += n * STEP
    g2 = dict(groups)
    for lookup_key, T in new_ones.items(): g2[lookup_key] = (T.reshape(-1, 3), groups[lookup_key][1], groups[lookup_key][2])
    c['groups'] = g2
    if log: log('scenery: %d overlapping flat triangles raised (%d groups)' % (len(level), len(new_ones)))
    return len(level)
