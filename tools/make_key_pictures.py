"""Draws the pictures of the Shift, Alt, Alt Gr and Ctrl keys from Kenney's own key pictures (CC0, dq456_pc/assets/input_prompts), in their style: a white key, the sign cut out of it.
Shift: the hollow up arrow printed on keyboards (the outline of Kenney's arrow key); Alt: "ALT" on the key shape of Tab; Alt Gr: "ALT" / "GR" on two lines, on the key shape of Caps Lock;
Ctrl: "CTRL" on the key shape of Tab. The letters are Kenney's own (taken from the A, C, L, T, G and R keys). Run once: python3 tools/make_key_pictures.py (writes keyboard_shift.png, keyboard_alt.png,
keyboard_altgr.png, keyboard_ctrl.png)."""
import os
import numpy as np
from PIL import Image
from scipy import ndimage

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dq456_pc', 'assets', 'input_prompts')


def alpha(name): return np.array(Image.open(os.path.join(FOLDER, name + '.png')).convert('RGBA'))[..., 3] > 127


def blank(name):
    """The key shape of a picture, its sign filled in (a plain white key)."""
    return ndimage.binary_fill_holes(alpha(name))


def sign(name):
    """The sign cut out of a key (holes of the key shape), cropped to its box."""
    a = alpha(name); holes = ndimage.binary_fill_holes(a) & ~a
    ys, xs = np.where(holes)
    return holes[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def scaled(mask, height):
    h, w = mask.shape; im = Image.fromarray((mask * 255).astype(np.uint8)).resize((max(1, round(w * height / h)), height), Image.LANCZOS)
    return np.array(im) > 127


def word(letters, height, gap):
    parts = [ndimage.binary_dilation(np.pad(scaled(sign('keyboard_' + c), height - 8), 4), iterations=4) for c in letters]          # (thickened: the letters of the one-letter keys are thinner than Kenney's word keys once scaled down)
    out = np.zeros((height, sum(p.shape[1] for p in parts) + gap * (len(parts) - 1)), bool); x = 0
    for p in parts: out[:, x:x + p.shape[1]] = p; x += p.shape[1] + gap
    return out


def cut(key, mask, cx, cy):
    h, w = mask.shape; y0, x0 = int(round(cy - h / 2)), int(round(cx - w / 2))
    key = key.copy(); key[y0:y0 + h, x0:x0 + w] &= ~mask
    return key


def box_center(mask):
    ys, xs = np.where(mask); return (xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2


def save(mask, name):
    a = np.zeros(mask.shape + (4,), np.uint8); a[mask] = 255
    img = Image.fromarray(a).resize((mask.shape[1] // 4, mask.shape[0] // 4), Image.LANCZOS)          # (drawn 4 times larger: smooth edges)
    img.save(os.path.join(FOLDER, name + '.png'))


def big(mask): return np.array(Image.fromarray((mask * 255).astype(np.uint8)).resize((mask.shape[1] * 4, mask.shape[0] * 4), Image.NEAREST)) > 127


def main():
    # Shift: hollow arrow = the outline of the arrow key's sign, on the plain key
    key = big(blank('keyboard_arrow_up')); arrow = big(ndimage.binary_fill_holes(alpha('keyboard_arrow_up')) & ~alpha('keyboard_arrow_up'))
    ys, xs = np.where(arrow); arrow = arrow[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    arrow = scaled(arrow, int(arrow.shape[0] * 1.35))                                          # (a little larger than the plain arrow: the printed sign of a Shift key)
    arrow = np.pad(arrow, 40); ring = arrow & ~ndimage.binary_erosion(arrow, iterations=24)
    save(cut(key, ring, *box_center(key)), 'keyboard_shift')
    # Alt: "ALT" on the Tab key shape, at the height of Kenney's "TAB"
    key = big(blank('keyboard_tab')); text_h = sign('keyboard_tab').shape[0] * 4
    save(cut(key, word('alt', text_h, 14), *box_center(key)), 'keyboard_alt')
    # Ctrl: "CTRL" on the same key shape, the letters a little narrower so that the four fit like Kenney's "TAB"
    save(cut(key, word('ctrl', int(text_h * 0.92), 10), *box_center(key)), 'keyboard_ctrl')
    # Alt Gr: "ALT" / "GR" on the Caps Lock key shape, like Kenney's "CAPS" / "LOCK"
    key = big(blank('keyboard_capslock')); holes = big(ndimage.binary_fill_holes(alpha('keyboard_capslock')) & ~alpha('keyboard_capslock'))
    lines, n = ndimage.label(ndimage.binary_dilation(holes, iterations=10, structure=np.ones((1, 3))) .any(axis=1)[:, None].repeat(holes.shape[1], 1))
    rows = sorted([np.where(lines[:, 0] == i)[0] for i in range(1, n + 1)], key=lambda r: r[0])
    line_h = max(1, min(r[-1] - r[0] + 1 for r in rows) - 16)
    cx, _ = box_center(key)
    k = cut(key, word('alt', line_h, 14), cx, (rows[0][0] + rows[0][-1]) / 2)
    save(cut(k, word('gr', line_h, 14), cx, (rows[-1][0] + rows[-1][-1]) / 2), 'keyboard_altgr')


if __name__ == '__main__':
    main()
