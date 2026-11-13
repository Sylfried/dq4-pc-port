"""Gamepad: the controllers that pyglet reads become pseudo key presses (see persistence/pad_inputs.py).

Once per game frame, `Gamepad.poll` compares the inputs held now with those held at the previous frame and dispatches `on_key_press` / `on_key_release` on the window with the pseudo key code of each
input that changed. The window's `KeyStateHandler` records them in `key_list`, so the game reads a gamepad like a keyboard (`_held(action)`), and the menus receive the same events as for a key."""
import importlib, sys, time
from pyglet.event import EventDispatcher
from dq4_pc.persistence import pad_inputs as PI

PRESS, RELEASE = 0.5, 0.3          # travel (0 to 1) of a stick or trigger that presses an input, and below which it is released again (hysteresis: no flicker around the threshold)
BUTTONS = (('a', 'PAD_A'), ('b', 'PAD_B'), ('x', 'PAD_X'), ('y', 'PAD_Y'), ('leftshoulder', 'PAD_LB'), ('rightshoulder', 'PAD_RB'),
           ('back', 'PAD_BACK'), ('start', 'PAD_START'), ('leftstick', 'PAD_L3'), ('rightstick', 'PAD_R3'))


TOUCHPAD_BUTTON = 13          # raw DirectInput button of the PlayStation touch pad click (DualShock 4 and DualSense: "touchpad:b13" / "misc1:b13" in the SDL controller base; pyglet does not name it)


def _axis(c, n):
    v = getattr(c, n, 0.0)
    return float(v) if isinstance(v, (int, float)) and v == v else 0.0


def sticks(c):
    """(lx, ly, rx, ry) of a controller, y positive DOWNwards (SDL convention; an XInput controller, `y_up`, has it upwards)."""
    lx, ly, rx, ry = _axis(c, 'leftx'), _axis(c, 'lefty'), _axis(c, 'rightx'), _axis(c, 'righty')
    if getattr(c, 'y_up', False): ly, ry = -ly, -ry
    return lx, ly, rx, ry


def strengths(c, family=None, mouse='off'):
    """{input name: travel from 0 to 1} of a pyglet controller. The d-pad and the left stick feed the same four inputs (PAD_UP...). `mouse` ('right', 'left', 'off'): the stick that moves the mouse
    pointer gives no input. `family` 'PS': the touch pad click (raw button 13) is the input PAD_TOUCH."""
    s = {name: 1.0 if getattr(c, attr, False) else 0.0 for attr, name in BUTTONS}
    s['PAD_LT'] = _axis(c, 'lefttrigger'); s['PAD_RT'] = _axis(c, 'righttrigger')
    dx, dy = _axis(c, 'dpadx'), _axis(c, 'dpady'); lx, ly, rx, ry = sticks(c)
    if mouse == 'left': lx = ly = 0.0
    if mouse == 'right': rx = ry = 0.0
    s['PAD_UP'] = max(dy, -ly, 0.0); s['PAD_DOWN'] = max(-dy, ly, 0.0); s['PAD_LEFT'] = max(-dx, -lx, 0.0); s['PAD_RIGHT'] = max(dx, lx, 0.0)
    s['PAD_RS_UP'] = max(-ry, 0.0); s['PAD_RS_DOWN'] = max(ry, 0.0); s['PAD_RS_LEFT'] = max(-rx, 0.0); s['PAD_RS_RIGHT'] = max(rx, 0.0)
    if family == 'PS':
        bc = getattr(c, '_button_controls', None) or ()
        s['PAD_TOUCH'] = 1.0 if len(bc) > TOUCHPAD_BUTTON and getattr(bc[TOUCHPAD_BUTTON], 'value', False) else 0.0
    return s


DEAD_ZONE = 0.2              # stick travel below which the mouse pointer does not move
POINTER_TIME = 1.0           # seconds for the pointer to cross the window's width with the stick fully tilted (the speed grows as the square of the tilt beyond the dead zone: fine aiming)
AWAKE = 3.0                  # seconds after the stick last moved the pointer during which the Action input clicks where the pointer is (afterwards it is the Action key again)
SYNC = 2.0                   # pixels: a pointer farther than this from the stick's own (fractional) position was moved by the real mouse (the pointer the system gives back may differ by a pixel)


class PadMouse:
    """The mouse pointer moved by a stick (the right stick; no longer a setting): moves the system pointer over the window (the game reads it like the mouse: hover, menus) and, for
    AWAKE seconds after a move, makes the input bound to "Action" a left click at the pointer."""
    def __init__(self, win):
        self.win = win; self.pos = None; self.moved_at = -1e9; self.t = None

    def awake(self, now=None):
        return ((time.monotonic() if now is None else now) - self.moved_at) < AWAKE

    def move(self, x, y, now=None):
        """Stick (x, y), y positive downwards -> pointer moved (dispatches on_mouse_motion). -> True if it moved."""
        now = time.monotonic() if now is None else now; dt = 0.0 if self.t is None else min(0.1, max(0.0, now - self.t)); self.t = now
        m = (x * x + y * y) ** 0.5
        if m <= DEAD_ZONE or dt <= 0.0: return False
        w, h = float(getattr(self.win, 'width', 1280)), float(getattr(self.win, 'height', 720))
        real = getattr(self.win, 'mouse', None)
        if self.pos is None or (real and max(abs(real[0] - self.pos[0]), abs(real[1] - self.pos[1])) > SYNC):          # the real mouse moved since: the stick starts from where the pointer is
            mx, my = real or (w / 2, h / 2); self.pos = [float(mx), float(my)]
        k = ((m - DEAD_ZONE) / (1.0 - DEAD_ZONE)) ** 2 * w / POINTER_TIME * dt / m
        ox, oy = self.pos; self.pos = [min(w - 1, max(0.0, ox + x * k)), min(h - 1, max(0.0, oy - y * k))]
        nx, ny = int(self.pos[0]), int(self.pos[1]); self.moved_at = now
        try: self.win.set_mouse_position(nx, ny)                     # (the system pointer follows: visible, and the game's own reading of the mouse agrees)
        except Exception: pass
        EventDispatcher.dispatch_event(self.win, 'on_mouse_motion', nx, ny, nx - int(ox), ny - int(oy))
        return True

    def click(self, press):
        x, y = int(self.pos[0]), int(self.pos[1])
        EventDispatcher.dispatch_event(self.win, 'on_mouse_press' if press else 'on_mouse_release', x, y, 1, 0)          # (1 = pyglet.window.mouse.LEFT)


VENDOR_FAMILY = {'5e04': 'XB', '4c05': 'PS', '7e05': 'NS'}          # USB vendors Microsoft (0x045E), Sony (0x054C), Nintendo (0x057E) as they appear, bytes swapped, in the SDL-style guid that pyglet builds (pyglet.input.controller.create_guid)
NAME_FAMILY = (('XB', ('xbox', 'x-box', 'xinput')), ('PS', ('playstation', 'dualshock', 'dualsense', 'ps3', 'ps4', 'ps5', 'sony', 'wireless controller')), ('NS', ('nintendo', 'switch', 'joy-con', 'pro controller')))


def family_of(c):
    """Family of a pyglet controller, which decides the logos shown in the Controls menu: 'XB' Xbox, 'PS' PlayStation, 'NS' Nintendo, or None when it is not recognized."""
    guid = str(getattr(c, 'guid', '') or '').lower(); name = str(getattr(c, 'name', '') or '').lower()
    if guid == 'xinputcontroller': return 'XB'
    for family, words in NAME_FAMILY:
        if any(w in name for w in words): return family
    if len(guid) == 32 and guid[8:12] in VENDOR_FAMILY and guid[4:8] == '0000': return VENDOR_FAMILY[guid[8:12]]
    return None


XI_BUTTONS = (('start', 0x10), ('back', 0x20), ('leftstick', 0x40), ('rightstick', 0x80), ('leftshoulder', 0x100), ('rightshoulder', 0x200), ('a', 0x1000), ('b', 0x2000), ('x', 0x4000), ('y', 0x8000))
XI_DPAD = (0x1, 0x2, 0x4, 0x8)          # up, down, left, right
SCAN_EVERY = 2.0                        # seconds between two looks at the XInput slots that have no controller (asking for an empty slot at every frame is slow on old XInput libraries)


def load_xinput():
    """-> function `get(slot)` (0 to 3) giving (buttons, left trigger, right trigger, lx, ly, rx, ry) of the XInput controller in that slot, or None if the slot is empty; None itself when XInput is not there (not Windows)."""
    if sys.platform != 'win32': return None
    import ctypes
    for name in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
        try: dll = ctypes.WinDLL(name); break
        except OSError: continue
    else: return None

    class Gamepad_(ctypes.Structure): _fields_ = [('buttons', ctypes.c_ushort), ('lt', ctypes.c_ubyte), ('rt', ctypes.c_ubyte), ('lx', ctypes.c_short), ('ly', ctypes.c_short), ('rx', ctypes.c_short), ('ry', ctypes.c_short)]
    class State(ctypes.Structure): _fields_ = [('packet', ctypes.c_ulong), ('pad', Gamepad_)]

    def get(slot):
        st = State()
        if dll.XInputGetState(slot, ctypes.byref(st)) != 0: return None          # (ERROR_DEVICE_NOT_CONNECTED)
        p = st.pad; return p.buttons, p.lt, p.rt, p.lx, p.ly, p.rx, p.ry
    return get


class XInputPad:
    """An Xbox controller read straight from the XInput library, once per frame, with the attributes of a pyglet controller (pyglet's own XInput reader, which runs in a thread and posts its changes through the event loop,
    gave nothing on an Xbox One controller over Bluetooth, cause not found). `get`: see load_xinput. y axes positive upwards (`y_up`), like pyglet's XInput controllers."""
    guid = 'xinputcontroller'; y_up = True

    def __init__(self, get, slot):
        self.get, self.slot = get, slot; self.name = 'Xbox controller %d (XInput)' % (slot + 1); self.connected = False; self.refresh()

    def refresh(self):
        """Reads the slot again: sets the attributes (all at rest when the slot is empty) and `connected`."""
        state = self.get(self.slot); self.connected = state is not None
        b, lt, rt, lx, ly, rx, ry = state or (0,) * 7
        for name, mask in XI_BUTTONS: setattr(self, name, bool(b & mask))
        up, down, left, right = (1.0 if b & m else 0.0 for m in XI_DPAD); self.dpadx, self.dpady = right - left, up - down
        self.lefttrigger, self.righttrigger = lt / 255.0, rt / 255.0
        self.leftx, self.lefty, self.rightx, self.righty = (max(-1.0, v / 32767.0) for v in (lx, ly, rx, ry))


class Gamepad:
    """The connected controllers of a window. `manager`: a `pyglet.input.ControllerManager` (a fake one in the tests); by default pyglet's, if the platform has one."""

    def __init__(self, window, manager=None, xinput='auto'):
        self.win = window; self.pads = []; self.held = set(); self.manager = manager; self.active = None; self.seen = set(); self._scan_at = 0.0          # active: the controller that was used last
        self.mouse = PadMouse(window); self.clicking = set()          # (inputs pressed as a mouse click: released as a click too)
        get = load_xinput() if xinput == 'auto' else xinput
        self.direct = [XInputPad(get, i) for i in range(4)] if get else []          # the four XInput slots: read here, not through pyglet
        if manager is None:
            try:
                self.manager = manager = importlib.import_module('pyglet.input').ControllerManager()
            except Exception as ex:
                print('Gamepad: not available (%r)' % (ex,), flush=True); return
        manager.push_handlers(on_connect=self._connect, on_disconnect=self._disconnect)
        for c in manager.get_controllers(): self._connect(c)

    def _connect(self, controller):
        if controller in self.pads: return
        if str(getattr(controller, 'guid', '')).lower() == 'xinputcontroller':
            if self.direct: return                           # (read directly)
            controller.y_up = True
        try: controller.open()
        except Exception as ex: print('Gamepad: %r cannot be opened (%r)' % (getattr(controller, 'name', '?'), ex), flush=True); return
        self.pads.append(controller); print('Gamepad: %r connected (family %s)' % (getattr(controller, 'name', '?'), family_of(controller)), flush=True)

    def release(self):
        """The game closes (or starts again in another language): the controllers are released and the manager no longer calls this object (the next game opens them again)."""
        if self.manager is not None:
            try: self.manager.remove_handlers(on_connect=self._connect, on_disconnect=self._disconnect)
            except Exception: pass
        for c in self.pads:
            try: c.close()
            except Exception: pass
        self.pads = []; self.held = set(); self.active = None

    def _disconnect(self, controller):
        if controller in self.pads: self.pads.remove(controller)
        if self.active is controller: self.active = None

    def poll(self, active=True):
        """Presses and releases the pseudo keys that changed since the last call. `active` false (the window has lost focus): every held input is released and none is read. The stick chosen
        for the mouse moves the pointer; while it is awake, the "Action" input clicks."""
        now = set(); pads = self.pads + self._direct_pads(); reg = getattr(self.win, 'reg', None); aim = None
        stick = PI.MOUSE_STICK if reg is not None else 'off'          # (the right stick always moves the pointer; the option is gone)
        if active:
            for c in pads:
                fam = family_of(c)
                for name, v in strengths(c, fam, stick).items():
                    if v > (RELEASE if name in self.held else PRESS):
                        now.add(name); self.active = c
                        if id(c) not in self.seen: self.seen.add(id(c)); print('Gamepad: first input read from %r (%s)' % (getattr(c, 'name', '?'), name), flush=True)
                if stick != 'off':
                    lx, ly, rx, ry = sticks(c); v = (rx, ry) if stick == 'right' else (lx, ly)
                    if aim is None or v[0] * v[0] + v[1] * v[1] > aim[1][0] * aim[1][0] + aim[1][1] * aim[1][1]: aim = (c, v)
        if aim is not None and self.mouse.move(*aim[1]): self.active = aim[0]          # (one move per frame, with the most tilted stick: two controllers connected, e.g. a PlayStation one and its Xbox emulation, must not split the frame time)
        if reg is not None: reg.set_pad_family(self.family())
        click = set(PI.inputs(reg['gamepad'].get('A'))) if reg is not None else set()
        for name in sorted(self.held - now):
            if name in self.clicking: self.clicking.discard(name); self.mouse.click(False)
            else: self._send('on_key_release', name)
        for name in sorted(now - self.held):
            if name in click and self.mouse.awake() and self.mouse.pos is not None: self.clicking.add(name); self.mouse.click(True)          # (the pointer was just moved with the stick: Action = a click where it is)
            else: self._send('on_key_press', name)
        self.held = now

    def _direct_pads(self):
        """The XInput controllers that are plugged in, read again: the ones already connected at every frame, the empty slots only every SCAN_EVERY seconds."""
        scan = time.monotonic() >= self._scan_at
        if scan: self._scan_at = time.monotonic() + SCAN_EVERY
        out = []
        for p in self.direct:
            was = p.connected
            if was or scan: p.refresh()
            if p.connected and not was: print('Gamepad: %r connected (family XB)' % (p.name,), flush=True)
            if p.connected: out.append(p)
        return out

    def family(self):
        """Family ('XB', 'PS' or 'NS') of the controller used last, else of the first one connected; Xbox when none is connected or recognized (the logos are then the most common ones)."""
        for c in ([self.active] if self.active is not None else []) + self.pads + [p for p in self.direct if p.connected]:
            f = family_of(c)
            if f: return f
        return 'XB'

    def _send(self, event, name):
        EventDispatcher.dispatch_event(self.win, event, PI.SYMBOL[name], 0)          # (not through the window's queue: the key state and the handlers must see it at once)
