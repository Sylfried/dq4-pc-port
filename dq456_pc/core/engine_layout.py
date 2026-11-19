"""What differs between the engines of the three games, for the engine driver (engine.py) and the packet log (pktlog.py).

Dragon Quest V and VI share a newer version of Dragon Quest IV's engine:
- the drawing commands sent to Unity (NativeManager's `cmd_*` table, read in the C# code of each game) are numbered differently: three commands that DQ IV
  does not have (`cmd_fld_etc`, `cmd_mesh_ortho`, `cmd_particle`) are inserted. The port keeps DQ IV's numbers everywhere and translates the others (`packet_type`);
  the new commands get the numbers FLD_ETC, MESH_ORTHO and PARTICLE;
- the current game part (title, town, battle, world map...) is kept by `args::GamePartManager` (+ 0x1c) instead of `Global` (+ 0xee), with other numbers:
  they are translated to DQ IV's (`PARTS_V2`), the parts DQ IV does not have get 0x100 + their number;
- the static variables the port reads (packet cursors, message window, menu manager...) are at other addresses: they are found in the code of exported
  functions that use them (`data_refs`), the same way for the three games (for DQ IV the result is checked against the addresses known before)."""
import struct

FLD_ETC, MESH_ORTHO, PARTICLE = 100, 101, 102           # packets of DQ V / VI that DQ IV does not have
PART_EXTRA = 0x100                                      # + the engine's number: a part that DQ IV does not have

# DQ V / VI part numbers (GamePartManager::ChangeGamePart in Global::startTown, startBattle, startField, startCasino, startBook) -> DQ IV's
# (PART_TOWN 0xc, PART_BATTLE 0xd, PART_FIELD 0xe, PART_CASINO 0xf, PART_BESTIARY 0x10); 3 = the start menu in both. 0xb (Global::startTitle: logos, title, credits) is a scene
# drawn like a town (its own map, DQ V: ev17), as DQ IV's title.
PARTS_V2 = {3: 0x3, 4: 0xc, 5: 0xd, 6: 0xe, 7: 0xf, 8: 0x10, 0xb: 0xc}
# DQ VI numbers its parts one higher (Global::loadGame 4, startTown 5, startBattle 6, startField 7, startCasino 8, startBook 9, startTitle 0xa; 0xb = startCurling)
PARTS_DQ6 = {4: 0x3, 5: 0xc, 6: 0xd, 7: 0xe, 8: 0xf, 9: 0x10, 0xa: 0xc}
PARTS = {'dq5': PARTS_V2, 'dq6': PARTS_DQ6}
PART_MANAGER_V2 = ('_ZN4args17g_GamePartManagerE', 0x1c)      # (u16; + 0x1e: the next part)
PART_GLOBAL_V1 = 0xee                                          # DQ IV: Global + 0xee (u16; + 0xf0: the next part)


def packets_v2():
    """{DQ V / VI packet number: DQ IV packet number}."""
    m = {i: i for i in range(8)}                                # cmd_fld_load .. cmd_fld_on_off
    m[8] = FLD_ETC; m[9] = 8                                    # cmd_fld_etc, cmd_back_color
    m.update({i: i - 1 for i in range(10, 28)})                 # cmd_fade .. cmd_mesh_tex_offset
    m[28] = MESH_ORTHO
    m.update({i: i - 2 for i in range(29, 40)})                 # cmd_field_load .. cmd_bgm
    m[40] = PARTICLE
    return m


def data_refs(core, address, size=0x200):
    """The data addresses (library offsets) that the code from `address` builds with `adrp` + `add` / `ldr` / `str` (immediate offset), in order, up to the first `ret`."""
    out, pages = [], {}
    base = core.LIB_BASE
    raw = core.mem(address, size)
    for k in range(0, len(raw) - 3, 4):
        w, = struct.unpack_from('<I', raw, k); pc = address + k
        if w == 0xd65f03c0: break                                                        # ret
        if (w & 0x9f000000) == 0x90000000:                                               # adrp
            imm = (((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3)
            if imm & (1 << 20): imm -= 1 << 21
            pages[w & 31] = (pc & ~0xfff) + (imm << 12); continue
        rn = (w >> 5) & 31
        if rn not in pages: continue
        if (w & 0xff800000) == 0x91000000:                                               # add xd, xn, #imm (xd then holds that address)
            t = pages[rn] + ((w >> 10) & 0xfff) * (4096 if (w >> 22) & 1 else 1)
            out.append(t - base); pages[w & 31] = t
        elif (w & 0x3b000000) == 0x39000000:                                             # ldr / str (unsigned offset), any size
            out.append(pages[rn] + (((w >> 10) & 0xfff) << (w >> 30)) - base)
    return out


# The message window (ui_MsgLoop's state, from `msg_state`; SDrawCTRL of the canvas, `obj_message`): offsets of the fields the port reads. DQ V / VI insert a word at + 0x10 of the state
# (the fields after it move by 4: ui_MsgLoop, ui_MsgSetup); DQ V also inserts 8 bytes at the start of SDrawCTRL (all its fields move by 8: CanvasSetup, GetMessageCanvas, ui_MsgSystemInit),
# DQ VI does not: the shift is read in SDrawCTRL::CanvasSetup, whose first `ldr x, [x20, #imm]` reads the port (DQ IV + 0x30).
MSG_FIELDS = {'active': 0x2, 'lines': 0x14, 'speed': 0x24, 'current': 0x40, 'end': 0x42}       # open (byte), visible lines - 1, letters per frame / 4, current letter, end of line
CANVAS_FIELDS = {'buffer': 0x10, 'port': 0x30, 'line_height': 0x42, 'cursor': 0x46, 'scroll': 0x4a}      # text bitmap, its MenuPort, height of a line, write position (x, y: 2 u16), current scroll
MSG_INSERT_V2, CANVAS_SHIFT_V2 = (0x10, 4), 8


def msg_fields(v2):
    return {k: v + (MSG_INSERT_V2[1] if v2 and v >= MSG_INSERT_V2[0] else 0) for k, v in MSG_FIELDS.items()}


def canvas_fields(shift):
    """`shift`: True / False (DQ V's shift or none) or the number of bytes."""
    if isinstance(shift, bool): shift = CANVAS_SHIFT_V2 if shift else 0
    return {k: v + shift for k, v in CANVAS_FIELDS.items()}


def canvas_shift(core, setup):
    """The SDrawCTRL shift of this engine, from SDrawCTRL::CanvasSetup (`setup`): its first load through x20 (this) reads the port; None if not found."""
    raw = core.mem(setup, 0x80)
    for k in range(0, len(raw), 4):
        w, = struct.unpack_from('<I', raw, k)
        if w == 0xd65f03c0: break
        if (w & 0xffc003e0) == 0xf9400280: return ((w >> 10) & 0xfff) * 8 - CANVAS_FIELDS['port']        # ldr x, [x20, #imm]
    return None


# The world map (FieldData, the object whose drawBlock sends the tiles around the hero; its CWorldMap holds the whole grid of block numbers, 1-based, 10 bits):
# DQ IV: CWorldMap at + 0x180 (grid + 8, width and height + 0x18 as two int32); DQ V / VI: CWorldMap at + 0x1b0 (header bytes w0, h0, w1, h1 at [+ 0]: width = w0 * w1,
# height = h0 * h1; grid + 0x10), and each block of the grid also has a tile orientation (CWorldMap::getUV: a nibble per block at [+ 0x30], an index into 8-byte entries at
# [+ 0x28] whose first byte is the orientation, sent as bits 12-15 of the tile). The block table (6 bytes per block: kind at + 1, tile at + 2, other tile at + 4) is at
# + 0x180 / + 0x1d0; the animated kinds add a frame offset: kind 0 -> tile 2 + anim0, kind 8 -> tile 1 + anim8, kind 0x18 -> tile 1 + anim18 (library halfwords, ascending
# addresses, read by drawBlock with ldrsh), DQ V / VI add the FieldData words + 0x208 (kind 8) and + 0x20c (kind 0x18).
WORLD_V1 = {'blocks': 0x180, 'grid': 0x188, 'size': 0x198}
WORLD_V2 = {'map': 0x1b0, 'blocks': 0x1d0, 'anim8': 0x208, 'anim18': 0x20c}


def halfword_refs(core, address, size=0x200):
    """The library offsets that the code from `address` reads with `ldrsh w, [x, #imm]` after an `adrp` of that register, up to the first `ret`."""
    out, pages = [], {}
    raw = core.mem(address, size)
    for k in range(0, len(raw) - 3, 4):
        w, = struct.unpack_from('<I', raw, k); pc = address + k
        if w == 0xd65f03c0: break
        if (w & 0x9f000000) == 0x90000000:
            imm = (((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3)
            if imm & (1 << 20): imm -= 1 << 21
            pages[w & 31] = (pc & ~0xfff) + (imm << 12); continue
        if (w & 0xffc00000) == 0x79c00000 and ((w >> 5) & 31) in pages:              # ldrsh w (unsigned offset)
            out.append(pages[(w >> 5) & 31] + (((w >> 10) & 0xfff) << 1) - core.LIB_BASE)
        if not ((w & 0x3b400000) == 0x39000000): pages.pop(w & 31, None)           # any other instruction than a store may overwrite its first register: its page is forgotten
    return out


# DQ IV's addresses (library offsets), as known before the other games: `Layout.fixed` (engines built without their library, in the tests) and the check of `Layout`
DQ4 = {'global_object': 0x258158, 'is_amazon': 0x24f684, 'cur_i': 0x258278, 'cur_f': 0x258280, 'obj_message': 0x252330, 'msg_state': 0x25238c, 'menu_manager': 0x252078,
       'resource_name': 0x258290, 'input_buffer': 0x2582c0, 'menu_ports_count': 0x252094, 'menu_ports': 0x252098}
DQ4_WORLD_ANIM = (0x275830, 0x275834, 0x275838)


class Layout:
    """The layout of the running game's engine (`core`: emu_core.Core with the library loaded). Missing pieces are None: the features that need them are left out."""
    resource_name = None            # (fixed layout only) address of the map name requested from Unity; otherwise strings[0] of GameInit, see map_name
    input_buffer = None             # (fixed layout only) address of the pointer to GameUpdate's input buffer; otherwise core.inp, see messages_to_engine

    @classmethod
    def fixed(cls, lib_base):
        """DQ IV's layout from its known addresses, without reading the library."""
        self = cls.__new__(cls)
        self.v2 = False; self.packets = None; self.msg = msg_fields(False); self.canvas = canvas_fields(False)
        for k, v in DQ4.items(): setattr(self, k, lib_base + v)
        self.world_anim = tuple(lib_base + a for a in DQ4_WORLD_ANIM)
        self.part_address = self.global_object + PART_GLOBAL_V1
        return self

    def __init__(self, core, v2, game=None):
        self.v2 = v2
        self.parts = PARTS.get(game, PARTS_V2)
        self.field_floats_first = game == 'dq6'           # DQ VI's FieldData::drawBlock asks for its 2 camera floats before writing its packet 28 (UnitySetPacket(0x1e, opt)): they belong to it
        self.packets = packets_v2() if v2 else None
        E = core.export
        cs = E('_ZN9SDrawCTRL11CanvasSetupEPvPKs'); sh = canvas_shift(core, cs) if cs else None
        self.msg = msg_fields(v2); self.canvas = canvas_fields(v2 if sh is None else sh)
        self.global_object = E('g_Global')
        self.is_amazon = E('g_isAmazon') or E('g_IsAmazon')
        if v2:
            p = E(PART_MANAGER_V2[0]); self.part_address = p + PART_MANAGER_V2[1] if p else None
        else:
            self.part_address = self.global_object + PART_GLOBAL_V1 if self.global_object else None
        ref = lambda name, n=0: (lambda r: core.LIB_BASE + r[n] if len(r) > n else None)(data_refs(core, E(name))) if E(name) else None
        self.cur_i = ref('_Z14UnityGetPacketi')
        self.cur_f = ref('_Z19UnitySetFloatPacketPf')
        canvas = ref('GetMessageCanvas')
        self.obj_message = canvas - self.canvas['buffer'] if canvas else None       # SDrawCTRL of the message window (GetMessageCanvas reads its canvas bitmap)
        self.msg_state = ref('_Z12ui_MsgIsNonev')                                    # ui_MsgLoop's state (u16); its other fields: `msg`
        self.menu_manager = ref('_ZN11MenuManager5setupEv')                          # pointer to the MenuManager (at + 8, the open menus)
        self.menu_ports_count = ref('MenuPortInit', 0)                                  # (i16) number of MenuPort entries, and the pointer to their table (0x20 bytes each), written by MenuPortInit
        self.menu_ports = ref('MenuPortInit', 1)
        db = E('_ZN9FieldData9drawBlockEv')
        anim = sorted(set(halfword_refs(core, db))) if db else []
        self.world_anim = tuple(core.LIB_BASE + a for a in anim) if len(anim) == 3 else None      # animation offsets of the block kinds 0, 8, 0x18 (see WORLD_V1)

    def map_name(self, core):
        """The name of the map resource that the engine has just requested from Unity (UnitySetString writes it in strings[0])."""
        p = self.resource_name if self.resource_name else struct.unpack('<Q', core.mem(core.strb, 8))[0]
        return core.read_cstr(p).decode('latin-1') if p else ''

    def messages_to_engine(self, core):
        """Address of GameUpdate's input buffer (the Unity -> engine messages)."""
        return struct.unpack('<Q', core.mem(self.input_buffer, 8))[0] if self.input_buffer else core.inp

    def packet_type(self, t):
        """The DQ IV number of a packet number sent by this engine."""
        return t if self.packets is None else self.packets.get(t, PART_EXTRA + t)

    def part(self, core):
        """The current game part, in DQ IV's numbers."""
        if self.part_address is None: return 0
        p = struct.unpack('<H', core.mem(self.part_address, 2))[0]
        return self.parts.get(p, PART_EXTRA + p) if self.v2 else p
