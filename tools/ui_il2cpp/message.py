"""Export of the message window (MenuMessage): for each window type (MenuMessage.canvas_data), window position, frame
(frameData), quadrilateral of the text canvas (the text is drawn by the engine) and position of the end-of-page cursor.
Usage: python message.py output.json   (variables DQ_IL2, DQ_META, DQ_FRAME as in layout.py)"""
import sys, json, struct
import scene as S, runall2 as R, menusys as M, layout as L, addresses as A
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import *
T = S.T
r4 = lambda x: round(float(x), 4)


def read_borders():
    b = open(M.FRAME, 'rb').read(); n = struct.unpack_from('<i', b, 0)[0]; p = 4; out = []
    for i in range(n):
        nv, ni = struct.unpack_from('<ii', b, p); p += 8
        v = [struct.unpack_from('<5f', b, p + 20 * j) for j in range(nv)]; p += 20 * nv
        t = list(struct.unpack_from('<%di' % ni, b, p)); p += 4 * ni
        out.append((v, t))
    return out


BORDERS = read_borders()
st = R.statics(T, 'MenuMessage')
parts_win = T.u(st + A.field('MenuMessage', 'm_window'), 8)       # MenuMessage.m_window (MenuParts)
go_win = T.U[parts_win]['go']
mf_win = [c for c in T.U[go_win]['comps'] if T.U[c]['kind'] == 'MeshFilter'][0]
ALL = []
NOW_TYPE = A.field('MenuMessage', 'm_nowType')


def _border(uc, a, sz, ud):
    """m_frame.Change(n): delegate call not emulated -> we set the frame mesh n on the window ourselves (then we skip the call)."""
    n = uc.reg_read(UC_ARM64_REG_X1) & 0xffffffff
    if n >= len(BORDERS):                                         # a type whose frame number is not a frame (DQ VI: -1, no frame): the window keeps no frame mesh
        ALL.append(n); uc.reg_write(UC_ARM64_REG_PC, A.SET_CANVAS_MESH_FRAME_CALL + 4); return
    v, t = BORDERS[n]
    m = T.U[mf_win].get('mesh')
    if not m: m = T.U[mf_win]['mesh'] = T.newU('Mesh', 'UnityEngine.Mesh', vtx=[], uv=[], tris={}, sub=1)
    T.U[m]['vtx'] = [tuple(x[:3]) for x in v]; T.U[m]['uv'] = [tuple(x[3:]) for x in v]; T.U[m]['tris'] = {0: t}
    ALL.append(n)
    uc.reg_write(UC_ARM64_REG_PC, A.SET_CANVAS_MESH_FRAME_CALL + 4)


T.uc.hook_add(UC_HOOK_CODE, _border, None, A.SET_CANVAS_MESH_FRAME_CALL, A.SET_CANVAS_MESH_FRAME_CALL)


def export_saves():
    cd = T.u(st + A.field('MenuMessage', 'canvas_data'), 8); n = T.u(cd + 0x18, 4)
    msg = T.msg
    canvas_go = T.u(msg + 0x18, 8)
    types = []
    for no in range(n):
        raw = struct.unpack('<iiffffff', bytes(T.uc.mem_read(cd + 0x20 + 32 * no, 32)))
        T.uc.mem_write(msg + NOW_TYPE, b'\xff\xff')              # m_nowType: forces the recalculation
        del ALL[:]
        err = T.run(A.SET_CANVAS_MESH, [msg, no])
        cm = T.U[T.u(msg + 0x28, 8)]
        win = T.U[go_win]; feed_parts = T.u(msg + 0x20, 8); feed_go = T.U[feed_parts]['go']
        fm = T.U[mf_win].get('mesh'); fm = T.U[fm] if fm else None
        t = dict(no=no, err=err, frame=raw[0], indent=raw[1], cursor=[r4(raw[2]), r4(raw[3])], yDif=r4(raw[4]), scale=r4(raw[5]), shift=r4(raw[6]),
                 flag=struct.unpack('<i', struct.pack('<f', raw[7]))[0] & 0xff,
                 win=[r4(x) for x in T.world(win['tr'])],
                 canvas=dict(vtx=[[r4(v[0]), r4(v[1]), r4(v[2])] for v in cm['vtx']], uv=[[r4(x) for x in v] for v in cm['uv']], tris=cm['tris'].get(0)),
                 canvas_local=[r4(x) for x in T.U[T.U[canvas_go]['tr']].get('lpos', [0, 0, 0])],
                 feed_local=[r4(x) for x in T.U[T.U[feed_go]['tr']].get('lpos', [0, 0, 0])],
                 frame_mesh=dict(vtx=[[r4(v[0]), r4(v[2])] for v in fm['vtx']], uv=[[r4(x) for x in v] for v in fm['uv']], tris=fm['tris'].get(0)) if fm else None)
        types.append(t)
    fg = T.U[T.U[T.u(msg + 0x20, 8)]['go']]
    feed = None
    for c in fg['comps']:
        cu = T.U[c]
        if cu['kind'] == 'MeshFilter' and cu.get('mesh'):
            m = T.U[cu['mesh']]; feed = dict(vtx=[[r4(v[0]), r4(v[2])] for v in m['vtx']], uv=[[r4(x) for x in v] for v in m['uv']], tris=m['tris'].get(0))
    for c in fg['comps']:
        if T.U[c]['kind'] == 'MenuParts': feed['parts'] = dict(nowParts=T.u(c + 0x20, 4, True))
        if T.U[c]['kind'] == 'MeshRenderer' and feed:
            feed['mats'] = [dict(sheet=T.U[mm].get('sheet'), part=T.U[mm].get('part')) for mm in T.U[c].get('mat', []) if mm in T.U]
    mr = [c for c in T.U[go_win]['comps'] if T.U[c]['kind'] == 'MeshRenderer'][0]
    win_mats = [dict(sheet=T.U[mm].get('sheet'), part=T.U[mm].get('part')) for mm in T.U[mr].get('mat', []) if mm in T.U]
    return dict(types=types, feed=feed, frame_mats=win_mats, canvas_size=512, screenH=T.screen[1])


if __name__ == '__main__':
    out = export_saves()
    json.dump(out, open(sys.argv[1], 'w'))
    for t in out['types']:
        print(t['no'], 'err', t['err'], 'frame', t['frame'], 'indent', t['indent'], 'win', t['win'], 'canvas', t['canvas']['vtx'][:3], 'feed', t['feed_local'])
