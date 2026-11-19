"""Pictures of the language screen: the flags (`dq456_pc/assets/flags/<code>.png`, 120 x 80, named by their ISO 3166 code: public domain renders, see THIRD_PARTY_NOTICES.md;
`flags.txt` names them), and the globe of the start menu's language plate (white strokes, no fill), drawn by the port. Antialiased (drawn 4 times larger then averaged)."""
import os
import numpy as np

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'flags')
SUPER = 4
_names = None


def names():
    """{flag code: country name in English} of every flag of the project, in the order of the codes."""
    global _names
    if _names is None:
        _names = {}
        try:
            with open(os.path.join(FOLDER, 'flags.txt'), encoding='utf-8') as f:
                for line in f:
                    code, sep, name = line.partition('=')
                    if sep and not line.startswith('#'): _names[code.strip()] = name.strip()
        except OSError: pass
    return _names


def flag(code, w=120, h=80):
    """RGBA (h, w, 4) uint8 of the flag `code` (ISO 3166, "fr", "gb-sct"...), top row first, fitted into w x h (transparent around a flag of another shape); gray if it is missing."""
    from PIL import Image
    p = os.path.join(FOLDER, str(code).lower() + '.png')
    if not os.path.isfile(p):
        out = np.zeros((h, w, 4), np.uint8); out[...] = (90, 90, 90, 255); return out
    im = Image.open(p).convert('RGBA')
    if im.size != (w, h): im = im.resize((w, h), Image.LANCZOS)
    return np.asarray(im, np.uint8).copy()


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
