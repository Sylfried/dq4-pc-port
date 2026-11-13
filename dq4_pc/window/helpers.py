"""Small stateless functions of the window: usable screen area, depth rank, free camera, camera height, projection matrix..."""
import math, os, sys
import numpy as np
import pyglet
from dq4_pc.core import engine as ENGINE
from dq4_pc.window.constants import GROUP_SLOTS, WINDOW_MARGIN


def useful_zone():
    """Maximum (width, height) of a drawing area that fits on the main screen with its title bar and the taskbar; None if the screen is unknown."""
    try:
        ec = pyglet.display.get_display().get_default_screen()
        try: k = max(1.0, float(ec.get_dpi()) / 96.0)
        except Exception: k = 1.0
        return int(ec.width - 16 * k), int(ec.height - WINDOW_MARGIN * k)
    except Exception: return None


def adjust_size(w, h):
    """Brings a window size that is too large for the screen down to the largest size of the same shape that fits: Windows then shrinks the window without warning and the drawing kept the requested size (zoomed scene, partly outside the window)."""
    zu = useful_zone()
    if zu is None or (w <= zu[0] and h <= zu[1]): return int(w), int(h)
    k = min(zu[0] / float(w), zu[1] / float(h)); nw, nh = max(320, int(w * k)), max(180, int(h * k))
    print('Window %d x %d too large for the screen: %d x %d' % (w, h, nw, nh), flush=True)
    return nw, nh


FSO_KEY = r'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
FSO_FLAG = 'DISABLEDXMAXIMIZEDWINDOWEDMODE'          # checkbox "Disable fullscreen optimizations" (Properties > Compatibility); set it for Python, removes it


def restore_fullscreen_optimizations():
    """Windows only: removes from the compatibility settings of the Python interpreter (the venv launcher and the base interpreter) the checkbox
    "Disable fullscreen optimizations" that had set there, so that Windows renders them as before. The other settings set on those programs are kept; the value is deleted when none are left.
    Windows reads the checkbox only when a process is created: effective at the next launch. No effect when nothing was set (key or value missing); no error propagates. -> modified paths.
    shortcut: called at every launch, to be removed when nobody has the value anymore."""
    if not sys.platform.startswith('win'): return []
    done = []
    try:
        import winreg
        exes = []
        for x in (sys.executable, getattr(sys, '_base_executable', None)):
            x = os.path.normpath(x) if x else None
            if x and x.lower() not in [e.lower() for e in exes]: exes.append(x)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FSO_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
            for x in exes:
                try: old, kind = winreg.QueryValueEx(k, x)
                except FileNotFoundError: continue
                if kind != winreg.REG_SZ: continue                      # (value of another type: left untouched)
                flags = [w for w in old.split() if w != '~']
                if FSO_FLAG not in flags: continue
                flags = [w for w in flags if w != FSO_FLAG]
                if flags: winreg.SetValueEx(k, x, 0, winreg.REG_SZ, ' '.join(['~'] + flags))
                else: winreg.DeleteValue(k, x)
                done.append(x)
        if done: print('Full-screen optimizations restored for %s (effective at the next launch)' % ', '.join(done), flush=True)
    except FileNotFoundError: pass                                          # (the key does not exist: nothing was ever set)
    except Exception as ex:
        print('Full-screen optimizations unchanged: %r' % (ex,), flush=True)
    return done


def whole_pixels(v):
    """`v` rounded to the nearest whole number, halves away from zero: symmetric (whole_pixels(-v) == -whole_pixels(v)), so two coordinates moving by the same amount in opposite directions change at the same frame."""
    return math.copysign(math.floor(abs(v) + 0.5), v)


def shadow_offset(steps, now):
    """(dx, dy) map pixels from a character to the shadow the engine places itself on the world map (the balloon: straight south, 0 to 32 pixels as it rises): the median of its last three
    engine steps (`steps`, a deque; `now` when there is none). When the balloon turns, the engine moves its shadow one step late, so for one step the offset jumps by the balloon's own step
    (3 pixels) and comes back: the shadow shook around the balloon, mostly in diagonal. The median drops that one-step jump; a real change (taking off, landing) is followed one step later."""
    if not steps: return now
    xs = sorted(v[0] for v in steps); ys = sorted(v[1] for v in steps)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def field_depth_rank(sprites):
    """World map: stacking rank of each placed sprite (the greatest rank is in front; it sets the height 0.04 + rank x 0.0005 of the flat sprite).
    The game (FieldPartyDraw::draw, libdq4core 0x1ec5a8) sorts the party members by decreasing depth (selection sort; at equal depth, the lowest slot keeps the head) then gives them
    SpriteCharacter::setDepth 10, 9, 8... in that order: at equal depth, the hero (slot 0) is in front of the partner. Order here: engine height z (3rd value of the position), then the southernmost
    (a partner south of the hero is in front of the hero), then, at equal position (landing of a chimaera wing or of Zoom: the party is stacked on a single point), the LOWEST slot in front
    for the party; vehicles (slots >= 10) keep the most recent in front."""
    seen = [(float(s['pos'][2]) if len(s['pos']) > 2 else 0.0, float(s['pos'][1]), -sl if sl < GROUP_SLOTS else sl, sl) for sl, s in sprites.items() if s['pos'] is not None]
    return {sl: i for i, (_, _, _, sl) in enumerate(sorted(seen))}


def rot_unity(ex, ey, ez):
    """3x3 matrix of a Unity rotation (Euler angles in degrees, order z then x then y, left-handed space): column = local axis in the world."""
    cx, sx, cy, sy, cz, sz = (math.cos(math.radians(ex)), math.sin(math.radians(ex)), math.cos(math.radians(ey)), math.sin(math.radians(ey)), math.cos(math.radians(ez)), math.sin(math.radians(ez)))
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]); Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]); Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def portrait_base_height(aspect):
    """Visible height, in short sides of the phone's portrait 16:9 screen, for a window of shape `aspect` (width / height): the part of the world the phone shows (short side across,
    long side = 16/9 short sides up) is the base. A landscape window shows it with its two sides swapped (16:9: long side across, short side up) and a portrait window as on the phone; a window of another
    shape keeps the whole base and shows more on one side: wider than 16:9 (or than 9:16 in portrait) -> more on the sides, narrower -> more above and below. Continuous: 1 at 16:9, 16/9 from a square to 9:16."""
    a = max(float(aspect), 1e-6); long_side = 16.0 / 9.0
    if a >= long_side: return 1.0
    if a >= 1.0: return long_side / a
    if a > 1.0 / long_side: return long_side
    return 1.0 / a


def screen_column(width, height, area=(450.0, 800.0)):
    """(width, height) in interface units of what a window of `width` x `height` pixels shows of the interface camera's layer, `area` (units) not stretched: a landscape
    window takes its whole height (its top and bottom edges touch the screen's, the rest is on the left and right), a portrait window its whole width (the rest above and below)."""
    k = height / area[1] if width >= height else width / area[0]
    return width / k, height / k


def camera_free(e):
    """Free camera: position + rotation (as in battle), no target. Packet 11 bit 7 (scenes, title); casino: the engine sends the position and the rotation (packet 10, mask 5) without packet 11."""
    return bool(e.cam_free or (getattr(e, 'part', None) == ENGINE.PART_CASINO and e.cam_rot is not None))


def background_gradient(topmost, bottom):
    """Is the town's background a real gradient (packet 8: colors of the top and bottom of the frame, `State.top_background` / `bottom_background`)? False without packet 8 (None) or if the two colors are equal: clearing
    the frame to that color is enough (no difference)."""
    return topmost is not None and bottom is not None and max(abs(float(a) - float(b)) for a, b in zip(topmost, bottom)) > 1e-6


def matrix(cam, target, fov, aspect, n=1.0, f=200.0, topmost=(0, 1, 0)):
    pos = np.array(cam, float); fw = np.array(target, float) - pos; fw /= np.linalg.norm(fw)
    right = np.cross(topmost, fw); right /= np.linalg.norm(right); topmost = np.cross(fw, right)
    th = math.tan(math.radians(fov) / 2)
    M = np.zeros((4, 4))
    M[0, :3] = right / (th * aspect); M[0, 3] = -pos @ right / (th * aspect)
    M[1, :3] = topmost / th; M[1, 3] = -pos @ topmost / th
    k = (f + n) / (f - n)
    M[2, :3] = fw * k; M[2, 3] = -pos @ fw * k - 2 * f * n / (f - n)
    M[3, :3] = fw; M[3, 3] = -pos @ fw
    return M, right


def transitions_dwm(window, active):
    """Windows only: enables or disables the window animations done by the window manager (DWM: fade / zoom opening, minimizing, restoring; DWMWA_TRANSITIONS_FORCEDISABLED).
    Disabled while the game window opens, they do not pile on top (a fade of the window itself, over the black then the logos, looks like a curtain); restored afterwards (see on_draw).
    No error propagates (system without DWM, missing handle: nothing changes). -> True if the system accepted."""
    if not sys.platform.startswith('win'): return False
    try:
        import ctypes
        hwnd = getattr(window, '_hwnd', None)
        if not hwnd: return False
        v = ctypes.c_int(0 if active else 1)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 3, ctypes.byref(v), ctypes.sizeof(v)) == 0
    except Exception as ex:
        print('Window transitions (DWM) unchanged: %r' % (ex,), flush=True); return False


def row_above_screen(window):
    """Windows only (lead 2): the full screen window gets one more pixel row, above its monitor (off screen); the drawing keeps the monitor's size and place. **Assumed** (cannot be verified outside Windows):
    a window that covers its monitor exactly is presented without the window manager (direct flip), so what comes on top of it (screenshot tool, volume bar, notifications) flashes black or does not open; one row more and it
    stays an ordinary composited window. The game's view (pyglet's child window that carries OpenGL) gets the same row (keep_row_above): pyglet keeps the monitor's size as the drawing size, so the drawing (from the bottom)
    fills exactly the visible part. DQ_FULL_EXACT=1: the window covers the monitor exactly, as before. -> True if done."""
    window._row_above = False
    if not sys.platform.startswith('win') or os.environ.get('DQ_FULL_EXACT'): return False
    try:
        import ctypes
        hwnd, view = getattr(window, '_hwnd', None), getattr(window, '_view_hwnd', None)
        if not (hwnd and view and window.fullscreen): return False
        ec = window.screen; w, h = int(ec.width), int(ec.height)
        window._row_above = True          # (before resizing: the window's WM_SIZE resets its view to the monitor's size, and on_resize gives it its row back, see keep_row_above)
        if not ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), None, int(ec.x), int(ec.y) - 1, w, h + 1, SWP_QUIET): window._row_above = False; return False
        return keep_row_above(window)
    except Exception as ex:
        window._row_above = False; print('Full screen window left at the size of the monitor (%r)' % (ex,), flush=True); return False


SWP_QUIET = 0x0004 | 0x0010 | 0x0200          # SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER


def keep_row_above(window):
    """Windows, full screen with the extra row (row_above_screen): the game's view gets the row too. Called after every resize of the window (on_resize): pyglet puts the view back at the monitor's size at each WM_SIZE
    (restored after a minimize, shown again, display change), which would leave the bottom row of the monitor uncovered and the picture one row too high. -> True if the view has its row."""
    if not getattr(window, '_row_above', False) or not window.fullscreen or not sys.platform.startswith('win'): return False
    try:
        import ctypes
        view = getattr(window, '_view_hwnd', None); ec = window.screen
        return bool(view) and bool(ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(view), None, 0, 0, int(ec.width), int(ec.height) + 1, SWP_QUIET))
    except Exception as ex:
        print('Full screen view not resized (%r)' % (ex,), flush=True); return False


def pause_transitions_dwm(window, seconds=2.0):
    """Windows only: turns the DWM animations off (see transitions_dwm) for the time of a full screen / window switch, then back on `seconds` later. Without this, the hide and show around the switch play the
    fade-out and fade-in of the window manager (they were turned back on 2 s after the first game frame, see on_draw): a flash that the frame drawn at the final size cannot hide. A new call restarts the delay.
    -> True if the system accepted (nothing to restore otherwise)."""
    if not transitions_dwm(window, False): return False
    back = getattr(window, '_dwm_back', None)
    if back is None: window._dwm_back = back = lambda dt: transitions_dwm(window, True)
    pyglet.clock.unschedule(back); pyglet.clock.schedule_once(back, seconds)
    return True
