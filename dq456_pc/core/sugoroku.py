"""Dragon Quest V's T'n'T board (the engine's "sugoroku"): the direction arrows that Unity's Make_Sugoroku_Arrow window shows on the board.

The engine plays the board itself (dice, squares, events) in the town map of the board: its squares are one MeshChara (Custom/DssaNormal shader, texture m8100) drawn
by battle_scene (ground meshes), its menus are ordinary windows. The direction arrows are the two icons of the window of type ARROW_TYPE, placed in the world:
TownSugorokuArrow::draw sends, for arrow i (code i = 0 or 1):
- [12, i, 0x100] then the array of 3 floats (6 shorts): its position in the map (x, y, -z of the engine: like the squares' vertices);
- [12, i, 0x200] then 1 float: its turn around the vertical axis, in degrees (Transform.rotation = Euler(its x, angle, its z));
- [12, i, 0x300 | frame]: the icon of its animation (0 to 5 of the PartsInfo sheet ARROW_PARTS);
and code 10 = the active arrows (bit i: arrow i shown). The window is drawn while the engine asks for it every frame (MenuItem::drawActive).
The arrows are 1.8 x 1.8 units icons (MenuParts.AddIcon(Vector3.zero, 0, true, 1.8, 1.8)) on the Default layer: in the scene, seen by the town's camera, lying on the board.
To move, the player pushes the direction of an arrow: the engine reads its pad (window::NormalControl::executePlayer, then SugorokuSystemPlayerMove::sugorokuMoveSet).
"""
import math
import struct

import numpy as np

ARROW_TYPE = 87                              # DQ V's window type of Make_Sugoroku_Arrow (MenuPortItemTable)
ARROW_PARTS = 14                             # MenuPartsCommon.ICON_SUGOROKU_ARROW: PartsInfo index of the arrow icons (MenuTexture sheet)
ARROW_SIZE = 1.8                             # MenuParts.AddIcon(..., sizeW 1.8, sizeH 1.8)
ARROW_TILT = 90.0                            # the icon lies on the board (rotation x of its MenuParts)
POSITION, TURN, FRAME = 1, 2, 3              # (code value >> 8) of an arrow's code
ACTIVE_CODE = 10                             # code 10: bit i = arrow i shown
ARROWS = (0, 1)


def floats(values):
    """The floats of a MenuPort.Receive array (values of 16 bits, two per float, low half first)."""
    raw = struct.pack('<%dH' % len(values), *[v & 0xffff for v in values])
    return list(struct.unpack('<%df' % (len(raw) // 4), raw[:len(raw) // 4 * 4]))


def code(f, i, v):
    """Code `i` = `v` of the arrow window `f` (an engine window dict): an arrow's frame, or the announcement of the array that follows (kept in f['arrow_pending'])."""
    if i not in ARROWS: return
    a = f.setdefault('arrows', {}).setdefault(i, {'pos': None, 'turn': 0.0, 'frame': 0})
    kind = (v >> 8) & 0xff
    if kind in (POSITION, TURN): f['arrow_pending'] = (i, kind)
    elif kind == FRAME: a['frame'] = v & 0xff


def receive(f, values):
    """The array that follows an arrow's code 0x100 or 0x200 (MenuPort.Receive)."""
    i, kind = f.pop('arrow_pending')
    fl = floats(values); a = f.setdefault('arrows', {}).setdefault(i, {'pos': None, 'turn': 0.0, 'frame': 0})
    if kind == POSITION and len(fl) >= 3: a['pos'] = tuple(fl[:3])
    elif kind == TURN and fl: a['turn'] = fl[0]


def shown(f):
    """[(position, turn in degrees, frame)] of the arrows the window shows."""
    if not f or not f.get('visible'): return []
    mask = f.get('indicators', {}).get(ACTIVE_CODE, 0)
    return [(a['pos'], a['turn'], a['frame']) for i, a in sorted(f.get('arrows', {}).items()) if mask >> i & 1 and a['pos'] is not None]


def euler(x, y, z):
    """Unity's Quaternion.Euler(x, y, z) as a 3 x 3 matrix (rotation z, then x, then y; degrees)."""
    rx, ry, rz = (math.radians(t) for t in (x, y, z))
    X = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    Y = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Z = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    return Y @ X @ Z


def corners(pos, turn, tilt=ARROW_TILT, size=ARROW_SIZE):
    """The 4 corners (top left, top right, bottom right, bottom left of the icon) of an arrow in the map: its square of `size` in its local XY plane, turned by Euler(tilt, turn, 0)."""
    h = size / 2.0
    local = np.array([[-h, h, 0.0], [h, h, 0.0], [h, -h, 0.0], [-h, -h, 0.0]])
    return local @ euler(tilt, turn, 0.0).T + np.array(pos, float)


def icon_rect(info, frame):
    """(x, y, size) in pixels of the sheet of the arrow's icon `frame` (PartsInfo.SetUV: number frame + startNo, widthNum per row from startV)."""
    n = frame + info['startNo']; w = info['widthNum']; px = info['ps'] if 'ps' in info else int(round(info['uvsize'] * info['W']))
    return (n % w) * px, int(round(info['startV'] * info['W'])) + (n // w) * px, px


UP, DOWN, LEFT, RIGHT = 0x1, 0x2, 0x4, 0x8   # the engine's key bits (engine.UP...)
HOLD = 8                                     # engine steps a clicked arrow's direction stays pushed


def tip(turn, tilt=ARROW_TILT):
    """The direction the arrow points to in the map (the icon's +Y axis turned by Euler(tilt, turn, 0))."""
    return euler(tilt, turn, 0.0) @ np.array([0.0, 1.0, 0.0])


def key_of(dx, dy):
    """The direction key of a move on the screen (dx to the right, dy upward): the larger of the two."""
    if abs(dx) >= abs(dy): return RIGHT if dx > 0 else LEFT
    return UP if dy > 0 else DOWN


def inside(pt, quad, grow=1.0):
    """Is the point `pt` in the convex quadrilateral `quad` (4 screen points), enlarged `grow` times around its center?"""
    q = np.array(quad, float); c = q.mean(0); q = c + (q - c) * grow; x, y = pt; sign = 0
    for k in range(4):
        (x0, y0), (x1, y1) = q[k], q[(k + 1) % 4]
        s = (x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)
        if abs(s) < 1e-12: continue
        if sign == 0: sign = 1 if s > 0 else -1
        elif (s > 0) != (sign > 0): return False
    return True
