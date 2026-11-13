"""HD smoothing of sprite sheets: EPX x8 enlargement, computed
at load time and cached (no game file modified).

Each cell (24x32) is enlarged separately then placed back into a new atlas with a margin (gutter) that repeats
the cell's edges: bilinear filtering and mipmaps therefore cannot make the neighboring cell bleed over.
Transparent pixels take the color of the neighboring opaque edge to avoid dark fringes when filtering.
"""
import numpy as np
from dq4_pc.language import N_

VERSION = 5          # to be incremented when an algorithm changes (invalidates the caches); 4: hero halo kept as a soft gradient; 5: halo removed, enclosed pixels opaque
FACTOR = 8


# Sheets that are not cut into 24 x 32 character cells over 3 columns. Chara.SetTexture (libdq4core, libunity 0xCCC6F8): identifier 193, the world map boat (two
# sprites: the ship, rows 0 to 4, and its wake, rows 5 to 9), takes the "mesh12" mesh: 0.8 x 0.8 square (versus 0.48 x 0.64 for a character), 40 x 40 cells, 12
# columns; 194 is an alias of 193.
# identifier -> (cell width, cell height, columns, rows, panel width ratio, panel height ratio)
SPECIAL_SHEETS = {193: (40, 40, 12, 10, 0.8 / 0.48, 0.8 / 0.64)}
SHEET_ALIASES = {194: 193}


def sheet_geometry(ident, arr, wid=24, topmost=32, cols=3):
    """Splitting of sheet `h<ident>`: dict(ident, width, height, cols, nl, pw, ph, standard). ident: the alias is already resolved (193 for 194); nl: rows (4 for a character, 8 if the 5th row is not empty);
    pw, ph: ratio of the drawn panel to that of a character (1 except for the boat)."""
    ident = SHEET_ALIASES.get(ident, ident)
    if ident in SPECIAL_SHEETS:
        l, h, c, nl, pw, ph = SPECIAL_SHEETS[ident]
        return dict(ident=ident, width=l, height=h, cols=c, nl=nl, pw=pw, ph=ph, standard=False)
    nl = 8 if arr[4 * topmost:5 * topmost, :cols * wid, 3].any() else 4
    return dict(ident=ident, width=wid, height=topmost, cols=cols, nl=nl, pw=1.0, ph=1.0, standard=True)


def uv_cell(f, col, row):
    """(u0, u1, v0, v1) of the cell (column, row) of a sprite sheet atlas `f` (original or HD, gutters excluded); v1 = top of the cell (Unity: v = 0 at the bottom of the texture)."""
    pl, ph, g = f['cl'] + 2 * f['g'], f['ch'] + 2 * f['g'], f['g']
    return (col * pl + g) / f['tw'], (col * pl + g + f['cl']) / f['tw'], 1 - (row * ph + g + f['ch']) / f['th'], 1 - (row * ph + g) / f['th']


def _key(a):
    """Pixel comparison key: 32-bit RGBA, any almost transparent pixel = 0."""
    k = np.ascontiguousarray(a).view('<u4')[..., 0].copy()
    k[a[..., 3] < 8] = 0
    return k


def _dilate(a, step=2):
    """Gives transparent pixels the color of an opaque neighbor (alpha unchanged), `step` times."""
    a = a.copy()
    for _ in range(step):
        op = a[..., 3] >= 8
        if op.all() or not op.any(): break
        pad = np.pad(a, ((1, 1), (1, 1), (0, 0)))
        po = np.pad(op, 1)
        h, w = op.shape
        new = a.copy(); done = op.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            neighbours = pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]; vo = po[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            take = ~done & vo
            new[take, :3] = neighbours[take, :3]; done |= take
        a = new
    return a


def _x2(a):
    """EPX (Scale2x): each pixel becomes 4; the corners take the neighbor's color when two adjacent neighbors are identical."""
    k = _key(a)
    p = lambda m: np.pad(m, ((1, 1), (1, 1)) + ((0, 0),) * (m.ndim - 2), mode='edge')
    ap, kp = p(a), p(k)
    A, D, C, B = ap[:-2, 1:-1], ap[2:, 1:-1], ap[1:-1, :-2], ap[1:-1, 2:]
    kA, kD, kC, kB = kp[:-2, 1:-1], kp[2:, 1:-1], kp[1:-1, :-2], kp[1:-1, 2:]
    h, w = k.shape
    out = np.empty((2 * h, 2 * w, 4), np.uint8)
    out[0::2, 0::2] = np.where(((kC == kA) & (kC != kD) & (kA != kB))[..., None], A, a)
    out[0::2, 1::2] = np.where(((kA == kB) & (kA != kC) & (kB != kD))[..., None], B, a)
    out[1::2, 0::2] = np.where(((kD == kC) & (kD != kB) & (kC != kA))[..., None], C, a)
    out[1::2, 1::2] = np.where(((kB == kD) & (kB != kA) & (kD != kC))[..., None], D, a)
    return out


def _alpha_count(cell): return len(np.unique(cell[..., 3]))


def outside(free, cell=None):
    """Mask of the `free` pixels (bool h x w) reached from the edge of their cell without crossing a non-free pixel (4-neighborhood); `cell` = (width, height) of the cells of a sheet (the
    flood never crosses from one cell to the next), None = the whole picture. The free pixels it does not reach are enclosed by the drawing."""
    h, w = free.shape; cw, ch = cell or (w, h)
    if h % ch or w % cw: cw, ch = w, h
    f = free.reshape(h // ch, ch, w // cw, cw).transpose(0, 2, 1, 3).reshape(-1, ch, cw)
    out = np.zeros_like(f); out[:, 0, :] = f[:, 0, :]; out[:, -1, :] = f[:, -1, :]; out[:, :, 0] |= f[:, :, 0]; out[:, :, -1] |= f[:, :, -1]
    while True:
        grow = out.copy()
        grow[:, 1:, :] |= out[:, :-1, :]; grow[:, :-1, :] |= out[:, 1:, :]; grow[:, :, 1:] |= out[:, :, :-1]; grow[:, :, :-1] |= out[:, :, 1:]
        grow &= f
        if (grow == out).all(): break
        out = grow
    return out.reshape(h // ch, w // cw, ch, cw).transpose(0, 2, 1, 3).reshape(h, w)


def clean_sheet(arr, threshold=128, soft=False, cell=None):
    """Sprite sheet -> (sheet, cleaned). The hero sheets (h100 to h127) have a halo of alpha 1 to 105 in a stray color (magenta) around the body (alpha 204 to 255); without cleaning it appears as a purple
    fringe and the body, with alpha 0.8 to 1, lets the scenery show through. Body (alpha >= threshold) -> 255. Halo (the partly transparent pixels reached from the edge of the cell, `cell` = (width,
    height)): removed, alpha 0 (no purple outline around the characters; `soft` keeps it with its gradient in the body's colors).
    The partly transparent pixels **enclosed** by the body (a few dark pixels between an arm and the chest, 0 to 15 per sheet) are opaque: removed or half transparent, they made holes (Kiryl's torso).
    Sheets with binary alpha (NPCs, monsters) are rendered as is."""
    al = arr[..., 3]
    if not ((al > 0) & (al < 255)).any(): return arr, False
    body = al >= threshold; halo = outside(~body, cell) & (al > 0)
    a = arr.copy(); a[..., 3] = np.where(al == 0, 0, np.where(halo, al if soft else 0, 255)).astype(np.uint8)
    if soft:
        b = a.copy(); b[halo, 3] = 0
        a[halo, :3] = _dilate(b, 3)[halo, :3]
    return a, True


def upscale_epx(cell, passes=3):
    """Iterated EPX/Scale2x (x8); bicubic fallback if the alpha is already softened (sheets filtered in the original)."""
    if _alpha_count(cell) > 8: return upscale_bicubic(cell, 2 ** passes)
    a = _dilate(cell)
    for _ in range(passes): a = _x2(a)
    return a


def upscale_sheet(arr, wid, topmost, columns, lines, algo=None, gutter=4, factor=FACTOR):
    """Sprite sheet -> (HD atlas, cell_w, cell_h); `factor` = 1 for the original sheets (gutter only); the cell (col, line) starts at
    (col*(cell_w+2*gutter)+gutter, line*(cell_h+2*gutter)+gutter) in the atlas (origin at the top left)."""
    algo = algo or upscale_epx
    cl, ch = wid * factor, topmost * factor
    pl, ph = cl + 2 * gutter, ch + 2 * gutter
    atlas = np.zeros((lines * ph, columns * pl, 4), np.uint8)
    for r in range(lines):
        for c in range(columns):
            cell = arr[r * topmost:(r + 1) * topmost, c * wid:(c + 1) * wid]
            if cell.shape[:2] != (topmost, wid): continue
            g = np.pad(algo(cell), ((gutter, gutter), (gutter, gutter), (0, 0)), mode='edge')
            atlas[r * ph:(r + 1) * ph, c * pl:(c + 1) * pl] = g
    return atlas, cl, ch


# ---- other algorithms -----------------------------------------------------------------------------------------------

def _interp_matrix(n_in, f, sigma=0.0):
    """Bilinear interpolation matrix (n_in*f, n_in) (aligned pixel centers), followed by a Gaussian blur (sigma in output pixels)."""
    n_out = n_in * f
    x = (np.arange(n_out) + 0.5) / f - 0.5
    i0 = np.floor(x).astype(int); t = (x - i0).astype(np.float32)
    M = np.zeros((n_out, n_in), np.float32); r = np.arange(n_out)
    M[r, np.clip(i0, 0, n_in - 1)] += 1 - t
    M[r, np.clip(i0 + 1, 0, n_in - 1)] += t
    if sigma > 0:
        d = np.arange(n_out)
        G = np.exp(-0.5 * ((d[:, None] - d[None, :]) / sigma) ** 2).astype(np.float32)
        G /= G.sum(1, keepdims=True)
        M = G @ M
    return M


def upscale_bicubic(cell, f=8):
    """Bicubic interpolation x f (premultiplied alpha, alpha contrast to keep a sharp silhouette)."""
    from PIL import Image
    h, w = cell.shape[:2]
    im = Image.fromarray(_dilate(cell)).convert('RGBa').resize((w * f, h * f), Image.BICUBIC).convert('RGBA')
    a = np.array(im)
    al = a[..., 3].astype(np.float32) / 255
    a[..., 3] = (np.clip((al - 0.5) * 3 + 0.5, 0, 1) * 255).astype(np.uint8)
    return _dilate(a, 3)


# (displayed name, cache identifier, function); index 0 = original sprites (sharp pixels, no enlargement), 1 = EPX x8; mode 4 (pixel perfect) is handled by window.py
# ("regions lissees" and "bicubique" were removed: they blurred the outlines instead of sharpening them; upscale_bicubic is now only used as an EPX fallback for
# sheets that are already softened)
MODES = [(N_('window.originals_sharp_pixels'), None, None),
         ('EPX x8', 'epx', upscale_epx)]


# ---- map window plans (256 x 256 displayed in 4:3) ------------------------------------------------------

def upscale_plan(a, wid=1024, topmost=768, epx=False):
    """Map plan (RGBA 256 x 256, displayed in 4:3) enlarged with Lanczos then slightly sharpened: much sharper than plain linear filtering by the graphics card (premultiplied alpha).
    `epx` (world plan, whose lands are pixel art on a painted background): two EPX passes first round the outlines of the lands."""
    from PIL import Image, ImageFilter
    if epx:
        for _ in range(2): a = _x2(a)
        im = Image.fromarray(a).filter(ImageFilter.GaussianBlur(1.1))
        r = np.array(im.resize((wid, topmost), Image.LANCZOS))
    else:
        r = np.array(Image.fromarray(a).convert('RGBa').resize((wid, topmost), Image.LANCZOS).convert('RGBA'))
    rgb = np.array(Image.fromarray(r[..., :3]).filter(ImageFilter.UnsharpMask(radius=1.6, percent=45, threshold=2)))
    r[..., :3] = rgb
    return r


def veil_plan(plan, mask, lookup_key, x0=48, y0=16, block=10, f=4):
    """Places on the enlarged plan (1024 x 768) the veil of the world map's unexplored blocks. `mask`: grayed silhouette of the lands (192 x 256 RGBA, alpha 255 on land, 3 on sea),
    `lookup_key`: 16 integers, set bit = unexplored block of `block` x `block` pixels (16 x 16 blocks from (x0, y0) in the 256 x 192 plan). The game places square blocks; here the silhouette (rounded outline)
    and the block boundary are smoothed after enlargement, which avoids the staircase effect without changing what is hidden."""
    h, w = mask.shape[:2]
    R = lambda n, s: _interp_matrix(n, f, s)
    Ry, Rx = R(h, 4.5), R(w, 4.5)
    land = np.clip((mask[..., 3].astype(np.float32) - 3) / 252.0, 0, 1)
    t_hd = Ry @ land @ Rx.T
    alpha_t = np.clip((t_hd - 0.36) * 3.0 + 0.5, 0, 1)          # threshold slightly below 0.5: the outline covers the plan's green fringe under the silhouette
    clr = np.stack([(Ry @ (mask[..., k].astype(np.float32) * land) @ Rx.T) / np.maximum(t_hd, 1e-3) for k in range(3)], -1)
    v = np.zeros((h, w), np.float32)
    for r, m in enumerate(lookup_key[:16]):
        for c in range(16):
            if m >> c & 1: v[y0 + block * r:y0 + block * (r + 1), x0 + block * c:x0 + block * (c + 1)] = 1.0
    Ry2, Rx2 = R(h, 5.0), R(w, 5.0)
    v_hd = np.clip((Ry2 @ v @ Rx2.T - 0.5) * 3.0 + 0.5, 0, 1)
    a = (alpha_t * v_hd)[..., None]
    out = plan.copy()
    out[..., :3] = np.clip(plan[..., :3].astype(np.float32) * (1 - a) + clr * a + 0.5, 0, 255).astype(np.uint8)
    return out
