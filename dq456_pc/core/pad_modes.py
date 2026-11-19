"""Input modes of the mobile game's touch pad (the engine's MenuPortSendPadInputMode -> Unity's TouchPad.SetInputMode): which field buttons the game shows in each mode.

The engine sends the mode on port 0 ([0, 9, mode], only when it changes) and keeps the last one in a static of MenuPortSendPadInputMode (-1 before the first one: normal mode).
SetInputMode only switches buttons off (GameObject.SetActive): the usual rules of the port (Global.Flag, map bit 0x20...) still apply on top of it.

- DQ IV: no input modes (the engine has no MenuPortSendPadInputMode).
- DQ V (TouchPad.SetInputMode 0xD3B55C; MODE_NORMAL 0, MODE_SUGOROKU_A 1, MODE_SUGOROKU_B 2, MODE_SCOPE 3, MODE_SPECIAL_MODE 4): Commands and Chat only in mode 0,
  Map in modes 0 and 4, the rotation bar in every mode but 1 (T'n'T board, moving along the arrows).
- DQ VI (TouchPad.SetInputMode 0xD3E14C; MODE_NORMAL 0, MODE_HYOUTAN 1, MODE_BED 2, MODE_SUBMARINE 3, MODE_PEGASUS 4, MODE_PEGASUS_EX 5): the static table
  TouchPad.+0x90 (int[6, 3], field data of <PrivateImplementationDetails>) gives per mode (extra icon, Commands, Chat). A non-zero extra value shows the extra button
  (l_btExtra, TouchPad.Start: CreateMenuButton(0x2000, 52, 4, 8, 44, 368, -32, 1.0)) with the icon 0x33 + value: 52 Gourd Island, 53 submarine, 54 Pegasus. Its key 0x2000
  is the vehicle command the engine reads (fld::FieldCommandVehicle::isExec, pad trigger bit 13). From mode 4 on, the Commands button carries no key.
"""

EXTRA_KEY = 0x2000                      # key of DQ VI's extra button (TouchPad.PAD_START)
EXTRA_ICON_BASE = 0x33                  # its icon: 0x33 + the table's value (TouchPad.SetInputMode: SetIcon(value + 0x33))
DQ6_TABLE = ((0, 1, 1), (1, 1, 1), (0, 0, 0), (2, 1, 1), (0, 0, 1), (3, 0, 1))          # (extra icon, Commands, Chat) of modes 0 to 5
DQ5_MODES = 5


def normal(game, mode):
    """The mode as the tables read it: -1 (no mode sent yet) or an unknown value = normal mode 0."""
    n = len(DQ6_TABLE) if game == 'dq6' else DQ5_MODES if game == 'dq5' else 1
    return mode if 0 <= mode < n else 0


def shown(game, mode):
    """{element: allowed by the mode} for the field elements 'map', 'menu', 'chat', 'bar' and 'extra' (DQ VI's extra button)."""
    m = normal(game, mode)
    if game == 'dq5':
        return {'map': m in (0, 4), 'menu': m == 0, 'chat': m == 0, 'bar': m != 1, 'extra': False}
    if game == 'dq6':
        e, c, t = DQ6_TABLE[m]
        return {'map': True, 'menu': bool(c), 'chat': bool(t), 'bar': True, 'extra': bool(e)}
    return {'map': True, 'menu': True, 'chat': True, 'bar': True, 'extra': False}


def extra_icon(game, mode):
    """Icon number (MenuTexture sheet) of DQ VI's extra button in this mode, or None when the mode has no extra button."""
    if game != 'dq6': return None
    e = DQ6_TABLE[normal(game, mode)][0]
    return EXTRA_ICON_BASE + e if e else None


def static_address(code_bytes, fn):
    """Address of the static that MenuPortSendPadInputMode compares with (its first two instructions: adrp xN, page; ldrh wM, [xN, #offset]), or None.
    `code_bytes`: the function's first 8 bytes; `fn`: its address."""
    if len(code_bytes) < 8: return None
    i0 = int.from_bytes(code_bytes[:4], 'little'); i1 = int.from_bytes(code_bytes[4:8], 'little')
    if (i0 & 0x9f000000) != 0x90000000 or (i1 & 0xffc00000) != 0x79400000: return None          # adrp, then ldrh (unsigned offset)
    imm = (((i0 >> 5) & 0x7ffff) << 2) | ((i0 >> 29) & 3)
    if imm & (1 << 20): imm -= 1 << 21
    return (fn & ~0xfff) + (imm << 12) + ((i1 >> 10) & 0xfff) * 2


def adrp_add(pc, w0, w1):
    """Address that `adrp xN, page` at `pc` (word w0) then `add xN, xN, #imm` (word w1) put in xN, or None if the two words are not that pair."""
    if (w0 & 0x9f000000) != 0x90000000 or (w1 & 0xff800000) != 0x91000000: return None
    imm = (((w0 >> 5) & 0x7ffff) << 2) | ((w0 >> 29) & 3)
    if imm & (1 << 20): imm -= 1 << 21
    return (pc & ~0xfff) + (imm << 12) + (((w1 >> 10) & 0xfff) << (12 if w1 >> 22 & 1 else 0))
