"""The addresses the layout reader needs in the running game's libil2cpp.so, found by name instead of being written down for one game.

- C# methods: by their name (and a part of their signature, for overloads) in script.json (Il2CppDumper);
- the IL2CPP runtime helpers that the generated code calls (metadata initialization, object and array creation, exceptions): the most called function of the
  library is the metadata initialization; the others sit at fixed distances from it (the same Unity version builds the same block of helpers: checked on
  Dragon Quest IV and V);
- the delegate call `m_frame.Change(n)` of MenuMessage.SetCanvasMesh(short): its first `blr`;
- the library's segments: the start of the data (code called there = a virtual call on a dummy object) and the writable area of the method infos."""
import collections, struct
import disasm as d

_by_name = collections.defaultdict(list)
for _m in d.D['ScriptMethod']: _by_name[_m['Name']].append((_m['Address'], _m.get('Signature', '')))


def method(name, sig=None):
    """Address of the C# method `name` (script.json form: Class$$Method); `sig`: a part of its signature that tells the overloads apart."""
    found = [a for a, s in _by_name.get(name, ()) if sig is None or sig in s]
    if len(found) != 1: raise SystemExit('libil2cpp.so: method %s%s not found once (%d found)' % (name, ' (%s)' % sig if sig else '', len(found)))
    return found[0]


def _segments():
    so = d.so; e_phoff = struct.unpack_from('<Q', so, 0x20)[0]; e_phentsize, e_phnum = struct.unpack_from('<HH', so, 0x36)
    out = []
    for i in range(e_phnum):
        t, fl, off, va, pa, fs, ms, al = struct.unpack_from('<IIQQQQQQ', so, e_phoff + i * e_phentsize)
        if t == 1: out.append((va, va + ms, fl, off, fs))
    return out


SEGMENTS = _segments()
CODE_END = max(end for va, end, fl, off, fs in SEGMENTS if fl & 1)              # executable segment: the code; from its end on, the data
METHOD_INFOS = max((va, end) for va, end, fl, off, fs in SEGMENTS if fl & 2)     # last writable segment (bss): the method infos (MethodInfo) live there


def _most_called():
    """The two functions of the library called by the most `bl`."""
    cnt = collections.Counter()
    so = d.so
    for va, end, fl, off, fs in SEGMENTS:
        if not fl & 1: continue
        n = fs // 4; ws = struct.unpack_from('<%dI' % n, so, off)
        for k, w in enumerate(ws):
            if (w & 0xfc000000) == 0x94000000:                                            # bl
                o = w & 0x3ffffff
                if o & (1 << 25): o -= 1 << 26
                cnt[va + 4 * k + 4 * o] += 1
    return [a for a, n in cnt.most_common(2)]


INIT, _SECOND = _most_called()                # il2cpp_codegen_initialize_runtime_metadata; another runtime helper
HELPERS = dict(init=INIT, arrnew=INIT + 0x74, arrnew2=INIT + 0x7c, objnew=INIT + 0x218, throw=INIT + 0x220, throw2=INIT + 0x228)
HELPER_BLOCK = (INIT - 0x18c, INIT - 0x18c + 0x1000)          # the block of runtime helpers: calls into it are neutralized
RGCTX_INIT = _SECOND + 0x5c                   # initialization of the runtime context of a generic method (rgctx)


def first_blr(fn):
    """Address of the first `blr` (indirect call) of the function at `fn`."""
    for k in range(0, 0x1000, 4):
        w, = struct.unpack('<I', d.rd(fn + k, 4))
        if (w & 0xfffffc1f) == 0xd63f0000: return fn + k
    raise SystemExit('libil2cpp.so: no indirect call in the function at %#x' % fn)


_FIELDS = None


def field(cls, name):
    """Offset of the field `name` of the class `cls` in dump.cs (instance or static); None if the class has no such field."""
    global _FIELDS
    if _FIELDS is None:
        import re
        _FIELDS, cur = {}, None
        for l in open(d.os.path.join(d.BASE, 'dump.cs'), encoding='utf-8', errors='replace'):
            mm = re.match(r'^(?:public |private |internal |protected )?(?:static |sealed |abstract |readonly )*(?:class|struct|enum|interface) (\S+)', l)
            if mm: cur = mm.group(1); continue
            m2 = re.match(r'\t[^(]*?(\S+); // 0x([0-9A-F]+)$', l.rstrip())
            if m2 and cur: _FIELDS.setdefault((cur, m2.group(1)), int(m2.group(2), 16))
    return _FIELDS.get((cls, name))


BUILD_XYZ = method('MenuParts$$Build', 'float x')                       # Build(indent, screenIndent, x, y, z, parent)
BUILD_POS = method('MenuParts$$Build', 'Vector3_o pos')                 # Build(indent, Vector3 pos, parent)
IBASE_CHANGE_INT = method('MenuParts.IBase$$Change', 'int32_t i')
SET_TEXT_COLOR = method('MenuParts$$SetTextColor', 'MenuParts_o* __this')
SET_CANVAS_MESH = method('MenuMessage$$SetCanvasMesh', 'int16_t no')
SET_CANVAS_MESH_FRAME_CALL = first_blr(SET_CANVAS_MESH)                  # m_frame.Change(n) (delegate)
MESSAGE_CTOR = method('MenuMessage$$.ctor')
LANG_APPLY = method('MenuParts.LangParam$$Apply')
IBUTTON_CCTOR = method('MenuParts.IButton$$.cctor')
EINDENT_INIT = method('eIndent$$Init')
ADD_PARTS = method('MenuPortItem$$AddParts')
TABLE_ITEM_PARAM = method('MenuPortItem$$SetTableForItemParam', 'int32_t partsNo')
TABLE_ITEM_PARAM_IBASE = method('MenuPortItem$$SetTableForItemParam', 'IBase_o* ibase')
TABLE_TEXT_COLOR = method('MenuPortItem$$SetTableForItemParamTextColorChanger')
TABLE_CODE_PARTS = method('MenuPortItem$$SetTableForCode', 'int16_t partsNo')
TABLE_CODE_FUNC = method('MenuPortItem$$SetTableForCode', 'FUNC_SetCode')
