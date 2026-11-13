"""Touch buttons of the mobile version, displayed on screen outside battle: Map, Commands (menu), party chat, and the D-pad (touch gamepad, usable with the mouse).
In battle, only the port's own "Battle speed" button ("Manual", "Normal", "Fast", "Tres rapide"; click = next speed) is shown: there is no equivalent button in the mobile game, and it sends nothing to the engine.
It is on the left edge of the screen (grid cell; DQ_SPEED_ANCHOR=1 attaches it to the bottom left corner of the bottom box (commands or message), as the "Flee" button is to the bottom right corner of the commands, which was the default), and has no label: arrows show the speed
(hollow triangle: "Manual"; one triangle: "Normal"; two: "Fast"; three: "Tres rapide"). A player who moves it in the interface editor keeps it at the chosen location.

The original game draws them in the Unity layer (TouchPad: "Map Button" = key 0x1000, "Command Button" = 0x800, "Talk Button" = 0x400; icons 3, 4 and 15 of the
MenuTexture sheet, 32 px row at y = 224). The engine says when they are visible through the Global.Flag word (first word of its output): (Flag & (8 | 0x30047)) == 8 (pad present, no player lock, fade, screen effect, locked interface or pause); the Map also requires bit 0x20. Positions are set on a grid of 32 x 18 cells (optional snapping).

The D-pad is that of TouchPad ("Button" sheet: ring, eight direction pills with their arrow, ball); in the original code the ring does not move (only the ball follows the finger) and it is always opaque. On PC
it is fixed (bottom right by default, to be moved in the interface editor): a press in its grab zone (1.178 radius) grabs it, the ball follows the mouse (limited to 0.4526 radius), the direction is one of the eight sectors of
45 degrees, like the keyboard keys (so it follows the camera). Its diameter is one and a half times that of the mobile game (DPAD_DIAMETER; the "D-pad size" setting at 67% gives back the original size). Held at the EDGE of the ring
(`dpad_run`: TRAVEL_THRESHOLD of the radius or more), it makes the hero run like the accelerator key; closer to the center he walks normally. The "map mode" button is no longer here: it is the one in the map window (type 22)."""
import math, os, time
import numpy as np
import pyglet
from pyglet import gl
from dq4_pc.language import tr, N_

COLS, LINES = 32, 18                       # screen grid (cells proportional to the window)
SPEED_ANCHOR_DEFAULT = False                 # battle speed button: False = at its place in the grid, on the left edge of the screen (default: "put it back on the left edge for now"); True = attached to the bottom left corner of the bottom box

def speed_anchor():
    """Is the battle speed button attached to the bottom box? Not by default: it stays on the left edge of the screen, at the grid cell (DEFAULT) or where the player placed it. To try it: environment variable DQ_SPEED_ANCHOR=1 (attached to the bottom left corner of the box) or 0."""
    v = os.environ.get('DQ_SPEED_ANCHOR')
    if v is None or not v.strip(): return SPEED_ANCHOR_DEFAULT
    v = v.strip().lower()
    return True if v in ('1', 'oui', 'yes', 'true', 'vrai') else False if v in ('0', 'non', 'no', 'false', 'faux') else SPEED_ANCHOR_DEFAULT
NAMES = ('map', 'menu', 'chat')
DPAD = 'dpad'
BAR = 'bar'                                   # camera rotation bar (the game's l_RotBar): at the very top of the screen (at the bottom before), across its full width; neither movable nor resizable
BATTLE = 'battle'                            # "Battle speed" button (specific to the port): shown in battle only, in place of the three field buttons
BUTTONS = NAMES + (BATTLE,)                   # all the rectangular buttons
EDITOR_NAMES = BUTTONS + (DPAD, BAR)                 # all the elements placed in the interface editor
SCREEN_EDITOR_NAMES = NAMES + (DPAD, BAR)              # "On-screen buttons and D-pad" interface: Map, Commands, Chat and the D-pad (the battle speed button has its own interface)
SPEED_EDITOR_NAMES = (BATTLE,)                  # "Battle: speed button" interface


def editor_names(target):
    """Elements of the interface editor for the chosen target (settings.SCREEN_TARGET, settings.SPEED_TARGET); empty for another interface."""
    return SPEED_EDITOR_NAMES if target == 'speed_button' else SCREEN_EDITOR_NAMES if target == 'buttons' else ()

DEFAULT = {'map': (0.4, 1.5), 'menu': (0.4, 12), 'chat': (0.4, 14), BATTLE: (0.4, 8)}      # top left corner (column, line): left column (the D-pad is at the bottom right), Map at the top (line 1.5: below the rotation bar), Commands then Chat lower; battle speed between the two: to the left of the battle windows (centered portrait column), it hides none of them
DECL = {'map': 0x1000, 'menu': 0x800, 'chat': 0x400}
ICON = {'map': 3, 'menu': 4, 'chat': 15, 'rot_l': 0, 'rot_r': 1, 'bar_1': 42, 'bar_2': 43, 'bar_3': 44}      # icon number in the MenuTexture sheet (32 per row); rot_g / rot_d: the two rotation icons and barre_1..3: the central pattern of l_RotBar (TouchPad.Start: AddIcon 0 and 1 at -198 and +198, AddContiguousIcon 42 of 3 x 1, size 0.9)
CAPTION = {'map': N_('settings.map'), 'menu': N_('settings.controls'), 'chat': N_('menus.talk'), BATTLE: N_('settings.battle_speed'), DPAD: N_('menus.d_pad'), BAR: N_('menus.camera_rotation_bar')}            # (names of the elements in the interface editor: translated when drawn)
ICON_ROW = 224                           # y coordinate of the icon row in the sheet (PartsInfo[3])
# Button plates (TouchPad.CreateMenuButton 0xD2377C: plate (t x 40 + 32) x (t x 32 + 32) for a size t) in units of the original interface (450 x 800):
# (width, height, icon side = 48 x icon size)
DQ_PLATE = {'map': (72.0, 64.0, 57.6), 'menu': (72.0, 64.0, 57.6), 'chat': (63.0, 56.8, 48.0), BATTLE: (118.0, 60.0, 0.0)}      # (the battle speed button has no icon: wider plate that carries "Speed" and the current speed)
PLATE_CORNER = 16.0                           # corners of the 9-slice plate ("Button" sheet, part 7), in interface units

# ---- D-pad (TouchPad): pieces of the "Button" sheet (512 x 512), (x, y, width, height) in pixels from the top left
DPAD_ART = {'ring': (256, 256, 256, 256), 'pill': (384, 192, 128, 64), 'pill_on': (256, 192, 128, 64), 'ball': (448, 128, 64, 64), 'ball_on': (384, 128, 64, 64), 'halo': (320, 128, 64, 64)}      # (CurLight 384, 128 and CurBS 320, 128: orange ball and blink halo of the D-pad, TouchPad.SetPadBlink)
# Original values (TouchPad, libil2cpp.so, RVA; fidelity): c_PadScaleTBL, MPad 256 x 0.63, Dirs at 104 units from the center, c_MoveThreshold 10,
# c_moveNakaLimit 36.5, c_padColRad 95 for a radius of 80.64
DPAD_DIAMETER = 1.5 * 161.28                     # diameter of the ring in units of the original interface (800 high: scale H / 800) before the game option and the port setting: ONE AND A HALF TIMES that of the mobile game (256 x c_PadBaseScaleXY 0.63 = 161.28). History: double (the D-pad, small on a PC screen, is operated with the mouse), then "reduce the size of the D-pad by 25% by default": 0.75 x 2 = 1.5; the "D-pad size" setting (50 to 200%) applies on top
DPAD_SCALE = (1.225, 1.0, 0.775)           # "D-pad size" game option (g_pad_size: 0 "Grande", 1 "Moyenne" (default), 2 "Petite") -> factor (c_PadScaleTBL)
DOT_RADIUS = 104.0 / 256.0                # distance from the center of the ring to the center of a pill (fraction of the diameter; the 128 x 64 quad runs from 72 to 136 units)
BALL_TRAVEL = 0.4526                         # maximum travel of the ball (fraction of the ring radius: 36.5 / 80.64)
DEAD_ZONE = 0.124                            # below this (fraction of the radius: 10 / 80.64), no direction
DPAD_WIDTH_MAX = 0.75                     # maximum diameter of the D-pad (fraction of the window width): in 9:16 portrait, twice the mobile size takes up 0.72 of it; a narrower window shrinks it so that it fits
TRAVEL_THRESHOLD = 0.9                            # D-pad travel: the pointer reaches the edge of the ring (fraction of the radius, 1 = the drawn edge; the grab zone goes up to 1.178); below it, the hero walks. Chosen value (assumed: "when the joystick touches the edges")
BLINK_PERIOD = 1.0                        # blink of the central circle (seconds per cycle): value chosen by the port (the game's constants, MOVE_WAIT_TIME / MOVE_LIMIT_ALPHA, are unused; assumed)
BAR_HEIGHT = 57.6                           # height of the rotation bar (grab band) in units of the original interface (800 high): that of the l_RotBar icons (size 0.9 x 64); the band sits on the bottom edge, with the icons whole (on mobile, except on notched screens, the bottom of the bar is cut off by the screen edge)
BAR_THRESHOLD = 8.0                        # c_RotThreshold: movement (units) beyond which a press on the bar becomes a rotation (below that: a tap)
BAR_MARGIN = 0.5                           # (in icons) gap between each rotation icon and the side edge of the screen
BAR_END = 2.0                              # width of the end zones, in icons: pressing there turns the camera as long as the button is held
DPAD_GRAB = 1.178                           # radius of the grab zone (fraction of the ring radius: 95 / 80.64 collider, a little wider than the drawn ring)

# ---- style of the mobile game's windows (screenshot of the command menu): translucent midnight-blue background, five-stroke frame (gray, light gray, white, gray,
# dark gray), rounded corners; buttons = gray gradient plates (light at the top, dark at the bottom), light gray border. Drawn as arrays (distance to the edge)
# then kept as textures: no per-frame cost.
DQ_BACKGROUND = (8, 16, 40); BACKGROUND_OPACITY = 0.82
GAME_OPACITY = 0.68                                                                                    # background of the game windows: black at 68% opacity (measured on the field windows, through which the scenery is visible)
DQ_EDGES = ((138, 138, 138), (205, 205, 205), (255, 255, 255), (132, 132, 132), (41, 41, 41))       # frame strokes from the outside to the inside
TOP_PLATE, BOTTOM_PLATE = (86, 87, 85), (34, 37, 31)                                                  # gradient of a plate's background (top -> bottom)
_textures = {}


def _distance(w, h, r):
    """Signed distance (positive inside) from each pixel to the edge of a rounded-corner rectangle w x h (radius r), array (h, w)."""
    yy, xx = np.mgrid[0:h, 0:w]; xx = xx + 0.5; yy = yy + 0.5
    px = np.abs(xx - w / 2.0) - (w / 2.0 - r); py = np.abs(yy - h / 2.0) - (h / 2.0 - r)
    return -(np.hypot(np.maximum(px, 0.0), np.maximum(py, 0.0)) + np.minimum(np.maximum(px, py), 0.0) - r)


def _texture(a):
    h, w = a.shape[:2]
    t = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(np.clip(a, 0, 255).astype(np.uint8)[::-1]).tobytes(), pitch=w * 4).get_texture()
    gl.glBindTexture(t.target, t.id)
    gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    return t


def _keep(lookup_key, factory):
    t = _textures.get(lookup_key)
    if t is None:
        if len(_textures) > 80: _textures.clear()
        t = _textures[lookup_key] = factory()
    return t


def _restore_blend():
    """Alpha blending of the blitted texture: pyglet.shapes turns it off at the end of each drawing, so it must be turned back on before a blit (otherwise corners and translucent background come out opaque)."""
    gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)


def border(x, y, w, h, k, highlight=0.0, background=None, opacity=None):
    """Window in the style of the mobile game's menus: translucent background (midnight blue by default; `background` and `opacity`: other color), five-stroke frame of 1.25 px at 720 p,
    rounded corners (transparent outside the frame). `highlight` (0 to 1): lighter background (pressed button)."""
    w, h = int(round(w)), int(round(h))
    if w < 4 or h < 4: return
    background = DQ_BACKGROUND if background is None else tuple(background); opacity = BACKGROUND_OPACITY if opacity is None else opacity
    def fab():
        b = max(1.0, 1.25 * k); d = _distance(w, h, 9.0 * k); n = len(DQ_EDGES)
        a = np.zeros((h, w, 4), np.float32); ring = np.clip(np.floor(d / b), 0, n).astype(int)
        for i, c in enumerate(DQ_EDGES): a[ring == i, :3] = c
        a[ring == n, :3] = np.array(background, np.float32) * (1 - highlight) + 90.0 * highlight; a[..., 3] = 255.0
        a[ring == n, 3] = 255.0 * (opacity + (1 - opacity) * highlight)
        a[..., 3] *= np.clip(d + 0.5, 0.0, 1.0)
        return _texture(a)
    t = _keep(('frame', w, h, round(k * 100), round(highlight * 10), background, round(opacity * 100)), fab)
    _restore_blend(); t.blit(int(round(x)), int(round(y)))


def plate(x, y, w, h, k, chosen=False, outline=None):
    """Background of a button like those of the mobile game's command menu: light gray border, gray gradient, rounded corners. Chosen: lighter (like a pressed game button), with no other mark.
    `outline` (r, g, b): outline of this color, thicker than the border (mouse selection)."""
    w, h = int(round(w)), int(round(h))
    if w < 4 or h < 4: return
    def fab():
        d = _distance(w, h, 6.0 * k); bw = max(1.5, 1.6 * k) if outline is None else max(2.5, 2.8 * k); t = (np.mgrid[0:h, 0:w][0] + 0.5) / h      # t: 0 at the top, 1 at the bottom
        topmost, bottom = np.array(TOP_PLATE, np.float32), np.array(BOTTOM_PLATE, np.float32)
        a = np.zeros((h, w, 4), np.float32)
        background = topmost[None, None, :] * (1 - t[..., None]) + bottom[None, None, :] * t[..., None] + (26.0 if chosen else 0.0)
        c0, c1 = ((228, 230, 226), (150, 152, 147)) if chosen else ((186, 188, 185), (112, 114, 110))
        edge = np.array(c0, np.float32)[None, None, :] * (1 - t[..., None]) + np.array(c1, np.float32)[None, None, :] * t[..., None]
        if outline is not None: edge = np.zeros_like(edge) + np.array(outline, np.float32)
        inside = (d >= bw)[..., None]
        a[..., :3] = np.where(inside, background, edge); a[..., 3] = 255.0 * np.clip(d + 0.5, 0.0, 1.0)
        return _texture(a)
    t = _keep(('plaque', w, h, round(k * 100), bool(chosen), outline), fab)
    _restore_blend(); t.blit(int(round(x)), int(round(y)))


def outline(x, y, w, h, k, color, radius=6.0):
    """Outline (ring of 2.8 px at 720 p, rounded corners, transparent interior) of the given color: mouse selection of a button."""
    w, h = int(round(w)), int(round(h))
    if w < 4 or h < 4: return
    def fab():
        d = _distance(w, h, radius * k); bw = max(2.5, 2.8 * k)
        a = np.zeros((h, w, 4), np.float32); a[..., :3] = np.array(color, np.float32)
        a[..., 3] = 255.0 * np.clip(d + 0.5, 0.0, 1.0) * (1.0 - np.clip(d - bw + 0.5, 0.0, 1.0))
        return _texture(a)
    t = _keep(('contour', w, h, round(k * 100), tuple(color)), fab)
    _restore_blend(); t.blit(int(round(x)), int(round(y)))


def draw_grid(W, H):
    """Placement grid of the screen (COLS x LINES cells): translucent white lines."""
    gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
    for i in range(COLS + 1):
        l = pyglet.shapes.Line(i * W / COLS, 0, i * W / COLS, H, thickness=1, color=(255, 255, 255)); l.opacity = 38; l.draw()
    for j in range(LINES + 1):
        l = pyglet.shapes.Line(0, j * H / LINES, W, j * H / LINES, thickness=1, color=(255, 255, 255)); l.opacity = 38; l.draw()


def battle_visible(e):
    """Is the battle speed button shown? Not during the black screen that waits for the battle scene (State.load_wait), nor when a fade to black is rising or the screen is black (start and end of the battle):
    like the field buttons, which the engine hides during fades. A fade that goes back down (battle entry) lets it appear."""
    if e.load_wait is not None: return False
    for p in (e.fade, e.background_fade):
        if p['a'] >= 0.999 or (p['n'] >= 1 and p['step'] > 0): return False
    return True


def speed_arrows(x, y, w, h, speed):
    """Battle speed as arrows, no label: a hollow triangle (gray) for "Manual", then one, two or three filled triangles ("Normal": white; "Fast": yellow; "Tres rapide": orange, warmer as it speeds up), like the
    triangular cursor of the game menus. Group centered in the (x, y, w, h) plate. Used by the battle speed button and by the battle rewind of the history."""
    from dq4_pc.persistence import settings as RG
    v = RG.battle_notch(speed)
    num = {0.0: 1, 1.0: 1, 2.0: 2, 3.0: 3}[v]; clr = {0.0: (170, 174, 182), 1.0: (255, 255, 255), 2.0: (255, 235, 130), 3.0: (255, 176, 80)}[v]
    th = h * 0.42; tw = th * 0.80; ec = tw * 0.22; total = num * tw + (num - 1) * ec           # height and width of a triangle, gap between two
    x0 = x + (w - total) / 2.0; yc = y + h / 2.0
    for i in range(num):
        a = x0 + i * (tw + ec)
        vertices = (a, yc - th / 2, a, yc + th / 2, a + tw, yc)
        if v == 0.0:                                                                         # "Manual": hollow triangle
            e = max(2.0, h * 0.045)
            pyglet.shapes.Polygon((vertices[0], vertices[1]), (vertices[2], vertices[3]), (vertices[4], vertices[5]), color=clr).draw()
            d = e * 2.1; pyglet.shapes.Polygon((a + d * 0.55, yc - th / 2 + d), (a + d * 0.55, yc + th / 2 - d), (a + tw - d * 1.1, yc), color=BOTTOM_PLATE).draw()
        else: pyglet.shapes.Triangle(*vertices, color=clr).draw()


class Buttons:
    def __init__(self, game):
        self.J = game; self.spr = {}; self.orig = {}; self.taken = None; self.press_state = None; self.editing = False; self.lookup_key = None
        self.dpad_on = False; self.dpad_dragging = False; self.cv = (0.0, 0.0); self.art = None      # D-pad held by the mouse; mouse position relative to the center (ring radius = 1); textures

    # ---- geometry
    def scale_factor(self, name_str=None):
        """Pixels per unit of the original interface (800 high), "Button size" setting included (the battle speed button: its own size)."""
        return self.J.height / 800.0 * float(self.J.reg['speed_button_size' if name_str == BATTLE else 'buttons_size'])

    def size_value(self):
        return DQ_PLATE['map'][0] * self.scale_factor()

    def anchor(self):
        """Attachment of the battle speed button to the bottom box (dict x, y, w, h in pixels, computed by the window: left edge and bottom edge of the box, size of the "Flee" plate), or None: out of battle, in
        the editor, when the player placed it themselves, or as long as no box has been seen (grid position)."""
        J = self.J; a = getattr(J, 'battle_anchor', None)
        if a is None or self.editing or J.reg['speed_button_pos'] or not speed_anchor(): return None
        from dq4_pc.core.engine import PART_BATTLE
        return a if J.engine.state.part == PART_BATTLE else None

    def _anchor_ready(self):
        """The speed button is shown only if it has a place: the one the player gave it, or, with the original menus, its anchor under the bottom box (computed by the window before drawing: never the default grid position, which is on the left of the screen)."""
        J = self.J
        if not speed_anchor(): return True                                          # no anchor: the button is at its grid cell, on the left edge, from the first frame
        return bool(J.reg['speed_button_pos']) or getattr(J, 'ui_msg', None) is None or getattr(J, 'battle_anchor', None) is not None

    def dims(self, name_str):
        """(width, height) in pixels: original plate of a button (72 x 64, 63 x 56.8...) or diameter of the D-pad ring."""
        if name_str == DPAD: c = self.dpad_diameter(); return c, c
        if name_str == BATTLE:
            a = self.anchor(); t = float(self.J.reg['speed_button_size'])
            if a and a.get('w'): return a['w'] * t, a['h'] * t       # same plate as "Flee" (at the size of the button setting)
        w, h, _ = DQ_PLATE[name_str]; k = self.scale_factor(name_str); return w * k, h * k

    def dpad_diameter(self):
        """Diameter of the D-pad ring in pixels: scale of the original interface, "D-pad size" game option, port setting."""
        d = self.J.height / 800.0 * DPAD_DIAMETER * DPAD_SCALE[self.J.engine.dpad_size()] * float(self.J.reg['dpad_size'])
        return min(d, DPAD_WIDTH_MAX * self.J.width)          # window narrower than the mobile portrait (9:16): the doubled D-pad must not stick out of the screen

    def cell(self, name_str):
        p = self.J.reg['speed_button_pos'] if name_str == BATTLE else self.J.reg['buttons_pos'].get(name_str)
        if p and len(p) == 2: return tuple(p)
        if name_str == DPAD:                                   # original: at the bottom right, half a cell from the edge
            c = self.dpad_diameter(); return (COLS - c * COLS / self.J.width - 0.6, LINES - c * LINES / self.J.height - 0.6)
        return DEFAULT[name_str]

    def rect(self, name_str):
        """(x, y, width, height) in pixels, origin at the bottom left."""
        W, H = self.J.width, self.J.height
        if name_str == BAR: h = BAR_HEIGHT * H / 800.0; return 0.0, H - h, float(W), h
        w, h = self.dims(name_str)
        if name_str == BATTLE:
            a = self.anchor()
            if a: return min(max(0.0, a['x']), W - w), min(max(0.0, a['y'] - h), H - h), w, h         # under the bottom left corner of the box (the top of the plate touches its bottom edge)
        col, lig = self.cell(name_str)
        x = min(max(0.0, col * W / COLS), W - w); y = min(max(0.0, H - lig * H / LINES - h), H - h)
        return x, y, w, h

    def under(self, x, y, visible_ones):
        if DPAD in visible_ones:
            rx, ry, c, _ = self.rect(DPAD)
            if math.hypot(x - rx - c / 2, y - ry - c / 2) <= c / 2 * DPAD_GRAB: return DPAD
        for name_str in reversed(BUTTONS):
            if name_str not in visible_ones: continue
            rx, ry, w, h = self.rect(name_str)
            if rx <= x <= rx + w and ry <= y <= ry + h: return name_str
        return None

    def visible_ones(self):
        """Buttons to show: those the engine allows (outside the Esc menu, battle, screen effects); in battle, only the battle speed button (outside the black screen and fade to black)."""
        J = self.J
        if J.pause.opened or J.engine.state.effect is not None or getattr(J.engine.state, 'screen_effect', None) is not None: return ()
        if getattr(J.engine, 'end_roll', None) is not None: return ()                                  # (the end of the game: the credits and "The End" take the whole screen)
        from dq4_pc.core.engine import PART_BATTLE, PART_TOWN
        if J.engine.state.part == PART_BATTLE: return (BATTLE,) if J.reg['speed_button'] and battle_visible(J.engine.state) and self._anchor_ready() else ()        # (the speed button has its own display setting)
        if not J.reg['buttons']: return ()
        if J.map_open: return ()                                                  # map open: no more buttons on screen (the "mode" button and the back button are those of the map window, type 22)
        f = J.engine.flags()
        if (f & (8 | 0x30047)) != 8: return ()
        return tuple(n for n in NAMES if n != 'map' or f & 0x20) + ((DPAD,) if J.reg['dpad'] else ()) + ((BAR,) if J.reg['rotation_bar'] and J.engine.state.part == PART_TOWN else ())      # (the world map does not rotate)

    def allowed(self, name_str):
        """Does the engine allow this field button (Map, Commands, Chat) right now, whether or not the "boutons" setting shows it? The keyboard plays the button's sound effect there (the same situations as with the finger)."""
        J = self.J
        from dq4_pc.core.engine import PART_BATTLE
        if J.pause.opened or J.engine.state.effect is not None or getattr(J.engine.state, 'screen_effect', None) is not None or J.engine.state.part == PART_BATTLE or J.map_open: return False
        f = J.engine.flags()
        return (f & (8 | 0x30047)) == 8 and (name_str != 'map' or bool(f & 0x20))

    # ---- mouse
    def press(self, x, y, visible_ones):
        n = self.under(x, y, visible_ones)
        if n == DPAD: self.dpad_on = True; self.dpad_dragging = False; self.dpad_drag(x, y)
        elif n: self.press_state = n
        elif BAR in visible_ones and y >= self.rect(BAR)[1]: n = BAR                      # the bar has its own gesture (Game._bar_press): no state here, and it comes after the buttons and the D-pad, which may overlap it
        return n

    def bar_reset_zone(self, x):
        """Is the point at x on the central pattern of the bar (the three cells, cube in the middle)? A tap that stays there brings the camera back to north (a click on the cube is enough)."""
        return abs(x - self.J.width / 2.0) <= 1.5 * BAR_HEIGHT * self.J.height / 800.0

    def bar_end_at(self, x):
        """-1 / +1 if x is in the left / right end zone of the bar (BAR_END icons wide, where the two rotation icons are): the camera turns that way while the button is held; else 0."""
        z = (BAR_END + BAR_MARGIN) * BAR_HEIGHT * self.J.height / 800.0
        return -1 if x < z else 1 if x > self.J.width - z else 0

    def let_go(self, x, y, visible_ones):
        """-> name of the button (full click: release on the pressed button) or None."""
        n, self.press_state = self.press_state, None
        return n if n and self.under(x, y, visible_ones) == n else None

    # ---- position editing
    def take(self, x, y, names=EDITOR_NAMES):
        n = self.under(x, y, names)
        if n: rx, ry = self.rect(n)[:2]; self.taken = (n, x - rx, y - ry)
        return n

    def move_to(self, x, y):
        if not self.taken: return
        n, dx, dy = self.taken; W, H = self.J.width, self.J.height; w, h = self.dims(n)
        px = min(max(0.0, x - dx), W - w); py = min(max(0.0, y - dy), H - h)         # bottom left corner requested
        col = px * COLS / W; lig = (H - py - h) * LINES / H
        if self.J.reg['buttons_snap']: col, lig = float(round(col)), float(round(lig))
        else: col, lig = round(col, 2), round(lig, 2)
        col = min(max(0.0, col), COLS - w * COLS / W); lig = min(max(0.0, lig), LINES - h * LINES / H)
        if n == BATTLE: self.J.reg['speed_button_pos'] = [col, lig]; return
        pos = dict(self.J.reg['buttons_pos']); pos[n] = [col, lig]; self.J.reg['buttons_pos'] = pos

    def place(self): self.taken = None

    # ---- D-pad with the mouse
    def dpad_drag(self, x, y):
        """Mouse moved (or pressed): position relative to the center of the ring, in radii."""
        rx, ry, c, _ = self.rect(DPAD); r = c / 2
        self.cv = ((x - rx - r) / r, (y - ry - r) / r)
        if math.hypot(*self.cv) >= DEAD_ZONE: self.dpad_dragging = True            # left the central circle: it is a drag (a direction), no longer a tap

    def dpad_drop(self):
        self.dpad_on = False; self.dpad_dragging = False; self.cv = (0.0, 0.0)

    def dpad_release(self):
        """Mouse button released on the D-pad. -> True if it was a TAP on the central circle: pressed then released without ever leaving it (no drag); the game sees the action key there (like the A key)."""
        tap = self.dpad_on and not self.dpad_dragging
        self.dpad_drop()
        return tap

    def dpad_sector(self):
        """45-degree sector of the held direction (0 up, 1 up-right, 2 right... clockwise) or None (dead zone, D-pad not held)."""
        if not self.dpad_on: return None
        vx, vy = self.cv
        if math.hypot(vx, vy) < DEAD_ZONE: return None
        return int(((math.degrees(math.atan2(vx, vy)) + 22.5) % 360.0) // 45.0)

    def dpad_run(self):
        """Is the D-pad held at the EDGE of the ring (at TRAVEL_THRESHOLD of the radius or more, in a direction)? The hero then runs (like with the accelerator key); closer to the center, he walks normally."""
        return self.dpad_on and self.dpad_sector() is not None and math.hypot(*self.cv) >= TRAVEL_THRESHOLD

    def dpad_bits(self):
        """Direction of the D-pad as game gamepad bits (up / down / left / right), like that of the movement keys."""
        if self.dpad_on and DPAD not in self.visible_ones(): self.dpad_drop(); return 0
        k = self.dpad_sector()
        if k is None: return 0
        from dq4_pc.core import engine as ENGINE
        return (ENGINE.UP, ENGINE.UP | ENGINE.RIGHT, ENGINE.RIGHT, ENGINE.DOWN | ENGINE.RIGHT, ENGINE.DOWN, ENGINE.DOWN | ENGINE.LEFT, ENGINE.LEFT, ENGINE.UP | ENGINE.LEFT)[k]

    # ---- drawing
    def _icon(self, name_str):
        """Original 32 x 32 icon (RGBA), color of the transparent pixels propagated by one pixel (no dark fringe when the filter blends the edges)."""
        a = self.orig.get(name_str)
        if a is None:
            from PIL import Image
            from dq4_pc.world import hd as HD
            f = os.path.join(self.J.args.cache, 'ui_MenuTexture.png')
            try: im = Image.open(f).convert('RGBA'); n = ICON[name_str]; x0, y0 = n % 32 * 32, ICON_ROW + n // 32 * 32; a = np.array(im.crop((x0, y0, x0 + 32, y0 + 32)))
            except Exception: a = np.zeros((32, 32, 4), np.uint8); a[..., 3] = 120
            a = self.orig[name_str] = HD._dilate(a, 1)
        return a

    def _outline(self, name_str):
        """Dark outline of an icon (32 x 32, black at alpha 200): one original pixel around the opaque pixels, EXCEPT in the gaps between the dashes of the rotation bar's arrows (a transparent pixel with an
        opaque one at most 2 pixels to its left and to its right): the old outline (8 shifted black copies) filled those gaps with black bars."""
        a = self.orig.get(name_str + '#o')
        if a is None:
            op = self._icon(name_str)[..., 3] > 40; p = np.pad(op, 2)
            sh = lambda dy, dx: p[2 + dy:2 + dy + 32, 2 + dx:2 + dx + 32]
            ring = np.zeros_like(op)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1): ring |= sh(dy, dx)
            gap = (sh(0, -1) | sh(0, -2)) & (sh(0, 1) | sh(0, 2))
            a = np.zeros((32, 32, 4), np.uint8); a[ring & ~op & ~gap] = (0, 0, 0, 200)
            self.orig[name_str + '#o'] = a
        return a

    def _sprite(self, name_str, c):
        """Icon sprite for a button of c pixels per side. The icon is first enlarged by an integer n (nearest neighbor: each original pixel becomes a sharp block), then
        scaled down to the exact pixel size by the linear filter: pixels stay crisp, only the boundary between two pixels is softened (a direct linear enlargement from 32 to 72 px smeared them)."""
        n = max(1, int(np.ceil(c / 32.0 - 1e-6)))
        s = self.spr.get((name_str, n))
        if s is None:
            a = np.repeat(np.repeat(self._outline(name_str[:-2]) if name_str.endswith('#o') else self._icon(name_str), n, axis=0), n, axis=1); t_ = 32 * n
            img = pyglet.image.ImageData(t_, t_, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes(), pitch=t_ * 4)
            t = img.get_texture(); gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            for wrap in (gl.GL_TEXTURE_WRAP_S, gl.GL_TEXTURE_WRAP_T): gl.glTexParameteri(t.target, wrap, gl.GL_CLAMP_TO_EDGE)          # (a scaled icon must never sample its opposite edge: the stray lines of the rotation bar in a window)
            s = self.spr[(name_str, n)] = pyglet.sprite.Sprite(t)
        return s, n

    def _plate(self, x, y, w, h, pressed, name_str=None):
        """Original plate of the button ("Button" sheet, part 7, 9 slices with 16-unit corners, "pressed" image when the button is down), like the buttons of the game windows: Render.plate.
        -> False without the original menus (the fallback draws the background)."""
        r = getattr(self.J, 'ui_render', None)
        return bool(r is not None and r.plate(x, y, w, h, (self.J.width, self.J.height), pressed, corner=PLATE_CORNER * self.scale_factor(name_str)))

    def _battle_arrows(self, x, y, w, h):
        speed_arrows(x, y, w, h, self.J.reg['battle_speed'])

    def _dpad_art(self):
        """D-pad sprites (pieces of the "Button" sheet, anchored at the center to rotate around)."""
        if self.art is None:
            from PIL import Image
            from dq4_pc.world import hd as HD
            try: im = np.array(Image.open(os.path.join(self.J.args.cache, 'ui_Button.png')).convert('RGBA'))
            except Exception: im = np.zeros((512, 512, 4), np.uint8)
            self.art = {}
            for name_str, (x, y, w, h) in DPAD_ART.items():
                a = HD._dilate(im[y:y + h, x:x + w].copy(), 1)
                t = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes(), pitch=w * 4).get_texture()
                gl.glBindTexture(t.target, t.id)
                gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
                t.anchor_x = w / 2.0; t.anchor_y = h / 2.0
                self.art[name_str] = pyglet.sprite.Sprite(t)
        return self.art

    def action_possible(self):
        """Is an action possible now? (the D-pad then animates, as on mobile.) Yes when the game makes the central circle blink (packet 19, TouchPad.SetPadBlink, tutorial); otherwise, on the free
        field, when an icon bubble is shown (the game puts the bubble on the target the hero can talk to, search or open: assumed, the original game ties the D-pad blink only to its tutorial)."""
        e = self.J.engine.state
        if getattr(e, 'pad_blink', False): return True
        free = getattr(self.J, '_terrain_free', None)
        if free is not None and not free(): return False
        return any(ic.get('pos') is not None and ic.get('alpha', 0.0) > 0.02 for ic in getattr(e, 'icons', {}).values())

    def _dpad(self, editing=False):
        """D-pad: ring, eight pills (the one of the held direction lights up), ball that follows the mouse. Always opaque; the orange ball and its halo (SetVisibleColMove) pulse when an action is possible
        (see action_possible); MOVE_WAIT_TIME / MOVE_LIMIT_ALPHA are unused constants."""
        art = self._dpad_art(); x, y, c, _ = self.rect(DPAD); cx, cy = x + c / 2, y + c / 2; k = c / 256.0
        sect = self.dpad_sector()
        a = 1.0                                                                            # (hidden, it stays whole in the editor: the "Hidden" veil from pause.py darkens it like the other elements)
        def place(name_str, px, py, rot=0.0, op=1.0):
            sp = art[name_str]; sp.update(x=px, y=py, scale=k, rotation=rot); sp.opacity = int(255 * a * op); sp.draw()
        place('ring', cx, cy)
        for i in range(8):
            ang = i * 45.0; r = DOT_RADIUS * c
            place('pill_on' if sect == i else 'pill', cx + math.sin(math.radians(ang)) * r, cy + math.cos(math.radians(ang)) * r, ang)
        vx, vy = self.cv if self.dpad_on else (0.0, 0.0); n = math.hypot(vx, vy)
        if n > BALL_TRAVEL: vx, vy = vx * BALL_TRAVEL / n, vy * BALL_TRAVEL / n
        bx, by = cx + vx * c / 2, cy + vy * c / 2
        if self.dpad_on and (not self.dpad_dragging or self.dpad_run()): place('halo', bx, by); place('ball_on', bx, by)                 # tap in progress, or travel (pointer at the edge of the ring): lit ball
        elif self.action_possible() and not editing:                                                                  # an action is possible (bubble shown) or the game makes the central circle blink: the orange ball and its halo fade in and out smoothly
            ph = 0.5 - 0.5 * math.cos(2.0 * math.pi * (time.perf_counter() % BLINK_PERIOD) / BLINK_PERIOD)
            place('ball', bx, by); place('halo', bx, by, 0.0, ph); place('ball_on', bx, by, 0.0, ph)
        else: place('ball', bx, by)

    def _bar(self):
        """Rotation bar, like the mobile game's l_RotBar (TouchPad.Start): icons only, no background. In the middle the three-cell pattern (arrows and cube, icons 42 to 44), at the two ends the rotate-left icon (0) and the rotate-right icon (1).
        On mobile the whole thing fits within the 450 units of the interface; here (wider window) the two rotation icons are stuck to the left and right edges, the pattern stays in the center, the grab area covers the full width."""
        x, y, w, s = self.rect(BAR); cx = x + w / 2.0; g = getattr(self.J, 'bar_gesture', None); active = g is not None and g.in_progress
        s = float(round(s)); y = float(round(y)); c0 = round(cx - 1.5 * s); m = round(BAR_MARGIN * s)      # whole pixels: the three cells of the pattern meet exactly, with no seam
        icons = (('rot_l', x + m), ('bar_1', c0), ('bar_2', c0 + s), ('bar_3', c0 + 2 * s), ('rot_r', x + w - s - m))
        for name_str, px in icons:                                                              # 1. all the dark outlines first (the thin dashes were hardly visible on a bright map), never inside the gaps of the dashes:
            sprite, n = self._sprite(name_str + '#o', s); sprite.update(x=px, y=y, scale=s / (32.0 * n)); sprite.draw()
        for name_str, px in icons:                                                              # 2. then the icons
            sprite, n = self._sprite(name_str, s)
            sprite.update(x=px, y=y, scale=s / (32.0 * n)); sprite.color = (255, 255, 255); sprite.opacity = 255 if active else 235; sprite.draw()

    def draw_all(self, visible_ones, editing=False, grid=True):
        if not visible_ones and not editing: return
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        W, H = self.J.width, self.J.height
        if editing:                                              # dark veil and grid (optional)
            background = pyglet.shapes.Rectangle(0, 0, W, H, color=(0, 0, 0)); background.opacity = 110; background.draw()
            if grid: draw_grid(W, H)
        if BAR in visible_ones:
            self._bar()
            if editing:
                x, y, w, h = self.rect(BAR)
                pyglet.shapes.Box(x, y, w, h, thickness=2, color=(255, 235, 130)).draw()
                label = self.J._lbl(tr(CAPTION[BAR]), max(11.0, h / 4.0), (255, 235, 130, 255)); label.x = x + w / 2 - label.content_width / 2; label.y = y - label.content_height - 4; label.draw()          # (the bar is at the top: its name below it)
        for name_str in BUTTONS:
            if name_str not in visible_ones: continue
            x, y, w, h = self.rect(name_str); active = self.press_state == name_str or (self.taken is not None and self.taken[0] == name_str)
            if name_str == BATTLE:                                    # like the "Flee" plate: a small game window frame (translucent black background, five-stroke frame) that carries the button plate
                k = h / 56.0; border(x, y, w, h, k, 0.0, (0, 0, 0), GAME_OPACITY); m = 5.0 * k
                actual = self._plate(x + m, y + m, w - 2 * m, h - 2 * m, active, name_str)
                if not actual: border(x + m, y + m, w - 2 * m, h - 2 * m, k, 0.45 if active else 0.0)
            else:
                actual = self._plate(x, y, w, h, active)
                if not actual: border(x, y, w, h, h / 60.0, 0.45 if active else 0.0)    # without the original menus: drawn button background (midnight-blue window with a white frame, like those of the mobile game)
            if name_str == BATTLE: self._battle_arrows(x, y, w, h)
            else:
                ci = DQ_PLATE[name_str][2] * self.scale_factor(); s, n = self._sprite(name_str, ci)
                s.update(x=x + (w - ci) / 2, y=y + (h - ci) / 2, scale=ci / (32.0 * n))
                s.color = (170, 170, 170) if active and not actual else (255, 255, 255); s.opacity = 255 if editing else 235
                s.draw()
            if editing:
                pyglet.shapes.Box(x, y, w, h, thickness=2, color=(255, 235, 130)).draw()
                label = self.J._lbl(tr(CAPTION[name_str]), max(11.0, h / 5.0), (255, 235, 130, 255)); label.x = min(max(4.0, x + w / 2 - label.content_width / 2), W - label.content_width - 4); label.y = min(y + h + 4, H - label.content_height - 2); label.draw()
        if DPAD in visible_ones:
            self._dpad(editing)
            if editing:
                x, y, c, _ = self.rect(DPAD); active = self.taken is not None and self.taken[0] == DPAD
                pyglet.shapes.Box(x, y, c, c, thickness=2, color=(255, 235, 130)).draw()
                label = self.J._lbl(tr(CAPTION[DPAD]), max(11.0, self.size_value() / 5.0), (255, 235, 130, 255)); label.x = min(max(4.0, x + c / 2 - label.content_width / 2), W - label.content_width - 4); label.y = min(y + c + 4, H - label.content_height - 2); label.draw()
