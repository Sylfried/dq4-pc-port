"""Pictures of the game languages, drawn by the port: no picture file. French: three vertical bands; English: the Union Flag (saltires counterchanged, as on the real flag), both 3:2;
the globe of the start menu's language plate (white strokes, no fill). Antialiased (drawn 4 times larger then averaged); the flags have a thin dark outline so that they stand out on the
dark plates of the start menu."""
import numpy as np

FR_BLUE, FR_WHITE, FR_RED = (0, 0, 145), (255, 255, 255), (225, 0, 15)
UK_BLUE, UK_WHITE, UK_RED = (1, 33, 105), (255, 255, 255), (200, 16, 46)
OUTLINE = (24, 24, 24)
SUPER = 4


def _french(w, h):
    a = np.empty((h, w, 3), np.float32); x = (np.arange(w) + 0.5) / w
    for lo, hi, col in ((0.0, 1 / 3, FR_BLUE), (1 / 3, 2 / 3, FR_WHITE), (2 / 3, 1.0, FR_RED)):
        a[:, (x >= lo) & (x < hi)] = col
    return a


def _union(w, h):
    """Union Flag on a w x h field (y down): blue field, white saltire (width h / 5), red saltire (h / 15) on the counter-clockwise side of each arm, white cross (h / 3), red cross (h / 5)."""
    a = np.empty((h, w, 3), np.float32); a[:] = UK_BLUE
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    cx, cy = w / 2.0, h / 2.0; px, py = xs - cx, ys - cy
    for sx, sy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):                      # the four arms of the saltire, from the center to a corner
        ax, ay = sx * cx, sy * cy; n = np.hypot(ax, ay); ax, ay = ax / n, ay / n
        arm = (px * ax + py * ay) > 0                                         # (the half of the plane on this arm's side)
        d = px * (-ay) + py * ax                                              # signed distance to the arm's line; positive = clockwise side (y down)
        a[arm & (np.abs(d) < h / 10.0)] = UK_WHITE
        a[arm & (d < 0) & (d > -h / 15.0)] = UK_RED                           # (counter-clockwise side: the broad white is uppermost in the hoist, as on the real flag)
    a[(np.abs(px) < h / 6.0) | (np.abs(py) < h / 6.0)] = UK_WHITE
    a[(np.abs(px) < h / 10.0) | (np.abs(py) < h / 10.0)] = UK_RED
    return a


def flag(language, w=60, h=40):
    """RGBA (h, w, 4) uint8 of the flag of `language` ('fr' or 'en'), top row first."""
    big = (_french if language == 'fr' else _union)(w * SUPER, h * SUPER)
    rgb = big.reshape(h, SUPER, w, SUPER, 3).mean(axis=(1, 3))
    out = np.empty((h, w, 4), np.uint8); out[..., :3] = np.clip(np.rint(rgb), 0, 255); out[..., 3] = 255
    out[0, :, :3] = out[-1, :, :3] = OUTLINE; out[:, 0, :3] = out[:, -1, :3] = OUTLINE
    return out


GLOBE_STROKE = 0.11              # width of the globe's strokes, in radii (about 2.5 pixels of the 48-pixel picture)
GLOBE_MERIDIAN = 0.45            # half width of the meridian's ellipse, in radii


def globe(size=48):
    """RGBA (size, size, 4) uint8: the globe of the language plate, top row first: white strokes only, no fill, no colour and no details:
    the outline of the planet, one meridian (an ellipse) and the equator. Transparent everywhere else (the plate shows through)."""
    n = size * SUPER; r = n / 2.0 - SUPER * 1.5
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    x, y = (xs - n / 2.0) / r, (ys - n / 2.0) / r; d = np.hypot(x, y)
    w = GLOBE_STROKE / 2.0
    lines = np.abs(d - (1.0 - w)) < w                                                         # the outline of the planet
    inside = d < 1.0 - w
    lines |= inside & (np.abs(np.abs(x) - GLOBE_MERIDIAN * np.sqrt(np.clip(1.0 - y * y, 0.0, 1.0))) < w)          # one meridian: the ellipse x = +-k * sqrt(1 - y^2)
    lines |= inside & (np.abs(y) < w)                                                         # the equator
    a = lines.astype(np.float32).reshape(size, SUPER, size, SUPER).mean(axis=(1, 3))
    out = np.zeros((size, size, 4), np.uint8); out[..., :3] = 255; out[..., 3] = np.clip(np.rint(a * 255.0), 0, 255)
    return out
