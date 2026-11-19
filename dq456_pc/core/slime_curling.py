"""Dragon Quest VI's slime curling: what Unity's SlimeCurlingPort and its two behaviours do with the mini-game's two ports (menu ports of category 5).

The engine draws the whole game itself (the course, the slime, the coins: a 3D scene like a town). Unity only gives it the touch screen, in "LCD" units: x from 0 (left edge of the phone)
to LCD_WIDTH (right edge), y from the middle of the screen, downwards, LCD_HEIGHT across (SlimeCurling__Behaviour.Awake: 256 units across, 256 / aspect up).
- type 0, SlimeCurling__TouchPanel: at each frame, unless the game's flag bit 16 is up (Global.Flag), it sends [x, y, touching] (the first touch; [0, LCD_HEIGHT / 2, 0] without one).
  The engine turns it on and off with [on] (GameObject.SetActive).
- type 1, SlimeCurling__ConvertPosition: the engine sends a point of the world (three floats, each one in two shorts, low first); Unity answers its place on the screen [x, y]
  (Camera.WorldToViewportPoint of the scene camera, in the same units), only when it moved.
"""
import struct

PORT_CATEGORY = 5                    # [port, 1, category, type] on port 0: MenuPortSystem creates a SlimeCurlingPort
TOUCH_PANEL, CONVERT_POSITION = 0, 1           # the port's type
LCD_WIDTH = 256.0                    # SlimeCurling__Behaviour.LCD_WIDTH
TOUCH_PAUSED = 0x10000               # Global.Flag bit 16 (byte 2, bit 0): SlimeCurling__TouchPanel.Update sends nothing
MOVED = 1e-10                        # SlimeCurling__ConvertPosition: square of the distance from the last answer above which it answers again


def lcd_height(aspect):
    """SlimeCurling__Behaviour.LCD_HEIGHT: 256 / the phone's aspect (width / height)."""
    return LCD_WIDTH / aspect


def new():
    return {'live': True, 'ports': {}, 'touch_on': True, 'point': None, 'answered': (0.0, 0.0, 0.0)}


def add_port(st, port, kind):
    """A port of the mini-game created (SlimeCurlingPort constructor); the touch panel starts active (its object is created active), the converter inactive (it only answers)."""
    st['ports'][port] = kind; st['live'] = True
    if kind == TOUCH_PANEL: st['touch_on'] = True


def close_port(st, port):
    st['ports'].pop(port, None)
    if not st['ports']: st['live'] = False


def port_of(st, kind):
    for p, k in st['ports'].items():
        if k == kind: return p
    return None


def floats(a):
    """Floats of a message (MenuPort.Param.GetFloat: each one in two shorts, the low one first)."""
    out = []
    for i in range(0, len(a) - 1, 2): out.append(struct.unpack('<f', struct.pack('<HH', a[i] & 0xffff, a[i + 1] & 0xffff))[0])
    return out


def notice(st, port, a):
    """SlimeCurlingPort.NoticeReceive: the touch panel's [on]; the converter's point (kept until the window answers)."""
    kind = st['ports'].get(port)
    if kind == TOUCH_PANEL and a: st['touch_on'] = (a[0] & 0xffff) != 0
    elif kind == CONVERT_POSITION and len(a) >= 6: st['point'] = tuple(floats(a[:6]))


def short(v):
    """An integer as Unity stores it in a message (strh: its low 16 bits, signed)."""
    return ((int(v) + 0x8000) & 0xffff) - 0x8000


def to_lcd(vx, vy, aspect):
    """A viewport point of the phone's screen (0 to 1, from the bottom left) -> (x, y) in LCD units, truncated like `(int)` (an infinite value gives int.MinValue, whose low 16 bits are 0)."""
    def trunc(v): return 0 if v in (float('inf'), float('-inf')) or v != v else short(int(v))
    return trunc(vx * LCD_WIDTH), trunc((0.5 - vy) * lcd_height(aspect))


def touch_message(st, flags, touching, viewport, aspect):
    """SlimeCurling__TouchPanel.Update -> the message for the engine, or None (panel off, or the game's flag bit 16 up). `viewport`: the pointer's place on the phone's screen (0 to 1)."""
    if not st['live'] or not st['touch_on'] or port_of(st, TOUCH_PANEL) is None or flags & TOUCH_PAUSED: return None
    x, y = to_lcd(viewport[0], viewport[1], aspect) if touching else to_lcd(0.0, 0.0, aspect)          # (no touch: the zero vector's place, the bottom left corner)
    return [x, y, 1 if touching else 0]


def convert_answer(st, viewport, aspect):
    """SlimeCurling__ConvertPosition.NoticeReceive: the point's place on the screen -> [x, y] for the engine, or None when it has not moved. `viewport`: (vx, vy) of the point."""
    st['point'] = None
    x = viewport[0] * LCD_WIDTH; y = (0.5 - viewport[1]) * lcd_height(aspect)
    ax, ay, az = st['answered']
    if (x - ax) ** 2 + (y - ay) ** 2 + az * az < MOVED: return None
    st['answered'] = (x, y, 0.0)
    inf = lambda v: v in (float('inf'), float('-inf'))
    return [0 if inf(x) else short(int(x)), 0 if inf(y) else short(int(y))]


def window_to_viewport(wx, wy, width, height, base_height, phone_aspect):
    """A window pixel (from the bottom left) -> the place on the phone's screen (viewport, 0 to 1 from its bottom left), the phone's screen centered on the window like the scene:
    the window's height shows `base_height` short sides of the phone (helpers.portrait_base_height), so one LCD unit is height / (256 x base_height) pixels."""
    s = height / (LCD_WIDTH * base_height)
    x = LCD_WIDTH / 2.0 + (wx - width / 2.0) / s; y = (height / 2.0 - wy) / s
    return x / LCD_WIDTH, 0.5 - y / lcd_height(phone_aspect)
