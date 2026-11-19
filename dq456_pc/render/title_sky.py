# -*- coding: utf-8 -*-
"""Title screen sky in wide format (pure functions: no OpenGL calls, everything can be tested without a window).

The original lays out the title for a portrait screen (9:16). Its sky (object "kumo", model 000_kumo2) is a carpet of IDENTICAL cloud tiles: 4 rows (stacked in the height, offset by half a tile
from one another) of 3 tiles of 11.5 units; the object slides by 0.0192 unit per frame then comes back (period 11.5): the portrait area sees less than one tile in width. In 16/9, 21/9 or wider,
the same tile appeared 3 to 6 times in a row, as is: the repetition was plain to see.

DEFAULT RENDERING: the original background at the height of the phone's portrait screen, in the middle of the 16:9 landscape screen, and the left and right
edges extended by continuing the animation smoothly (not a mere copy). The title camera already keeps the phone's whole height: the portrait area shows the original sky exactly. On each
side, bands continue it EXACTLY (`WideSky(deform=False)`: the original's own u and v, scrolling followed), and a variant of the cloud tile (`variant_tile`: strips of the tile shifted sideways, soft wavy
joins, contrast kept, top and bottom rows untouched) is laid over them with an alpha rising from 0 at the edge of the area to 1 at VARIANT_RAMP tiles (`WideSky.side_layers`): no seam at the edge, and
the sides (one variant on the left, another on the right) no longer repeat what the middle shows; the whole scrolls together. `DQ_SKY_FLAT=1`: the flat rendering below.

FLAT RENDERING (the default): "adjust the height to automatically fit the window height, and the repetition will be along the width, and do apply the visual effects as agreed": the sky is drawn flat, at screen scale (`screen_sky`): the texture (square, 256 x 256) has the window's HEIGHT as its height, at any window size, with no additional enlargement; it repeats across the
WIDTH (1.78 times in 16/9); the wave effect of the old band rendering (undulating horizontal stretch 0.52 to 1.48 times and vertical slide, `STRETCH` / `SLIDE`) is applied to the whole width, fixed on screen while
the texture scrolls underneath (the clouds deform as they pass): the copies of the same tile therefore do not look alike; the tint gradient of the original rows (orange at the top and bottom, white in the middle) is taken over as it appeared
on screen (`screen_gradient`); the scrolling keeps the original speed (one tile per 11.5 units of object slide, i.e. 599 engine frames). The previous renderings remain available: `DQ_SKY_ENLARGED=1`
(trial below), `DQ_SKY_BANDS=1` (bands), `DQ_SKY_COPIES=1` (copies).

TRIAL (enlarged, `DQ_SKY_ENLARGED=1`): the sky image is ENLARGED around the center of the screen (`screen_zoom`: x 3.16 in 16/9) so that the whole window shows only what the portrait area of the original game showed: a single
tile, never repeated; no more bands. The old solution (stretched bands, below) remains available with DQ_SKY_BANDS=1 for comparison.

Previous solution (bands): the central portrait area (width = height x 9/16) remains EXACTLY the original sky; on each side, starting from its edge, bands with the same geometry as the sky rows
(same y, z, same vertex colors) take up the texture again with a horizontal stretch that varies smoothly along the band (from 0.52 to 1.48 times the original size, average 1: same overall scale), and a vertical slide of the texture inside each row (zero at its edges: the seams between rows remain those of the original), with different phases on the left and right: the same cloud shape no longer appears twice at the same place or at the same size. The stretch equals 1 at the edge of the zone:
continuous join, no seam. The texture coordinates follow the scrolling of the object (the join at the edge remains exact at each frame).
"""
import math
import numpy as np

ASPECT_PORTRAIT = 0.5625              # SceneCamera.ASPECT_DEF: portrait screen 450 x 800
STEP_PER_TILE = 16                  # band columns per tile (11.5 units): the stretch varies over ~ 0.6 tile, at least 9 columns per undulation
STRETCH = ((0.30, 0.61, 0.0), (0.18, 1.37, 1.7))        # (amplitude, wavelength in tiles, phase) of the two undulations of the horizontal stretch (sum of the amplitudes < 1: the direction of the texture never reverses)
SIDE_PHASE = (0.0, 2.3)                                 # phases added on the left (0) and on the right (1): two different sides
SLIDE = ((0.03, 1.9, 0.5),)                           # same for the vertical slide of the texture in the middle of each row (fraction of the tile height); zero at the row edges: their join is intact
SUB_ROWS = 4                                        # a row of the bands is cut into 4 to follow the slide (zero at the row edge, maximal in the middle)
RAMP = 0.6                                             # distance (in tiles) over which the effect rises from 0 to 1 (cubic smoothing): join without a break at the edge of the zone
import os
if os.environ.get('DQ_SKY_PARAMS'):                                    # (test) "a1,a2,slide,slide_length": tuning trials
    _p = [float(x) for x in os.environ['DQ_SKY_PARAMS'].split(',')]
    STRETCH = ((_p[0], STRETCH[0][1], STRETCH[0][2]), (_p[1], STRETCH[1][1], STRETCH[1][2])); SLIDE = ((_p[2], _p[3], 0.5),)
MAX_COLUMNS = 600                                      # safeguard (absurdly wide window)


TILE_WIDTH = 1.0                    # flat rendering: width of a tile on screen, in window heights (square texture: 1)
TILE_COLUMNS = 24                    # mesh columns per tile (the shortest wave of the stretch: 0.61 tile, i.e. 14 columns)
SCREEN_LINES = 9                       # mesh lines in the height (profile of the vertical slide and tint gradient; the gradient cuts are added to them)
if os.environ.get('DQ_SKY_TILE'):                                     # (test) tile width in window heights
    try: TILE_WIDTH = max(0.2, float(os.environ['DQ_SKY_TILE']))
    except ValueError: pass


def stretch_plate(d):
    """Flat rendering: texture abscissa (in tiles) at distance `d` (in tiles, array) from the left edge of the window. Exact integral of 1 + sum of the `STRETCH` waves: G(0) = 0, slope between 0.52 and 1.48 (never a reversal),
    overall scale 1 (the sum of the waves has zero mean). Same wave effect as the bands, but periodic and without a ramp: it applies to the whole width."""
    d = np.asarray(d, float); G = d.copy()
    for a, lg, ph in STRETCH:
        w = 2.0 * math.pi / lg
        G = G + a / w * (math.cos(ph) - np.cos(w * d + ph))
    return G


def flat_sliding(d):
    """Flat rendering: vertical slide of the texture (fraction of its height, before the sin(pi t) profile that cancels it at the top and bottom of the window) at distance `d` (tiles) from the left edge."""
    d = np.asarray(d, float); g = np.zeros_like(d)
    for a, lg, ph in SLIDE: g = g + a * np.sin(2.0 * math.pi * d / lg + ph)
    return g


def screen_gradient(M, rows, x_probe):
    """Tint gradient of the original sky as it appears on screen: -> (y, colors): `y` = increasing normalized screen ordinates (-1 bottom, +1 top), `colors` (n, 4) = corresponding vertex color, from the
    projection (matrix `M`) of the edges and of a few intermediate points of each original row (the color is linear in the world, not on screen). Points outside the lens (behind the camera) are ignored."""
    M = np.asarray(M, float); ys, cs = [], []
    for r in rows:
        t = np.linspace(0.0, 1.0, 9)
        y = r.bottom[0] + t * (r.topmost[0] - r.bottom[0]); z = r.bottom[1] + t * (r.topmost[1] - r.bottom[1])
        h = M @ np.stack([np.full_like(y, x_probe), y, z, np.ones_like(y)])
        ok = h[3] > 1e-6
        if not ok.any(): continue
        ys.append((h[1][ok] / h[3][ok])); cs.append(np.asarray(r.bottom[3], float)[None] + t[ok, None] * (np.asarray(r.topmost[3], float) - np.asarray(r.bottom[3], float))[None])
    if not ys: return np.array([-1.0, 1.0]), np.ones((2, 4))
    y = np.concatenate(ys); c = np.concatenate(cs); o = np.argsort(y, kind='stable')
    y, c = y[o], c[o]
    guard = np.concatenate([[True], np.diff(y) > 1e-9]); return y[guard], c[guard]


def screen_sky(aspect, phi_tiles, gradient=None, tile=None, lines=None):
    """Flat sky, at screen scale: triangles (positions, texture coordinates, colors) in normalized coordinates (x and y from -1 to 1, depth at the back), for a window of width / height ratio `aspect`. The texture has the window's height as its height (v from 0.998 at the bottom to 0.002 at the top, like the original rows) and `tile` window heights as its width (`TILE_WIDTH`); it repeats across the
    width (u in tiles, texture in REPEAT). `phi_tiles` = scrolling of the object in tiles (the content slides toward +x when it increases, like the original object). `gradient` = (y, colors) from `screen_gradient` (white if None).
    The stretch (`stretch_plate`) and the slide (`flat_sliding`) are fixed on screen: the texture scrolls underneath."""
    tile = TILE_WIDTH if tile is None else float(tile); aspect = float(aspect)
    tile_ndc = 2.0 * tile / aspect; dx = tile_ndc / TILE_COLUMNS
    K = int(math.ceil(2.0 / dx)) + 1
    i = np.arange(K + 1); X = -1.0 + i * dx; d = i / float(TILE_COLUMNS)                 # d: tiles from the left edge
    t = np.linspace(0.0, 1.0, (SCREEN_LINES if lines is None else int(lines)) + 1)
    if gradient is not None:                                                                  # the gradient cuts (edges of the original rows) become mesh lines
        yc = (np.asarray(gradient[0], float) + 1.0) / 2.0
        t = np.unique(np.round(np.concatenate([t, yc[(yc > 0.0) & (yc < 1.0)]]), 6))
    if gradient is None: col = np.ones((len(t), 4))
    else: col = np.stack([np.interp(2.0 * t - 1.0, gradient[0], gradient[1][:, k]) for k in range(4)], axis=1)
    U = stretch_plate(d) - float(phi_tiles)
    dv = flat_sliding(d)
    uu = np.repeat(U[:, None], len(t), axis=1)
    vv = 0.998 - 0.996 * t[None] + dv[:, None] * np.sin(math.pi * t)[None]
    pos = np.zeros((K + 1, len(t), 3)); pos[:, :, 0] = X[:, None]; pos[:, :, 1] = (2.0 * t - 1.0)[None]; pos[:, :, 2] = BACKGROUND_Z
    uv = np.stack([uu, vv], axis=2); cc = np.repeat(col[None], K + 1, axis=0)
    tri_indices = lambda a: WideSky._triangles(a)
    return tri_indices(pos).astype(np.float32), tri_indices(uv).astype(np.float32), tri_indices(cc).astype(np.float32)


BACKGROUND_Z = 0.9999                          # depth (normalized) of the flat sky: at the back, in front of the far plane (the GL_LESS depth test lets it through), behind everything else


def zone_portrait(width_px, height_px):
    """9:16 portrait column in the middle of the window, in pixels: (x of the left edge, width). The whole window when it is narrower than (or equal to) the portrait."""
    wz = min(float(width_px), float(height_px) * ASPECT_PORTRAIT)
    return (width_px - wz) / 2.0, wz


def half_zone_ndc(aspect):
    """Half-width of the portrait area in normalized screen coordinates (-1..1) for a window of width / height ratio `aspect`."""
    return min(1.0, ASPECT_PORTRAIT / float(aspect))


def screen_zoom(aspect):
    """Zoom (trial) of the title screen sky, centered on the screen: 1 for a window as narrow as the portrait (or narrower), otherwise `aspect / ASPECT_PORTRAIT` (16/9: x 3.16; 21/9: x 4.15): the whole window
    then shows what only the portrait area of the original game showed (less than one tile of clouds in width), so the same tile is never repeated in it. `DQ_SKY_ZOOM` (test) forces a value."""
    try:
        if os.environ.get('DQ_SKY_ZOOM'): return max(1.0, float(os.environ['DQ_SKY_ZOOM']))
    except ValueError: pass
    return max(1.0, float(aspect) / ASPECT_PORTRAIT)


def zoom_matrix(M, z):
    """Projection matrix `M` (4 x 4, columns of the homogeneous coordinate space) followed by an enlargement `z` of the image around the center of the screen (screen x and y multiplied by z; the depth does not change)."""
    S = np.diag([float(z), float(z), 1.0, 1.0])
    return S @ np.asarray(M, float)


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _waves(t, waves, side):
    return sum(a * np.sin(2.0 * math.pi * t / lg + ph + SIDE_PHASE[side]) for a, lg, ph in waves)


def deformation(d, side, period=11.5):
    """Deformation of the texture at distance `d` (world units, array) from the edge of the portrait area, on `side` 0 (left) or 1 (right).
    -> (G, dv): G = texture abscissa traveled, in world units (G(0) = 0, G'(0) = 1, G' stays between 0.52 and 1.48: monotonic, and overall G ~ d: same scale). dv = vertical slide (fraction of texture, dv(0) = 0, dv'(0) = 0): the
    builder applies it with a sin(pi t) profile over the height of each row, because the sky rows are stacked with a half-tile offset and only join if their edges read the texture from v = 0 to 1."""
    d = np.asarray(d, float)
    step = period / 256.0
    n = int(math.ceil(float(d.max() if d.size else 0.0) / step)) + 2
    td = np.arange(n) * step / period                                   # fine table (1/256 of a tile), integrated by the trapezoid rule: G exact to the precision of the table, deterministic
    s = 1.0 + _smooth(td / RAMP) * _waves(td, STRETCH, side)
    G = np.concatenate([[0.0], np.cumsum((s[1:] + s[:-1]) * 0.5 * step)])
    dv = _smooth(d / period / RAMP) * _waves(d / period, SLIDE, side)
    return np.interp(d, np.arange(n) * step, G), dv


class Row:
    """A row of sky tiles: bottom / top edge (y, z, v, color), tiles (xg, xd, ug, ud) and period."""
    def __init__(self, bottom, topmost, quads):
        self.bottom, self.topmost = bottom, topmost
        self.quads = quads                                              # (n, 4): left / right abscissa, left / right u, sorted by abscissa
        x0, x1 = float(quads[0, 0]), float(quads[-1, 1])
        self.x0 = x0
        self.period = (x1 - x0) / (len(quads) / 2.0)                   # 2 half-tiles = 1 texture tile
        k = max(1, len(quads) // int(round((x1 - x0) / self.period)))
        one = quads[:k]
        self.quad_tile = one
        self.rate = float((one[:, 3] - one[:, 2]).sum() / (one[:, 1] - one[:, 0]).sum())      # u per world unit

    def u(self, x):
        """u of the original sky texture at abscissa `x` (array, excluding scrolling), exactly that of the quadrilaterals (including beyond the 3 tiles: the pattern repeats)."""
        x = np.asarray(x, float)
        xr = self.x0 + np.mod(x - self.x0, self.period)
        i = np.clip(np.searchsorted(self.quad_tile[:, 0], xr, side='right') - 1, 0, len(self.quad_tile) - 1)
        xg, xd, ug, ud = self.quad_tile[i].T
        return ug + (xr - xg) / np.maximum(xd - xg, 1e-9) * (ud - ug)


def analyze(pos, uv, col):
    """Sky rows from the object's vertices (N vertices, N a multiple of 6: triangles of quadrilaterals aligned on x and y). ValueError if the structure is not the expected one."""
    pos = np.asarray(pos, float); uv = np.asarray(uv, float); col = np.asarray(col, float)
    if len(pos) == 0 or len(pos) % 6: raise ValueError('sky: %d vertices' % len(pos))
    P, U, C = pos.reshape(-1, 6, 3), uv.reshape(-1, 6, 2), col.reshape(-1, 6, 4)
    rank = {}
    for p, u, c in zip(P, U, C):
        xg, xd = float(p[:, 0].min()), float(p[:, 0].max()); yb, yh = float(p[:, 1].min()), float(p[:, 1].max())
        if xd - xg < 1e-6 or yh - yb < 1e-6: raise ValueError('sky: degenerate quad')
        g, d, b, h = (np.abs(p[:, 0] - xg) < 1e-4), (np.abs(p[:, 0] - xd) < 1e-4), (np.abs(p[:, 1] - yb) < 1e-4), (np.abs(p[:, 1] - yh) < 1e-4)
        if not (np.all(g | d) and np.all(b | h)): raise ValueError('sky: quad not aligned')
        corner = lambda m: (float(p[m, 1].mean()), float(p[m, 2].mean()), float(u[m, 1].mean()), c[m].mean(0))
        bottom, topmost = corner(b), corner(h)
        rank.setdefault((round(yb, 2), round(yh, 2)), {'bottom': bottom, 'top': topmost, 'q': []})['q'].append((xg, xd, float(u[g, 0].mean()), float(u[d, 0].mean())))
    out = []
    for k in sorted(rank):
        r = rank[k]; q = np.array(sorted(r['q']), float)
        if len(q) < 2 or len(q) % 2 or np.abs(q[1:, 0] - q[:-1, 1]).max() > 1e-3: raise ValueError('sky: row not contiguous')
        ra = Row(r['bottom'], r['top'], q)
        if len(q) > 2 and np.abs(q[2:, 2:] - q[:-2, 2:]).max() > 0.01: raise ValueError('sky: row not periodic')
        out.append(ra)
    return out


def zone_edges(M, rows, half, x_probe, ui_scale=33):
    """World abscissas where the portrait area (|screen x| <= half) and the whole window (|screen x| <= 1) intersect the sky, on the VISIBLE part of the rows (|screen y| <= 1.02).
    -> (zone_bottom, zone_top, screen_bottom, screen_top): outer bounds of the zone (no point of the zone outside [zone_bottom, zone_top]) and of the window; None if nothing is visible."""
    M = np.asarray(M, float); t = np.linspace(0.0, 1.0, ui_scale)
    zb, zh, eb, eh = [], [], [], []
    for r in rows:
        y = r.bottom[0] + t * (r.topmost[0] - r.bottom[0]); z = r.bottom[1] + t * (r.topmost[1] - r.bottom[1])
        cl = np.stack([np.full_like(y, x_probe), y, z, np.ones_like(y)])
        h = M @ cl
        with np.errstate(divide='ignore', invalid='ignore'):
            ok = (h[3] > 1e-6) & (np.abs(h[1] / h[3]) <= 1.02)
        if not ok.any(): continue
        y, z = y[ok], z[ok]
        for q, bottom, topmost in ((half, zb, zh), (1.0, eb, eh)):
            ground = []
            for sg in (-1.0, 1.0):
                a = M[0, 0] - sg * q * M[3, 0]
                b = sg * q * (M[3, 1] * y + M[3, 2] * z + M[3, 3]) - (M[0, 1] * y + M[0, 2] * z + M[0, 3])
                if abs(a) < 1e-9: return None
                ground.append(b / a)
            bottom.append(np.minimum(ground[0], ground[1]).min()); topmost.append(np.maximum(ground[0], ground[1]).max())
    if not zb: return None
    return min(zb), max(zh), min(eb), max(eh)


VARIANT_SEEDS = (11, 27)               # the left and right sides each get their own variant of the cloud tile (variant_tile)
VARIANT_RAMP = 0.45                      # tiles over which a side goes from the original tile (continued as is from the portrait area's edge) to its variant (smoothstep)
VARIANT_STRIPS, VARIANT_SOFT, VARIANT_WAVE = 2, 0.10, 0.04          # strips of the variant, softness of their edges (fraction of a tile), waviness of those edges (fraction of a tile)
VARIANT_EDGE = 0.2                       # fraction of the tile's height over which the variant fades back into the original at its top and bottom edges


def variant_tile(tex, seed, strips=VARIANT_STRIPS, soft=VARIANT_SOFT, wave=VARIANT_WAVE):
    """another cloud tile from the original one (RGBA, rows top first), seamless like it: `strips` vertical strips each show the tile shifted sideways by a random amount (deterministic: `seed`),
    joined by soft, wavy edges and blended so that the contrast stays the tile's (variance-preserving blend around the mean color). Near its top and bottom edges the variant fades back into the
    original (VARIANT_EDGE): the sky rows stack the tile vertically half a tile apart, and their joins stay the original's; the left and right edges match too (the strips wrap around): the side of the
    sky that shows it scrolls like the original without a seam."""
    rng = np.random.default_rng(seed)
    t = np.asarray(tex, np.float32); h, w = t.shape[:2]
    mu = t.reshape(-1, t.shape[2]).mean(0)
    yy, xx = np.mgrid[0:h, 0:w]; X = (xx + 0.5) / w; Y = (yy + 0.5) / h
    Xw = X + wave * np.sin(2.0 * math.pi * (Y + rng.uniform())) + 0.5 * wave * np.sin(4.0 * math.pi * (Y + rng.uniform()))
    acc = np.zeros_like(t); w2 = np.zeros((h, w), np.float32)
    for i in range(strips):
        c = (i + 0.5 + rng.uniform(-0.2, 0.2)) / strips
        d = (Xw - c + 0.5) % 1.0 - 0.5
        m = np.exp(-0.5 * (d / (0.5 / strips + soft)) ** 8)                       # (flat top: the strip itself; soft edges)
        acc += m[..., None] * (np.roll(t, int(rng.integers(w)), 1) - mu); w2 += m * m
    v = mu + acc / np.sqrt(np.maximum(w2, 1e-6))[..., None]
    edge = _smooth(np.minimum(Y, 1.0 - Y) / VARIANT_EDGE)[..., None]                  # (the top and bottom of the tile stay the original's: the sky rows meet there half a tile apart)
    out = np.clip(np.round(t + (v - t) * edge), 0, 255).astype(np.uint8)
    if t.shape[2] > 3: out[..., 3] = np.asarray(tex)[..., 3]
    return out


class WideSky:
    """Sky bands on either side of the portrait area. `pos` / `uv` / `col`: vertices of the "kumo" object at its original position (before scrolling). `deform` False (the default rendering): the
    bands continue the original sky exactly (no stretch, no slide): the variants of the tile (variant_tile) take over from the edge of the area (side_layers)."""
    def __init__(self, pos, uv, col, deform=True):
        self.deform = deform
        self.rows = analyze(pos, uv, col)
        self.period = self.rows[0].period
        self.step = self.period / STEP_PER_TILE
        self.x_mil = float(np.mean([(r.quads[0, 0] + r.quads[-1, 1]) / 2 for r in self.rows]))
        self._key = None; self._all = None; self._ref = []; self._sides = []

    def _build(self, M, aspect):
        """Geometry of the bands (positions, colors, stretch: everything except the u join at the edge, which follows the scrolling)."""
        self._all = None; self._ref = []; self._sides = []
        half = half_zone_ndc(aspect)
        if half >= 1.0 - 1e-6: return                                   # window as narrow as the portrait: nothing to add
        b = zone_edges(M, self.rows, half, self.x_mil)
        if b is None: return
        zb, zh, eb, eh = b
        P, U, C, R = [], [], [], []
        for side, (xs, direction, ext) in enumerate(((zb, -1.0, zb - eb), (zh, 1.0, eh - zh))):
            if ext <= 0.0: continue
            K = int(min(MAX_COLUMNS, math.ceil(ext / self.step) + 2))
            d = np.arange(K + 1) * self.step
            G, dv = deformation(d, side, self.period) if self.deform else (d.copy(), np.zeros_like(d))
            first = sum(len(a) for a in P); ramp = _smooth(d / (VARIANT_RAMP * self.period))          # (share of the side's variant, column by column)
            X = xs + direction * d
            t = np.linspace(0.0, 1.0, SUB_ROWS + 1)                       # sub-rows, from the bottom edge (0) to the top edge (1)
            for ri, r in enumerate(self.rows):
                lerp = lambda a, b: np.asarray(a, float)[None] + t[:, None] * (np.asarray(b, float) - np.asarray(a, float))[None]
                yz = lerp(r.bottom[:2], r.topmost[:2]); cc = lerp(r.bottom[3], r.topmost[3])                   # (S + 1, 2), (S + 1, 4): linear vertex color, like the original sky
                v = r.bottom[2] + t * (r.topmost[2] - r.bottom[2])
                pos = np.zeros((K + 1, len(t), 3)); pos[:, :, 0] = X[:, None]; pos[:, :, 1:] = yz[None]
                uv = np.zeros((K + 1, len(t), 2)); uv[:, :, 0] = (direction * r.rate * G)[:, None]               # u relative to the starting point (join added at each frame)
                uv[:, :, 1] = v[None] + dv[:, None] * np.sin(math.pi * t)[None]
                col = np.zeros((K + 1, len(t), 4)); col[:] = cc[None]
                share = np.repeat(ramp[:, None, None], len(t), axis=1)
                if direction < 0: pos, uv, col, share = pos[::-1], uv[::-1], col[::-1], share[::-1]            # increasing abscissas: same traversal direction (hence front-facing) as the original quadrilaterals
                p = self._triangles(pos)
                self._ref.append((sum(len(a) for a in P), sum(len(a) for a in P) + len(p), ri, xs))
                P.append(p); U.append(self._triangles(uv)); C.append(self._triangles(col)); R.append(self._triangles(share)[:, 0])
            self._sides.append((side, first, sum(len(a) for a in P)))
        if P: self._all = (np.concatenate(P), np.concatenate(U), np.concatenate(C)); self._share = np.concatenate(R)

    def bands(self, M, aspect, phi):
        """-> (positions (N, 3), texture coordinates (N, 2), colors (N, 4)) in float32: triangles of the bands on either side of the zone; None if there is nothing to add.
        `phi` = x displacement of the object from its original position (scrolling): the u of the bands is that of the original sky at the edge of the zone."""
        lookup_key = (np.asarray(M, float).tobytes(), float(aspect))
        if lookup_key != self._key: self._build(M, aspect); self._key = lookup_key
        if self._all is None: return None
        P, U, C = self._all
        U = U.copy()
        for start_idx, end, ri, xs in self._ref: U[start_idx:end, 0] += self.rows[ri].u(xs - phi)
        return P.astype(np.float32), U.astype(np.float32), C.astype(np.float32)

    def side_layers(self, C):
        """after `bands`: [(side 0 left / 1 right, first vertex, end, colors)]: the vertices of each side, with the colors `C` (bands' result) whose alpha is the share of that side's variant
        (0 at the edge of the portrait area, 1 from VARIANT_RAMP tiles on): drawn over the bands with the variant's texture, they turn the continued original into the variant without a seam."""
        if self._all is None: return []
        out = []
        for side, a, b in self._sides:
            cc = np.array(C[a:b], np.float32); cc[:, 3] = cc[:, 3] * self._share[a:b]
            out.append((side, a, b, cc))
        return out

    @staticmethod
    def _triangles(a):
        """(n, S + 1, k): columns x sub-rows -> triangles (bottom left, top left, top right, bottom left, top right, bottom right) of each quadrilateral (same order as the original sky)."""
        g, d = a[:-1], a[1:]
        bg, hg, hd, bd = g[:, :-1], g[:, 1:], d[:, 1:], d[:, :-1]
        return np.stack([bg, hg, hd, bg, hd, bd], axis=2).reshape(-1, a.shape[2])


def cloned_positions(cur, dx):
    """Vertex positions of a copy of a sky plane (`ext_map`). `cur` is not modified; -> (n, 3) float32 array.

    `dx` number: copy SHIFTED by dx on x (title sky copies).
    `('mirror', 'min')` or `('mirror', 'max')`: copy MIRRORED about the left or right edge **of the plane as it is
    now** (x -> 2 xe - x: the edge points do not move, the image extends without a seam; skies of dpout and ev09).
    `('mirror', xe)` with a number is still accepted: mirror about the plane x = xe.

    **The side, not the x value**: the sky plane of `ev09` carries a movement (from +9.0 to 0.0 in 900 steps, looping). With an axis
    fixed at load time, the copy moved back by d while the original moved forward by d, a gap of 2d: broken seam and black void
    up to a third of the plane. The axis is therefore re-read at each update, from the current vertices.
    """
    p = np.array(cur, np.float32)
    if isinstance(dx, tuple) and dx and dx[0] == 'mirror':
        side = dx[1]
        xe = (float(p[:, 0].min()) if side == 'min' else float(p[:, 0].max())) if isinstance(side, str) else float(side)
        p[:, 0] = np.float32(2.0 * xe) - p[:, 0]
    else: p[:, 0] += np.float32(dx)
    return p
