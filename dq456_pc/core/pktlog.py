"""Structured log of the engine->Unity packets (cut at the cursor writes)."""
import struct, unicorn
CUR_I, CUR_F = 0x258278, 0x258280


class PacketLog:
    def __init__(self, core, layout=None):
        """`layout` (engine_layout.Layout): the cursors of the running game's engine and its packet numbers; without it, DQ IV's."""
        self.core = core; L = core.LIB_BASE
        self.layout = layout
        self.ci = layout.cur_i if layout and layout.cur_i else L + CUR_I
        self.cf = layout.cur_f if layout and layout.cur_f else L + CUR_F
        self.ev = []
        core.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._w, None, self.ci, self.ci + 7)
        core.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._w2, None, self.cf, self.cf + 7)
        g = core.export('_Z14UnityGetPacketi')
        core.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, s, u: self.ev.append(('G', 0)), None, g, g)
        if layout is not None and getattr(layout, 'field_floats_first', False):              # (DQ VI: the floats drawBlock writes before its packet open it, as UnityGetPacket does)
            db = core.export('_ZN9FieldData9drawBlockEv')
            if db: core.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, s, u: self.ev.append(('G', 0)), None, db, db)
    def _w(self, uc, acc, addr, size, value, user):
        if size == 8: self.ev.append(('I', value & 0xffffffffffffffff))
    def _w2(self, uc, acc, addr, size, value, user):
        if size == 8: self.ev.append(('F', value & 0xffffffffffffffff))
    def begin(self):
        self.ev = []
    def packets(self):
        """-> list [type, ints without the type, floats] for the frame that has just been computed (type: DQ IV's number, see engine_layout).
        The floats go to the "open" packet (UnityGetPacket called, not yet validated), otherwise to the last valid packet."""
        c = self.core
        out = []; pi = c.outp + 4; pf = c.outf; pend = []; opened = False
        for kind, val in self.ev:
            if kind == 'G': opened = True
            elif kind == 'F' and val > pf:
                n = (val - pf) // 4
                fl = list(struct.unpack('<%df' % n, c.mem(pf, n * 4))); pf = val
                if opened: pend += fl
                elif out: out[-1][2] += fl
            elif kind == 'I' and pi < val <= c.outp + 0x40000:
                n = (val - pi) // 4
                ints = list(struct.unpack('<%di' % n, c.mem(pi, n * 4)))
                out.append([self.layout.packet_type(ints[0]) if self.layout else ints[0], ints[1:], pend]); pend = []; pi = val; opened = False
        if pend and out: out[-1][2] += pend
        return out
