"""Battle effects made of a full screen quad (tint, flash): fitted to the original game's 4:3 screen, hence too narrow when the battle is widened to 16/9."""
import numpy as np

# Effect models (5000 + effect number) whose quad covers the whole 4:3 field: effect 35 (packet 25, quad of 12.9 x 12.9: a purple tint over the whole screen).
# The other wide quads (effect 9, 7 units) are larger than the field and remain correct; add a model here only after seeing it next to an untinted band.
FULL_SCREEN_MODELS = frozenset({5035})
ORIGINAL_ASPECT = 4.0 / 3.0          # the quad was drawn for this screen


def widen(loc, model, aspect):
    """Local coordinates (n x 3, axis 0 = screen horizontal) of a battle mesh: those of a full screen quad are stretched in width by aspect / (4/3) around their center, to cover the whole wide screen. Other
    meshes, and a screen of 4:3 proportions or narrower, are rendered as is (same object). -> coordinates to use."""
    if model not in FULL_SCREEN_MODELS or aspect <= ORIGINAL_ASPECT: return loc
    loc = np.array(loc, np.float32, copy=True)
    if len(loc) == 0: return loc
    c = (float(loc[:, 0].min()) + float(loc[:, 0].max())) / 2.0
    loc[:, 0] = c + (loc[:, 0] - c) * np.float32(aspect / ORIGINAL_ASPECT)
    return loc
