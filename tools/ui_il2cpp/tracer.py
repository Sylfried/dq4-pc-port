"""Tracer: runs a libil2cpp.so function (ARM64) under Unicorn, replacing its calls
by stubs that log (name, arguments typed according to dump.cs) and return dummy objects."""
import sys, struct, re, json, bisect, os
from unicorn import *
from unicorn.arm64_const import *
import disasm as d
import reloc as rl
import addresses as A

so = d.so
PAGE = 0x1000
HEAP, STACK = 0x40000000, 0x7f000000
RET_INS = bytes.fromhex('c0035fd6')

def island(t, fn, end):
    """Is `t` a branch island of the function [fn, end): a few instructions placed elsewhere by the linker, ending with a `b` back into the function
    (DQ VI: `ldr x20, [x20, #imm] ; b <back>`)? It is part of the function's own flow: it is neither stubbed nor followed as a call."""
    raw = d.rd(t, 16)
    if not raw: return False
    for k in range(4):
        w, = struct.unpack_from('<I', raw, 4 * k)
        if (w & 0xfc000000) == 0x14000000:                                          # b
            o = w & 0x3ffffff
            if o & (1 << 25): o -= 1 << 26
            return fn <= t + 4 * k + 4 * o < end
        if (w & 0xfc000000) == 0x94000000 or w == 0xd65f03c0 or (w & 0xfffffc1f) in (0xd63f0000, 0xd61f0000): return False      # bl, ret, blr, br: a function
    return False


# ---------------------------------------------------------------- signatures (dump.cs)
SIG = {}      # rva -> dict
def _split(p):
    out, dep, cur = [], 0, ''
    for ch in p:
        if ch in '<[(': dep += 1
        if ch in '>])': dep -= 1
        if ch == ',' and dep == 0: out.append(cur.strip()); cur = ''
        else: cur += ch
    if cur.strip(): out.append(cur.strip())
    return out
def load_sigs(path=None):
    path = path or os.path.join(d.BASE, 'dump.cs')
    cls = None; rva = None
    for l in open(path, encoding='utf-8', errors='replace'):
        mm = re.match(r'^(?:public |private |internal |protected )?(?:static |sealed |abstract |readonly )*(?:class|struct|enum|interface) (\S+)', l)
        if mm: cls = mm.group(1); continue
        mm = re.match(r'\t// RVA: 0x([0-9A-F]+) Offset', l)
        if mm: rva = int(mm.group(1), 16); continue
        if rva is not None and l.startswith('\t') and not l.strip().startswith('//') and not l.strip().startswith('['):
            m2 = re.match(r'\t(.*?)\b([\w.<>$]+)\((.*)\) \{ \}', l)
            if m2:
                head = m2.group(1).split(); name = m2.group(2); params = _split(m2.group(3))
                static = 'static' in head
                ret = head[-1] if head else ''
                ps = []
                for p in params:
                    p = re.sub(r'\s*=\s*[^,]*$', '', p)
                    toks = p.split()
                    ps.append((' '.join(toks[:-1]), toks[-1]) if len(toks) > 1 else (p, ''))
                SIG[rva] = dict(cls=cls, name=name, static=static, ret=ret, params=ps)
            rva = None
load_sigs()
KIND = {}      # type name -> 'class' | 'struct' | 'enum'
STAT = {}      # class -> [(type, offset)]
INST = {}      # class -> [(type, offset)] instance fields
def load_fields(path=None):
    path = path or os.path.join(d.BASE, 'dump.cs')
    cls = None
    for l in open(path, encoding='utf-8', errors='replace'):
        mm = re.match(r'^(?:public |private |internal |protected )?(?:static |sealed |abstract |readonly )*(class|struct|enum|interface) (\S+)', l)
        if mm: cls = mm.group(2); KIND[cls] = mm.group(1); continue
        mm = re.match(r'\t(?:public |private |internal |protected )?(?:\[[^\]]*\] )?static (?:readonly )?(\S+) (\w+); // 0x([0-9A-F]+)', l)
        if mm and cls: STAT.setdefault(cls, []).append((mm.group(1), int(mm.group(3), 16)))
        else:
            m3 = re.match(r'\t(?:public |private |internal |protected )(?:readonly )?([\w.<>\[\],?]+) (\w+); // 0x([0-9A-F]+)$', l.rstrip())
            if m3 and cls and 'const' not in l: INST.setdefault(cls, []).append((m3.group(1), int(m3.group(3), 16)))
load_fields()

FLT = {'float', 'single'}
HFA = {'Vector2': 2, 'Vector3': 3, 'Vector4': 4, 'Color': 4, 'Rect': 4, 'Quaternion': 4, 'Color32': 0}
INTW = {'bool': 1, 'byte': 8, 'sbyte': -8, 'short': -16, 'ushort': 16, 'int': -32, 'uint': 32, 'long': -64, 'ulong': 64, 'char': 16}

PRIM = set(INTW) | FLT | set(HFA) | {'double', 'IntPtr', 'UIntPtr', 'Matrix4x4', 'Bounds', 'Ray'}
class Abort(Exception): pass
_SA = sorted(set(d.names) | set(SIG))
def fend(fn):
    import bisect
    i = bisect.bisect_right(_SA, fn)
    return _SA[i] if i < len(_SA) else fn + 0x4000


class Tr:
    def __init__(self):
        self.uc = uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)
        top = 0
        for v, o, s in d.segs: top = max(top, v + s)
        segs_end = 0
        e_phoff = struct.unpack_from('<Q', so, 0x20)[0]; e_phentsize, e_phnum = struct.unpack_from('<HH', so, 0x36)
        for i in range(e_phnum):
            t, fl, off, va, pa, fs, ms, al = struct.unpack_from('<IIQQQQQQ', so, e_phoff + i * e_phentsize)
            if t == 1: segs_end = max(segs_end, va + ms)
        size = (segs_end + PAGE) & ~(PAGE - 1)
        uc.mem_map(0, size, UC_PROT_ALL)
        for i in range(e_phnum):
            t, fl, off, va, pa, fs, ms, al = struct.unpack_from('<IIQQQQQQ', so, e_phoff + i * e_phentsize)
            if t == 1: uc.mem_write(va, so[off:off + fs])
        for off, add in rl.R.items(): uc.mem_write(off, struct.pack('<Q', add))
        uc.mem_map(HEAP, 0x4000000, UC_PROT_ALL)
        uc.mem_map(STACK, 0x100000, UC_PROT_ALL)
        self.heap = HEAP + 0x1000
        uc.mem_write(0, RET_INS)       # calls through null pointers (unresolved virtuals): immediate return
        def nullcall(uc_, a, s, ud):
            self.event('nullcall', lr=uc.reg_read(UC_ARM64_REG_X30), x0=self.fmt(uc.reg_read(UC_ARM64_REG_X0)))
        uc.hook_add(UC_HOOK_CODE, nullcall, None, 0, 0)
        def dataexec(uc_, a, s_, ud):
            lr = uc.reg_read(UC_ARM64_REG_X30)
            self.event('dataexec', pc=a, lr=lr)
            uc.reg_write(UC_ARM64_REG_X0, 0)
            uc.reg_write(UC_ARM64_REG_PC, lr)
        self.data_lo = A.CODE_END
        uc.hook_add(UC_HOOK_CODE, dataexec, None, A.CODE_END, segs_end)
        self.uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED, self._unm)
        self.klass = {}        # T -> dummy class
        self.kname = {}        # dummy class -> name
        self.obj = {}          # object address -> (id, description)
        self.log = []
        self.patched = {}
        self.hooks = []
        self.strs = {}
        self.statics_done = set()
        self.verbose = False

    # ---- memory
    def u(self, a, n, sg=False):
        return int.from_bytes(self.uc.mem_read(a, n), 'little', signed=sg)
    def w(self, a, v, n=8):
        self.uc.mem_write(a, (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little'))
    def alloc(self, n):
        a = self.heap; self.heap += (n + 15) & ~15; return a
    def _unm(self, uc, access, addr, size, value, ud):
        pc = uc.reg_read(UC_ARM64_REG_PC)
        if access == UC_MEM_FETCH_UNMAPPED:
            # virtual call / delegate on a null address: we log and return
            self.event('virtcall', pc=pc, target=addr, lr=uc.reg_read(UC_ARM64_REG_X30))
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30)); uc.reg_write(UC_ARM64_REG_X0, 0)
            return True
        self.event('memfault', pc=pc, access=access, addr=addr)
        raise Abort('mem %d @%x pc=%x' % (access, addr, pc))

    def event(self, kind, **kw):
        kw['kind'] = kind; self.log.append(kw)

    # ---- objects / dummy classes
    def new_klass(self, T):
        k = self.alloc(0x400)
        st = self.alloc(0x800)
        self.w(k + 0xb8, st)
        self.w(k + 0xe0, 0xffffffff, 4); self.w(k + 0xd8, 0xffffffff, 4)
        self.w(k + 0x28, 0xffffffff, 4)
        hier = self.alloc(16); self.w(hier, k); self.w(k + 0xc8, hier); self.w(k + 0x130, 1, 1)          # Il2CppClass.typeHierarchy / typeHierarchyDepth: the class is its own only ancestor (a cast to that same class succeeds, to another one fails)
        self.klass[T] = k; self.kname[k] = rl.M.get(T) or ('T%x' % T)
        cn = self.kname[k].replace('_TypeInfo', '')
        for tp, off in STAT.get(cn, []):
            if tp in PRIM or KIND.get(tp) in ('struct', 'enum') or tp.endswith('[]') or tp.endswith(']') or tp.startswith('Method$'):
                continue
            self.w(st + off, self.new_obj(0))
        return k
    def dummy(self):
        o = self.alloc(0x100); self.obj[o] = len(self.obj) + 1; return o
    def new_obj(self, klass, desc=None, size=0x200, fill=True):
        o = self.alloc(size); self.w(o, klass)
        self.obj[o] = len(self.obj) + 1
        if fill and klass in self.kname:
            cn = self.kname[klass].replace('_TypeInfo', '')
            for tp, off in INST.get(cn, []):
                if tp in PRIM or KIND.get(tp) in ('struct', 'enum') or tp.startswith('Method$') or off >= size - 8: continue
                self.w(o + off, self.dummy())
        return o
    def oname(self, v):
        if v in self.obj:
            k = self.u(v, 8)
            return '@%d:%s' % (self.obj[v], (self.kname.get(k, '?').replace('_TypeInfo', '')))
        return None

    # ---- intercepted calls
    def intercept(self, addr, handler):
        if addr in self.patched: return
        self.patched[addr] = bytes(self.uc.mem_read(addr, 4))
        self.uc.mem_write(addr, RET_INS)
        self.hooks.append(self.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, ud: handler(a), None, addr, addr))
    def restore(self):
        for a, b in self.patched.items():
            if b is not None: self.uc.mem_write(a, b)
        for h in self.hooks: self.uc.hook_del(h)
        self.patched = {}; self.hooks = []

    def regs(self):
        uc = self.uc
        X = [uc.reg_read(UC_ARM64_REG_X0 + i) for i in range(8)]
        F = []
        for i in range(8):
            v = uc.reg_read(UC_ARM64_REG_S0 + i)
            F.append(struct.unpack('<f', struct.pack('<I', v & 0xffffffff))[0])
        return X, F

    def fmt(self, v):
        n = self.oname(v)
        if n: return n
        if v in self.kname: return 'K:' + self.kname[v]
        if v in rl.S or v in self.strs: return repr(self.strs.get(v) or rl.S.get(v))
        return v

    def bind(self, rva, X, F):
        sg = SIG.get(rva)
        if not sg: return None
        out = []; ni = 0; nf = 0
        if not sg['static']:
            out.append(('this', self.fmt(X[0]))); ni = 1
        for t, nm in sg['params']:
            tt = t.replace('ref ', '').replace('out ', '').replace('in ', '')
            if t.startswith(('ref ', 'out ')):
                out.append((nm, 'ref %x' % X[ni] if ni < 8 else None)); ni += 1; continue
            if tt in FLT: out.append((nm, round(F[nf], 4) if nf < 8 else None)); nf += 1
            elif tt in HFA and HFA[tt]:
                k = HFA[tt]; out.append((nm, tuple(round(x, 4) for x in F[nf:nf + k]) if nf + k <= 8 else None)); nf += k
            elif tt in INTW:
                bits = INTW[tt]; v = X[ni] if ni < 8 else 0
                if tt == 'bool': v &= 1
                elif bits < 0: b = -bits; v &= (1 << b) - 1; v = v - (1 << b) if v >> (b - 1) else v
                else: v &= (1 << bits) - 1
                out.append((nm, v)); ni += 1
            else:
                out.append((nm, self.fmt(X[ni]) if ni < 8 else None)); ni += 1
        return out

    def stub_for(self, addr):
        rva = addr
        sg = SIG.get(rva)
        nm = (sg['cls'] + '.' + sg['name']) if sg else d.names.get(addr, 'sub_%x' % addr)
        def h(a, rva=rva, nm=nm, sg=sg):
            X, F = self.regs()
            b = self.bind(rva, X, F) if sg else None
            ret = 0
            if sg:
                r = sg['ret']
                if r in ('void',): ret = 0
                elif r in INTW or r in FLT or r in HFA or r in ('double',):
                    ret = 0
                    for i in range(4): self.uc.reg_write(UC_ARM64_REG_S0 + i, 0)
                else:
                    k = self.klass_for_type(r) or 0
                    ret = self.new_obj(k)
            else:
                ret = X[0]
            self.uc.reg_write(UC_ARM64_REG_X0, ret)
            self.event('call', name=nm, args=b if b is not None else [self.fmt(x) for x in X[:6]], floats=[round(f, 4) for f in F[:4]] if not b else None, ret=self.oname(ret) if ret in self.obj else ret, lr=self.uc.reg_read(UC_ARM64_REG_X30))
        return h

    def klass_named(self, short):
        """The dummy class of the Unity / game type `short` ("BoxCollider"), found by its TypeInfo whatever its namespace ("UnityEngine.BoxCollider_TypeInfo"), created if needed; None if unknown."""
        T = next((t for t, n in rl.M.items() if n == short + '_TypeInfo' or n.endswith('.' + short + '_TypeInfo')), None)
        if T is None: return None
        k = self.klass.get(T) or self.new_klass(T)
        if self.u(T, 8) == 0: self.w(T, k)
        return k

    def klass_for_type(self, tname):
        key = tname.split('<')[0]
        for T, k in self.klass.items():
            if self.kname[k].replace('_TypeInfo', '') == tname: return k
        return None

    # ---- IL2CPP helpers
    def helpers(self):
        def init(a):
            X, _ = self.regs(); T = X[0]
            if T in rl.S:
                if self.u(T, 8) == 0 or self.u(T, 8) == T:
                    o = self.dummy(); self.strs[o] = rl.S[T]; self.w(T, o)
                return
            if T not in self.klass or self.u(T, 8) == 0:
                k = self.klass.get(T) or self.new_klass(T); self.w(T, k)
            self.event('init', cls=rl.M.get(T))
        def objnew(a):
            X, _ = self.regs(); k = X[0]
            if k not in self.kname:      # we received the value loaded from the variable
                pass
            o = self.new_obj(k)
            self.uc.reg_write(UC_ARM64_REG_X0, o)
            self.event('new', cls=self.kname.get(k), obj=self.obj[o])
        def arrnew(a):
            X, _ = self.regs(); k, n = X[0], X[1] & 0xffffffff
            o = self.alloc(0x20 + 8 * n + 16); self.w(o, k); self.w(o + 0x18, n, 8)
            self.obj[o] = len(self.obj) + 1
            self.uc.reg_write(UC_ARM64_REG_X0, o)
            self.event('newarr', cls=self.kname.get(k), n=n, obj=self.obj[o])
        def arrnew2(a):
            X, _ = self.regs(); k = X[0]; dims = [self.u(X[1] + 8 * i, 8) for i in range(2)]
            tot = max(1, dims[0] * dims[1])
            o = self.alloc(0x20 + 16 * tot + 64); self.w(o, k)
            bd = self.alloc(32)
            for i, dd in enumerate(dims): self.w(bd + 16 * i, dd)
            self.w(o + 0x10, bd); self.w(o + 0x18, tot)
            self.obj[o] = len(self.obj) + 1
            self.uc.reg_write(UC_ARM64_REG_X0, o)
            self.event('newarr2', cls=self.kname.get(k), dims=dims, obj=self.obj[o])
        def throw(a):
            self.event('throw', lr=self.uc.reg_read(UC_ARM64_REG_X30), addr=a)
            raise Abort('throw @%x' % a)
        def ident(a): pass
        H_ = A.HELPERS
        self.intercept(H_['init'], init)
        self.intercept(H_['objnew'], objnew)
        self.intercept(H_['arrnew'], arrnew); self.intercept(H_['arrnew2'], arrnew2)
        self.intercept(H_['throw'], throw); self.intercept(H_['throw2'], throw)

    REAL = re.compile(r'^(MenuPortItemTable\.Sub_|eIndent\.|MenuPortItemTable\.<>c__DisplayClass\d+_\d+\.<)')
    def observe(self, addr, nm):
        if addr in self.patched: return
        def h(a, nm=nm):
            X, F = self.regs(); sg = SIG.get(addr)
            fx = getattr(self, 'fixups', {}).get(nm)
            if fx: fx(X, F)
            self.event('enter', name=nm, args=self.bind(addr, X, F) if sg else [self.fmt(x) for x in X[:6]], floats=None if sg else [round(f, 4) for f in F[:4]])
        self.patched[addr] = None
        self.hooks.append(self.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, ud: h(a), None, addr, addr))
    def collect(self, fn, seen):
        if fn in seen: return
        seen.add(fn)
        end = fend(fn)
        for ins in d.md.disasm(d.rd(fn, end - fn), fn):
            if ins.mnemonic in ('bl', 'b') and ins.operands[0].type == 2:
                t = ins.operands[0].imm
                if fn <= t < end or t in self.patched or island(t, fn, end): continue
                sg = SIG.get(t); nm = (sg['cls'] + '.' + sg['name']) if sg else d.names.get(t, 'sub_%x' % t)
                if A.HELPER_BLOCK[0] <= t <= A.HELPER_BLOCK[1]:
                    self.intercept(t, lambda a: None); continue
                if self.REAL.match(nm) and 'ctor' not in nm:
                    self.observe(t, nm); self.collect(t, seen)
                else: self.intercept(t, self.stub_for(t))

    def run(self, fn, args=(), fargs=(), maxins=400000):
        """Runs fn ; all the direct `bl`/`b` to other functions are intercepted (logged)."""
        self.log = []
        self.helpers()
        self.collect(fn, set())
        uc = self.uc
        sp = STACK + 0xf0000
        uc.reg_write(UC_ARM64_REG_SP, sp)
        uc.reg_write(UC_ARM64_REG_X30, 0x1000)       # dummy return
        for i, v in enumerate(args): uc.reg_write(UC_ARM64_REG_X0 + i, v)
        for i, v in enumerate(fargs): uc.reg_write(UC_ARM64_REG_S0 + i, struct.unpack('<I', struct.pack('<f', v))[0])
        # return address: a dummy 'ret' instruction
        err = None
        try:
            uc.emu_start(fn, 0x1000, count=maxins)
        except (UcError, Abort) as e:
            err = str(e)
        self.restore()
        return err

if __name__ == '__main__':
    T = Tr()
    fn = int(sys.argv[1], 16)
    args = [int(x, 0) for x in sys.argv[2:]]
    err = T.run(fn, args)
    for e in T.log: print(e)
    print('ERR', err)
