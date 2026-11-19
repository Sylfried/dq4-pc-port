"""Dragon Quest V's volcano on the world map: what Unity's Volcano component adds to the place icon of the mountain (FieldSymbol kind MOUNTAIN).

Volcano.Init rewrites the icon's mesh: quad 0 the mountain (the icon itself, drawn with the other icons), quad 1 the crater (icon rectangle CRATER) at (4, 7) from the icon's corner,
quads 2 to 4 three puffs of smoke (icon rectangle SMOKE), drawn with the shader Custom/FieldVolcano (alpha blending, after the icons). Volcano.Update, at each frame: every 4th frame
each puff's step k goes up by 2 (0 to 22, then again from 0; the three start at 0, 8 and 16); a puff is placed at (4 - s, 16 + k + s) and grows by s = k / 6 on every side, its alpha
falls from 1 to 0 (31 x (24 - k) / 24, in 31sts). The game's random jitter (Utility.Rand(1)) is always 0.
Units: pixels of the icon texture, x to the right, z up the map (the icon's top left corner at 0; one map tile is 16 pixels).
"""
MOUNTAIN, CRATER, SMOKE = 19, 40, 41          # FieldSymbol kinds / s_symbols rectangles: the mountain that gets a Volcano, the crater, the smoke
CRATER_AT = (4.0, 7.0)                        # Volcano.Init: SetVerticesColors(4, 4, 8, 7, 0, ...)
SMOKE_X, SMOKE_Z = 4.0, 16.0
STARTS = (0, 8, 16)                           # Volcano..ctor: m_smoke
STEPS = 24


def smoke_steps(frames):
    """Each puff's step k after `frames` updates (every 4th update adds 2)."""
    n = frames // 4
    return [(k + 2 * n) % STEPS for k in STARTS]


def quads(frames, crater_size, smoke_size):
    """The crater and the three puffs at this frame: [(x, z_top, width, height, alpha, kind)] in the icon's pixels (z_top: the quad's upper edge, z going up the map)."""
    out = [(CRATER_AT[0], CRATER_AT[1], crater_size[0], crater_size[1], 1.0, CRATER)]
    for k in smoke_steps(frames):
        s = k / 6.0
        alpha = (31 * (STEPS - k) // STEPS) / 31.0
        out.append((SMOKE_X - s, SMOKE_Z + k + s, smoke_size[0] + 2 * s, smoke_size[1] + 2 * s, alpha, SMOKE))
    return out
