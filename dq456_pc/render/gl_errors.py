"""OpenGL errors of the setups that may fail on some machines (offscreen rendering, blur, the mini-games' backdrop copy).

The game runs with pyglet's per-call error check off (main.py: it called glGetError after each of about a thousand OpenGL calls a frame, a cost on the CPU and, on threaded
drivers, a wait for the graphics card). Those setups relied on the error that the check raised to fall back (direct drawing, sharp menus, black behind the mini-games): they now
clear the error flag before their calls and look at it once after them."""
from pyglet import gl


def clear():
    """Forgets the errors left by earlier calls (glGetError returns them one at a time)."""
    for _ in range(16):
        if not gl.glGetError(): break


def check(what):
    """Raises if one of the calls since `clear` failed."""
    err = gl.glGetError()
    if err:
        clear(); raise RuntimeError('%s: OpenGL error %#x' % (what, err))
