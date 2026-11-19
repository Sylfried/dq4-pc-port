"""Test of the crash (Windows, first launch after the code was switched to English): the `_cachee` method of the game window became `_hidden`, and pyglet's
Windows window (`Win32Window`) already has a `_hidden = False` attribute: it shadowed the method and the first drawing of a menu crashed (`'bool' object is not callable`).
Linux (tests, screenshots) does not have this attribute: nothing had caught it.

This test reads pyglet's source code for ALL platforms (Windows, X11, macOS, Wayland, headless), so it runs everywhere, and rejects any game window name
(method, class attribute, `self.x = ...` in the dq456_pc/window files) that is also a pyglet window name, except those written on purpose (list below).
It also checks that a mouse click while the engine is loading (the logos) is ignored instead of reading `self.engine` before it exists.

    python3 tests/test_window_name_collisions.py
"""
import ast, glob, os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F
from dq456_pc.window import keyboard_mouse as KM

PYGLET_FILES = ('window/__init__.py', 'window/win32/__init__.py', 'window/xlib/__init__.py', 'window/cocoa/__init__.py',
                'window/wayland/__init__.py', 'window/headless/__init__.py', 'event.py')

# written on purpose by the game (full_screen.py: size and screen of the pyglet window, updated by hand when the mode changes)
DELIBERATE = {'_width', '_height', '_screen', '_fields_'}      # `_fields_`: class attribute of the ctypes structures of gamepad.py (XInput), not a name of the game window


def names_in(path):
    """Names defined by a file: functions, class attributes, `self.x = ...`."""
    with open(path, encoding='utf-8') as fh: tree = ast.parse(fh.read())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): out.add(n.name)
        elif isinstance(n, ast.ClassDef):
            for b in n.body:
                if isinstance(b, ast.Assign): out.update(t.id for t in b.targets if isinstance(t, ast.Name))
                elif isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name): out.add(b.target.id)
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for tg in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                for x in ast.walk(tg):
                    if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == 'self': out.add(x.attr)
    return out


class WindowNames(unittest.TestCase):
    def test_no_name_shared_with_pyglet_windows(self):
        pyglet_dir = os.path.dirname(pyglet.__file__); theirs = {}
        for f in PYGLET_FILES:
            p = os.path.join(pyglet_dir, *f.split('/'))
            if os.path.exists(p):
                for k in names_in(p): theirs.setdefault(k, []).append(f)
        self.assertIn('_hidden', theirs, "reading pyglet's code no longer finds Win32Window._hidden: this test checks nothing any more")
        ours = {}
        for p in sorted(glob.glob(os.path.join(ROOT, 'dq456_pc', 'window', '*.py'))):
            for k in names_in(p): ours.setdefault(k, []).append(os.path.basename(p))
        shared = sorted(k for k in set(ours) & set(theirs) if not k.startswith('__') and not k.startswith('on_') and k not in DELIBERATE)
        self.assertEqual(shared, [], 'names of the game window already taken by pyglet (see the files): ' + '; '.join(f'{k} {ours[k]} / {theirs[k]}' for k in shared))

    def test_menu_method_renamed(self):
        self.assertTrue(callable(F.Game._menu_hidden))
        self.assertFalse(hasattr(F.Game, '_hidden'))

    def test_event_handlers_only_overridden_on_purpose(self):
        """The game's `on_*` must be real pyglet events (a typo would produce a useless handler)."""
        events = set(pyglet.window.BaseWindow.event_types)
        for p in sorted(glob.glob(os.path.join(ROOT, 'dq456_pc', 'window', '*.py'))):
            with open(p, encoding='utf-8') as fh: body = ast.parse(fh.read()).body
            for n in body:
                if isinstance(n, ast.ClassDef) and n.name.endswith('Mixin'):
                    for f in n.body:
                        if isinstance(f, ast.FunctionDef) and f.name.startswith('on_'): self.assertIn(f.name, events, f'{os.path.basename(p)} : {f.name}')


class MouseBeforeEngine(unittest.TestCase):
    def test_click_during_loading_is_ignored(self):
        """During the logos, `Game._ready` is false and `self.engine` does not exist yet: the click skips the logo, without reading anything else."""
        g = types.SimpleNamespace(_ready=False, _logo_touched=False)
        self.assertIsNone(KM.KeyboardMouseMixin.on_mouse_press(g, 10, 10, pyglet.window.mouse.LEFT, 0))
        self.assertTrue(g._logo_touched)
        self.assertFalse(hasattr(g, 'engine'))


if __name__ == '__main__':
    unittest.main()
