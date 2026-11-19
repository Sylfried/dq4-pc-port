"""Outlines of the battle sceneries: trees, mountains, grass tufts, rocks.

Cause (measured, see tests/test_scenery_outlines.py): these silhouettes are drawn in 256 x 256 textures whose alpha is STRICTLY binary (0 or 255, never an
intermediate value: 41 textures out of 140 sceneries); the scenery is enlarged x6 then displayed 1280 to 2560 px wide, so one texel covers 4 to 10 screen pixels. Bilinear filtering softens
the color but the outline (alpha 0.5) follows the texel grid: staircase steps of 4 to 10 px along the whole border, which MSAA (which only smooths ONE-pixel steps) does not
touch. The transparent texels are moreover BLACK (0, 0, 0): bilinear filtering darkens the border of the foliage with a dark fringe.

Remedy, on the texture alone, without touching the rest of the drawing:
  - the alpha goes to x4 resolution: two EPX passes (Scale2x, which straightens the steps into straight slopes without losing the tips) then a 0.3 texel Gaussian blur that rounds the
    corners and gives a one-screen-pixel ramp (alpha-to-coverage and the `FRAG` threshold make it an antialiased edge);
  - the color (RGB) is enlarged x4 by bilinear interpolation (same sample positions as the GPU: the interior of the drawing stays that of the linearly filtered original, to within less than one
    gray level on average, 9 at worst on a very high-contrast corner) after giving the transparent texels the color of the neighboring opaque edge (no more black fringe).
Only cut-out textures with binary alpha at least 128 px on a side are processed (foliage, relief, rocks): skies, floors, opaque or semi-transparent (blended) textures,
small pattern textures (grids, torches) are left as they are.
"""
import numpy as np
from dq456_pc.world import hd as HD

FACTOR = 4                  # resolution of the alpha and color after processing (2 EPX passes)
PASSES_EPX = 2
SIGMA = 1.25                 # Gaussian blur of the alpha, in pixels of the enlarged texture (0.3 original texel)
SIDE_MIN = 128               # smallest side (in texels) of a processed texture
PARTIAL_MAX = 0.005          # maximum share of intermediate-alpha texels for a "binary" texture
KEPT_TEXTURES = 12         # enlarged textures kept on the graphics card (the oldest are released)


def is_sliced(arr, lookup_key=None):
    """True if the RGBA texture `arr` is a cut-out with binary alpha (foliage, relief) to be processed. `lookup_key`: scenery group key; ('tr', ...) = transparent (blended) material, excluded."""
    if isinstance(lookup_key, tuple) and lookup_key and lookup_key[0] == 'tr': return False
    if arr is None or arr.ndim != 3 or arr.shape[2] != 4 or min(arr.shape[:2]) < SIDE_MIN: return False
    a = arr[..., 3]
    transp = a < 128
    if not transp.any() or transp.all(): return False
    return float(((a > 0) & (a < 255)).mean()) <= PARTIAL_MAX


def _bilinear(a, f):
    """Enlarges x f by wrap-around (REPEAT) bilinear interpolation, texel centers like the GPU: the result, linearly filtered, gives back the filtered original image (difference < 1 level on average)."""
    a = a.astype(np.float32)
    for ax in (0, 1):
        n = a.shape[ax]
        c = (np.arange(n * f, dtype=np.float32) + 0.5) / f - 0.5
        i0 = np.floor(c).astype(np.int64); t = (c - i0).astype(np.float32)
        t = t.reshape([-1 if k == ax else 1 for k in range(a.ndim)])
        a = np.take(a, i0 % n, axis=ax) * (1.0 - t) + np.take(a, (i0 + 1) % n, axis=ax) * t
    return a


def _fast_bilinear(rgb, f):
    """Same result as `_bilinear` (uint8) via PIL's bilinear resize (texel centers), 10 times faster; wrap-around edge via a 2-texel margin. None if PIL is missing."""
    try: from PIL import Image
    except ImportError: return None
    h, w = rgb.shape[:2]
    p = np.pad(rgb, ((2, 2), (2, 2), (0, 0)), mode='wrap')
    r = np.asarray(Image.fromarray(np.ascontiguousarray(p)).resize(((w + 4) * f, (h + 4) * f), Image.BILINEAR))
    return np.ascontiguousarray(r[2 * f:-2 * f, 2 * f:-2 * f])


def _fill_transparent(rgb, opaque, step=3):
    """Gives transparent texels the color of the nearest opaque texel, over `step` rings (wrap-around texture)."""
    rgb = rgb.copy(); done = opaque.copy()
    for _ in range(step):
        if done.all(): break
        new = rgb.copy(); nf = done.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            v = np.roll(rgb, (dy, dx), (0, 1)); vf = np.roll(done, (dy, dx), (0, 1))
            take = ~nf & vf
            new[take] = v[take]; nf |= take
        rgb, done = new, nf
    return rgb


def _blur(m, sigma):
    """Separable Gaussian blur with wrap-around."""
    if sigma <= 0: return m
    r = max(1, int(np.ceil(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    for ax in (0, 1):
        m = sum(float(w) * np.roll(m, s, axis=ax) for w, s in zip(k, range(-r, r + 1)))
    return m


def _fast_blur(m, sigma):
    """PIL Gaussian blur on a uint8 mask (0 to 255), with wrap-around (4-sigma margin); None if PIL is missing."""
    try: from PIL import Image, ImageFilter
    except ImportError: return None
    r = int(np.ceil(4 * sigma)); h, w = m.shape
    p = np.pad(m, r, mode='wrap')
    b = np.asarray(Image.fromarray(p).filter(ImageFilter.GaussianBlur(sigma)))
    return b[r:r + h, r:r + w]


def softened_alpha(mask, passes=PASSES_EPX, sigma=SIGMA):
    """Binary mask (h, w) of bool -> float32 alpha (h * 2^passes, w * 2^passes) between 0 and 1, with wrap-around."""
    h, w = mask.shape
    a = np.zeros((h, w, 4), np.uint8); a[..., 3] = np.where(mask, 255, 0)
    margin = 2
    a = np.pad(a, ((margin, margin), (margin, margin), (0, 0)), mode='wrap')
    for _ in range(passes): a = HD._x2(a)
    n = margin * 2 ** passes
    m = np.ascontiguousarray(a[n:-n, n:-n, 3])
    b = _fast_blur(m, sigma) if sigma > 0 else m
    if b is not None: return b.astype(np.float32) / 255.0
    return np.clip(_blur(m.astype(np.float32) / 255.0, sigma), 0.0, 1.0)


def soften(arr, passes=PASSES_EPX, sigma=SIGMA):
    """RGBA uint8 texture (h, w, 4) with binary alpha -> RGBA uint8 texture (h * f, w * f, 4) with a softened outline (see the module header)."""
    f = 2 ** passes
    rgb = _fill_transparent(arr[..., :3], arr[..., 3] >= 128)          # transparent texels: color of the neighboring opaque edge (3 rings)
    al = softened_alpha(arr[..., 3] >= 128, passes, sigma)
    out = np.empty((arr.shape[0] * f, arr.shape[1] * f, 4), np.uint8)
    fast = _fast_bilinear(rgb, f)
    out[..., :3] = fast if fast is not None else np.clip(_bilinear(rgb, f) + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(al * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out


def for_scenery(arr, lookup_key=None):
    """Texture to give the GPU for a battle scenery group: softened if it is a cut-out to be processed, otherwise `arr` unchanged."""
    return soften(arr) if is_sliced(arr, lookup_key) else arr
