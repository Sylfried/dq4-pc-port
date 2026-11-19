"""Map pictures composed like the game's map windows do (no window, testable without a screen)."""
import numpy as np

PICTURE = 256 * 192 * 3


def dq6_world_picture(raw, blocks, rows):
    """DQ VI's small world map (ICityMap b__2): its TextAsset `raw` holds two 256 x 192 RGB pictures. The int parameter (0, 0) `blocks` = block size << 16 | blocks per row; from x = 48,
    y = 16, the block j of block row i is taken from the second picture (the veiled lands) when bit j of the i-th number of `rows` (MenuPort.Receive after the picture's name) is set,
    everything else from the first one. -> 192 x 256 x 4 (RGBA, top first) or None (no data)."""
    if raw is None or len(raw) < 2 * PICTURE: return None
    first = np.frombuffer(raw[:PICTURE], np.uint8).reshape(192, 256, 3); second = np.frombuffer(raw[PICTURE:2 * PICTURE], np.uint8).reshape(192, 256, 3)
    out = first.copy(); size, count = blocks >> 16 & 0xffff, blocks & 0xffff
    for i in range(count):
        bits = rows[i] if i < len(rows) else 0
        for j in range(count):
            if bits >> j & 1:
                y, x = 16 + i * size, 48 + j * size
                out[y:y + size, x:x + size] = second[y:y + size, x:x + size]
    return np.dstack([out, np.full((192, 256), 255, np.uint8)])
