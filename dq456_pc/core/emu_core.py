#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Engine of the original game under Unicorn: AArch64 ELF loader, APK file system, emulated memory and libc functions (`Core`).

Loads `libdq4core.so` (the engine's 64-bit ARM code, never modified) into an emulator (Unicorn)
on PC, without Unity. The game files are read directly from the player's APKs (nothing is copied
or distributed). The driving code (steps, hooks, packets) is in `engine.py`.
"""
import os, struct, re, time, zipfile, bisect, traceback
import numpy as np

MASK64 = (1 << 64) - 1
PAGE = 0x1000


def up(x, a=PAGE):
    return (x + a - 1) & ~(a - 1)


# ----------------------------------------------------------------------------------------------
# Log: screen + file
# ----------------------------------------------------------------------------------------------
class Log:
    def __init__(self, path=None):
        self.f = open(path, 'w', encoding='utf-8', errors='replace') if path else None

    def __call__(self, *a):
        s = ' '.join(str(x) for x in a)
        try:
            print(s)
        except Exception:
            print(s.encode('ascii', 'replace').decode())
        if self.f:
            self.f.write(s + '\n')
            self.f.flush()


# ----------------------------------------------------------------------------------------------
# ELF 64-bit AArch64
# ----------------------------------------------------------------------------------------------
DT_PLTRELSZ, DT_HASH, DT_STRTAB, DT_SYMTAB, DT_RELA, DT_RELASZ = 2, 4, 5, 6, 7, 8
DT_INIT, DT_JMPREL, DT_INIT_ARRAY, DT_INIT_ARRAYSZ, DT_GNU_HASH = 12, 23, 25, 27, 0x6ffffef5
DT_RELRSZ, DT_RELR = 35, 36
R_ABS64, R_GLOB_DAT, R_JUMP_SLOT, R_RELATIVE = 257, 1025, 1026, 1027


def _component(name, i):
    """(end index, text) of the <length><identifier> component of a mangled name starting at `i`, or None."""
    j = i
    while j < len(name) and name[j].isdigit(): j += 1
    if j == i: return None
    n = int(name[i:j])
    return (j + n, name[i:j + n]) if j + n <= len(name) else None


def strip_namespace(name):
    """The mangled name without its first nested component: `_ZN3fld9FieldData9drawBlockEv` -> `_ZN9FieldData9drawBlockEv`,
    `_ZN4ardq10ui_MsgLoopEv` -> `_Z10ui_MsgLoopv` (a function directly in the namespace), `_ZN4menu18gMaterielMenu_SAVEE` -> `gMaterielMenu_SAVE` (a variable directly
    in the namespace: at global scope its name is not mangled), `_ZNK...` kept const. None if the name is not nested."""
    if not name.startswith('_ZN'): return None
    i = 3; cv = ''
    while i < len(name) and name[i] in 'KVr': cv += name[i]; i += 1
    first = _component(name, i)
    if first is None: return None
    rest = name[first[0]:]
    second = _component(rest, 0) if rest[:1].isdigit() else None
    if second is None: return None
    after = rest[second[0]:]
    if after == 'E' and not cv: return second[1].lstrip('0123456789')        # a variable
    if after.startswith('E') and not cv:
        return '_Z' + second[1] + after[1:]           # a single component left: no longer a nested name
    return '_ZN' + cv + rest


class Elf:
    def __init__(self, data):
        if data[:4] != b'\x7fELF' or data[4] != 2:
            raise ValueError("this file is not a 64-bit ELF")
        e_machine = struct.unpack_from('<H', data, 18)[0]
        if e_machine != 183:
            raise ValueError("this is not 64-bit ARM code")
        e_phoff = struct.unpack_from('<Q', data, 0x20)[0]
        e_phentsize, e_phnum = struct.unpack_from('<HH', data, 0x36)
        segs = []
        for i in range(e_phnum):
            segs.append(struct.unpack_from('<IIQQQQQQ', data, e_phoff + i * e_phentsize))
        loads = [s for s in segs if s[0] == 1]
        self.size = up(max(s[3] + s[6] for s in loads))
        self.img = bytearray(self.size)
        for (t, fl, off, va, pa, fsz, msz, al) in loads:
            self.img[va:va + fsz] = data[off:off + fsz]
        dyn = [s for s in segs if s[0] == 2]
        if not dyn:
            raise ValueError('no dynamic section')
        self.dyn = {}
        p = dyn[0][3]
        while True:
            tag, val = struct.unpack_from('<qQ', self.img, p)
            p += 16
            if tag == 0:
                break
            self.dyn.setdefault(tag, []).append(val)
        d = self.dyn
        self.symtab, self.strtab = d[DT_SYMTAB][0], d[DT_STRTAB][0]
        self.nsyms = self._count_syms()
        self.syms = []
        for i in range(self.nsyms):
            st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
                '<IBBHQQ', self.img, self.symtab + 24 * i)
            self.syms.append((self._str(st_name), st_info >> 4, st_info & 15, st_shndx, st_value, st_size))
        self.exports = {}
        funcs = []
        for (name, bind, typ, shndx, val, sz) in self.syms:
            if shndx != 0 and name:
                self.exports[name] = val
                if typ == 2:
                    funcs.append((val, sz, name))
        funcs.sort()
        self.func_starts = [f[0] for f in funcs]
        self.funcs = funcs

    def _u32(self, o):
        return struct.unpack_from('<I', self.img, o)[0]

    def _str(self, off):
        p = self.strtab + off
        e = self.img.index(b'\0', p)
        return bytes(self.img[p:e]).decode('utf-8', 'replace')

    def _count_syms(self):
        d = self.dyn
        if DT_HASH in d:
            return self._u32(d[DT_HASH][0] + 4)
        h = d[DT_GNU_HASH][0]
        num, symoff, bloom, shift = struct.unpack_from('<IIII', self.img, h)
        buckets = h + 16 + bloom * 8
        chains = buckets + num * 4
        maxb = max(self._u32(buckets + 4 * i) for i in range(num))
        if maxb < symoff:
            return symoff
        idx = maxb
        while not (self._u32(chains + 4 * (idx - symoff)) & 1):
            idx += 1
        return idx + 1

    def aliases(self):
        """{name without its first namespace: offset} for the exported C++ names that are inside a namespace (see Core.export); names found twice are left out."""
        if getattr(self, '_aliases', None) is None:
            found, twice = {}, set()
            for name, off in self.exports.items():
                alias = strip_namespace(name)
                if alias is None or alias in self.exports: continue
                if alias in found and found[alias] != off: twice.add(alias)
                found[alias] = off
            self._aliases = {k: v for k, v in found.items() if k not in twice}
        return self._aliases

    def relocate(self, base, stub_for):
        """Applies the relocations in the image. stub_for(name, bind) -> address of an external import."""
        d = self.dyn
        if DT_RELR in d:
            raise ValueError('RELR relocations not supported')
        st = {'ABS64': 0, 'GLOB_DAT': 0, 'JUMP_SLOT': 0, 'RELATIVE': 0, 'unknown': {},
              'internal': 0, 'external': set()}
        tables = []
        if DT_RELA in d:
            tables.append((d[DT_RELA][0], d[DT_RELASZ][0]))
        if DT_JMPREL in d:
            tables.append((d[DT_JMPREL][0], d[DT_PLTRELSZ][0]))
        cache = {}
        for off, sz in tables:
            for i in range(sz // 24):
                r_off, r_info, r_add = struct.unpack_from('<QQq', self.img, off + 24 * i)
                t, sym_idx = r_info & 0xffffffff, r_info >> 32
                if t == R_RELATIVE:
                    val = base + r_add
                    st['RELATIVE'] += 1
                elif t in (R_ABS64, R_GLOB_DAT, R_JUMP_SLOT):
                    if sym_idx == 0:
                        S = 0
                    else:
                        name, bind, typ, shndx, value, size = self.syms[sym_idx]
                        if shndx != 0:
                            S = base + value
                            st['internal'] += 1
                        else:
                            if name not in cache:
                                cache[name] = stub_for(name, bind)
                            S = cache[name]
                            st['external'].add(name)
                    val = S + (r_add if t in (R_ABS64, R_GLOB_DAT) else 0)
                    st[{R_ABS64: 'ABS64', R_GLOB_DAT: 'GLOB_DAT', R_JUMP_SLOT: 'JUMP_SLOT'}[t]] += 1
                else:
                    st['unknown'][t] = st['unknown'].get(t, 0) + 1
                    continue
                struct.pack_into('<Q', self.img, r_off, val & MASK64)
        return st

    def init_functions(self, base):
        """Addresses of the constructors, in call order (after relocation)."""
        out = []
        d = self.dyn
        if DT_INIT in d:
            out.append(base + d[DT_INIT][0])
        if DT_INIT_ARRAY in d:
            a, n = d[DT_INIT_ARRAY][0], d[DT_INIT_ARRAYSZ][0]
            for i in range(n // 8):
                p = struct.unpack_from('<Q', self.img, a + 8 * i)[0]
                if p not in (0, MASK64):
                    out.append(p)
        return out


# ----------------------------------------------------------------------------------------------
# Game files: read from the APKs
# ----------------------------------------------------------------------------------------------
class ApkFs:
    def __init__(self, zips):
        self.zips = [zipfile.ZipFile(z) for z in zips]
        self.names = {}
        for zf in self.zips:
            for n in zf.namelist():
                self.names.setdefault(n, zf)
        self.cache = {}

    def open(self, rel):
        for cand in ('assets/' + rel, rel):
            if cand in self.cache:
                return self.cache[cand]
            zf = self.names.get(cand)
            if zf is not None:
                data = zf.read(cand)
                if len(self.cache) < 200:
                    self.cache[cand] = data
                return data
        return None


# ----------------------------------------------------------------------------------------------
# minimal printf (AArch64 va_list)
# ----------------------------------------------------------------------------------------------
_FMT = re.compile(rb'%([-+ #0]*)(\d+|\*)?(?:\.(\d+|\*))?(hh|h|ll|l|z|j|t|L)?([diouxXcsfFeEgGpn%])')


class VaList:
    def __init__(self, core, ptr):
        self.c, self.p = core, ptr

    def _u64(self, a):
        return int.from_bytes(self.c.mem(a, 8), 'little')

    def gp(self):
        c, p = self.c, self.p
        stack, grtop = self._u64(p), self._u64(p + 8)
        gr = int.from_bytes(c.mem(p + 24, 4), 'little', signed=True)
        if gr >= 0 or gr + 8 > 0:
            addr = stack
            c.mem_w(p, ((stack + 8) & MASK64).to_bytes(8, 'little'))
        else:
            addr = grtop + gr
            c.mem_w(p + 24, (gr + 8).to_bytes(4, 'little', signed=True))
        return self._u64(addr)

    def fp(self):
        c, p = self.c, self.p
        stack, vrtop = self._u64(p), self._u64(p + 16)
        vr = int.from_bytes(c.mem(p + 28, 4), 'little', signed=True)
        if vr >= 0 or vr + 16 > 0:
            addr = stack
            c.mem_w(p, ((stack + 8) & MASK64).to_bytes(8, 'little'))
        else:
            addr = vrtop + vr
            c.mem_w(p + 28, (vr + 16).to_bytes(4, 'little', signed=True))
        return struct.unpack('<d', c.mem(addr, 8))[0]


def format_c(core, fmt, va):
    out = bytearray()
    pos = 0
    for m in _FMT.finditer(fmt):
        out += fmt[pos:m.start()]
        pos = m.end()
        flags, width, prev, length, conv = m.groups()
        conv = conv.decode()
        if conv == '%':
            out += b'%'
            continue
        if width == b'*':
            v = va.gp() & 0xffffffff
            width = str(v - (1 << 32) if v >> 31 else v).encode()
        if prev == b'*':
            v = va.gp() & 0xffffffff
            prev = str(max(v - (1 << 32) if v >> 31 else v, 0)).encode()
        spec = '%' + flags.decode() + (width.decode() if width else '') + ('.' + prev.decode() if prev else '')
        if conv in 'di':
            v = va.gp()
            bits = 64 if length in (b'l', b'll', b'z', b'j', b't') else 32
            v &= (1 << bits) - 1
            if v >> (bits - 1):
                v -= 1 << bits
            out += ((spec + 'd') % v).encode()
        elif conv in 'ouxX':
            v = va.gp()
            bits = 64 if length in (b'l', b'll', b'z', b'j', b't') else 32
            out += ((spec + conv) % (v & ((1 << bits) - 1))).encode()
        elif conv == 'c':
            out += bytes([va.gp() & 0xff])
        elif conv == 's':
            p = va.gp()
            s = core.read_cstr(p).decode('latin-1') if p else '(null)'
            out += ((spec + 's') % s).encode('latin-1')
        elif conv in 'fFeEgG':
            out += ((spec + conv) % va.fp()).encode()
        elif conv == 'p':
            out += ('0x%x' % va.gp()).encode()
        elif conv == 'n':
            va.gp()
    out += fmt[pos:]
    return bytes(out)


# ----------------------------------------------------------------------------------------------
# Emulator
# ----------------------------------------------------------------------------------------------
class Core:
    LIB_BASE = 0x10000000
    STUB_BASE, STUB_SIZE = 0x08000000, 0x100000
    HEAP_BASE, HEAP_SIZE = 0x20000000, 0x10000000
    STACK_BASE, STACK_SIZE = 0x40000000, 0x800000
    TLS_BASE, TLS_SIZE = 0x41000000, 0x10000
    DATA_BASE, DATA_SIZE = 0x42000000, 0x10000
    FILE_BASE = 0x60000000
    DATA_IMPORTS = ('__stack_chk_guard',)
    # memcpy / memmove in ARM64 code (x0 = destination, x1 = source, x2 = size; overlap-safe: forward when destination - source >= size, unsigned, otherwise backward; 8 bytes at a time,
    # then byte by byte; returns x0): the engine calls memcpy 12 (DQ IV), 51 (DQ V), 23 (DQ VI) times a step, and each call through the Python hook cost about 30 microseconds
    # (three register reads, a memory read, a memory write): up to 1.5 ms of a 3 ms step. The routine lives in the last page of the stub region; the import keeps its slot, which holds a
    # branch to the routine and is left out of the hook's ranges. The relocated library is unchanged (its fingerprint tells which engine a savestate belongs to: every existing state stays valid).
    NATIVE_SIZE = 0x1000
    _args = None                   # (X0 to Xn-1 in one call: _install_fast_access)
    # strncmp, strcmp, strlen likewise (STRINGS_NATIVE, from offset 0x80 of the page; byte by byte, the result's sign as bionic's: the difference of the first unequal unsigned bytes):
    # the engine calls strncmp by the ten thousand in some scenes (name lookups: 24 000 to 49 000 calls in 900 steps, 974 in a single DQ VI town step), at about 40 microseconds each through the hook.
    NATIVE_TARGETS = {'memcpy': 0, 'memmove': 0, '__memcpy_chk': 0, 'strncmp': 0x80, 'strcmp': 0xb0, 'strlen': 0xd4}          # import -> offset of its routine in the native page
    NATIVE_IMPORTS = tuple(NATIVE_TARGETS)
    STRINGS_NATIVE = struct.pack('<27I', 0xb4000102, 0x38401403, 0x38401424, 0x6b040065, 0x540000c1, 0x34000063, 0xf1000442, 0x54ffff41, 0x52800000, 0xd65f03c0, 0x2a0503e0, 0xd65f03c0,      # strncmp
                                 0x38401403, 0x38401424, 0x6b040065, 0x54000081, 0x35ffff83, 0x52800000, 0xd65f03c0, 0x2a0503e0, 0xd65f03c0,                                                        # strcmp
                                 0xaa0003e1, 0x38401422, 0x35ffffe2, 0xcb000020, 0xd1000400, 0xd65f03c0)                                                                                                # strlen
    MEMCPY_NATIVE = struct.pack('<30I', 0xb40003a2, 0xaa0003e3, 0xcb010004, 0xeb02009f, 0x540001c2, 0x8b020003, 0x8b020021, 0xf100205f, 0x540000a3, 0xf85f8c25, 0xf81f8c65, 0xd1002042, 0x17fffffb,
                                0xb4000202, 0x385ffc25, 0x381ffc65, 0xd1000442, 0x17fffffc, 0xf100205f, 0x540000a3, 0xf8408425, 0xf8008465, 0xd1002042, 0x17fffffb, 0xb40000a2, 0x38401425,
                                0x38001465, 0xd1000442, 0x17fffffc, 0xd65f03c0)

    def __init__(self, libdata, fs, log, assets_dir='/dq/assets', save_dir='/dq/save', real_files=None):
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ_UNMAPPED, UC_HOOK_MEM_WRITE_UNMAPPED, \
            UC_HOOK_MEM_FETCH_UNMAPPED
        import unicorn.arm64_const as C
        self.C = C
        self.XREG = [getattr(C, 'UC_ARM64_REG_X%d' % i) for i in range(31)]
        self.log, self.fs = log, fs
        self.real_files = real_files or {}
        self.assets_dir, self.save_dir = assets_dir.rstrip('/'), save_dir.rstrip('/')
        self.elf = Elf(libdata)
        uc = self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.reg_write(C.UC_ARM64_REG_CPACR_EL1, 0x300000)  # enables FP / NEON
        # memory
        uc.mem_map(self.STUB_BASE, self.STUB_SIZE, UC_PROT_ALL)
        uc.mem_write(self.STUB_BASE, bytes.fromhex('c0035fd6') * (self.STUB_SIZE // 4))  # "ret" everywhere
        self.native_base = self.STUB_BASE + self.STUB_SIZE - self.NATIVE_SIZE
        self.native = not os.environ.get('DQ_NO_NATIVE_IMPORTS')          # (test) DQ_NO_NATIVE_IMPORTS=1: every import through its Python handler
        uc.mem_write(self.native_base, self.native_code())
        uc.mem_map(self.HEAP_BASE, self.HEAP_SIZE, UC_PROT_ALL)
        uc.mem_map(self.STACK_BASE, self.STACK_SIZE, UC_PROT_ALL)
        uc.mem_map(self.TLS_BASE, self.TLS_SIZE, UC_PROT_ALL)
        uc.mem_map(self.DATA_BASE, self.DATA_SIZE, UC_PROT_ALL)
        self.RET = self.STUB_BASE  # return address of calls (stub 0)
        self.stub_names = ['<retour>']
        self.stub_idx = {}
        self.data_ptr = self.DATA_BASE
        self.heap_ptr = self.HEAP_BASE
        self.heap_blocks = {}          # pointer -> size of the live blocks
        self.heap_free = {}            # taille -> blocs rendus par free, prets a resservir
        self.heap_scratch = {}         # name -> the viewer's work buffer, kept from one call to the next (see scratch)
        self.sp_top = self.STACK_BASE + self.STACK_SIZE - 0x100
        tp = self.TLS_BASE + 0x100
        uc.mem_write(tp + 0x28, (0x5a3c9e7d11223300).to_bytes(8, 'little'))  # stack canary (bionic)
        uc.reg_write(C.UC_ARM64_REG_TPIDR_EL0, tp)
        # lib
        self.stats = self.elf.relocate(self.LIB_BASE, self.stub_for)
        uc.mem_map(self.LIB_BASE, self.elf.size, UC_PROT_ALL)
        uc.mem_write(self.LIB_BASE, bytes(self.elf.img))
        # counters
        self.import_calls, self.unimpl = {}, {}
        self._arity = {}
        self.files, self.fopen_log = {}, []
        self.next_file = 0
        self.gl_calls, self.gl_count = [], {}
        self.gl_textures, self.gl_bound, self.gl_serial = {}, 0, 0          # textures registered by the host (id -> numpy array), texture bound by the engine, number of uploads received
        self.hook_error = None
        self.last_fault = None
        for lo, hi in self._hook_ranges(self._native_slots()): uc.hook_add(UC_HOOK_CODE, self._stub_hook, None, lo, hi)
        uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED,
                    self._mem_hook)
        self._install_fast_access()

    def _install_fast_access(self):
        """The general registers (X0 to X30, SP, PC) and the memory read through Unicorn's C library directly: the Python binding's generic path (register class lookup, ctypes value per
        register, two copies of every memory read) cost 5 to 10 us a call, and the engine calls the imports (strncmp, fopen...) by the thousand in some frames (a DQ VI town: 974 calls,
        150 ms every 65 frames). Same values and errors; anything else (other registers, aux arguments) goes through the binding. Nothing changes if the binding is not the expected one."""
        try:
            import ctypes
            from unicorn import UcError
            from unicorn.unicorn_py3 import unicorn as UM
            lib, uch = UM.uclib, self.uc._uch
            lib.uc_reg_read; lib.uc_reg_write; lib.uc_reg_read_batch; lib.uc_mem_read          # noqa: B018 (present)
        except Exception: return
        plain = frozenset(self.XREG) | {self.C.UC_ARM64_REG_SP, self.C.UC_ARM64_REG_PC}
        u64 = ctypes.c_uint64(); ref = ctypes.byref(u64)
        read0, write0 = self.uc.reg_read, self.uc.reg_write

        def reg_read(reg_id, aux=None):
            if aux is None and reg_id in plain:
                st = lib.uc_reg_read(uch, reg_id, ref)
                if st: raise UcError(st, reg_id)
                return u64.value
            return read0(reg_id, aux)

        def reg_write(reg_id, value):
            if reg_id in plain and isinstance(value, int):
                v = ctypes.c_uint64(value & MASK64); st = lib.uc_reg_write(uch, reg_id, ctypes.byref(v))
                if st: raise UcError(st, reg_id)
                return
            write0(reg_id, value)

        batches = {}

        def args(n):
            """X0 to X(n-1) in one call."""
            if n <= 0: return []
            b = batches.get(n)
            if b is None:
                vals = (ctypes.c_uint64 * n)()
                b = batches[n] = ((ctypes.c_int * n)(*self.XREG[:n]), vals, (ctypes.c_void_p * n)(*[ctypes.addressof(vals) + 8 * i for i in range(n)]))
            st = lib.uc_reg_read_batch(uch, b[0], b[2], n)
            if st: raise UcError(st)
            return list(b[1])

        def mem(a, n):
            buf = ctypes.create_string_buffer(n)
            st = lib.uc_mem_read(uch, a, buf, n)
            if st: raise UcError(st, a, n)
            return buf.raw

        self.uc.reg_read, self.uc.reg_write = reg_read, reg_write
        self.mem, self._args = mem, args

    @classmethod
    def native_code(cls):
        """The native page's code: memcpy at 0, the string routines at 0x80."""
        return cls.MEMCPY_NATIVE.ljust(cls.NATIVE_TARGETS['strncmp'], b'\0') + cls.STRINGS_NATIVE

    def _native_slots(self):
        """Writes a branch to its ARM64 routine in the slot of each import that has one. -> the slots' addresses (none with DQ_NO_NATIVE_IMPORTS)."""
        names = [n for n in self.NATIVE_IMPORTS if n in self.stub_idx] if self.native else []
        for n in names:
            a = self.stub_idx[n]; self.uc.mem_write(a, struct.pack('<I', 0x14000000 | (((self.native_base + self.NATIVE_TARGETS[n] - a) >> 2) & 0x3ffffff)))          # b <routine>
        return sorted(self.stub_idx[n] for n in names)

    def _hook_ranges(self, slots):
        """The stub region's addresses the Python hook watches, as inclusive (first, last) ranges: every slot but the return stub (slot 0), the slots in `slots` and the native page."""
        out = []; lo = self.STUB_BASE + 4
        for a in sorted(slots) + [self.native_base]:
            if a > lo: out.append((lo, a - 1))
            lo = a + 4
        return out

    # -- memory access
    def mem(self, a, n):
        return bytes(self.uc.mem_read(a, n))

    def mem_w(self, a, b):
        self.uc.mem_write(a, bytes(b))

    def read_cstr(self, a, limit=1 << 20):
        out = bytearray()
        while len(out) < limit:
            chunk = 64 - (a & 63)
            try:
                b = self.mem(a, chunk)
            except Exception:
                b = self.mem(a, 1)
            i = b.find(b'\0')
            if i >= 0:
                out += b[:i]
                return bytes(out)
            out += b
            a += len(b)
        return bytes(out)

    HEAP_ALERT, HEAP_CRITICAL = 200 << 20, 240 << 20            # the window warns the player at 200 MB (78%) then at 240 MB (94%) of the 256 MB heap: see Game._watch_heap

    def heap_used(self):
        """Heap bytes reached by the pointer (the highest ever allocated). Blocks returned by `free` are reused without raising it."""
        return self.heap_ptr - self.HEAP_BASE

    def heap_live(self):
        """Bytes actually alive: what the engine still holds, excluding the blocks it has returned."""
        return sum(self.heap_blocks.values())

    def malloc(self, n):
        """Allocates `n` bytes in the engine's heap, **reusing** a block of the same size already returned by `free`.

        Before, the pointer only moved forward and `free` returned nothing: measured on real battles, the engine in fact frees
        96 to 101% of what a battle allocates, and the memory actually alive peaks at 1.8 MB. The 256 MB heap was therefore filling up
        for nothing, in about 183 battles, and each savestate cost more and more (0.62 s at 200 MB versus 0.016 s at 2 MB).

        Reuse **by exact size**, with no splitting or merging: two blocks can never overlap. The engine's sizes
        are very regular (1024 and 512 bytes make up 96% of a battle's blocks), so reuse covers almost everything.
        The returned block is **zeroed**: with the old allocator, every allocation landed in fresh memory, hence zeroed, so the engine
        may have relied on it (`calloc` did nothing more than `malloc`). This keeps exactly what the engine used to see.
        """
        n = (max(int(n), 1) + 15) & ~15
        reusable = self.heap_free.get(n)
        if reusable:
            p = reusable.pop()
            self.mem_w(p, bytes(n))
        else:
            p = self.heap_ptr
            if p + n > self.HEAP_BASE + self.HEAP_SIZE:
                raise MemoryError('heap exhausted')
            self.heap_ptr += n
        self.heap_blocks[p] = n
        return p

    def free(self, p):
        """Returns a block to the heap: it goes back into the pool for its size. An unknown pointer (outside the heap, already returned, or allocated before
        the pool was set up) is ignored, as before: the engine sometimes frees what it did not allocate here."""
        n = self.heap_blocks.pop(p, None)
        if n is not None: self.heap_free.setdefault(n, []).append(p)

    def scratch(self, name_str, n):
        """Viewer work buffer **in the engine's heap**, kept from one call to the next (reading a text through `TextAPI::extractText`...).

        It is not part of any savestate: loading a state moves the heap pointer back, and the buffer can end up **above** it, that is, returned to the allocator.
        The engine then reallocates the same area and the buffer silently overwrites one of its own blocks (reproduced: buffer at 0x20244920, state loaded,
        the engine's next `malloc` -> 0x20244920).
        `heap_rewind` therefore forgets the buffers that are no longer alive, and a new one is taken here.
        """
        p = self.heap_scratch.get(name_str)
        if p is None: p = self.heap_scratch[name_str] = self.malloc(n)
        return p

    def heap_rewind(self, ptr):
        """Loading a savestate moves the heap pointer back: everything that lived above it no longer exists.
        Without this cleanup, the pool would hand out blocks that the engine is going to reallocate through the pointer, and two allocations would overlap;
        and a viewer work buffer left above would get reallocated from under it."""
        self.heap_ptr = ptr
        self.heap_blocks = {p: n for p, n in self.heap_blocks.items() if p + n <= ptr}
        self.heap_free = {n: [p for p in lst if p + n <= ptr] for n, lst in self.heap_free.items()}
        self.heap_scratch = {k: p for k, p in self.heap_scratch.items() if p in self.heap_blocks}

    def cstr(self, s):
        b = s.encode() if isinstance(s, str) else s
        p = self.malloc(len(b) + 1)
        self.mem_w(p, b + b'\0')
        return p

    # -- imports
    def stub_for(self, name, bind):
        if name in self.DATA_IMPORTS:
            p = self.data_ptr
            self.data_ptr += 16
            self.uc.mem_write(p, (0x5a3c9e7d11223300).to_bytes(8, 'little'))
            return p
        if name in self.stub_idx:
            return self.stub_idx[name]
        if bind == 2 and not hasattr(self, 'h_' + name):  # weak and unknown -> NULL
            return 0
        addr = self.STUB_BASE + 4 * len(self.stub_names)
        self.stub_names.append(name)
        self.stub_idx[name] = addr
        return addr

    def _stub_hook(self, uc, address, size, user):
        try:
            name = self.stub_names[(address - self.STUB_BASE) // 4]
            self.import_calls[name] = self.import_calls.get(name, 0) + 1
            n = self._arity.get(name)      # we only read the registers the handler needs (very frequent call)
            if n is None:
                g = getattr(self, 'h_' + name, None)
                try: n = (g.__func__.__code__.co_argcount - 1) if g is not None else 0
                except AttributeError: n = 8
                self._arity[name] = n
            regs = self._args(n) if self._args is not None else [uc.reg_read(self.XREG[i]) for i in range(n)]
            h = getattr(self, 'h_' + name, None)
            if h is None:
                self.unimpl[name] = self.unimpl.get(name, 0) + 1
                if self.unimpl[name] == 1:
                    self.log('  [unhandled import] %s called from %s' % (
                        name, self.where(uc.reg_read(self.XREG[30]))))
                ret = 0
            else:
                ret = h(*regs)
            if ret is not None:
                uc.reg_write(self.XREG[0], ret & MASK64)
        except Exception:
            self.hook_error = traceback.format_exc()
            uc.emu_stop()

    def _mem_hook(self, uc, access, address, size, value, user):
        self.last_fault = (access, address, size)
        return False

    def stack_arg(self, n):
        sp = self.uc.reg_read(self.C.UC_ARM64_REG_SP)
        return int.from_bytes(self.mem(sp + 8 * n, 8), 'little')

    # -- symbols
    def where(self, addr):
        if self.LIB_BASE <= addr < self.LIB_BASE + self.elf.size:
            off = addr - self.LIB_BASE
            i = bisect.bisect_right(self.elf.func_starts, off) - 1
            if i >= 0:
                s, sz, n = self.elf.funcs[i]
                return '%s+%#x' % (n, off - s)
            return 'lib+%#x' % off
        if self.native_base <= addr < self.STUB_BASE + self.STUB_SIZE:
            off = addr - self.native_base; name_str, start = max(((n, o) for n, o in self.NATIVE_TARGETS.items() if o <= off and n in ('memcpy', 'strncmp', 'strcmp', 'strlen')), key=lambda x: x[1])
            return 'native:%s+%#x' % (name_str, off - start)
        if self.STUB_BASE <= addr < self.STUB_BASE + self.STUB_SIZE:
            i = (addr - self.STUB_BASE) // 4
            return 'import:' + (self.stub_names[i] if i < len(self.stub_names) else '?')
        return '%#x' % addr

    # -- calls
    def export(self, name):
        """Address of an exported symbol, or None. A name that this library does not have is also looked up WITHOUT its first namespace
        (`_ZN9FieldData9drawBlockEv` finds `_ZN3fld9FieldData9drawBlockEv`, `_Z10ui_MsgLoopv` finds `_ZN4ardq10ui_MsgLoopEv`): the engines of
        Dragon Quest V and VI put most classes of Dragon Quest IV's engine into namespaces. Only a name found once is accepted."""
        off = self.elf.exports.get(name)
        if off is None: off = self.elf.aliases().get(name)
        return None if off is None else self.LIB_BASE + off

    def call(self, fn, *args, label='', timeout_s=90):
        from unicorn import UcError
        C, uc = self.C, self.uc
        for i, v in enumerate(args[:8]):
            uc.reg_write(self.XREG[i], int(v) & MASK64)
        uc.reg_write(C.UC_ARM64_REG_SP, self.sp_top)
        uc.reg_write(self.XREG[30], self.RET)
        self.hook_error, self.last_fault = None, None
        try:
            uc.emu_start(fn, self.RET, timeout=int(timeout_s * 1000000))
        except UcError as e:
            self.report_fault(e, label)
            return None
        if self.hook_error:
            self.log('!!! error in an emulated import during %s:\n%s' % (label, self.hook_error))
            return None
        pc = uc.reg_read(C.UC_ARM64_REG_PC)
        if pc != self.RET:
            self.log('!!! %s interrupted (max duration %ss?) PC=%s' % (label, timeout_s, self.where(pc)))
            return None
        return uc.reg_read(self.XREG[0])

    def report_fault(self, e, label):
        C, uc = self.C, self.uc
        pc = uc.reg_read(C.UC_ARM64_REG_PC)
        self.log('!!! EMULATION ERROR in %s: %s' % (label, e))
        self.log('    PC = %#x  (%s)' % (pc, self.where(pc)))
        try:
            self.log('    bytes at PC: %s' % self.mem(pc, 4).hex())
        except Exception:
            pass
        if self.last_fault:
            kind = {16: 'read', 17: 'write', 18: 'execution'}.get(self.last_fault[0], str(self.last_fault[0]))
            self.log('    invalid access: %s at address %#x (%d bytes)' % (kind, self.last_fault[1], self.last_fault[2]))
        self.log('    LR = %s   SP = %#x' % (self.where(uc.reg_read(self.XREG[30])), uc.reg_read(C.UC_ARM64_REG_SP)))
        self.log('    x0-x8: ' + ' '.join('%x' % uc.reg_read(self.XREG[i]) for i in range(9)))
        fp = uc.reg_read(self.XREG[29])
        self.log('    call stack (FP chain):')
        for _ in range(14):
            try:
                nxt = int.from_bytes(self.mem(fp, 8), 'little')
                ret = int.from_bytes(self.mem(fp + 8, 8), 'little')
            except Exception:
                break
            self.log('      %s' % self.where(ret))
            if nxt <= fp or nxt == 0:
                break
            fp = nxt

    def run_init(self):
        fns = self.elf.init_functions(self.LIB_BASE)
        ok = 0
        for f in fns:
            r = self.call(f, label='constructor %s' % self.where(f))
            if r is None:
                return False
            ok += 1
        self.log('constructors run: %d / %d' % (ok, len(fns)))
        return True

    # -- virtual files
    def norm(self, p):
        s = p.decode('latin-1').replace('\\', '/')
        for pre in (self.assets_dir, self.save_dir):
            if s.startswith(pre):
                s = s[len(pre):]
        parts = []
        for c in s.split('/'):
            if c in ('', '.'):
                continue
            if c == '..':
                if parts:
                    parts.pop()
                continue
            parts.append(c)
        return '/'.join(parts)

    def h_fopen(self, path, mode, *a):
        p, m = self.read_cstr(path), self.read_cstr(mode).decode()
        ps = p.decode('latin-1')
        if ps in self.real_files and 'w' not in m and 'a' not in m:
            fp = open(self.real_files[ps], 'rb')
            self.fopen_log.append((ps, True))
            self.next_file += 1
            h = self.FILE_BASE + 0x100 * self.next_file
            self.files[h] = {'fp': fp, 'name': ps}
            return h
        rel = self.norm(p)
        if 'w' in m or 'a' in m:
            data, w = bytearray(), True
        else:
            d = self.fs.open(rel) if self.fs else None
            if d is None:
                self.fopen_log.append((p.decode('latin-1'), False))
                return 0
            data, w = bytearray(d), False
        self.fopen_log.append((p.decode('latin-1'), True))
        self.next_file += 1
        h = self.FILE_BASE + 0x100 * self.next_file
        self.files[h] = {'d': data, 'pos': 0, 'w': w, 'name': rel}
        return h

    def h_fclose(self, h, *a):
        f = self.files.pop(h, None)
        if f and 'fp' in f:
            f['fp'].close()
        return 0

    def h_fread(self, ptr, size, n, h, *a):
        f = self.files.get(h)
        if not f or size == 0:
            return 0
        want = size * n
        if 'fp' in f:
            chunk = f['fp'].read(want)
            items = len(chunk) // size
            if len(chunk) != items * size:
                f['fp'].seek(items * size - len(chunk), 1)
                chunk = chunk[:items * size]
            if chunk:
                self.mem_w(ptr, chunk)
            return items
        chunk = bytes(f['d'][f['pos']:f['pos'] + want])
        items = len(chunk) // size
        chunk = chunk[:items * size]
        if chunk:
            self.mem_w(ptr, chunk)
        f['pos'] += len(chunk)
        return items

    def h_fwrite(self, ptr, size, n, h, *a):
        f = self.files.get(h)
        if not f:
            return 0
        f['d'][f['pos']:f['pos'] + size * n] = self.mem(ptr, size * n)
        f['pos'] += size * n
        return n

    def h_fseek(self, h, off, whence, *a):
        f = self.files.get(h)
        if not f:
            return MASK64
        if off >> 63:
            off -= 1 << 64
        if 'fp' in f:
            f['fp'].seek(off, whence & 3)
            return 0
        base = {0: 0, 1: f['pos'], 2: len(f['d'])}.get(whence & 3, 0)
        f['pos'] = max(0, base + off)
        return 0

    def h_ftell(self, h, *a):
        f = self.files.get(h)
        if f and 'fp' in f:
            return f['fp'].tell()
        return f['pos'] if f else MASK64

    # -- memory / strings
    def h_malloc(self, n, *a):
        return self.malloc(n)

    def h_calloc(self, n, m, *a):
        return self.malloc(n * m)          # (malloc always returns zeroed memory, reused block included: see malloc)

    def h_clock(self, *a):
        return int(time.process_time() * 1000000) & 0x7fffffffffffffff         # (CLOCKS_PER_SEC = 1000000 on Android)

    def h_strncpy(self, d, s, n, *a):
        b = self.read_cstr(s)[:n]
        self.mem_w(d, b + b'\0' * (n - len(b)))
        return d

    def h___cxa_pure_virtual(self, *a):
        raise RuntimeError('pure virtual function called by the engine')

    def h_free(self, p, *a):
        self.free(p); return 0

    def h__Znam(self, n, *a):
        return self.malloc(n)

    h__Znwm = h__Znam

    def h__ZdlPv(self, p, *a):
        return self.h_free(p)

    def h__ZdaPv(self, p, *a):
        self.free(p); return 0

    h__ZdlPv = h__ZdaPv

    def h_memcpy(self, d, s, n, *a):
        if n:
            self.mem_w(d, self.mem(s, n))
        return d

    h_memmove = h_memcpy

    def h___memcpy_chk(self, d, s, n, dl, *a):
        return self.h_memcpy(d, s, n)

    def h_memset(self, d, c, n, *a):
        if n:
            self.mem_w(d, bytes([c & 0xff]) * n)
        return d

    def h_strlen(self, s, *a):
        return len(self.read_cstr(s))

    def h___strlen_chk(self, s, n, *a):
        return len(self.read_cstr(s))

    def h_strcmp(self, a, b, *x):
        s, t = self.read_cstr(a), self.read_cstr(b)
        return (s > t) - (s < t)

    def h_strncmp(self, a, b, n, *x):
        s, t = self.read_cstr(a, n)[:n], self.read_cstr(b, n)[:n]
        return (s > t) - (s < t)

    def h_strstr(self, a, b, *x):
        i = self.read_cstr(a).find(self.read_cstr(b))
        return 0 if i < 0 else a + i

    def h_strcpy(self, d, s, *a):
        self.mem_w(d, self.read_cstr(s) + b'\0')
        return d

    def h___strcpy_chk(self, d, s, n, *a):
        return self.h_strcpy(d, s)

    def h_strcat(self, d, s, *a):
        e = d + len(self.read_cstr(d))
        self.mem_w(e, self.read_cstr(s) + b'\0')
        return d

    def h___strcat_chk(self, d, s, n, *a):
        return self.h_strcat(d, s)

    def h_atoi(self, s, *a):
        m = re.match(rb'\s*[-+]?\d+', self.read_cstr(s))
        return int(m.group()) if m else 0

    def h_vsnprintf(self, d, size, fmt, va, *a):
        out = format_c(self, self.read_cstr(fmt), VaList(self, va))
        if size:
            self.mem_w(d, out[:size - 1] + b'\0')
        return len(out)

    def h___vsprintf_chk(self, d, flag, slen, fmt, va, *a):
        out = format_c(self, self.read_cstr(fmt), VaList(self, va))
        self.mem_w(d, out + b'\0')
        return len(out)

    # -- C++ / system
    def h___cxa_atexit(self, *a):
        return 0

    def h___cxa_finalize(self, *a):
        return None

    def h___cxa_guard_acquire(self, g, *a):
        return 1 if self.mem(g, 1)[0] == 0 else 0

    def h___cxa_guard_release(self, g, *a):
        self.mem_w(g, b'\x01')
        return None

    def h___stack_chk_fail(self, *a):
        self.hook_error = 'stack_chk_fail : pile corrompue (appele depuis %s)' % self.where(
            self.uc.reg_read(self.XREG[30]))
        self.uc.emu_stop()

    def h___android_log_write(self, prio, tag, text, *a):
        t = self.read_cstr(text).decode('utf-8', 'replace')
        self.log('  [game log] %s: %s' % (self.read_cstr(tag).decode('utf-8', 'replace'), t[:300]))
        return 0

    # -- OpenGL: calls are counted; the textures the host has registered (gl_textures) receive the pixels the engine uploads (end credits)
    def h_glBindTexture(self, target, tex, *a):
        self.gl_count['glBindTexture'] = self.gl_count.get('glBindTexture', 0) + 1
        self.gl_bound = tex
        return None

    def h_glGetError(self, *a):
        return 0

    def h_glTexSubImage2D(self, target, level, xo, yo, w, h, fmt, typ, *a):
        pix = self.stack_arg(0)
        self.gl_count['glTexSubImage2D'] = self.gl_count.get('glTexSubImage2D', 0) + 1
        if len(self.gl_calls) < 40:
            self.gl_calls.append((target, level, xo, yo, w, h, fmt, typ, pix))
        img = self.gl_textures.get(self.gl_bound)
        if img is not None and level == 0 and fmt == 0x1908 and typ == 0x1401 and w > 0 and h > 0:          # GL_RGBA, GL_UNSIGNED_BYTE: the row band replaces the same rows of the registered texture (array of height x width x 4 bytes)
            if yo >= 0 and xo >= 0 and yo + h <= img.shape[0] and xo + w <= img.shape[1]:
                img[yo:yo + h, xo:xo + w] = np.frombuffer(self.mem(pix, w * h * 4), np.uint8).reshape(h, w, 4)
                self.gl_serial += 1
        return None
