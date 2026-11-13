import struct, sys
def chunks(raw):
    """FLD: sequence of 'TAG4' chunks + size(4, total size of the chunk); FHDR has its own size."""
    out = []; p = 0
    while p + 8 <= len(raw):
        tag = raw[p:p+4]
        if not tag.isalpha(): break
        sz = struct.unpack_from('<I', raw, p + 4)[0]
        if sz < 8 or p + sz > len(raw): out.append((tag.decode(), p, len(raw) - p)); break
        out.append((tag.decode(), p, sz)); p = (p + sz + 15) & ~15
    return out
def map_objs(raw):
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    p, s = cs['FMAP']
    nobj, mobj = struct.unpack_from('<2I', raw, p + 8)
    objs = []
    for i in range(max(nobj, mobj)):                                # FLD_MAP.nobj = map objects; FLD_MAP.mobj >= nobj: with the event objects that follow (FEAN, 21 maps), hidden at start (FldObject.Load)
        o = p + 0x20 + 0x50 * i
        pos = struct.unpack_from('<3f', raw, o); oid = struct.unpack_from('<i', raw, o + 12)[0]
        rot = struct.unpack_from('<3f', raw, o + 16); model, com = struct.unpack_from('<hH', raw, o + 28)
        scl = struct.unpack_from('<3f', raw, o + 32); uid = struct.unpack_from('<i', raw, o + 44)[0]
        flag32, prio = struct.unpack_from('<ii', raw, o + 48); flag = flag32 & 0xffff; rest = raw[o + 52:o + 80]        # FldObject.Load: int32 flags at +48 (billboards: 0x4, 0x20; 0x40000 = common), int32 PRIORITY at +52 (render queue 3000 + priority, FldObject.set_priority; before, `prio` was the high half of the flags)
        sequence_object, pmv = struct.unpack_from('<hh', raw, o + 64); canim = struct.unpack_from('<h', raw, o + 74)[0]       # FLD_MAP_OBJ: seq_obj_id (FSEQ entry: mesh sequence played continuously), pmv_id (FPMV movement played continuously), -1 = none; canim_id (number of the common animation table of FCAN, -1 = none)
        objs.append(dict(i=i, pos=pos, id=oid, rot=rot, model=model, com=com, scl=scl, uid=uid, flag=flag, prio=prio, sequence_object=sequence_object, pmv=pmv, canim=canim, rest=rest.hex()))
    return nobj, objs
def fean(raw):
    """FEAN: event animations (FldObject.FLD_EVENT_ANIM_DATA, read by FldObject.Load: count, an unused float, then pairs of int16). -> list of (start, end); the animation number is the index + 1.
    Animation `no` shows the map objects start .. end - 1 (the event objects, indices >= nobj: their ranges cover exactly nobj .. mobj - 1 in the 21 maps that have any) and hides the base objects with the same `uid`
    (FldObject.SetEventAnimation, packet 6)."""
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    if 'FEAN' not in cs: return []
    p = cs['FEAN'][0]; n = min(struct.unpack_from('<i', raw, p + 8)[0], max(0, (len(raw) - p - 16) // 4))      # (the size written in the chunk is sometimes too small - ddb5b - : the game reads n from the count, not from the size)
    return [struct.unpack_from('<hh', raw, p + 16 + 4 * i) for i in range(n)]
def canim(raw):
    """FCAN: common animation tables. -> list of tables; a table = list of entries (model, seq_obj_id, pmv_id) whose index + 1 is the animation number
    (FldObject.SetCommonAnimation: model to display, mesh sequence (FSEQ), movement (FPMV))."""
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    if 'FCAN' not in cs: return []
    p, s = cs['FCAN']; n = struct.unpack_from('<i', raw, p + 8)[0]; q = p + 12
    pairs = [struct.unpack_from('<ii', raw, q + 8 * i) for i in range(n)]; q += 8 * n; out = []
    for node, _ in pairs:
        out.append([struct.unpack_from('<3h', raw, q + 8 * i) for i in range(node)]); q += 8 * node
    return out

def _motion_header(raw, o):
    flag, nkey, loops, delay, loop_delay, ksz = struct.unpack_from('<6h', raw, o); end = struct.unpack_from('<i', raw, o + 16)[0]
    return dict(flag=flag, nkey=nkey, repeat=loops, delay=delay, loop_delay=loop_delay, end=end)

def pmv(raw):
    """FPMV: object movements (position, rotation, scale as keys, frame = 1/60 s). -> list of {'end', 'repeat', 'keys': [(frame, pos, rot, scl)]}"""
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    if 'FPMV' not in cs: return []
    p, s = cs['FPMV']; n = struct.unpack_from('<i', raw, p + 8)[0]; out = []
    for o in struct.unpack_from('<%di' % n, raw, p + 12):
        m = _motion_header(raw, o); keys = []
        for k in range(m['nkey']):
            v = struct.unpack_from('<i9f', raw, o + 0x20 + 40 * k); keys.append((v[0], (v[1], -v[2], v[3]), v[4:7], v[7:10]))      # key positions: readPosition negates y as for objects
        m['keys'] = keys; out.append(m)
    return out

def sra(raw):
    """FSRA: animated material colors (FldObject.ReadMotion, kind 5; the game only reads the diffuse color). Each entry: material name (32 bytes), same header as FPMV, then 68-byte keys
    (frame, ambient, diffuse, specular, emissive: 4 RGBA floats each). -> list of {'name', 'event', 'end', 'repeat', 'delay', 'loop_delay', 'nkey', 'flag', 'keys': [(frame, (r, v, b, a))]} ;
    `event`: number of the event animation that starts it (0: always running)."""
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    if 'FSRA' not in cs: return []
    p, s = cs['FSRA']; n = struct.unpack_from('<i', raw, p + 8)[0]; out = []
    for o in struct.unpack_from('<%di' % n, raw, p + 12):
        m = _motion_header(raw, o + 0x20); m['name'] = raw[o:o + 0x20].split(b'\0', 1)[0].decode('ascii', 'replace'); m['event'] = struct.unpack_from('<i', raw, o + 0x34)[0]
        m['keys'] = [(v[0], v[5:9]) for v in (struct.unpack_from('<i16f', raw, o + 0x40 + 68 * k) for k in range(m['nkey']))]
        out.append(m)
    return out

def sequences(raw):
    """FSQD: mesh sequences (key = frame at 1/60 s, value = frame mesh number); FSEQ: sequence objects (FldObject.FLD_SEQ_OBJ, 20 bytes).
    -> (list of FSEQ entries [(obj, seq, group, start delay, delay between two loops, number of loops, _, original number of loops)], list of sequences {'end', 'repeat', 'keys': [(frame, value)]}).
    Number of loops: -1 = endless, N = N loops then stop on the last key, 0 = never started by itself (only by a common animation); delays in 1/60 s."""
    cs = {t: (p, s) for t, p, s in chunks(raw)}; ent = []; sequences = []
    if 'FSEQ' in cs:
        p, s = cs['FSEQ']; n = struct.unpack_from('<i', raw, p + 8)[0]
        ent = [struct.unpack_from('<8h', raw, p + 12 + 20 * i) for i in range(n)]
    for t, p, s in chunks(raw):
        if t != 'FSQD': continue
        m = _motion_header(raw, p + 16); m['keys'] = [struct.unpack_from('<2i', raw, p + 48 + 8 * k) for k in range(m['nkey'])]; sequences.append(m)
    return ent, sequences

def plp(raw):
    """FPLP: animated palettes of objects (FldObject.FLD_PLP_DATA). -> list of {'name', 'pam', 'event', 'obj'}: the map object `obj` (FMAP) sees its textures whose name contains `name_str`
    replaced, frame after frame, by those of the palette animation `pam` (FPAM); `event` >= 1: only during the event animation with that number (otherwise frame 0).
    24-byte record: name (16, 0-terminated), animation number (1), event number (1), object (2), 4 unused bytes."""
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    if 'FPLP' not in cs: return []
    p, s = cs['FPLP']; n = struct.unpack_from('<i', raw, p + 8)[0]; out = []
    for k in range(n):
        o = p + 12 + 24 * k
        name_str = raw[o:o + 16].split(b'\0')[0].decode('ascii', 'replace'); pam, ev, obj = struct.unpack_from('<BBh', raw, o + 16)
        out.append(dict(name=name_str, pam=pam, event=ev, obj=obj))
    return out

def pam(raw):
    """FPAM: palette animations (FldObject.FLD_PAM_DATA). -> list of {'frame', 'key', 'durations'}: start frame and key, duration of each key (1/60 s; the textures of each key are 'pam/<name>.NNN').
    Header (4 x int16: frame, key, number of keys, flag) then, per key: duration (int16) + palette (16 colors of 2 bytes, 256 if flag & 1)."""
    cs = {t: (p, s) for t, p, s in chunks(raw)}
    if 'FPAM' not in cs: return []
    p, s = cs['FPAM']; n = struct.unpack_from('<i', raw, p + 8)[0]; out = []
    for o in struct.unpack_from('<%di' % n, raw, p + 12):
        fr, lookup_key, nc, flag = struct.unpack_from('<4h', raw, o); q = o + 8; durations = []
        for _ in range(nc):
            durations.append(struct.unpack_from('<h', raw, q)[0]); q += 2 + (0x200 if flag & 1 else 0x20)
        out.append(dict(frame=fr, key=lookup_key, durations=durations))
    return out

if __name__ == '__main__':
    raw = open(sys.argv[1], 'rb').read()
    print([(t, hex(p), hex(s)) for t, p, s in chunks(raw)])
    n, objs = map_objs(raw); print('nobj', n)
    for o in objs: print(o)
