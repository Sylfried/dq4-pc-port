"""The game's interface sheets extracted to the cache (ui_MenuTexture.png, 1024 x 1024; ui_Button.png): decoded once per run and shared.

Decoding a 1024 x 1024 PNG takes tens of milliseconds. The menus, the field buttons (each of their icons), the D-pad, the icon bubbles above the characters, the damage digits and the Esc menu each
decoded the sheet again on their first use; the field buttons and the bubble all appear at once the first time the player gets control (after the welcome of the church when a log is loaded),
which made a short stall. Here each file is read once; the arrays are read-only (every user copies the cells it takes)."""
import os
import numpy as np

_arrays = {}
_images = {}


def rgba(cache_folder, name_str):
    """The sheet `name_str` of the cache as a read-only RGBA array (rows from the top), decoded on the first call only. Raises the error of PIL when the file is missing or unreadable."""
    p = os.path.abspath(os.path.join(cache_folder, name_str))
    a = _arrays.get(p)
    if a is None:
        from PIL import Image
        with Image.open(p) as im: a = np.array(im.convert('RGBA'))
        a.setflags(write=False); _arrays[p] = a
    return a


def pil(cache_folder, name_str):
    """The same sheet as a PIL RGBA image (built once from the shared array)."""
    p = os.path.abspath(os.path.join(cache_folder, name_str))
    im = _images.get(p)
    if im is None:
        from PIL import Image
        im = _images[p] = Image.fromarray(np.ascontiguousarray(rgba(cache_folder, name_str)), 'RGBA')
    return im


DQ4_ICON_ROW = 224          # y of the interface block of the MenuTexture sheet in DQ IV (its icon row: PartsInfo[3]); the cursor, the back icon, the arrows, the small marks and the digits are below it


def interface_dy(window):
    """How far down the interface block of the MenuTexture sheet is in the running game, compared with DQ IV (DQ V / VI: 352, their block starts at y = 576): PartsInfo[3] of the game's
    window layout (ui_layout.json header); without the layout, the known value of the game (NO_LAYOUT_DY)."""
    try: return int(window.ui_g.ml.hdr['info'][3]['sy']) - DQ4_ICON_ROW
    except Exception:
        from dq456_pc import games as GM
        return NO_LAYOUT_DY.get(GM.profile().key, 0)


NO_LAYOUT_DY = {'dq4': 0, 'dq5': 352, 'dq6': 352}          # interface_dy of each game, for the plain menus (no ui_layout.json)
