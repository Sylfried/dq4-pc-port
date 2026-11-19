"""Draws the pictures of the LEFT stick's four directions from Kenney's own pictures (CC0, dq456_pc/assets/input_prompts), in the same version of the pack as the others: each
`<family>_stick_r_<direction>` picture with its "R" replaced by the "L" of `<family>_stick_l_press` (the press pictures of the two sticks differ only by that letter: the box where they
differ is copied, at the place where the right stick's direction picture has the same box). Families without their own press pictures (PlayStation) take Xbox's letters (the pack draws
the same stick for the three families). Run once: python3 tools/make_stick_pictures.py (writes <family>_stick_l_up/down/left/right.png)."""
import os
import numpy as np
from PIL import Image

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dq456_pc', 'assets', 'input_prompts')
FAMILIES = ('xbox', 'playstation', 'switch')
DIRECTIONS = ('up', 'down', 'left', 'right')


def load(name): return np.array(Image.open(os.path.join(FOLDER, name + '.png')).convert('RGBA'))


def letter_box(family):
    """(box (y0, y1, x0, x1), the R press picture, the L press picture) of the family (or Xbox's)."""
    for f in (family, 'xbox'):
        if all(os.path.exists(os.path.join(FOLDER, '%s_stick_%s_press.png' % (f, s))) for s in 'rl'):
            r, l = load(f + '_stick_r_press'), load(f + '_stick_l_press'); break
    ys, xs = np.nonzero(np.any(r != l, axis=2))
    y0, y1, x0, x1 = ys.min() - 2, ys.max() + 3, xs.min() - 2, xs.max() + 3
    return (y0, y1, x0, x1), r, l


def left_picture(family, direction):
    (y0, y1, x0, x1), r, l = letter_box(family)
    src = load('%s_stick_r_%s' % (family, direction)); h, w = y1 - y0, x1 - x0
    patch = r[y0:y1, x0:x1].astype(int)
    best = None
    for dy in range(-y0, src.shape[0] - y1 + 1):          # the place where the direction picture has the R press picture's letter box (exactly the same pixels)
        for dx in range(-x0, src.shape[1] - x1 + 1):
            e = np.abs(src[y0 + dy:y1 + dy, x0 + dx:x1 + dx].astype(int) - patch).max()
            if best is None or e < best[0]: best = (e, dy, dx)
    e, dy, dx = best
    if e > 8: raise SystemExit('%s_stick_r_%s: no "R" letter box found (difference %d)' % (family, direction, e))
    out = src.copy(); out[y0 + dy:y1 + dy, x0 + dx:x1 + dx] = l[y0:y1, x0:x1]
    return out


if __name__ == '__main__':
    for f in FAMILIES:
        for d in DIRECTIONS:
            Image.fromarray(left_picture(f, d)).save(os.path.join(FOLDER, '%s_stick_l_%s.png' % (f, d)), optimize=True)
            print('%s_stick_l_%s.png' % (f, d))
