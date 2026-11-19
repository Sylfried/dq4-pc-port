"""DQ VI's world map tiles: FieldData::setMeshInfo(uv, opt) of libdq6core.so redone with numpy (no engine call).

The Unity layer draws the world map as a mesh of 25 x 53 tiles whose texture coordinates the engine writes (Field.SetIndexList -> FieldSet -> setMeshInfo, 32 bytes a tile).
The port asked the engine for them, also for the 25 columns on each side of the phone's mesh (the 16:9 screen is wider): three emulated calls of 4 to 7 ms each time a tile or an
animation step changed, hence stalls on the world map, worse when running. The same computation, read in the library (0x22e778, CWorldMap::getWorldNo 0x230938, getUV 0x2309fc):

  map = FieldData + (0x680 if opt & 0x100 else 0x638) (a CWorldMap: +0 header (u8 w, h, bw, bh), +0x10 cells (u16), +0x20 tile entries (6 bytes), +0x28 UV kinds (8 bytes), +0x30 UV nibbles)
  origin (x0, y0) = FieldData + 0x6f4, + 0x6f8 (0 for opt 0x301); rows y0 - 10 to y0 + 42, columns x0 - 4 to x0 + 20, wrapped around the map (W = w * bw, H = h * bh)
  opt 0x201: tile = anim 0x38ba4c + FieldData[0x6e0] + (x & 3 | (y & 3) << 2), UV kind 0
  otherwise: entry = entries[(cell - 1) & 0x3ff]; tile = s16 at +4 when its kind (byte 1) is 0, else s16 at +2, plus anim 0x38ba4c + FieldData[0x6e0] (kind 0x18) or
             anim 0x38ba48 + FieldData[0x6dc] (kind 8); UV kind = byte at UV kinds + 8 * nibble (cell index i: high nibble of byte i / 2 when i is even, low when odd)
  corners = table 0x155eb8 + 32 * UV kind (8 floats) + (tile % 32, tile / 32) / 32, in the order 0 1, 6 7, 4 5, 2 3.
"""
import struct
import numpy as np

COLS, ROWS = 25, 53
FIRST_COL, FIRST_ROW = -4, -10
CORNERS = 0x155eb8                 # library: 8 floats per UV kind
ANIM_24, ANIM_8 = 0x38ba4c, 0x38ba48       # library halfwords: the animation steps (FieldData::nextAnimation24 / nextAnimation8)
CORNER_ORDER = (0, 1, 6, 7, 4, 5, 2, 3)


def _wrap(v, n):
    """The engine's wrap of a row or a column (one period at most either way): v + n when v < 0, v - n when v >= n."""
    return np.where(v < 0, v + n, np.where(v >= n, v - n, v))


def _runs(ys):
    """[(first row, number of rows)] of consecutive rows (the wrap splits them in two at most)."""
    out = []
    for y in ys.tolist():
        if out and out[-1][0] + out[-1][1] == y: out[-1][1] += 1
        else: out.append([y, 1])
    return out


_CORNERS = {}


def tile_uvs(mem, lib, fd, opt, sides=(0,)):
    """{k: uv (53, 25, 4, 2) float32} of the tile mesh `opt` moved by 25 * k columns (k in `sides`), as setMeshInfo writes it. mem(address, size) -> bytes; lib: the library's base."""
    def i32(a): return struct.unpack('<i', mem(a, 4))[0]
    def s16(a): return struct.unpack('<h', mem(a, 2))[0]
    def u64(a): return struct.unpack('<Q', mem(a, 8))[0]
    m = fd + (0x680 if opt & 0x100 else 0x638)
    x0, y0 = (0, 0) if opt == 0x301 else (i32(fd + 0x6f4), i32(fd + 0x6f8))
    w, h, bw, bh = mem(u64(m), 4)
    W, H = w * bw, h * bh
    ys = _wrap(np.arange(y0 + FIRST_ROW, y0 + FIRST_ROW + ROWS, dtype=np.int64), H)
    corners = _CORNERS.get(lib)
    if corners is None: corners = _CORNERS[lib] = np.frombuffer(mem(lib + CORNERS, 256 * 32), np.float32).reshape(256, 8)[:, list(CORNER_ORDER)].copy()          # (library constant)
    a24 = s16(lib + ANIM_24) + i32(fd + 0x6e0)
    if opt != 0x201:
        cells_at, entries_at, kinds_at, nibbles_at = u64(m + 0x10), u64(m + 0x20), u64(m + 0x28), u64(m + 0x30)
        runs = _runs(ys)
        rows = np.concatenate([np.frombuffer(mem(cells_at + 2 * W * y, 2 * W * n), np.uint16).reshape(n, W) for y, n in runs])          # (53, W)
        if W % 2 == 0:
            nib = np.concatenate([np.frombuffer(mem(nibbles_at + (W * y) // 2, (W // 2) * n), np.uint8).reshape(n, W // 2) for y, n in runs])          # (53, W / 2)
            nib = np.stack([nib >> 4, nib & 0xf], axis=-1).reshape(ROWS, W)          # (cell i: high nibble when i is even)
        else:
            nib = np.empty((ROWS, W), np.uint8)
            for r, y in enumerate(ys.tolist()):
                b = np.frombuffer(mem(nibbles_at + (W * y) // 2, W // 2 + 1), np.uint8); i = W * y + np.arange(W)
                nib[r] = np.where(i & 1, b[(i >> 1) - ((W * y) >> 1)] & 0xf, b[(i >> 1) - ((W * y) >> 1)] >> 4)
        uv_kinds = np.frombuffer(mem(kinds_at, 16 * 8), np.uint8).reshape(16, 8)[:, 0].astype(np.int64)
        a8 = s16(lib + ANIM_8) + i32(fd + 0x6dc)
        no_all = (rows.astype(np.int64) - 1) & 0x3ff
        ent = np.frombuffer(mem(entries_at, 6 * (int(no_all.max()) + 1)), np.uint8).reshape(-1, 6)
        ek = ent[:, 1].astype(np.int64); t2 = ent[:, 2:4].copy().view('<i2')[:, 0].astype(np.int64); t4 = ent[:, 4:6].copy().view('<i2')[:, 0].astype(np.int64)
        tiles = np.where(ek == 0, t4, t2 + np.where(ek == 0x18, a24, np.where(ek == 8, a8, 0)))          # per tile entry
    out = {}
    for k in sides:
        xs = _wrap(np.arange(x0 + 25 * k + FIRST_COL, x0 + 25 * k + FIRST_COL + COLS, dtype=np.int64), W)
        if opt == 0x201:
            tile = a24 + ((xs[None, :] & 3) | ((ys[:, None] & 3) << 2))
            kind = np.zeros(tile.shape, np.int64)
        else:
            tile = tiles[no_all[:, xs]]
            kind = uv_kinds[nib[:, xs]]
        u = (tile & 31).astype(np.float32) / np.float32(32.0)
        v = np.trunc(tile / 32.0).astype(np.float32) / np.float32(32.0)
        c = corners[kind]                                                            # (53, 25, 8)
        uv = np.empty((ROWS, COLS, 8), np.float32)
        uv[..., 0::2] = c[..., 0::2] + u[..., None]; uv[..., 1::2] = c[..., 1::2] + v[..., None]
        out[k] = uv.reshape(ROWS, COLS, 4, 2)
    return out
