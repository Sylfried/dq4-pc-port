"""Replaces MenuParts.SystemInit (loading of Resources): real fonts/shaders/colors/frameData, outside Unity."""
import struct, re
import runall2 as R, reloc as rl, addresses as A
import os
FRAME = os.environ.get('DQ_FRAME', 'frameData.bin')

def klass_of(T, name):
    for tok, nm in rl.M.items():
        if nm == name + '_TypeInfo':
            k = T.klass.get(tok) or T.new_klass(tok); T.w(tok, k); return k
    return None
def arr(T, items, esize, kname=None):
    n = len(items); o = T.alloc(0x20 + esize * n + 16); T.w(o + 0x18, n, 8); T.obj[o] = len(T.obj) + 1
    for i, raw in enumerate(items): T.uc.mem_write(o + 0x20 + esize * i, raw)
    return o
def load_frames(T, path=FRAME):
    b = open(path, 'rb').read(); n = struct.unpack_from('<i', b, 0)[0]; p = 4; objs = []
    kml = klass_of(T, 'MeshList')
    for i in range(n):
        nv, ni = struct.unpack_from('<ii', b, p); p += 8
        v = [struct.unpack_from('<5f', b, p + 20 * j) for j in range(nv)]; p += 20 * nv
        t = struct.unpack_from('<%di' % ni, b, p); p += 4 * ni
        m = T.new_obj(kml or 0, fill=False)
        T.w(m + 0x10, arr(T, [struct.pack('<3f', *x[:3]) for x in v], 12))
        T.w(m + 0x18, arr(T, [struct.pack('<2f', *x[3:]) for x in v], 8))
        T.w(m + 0x20, arr(T, [struct.pack('<i', x) for x in t], 4))
        objs.append(m)
    return arr(T, [struct.pack('<Q', o) for o in objs], 8)

def system_init(T, frame_path=FRAME, lang=1):
    st = R.statics(T, 'MenuParts'); F = lambda name: A.field('MenuParts', name)          # (static fields by name: DQ VI inserts some)
    T.w(st + F('l_unityFont'), T.newU('Font', 'UnityEngine.Font'))
    for fld, nm in (('l_fontShader', 'font'), ('l_grayShader', 'gray'), ('l_reverseShader', 'reverse'), ('l_pictureShader', 'picture'), ('l_partsShader', 'parts')):
        T.w(st + F(fld), T.newU('Shader', 'UnityEngine.Shader', name=nm))
    cl = T.u(st + F('s_colorList'), 8); fl = T.u(st + F('l_colorFontList'), 8); n = T.u(cl + 0x18, 8)
    for i in range(n):
        col = list(struct.unpack('<4f', bytes(T.uc.mem_read(cl + 0x20 + 16 * i, 16))))
        m = T.newU('Material', 'UnityEngine.Material', shader='font', color=[round(x, 4) for x in col], tex=None, sheet='font')
        T.w(fl + 0x20 + 8 * i, m)
    T.w(st + F('l_frameData'), load_frames(T, frame_path))
    # language: GetLangages.m_langagesNumber (0 = ja, 1 = en: the language that the French patch replaces) -> MenuParts.LangParam.Apply
    sl = T.u(st + F('s_langParam'), 8)
    T.run(A.LANG_APPLY, [sl + 0x20 + 0x18 * lang])
    set_language(T, lang)
    return n


def set_language(T, lang=1):
    """GetLangages.m_langagesNumber / LangJapanese: read by about sixty menu functions (sizes, text offsets, Japanese variants...).
    Without this the emulation took "other language" branches and the button labels ended up 20 units too low."""
    klass_of(T, 'GetLangages')
    sg = R.statics(T, 'GetLangages')
    if not sg: print('GetLangages: statics not found'); return
    T.w(sg + 0, lang, 4); T.w(sg + 4, 1 if lang == 0 else 0, 1)

def make_message(T, port=0):
    """Builds the message window (MenuMessage..ctor): several windows are placed relative to it (MenuMessage.m_window)."""
    obj = T.new_obj(klass_of(T, 'MenuMessage') or 0)
    err = T.run(A.MESSAGE_CTOR, [obj, port])
    T.msg = obj
    return err
