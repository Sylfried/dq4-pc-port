"""Scenes composed for the width of the phone's portrait screen, shown in a landscape window: what lies beside the phone's width (the ends of the scenery, an overlay
that appears or vanishes at the phone's edges) is hidden by the port (a camouflage, not the original picture):

- the sides beyond the phone's width are blurred, slightly darkened, with a soft border (window/backdrop._blur_sides);
- the meshes of the orthographic layer (DQ V / VI cmd_mesh_ortho: here the stage animation of twn::TownStageSsaDraw) fade out toward the phone's edges, so that they no longer
  pop in or out where the landscape window still shows them.

DQ VI's prologue (map e01din2: the cliff, the ocarina, the dragon's flight above the clouds): the ends of the cliff showed on the right; the flying dragon (orthographic layer, model 602)
is drawn by the engine only while it is on the phone's screen: it appeared in the middle of the left side of the window and vanished in the middle of its right side."""

PHONE_WIDTH_MAPS = {'dq6': ('e01din2',)}          # game -> maps concerned
SIDES_LUM = 0.9                                     # the blurred sides, slightly darkened
SIDES_FEATHER = 0.2                                 # soft border between the sharp phone width and the blurred sides (fraction of the half width)
ORTHO_FADE = (0.65, 1.0)                            # orthographic meshes: opaque up to 0.65 of the phone's half width, transparent from its edge (vertex by vertex)
LONG_SIDE = 16.0 / 9.0


def concerned(game, map_name):
    return map_name in PHONE_WIDTH_MAPS.get(game, ())


def base_height(aspect):
    """Visible height of the window in short sides of the phone (window/helpers.portrait_base_height)."""
    a = max(float(aspect), 1e-6)
    if a >= LONG_SIDE: return 1.0
    if a >= 1.0: return LONG_SIDE / a
    if a > 1.0 / LONG_SIDE: return LONG_SIDE
    return 1.0 / a


def column(aspect):
    """Width of the phone's screen in the window, as a fraction of the window's width (the same scale as the scene): 0.5625 at 16:9 and 16:10, 1 or more in a portrait window."""
    return 1.0 / (max(float(aspect), 1e-6) * base_height(aspect))


def ortho_alpha(x, half_width):
    """Opacity factor of an orthographic vertex at x (the layer's units, the phone showing -half_width..half_width): 1 in the middle, 0 from the phone's edges, smooth in between."""
    a, b = ORTHO_FADE; t = (abs(float(x)) / half_width - a) / (b - a)
    t = min(max(t, 0.0), 1.0)
    return 1.0 - t * t * (3.0 - 2.0 * t)
