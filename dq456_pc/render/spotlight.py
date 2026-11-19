"""DQ V / VI Spotlight (packet 34, effect 7: core/engine.py Engine._spotlight): the screen darkened around a lit square, attached to the scene camera.

Unity (Spotlight.Setup / RemakeVertices): the point (x, y, -z) is projected by the scene camera (WorldToViewportPoint), raised by 0.04 of the screen's height; around it a square of half side
(size + 10) / 256 of the phone's width (portrait: its short side), in screen coordinates (the shaders take the vertices as they are). The screen outside the square has the side color; inside, the
texture `etc/en01` (a disc; `etc/en02`, softer, with bit 11: the torch) is drawn twice: Custom/Pre-Spotlight (side color, alpha x (1 - texture alpha)) then Custom/Post-Spotlight (light
color, alpha x texture alpha), both alpha blended over the scene.

The window shows the phone's short side across its height (helpers.portrait_base_height): the same sizes are measured there.

DQ VI's mask (packet 34, effect 11, Capture.SetupMaskEffect): 15 vertices in screen coordinates, two fans around (0, +-w/h) (w/h: the phone's screen); the band |y| <= w/h, a square as wide as the
phone, shows the texture `etc/ccmsk` (a quarter of a disc, its center at the texture's corner u = 1, v = 0) mirrored into the four quarters around the screen's center; above and below, its
opaque black row. Custom/ScreenMask draws the texture as it is, alpha blended.
"""
import numpy as np

RAISE = 0.04                    # viewport units of the phone's height (Spotlight.Setup: m_Pos.y = 2 (y + 0.04) - 1)
PHONE_LONG = 16.0 / 9.0         # the phone's long side, in short sides


def texture_name(torch):
    return 'en02' if torch else 'en01'


def square(pos, size, M, width, height, base_height):
    """Center (pixels, y up) and half side (pixels) of the lit square in a window of width x height, M = the scene's projection x view (4 x 4, column vectors), base_height = phone short sides
    shown across the window's height. None if the point is behind the camera."""
    p = M @ np.array([pos[0], pos[1], -pos[2], 1.0])
    if p[3] <= 1e-9: return None
    nx, ny = p[0] / p[3], p[1] / p[3]
    ny += 2.0 * RAISE * PHONE_LONG / base_height
    half = (size + 10) / 256.0 / base_height * height / 2.0          # (size + 10) / 256 of half the phone's width = of a short side's half, measured on the window's height
    return ((nx + 1.0) / 2.0 * width, (ny + 1.0) / 2.0 * height), half


def side_rects(center, half, width, height):
    """The four rectangles (x, y, w, h) around the square: the screen outside it (Unity's four trapezoids cover the same area)."""
    (cx, cy), h = center, half
    x0, x1, y0, y1 = cx - h, cx + h, cy - h, cy + h
    out = [(0.0, 0.0, max(0.0, x0), float(height)), (x1, 0.0, max(0.0, width - x1), float(height)),
           (x0, 0.0, x1 - x0, max(0.0, y0)), (x0, y1, x1 - x0, max(0.0, height - y1))]
    return [r for r in out if r[2] > 0 and r[3] > 0]


def mask_picture(quarter):
    """The mask's square from the texture (rows from the top, RGBA): the texture's corner at the center, mirrored into the four quarters (Unity: u = 1 + x, v = |y| / (w / h))."""
    top = np.concatenate([quarter, quarter[:, ::-1]], axis=1)
    return np.concatenate([top, top[::-1]], axis=0)


def mask_square(width, height, base_height):
    """Center (pixels) and half side of the mask's square: as wide as the phone's short side, at the window's center."""
    return (width / 2.0, height / 2.0), height / base_height / 2.0
