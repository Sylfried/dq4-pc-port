"""Menu windows of the original game: exact layout (read from the game's Unity code, see tools/ui_il2cpp), drawn with the game's sheets.

The layout file (cache/ui_layout.json) describes, for each window type (Make_* of MenuPortItemTable): the objects (position, mesh,
materials, text), the editable elements (IText / IIcon / IButton / IBar...) and their bindings (id, no) -> element, and the effect of each code
(move / display). This module applies the engine's messages (setItemParam*, setItemCode, cursor) to these objects and draws them.
Game coordinate system: portrait 450 x 800, X to the right, Z up, origin at the center of the screen, Y = depth (larger = in front)."""
import os, re, json, math, time
import numpy as np
import pyglet
from pyglet import gl
from pyglet.graphics.shader import Shader, ShaderProgram
from dq456_pc.language import tr
from dq456_pc import games as GM
from dq456_pc.core.plates import separate_plates

VERTEX = '''#version 330 core
in vec2 position; in vec2 tex_coords; in vec4 colors;
uniform vec2 vp;
out vec2 v_uv; out vec4 v_col;
void main() { gl_Position = vec4(position.x / vp.x * 2.0 - 1.0, position.y / vp.y * 2.0 - 1.0, 0.0, 1.0); v_uv = tex_coords; v_col = colors; }'''
FRAG = '''#version 330 core
in vec2 v_uv; in vec4 v_col; out vec4 fragColor;
uniform sampler2D tex; uniform int mode;
void main() {
    vec4 c;
    if (mode == 3) {                                                                               // map plane: sharp texels, only the border between two texels is smoothed ("sharp bilinear")
        vec2 ts = vec2(textureSize(tex, 0)); vec2 p = v_uv * ts; vec2 seam = floor(p + 0.5);
        vec2 aa = max(fwidth(p), vec2(1e-4)); c = texture(tex, (seam + clamp((p - seam) / aa, -0.5, 0.5)) / ts); }
    else c = texture(tex, v_uv);
    if (mode == 1) { float g = dot(c.rgb, vec3(0.299, 0.587, 0.114)); c.rgb = vec3(g); }          // grayed button
    else if (mode == 2) { c.rgb = vec3(1.0) - c.rgb; }                                            // inverted button
    c *= v_col;
    if (c.a < 0.004) discard;
    fragColor = c; }'''

LINE_HEIGHT = 1.246     # (fallback font GMaruGoPro-M, used only without ui_garrir.*) line height of the font in "em" (OS/2 winAscent + winDescent of GMaruGoPro-M): consistent with the spacing of the HP/MP bars (28 px) and the centering of the buttons
FONT_SIZE = 19.0        # (fallback GMaruGoPro-M) native size of the game font (GMaruGoPro-M, Font.fontSize): 1 character = taille_caractere * 0.1 * 19 units
TEXT_MARKS = {0: (1.0, None), 1: (1.0, 8.0), 2: (1.0, 'base'), 3: (1.0, 9.0), 4: (1.0, 6.25), 5: ('x14', 'base')}   # "^n" at the head of a text (IText): (x scale, character size)


def first_line_baseline(zp, row, n, step, asc):
    """Vertical coordinate (units, upward) of the baseline of the first line of a TextMesh: TextMesh.anchor places the anchor point zp at the top (row 0), middle (1) or bottom (2) of a block of n lines of height `step`
    (= the font's line spacing x characterSize x 0.1 x lineSpacing); the baseline is `asc` (the font's ascent x characterSize x 0.1) below the top of the line, whatever lineSpacing is.
    Verified on the mobile capture (ecran4: "Rat volant" 1 line, "Scarapince / x2" 3 lines, "Ragnar" tab), to within 0.3 unit."""
    hb = n * step
    return zp + (hb if row == 2 else hb / 2 if row == 1 else 0.0) - asc


TEXT_CENTERING = os.environ.get('DQ_ORIGINAL_TEXT', '') not in ('1', 'true')      # DQ_ORIGINAL_TEXT=1: exact vertical placement of the original game, without the optical re-centering of `text_recentering` or the tracking of the type 54 title


def text_recentering(leading, u, ls):
    """Lift (units) to apply to the text to center the ink in its line (every text is centered). The game set lineSpacing (0.441 targets, 0.481 monster plates,
    0.801 tabs / buttons / names...) for the Japanese font: the line box is shortened by (1 - ls) but the baseline stays at `ascent` from the top of the line, so with SE-GARRIR (ink centered in its natural 23.5 px box)
    the text drops by (1 - ls) x line spacing x u / 2 below the center of its box (6.5 units for "Rat volant" and the plates: text stuck to the bottom of the frame). Applied to the three vertical anchors (the ink / box gap does not depend on the anchor;
    only the middle case has a mobile reference, ecran4). lineSpacing >= 1 (HP / MP / Lv., set on the gauges): 0. DELIBERATE DEVIATION from the original game, which has the same flaw."""
    return leading * u * (1.0 - ls) / 2 if TEXT_CENTERING and ls < 1.0 else 0.0


# Button states (MenuParts.BUTTON_STATE_*, param (id, 0) of a plate): 0 normal, 1 pressed, 2 invisible, 3 grayed (gray shader), 4 inverted (inverse shader, pressed).
STATE_NORMAL, STATE_PRESSED, STATE_INVISIBLE, STATE_GRAYED, STATE_INVERTED = 0, 1, 2, 3, 4
AUTO_CAPTION = 'Sauvegarde automatique'      # string 623 of the game (FR patch): the label of the auto plate when the engine does not send one (it only sends it with a valid data5.dat)
TEXT_GRAY = 3                               # MenuParts.TEXT_COLOR_GRAY: text color of a grayed button (game palette)
AUTO_BUTTON = 4                              # number of the "Sauvegarde automatique" button of the start menu (type 53, engine cell (4, 1), bank 4 = data5.dat)
LANGUAGE_BUTTON = 12                         # the port's language button of the start menu (type 53), between "License" (11) and "Saves" (8); the engine has no such number and never receives it
LICENSE_BUTTON = 11
GLOBE_PX = 48                                # texture 'globe' of the language plate (pixels, square); the globe takes 28 x 28 units on the plate


def is_state_active(state):
    """Does a button react to contact (mouse, touch) and to confirmation? MenuParts.IButton: the state callback file (RVA 0xD043CC) disables the hit test (`defaultIsHit`, 0xCFDB6C) for states 2 (invisible),
    3 (grayed) and 4 (inverted); normal and pressed leave it active. A grayed button is therefore neither hovered nor chosen, and the engine receives nothing."""
    return state not in (STATE_INVISIBLE, STATE_GRAYED, STATE_INVERTED)


# MenuPortItemTable.IBetText (DQ V / VI betting lines): its static s_replace table, applied in order with string.Replace: @0 closes a color, @1 to @7 open one
BET_CODES = (('@0', '</color>'), ('@1', '<color=#ff84ffff>'), ('@2', '<color=#31ceffff>'), ('@3', '<color=#84ff84ff>'), ('@4', '<color=#ffc542ff>'),
             ('@5', '<color=#ff4242ff>'), ('@6', '<color=#4280ffff>'), ('@7', '<color=#ffff00ff>'))


def bet_text(s):
    """Text of a betting line as IBetText's TextMesh receives it: the codes @0 to @7 replaced by Unity rich text color tags."""
    for code, tag in BET_CODES: s = s.replace(code, tag)
    return s


def expand_tabs(s, tab_size):
    """TextMesh.tabSize: a tab equals `tabSize` times the width of a space (8 for "Cout en PM:	  2" of the spells and the "Nv." line of the party order, 25 for the "x2" of the group plates); the game's font has no glyph for "	":
    it counted for nothing and the following text stuck to what preceded it ("Nv." drawn over the character's sprite, "x2" stuck to the left of the plate). Cell without tabSize: unchanged."""
    if not tab_size or not isinstance(s, str) or '\t' not in s: return s
    return s.replace('\t', ' ' * max(0, int(round(tab_size))))


def auto_plate_available(code_auto, engine_label_text):
    """Does the auto-save exist? The engine says so through code 0 of the start menu (1: data5.dat valid, 0: missing or unreadable) and sends the label of cell (4, 1) only in the first case;
    `code_auto` None (code not yet received): the label decides."""
    if code_auto is not None: return code_auto != 0
    return bool((engine_label_text or '').strip())


def read_borders(path):
    """frameData (the game's TextAsset): number of meshes, then for each: number of vertices, number of indices, vertices (x, y, z, u, v), indices."""
    import struct
    b = open(path, 'rb').read(); n = struct.unpack_from('<i', b, 0)[0]; p = 4; out = []
    for _ in range(n):
        nv, ni = struct.unpack_from('<ii', b, p); p += 8
        v = np.frombuffer(b, '<f4', nv * 5, p).reshape(nv, 5); p += 20 * nv
        t = np.frombuffer(b, '<i4', ni, p); p += 4 * ni
        out.append(dict(vtx=[[float(x[0]), float(x[2])] for x in v], uv=[[float(x[3]), float(x[4])] for x in v], tri=[int(i) for i in t]))
    return out


def three_lines(t1, t0):
    """(proposed fix) type 1 (battle: frame 188 high, canvas 164 = 4 lines of 34) brought down to the height of the field window (type 0: frame 126, 3 lines):
    the top two rows of the frame and the top of the canvas move down by dz, the bottom edge does not move; V of the canvas bottom = height / 512 (the top stays at V = 0)."""
    import copy
    t = copy.deepcopy(t1)
    h1 = max(v[1] for v in t1['frame_mesh']['vtx']) - min(v[1] for v in t1['frame_mesh']['vtx'])
    h0 = max(v[1] for v in t0['frame_mesh']['vtx']) - min(v[1] for v in t0['frame_mesh']['vtx'])
    dz = h1 - h0
    mid = (max(v[1] for v in t1['frame_mesh']['vtx']) + min(v[1] for v in t1['frame_mesh']['vtx'])) / 2
    for v in t['frame_mesh']['vtx']:
        if v[1] > mid: v[1] -= dz
    cv = t['canvas']; zmax = max(v[2] for v in cv['vtx']); zmin = min(v[2] for v in cv['vtx'])
    for v in cv['vtx']:
        if v[2] == zmax: v[2] -= dz
    hv = (zmax - dz - zmin) / 512.0 / (t.get('scale') or 1.0)
    for u, v in zip(cv['uv'], cv['vtx']):
        if v[2] == zmin: u[1] = hv
    return t


def limit_lines(t, num=3, lh=28.0, margin=3.0):
    """Message window: the canvas shows exactly `num` lines of `lh` pixels (plus a 3-pixel margin, the engine's scrolling starts at -3) instead of 3.5 lines: the original layout
    lets the top of the next line show under the last line (canvas of 100.5 for lines of 28: type 0; battle: lines of 34)."""
    import copy
    cv = t['canvas']; zmax = max(v[2] for v in cv['vtx']); zmin = min(v[2] for v in cv['vtx']); h = num * lh + margin
    if zmax - zmin <= h + 0.5: return t
    t = copy.deepcopy(t); cv = t['canvas']
    for v in cv['vtx']:
        if v[2] == zmin: v[2] = zmax - h
    for u, v in zip(cv['uv'], cv['vtx']):
        if v[2] == zmax - h: u[1] = h / 512.0
    return t


def full_text(t):
    """Battle message types 2 and 3 (action messages): the original layout draws their text canvas at 90% (`scale` 0.9: 490 pixels of the canvas in 441 units), which makes the text
    smaller than in the field dialogues and the battle start message. The whole window (frame, canvas, end-of-page cursor) is enlarged by 1 / scale around its bottom-left corner, then re-centered:
    the text has the size of the other dialogues, with as many characters per line as in the original (bottom edge unchanged)."""
    import copy
    f = 1.0 / (t.get('scale') or 1.0)
    if abs(f - 1.0) < 1e-6: return t
    t = copy.deepcopy(t)
    for v in t['frame_mesh']['vtx']: v[0] *= f; v[1] *= f
    for v in t['canvas']['vtx']: v[0] *= f; v[2] *= f
    fl = t['feed_local']; t['feed_local'] = [fl[0] * f, fl[1], fl[2] * f]
    w0 = max(v[0] for v in t['frame_mesh']['vtx']) / f; w1 = w0 * f                  # frame width before / after
    t['win'] = [t['win'][0] - (w1 - w0) / 2, t['win'][1], t['win'][2]]
    return t


def same_box(t, ref):
    """a battle message type drawn in the box of the action messages (`ref`, types 2 / 3 after full_text): the battle start message (type 1, "X apparaît !", 459 units wide where the
    actions' box is 510) and the 4-line one (type 4) take ref's frame, place and end-of-page cursor; their own text canvas (its size, its texels: the engine wraps their text to it) is put at the
    top-left corner of ref's canvas. A canvas taller than ref's (4 lines) raises the top of the frame by the difference, the bottom edge staying where it is: every battle box has the same width,
    the same bottom edge and the same rule (the "Dialogue" setting of the interface editor applies to all of them alike)."""
    import copy
    t = copy.deepcopy(t); r = copy.deepcopy(ref)
    cv, rc = t['canvas']['vtx'], r['canvas']['vtx']
    top, rtop = max(v[2] for v in cv), max(v[2] for v in rc); bottom, rbottom = min(v[2] for v in cv), min(v[2] for v in rc)
    dx, dz = min(v[0] for v in rc) - min(v[0] for v in cv), rtop - top
    extra = max(0.0, (top - bottom) - (rtop - rbottom))                  # (a 4-line canvas: the frame grows upward)
    if extra > 0:
        fz = [v[1] for v in r['frame_mesh']['vtx']]; mid = (max(fz) + min(fz)) / 2
        for v in r['frame_mesh']['vtx']:
            if v[1] > mid: v[1] += extra
        dz += extra
    for v in cv: v[0] += dx; v[2] += dz
    t['frame_mesh'] = r['frame_mesh']; t['win'] = r['win']; t['feed_local'] = r['feed_local']
    return t


class PageLayout:
    """cache/ui_layout.json: {'header': {...}, 'types': {number: {...}}}; frames: window meshes (frameData)"""
    def __init__(self, path, borders=None):
        with open(path, encoding='utf-8') as f: d = json.load(f)
        self.hdr = d['header']; self.types = d['types']; self.message = d.get('message')       # message: dialogue window (MenuMessage), absent from the old files
        if self.message:                                                 # battle (type 1): 3 lines like the field; the original frame (4 lines) stays at type 4, for the messages that have four
            ts = self.message['types']; ts.append(ts[1]); ts[1] = three_lines(ts[1], ts[0])
            for i in (2, 3): ts[i] = limit_lines(full_text(ts[i]), 3, 34.0)
            ts[1] = same_box(ts[1], ts[2]); ts[4] = same_box(limit_lines(ts[4], 4, 34.0), ts[2])          # (every battle box like the actions' one)
            ts[0] = limit_lines(ts[0], 3, 28.0)                          # battle action messages: text of the same size as in the dialogues
        self.info = self.hdr['info']; self.colors = [tuple(c) for c in self.hdr['colors']]
        self.pushed = tuple(self.hdr['pushed'])
        self.borders = read_borders(borders) if borders and os.path.exists(borders) else []


# MenuPortItemTable.name_button_param (RVA 0xCF8E00-0xCF8F98, .cctor): (number of rows, initial y coordinate, step) of the Make_NameButton list; the engine
# chooses the layout by the window's code 6 (`<Make_NameButton>b__0`, 0xD08BE8: rows 0 to number - 1 are enabled and placed at `initial - step x rank`, the others
# are disabled until the 6th). The exporter cannot run this function ("List index").
# Windows that are only a picture, created by their code function (MenuParts.CreateFromTexture(name, bFitWidth = true, 0.75): 450 wide, 337.5 high, built at the center of the screen): the names by value.
# DQ V Make_Sugoroku_Shop (the shops of the T'n'T boards): value 0 = the inn, any other = the shop. DQ VI Make_ShopPicture: the value is the index (shop, inn, church); its code 1 is the opacity, value / 31.
PICTURE_WINDOWS = {'Make_Sugoroku_Shop(': ('yado_pic', 'yorozu_pic'), 'Make_ShopPicture(': ('yorozu_pic', 'yado_pic', 'kyokai_pic')}
NUMBER_TEXT = '<Sub_ChangeNameButton>b__0'          # (int function of the level text of DQ VI's name change buttons, see Window.param_int)
NAMES_PRESETS = ((4, 382.0, 67.0), (5, 382.0, 67.0), (5, 434.0, 67.0), (6, 434.0, 67.0), (5, 412.0, 67.0))
NAMES_START, NAMES_STEP = 382.0, 67.0         # exported layout: row k at y coordinate 382 - 67 k (NAME_BUTTON_Y, NAME_BUTTON_DY)
CARD_COST_X_MAX = 214.0              # spell info panel (type 7) and spell info in battle (type 38): usable right edge of the cost line (right frame: x 63 to 221, measured on the screenshots, minus the plate margin)
CARD_DESC_X_MAX = 148.0              # spell info panel (type 7): usable right edge of the description (bottom frame: x -226 to 155.5, up to the back button, minus the plates' margin); the frame is only 2 lines high
BATTLE_DESC_X_MAX = 56.0              # item info in battle (type 38): usable right edge of the description (left cell: x -226 to 64.7, measured on a screenshot of the real engine, minus the margin); the cell is only 2 lines high, the "Attaque E 24" cell is to its right
# Item and spell descriptions: (window type, port, string number) -> usable right edge (interface units) of their frame, which only shows 2 lines. The port is in
# the key: the casino window (type 46) has four other text cells at the same string number (the lists, port 0 to 3) which are not descriptions. The patch's French
# text has lines of 38 characters, or a single line of 50 ("Peut aussi etre utilisee comme objet au / combat.", "Au combat, ils peuvent inverser le cours du
# temps."): it overflowed the frame and covered "Attaque E 74" (type 38) or the bag button (type 10). Render._text re-wraps it to this width then, if 2 lines are
# not enough, compresses it (Render._adjust_description).
DESCRIPTIONS = {(7, 0, 1): CARD_DESC_X_MAX, (10, 0, 4): CARD_DESC_X_MAX, (38, 2, 3): BATTLE_DESC_X_MAX,
                (46, 4, 3): CARD_DESC_X_MAX, (60, 4, 4): CARD_DESC_X_MAX, (61, 4, 4): CARD_DESC_X_MAX, (63, 0, 4): CARD_DESC_X_MAX, (70, 0, 3): CARD_DESC_X_MAX}      # 46, 60, 61, 63, 70: bottom bar of the shops and the casino (same frame as the spell info panel; Assumed: windows not opened in the engine)
COSTS = {(7, 0, 2): CARD_COST_X_MAX, (38, 2, 4): CARD_COST_X_MAX}      # lines "Cout en PM  2/ 30" (left-anchored, x 75): longer in French than "MP Cost  2/ 30", they are compressed to fit in their frame
COST_LISTS = {8: 4.0}      # field spell list (Make_NameButton): line "Cout en PM:<tab> 2" (tabSize 8, left-anchored in the right half of the button) -> lift (units); the text is fitted into its plate (Render._text). The battle list (Make_BattleIM, type 35) keeps the game's place: the number past the plate's right edge, as on the phone
COST_CELLS = (8, 34, 35)            # the cost lines (tab-8 cells) of these windows are green, the color of their TextMesh in the prefab (0, 1, 0)
MUTED_COSTS = (35, 8)               #: the battle spell list shows no cost line (the spell's own panel, the next window, gives it), the names in the middle of their plate; the field list too (type 8)
SEVEN_GIFTS = (6, 13)                 # MenuPortItem.s_shopType values for which Make_Casino_GiftList builds 7 prize rows (see Window._seven_gifts)
COMPRESSION_MIN = 0.7                 # maximum horizontal compression of a text that does not fit (2-line description, cost line)


def soft_hyphens(lines, width, room):
    """The patch's "$": a break point inside a word, never displayed. A line that fits in `room` (units; None: unknown) loses its "$"; a line that does not is cut at the last "$" whose
    head still fits with a hyphen ("Méga-" / "protection"), the rest goes on the next line (and is treated the same way). `width(text)` -> width in units. The engine does the same for the monster
    names it extracts with line breaks (MenuItem::ExtractTextUTF16, language 1); the other names (spells: "Méga$protection") reach the interface with their "$"."""
    out = []
    for l in lines:
        while '$' in l:
            plain = l.replace('$', '')
            if room is None or width(plain) <= room + 0.5: l = plain; break
            parts = l.split('$'); k = 1
            for j in range(2, len(parts)):
                if width(''.join(parts[:j]) + '-') <= room + 0.5: k = j
            out.append(''.join(parts[:k]) + '-'); l = '$'.join(parts[k:])
        out.append(l)
    return out


def uv_icon(info, no, scroll_offset):
    """PartsInfo.SetUV: 4 vertices (TL, TR, BR, BL) of icon number `no` in the sheet."""
    n = no + info['startNo']; w = info['widthNum']
    col = int(math.fmod(n, w)); lig = int(n / w)          # C integer division (toward zero)
    u0 = col * info['uvsize']; v0 = -(info['startV'] + lig * info['uvsize']); u1 = u0 + info['uvsize']; v1 = v0 - info['uvsize']
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


SHEET_ALPHA = {}                           # sheet (0 = MenuTexture, 1 = Button...) -> opacity (height x width, uint8) of the game's sheet, set by Render: used to measure the VISIBLE edge of a frame


def visible_edges(vtx, uv, tris, alpha, threshold=127):
    """(x0, x1, z0, z1) of the VISIBLE drawing of a frame mesh cell, in the mesh cell's local coordinate system (interface units), or None.
    A frame is a grid of tiles whose border tiles have a transparent margin in the sheet, of a size that differs from one frame to another (the dialogue frame: 6 units on the right, 4.5 at the top; the one for Yes / No: almost
    nothing): placing two frames edge to edge on the edges of their mesh cells offsets them by these margins. For each tile (mesh cell, triangles `tris`), `alpha` gives the columns and rows whose opacity exceeds `threshold`
    (the texture column grows with x, the row decreases as z goes up: v = -row / sheet height)."""
    h, l = alpha.shape; x0 = z0 = 1e9; x1 = z1 = -1e9; views = set()
    for i in range(0, len(tris) - 2, 3):
        ids = tris[i:i + 3]; P = [vtx[j] for j in ids]; U = [uv[j] for j in ids]
        bx0, bx1 = min(p[0] for p in P), max(p[0] for p in P); bz0, bz1 = min(p[1] for p in P), max(p[1] for p in P)
        if bx1 - bx0 < 1e-6 or bz1 - bz0 < 1e-6: continue
        c0 = min(u[0] for u in U) * l; c1 = max(u[0] for u in U) * l; r0 = min(-u[1] for u in U) * h; r1 = max(-u[1] for u in U) * h
        if c1 - c0 < 1e-6 or r1 - r0 < 1e-6: continue
        lookup_key = (round(bx0, 3), round(bx1, 3), round(bz0, 3), round(bz1, 3), round(c0, 3), round(r0, 3))
        if lookup_key in views: continue
        views.add(lookup_key)
        ca, ra = int(math.floor(c0 + 1e-6)), int(math.floor(r0 + 1e-6))
        a = alpha[ra:int(math.ceil(r1 - 1e-6)), ca:int(math.ceil(c1 - 1e-6))] > threshold
        if not a.any(): continue
        cols = np.where(a.any(axis=0))[0]; ranks = np.where(a.any(axis=1))[0]
        fx0 = max((ca + cols[0] - c0) / (c1 - c0), 0.0); fx1 = min((ca + cols[-1] + 1 - c0) / (c1 - c0), 1.0)        # fractions of the cell, from the left and from the top
        fh = max((ra + ranks[0] - r0) / (r1 - r0), 0.0); fb = min((ra + ranks[-1] + 1 - r0) / (r1 - r0), 1.0)
        x0 = min(x0, bx0 + (bx1 - bx0) * fx0); x1 = max(x1, bx0 + (bx1 - bx0) * fx1); z1 = max(z1, bz1 - (bz1 - bz0) * fh); z0 = min(z0, bz1 - (bz1 - bz0) * fb)
    return (x0, x1, z0, z1) if x0 < 1e8 else None


class Window:
    """An open menu window (an engine port): state modified according to the engine's messages."""
    def __init__(self, ml, typ, shop_type=0):
        self.ml = ml; self.typ = typ; self.t = ml.types[str(typ)]
        self.N = {}
        for n in self.t['nodes']:
            m = n.get('mesh')
            self.N[n['id']] = dict(id=n['id'], par=n['par'], pos=list(n['pos']), act=n['act'], mats=[dict(x) for x in n.get('mats', [])],
                                   vtx=[list(v) for v in m['vtx']] if m else None, uv=[list(v) for v in m['uv']] if m else None, sub=m['sub'] if m else None,
                                   text=dict(n['text']) if n.get('text') is not None else None, buttonId=(n.get('parts') or {}).get('buttonId'), pad=(n.get('parts') or {}).get('gamepad') or 0, state=0, tcol=0, tscale=1.0)
        self.parts = list(self.t['parts']); self.n_parts = len(self.parts)         # copy of the list: the church (type 66) adds the parts of its buttons to it
        name_str = self.t.get('name', '')                                              # types that the port animates or completes: the game does them with code that the exporter does not see
        self.church = name_str.startswith('Make_ChurchRoot'); self.eg_ids = []; self.church_texts = {}      # church: added elements, texts received before the buttons are created
        self.status = name_str.startswith('Make_BattleUpStatus'); self.shake = {}; self.t_cursor = None      # member plates in battle: shakes in progress (member -> state), start of the arrow's blinking
        self.names = name_str.startswith('Make_MonsterName')                            # monster plates: group marks (battle backdrop: they do not count toward the window's extent)
        if self.names:
            for node in self._marks(): node['marque'] = True
        self.begin = name_str.startswith('Make_StartMenuSelect')                       # start menu: frame chosen by code 3
        if name_str.startswith('Make_YesNo'): self._push_yes_no()                  # Yes / No: the two plates stacked on top of each other
        self.vals_code = {}; self.auto_grayed = False                              # last value of each received code; "Sauvegarde automatique" plate grayed by the viewer (see auto_plate)
        for pt in self.parts:
            node = self.N.get(pt['node'])
            for ib in pt['ib']:
                if ib['k'] == 'bar' and node and node['vtx'] and ib['vtx'] + 1 < len(node['vtx']):      # IBar.firstFunc: zero/width read from the quad
                    ib['zero'] = node['vtx'][ib['vtx']][0]; ib['width'] = node['vtx'][ib['vtx'] + 1][0] - node['vtx'][ib['vtx']][0]
                elif ib['k'] == 'frame' and ib.get('init') is not None: self._border(ib, ib['init'])
        self.params = {}
        for p in self.t['params']: self.params[(p['id'], p['no'])] = p
        for j, pt in enumerate(self.parts):                     # (see _face: the placeholder icon of a part that shows a portrait)
            if any(ib['k'] == 'other' and ib.get('cls', '').endswith('ITexture') for ib in pt['ib']): self._hide_placeholder(j)
        if name_str.startswith('Make_Casino_GiftList') and shop_type in SEVEN_GIFTS: self._seven_gifts()
        self.codes = {}
        for c in self.t['codes']: self.codes[c['id']] = [c]          # MenuPortItem.SetTableForCode: Dictionary<short, FUNC_SetCode>.set_Item, the last registration of a number wins (Make_BattleIM: the page arrows,
                                                                       # registered under code 1, are replaced by row 1's: the row's code no longer hides them, as on mobile; the arrows vanished on a page 2 of one line)
        for lst in self.codes.values():                       # "function" codes (monster plate...): code -1 = nothing to show, initial state
            for e in lst:
                if e['kind'] == 'func':
                    for nid, dd in ((e.get('fx') or {}).get('-1') or {}).get('d', {}).items():
                        if int(nid) in self.N and dd.get('act') is False: self.N[int(nid)]['act'] = False
        self.is_name_list = name_str.startswith('Make_NameButton'); self.names_offset = {}       # list of named buttons (type 8): offset already applied to each row (see _name_entries)
        if self.t.get('name', '').startswith('Make_NameButton'):       # list of 6 buttons but the engine only drives 5 (codes 0 to 4): the 6th (at the bottom, under "Quick save") stays hidden until a code shows it
            for e in self.codes.get(5, []):
                for nid, dd in ((e.get('fx') or {}).get('0') or {}).get('d', {}).items():
                    if int(nid) in self.N and dd.get('act') is False: self.N[int(nid)]['act'] = False
        self.pictures = next((v for k, v in PICTURE_WINDOWS.items() if name_str.startswith(k)), None); self.picture_index = name_str.startswith('Make_ShopPicture(')
        self.start_menu = self.t.get('name', '').startswith('Make_StartMenuSecond')
        if self.start_menu:     # start menu: the "Sauv. cloud" entry (button 8) no longer exists for the engine (byte g_isAmazon); the port puts its "Saves" button (export / import) there, label set here
            self.param_str(5, 0, tr('menus.saves'))
            self.language_plate = self._add_language_plate()
        if name_str.startswith('Make_Chapter('):               # chapter title: the exporter sees the quad of MenuParts.CreateFromTexture("Menu/map/hyodai1", bFitWidth = true, haspect = 1) with its default mesh (square of 450) and no texture (created by the code)
            for node in self.N.values():                  # CreateFromTexture fits the width (450) and deduces the height from the texture (256 x 128: 225): gold banner on a blue background, centered
                if node['vtx'] and node['mats'] and node['mats'][0].get('sheet') is None:
                    node['vtx'] = [[-225.0, 112.5], [225.0, 112.5], [225.0, -112.5], [-225.0, -112.5]]; node['mats'][0] = dict(node['mats'][0], sheet='hyodai1', color=[1.0, 1.0, 1.0, 1.0])
        self.was_seen = True; self.selected = None; self.selected_node = None; self.press_node = None; self.order = 0
        self.map_name = None; self.game_map = None            # map window (type 25): map image name, texture (set by the viewer)
        self.symbols = []; self.t_blink = None; self.map_mode = 3      # world map: discovered locations (x, y in pixels of the 256 x 192 map image), blinking start; filtering mode of the map image
        self.special = None                                                # small world map: special location (code 4), (x, y) in pixels of the 256 x 192 map image, or None

    # ---- applying messages
    def _ib(self, p):
        if 'parts' not in p or p['parts'] >= len(self.parts): return None, None
        pt = self.parts[p['parts']]
        return pt, (pt['ib'][p['base']] if p['base'] < len(pt['ib']) else None)

    def _border(self, ib, v):
        node = self.N.get(ib.get('go'))
        if node and 0 <= v < len(self.ml.borders):
            c = self.ml.borders[v]; node['vtx'] = [list(x) for x in c['vtx']]; node['uv'] = [list(x) for x in c['uv']]; node['sub'] = {'0': c['tri']}

    def _bar(self, ib, pt, v):
        node = self.N.get(pt['node'])
        if node and node['vtx']:
            o = ib['vtx']
            if v < 0: o -= 4; v = ~v
            if o + 2 < len(node['vtx']) and o >= 0:
                x = ib['zero'] + ib['width'] * v * 0.01
                node['vtx'][o + 1][0] = x; node['vtx'][o + 2][0] = x

    def _wrapped(self, p):
        w = (p.get('custom') or {}).get('wrap')
        if not w or w['parts'] >= len(self.parts): return None, None
        pt = self.parts[w['parts']]
        return pt, (pt['ib'][w['base']] if w['base'] < len(pt['ib']) else None)

    def param_int(self, i, no, v):
        p = self.params.get((i, no))
        if not p: return
        if 'custom' in p:
            cu = p['custom']; pt, ib = self._wrapped(p)
            if cu.get('cls', '').endswith('ICityMap'): return                                       # map window (type 25): the name of the map image texture (Menu/map) is set by the viewer (map_name)
            if cu.get('cls', '').endswith('StatusIconChanger'): self._status_icon(i, v); return       # status icons (dead, poison, sealed spell) and name color
            if cu.get('cls', '').endswith('ItemNumCTRL'): self._item_num(i, v); return              # quantity of a line of the item list (type 9)
            if cu.get('cls', '').endswith('BattleBar') and ib and ib['k'] == 'bar':      # BattleBar.Change(int): normal bar
                cu['_v'] = v; self._bar(ib, pt, v)
            return
        if 'textcolor' in p and p['textcolor'] is not None:
            for ib in self.parts[p['textcolor']]['ib']:
                if ib['k'] == 'text' and ib.get('go') in self.N: self.N[ib['go']]['tcol'] = v
            return
        pt, ib = self._ib(p)
        if not ib: return
        k = ib['k']
        if k == 'icon':
            node = self.N.get(pt['node'])
            if node and node['uv']:
                info = self.ml.info[ib['partsNo']]; o = ib['vtx']
                for j, uv in enumerate(uv_icon(info, v, 0)):
                    if o + j < len(node['uv']): node['uv'][o + j] = list(uv)
        elif k == 'text':
            if NUMBER_TEXT in (ib.get('int') or ''):                               # DQ VI Sub_ChangeNameButton: this text's int function writes the number itself (nothing below 1), not a color
                node = self.N.get(ib.get('go'))
                if node and node['text'] is not None: node['text']['text'] = str(v) if v >= 1 else ''; node['was_seen'] = True
            elif ib.get('go') in self.N: self.N[ib['go']]['tcol'] = v
        elif k == 'bar': self._bar(ib, pt, v)
        elif k == 'button':
            node = self.N.get(pt['node'])
            if node: node['state'] = v
        elif k == 'frame': self._border(ib, v)
        elif k == 'other' and ib.get('cls', '').endswith('ITexture'): self._face(p['parts'], v)

    def _face(self, j, v):
        """ITexture (IntChanger, DQ V / VI): the material's texture becomes the portrait Menu/face/f<v, 2 digits> (opaque white), or nothing if the game has no such picture (Render: a missing
        texture is not drawn, as the color 0 of the original). Its material is the node's one without a sheet. The part's other icon (Sub_BattleTactics: AddIcon 24 of sheet 1, never changed by a
        parameter) is a placeholder: blank in DQ VI's sheet, a monster in DQ V's (the healslime drawn on the portraits and on the "Équipe" row); it is not drawn (_hide_placeholder)."""
        node = self.N.get(self.parts[j]['node'])
        if not node: return
        for m in node['mats']:
            if m.get('sheet') is None or str(m.get('sheet')).startswith('face:'): m['sheet'] = 'face:f%02d' % v; m['color'] = [1.0, 1.0, 1.0, 1.0]; break

    def _hide_placeholder(self, j):
        pt = self.parts[j]; node = self.N.get(pt['node'])
        if not node: return
        bound = {q.get('base') for q in self.params.values() if q.get('parts') == j}
        for b, ib in enumerate(pt['ib']):
            if ib['k'] != 'icon' or ib.get('partsNo') != 1 or b in bound or not node.get('sub'): continue          # (type 42: its status icons, sheet 13, are driven by a StatusIconChanger)
            for k, idx in node['sub'].items():
                if ib['vtx'] in idx and int(k) < len(node['mats']): node['mats'][int(k)]['color'] = [0.0, 0.0, 0.0, 0.0]

    def _item_num(self, i, v):
        """ItemNumCTRL.Changer(v) (0xD08060): passive two-digit counter of a line of the item list (Sub_ItemButton: IBase 3 = tens, IBase 4 = ones, sheet 12, 32 px tiles).
        v < 2: two empty tiles (icon 1); otherwise tens = (v / 10) % 10 (icon 16 x digit, or 1 if zero), ones = icon 16 x (v % 10); 100 and above wrap modulo 100 (123 -> 23).
        The two digits are IBase 3 and 4 of the line's MenuParts (the one of element (line, 0))."""
        p0 = self.params.get((i, 0))
        if not p0 or p0.get('parts') is None or p0['parts'] >= len(self.parts): return
        pt = self.parts[p0['parts']]; node = self.N.get(pt['node'])
        if node is None or not node['uv'] or len(pt['ib']) < 5: return
        if v < 2: dz, one = 1, 1
        else: d = (v // 10) % 10; dz = d * 16 if d else 1; one = (v % 10) * 16
        for ib, no in ((pt['ib'][3], dz), (pt['ib'][4], one)):
            if ib['k'] != 'icon': continue
            info = self.ml.info[ib['partsNo']]; o = ib['vtx']
            for j, uv in enumerate(uv_icon(info, no, 0)):
                if o + j < len(node['uv']): node['uv'][o + j] = list(uv)

    def param_str(self, i, no, s):
        if getattr(self, 'start_menu', False) and (i, no) == (5, 0): s = tr('menus.saves')          # (DQ V / VI ignore g_isAmazon there and keep sending "Sauv. cloud": the port's button keeps its own label)
        if self.church: self.church_texts[(i, no)] = s
        p = self.params.get((i, no))
        if not p: return
        if 'custom' in p and not (p['custom'].get('k') == 'text' and p['custom'].get('go') is not None):
            cu = p['custom']; pt, ib = self._wrapped(p)
            if cu.get('cls', '').endswith('BattleBar') and ib and ib['k'] == 'bar':      # BattleBar.Change(string) = RedApply: "red" bar = current value
                self._bar(ib, pt, ~cu.get('_v', 0))
            return
        if 'custom' in p:                                                          # a text of its own class (MenuPortItemTable.IBetText: its codes @0 to @7 become colors)
            ib = p['custom']
            if ib.get('cls', '').endswith('IBetText'): s = bet_text(s)
        else: pt, ib = self._ib(p)
        if not ib or ib['k'] != 'text': return
        node = self.N.get(ib.get('go'))
        if not node or node['text'] is None: return
        node['cell'] = (i, no)                                                              # (which cell the node shows, see Render.hidden_cells)
        base = node.setdefault('base', dict(cs=node['text']['characterSize']))
        node['tscale'] = 1.0; node['text']['characterSize'] = base['cs']
        if ib.get('variant') == 1 and '^' in s:
            j = s.index('^')
            if j + 1 < len(s):
                c = ord(s[j + 1]) - 48
                if 0 <= c <= 5:
                    ui_scale, cs = TEXT_MARKS[c]
                    hiro = self.ml.hdr['lang']['hiro']
                    node['tscale'] = hiro if ui_scale == 1.0 and c == 0 else (min(hiro * 1.4, 1.0) if c == 5 else 1.0)
                    if isinstance(cs, float): node['text']['characterSize'] = cs
                    elif cs == 'base': node['text']['characterSize'] = ib.get('fsize', base['cs'])
                s = s[:j] + s[j + 2:]
        elif ib.get('variant') == 1 and ib.get('fsize'): node['text']['characterSize'] = ib['fsize']
        if (self.typ, i, no) in DESCRIPTIONS: node['wrap_x'] = DESCRIPTIONS[(self.typ, i, no)]; node['wrap_n'] = 2        # description of a spell or an item: the frame shows 2 lines; if the text is wider or taller, it is re-wrapped to the frame's width (Render._adjust_description)
        if (self.typ, i, no) in COSTS: node['fit_x'] = COSTS[(self.typ, i, no)]                                       # cost line: must fit in its frame, compressed if needed (Render._text)
        if self.typ in COST_LISTS and node['text'].get('tabSize') == 8.0: node['in_plate'] = True; node['raise'] = COST_LISTS[self.typ]
        if self.typ in COST_CELLS and node['text'].get('tabSize') == 8.0 and node.get('mats'): node['tint'] = tuple(node['mats'][0]['color'][:3]) + (1.0,)          # (the prefab's green)
        if self.typ in MUTED_COSTS and node['text'].get('tabSize') == 8.0: node['mute'] = True          # (not drawn)
        elif self.typ in MUTED_COSTS and node['text'].get('anchor') == 4: node['ink_center'] = True          # (the name alone, its letters in the middle of the plate)
        s = expand_tabs(s, node['text'].get('tabSize'))                              # see expand_tabs: all the cells at tabSize (types 8, 20, 31, 33, 34, 35, 39), no longer just the spell list
        node['text']['text'] = s; node['was_seen'] = True

    def reactivate(self):
        """MenuPortItem.NoticeReceive, first command after a stop (or the creation): `m_objectActive` false -> every part of `m_partsList` SetActive(true) (RVA 0xD061D8). The parts the
        engine hides with an "active" code (SetItemCode: a target list's unused rows) are shown again; the codes that follow hide what they must. Without this, a row the engine
        hid once stayed hidden: the engine fills the bag's row of the transfer targets (type 5) without ever sending its code, and "Bag" was missing after a transfer from the bag
        (or after loading a savestate taken then)."""
        for es in self.codes.values():
            for e in es:
                if e['kind'] == 'active':
                    pt = self.parts[e['parts']]
                    if pt['node'] in self.N: self.N[pt['node']]['act'] = True

    def code(self, i, c):
        self.vals_code[i] = c
        if self.church and i == 0: self._church(c)
        elif self.status: self._status(i, c)
        elif self.names and i == 4: self._reset_marks()
        elif self.begin and i == 3: self._start(c)
        elif getattr(self, 'is_name_list', False) and i == 6: self._name_entries(c); return      # (getattr: the tests build fake Window objects without this attribute)
        elif getattr(self, 'pictures', None) and i in (0, 1): self._picture(i, c); return
        for e in self.codes.get(i, []):
            if e['kind'] == 'active':
                pt = self.parts[e['parts']]
                if pt['node'] in self.N: self.N[pt['node']]['act'] = (c != 0)
            elif e['kind'] == 'func':
                fx = (e.get('fx') or {}).get(str(c))
                if not fx: self._mask_code(e, c); continue
                moved = {int(n) for v in e['fx'].values() for n, dd in v['d'].items() if 'pos' in dd}
                for nid in moved:                   # a node another value of this code moves goes back to its prefab place when this value says nothing of it (the list's ▲ after a short page)
                    node = self.N.get(nid)
                    if node is not None and str(nid) not in fx['d'] and 'pos0' in node: node['pos'] = list(node['pos0'])
                for nid, dd in fx['d'].items():
                    node = self.N.get(int(nid))
                    if not node: continue
                    if 'pos' in dd: node.setdefault('pos0', list(node['pos'])); node['pos'] = list(dd['pos'])
                    if 'act' in dd: node['act'] = bool(dd['act'])
                cache = {int(n) for v in e['fx'].values() for n, dd in v['d'].items() if dd.get('act') is False}
                for nid in cache:                   # an element that other codes hide is visible for this one if it does not hide it
                    if str(nid) not in fx['d'] and nid in self.N: self.N[nid]['act'] = True
                for t in fx.get('tc', []):          # MenuParts.SetTextColor(code): color of the texts marked by the mask
                    pt = self.parts[t['parts']] if t.get('parts') is not None else None
                    if pt:
                        for j, ib in enumerate(pt['ib']):
                            if (t['mask'] >> j) & 1 and ib['k'] == 'text' and ib.get('go') in self.N: self.N[ib['go']]['tcol'] = t['color']

    def _picture(self, i, c):
        """Picture windows (PICTURE_WINDOWS). Code 0: the picture is created once (a later value changes nothing); code 1 (DQ VI): its opacity, value / 31."""
        node = self.N.get('picture')
        if i == 0 and node is None:
            c &= 0xffff
            if self.picture_index:
                if c >= len(self.pictures): return                      # (the game's array has no such picture)
                name_str = self.pictures[c]
            else: name_str = self.pictures[0 if c == 0 else 1]
            self.N['picture'] = dict(id='picture', par=None, pos=[0.0, 0.0, 0.0], act=True, mats=[dict(sheet='pic:' + name_str, part=None, color=[1.0, 1.0, 1.0, 1.0], shader=None, offset=None)],
                                     vtx=[[-225.0, 168.75], [225.0, 168.75], [225.0, -168.75], [-225.0, -168.75]], uv=[[0.0, 1.0], [1.0, 1.0], [1.0, 0.25], [0.0, 0.25]], sub={'0': [0, 1, 3, 3, 1, 2]},          # (MeshMaker.SetUV(0, 1 - 0.75, 1, 1): the top three quarters of the 256 x 256 texture)
                                     text=None, buttonId=None, pad=0, state=0, tcol=0, tscale=1.0)
        elif i == 1 and node is not None and self.picture_index: node['mats'][0]['color'][3] = c / 31.0

    def _name_entries(self, c):
        """Make_NameButton, code 6 (`<Make_NameButton>b__0`): list layout. The `c` preset (NAMES_PRESETS) gives the number of visible rows and the vertical coordinate of the first one: the following rows (up to the 6th) are disabled, so neither
        drawn nor clickable (the 5th row, empty, stayed visible and led, on touch, to a nonexistent spell: <ERR ...> on screen). The row codes (0 hidden, 1 / 2 visible) arrive afterwards and take priority."""
        if not isinstance(c, int) or not 0 <= c < len(NAMES_PRESETS) or len(self.parts) < 7: return
        num, initial, step = NAMES_PRESETS[c]
        for k in range(6):
            nid = self.parts[1 + k]['node']; root = self.N.get(nid)
            if root is None: continue
            root['act'] = k < num and self.vals_code.get(k) != 0        # (replay of a window: the row's code may already be known)
            dz = (initial - step * k) - (NAMES_START - NAMES_STEP * k)                   # desired offset of row k (the game places the plate, its texts follow it)
            d = dz - self.names_offset.get(k, 0.0)
            if abs(d) > 1e-6:
                for node in self.N.values():
                    x = node; lineage = False
                    while x is not None:
                        if x['id'] == nid: lineage = True; break
                        x = self.N.get(x['par'])
                    if lineage: node['pos'][2] += d
                self.names_offset[k] = dz

    def _mask_code(self, e, c):
        """Code function whose argument is a BIT MASK over active / inactive elements (Make_Casino_Poker b__1: bit n = touch zone number n, cards 0 to 4 and "Donner" 5; the engine sends 63 for all of them).
        The layout exporter only tried the values 0 to 5: the `fx` array ignores the others. If the array does have this shape (for EVERY known value, the inactive elements are exactly those whose bit
        for their button number is 0, among those that value 0 disables), the same rule is applied to the received value: the element with button number n is active when bit n is 1. Otherwise no change (as before)."""
        fxs = e.get('fx') or {}
        ok = e.get('_masque')
        if ok is None:
            ok = e['_masque'] = False
            try:
                zero = {int(n) for n, dd in (fxs.get('0') or {}).get('d', {}).items() if dd.get('act') is False}
                bid = {n: self.N[n]['buttonId'] for n in zero if n in self.N and self.N[n]['buttonId'] is not None and self.N[n]['buttonId'] >= 0}
                if zero and len(bid) == len(zero) and len(set(bid.values())) == len(bid):
                    ok = True
                    for k, v in fxs.items():
                        if k.lstrip('-').isdigit() and int(k) >= 0:
                            off = {int(n) for n, dd in (v.get('d') or {}).items() if dd.get('act') is False}
                            if off != {n for n in zero if not (int(k) >> bid[n]) & 1}: ok = False; break
                    e['_masque'] = ok; e['_masque_ids'] = bid if ok else None
            except Exception: ok = e['_masque'] = False
        if not ok or not isinstance(c, int) or c < 0: return
        for n, b in e['_masque_ids'].items():
            if n in self.N: self.N[n]['act'] = bool((c >> b) & 1)

    # ---- church (type 66, Make_ChurchRoot)
    # The game makes the buttons in the window's code (Sub_ShopButton): the layout exporter only sees the title and the exit button ("Rien"). They are rebuilt here
    # from the code received from the engine (0: five buttons, otherwise four): (x, z from the bottom of the screen, width without the borders); nine-slice mesh of
    # the exit plate, button n = number n, gamepad 16 (confirm).
    CHURCH = {True: ((-111.5, 170.75, 177.1), (111.5, 170.75, 177.1), (-145.0, 106.25, 110.0), (0.0, 106.25, 110.0), (145.0, 106.25, 110.0)),
              False: ((0.0, 170.75, 177.1), (-145.0, 106.25, 110.0), (0.0, 106.25, 110.0), (145.0, 106.25, 110.0))}

    def _church(self, c):
        for n in self.eg_ids: self.N.pop(n, None)
        self.eg_ids = []; del self.parts[self.n_parts:]
        tpl = next((n for n in self.N.values() if n['vtx'] and n['mats'] and n['mats'][0].get('part') == 7 and n['buttonId'] is not None), None)      # existing button plate: the exit ("Rien", gamepad 32)
        label = next((n for n in self.N.values() if tpl and n['par'] == tpl['id'] and n['text'] is not None), None)
        pt0 = next((pt for pt in self.parts if tpl and pt['node'] == tpl['id']), None)
        if tpl is None or label is None or pt0 is None: return
        ax = sorted({abs(v[0]) for v in tpl['vtx']})
        if len(ax) < 2: return
        inside, outside = ax[-2], ax[-1]; nid = max(self.N) + 1
        for no, (x, z, wid) in enumerate(self.CHURCH[c == 0]):
            vtx = [[math.copysign(wid / 2 + (outside - inside) if abs(abs(v[0]) - outside) < 1e-3 else wid / 2, v[0]), v[1]] for v in tpl['vtx']]
            bid, tid = nid, nid + 1; nid += 2; z -= 400.0
            self.N[bid] = dict(id=bid, par=tpl['par'], pos=[x, tpl['pos'][1], z], act=True, mats=[dict(m) for m in tpl['mats']], vtx=vtx, uv=[list(u) for u in tpl['uv']], sub=tpl['sub'], text=None, buttonId=no, pad=0x10, state=0, tcol=0, tscale=1.0)
            self.N[tid] = dict(id=tid, par=bid, pos=[x + label['pos'][0] - tpl['pos'][0], label['pos'][1], z + label['pos'][2] - tpl['pos'][2]], act=True, mats=[dict(m) for m in label['mats']], vtx=None, uv=None, sub=None, text=dict(label['text']), buttonId=None, pad=0, state=0, tcol=0, tscale=1.0)
            self.eg_ids += [bid, tid]
            self.parts.append(dict(node=bid, ib=[dict(ib, go=tid) if ib['k'] == 'text' else dict(ib) for ib in pt0['ib']]))
            tb = next((j for j, ib in enumerate(self.parts[-1]['ib']) if ib['k'] == 'text'), None)
            if tb is None: continue
            self.params[(no, 0)] = dict(id=no, no=0, parts=len(self.parts) - 1, base=tb)         # replaces the exported bindings (parts absent from the layout)
            if (no, 0) in self.church_texts: self.param_str(no, 0, self.church_texts[(no, 0)])

    # ---- battle: member plates (type 29, Make_BattleUpStatus)
    SHAKE = ((-6, 6), (6, -6), (6, -6), (-6, 6), (6, 6), (-6, -6), (-6, -6), (6, 6))         # MenuMessage.s_shakeTable: offset of each frame, from the last (7) to the first (0); zero sum
    BLINK = 0.7                                                                                # BattleUpCursor.c_waitTime: seconds between the arrow's two tints

    def _icon(self, pt, ib, no):
        """IIcon.Change(no): the four UVs of icon number `no` of the element's sheet."""
        node = self.N.get(pt['node'])
        if node and node['uv']:
            for j, uv in enumerate(uv_icon(self.ml.info[ib['partsNo']], no, 0)):
                if ib['vtx'] + j < len(node['uv']): node['uv'][ib['vtx'] + j] = list(uv)

    def _member_root(self, i):
        """Node of the plate of member i (the one that code -1 hides), or None."""
        for e in self.codes.get(i, []):
            if e['kind'] == 'func' and 'Sub_BattleUpStatus' in (e.get('method') or ''):
                k = next(iter((((e.get('fx') or {}).get('-1') or {}).get('d') or {})), None)
                if k is not None and int(k) in self.N: return int(k)
        return None

    def _status(self, i, c):
        """Ids 0 to 3 = plates: code 8 starts ShakeFrame (m_shake = 8), code -1 hides the plate. Id 5 = arrow of the member who is acting: a code >= 0 shows it (SetActive), moves it, and BattleUpCursor.ForceUpdate sets it back to icon 2."""
        if i == 5:
            if c >= 0: self.t_cursor = time.monotonic(); self._cursor_icon(2, True)
            return
        rid = self._member_root(i)
        if rid is None: return
        if c == 8:
            sec = self.shake.get(i)
            if sec is None:                                   # the whole plate moves: its root, its texts, its bar, its face
                every = {rid}; added = True
                while added:
                    added = False
                    for node in self.N.values():
                        if node['par'] in every and node['id'] not in every: every.add(node['id']); added = True
                sec = self.shake[i] = dict(base={n: list(self.N[n]['pos']) for n in every}, dx=0.0, dz=0.0)
            sec['m'] = 8
        elif c < 0: self._end_shake(i, False)

    def _end_shake(self, i, red):
        """End of ShakeFrame: the plate returns to its place; red: m_shakeEndCallback = BattleBar.RedApply (the red bar catches up with the current value)."""
        sec = self.shake.pop(i, None)
        if sec is None: return
        for n, b in sec['base'].items():
            if n in self.N: self.N[n]['pos'][0] = b[0]; self.N[n]['pos'][2] = b[2]
        if red: self.param_str(i, 5, '')

    def _cursor_icon(self, no, reveal=False):
        """Icon of the target arrow (sheet 10); reveal: SetActive(true) of code >= 0 (the exporter does not see it: the code only moves it, the arrow stayed hidden)."""
        for pt in self.parts:
            for ib in pt['ib']:
                if ib['k'] == 'icon' and ib.get('partsNo') == 10:
                    self._icon(pt, ib, no); self.n_cursor = no
                    if pt['node'] in self.N: self.N[pt['node']]['up_cursor'] = True          # (the arrow of the member who is choosing, see Render.hide_up_cursor)
                    if reveal and pt['node'] in self.N: self.N[pt['node']]['act'] = True
                    return

    def tick(self, t=None):
        """One game frame (30 Hz): plate shake (ShakeFrame.Update: one offset from the table per frame, then the red of the bar); the target arrow blinks in real time (BattleUpCursor.Update)."""
        for i in list(self.shake):
            sec = self.shake[i]; sec['m'] -= 1
            dx, dz = self.SHAKE[sec['m']]; sec['dx'] += dx; sec['dz'] += dz
            for n, b in sec['base'].items():
                if n in self.N: self.N[n]['pos'][0] = b[0] + sec['dx']; self.N[n]['pos'][2] = b[2] + sec['dz']
            if sec['m'] == 0: self._end_shake(i, True)
        if self.t_cursor is not None:
            no = 2 + int(((time.monotonic() if t is None else t) - self.t_cursor) / self.BLINK) % 2
            if no != getattr(self, 'n_cursor', 2): self._cursor_icon(no)

    # ---- status icons (MenuPortItemTable.StatusIconChanger)
    def _status_icon(self, i, v):
        """StatusIconChanger: v = icon | (color << 16). The first icon (sheet 13) takes `v & 3` (0 nothing, 1 cross = dead, 2 skull = poison), the second the eye (3) if bit 2 is set (spell sealed);
        the color (header palette: white, yellow = at death's door, red = dead) tints the material of this sheet. i = index of the part that carries two icons of sheet 13."""
        pts = [pt for pt in self.parts if sum(1 for ib in pt['ib'] if ib['k'] == 'icon' and ib.get('partsNo') == 13) == 2]
        if not 0 <= i < len(pts): return
        pt = pts[i]; i1, i2 = [ib for ib in pt['ib'] if ib['k'] == 'icon' and ib.get('partsNo') == 13]
        self._icon(pt, i1, v & 3); self._icon(pt, i2, ((v >> 2) & 1) * 3)
        node = self.N.get(pt['node']); cs = self.ml.colors; c = (v >> 16) & 0xffff
        if node and c < len(cs):
            for m in node['mats']:
                if m.get('part') == 13: m['color'] = list(cs[c])

    # ---- battle: group marks under the monsters (MonsterMarkList, type 31)
    def _marks(self):
        """The 12 marks of type 31: parts of a single icon of sheet 6 (Button), in the order of the parts."""
        return [self.N[pt['node']] for pt in self.parts if len(pt['ib']) == 1 and pt['ib'][0]['k'] == 'icon' and pt['ib'][0].get('partsNo') == 6 and pt['node'] in self.N]

    def _reset_marks(self):
        """MonsterMarkList.Reset (code 4): all marks are hidden."""
        for node in self._marks(): node['act'] = False

    # ---- start menu (type 54, Make_StartMenuSelect)
    START_FRAME = 0xEF if GM.profile().key == 'dq6' else 0xDB          # IFrame.Change(START_FRAME + code): DQ IV and V 219 to 221, DQ VI 239 to 241 (its frames are numbered further on)

    def _start(self, c):
        """Code 3: IFrame.Change(START_FRAME + code) chooses the frame (DQ IV: 219: 316 high, 220: 262, 221: 260); code 2: a single button, lower down, the other two hidden."""
        if not 0 <= c <= 2: return
        border_part = next((ib for pt in self.parts for ib in pt['ib'] if ib['k'] == 'frame'), None)
        if border_part is not None: self._border(border_part, self.START_FRAME + c); TEXT_CENTERING and self._tab_title(border_part, c)
        bt = sorted((n for n in self.N.values() if n['buttonId'] is not None and n['buttonId'] >= 0 and n['pad'] == 0x10 and n['mats'] and n['mats'][0].get('part') == 7), key=lambda n: n['buttonId'])
        if not bt: return
        for node in self.N.values():
            if node['par'] is not None and '_z0' not in node: node['_z0'] = node['pos'][2]
        dz = (-266.25 - bt[0]['_z0']) if c == 2 else 0.0                     # the first button (and its texts) goes down to 135.75 from the bottom of the screen
        for node in self.N.values():
            if node['id'] == bt[0]['id'] or node['par'] == bt[0]['id']: node['pos'][2] = node['_z0'] + dz
        for node in bt[1:]: node['act'] = (c != 2)

    def _tab_title(self, border_part, c):
        """Title of type 54: the text is placed for frame 219 (tab 241.5 wide, 316 high); frames 220 (no tab) and 221 (tab 301.5 wide, 260 high) change the height
        and the width of the tab: the title follows it (at the bottom: the height lost; at the center: half the width gained), otherwise it floats above the tab ("Resume" / "Auto" list).
        Port choice: the original code (0xD0A604) only moves the buttons, but the text sent to code 2 is indeed the tab title."""
        tx = next((n for n in self.N.values() if n['par'] == border_part.get('go') and n['text'] is not None), None)
        if tx is None: return
        if '_x0' not in tx: tx['_x0'] = tx['pos'][0]; tx['_z0'] = tx['pos'][2]
        def tab(v):
            if not 0 <= v < len(self.ml.borders): return None
            vt = self.ml.borders[v]['vtx']; h = max(p[1] for p in vt); xs = [p[0] for p in vt if p[1] >= h - 12.5]
            return (h, max(xs)) if max(xs) < 400.0 else None             # no tab: full width
        o0, oc = tab(self.START_FRAME), tab(self.START_FRAME + c)
        if o0 is None or oc is None: return
        tx['pos'][0] = tx['_x0'] + (oc[1] - o0[1]) / 2.0; tx['pos'][2] = tx['_z0'] + (oc[0] - o0[0])

    def selection(self, button):
        """Chosen button (cursor): the elements with this number switch to the "pressed" state."""
        self.selected = button

    # ---- monster name plates (MenuPortItemTable.MonsterNamePlate, type 31)
    def _plate_nodes(self, i):
        for e in self.codes.get(i, []):
            fx = e.get('fx') or {}
            border = next(iter(((fx.get('-1') or {}).get('d') or {}).keys()), None)
            text = next(iter(((fx.get('1') or {}).get('d') or {}).keys()), None)
            if border is not None and text is not None: return int(border), int(text)
        return None, None

    def plate(self, i, name_str, prm, code):
        """ReceiveParameters(code >= 1): monster name, window fitted to one or two lines (VariableWindow 142 x 18 or 36), mask of the monsters in the group."""
        border, text = self._plate_nodes(i)
        if border is None or border not in self.N or text not in self.N: return
        pl = getattr(self, 'pl', None)
        if pl is None: pl = self.pl = {}
        nc = self.N[border]
        if 'base_vtx' not in nc: nc['base_vtx'] = [list(v) for v in nc['vtx']]; pl_off = [a - b for a, b in zip(self.N[text]['pos'], nc['pos'])]; nc['off_text'] = pl_off
        if name_str[:1] == '^' and len(name_str) >= 2: name_str = name_str[2:]                    # color mark: removed by the plate
        two = '\n' in name_str
        nc['vtx'] = [[x, z if two else (z - 9.0 if z > 0 else z + 9.0)] for x, z in nc['base_vtx']]       # window from 36 -> 18 high: top/bottom lines moved closer to the center
        nt = self.N[text]; nt['text']['text'] = expand_tabs(name_str, nt['text'].get('tabSize')); nt['was_seen'] = True; nt['tcol'] = 0        # "nom \n \t×N": the tab (tabSize 25) pushes "×N" toward the right edge of the plate
        mask = (prm[4] & 0xffff if len(prm) > 4 else 0) | ((prm[5] & 0xffff) << 16 if len(prm) > 5 else 0)
        pl[i] = dict(frame=border, text=text, mask=mask, code=code, two=two)
        nc['act'] = True

    def arrange(self, n, proj):
        """b__1(code = number of plates): x = center of the group's monsters (clamped to +-142), z = 105 (69 if more than two plates), rows of 58 going up; plates of the same row that
        overlap are then moved apart (separate_plates)."""
        pl = getattr(self, 'pl', {})
        lst = [i for i in range(min(n, 4)) if i in pl]
        xs = {}
        for i in lst:
            b = proj(pl[i]['mask']) if proj else None
            xs[i] = (b[0] + b[1]) / 2 if b else 0.0
        zs = {i: (69.0 if n > 2 else 105.0) for i in lst}
        xs = {i: min(max(xs[i], -142.0), 142.0) for i in lst}
        order = lst
        if n > 2:
            order = sorted(lst, key=lambda i: xs[i])
            for k, i in enumerate(order):
                if 1 <= k <= n - 2: zs[i] += 58.0
        separate_plates(order, xs, zs)
        for i in lst:
            d = pl[i]; x = xs[i]; z = zs[i]
            nc, nt = self.N[d['frame']], self.N[d['text']]
            nc['pos'] = [x, nc['pos'][1], z]; off = nc.get('off_text', [0, 0, 0]); nt['pos'] = [x + off[0], nt['pos'][1], z + off[2]]
        self._reset_marks(); marks = self._marks(); k = 0
        for i in lst:                                                       # MonsterMarkList.SetMark: target choice (code 2) = a mark of the plate's color under each monster of the group, at the monster's x, z = -64
            if pl[i]['code'] != 2 or not proj: continue
            for x in (proj(pl[i]['mask'], True) or []):
                if k >= len(marks): break
                node = marks[k]; k += 1; node['pos'] = [x, 0.0, -64.0]; node['act'] = True
                for j, uv in enumerate(uv_icon(self.ml.info[6], 5 + i, 0)): node['uv'][j] = list(uv)

    def buttons(self, ident=False):
        """Touch zones (MenuParts of a button: number, gamepad key sent to the engine on release): [(number, gamepad, x0, z0, x1, z1, depth)] in interface units; ident: the element's identifier is appended at the end of the tuple."""
        out = []
        for node in self.N.values():
            if not node['pad'] or node['buttonId'] is None or not node['vtx'] or not is_state_active(node['state']) or not self.visible(node['id']): continue
            xs = [node['pos'][0] + v[0] for v in node['vtx']]; zs = [node['pos'][2] + v[1] for v in node['vtx']]
            out.append((node['buttonId'], node['pad'], min(xs), min(zs), max(xs), max(zs), node['pos'][1]) + ((node['id'],) if ident else ()))
        return out

    def bottom(self):
        """Vertical coordinate (interface units) of the bottom edge of the window's visible parts."""
        zs = [node['pos'][2] + v[1] for node in self.N.values() if node['vtx'] and node['mats'] and not node.get('marque') and self.visible(node['id']) for v in node['vtx']]
        return min(zs) if zs else 0.0

    def extent(self):
        """(bottom, top) in interface units of the window's visible parts, or None if nothing is drawn."""
        zs = [node['pos'][2] + v[1] for node in self.N.values() if node['vtx'] and node['mats'] and not node.get('marque') and self.visible(node['id']) for v in node['vtx']]
        return (min(zs), max(zs)) if zs else None

    def visible_extent(self):
        """(x0, x1, z0, z1) of the VISIBLE drawing of the window's shown parts, in interface units (see `visible_edges`: the transparent margins of the frames do not count); the mesh cell edges when the sheet is not known. None if nothing is drawn."""
        r = None
        for node in self.N.values():
            if not (node['vtx'] and node['mats'] and not node.get('marque') and self.visible(node['id'])): continue
            lookup_key = (id(node['vtx']), len(node['vtx']), node['mats'][0].get('sheet'))
            if node.get('_vis_key') != lookup_key:
                al = SHEET_ALPHA.get(node['mats'][0].get('sheet')); sub = (node.get('sub') or {}).get('0')
                node['_vis_key'] = lookup_key; node['_vis'] = (visible_edges(node['vtx'], node['uv'], sub, al) if (al is not None and sub and node['uv']) else None) or (min(v[0] for v in node['vtx']), max(v[0] for v in node['vtx']), min(v[1] for v in node['vtx']), max(v[1] for v in node['vtx']))
            b = node['_vis']; b = (node['pos'][0] + b[0], node['pos'][0] + b[1], node['pos'][2] + b[2], node['pos'][2] + b[3])
            r = b if r is None else (min(r[0], b[0]), max(r[1], b[1]), min(r[2], b[2]), max(r[3], b[3]))
        return r

    def rects(self):
        """Rectangles (x0, z0, x1, z1) of the window's drawn elements (visible, with a mesh): the frames and the plates."""
        out = []
        for node in self.N.values():
            if node['vtx'] and node['mats'] and not node.get('marque') and self.visible(node['id']):
                xs = [node['pos'][0] + v[0] for v in node['vtx']]; zs = [node['pos'][2] + v[1] for v in node['vtx']]
                out.append((min(xs), min(zs), max(xs), max(zs)))
        return out

    def center_menu(self):
        """Start menu (type 53): the game sticks its buttons to the bottom edge of the portrait screen; the viewer centers them vertically (the whole group: "Sauvegarde automatique", the four choices, "License", "Saves", back)
        in a black frame. The offset is computed on the complete layout (visible or not) so that the group does not move when a button appears or disappears. -> offset applied (units)."""
        for node in self.N.values():
            if '_zc' not in node: node['_zc'] = node['pos'][2]
        zs = [node['_zc'] + v[1] for node in self.N.values() if node['vtx'] and node['mats'] for v in node['vtx']]
        if not zs: return 0.0
        dz = -(min(zs) + max(zs)) / 2.0
        for node in self.N.values(): node['pos'][2] = node['_zc'] + dz
        return dz

    def _plate(self, button):
        return next((n for n in self.N.values() if n['buttonId'] == button and n['mats'] and n['mats'][0].get('part') == 7 and n['vtx']), None)

    def _add_language_plate(self):
        """a plate of the port between "License" and "Saves" (the gap the game leaves there), built like "License" (the same 9-slice plate, narrower) with a globe on it (second
        material, sheet 'globe', drawn by the viewer: flags.globe). Number LANGUAGE_BUTTON: hovered, pressed and reached with the keys like the game's plates; the viewer intercepts it (the engine never
        receives it) and opens its language screen. -> the node, or None if the layout has no "License" or "Saves"."""
        left, right = self._plate(LICENSE_BUTTON), self._plate(8)
        if left is None or right is None: return None
        x0 = left['pos'][0] + max(v[0] for v in left['vtx']); x1 = right['pos'][0] + min(v[0] for v in right['vtx'])
        half = min(36.0, (x1 - x0) / 2.0 - 8.0); edge = max(abs(v[0]) for v in left['vtx']); corner = edge - min(abs(v[0]) for v in left['vtx'])
        if half < corner + 4.0: return None
        vtx = [[(half if abs(v[0]) > edge - 0.5 else half - corner) * (1.0 if v[0] > 0 else -1.0), v[1]] for v in left['vtx']]
        n = len(vtx); fw, fh = 14.0, 14.0; du, dv = 0.5 / GLOBE_PX, 0.5 / GLOBE_PX
        vtx += [[-fw, fh], [fw, fh], [fw, -fh], [-fw, -fh]]
        uv = [list(u) for u in left['uv']] + [[du, -dv], [1.0 - du, -dv], [1.0 - du, -1.0 + dv], [du, -1.0 + dv]]
        sub = {'0': list(left['sub']['0']), '1': [n, n + 1, n + 3, n + 3, n + 1, n + 2]}
        nid = max(self.N) + 1000
        self.N[nid] = dict(id=nid, par=left['par'], pos=[(x0 + x1) / 2.0, left['pos'][1], left['pos'][2]], act=True, mats=[dict(left['mats'][0]), dict(sheet='globe', part=None, color=[1.0, 1.0, 1.0, 1.0], shader='parts', offset=None)],
                           vtx=vtx, uv=uv, sub=sub, text=None, buttonId=LANGUAGE_BUTTON, pad=16, state=STATE_NORMAL, tcol=0, tscale=1.0)
        return self.N[nid]

    def set_language_globe(self, available):
        """The globe of the language plate; grayed (gray shader, no hover or confirmation) when the other language's APK files are missing: there is nothing to choose."""
        pl = getattr(self, 'language_plate', None)
        if pl is None: return
        pl['state'] = STATE_NORMAL if available else STATE_GRAYED
        pl['mats'][1]['color'] = [1.0, 1.0, 1.0, 1.0] if available else [0.45, 0.45, 0.45, 1.0]          # (the gray shader only touches the plate: the globe is dimmed with it)

    def gray_texts(self):
        """Gray text (TEXT_COLOR_GRAY) on the grayed button plates (state 3), white again when they no longer are. The game's gray shader only removes the color: on the gray plate of the start menu
        the difference is barely visible; the gray text shows that it is inactive (viewer's choice: the game itself only changes the text color for the buttons that asked for it)."""
        for pl in self.N.values():
            if pl['buttonId'] is None or not pl['mats'] or pl['mats'][0].get('part') != 7: continue
            for t in self.N.values():
                if t['par'] != pl['id'] or t['text'] is None: continue
                if pl['state'] == STATE_GRAYED: t['tcol'] = TEXT_GRAY; t['_gray'] = True
                elif t.pop('_gray', False): t['tcol'] = 0

    def auto_plate(self, button=AUTO_BUTTON, label_text=AUTO_CAPTION):
        """Start menu: "Sauvegarde automatique" plate (see _auto_plate) then gray text of the grayed plates."""
        self._auto_plate(button, label_text); self.gray_texts()

    def _auto_plate(self, button=AUTO_BUTTON, label_text=AUTO_CAPTION):
        """Start menu (type 53): the "Sauvegarde automatique" plate ALWAYS stays visible, with its label; without an auto-save it is grayed (state 3: gray shader) and thus inactive (`is_state_active`: no hover, no click,
        no keyboard confirmation; the engine, which has no cell 4 in this case, receives nothing). The original game, on the other hand, HIDES this plate (code 0 = 0: frame 215 / 216 then SetActive(false)); the user's request
        (grayed, never gone) takes precedence. With DQ_AUTO_HIDDEN: original behavior. Idempotent (called every frame)."""
        pl = next((n for n in self.N.values() if n['buttonId'] == button and n['mats'] and n['mats'][0].get('part') == 7 and n['vtx']), None)
        if pl is None: return
        tx = [n for n in self.N.values() if n['par'] == pl['id'] and n['text'] is not None]
        tag_label = ' '.join((n['text'].get('text') or '').strip() for n in tx).strip()
        if self.auto_grayed and tag_label == label_text: tag_label = ''                  # the port's replacement label is not the engine's (counts only as long as code 0 is missing)
        if auto_plate_available(self.vals_code.get(0), tag_label):
            if self.auto_grayed: self.auto_grayed = False; self.param_int(button, 0, STATE_NORMAL)         # the auto save has appeared: normal plate (the engine gives the label)
            pl['act'] = True; pl.pop('_vide', None); return
        if os.environ.get('DQ_AUTO_HIDDEN'): pl['act'] = False; pl['_vide'] = True; return           # (comparison) like the original game: plate hidden
        pl['act'] = True; pl.pop('_vide', None)
        if not self.auto_grayed or not tag_label: self.param_str(button, 1, label_text)
        self.auto_grayed = True; self.param_int(button, 0, STATE_GRAYED)

    def menu_border(self, margin=22.0, visible_ones=False):
        """Rectangle (x0, z0, x1, z1) of the whole layout (plates, buttons), enlarged by `margin`: the black frame of the start menu; `visible_ones`: only the shown elements (adventure log lists: the frame changes height)."""
        node_list = [node for node in self.N.values() if node['vtx'] and node['mats'] and (not visible_ones or self.visible(node['id']))]
        xs = [node['pos'][0] + v[0] for node in node_list for v in node['vtx']]
        zs = [node['pos'][2] + v[1] for node in node_list for v in node['vtx']]
        return (min(xs) - margin, min(zs) - margin, max(xs) + margin, max(zs) + margin) if xs else None

    def center_visible(self):
        """(x, z) of the center of what the window shows (frame, tab, plates, back button), in interface units; None if nothing. The pre-game windows (adventure log list, gender choice) are placed on the bottom-right edge
        of the portrait screen: the viewer centers them (through the drawing coordinate system, without touching the positions)."""
        r = self.menu_border(0.0, True)
        return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0) if r else None

    def extent_x(self):
        """(left, right) in interface units of all the window's parts (visible or not: the layout does not change), or None: limits within which a text must fit. Cached."""
        c = getattr(self, '_ex_cache', None)
        if c is None:
            xs = [node['pos'][0] + v[0] for node in self.N.values() if node['vtx'] and node['mats'] for v in node['vtx']]
            c = self._ex_cache = ((min(xs), max(xs)) if xs else None,)
        return c[0]

    YES_NO_SPACING = 1.0                       # gap between the two stacked plates (the one that separated the two side-by-side plates: from -0.5 to +0.5)

    def _seven_gifts(self):
        """Make_Casino_GiftList with MenuPortItem.s_shopType 6 or 13 (the engine's code 14; DQ V's prize counter): 7 rows 50 units apart from z 398 instead of 6 rows 58 apart from 393 (the
        exported layout), and the prices' text (right-aligned, one line per row) under number 7, 3 units higher, line spacing 2.65 instead of 3.07. The 7th row is a copy of the 6th."""
        rows = [pt for pt in self.parts[1:7]]
        if len(rows) != 6 or any(pt['node'] not in self.N for pt in rows): return
        def subtree(r):
            out = [r]; k = 0
            while k < len(out):
                out += [n['id'] for n in self.N.values() if n['par'] == out[k] and n['id'] not in out]; k += 1
            return out
        z0 = self.N[rows[0]['node']]['pos'][2]                               # (first row: z 393 of the column, -7 in the window)
        nid = max(k for k in self.N if isinstance(k, int)) + 1; mapping = {}
        for old in subtree(rows[5]['node']):
            n = self.N[old]; mapping[old] = nid; nid += 1
            self.N[mapping[old]] = dict(n, id=mapping[old], par=mapping.get(n['par'], n['par']), pos=list(n['pos']), mats=[dict(m) for m in n['mats']],
                                        uv=[list(u) for u in n['uv']] if n['uv'] else n['uv'], text=dict(n['text']) if n['text'] is not None else None)
        self.N[mapping[rows[5]['node']]]['buttonId'] = 6
        new = dict(rows[5], node=mapping[rows[5]['node']], ib=[dict(ib, go=mapping.get(ib.get('go'), ib.get('go'))) if 'go' in ib else dict(ib) for ib in rows[5]['ib']])
        self.parts.insert(7, new); j_new = 7
        for (i, no), p in list(self.params.items()):                         # (the back button's part moves to 8)
            if p.get('parts') is not None and p['parts'] >= 7: self.params[(i, no)] = dict(p, parts=p['parts'] + 1)
        for k, r in enumerate([pt['node'] for pt in rows] + [new['node']]):
            src = rows[min(k, 5)]['node']; dz = (z0 + 5.0 - 50.0 * k) - self.N[src]['pos'][2] if k < 6 else (z0 + 5.0 - 300.0) - (z0 - 58.0 * 5)
            for n in subtree(r): self.N[n]['pos'][2] += dz
        price = self.params.pop((6, 0), None)
        if price is not None:
            self.params[(7, 0)] = price
            node = self.N.get(self.parts[price['parts']]['ib'][price['base']].get('go'))
            if node and node['text'] is not None: node['pos'][2] += 3.0; node['text']['lineSpacing'] *= 2.65 / 3.07
        for no, base in ((0, 1), (1, 2), (3, 0)): self.params[(6, no)] = dict(id=6, no=no, parts=j_new, base=base)
        self.t = dict(self.t, codes=list(self.t['codes']) + [dict(id=6, kind='active', parts=j_new)])

    def _push_yes_no(self):
        """Yes / No (Make_YesNo, type 1): on mobile the two plates of the frame are side by side ("Yes" on the left, "No" on the right, 134 x 48 units each, one unit between them); here they are stacked,
        "Yes" above "No", as on DS (the stack is placed on the top-right corner of the dialogue box, see `Game._ui_yesno`). The stack keeps the column of the left plate
        (x from -134.5 to -0.5); the mesh cells (frame, plate, text) are moved as one block, nothing else changes: the engine's cursor already arranges Yes / No in one column (top = Yes, bottom = No), the touch zones
        and the selection follow the moved nodes. Without two numbered plates (other layout), nothing is changed."""
        plates = sorted((n for n in self.N.values() if n['buttonId'] is not None and n['mats'] and n['mats'][0].get('part') == 7 and n['vtx']), key=lambda n: n['pos'][0])
        if len(plates) != 2 or plates[0]['par'] != plates[1]['par']: return
        border = self.N.get(plates[0]['par'])                                             # the frame (two panels) is the common parent of the two plates
        if border is None or not border['vtx'] or len(border['vtx']) % 4: return
        g, d = plates; dx = g['pos'][0] - d['pos'][0]                                    # horizontal offset: the right plate moves onto the left column
        middle = (g['pos'][0] + d['pos'][0]) / 2.0 - border['pos'][0]                      # boundary between the two panels of the frame (local coordinate frame of the frame)
        quads = [range(i, i + 4) for i in range(0, len(border['vtx']), 4)]
        right = [q for q in quads if sum(border['vtx'][i][0] for i in q) / 4.0 > middle]; left = [q for q in quads if q not in right]
        if not right or not left: return
        zs = [border['vtx'][i][1] for q in left for i in q]; dz = -(max(zs) - min(zs) + self.YES_NO_SPACING)       # the height of one panel + the gap
        for q in right:
            for i in q: border['vtx'][i][0] += dx; border['vtx'][i][1] += dz
        tracked = {d['id']}; changed = True                                                # the right plate and everything descending from it (its text)
        while changed:
            changed = False
            for n in self.N.values():
                if n['id'] not in tracked and n['par'] in tracked: tracked.add(n['id']); changed = True
        for nid in tracked: n = self.N[nid]; n['pos'][0] += dx; n['pos'][2] += dz

    def visible(self, nid):
        while nid is not None:
            node = self.N.get(nid)
            if node is None: return True
            if not node['act']: return False
            nid = node['par']
        return True


BORDER_WITH_NAME = 191                          # frameData of the dialogue frame WITH name tab (192 = without tab: the one of type 0 in ui_layout.json); in each game, the frame just before type 0's (DQ VI: 211, 212)
WHO_POS = (-104.5, 4.0, -104.0)               # MenuMessage.m_who: local position of the name's TextMesh; the height has BIAS_FONT_Y added to it (= lang['dy'], added by Render._text)
WHO_SIZE = 10.0                             # characterSize of the name's TextMesh (that of the dialogues is 10.4975)


class MessageWindow:
    """The game's message window (MenuMessage): frame (frameData) + text canvas drawn by the engine + end-of-page cursor.
    The canvas is a 512 x 512 texture that wraps; the scroll `[3, y]` shifts the vertical origin of its UVs by (y & 0x1ff) / 512."""
    def __init__(self, ml):
        self.ml = ml; self.d = ml.message; self.was_seen = True; self.selected = None; self.selected_node = None; self.order = 0
        self.type = -1; self.y = 0; self.feed = False; self.N = {}; self.who = ''; self.with_name = False; self._base = None
        self.typ = -1; self.t = 0                                    # (for Render._text, which reads these two fields from the menu windows: type number, layout frame)
        try: self.with_name_frame = int(self.d['types'][0]['frame']) - 1
        except Exception: self.with_name_frame = BORDER_WITH_NAME
        self.select_language(0, 0, False)

    @staticmethod
    def _node(nid, pos, vtx, uv, tris, mat):
        return dict(id=nid, par=None, pos=pos, act=True, mats=[mat], vtx=vtx, uv=uv, sub={'0': tris}, text=None, buttonId=None, state=0, tcol=0, tscale=1.0)

    def select_language(self, typ, y, feed, who=''):
        """typ = window type (0 field, 1-3 battle), y = canvas scroll, feed = end-of-page cursor, who = name of the speaker ('': none).
        MenuMessage.NoticeReceive, command 4: the name is shown only on the field window (m_nowType == 0); the frame then becomes frameData 191 (the same as 192 + a tab stuck to the top-left edge, underlined)
        and the TextMesh "m_who" receives the name. The dimensions used to place the window (extent(), bottom()) stay those of the frame without a tab: the tab sticks out upward, it does not shift anything."""
        ts = self.d['types']; t = ts[typ] if 0 <= typ < len(ts) else ts[0]
        fm = self.d.get('frame_mats') or [{'sheet': 0, 'part': 4}]
        who = (who or '').strip(); has_tab = bool(who) and typ == 0 and len(self.ml.borders) > self.with_name_frame
        if typ != self.type or has_tab != self.with_name:
            self.type = typ; self.with_name = has_tab; w = t['win']; cv = t['canvas']; fl = t['feed_local']; fd = self.d['feed']
            fmesh = self._base = t['frame_mesh']
            if has_tab: c = self.ml.borders[self.with_name_frame]; fmesh = dict(vtx=c['vtx'], uv=c['uv'], tris=c['tri'])
            self.N = {
                'frame': self._node('frame', list(w), fmesh['vtx'], fmesh['uv'], fmesh['tris'], dict(sheet=fm[0]['sheet'], part=fm[0]['part'], color=None)),
                'canvas': self._node('canvas', [w[0], w[1] + 4.0, w[2]], [[v[0], v[2]] for v in cv['vtx']], [list(u) for u in cv['uv']], cv['tris'], dict(sheet='msg', color=[1, 1, 1, 1])),
                'cursor': self._node('cursor', [w[0] + fl[0], w[1] + fl[1] + 6.0, w[2] + fl[2]], fd['vtx'], fd['uv'], fd['tris'], dict(sheet=fd['mats'][0]['sheet'], part=fd['mats'][0]['part'], color=None)),
            }
            if has_tab:                                                  # TextMesh "m_who": local position (-104.5; 4; BIAS_FONT_Y - 104), size 10, anchor "top center", centered text, white
                node = self._node('speaker', [w[0] + WHO_POS[0], w[1] + WHO_POS[1], w[2] + WHO_POS[2] + self.ml.hdr['lang']['dy']], [], [], {}, None)
                node['mats'] = []; node['text'] = dict(text=who, characterSize=WHO_SIZE, lineSpacing=1.0, anchor=1, alignment=1, font=0); self.N['speaker'] = node
            self.uv0 = [list(u) for u in cv['uv']]; self._ty = None
        if has_tab: self.N['speaker']['text']['text'] = who
        self.who = who if has_tab else ''; self.t += 1
        self.N['cursor']['act'] = bool(feed); self.feed = bool(feed)
        if y != self.y or typ != getattr(self, '_ty', None):
            self.y = y; self._ty = typ
            dv = (int(y) & 0x1ff) / 512.0
            self.N['canvas']['uv'] = [[u[0], u[1] + dv] for u in self.uv0]

    def visible(self, nid):
        node = self.N.get(nid)
        return bool(node and node['act'])

    def extent(self):
        c = self.N.get('frame')
        if not c or not c['vtx']: return None
        vt = self._base['vtx'] if self.with_name else c['vtx']          # (the name tab does not count: the Yes/No and the scale keep the place of the frame without a tab)
        return (c['pos'][2] + min(v[1] for v in vt), c['pos'][2] + max(v[1] for v in vt))

    def visible_extent(self):
        """(x0, x1, z0, z1) of the VISIBLE drawing of the dialogue frame (without the name tab), in interface units (see `visible_edges`); the mesh cell edges when the sheet is not known."""
        c = self.N.get('frame')
        if not c or not c['vtx']: return None
        b = getattr(self, '_vis', None)
        if b is None or b[0] != (self.type, self.with_name):
            m = self._base if self.with_name else dict(vtx=c['vtx'], uv=c['uv'], tris=(c['sub'] or {}).get('0'))
            al = SHEET_ALPHA.get(c['mats'][0].get('sheet')) if c['mats'] else None
            v = visible_edges(m['vtx'], m['uv'], m['tris'], al) if (al is not None and m.get('tris')) else None
            self._vis = b = ((self.type, self.with_name), v or (min(p[0] for p in m['vtx']), max(p[0] for p in m['vtx']), min(p[1] for p in m['vtx']), max(p[1] for p in m['vtx'])))
        v = b[1]; return (c['pos'][0] + v[0], c['pos'][0] + v[1], c['pos'][2] + v[2], c['pos'][2] + v[3])

    def bottom(self):
        """Vertical coordinate (interface units) of the frame's bottom edge."""
        c = self.N.get('frame')
        return c['pos'][2] + min(v[1] for v in c['vtx']) if c and c['vtx'] else 0.0

    def extent_x(self):
        """(left, right) of the frame, interface units (Render._text: limits within which a text must fit)."""
        c = self.N.get('frame')
        return (c['pos'][0] + min(v[0] for v in c['vtx']), c['pos'][0] + max(v[0] for v in c['vtx'])) if c and c['vtx'] else None

    def rects(self):
        c = self.N.get('frame')
        if not c or not c['vtx']: return []
        return [(c['pos'][0] + min(v[0] for v in c['vtx']), c['pos'][2] + min(v[1] for v in c['vtx']), c['pos'][0] + max(v[0] for v in c['vtx']), c['pos'][2] + max(v[1] for v in c['vtx']))]


class BitmapFont:
    """The game's Unity bitmap font for the English language (and the FR patch): "SE-GARRIR" (Font "Garrick", 20 px, 218 glyphs); it replaces GMaruGoPro-M, the Japanese font.
    The data (ui_garrir.json: metrics and glyph rectangles; ui_garrir.png: 256 x 256 atlas, alpha) are extracted from base.apk by prepare_resources.
    A TextMesh with character size cs displays 1 font px = cs * 0.1 interface unit; the width of a line = the sum of the glyphs' "advance" (no kerning)."""
    PAD = 2                                                       # margin (font px) around a line: some glyphs extend past their "advance" (W, ’, …)
    UP, DOWN = 22, 9                                             # texture rows above / below the baseline

    def __init__(self, json_path, png_path):
        from PIL import Image
        d = json.load(open(json_path, encoding='utf-8'))
        self.leading = d['lineSpacing']; self.ascent = d['ascent']
        atlas = np.asarray(Image.open(png_path).convert('RGBA'))[::-1, :, 3]      # row n = v * 256 (Unity texture coordinates: v = 0 at the bottom)
        self.G = {}
        for code, vx, vy, vw, vh, adv, flip, ux, uy, uw, uh in d['glyphes']:
            c0, c1 = int(round(ux * 256)), int(round((ux + uw) * 256)); ra, rb = int(round(uy * 256)), int(round((uy + uh) * 256))
            b = atlas[min(ra, rb):max(ra, rb), c0:c1]
            if flip: b = b.T[::-1, ::-1]                          # "flipped" glyph: stored transposed in the atlas
            self.G[code] = (int(round(adv)), int(round(vx)), int(round(-vy - self.ascent)), np.ascontiguousarray(b))      # (advance, x offset, top of the glyph relative to the baseline (downward), bitmap)
        for code in '\u00a0\u202f\u2009':                              # no-break space (the FR patch puts one before "!", "?", ":"), thin and narrow: the no-break one had an advance of 11 px (glyph 160), they display as the normal space (5 px), everywhere
            if 32 in self.G: self.G[ord(code)] = self.G[32]
        self.tex = {}; self.wid = {}; self.fallback = None

    def _glyph(self, c):
        g = self.G.get(ord(c))
        if g is not None: return g
        if c < ' ': return (0, 0, 0, np.zeros((0, 0), np.uint8))       # control characters ("\r" at the end of a line): no width or drawing
        return None

    def cap_height(self):
        """Height of the capitals above the baseline, font px (the "H")."""
        g = self.G.get(ord('H'))
        return float(-g[2]) if g else float(self.ascent) * 0.7

    def width_px(self, text):
        """Width of a line in font px (sum of the advances; a character missing from the font counts as a space)."""
        w = self.wid.get(text)
        if w is None:
            w = self.wid[text] = sum((self._glyph(c) or self.G[32])[0] for c in text)
        return w

    def line(self, text):
        """-> (texture, width, height, base) in font px; base = distance from the top of the image to the baseline."""
        r = self.tex.get(text)
        if r is None:
            if len(self.tex) > 800:
                for t, *_ in self.tex.values(): t.delete() if hasattr(t, 'delete') else None
                self.tex.clear()
            W = int(self.width_px(text)) + 2 * self.PAD; H = self.UP + self.DOWN
            a = np.zeros((H, W), np.uint8); x = self.PAD
            for c in text:
                g = self._glyph(c) or self.G[32]
                adv, vx, top, b = g
                if b.size:
                    y0 = self.UP + top; x0 = x + vx; h, w = b.shape
                    sub = a[max(y0, 0):y0 + h, max(x0, 0):x0 + w]
                    bb = b[max(-y0, 0):max(-y0, 0) + sub.shape[0], max(-x0, 0):max(-x0, 0) + sub.shape[1]]
                    sub[...] = np.maximum(sub, bb)
                x += adv
            rgba = np.zeros((H, W, 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = a
            img = pyglet.image.ImageData(W, H, 'RGBA', np.ascontiguousarray(rgba[::-1]).tobytes(), pitch=W * 4)
            t = img.get_texture(); gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)      # bilinear filter, like the game's atlas (Texture2D.filterMode = Bilinear)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            r = self.tex[text] = (t, W, H, self.UP)
        return r


class Texts:
    """Text lines -> textures (the game's font rendered by Pillow, white; the color is applied when drawing)."""
    def __init__(self, font):
        self.font = font; self.pol = {}; self.tex = {}; self.bitmap = None; self.messages = None
        d = os.path.dirname(font); j, g = os.path.join(d, 'ui_garrir.json'), os.path.join(d, 'ui_garrir.png')
        m = os.path.join(d, 'ui_messages.font')                   # the game's message font (that of the engine's text canvas: dialogues and battle), optional: without it the history keeps SE-GARRIR
        if os.path.exists(m) and not os.environ.get('DQ_FONT_GMARU'):
            try:
                from dq456_pc.menus.message_font import MessageFont
                self.messages = MessageFont(m)
            except Exception as e: print('Message font unreadable (%r): using SE-GARRIR instead.' % (e,), flush=True)
        if os.path.exists(j) and os.path.exists(g) and not os.environ.get('DQ_FONT_GMARU'):        # DQ_FONT_GMARU=1 (test): old Japanese font, for comparison
            try: self.bitmap = BitmapFont(j, g)
            except Exception as e: print('SE-GARRIR font unreadable (%r): using the Japanese GMaruGoPro-M font instead.' % (e,), flush=True)
    def _font(self, px):
        from PIL import ImageFont
        f = self.pol.get(px)
        if f is None:
            for path in (self.font, 'DejaVuSans.ttf', 'arial.ttf'):
                try: f = ImageFont.truetype(path, px); break
                except Exception: f = None
            if f is None: f = ImageFont.load_default()
            self.pol[px] = f
        return f
    def line(self, text, px):
        """-> (texture, width, height, base); base = distance from the top of the image to the baseline."""
        k = (text, px)
        r = self.tex.get(k)
        if r is None:
            from PIL import Image, ImageDraw
            if len(self.tex) > 600:
                for t, *_ in self.tex.values(): t.delete() if hasattr(t, 'delete') else None
                self.tex.clear()
            f = self._font(px); asc, desc = f.getmetrics(); w = int(math.ceil(f.getlength(text))) + 4; h = asc + desc + 4
            im = Image.new('L', (w, h), 0); ImageDraw.Draw(im).text((2, 2 + asc), text, font=f, fill=255, anchor='ls')
            a = np.zeros((h, w, 4), np.uint8); a[..., :3] = 255; a[..., 3] = np.asarray(im)
            img = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes(), pitch=w * 4)
            t = img.get_texture(); gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            r = self.tex[k] = (t, w, h, 2 + asc)
        return r


class Render:
    """Draws Window objects on the screen: custom GL program, sheets 0 (MenuTexture) and 1 (Button)."""
    hidden_cells = None                # {window type: (cell numbers)}: cells not drawn for now (the battle replay's action labels); None: all
    hide_up_cursor = False             # the arrow of the member choosing a command (status plates, code 5) is not drawn (battle replay: the command phase is never seen)
    def __init__(self, ml, sheets, font):
        self.ml = ml; self.neighbors = []                      # neighbors: visible windows of the frame (their frames are used to compress the texts of a frameless window, with the fallback font only)
        self.prog = ShaderProgram(Shader(VERTEX, 'vertex'), Shader(FRAG, 'fragment'))
        self._white = None                                  # 1-pixel white texture (solid color squares: world map locations)
        self.tex = {}
        from dq456_pc.world.hd import _dilate
        for k, arr in sheets.items():
            SHEET_ALPHA[k] = np.ascontiguousarray(arr[..., 3])             # (original opacity: visible edges of the frames)
            arr = _dilate(arr, 3)                          # transparent pixels = the color of the neighboring edge (alpha unchanged): the cells of these sheets kept white / pink under their transparent pixels, which linear filtering brought back as a light fringe ("aura") around the icons and portraits
            h, w = arr.shape[:2]
            img = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(arr[::-1]).tobytes(), pitch=w * 4)
            t = img.get_texture(); gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            self.tex[k] = t
        self.texts = Texts(font)

    face_source = None          # called with a portrait name ("f05") -> RGBA array or None (game.py: face_loader)

    picture_source = None       # called with a texture name ("yado_pic") -> RGBA array or None (game.py: the data pack's textures)

    def _load_face(self, sh):
        """Portrait texture "face:fNN" (ITexture) or picture "pic:<name>" (PICTURE_WINDOWS) loaded on first use; False if the game has none by that name."""
        if not isinstance(sh, str): return False
        source = self.face_source if sh.startswith('face:') else self.picture_source if sh.startswith('pic:') else None
        if source is None: return False
        missing = self.__dict__.setdefault('_no_face', set())
        if sh in missing: return False
        arr = source(sh.split(':', 1)[1])
        if arr is None: missing.add(sh); return False
        self.add_texture(sh, arr, clamp=True); return True

    def add_texture(self, name_str, arr, clamp=False):
        """A picture of the port (RGBA array, top row first) as a sheet of its own, sampled like the game's sheets (uv v negative downward, linear filtering): the flags of the start menu."""
        h, w = arr.shape[:2]
        t = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(arr[::-1]).tobytes(), pitch=w * 4).get_texture(); gl.glBindTexture(t.target, t.id)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE if clamp else gl.GL_REPEAT)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        self.tex[name_str] = t

    def update_canvas(self, a, name_str='msg'):
        """The engine's text canvas (512 x 512 bytes of opacity) -> "msg" texture (white, alpha = opacity), which wraps as in Unity."""
        h, w = a.shape
        rgba = np.empty((h, w, 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = a
        img = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(rgba).tobytes(), pitch=w * 4)      # row 0 first = v 0, like the Unity texture
        t = img.get_texture(); gl.glBindTexture(t.target, t.id)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        self.tex[name_str] = t

    # ---- building the elements to draw
    def _items(self, win):
        """-> list of (depth, order, kind, data) of a window."""
        items = []; o = 0
        for node in win.N.values():
            if not win.visible(node['id']): continue
            o += 1
            if node['vtx']: items.append((node['pos'][1], o, 'm', (win, node)))
            if node['text'] is not None and node['text'].get('text'): items.append((node['pos'][1] + 0.001, o, 't', (win, node)))
        items.sort(key=lambda x: (x[0], x[1]))
        return items

    def draw_all(self, wins, cx, cy, s, vp):
        """wins: list of Window; (cx, cy) = pixel of the center of the game screen; s = pixels per unit; vp = (width, height) of the window."""
        if not wins: return
        items = []
        for wi, win in enumerate(wins): items += [(d, wi, o, g, x) for d, o, g, x in self._items(win)]
        for wi, win in enumerate(wins):
            if getattr(win, 'typ', 0) in (25, 26) and win.game_map is not None: items.append((1.0, wi, 0, 'c', (win, None)))         # layer: above the frame background (depth 0), below the marker (12 and up)
        items.sort(key=lambda x: x[:3])                      # like Unity (transparent objects sorted by depth on the camera): depth first, then the most recent window in front; a window's background no longer covers another's buttons
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA); gl.glDisable(gl.GL_DEPTH_TEST)
        self.prog.use(); self.prog['vp'] = (float(vp[0]), float(vp[1]))
        lot = None; buf = []
        def drain():
            nonlocal buf
            if buf and lot:
                a = np.concatenate(buf).astype(np.float32); n = len(a)
                vl = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', a[:, 0:2].ravel()), tex_coords=('f', a[:, 2:4].ravel()), colors=('f', a[:, 4:8].ravel()))
                gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(lot[0].target, lot[0].id); self.prog['mode'] = lot[1]
                vl.draw(gl.GL_TRIANGLES); vl.delete()
            buf = []
        ok_num = {id(win): {n.get('buttonId') for n in win.N.values() if n.get('pad') and not (n['pad'] & 0xA0) and n.get('buttonId') is not None and n.get('vtx')} for win in wins}       # numbers carried by a confirm button (gamepad 16 / 64)
        for _, _, _, g, (win, node) in items:
            if g == 'c':
                drain(); lot = None; self._map(win, cx, cy, s, vp); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            elif g == 'm':
                if self.hide_up_cursor and node.get('up_cursor'): continue
                for k, mat in enumerate(node['mats']):
                    idx = node['sub'].get(str(k))
                    if not idx: continue
                    sh = mat.get('sheet')
                    if sh not in self.tex and not self._load_face(sh): continue
                    col = list(mat.get('color') or (1, 1, 1, 1)); mode = 0; off = (0.0, 0.0)
                    if k == 0 and node['buttonId'] is not None and 'part' in mat and mat['part'] == 10 and node['buttonId'] < 0 and win.selected_node == node['id']:
                        if getattr(win, 'press_node', None) == node['id']: col = [c * 0.75 for c in col]        # PRESSED page arrow: like the mobile game (IButton(Material), DisplayClass6_0.b__0: Material.color = 0.75 on the four channels)
                        else: col[:3] = [1.4, 1.4, 1.4]                                 # hovered page arrow (PC, the mobile game has no hover): lightened
                    elif k == 0 and node['buttonId'] is not None and (node['buttonId'] >= 0 or win.selected_node == node['id']) and 'part' in mat and mat['part'] == 7:
                        if not is_state_active(node['state']): state = node['state']              # grayed / inverted / invisible: no hover or cursor (the contact test is cut off)
                        elif win.selected_node is not None: state = 1 if node['id'] == win.selected_node else node['state']       # mouse: only the pointed (or pressed) element is highlighted, not the whole row that shares its number
                        else: state = 1 if (win.selected is not None and win.selected == node['buttonId'] and not ((node['pad'] or 0) & 0xA0 and node['buttonId'] in ok_num[id(win)])) else node['state']       # a cancel button (gamepad 32 / 128, e.g. "Rien") that shares its number with a confirm button ("Acheter") does not light up with it
                        if state == 1 or state == 4: off = self.ml.pushed
                        if state == 2: col[3] = 0.0
                        if state == 3: mode = 1
                        if state == 4: mode = 2
                    if col[3] <= 0: continue
                    t = self.tex[sh]
                    if lot != (t, mode): drain(); lot = (t, mode)
                    v = np.array(node['vtx'], np.float32); u = np.array(node['uv'], np.float32)
                    ia = np.array(idx, np.int64); vv = v[ia]; uu = u[ia] + np.array(off, np.float32)
                    x = cx + (node['pos'][0] + vv[:, 0]) * s; y = cy + (node['pos'][2] + vv[:, 1]) * s
                    c = np.tile(np.array(col, np.float32), (len(ia), 1))
                    buf.append(np.column_stack([x, y, uu[:, 0], uu[:, 1], c]))
            else:
                drain(); lot = None
                self._text(win, node, cx, cy, s)
        drain()

    def _plate_model(self):
        """Mesh of the game's button plate (Button sheet, part 7, nine pieces of the "list" window Make_NameButton): vertices, UVs, indices, color."""
        m = getattr(self, '_plate_model_cache', None)
        if m is None:
            m = False
            for t in self.ml.types.values():
                for n in t.get('nodes', []):
                    mm = n.get('mesh'); mats = n.get('mats') or []
                    if mm and mats and mats[0].get('sheet') == 1 and mats[0].get('part') == 7 and len(mm['vtx']) == 36 and n.get('parts', {}).get('buttonId') == 0:
                        m = (np.array(mm['vtx'], np.float32), np.array(mm['uv'], np.float32), np.array(mm['sub']['0'], np.int64), list(mats[0].get('color') or (1, 1, 1, 1))); break
                if m: break
            self._plate_model_cache = m
        return m or None

    def plate(self, x, y, w, h, vp, chosen=False, corner=None, grayed=False):
        """Draws the background of a button exactly like the game's windows (e.g. "Heal all") in the pixel rectangle (x, y, w, h): the corners keep their proportions (those of the model: 16 corner units for its height),
        the middle stretches. chosen: pressed version of the sheet (the one of a chosen button in the game). corner: side length of the corners in pixels (the original 16 units, whatever the height: on-screen buttons).
        grayed: inactive button (the game's gray shader, and darkened to 55%: the removed color is barely visible on this gray plate).
        -> False if the game's plate is unavailable."""
        lay = self._plate_layout()
        if lay is None or 1 not in self.tex: return False
        xs, zs, ix, iz, uvi, col = lay
        cap = min((xs[1] - xs[0]) * h / (zs[-1] - zs[0]) if corner is None else corner, w / 2.0, h / 2.0)                    # the corner keeps its proportion with the plate's height (or the requested size)
        px = np.array((x, x + cap, x + w - cap, x + w), np.float32)[ix]; py = np.array((y, y + cap, y + h - cap, y + h), np.float32)[iz]
        uu = uvi + (np.array(self.ml.pushed, np.float32) if chosen else 0.0)
        if grayed: col = [col[0] * 0.55, col[1] * 0.55, col[2] * 0.55, col[3]]
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA); gl.glDisable(gl.GL_DEPTH_TEST)
        self.prog.use(); self.prog['vp'] = (float(vp[0]), float(vp[1]))
        pos = np.column_stack([px, py]).ravel(); tc = uu.astype(np.float32).ravel(); cl = np.tile(np.array(col, np.float32), len(ix))
        vl = getattr(self, '_plate_vl', None)                                 # (one vertex list, refilled: the on-screen buttons draw three plates a frame, each one used to create and free its own)
        if vl is None: vl = self._plate_vl = self.prog.vertex_list(len(ix), gl.GL_TRIANGLES, position=('f', pos), tex_coords=('f', tc), colors=('f', cl))
        else: vl.position[:] = pos; vl.tex_coords[:] = tc; vl.colors[:] = cl
        t = self.tex[1]; gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(t.target, t.id); self.prog['mode'] = 1 if grayed else 0
        vl.draw(gl.GL_TRIANGLES); self.prog.stop()
        return True

    def _plate_layout(self):
        """The plate model prepared once: its four x and four y levels (edges and corner limits), the level of each drawn vertex, its UVs and color; None without the model."""
        lay = getattr(self, '_plate_layout_cache', None)
        if lay is None:
            mod = self._plate_model()
            if mod is None: return None
            vtx, uv, idx, col = mod
            xs = sorted({round(float(v[0]), 2) for v in vtx}); zs = sorted({round(float(v[1]), 2) for v in vtx})          # four x coordinates and four y coordinates
            ix = np.array([xs.index(round(float(v[0]), 2)) for v in vtx[idx]]); iz = np.array([zs.index(round(float(v[1]), 2)) for v in vtx[idx]])
            lay = self._plate_layout_cache = (xs, zs, ix, iz, uv[idx], list(col))
        return lay

    def _map(self, win, cx, cy, s, vp):
        """Plan of the map window: 4:3 texture (enlarged map, veil included). Small map (type 25, ICityMap: CreateFromTexture 450 x 337.5 placed at (2, -2) under the frame, local scale 0.99): from x = -223 to 222.5,
        from z = 398 to 63.875; large world map (type 26): rectangle of 450 x 337.5 from x = -225 to 225 (original position not read: kept)."""
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA); gl.glDisable(gl.GL_DEPTH_TEST)
        self.prog.use(); self.prog['vp'] = (float(vp[0]), float(vp[1]))
        if getattr(win, 'typ', 0) == 25: xa, xb, zh, zb = -223.0, 222.5, 398.0, 398.0 - 334.125
        else: xa, xb, zh, zb = -225.0, 225.0, 400.0, 400.0 - 337.5
        x0, x1, y1, y0 = cx + xa * s, cx + xb * s, cy + zh * s, cy + zb * s
        u0, v0, u1, v1 = getattr(win, 'map_uv', None) or (0.0, 0.0, 1.0, 1.0)          # large world map: 256 x 192 pixel window of the 1024 x 1024 map image, centered on the player
        a = np.array([[x0, y0, u0, v0], [x1, y0, u1, v0], [x1, y1, u1, v1], [x0, y0, u0, v0], [x1, y1, u1, v1], [x0, y1, u0, v1]], np.float32)
        vl = self.prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', a[:, 0:2].ravel()), tex_coords=('f', a[:, 2:4].ravel()), colors=('f', np.ones(24, np.float32)))
        t = win.game_map; gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(t.target, t.id); self.prog['mode'] = getattr(win, 'map_mode', 3)         # enlarged map images (HD, veil included): linear filtering; large world map: sharp bilinear
        vl.draw(gl.GL_TRIANGLES); vl.delete(); self.prog['mode'] = 0
        sp = getattr(win, 'special', None)
        if sp is not None:                                                            # code 4: special location, red cross (MenuTexture, sheet 5, cell 3; AddIcon 1.2 x 16 = 21.6 units), bottom-left corner at (-227 + x k, 402 - y k) (anchor assumed, like the feather's)
            info = self.ml.info[5]; t = self.tex.get(info['tex']); k = 450.0 / 256.0
            if t is not None:
                uv = uv_icon(info, 3, 0); xl, yb = cx + (-227.0 + sp[0] * k) * s, cy + (402.0 - sp[1] * k) * s; xr, yt = xl + 21.6 * s, yb + 21.6 * s
                a = np.array([[xl, yt, *uv[0]], [xr, yt, *uv[1]], [xr, yb, *uv[2]], [xl, yt, *uv[0]], [xr, yb, *uv[2]], [xl, yb, *uv[3]]], np.float32)
                vl = self.prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', a[:, 0:2].ravel()), tex_coords=('f', a[:, 2:4].ravel()), colors=('f', np.ones(24, np.float32)))
                gl.glBindTexture(t.target, t.id); self.prog['mode'] = 0; vl.draw(gl.GL_TRIANGLES); vl.delete()
        sy = getattr(win, 'symbols', None)
        if sy:                                                                        # discovered locations (BlinkMapSymbol): red squares of 4 units whose transparency goes back and forth (0.5 per second: 1 -> 0 -> 1 in 4 s)
            if self._white is None:
                self._white = pyglet.image.ImageData(1, 1, 'RGBA', b'\xff\xff\xff\xff').get_texture()
            al = abs(1.0 - ((time.monotonic() - (win.t_blink or 0.0)) % 4.0) / 2.0); k = 450.0 / 256.0; q = []
            for xb, yb in sy:
                a0, b0 = cx + (-225.0 + xb * k - 2.0) * s, cy + (400.0 - yb * k - 2.0) * s; a1, b1 = a0 + 4.0 * s, b0 + 4.0 * s          # square of 4 units centered on the location (like the player's marker, of 24 units, centered on its position)
                q += [[a0, b0], [a1, b0], [a1, b1], [a0, b0], [a1, b1], [a0, b1]]
            q = np.array(q, np.float32); n = len(q)
            vl = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', q.ravel()), tex_coords=('f', np.zeros(n * 2, np.float32)), colors=('f', np.tile(np.array([1.0, 0.0, 0.0, al], np.float32), n)))
            t = self._white; gl.glBindTexture(t.target, t.id); vl.draw(gl.GL_TRIANGLES); vl.delete()

    PLATE_MARGIN = 7.0          # margin (interface units) left on each side between the text and the edge of a button's plate

    def _adjust_description(self, node, lines, layout, nmax, bm, u, ts, s, emy):
        """Description (for a frame that shows `nmax` lines and is `layout` units wide): (lines, compression factor). A text that already fits (at most `nmax` lines, none wider than the frame) is left as is, with the patch's line breaks.
        Otherwise the line breaks are replaced by spaces and the text is re-wrapped to the frame width; if it still needs more than `nmax` lines, it is compressed in width (down to COMPRESSION_MIN) to fit in `nmax` lines."""
        lookup_key = (tuple(lines), layout, nmax, u, ts, s)
        c = node.get('_adj')
        if c is not None and c[0] == lookup_key: return c[1]
        px = max(6, int(round(emy * s)))
        def wid(x):
            x = re.sub(r'@c\d', '', x)
            return bm.width_px(x) * u * ts if bm else (self.texts.line(x, px)[1] - 4) / s * ts
        useful = list(lines)
        while useful and not useful[-1].strip(): useful.pop()
        if not useful or (len(useful) <= nmax and all(wid(l.strip()) <= layout + 0.5 for l in useful)): res = (lines, 1.0)
        else:
            words = ' '.join(l.strip() for l in useful).split()
            def cut(d):
                out = []; cur = ''
                for w in words:
                    attempt = cur + ' ' + w if cur else w
                    if cur and wid(attempt) > d: out.append(cur); cur = w
                    else: cur = attempt
                if cur: out.append(cur)
                return out
            f = 1.0; out = cut(layout)
            while not (len(out) <= nmax and max(wid(l) for l in out) <= layout / f + 0.5) and f > COMPRESSION_MIN + 1e-9:
                f = max(COMPRESSION_MIN, round(f - 0.05, 4)); out = cut(layout / f)
            res = (out, f)
        node['_adj'] = (lookup_key, res)
        return res

    def _plate_x(self, win, node, zp):
        """(left edge, right edge) of the button plate (part 7) whose rectangle contains the text's anchor point, or None."""
        c = node.get('_pl'); where = (node['pos'][0], zp)                 # (the place too: a list window reused with another layout moves its rows, DQ V's Divers list then Tactique)
        if c is None or c[0] is not win.t or c[2] != where:
            r = None
            for o in win.N.values():
                if o is node or not o['vtx'] or not o['mats'] or o['mats'][0].get('part') != 7 or o['buttonId'] is None: continue
                xs = [o['pos'][0] + v[0] for v in o['vtx']]; zs = [o['pos'][2] + v[1] for v in o['vtx']]
                if min(xs) <= node['pos'][0] <= max(xs) and min(zs) <= zp <= max(zs): r = (min(xs), max(xs)); break
            node['_pl'] = c = (win.t, r, where)
        return c[1]

    def _plate_z(self, win, node, zp):
        """(bottom, top) in units of the VISIBLE part of the button plate (part 7) that holds the text's anchor point (its sheet's opaque pixels, see visible_edges), or None."""
        c = node.get('_pz'); where = (node['pos'][0], zp)                 # (the place too: a list window reused with another layout moves its rows, DQ V's Divers list then Tactique)
        if c is None or c[0] is not win.t or c[2] != where:
            r = None
            for o in win.N.values():
                if o is node or not o['vtx'] or not o['mats'] or o['mats'][0].get('part') != 7 or o['buttonId'] is None: continue
                xs = [o['pos'][0] + v[0] for v in o['vtx']]; zs = [o['pos'][2] + v[1] for v in o['vtx']]
                if not (min(xs) <= node['pos'][0] <= max(xs) and min(zs) <= zp <= max(zs)): continue
                al = SHEET_ALPHA.get(o['mats'][0].get('sheet')); sub = (o.get('sub') or {}).get('0')
                v = visible_edges(o['vtx'], o['uv'], sub, al) if al is not None and sub else None
                r = (o['pos'][2] + v[2], o['pos'][2] + v[3]) if v else (min(zs), max(zs)); break
            node['_pz'] = c = (win.t, r, where)
        return c[1]

    def _plate_width(self, win, node, zp):
        """Usable width (units) of the button plate (part 7) that carries this centered text, or None: the plate whose rectangle contains the text's anchor point."""
        t = node['text']; col = t['anchor'] % 3
        if col != 1 and win.typ not in (53, 54): return None                 # (texts to the left / right of a plate: only the start menu's lists, the other windows keep their layout)
        r = self._plate_x(win, node, zp)
        if r is None: return None
        xa = node['pos'][0]
        if col == 1: return r[1] - r[0] - 2 * self.PLATE_MARGIN                                      # centered text: the whole plate
        return (r[1] - self.PLATE_MARGIN - xa) if col == 0 else (xa - r[0] - self.PLATE_MARGIN)      # text to the left / right of its anchor point (e.g. "Chapitre 1 Nv. 1 001:07" of an adventure log line): up to the edge of the plate

    def _room(self, win, node, zp):
        """Width (units) a text can take from its anchor point: in its button plate if it has one, otherwise in its window (the same margin); None if unknown (soft_hyphens)."""
        col = node['text']['anchor'] % 3; xa = node['pos'][0]
        r = self._plate_x(win, node, zp)
        if r is None:
            r = win.extent_x()
            if not r or not r[0] <= xa <= r[1]: return None
        return {0: r[1] - self.PLATE_MARGIN - xa, 1: 2 * min(xa - r[0], r[1] - xa) - 2 * self.PLATE_MARGIN, 2: xa - r[0] - self.PLATE_MARGIN}[col]

    def _text(self, win, node, cx, cy, s):
        if node.get('mute'): return                                            # (a cell the port does not show: the battle list's costs)
        if self.hidden_cells and node.get('cell', (0, None))[1] in self.hidden_cells.get(getattr(win, 'typ', None), ()): return
        t = node['text']; lang = self.ml.hdr['lang']
        lines = t['text'].split('\n')
        bm = self.texts.bitmap                                         # original font (SE-GARRIR): 1 font px = characterSize * 0.1 unit; otherwise GMaruGoPro-M rendered by Pillow
        u = t['characterSize'] * 0.1
        if bm: emy = u; step = bm.leading * u * t['lineSpacing']; asc = bm.ascent * u
        else: emy = FONT_SIZE * u; step = LINE_HEIGHT * emy * t['lineSpacing']; asc = 0.88 * emy
        zp = node['pos'][2] - lang['dy']                                  # the game adds dy to the text position (compensation for the font's line spacing)
        ts = node['tscale']
        if '$' in t['text']:                                               # the patch's break points: removed, or a cut with a hyphen when the line does not fit
            px_ = max(6, int(round(emy * s))); plain = lambda x: re.sub(r'@c\d', '', x)
            wd = (lambda x: bm.width_px(plain(x)) * u * ts) if bm else (lambda x: (self.texts.line(plain(x), px_)[1] - 4) / s * ts)
            lines = soft_hyphens(lines, wd, self._room(win, node, zp))
        if node.get('wrap_x') is not None:                                # description wider or taller than its frame: re-wrapped, then compressed if 2 lines are not enough
            lines, f = self._adjust_description(node, lines, node['wrap_x'] - node['pos'][0], node.get('wrap_n', 2), bm, u, ts, s, emy); ts *= f
        N = len(lines)
        row = t['anchor'] // 3; col = t['anchor'] % 3
        base0 = first_line_baseline(zp, row, N, step, asc)               # TextMesh.anchor: the anchor point is the top (0-2), the middle (3-5) or the bottom (6-8) of the text block; line spacing and tabs exactly those of the game (only the descriptions and the spells' cost lines are re-wrapped / compressed / fitted)
        base0 += node.get('raise', 0.0)                                  # cost line of the spell lists (COST_LISTS)
        if node.get('ink_center') and bm and N == 1:                       # the name of a battle spell list, alone in its plate: the middle of its capitals at the middle of the plate's visible part
            r = self._plate_z(win, node, zp)
            if r is not None: base0 = (r[0] + r[1]) / 2 - (bm.cap_height() if hasattr(bm, 'cap_height') else bm.ascent * 0.7) * u / 2
        if bm: base0 += text_recentering(bm.leading, u, t['lineSpacing'])      # (ink centered in its plate; original font only: the game's settings are computed for the Japanese font, GMaruGoPro-M, when it serves as fallback)
        px = max(6, int(round(emy * s)))
        def tint(i):
            if isinstance(i, tuple): return i                                      # (explicit color of a <color=#...> tag: the betting lines of DQ V / VI)
            if i == 0 and node.get('tint'): return node['tint']                    # (the cell's own color, without a palette code)
            pal = self.ml.colors[i] if 0 <= i < len(self.ml.colors) else (1, 1, 1, 1)
            return (min(pal[0], 1.0), min(pal[1], 1.0), min(pal[2], 1.0), 1.0)
        segs_l = []; cur = node['tcol']                                    # "@cN" changes the text color (game palette); it carries over from one line to the next
        for l in lines:                                                    # (and Unity's rich text <color=#rrggbbaa> ... </color>, written by the betting lines: MenuPortItemTable.IBetText)
            segs = []; pos = 0
            for m in re.finditer(r'@c(\d)|<color=#([0-9a-fA-F]{8})>|</color>', l):
                if m.start() > pos: segs.append((l[pos:m.start()], cur))
                if m.group(1) is not None: cur = int(m.group(1))
                elif m.group(2) is not None: h = m.group(2); cur = tuple(int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4, 6))
                else: cur = node['tcol']
                pos = m.end()
            if pos < len(l): segs.append((l[pos:], cur))
            segs_l.append(segs)
        if bm: wid = [sum(bm.width_px(t) * u * ts for t, _ in segs) for segs in segs_l]
        else: wid = [sum((self.texts.line(t, px)[1] - 4) / s * ts for t, _ in segs) for segs in segs_l]
        bl = max(wid) if wid else 0.0
        if not bm:                                                        # fallback font (GMaruGoPro-M, without ui_garrir.*) only: a text wider than its plate or its window is compressed in width to fit. With SE-GARRIR (the game's font) nothing is compressed or re-wrapped: the text overflows as on mobile
            layout = self._plate_width(win, node, zp)
            if layout is None and win.extent_x() is None and not win.rects():              # window without its own frame (title and labels of a setting): the frame is in another visible window, take the smallest rectangle that contains the anchor point
                xa = node['pos'][0]; z_a = node['pos'][2] - lang['dy']; r_min = None
                for v in self.neighbors:
                    for (x0, z0, x1, z1) in v.rects():
                        if x0 <= xa <= x1 and z0 <= z_a <= z1 and (r_min is None or (x1 - x0) * (z1 - z0) < (r_min[2] - r_min[0]) * (r_min[3] - r_min[1])): r_min = (x0, z0, x1, z1)
                if r_min:
                    layout = {0: r_min[2] - self.PLATE_MARGIN - xa, 1: 2 * min(xa - r_min[0], r_min[2] - xa) - 2 * self.PLATE_MARGIN, 2: xa - r_min[0] - self.PLATE_MARGIN}[col]
            if layout is None and bl > 0:                                     # outside a button plate: the text must fit within the width of its window (from its anchor point, with the same margin)
                ex = win.extent_x(); xa = node['pos'][0]
                if ex and ex[0] <= xa <= ex[1]:
                    layout = {0: ex[1] - self.PLATE_MARGIN - xa, 1: 2 * min(xa - ex[0], ex[1] - xa) - 2 * self.PLATE_MARGIN, 2: xa - ex[0] - self.PLATE_MARGIN}[col]
                    if layout < 0.4 * bl: layout = None                         # (anchor too close to the edge for the text to be what is too wide)
            if layout and bl > layout:
                f = max(0.7, layout / bl); ts *= f; wid = [w * f for w in wid]; bl *= f
        x0 = node['pos'][0]
        if node.get('fit_x') is not None and col == 0 and bl > node['fit_x'] - x0:        # cost line of a spell sheet: longer in French than its frame, compressed horizontally (down to COMPRESSION_MIN)
            f = max(COMPRESSION_MIN, (node['fit_x'] - x0) / bl); ts *= f; wid = [w * f for w in wid]; bl *= f
        if node.get('in_plate') and col == 0 and bl > 0:                  # cost line of a spell list: "Cout en PM:<tab>  2" is longer in French than the right half of the button; it is fitted against the right edge of its plate (and never beyond the left edge)
            r = self._plate_x(win, node, zp)
            if r is not None: x0 = max(min(x0, r[1] - self.PLATE_MARGIN - bl), r[0] + self.PLATE_MARGIN)
        for i, segs in enumerate(segs_l):
            if not segs: continue
            lw = wid[i]
            al = {0: 0.0, 1: (bl - lw) / 2, 2: bl - lw}[t['alignment']]  # alignment of the line within the block
            bx = {0: 0.0, 1: bl / 2, 2: bl}[col]
            xs = x0 - bx + al
            y_base = base0 - i * step
            for text, ci in segs:
                if bm:                                                   # texture at the font's native size (1 px = 1 font px), enlarged by the bilinear filter as in Unity
                    tex, w, h, b = bm.line(text); k = u * s
                    x = cx + xs * s - bm.PAD * k * ts; y = cy + y_base * s - (h - b) * k
                    wd = w * k * ts; ht = h * k; advance = bm.width_px(text) * u * ts
                else:
                    tex, w, h, b = self.texts.line(text, px)
                    x = cx + xs * s - 2 * ts; y = cy + y_base * s - (h - b)
                    wd = w * ts; ht = h; advance = (w - 4) / s * ts
                a = np.array([[x, y, 0, 0], [x + wd, y, 1, 0], [x + wd, y + ht, 1, 1], [x, y, 0, 0], [x + wd, y + ht, 1, 1], [x, y + ht, 0, 1]], np.float32)
                vl = self.prog.vertex_list(6, gl.GL_TRIANGLES, position=('f', a[:, 0:2].ravel()), tex_coords=('f', a[:, 2:4].ravel()), colors=('f', np.tile(np.array(tint(ci), np.float32), 6)))
                gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(tex.target, tex.id); self.prog['mode'] = 0
                vl.draw(gl.GL_TRIANGLES); vl.delete()
                xs += advance


class Manager:
    """Receives what the game's interface records (Interface.obs) and holds one Window per menu port."""
    shop_type = 0          # MenuPortItem.s_shopType (the engine's code 14), read by the windows that the game builds after it
    def __init__(self, ml):
        self.ml = ml; self.f = {}
    def open_menu(self, port, typ):
        t = self.ml.types.get(str(typ))
        if t and not t.get('err') and (t.get('nodes') or t.get('name', '').startswith(tuple(PICTURE_WINDOWS))): self.f[port] = Window(self.ml, typ, self.shop_type)
        else: self.f.pop(port, None)
    def shutdown(self, port): self.f.pop(port, None)
    def reactivate(self, port):
        f = self.f.get(port)
        if f: f.reactivate()
    def replay(self, ui):
        """The windows of ports 2 to 11 (field menus) are created by the engine at startup, before the viewer starts listening: their creation and content are replayed."""
        self.shop_type = getattr(ui, 'shop_type', 0)
        for port, f in sorted(ui.f.items()):
            if f.get('type') is None: continue
            self.open_menu(port, f['type'])
            for (i, no), txt in f['cells'].items(): self.param_str(port, i, no, txt)
            for (i, no), v in (f.get('ints') or {}).items(): self.param_int(port, i, no, v)
            for i, c in f['indicators'].items(): self.code(port, i, c)
            if f.get('act') and f.get('since_act') is not None:                  # (active window: its parts shown again at its last activation, then the codes received since)
                self.reactivate(port)
                for i, c in f['since_act'].items(): self.code(port, i, c)
            for i, q in (f.get('plates') or {}).items():
                if 'name' in q and 'params' in q: self.plate(port, i, q['name'], q['params'], q['code'])
            if f.get('layout') is not None: self.arrange(port, f['layout'])
            if f.get('cur') is not None: self.selection(port, f['cur'])
    def param_int(self, port, i, no, v):
        f = self.f.get(port)
        if f: f.param_int(i, no, v)
    def param_str(self, port, i, no, s):
        f = self.f.get(port)
        if f: f.param_str(i, no, s)
    def code(self, port, i, c):
        f = self.f.get(port)
        if f: f.code(i, c)
    def selection(self, port, b):
        f = self.f.get(port)
        if f: f.selection(b)
    proj = None            # called with a monster mask -> (x min, x max) in interface units, or None; proj(mask, True) -> the list of x coordinates, one per monster (supplied by the viewer)
    def plate(self, port, i, name_str, prm, code):
        f = self.f.get(port)
        if f: f.plate(i, name_str, prm, code)
    def arrange(self, port, n):
        f = self.f.get(port)
        if f: f.arrange(n, self.proj)
    def tick(self):
        """One game frame: window animations (shaking of the battle plates, blinking of the target arrow)."""
        for f in self.f.values(): f.tick()


RESOURCES = {'ui_MenuTexture.png': 'MenuTexture', 'ui_Button.png': 'Button'}


def extract_garrir(o, d, json_path, png_path):
    """SE-GARRIR bitmap font (Unity Font) -> ui_garrir.json (metrics, glyphs: code, vert x y w h, advance, flipped, uv x y w h) and ui_garrir.png (RGBA atlas, as UnityPy renders it)."""
    t = o.read_typetree()
    tex_id = (t.get('m_Texture') or {}).get('m_PathID') or 0
    if not tex_id:                                       # DQ VI: the font's own texture reference is empty; its default material carries it (_MainTex, the Texture2D "SE-GARRIR")
        mat = o.assets_file.objects[t['m_DefaultMaterial']['m_PathID']].read_typetree()
        tex_id = next(e[1]['m_Texture']['m_PathID'] for e in mat['m_SavedProperties']['m_TexEnvs'] if e[0] == '_MainTex')
    o.assets_file.objects[tex_id].read().image.convert('RGBA').save(png_path)
    gl_ = [[r['index'], r['vert']['x'], r['vert']['y'], r['vert']['width'], r['vert']['height'], r['advance'], int(bool(r['flipped'])),
            r['uv']['x'], r['uv']['y'], r['uv']['width'], r['uv']['height']] for r in t['m_CharacterRects']]
    with open(json_path, 'w', encoding='utf-8') as f: json.dump({'name': t['m_Name'], 'fontSize': t['m_FontSize'], 'lineSpacing': t['m_LineSpacing'], 'ascent': t['m_Ascent'], 'descent': t['m_Descent'], 'pixelScale': t['m_PixelScale'], 'glyphes': gl_}, f)


FACES = 'ui_faces.npz'          # the portraits Menu/face/fNN (Texture2D "f01"... of the data pack, 128 x 128), shown by MenuParts.ITexture (DQ V / VI)


def extract_faces(apk_folder, cache, log=print):
    """Once: the data pack's portraits -> cache/ui_faces.npz (empty when the game has none, or when its interface has no ITexture: DQ IV)."""
    dest = os.path.join(cache, FACES)
    if os.path.exists(dest): return
    import numpy as np
    faces = {}
    lay = os.path.join(cache, 'ui_layout.json')
    if not os.path.exists(lay) or 'MenuParts.ITexture' in open(lay, encoding='utf-8').read():
        import UnityPy, zipfile
        log('Reading the portraits (once)...')
        pack = UnityPy.load(zipfile.ZipFile(os.path.join(apk_folder, 'split_UnityDataAssetPack.apk')).read('assets/bin/Data/datapack.unity3d'))
        for o in pack.objects:
            if o.type.name != 'Texture2D': continue
            d = o.read()
            if re.fullmatch(r'f\d\d', d.m_Name or '') and d.m_Name not in faces: faces[d.m_Name] = np.array(d.image.convert('RGBA'))
    os.makedirs(cache, exist_ok=True)
    np.savez_compressed(dest, **faces)


def face_loader(cache):
    """-> function name ("f05") -> RGBA array (top row first) or None; reads ui_faces.npz on first use."""
    box = {}
    def get(name_str):
        if 'z' not in box:
            try:
                import numpy as np
                box['z'] = np.load(os.path.join(cache, FACES))
            except Exception: box['z'] = {}
        z = box['z']
        return z[name_str] if name_str in getattr(z, 'files', z) else None
    return get


def prepare_resources(apk_folder, cache, log=print):
    """Extracts from the game's APKs (once only): MenuTexture and Button sheets, font, frame meshes. -> True if everything is there."""
    dest = {n: os.path.join(cache, n) for n in list(RESOURCES) + ['ui_font.otf', 'ui_frameData.bin']}
    dest_g = [os.path.join(cache, n) for n in ('ui_garrir.json', 'ui_garrir.png')]            # original font SE-GARRIR (optional: without it, GMaruGoPro-M)
    try:
        from dq456_pc.menus.message_font import extract_message_font
        extract_message_font(apk_folder, cache, log)                         # message font (optional), even when the other resources are already there
    except Exception as e: log('Message font not extracted: %r' % (e,))
    try: extract_faces(apk_folder, cache, log)                               # portraits (optional), likewise
    except Exception as e: log('Portraits not extracted: %r' % (e,))
    if all(os.path.exists(p) for p in list(dest.values()) + dest_g): return True
    try:
        import UnityPy, zipfile
        os.makedirs(cache, exist_ok=True)
        log('Reading the game menu resources (once)...')
        base = UnityPy.load(os.path.join(apk_folder, 'base.apk'))
        for o in base.objects:
            if o.type.name == 'Texture2D':
                d = o.read()
                for file_name, name_str in RESOURCES.items():
                    if d.m_Name == name_str and not os.path.exists(dest[file_name]): d.image.convert('RGBA').save(dest[file_name])
            elif o.type.name == 'Font':
                d = o.read()
                if d.m_Name == 'GMaruGoPro-M' and d.m_FontData and not os.path.exists(dest['ui_font.otf']):
                    open(dest['ui_font.otf'], 'wb').write(bytes(d.m_FontData))
                elif d.m_Name == 'SE-GARRIR' and not all(os.path.exists(p) for p in dest_g):
                    try: extract_garrir(o, d, *dest_g)
                    except Exception as e: log('SE-GARRIR font not extracted: %r' % (e,))
        if not os.path.exists(dest['ui_frameData.bin']) or not os.path.exists(dest['ui_font.otf']):
            pack = UnityPy.load(zipfile.ZipFile(os.path.join(apk_folder, 'split_UnityDataAssetPack.apk')).read('assets/bin/Data/datapack.unity3d'))
            for o in pack.objects:
                if o.type.name == 'TextAsset' and not os.path.exists(dest['ui_frameData.bin']):
                    d = o.read()
                    if d.m_Name == 'frameData':
                        raw = d.m_Script; open(dest['ui_frameData.bin'], 'wb').write(raw.encode('utf-8', 'surrogateescape') if isinstance(raw, str) else bytes(raw))
                elif o.type.name == 'Font' and not os.path.exists(dest['ui_font.otf']):          # Dragon Quest VI: its GMaruGoPro-M carries no font file; the data pack's own font (M+ 2c) stands in
                    d = o.read()
                    if d.m_FontData: open(dest['ui_font.otf'], 'wb').write(bytes(d.m_FontData))
        return all(os.path.exists(p) for p in dest.values())
    except Exception as e:
        log('Menu resources unavailable: %r' % (e,)); return False
