"""Test helper: draw a text cell with the REAL `Render._text`, without a window or GL context, and read the exact geometry of the quads (all menu texts are at the exact position of the game).

`Render._text` does its computations (anchor, line spacing, alignment, width) then sends one quad per line segment to `self.prog.vertex_list`; here `prog` records the quads and `ui_menu.gl` is replaced by a fake module.
The font is the game's when given (`ui_garrir.json`, real measurements), otherwise a dummy font with the same line spacing and the same ascent as SE-GARRIR (8 px per character).

    import _text_render as TR
    quads = TR.draw(window, node)          # [Quad(text, x, base, width, ts)] : x = left edge of the starting ink, base = baseline, ts = horizontal scale (1 = no compression)"""
import os, re, sys, types, collections

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
import numpy as np
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.menus import ui_menu as UM
UM.TEXT_CENTERING = False          # (re-centering is the port's default; these tests measure the EXACT position of the original game, option DQ_ORIGINAL_TEXT=1; tests/test_text_recentering.py turns it back on)

LEADING, ASCENT = 23.525390625, 18.88671875          # SE-GARRIR: line spacing and ascent (font px)
PAD, UP, DOWN = 2, 22, 9                              # margin, texture lines above / below the baseline (BitmapFont)
CACHE = _paths.ui_cache('/tmp/audit_final/interface/uicache')

Quad = collections.namedtuple('Quad', 'text x base width ts')


class FakeFont:
    """Dummy font (BitmapFont interface used by Render._text): `advance` px per character, control characters do not count. `line` creates no texture."""
    leading, ascent, PAD, UP, DOWN = LEADING, ASCENT, PAD, UP, DOWN

    def __init__(self, advance=8): self.advance = advance; self.calls = []

    def width_px(self, text): return self.advance * sum(1 for c in text if c >= ' ')

    def line(self, text):
        self.calls.append(text)
        return types.SimpleNamespace(target=0, id=0), int(self.width_px(text)) + 2 * PAD, UP + DOWN, UP


class RealFont:
    """The real SE-GARRIR font (ui_garrir.json / .png from `CACHE`) for the widths, but without a texture (`line` creates nothing)."""
    def __init__(self, bm): self.bm = bm; self.leading, self.ascent = bm.leading, bm.ascent; self.PAD, self.UP, self.DOWN = bm.PAD, bm.UP, bm.DOWN

    def width_px(self, text): return self.bm.width_px(text)

    def line(self, text): return types.SimpleNamespace(target=0, id=0), int(self.bm.width_px(text)) + 2 * self.bm.PAD, self.bm.UP + self.bm.DOWN, self.bm.UP


def real_font():
    """RealFont, or None if the font files are not there."""
    j, g = os.path.join(CACHE, 'ui_garrir.json'), os.path.join(CACHE, 'ui_garrir.png')
    return RealFont(UM.BitmapFont(j, g)) if os.path.exists(j) and os.path.exists(g) else None


class _Prog:
    def __init__(self): self.quads = []
    def vertex_list(self, n, mode, **kw):
        p = np.asarray(kw['position'][1], dtype=float).reshape(-1, 2); self.quads.append((p[0][0], p[0][1], p[1][0], p[2][1])); return types.SimpleNamespace(draw=lambda *a, **k: None, delete=lambda: None)
    def __setitem__(self, k, v): pass


class _Gl:
    GL_TRIANGLES = 4; GL_TEXTURE0 = 0x84C0
    @staticmethod
    def glActiveTexture(*a): pass
    @staticmethod
    def glBindTexture(*a): pass


def render(font=None, neighbors=(), ml=None):
    """A Render without GL: recording prog, `ml` (the real layout, or a minimal one: dy = 0, the text is at the cell's position, without line-spacing compensation); `font` None = fallback font (texts.bitmap None, dummy GMaruGoPro-M of 8 px per character)."""
    r = object.__new__(UM.Render)
    r.ml = ml or types.SimpleNamespace(hdr={'lang': {'dy': 0.0, 'hiro': 1.0}}, colors=[(1.0, 1.0, 1.0, 1.0)] * 8)
    r.texts = types.SimpleNamespace(bitmap=font, line=lambda text, px: (types.SimpleNamespace(target=0, id=0), 8 * len(text) + 4, 30, 22))
    r.neighbors = list(neighbors); r.prog = _Prog()
    return r


def draw(win, node, font=None, r=None, s=1.0):
    """Draws `node` of window `win` (cx = cy = 0, scale `s`) and returns its quads. `font`: FakeFont by default; for the fallback font, pass `r` (a render(None))."""
    if r is None: r = render(font if font is not None else FakeFont())
    bm = r.texts.bitmap; r.prog.quads = []; drawn = []                     # drawn: texts actually drawn, in order (a re-cut description no longer has the cell's lines)
    holder, name_str = (bm, 'line') if bm else (r.texts, 'line'); orig = getattr(holder, name_str)
    setattr(holder, name_str, (lambda text, *a: (drawn.append(text), orig(text, *a))[1]))
    old = UM.gl; UM.gl = _Gl
    try: r._text(win, node, 0.0, 0.0, s)
    finally: UM.gl = old; setattr(holder, name_str, orig) if bm is None else holder.__dict__.pop(name_str, None)
    u = node['text']['characterSize'] * 0.1; out = []
    for text, (x0, y0, x1, y1) in zip(drawn, r.prog.quads):
        if bm:
            ts = (x1 - x0) / ((int(bm.width_px(text)) + 2 * bm.PAD) * u * s)
            out.append(Quad(text, (x0 + bm.PAD * u * s * ts) / s, y0 / s + bm.DOWN * u, (x1 - x0) / s, ts))
        else:
            ts = (x1 - x0) / (8 * len(text) + 4)
            out.append(Quad(text, (x0 + 2 * ts) / s, (y0 + 8) / s, (x1 - x0) / s, ts))
    return out


def _segments(node):
    """Texts of the segments in the order in which Render._text draws them (one line = one segment per color "@cN")."""
    out = []
    for l in node['text']['text'].split('\n'):
        pos = 0
        for m in re.finditer(r'@c(\d)', l):
            if m.start() > pos: out.append(l[pos:m.start()])
            pos = m.end()
        if pos < len(l): out.append(l[pos:])
    return out


def make_window(typ, cells, port=0, name_str='Make_Test()', plates=()):
    """Synthetic window of type `typ`: one text cell per element of `cells` ({'pos': [x, y, z], 'anchor', 'alignment', 'ls', 'cs', 'tab'}: all optional), bound to parameter (port, k); node number 10 + k.
    `plates`: button plates (part 7, like the game's) {'pos': [x, z], 'w', 'h'} (total width and height), nodes 100 + k, button number k: the text whose anchor is inside was compressed to fit."""
    def text(k, c):
        return {'id': 10 + k, 'par': 1, 'pos': list(c.get('pos', [0.0, 4.0, 0.0])), 'act': True, 'mats': [],
                'text': {'font': 'font', 'characterSize': c.get('cs', 9.945), 'text': None, 'anchor': c.get('anchor', 3), 'alignment': c.get('alignment', 0), 'lineSpacing': c.get('ls', 0.801), 'tabSize': c.get('tab')}}
    def plate(k, c):
        w, h = c['w'] / 2.0, c['h'] / 2.0
        return {'id': 100 + k, 'par': 1, 'pos': [c['pos'][0], 4.0, c['pos'][1]], 'act': True, 'mats': [{'part': 7}], 'parts': {'buttonId': k, 'gamepad': 0x10},
                'mesh': {'vtx': [[-w, h], [w, h], [w, -h], [-w, -h]], 'uv': [[0, 0], [1, 0], [1, 1], [0, 1]], 'sub': {'0': [0, 1, 2, 0, 2, 3]}}}
    t = {'name': name_str, 'err': None, 'nodes': [{'id': 1, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True, 'mats': []}] + [plate(k, c) for k, c in enumerate(plates)] + [text(k, c) for k, c in enumerate(cells)],
         'parts': [{'node': 1, 'ib': [{'k': 'text', 'go': 10 + k, 'variant': 0} for k in range(len(cells))]}], 'params': [{'id': port, 'no': k, 'parts': 0, 'base': k} for k in range(len(cells))], 'codes': [], 'builds': []}
    return UM.Window(types.SimpleNamespace(types={str(typ): t}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0)), typ)
