"""Full screen monitors: the pure logic (no window or OpenGL), so it can be tested with fake screens (tests/test_screens.py).
Full screen always happens on the monitor where the window is (no player choice: removed at the player's request; the `ecran_plein` setting no longer exists):
- listing: the monitors detected by pyglet (`display.get_screens`) -> descriptions (index, position, dimensions, name, primary);
- screen_of: the monitor that contains the center of a rectangle (the window);
- target: the full screen monitor (the window's, otherwise the primary)."""


def _name_of(ec):
    """Monitor name when pyglet provides it (Windows: the monitor's friendly name, X11: the output name); '' otherwise (never an error)."""
    for attempt in (lambda: ec.get_monitor_name(), lambda: ec.name):
        try:
            n = attempt()
            if isinstance(n, str) and n.strip(): return n.strip()
        except Exception: pass
    return ''


def listing(screens):
    """List of pyglet's screens (in the order of `get_screens()`) -> [dict(index, x, y, width, height, name, primary)]; exactly one primary (the one the system reports, failing that the one at (0, 0), failing that the first).
    An unreadable screen is ignored; unreadable `screens` -> []."""
    output = []
    try: entries = list(screens)
    except Exception: return []
    for src, ec in enumerate(entries):
        try: d = dict(x=int(ec.x), y=int(ec.y), width=int(ec.width), height=int(ec.height), name=_name_of(ec), primary=False)
        except Exception: continue
        try: d['reported'] = bool(ec.is_primary)
        except Exception: d['reported'] = None
        d['source'] = src          # (position in pyglet's list: finds the Screen object again even if an unreadable screen was ignored)
        output.append(d)
    if not output: return []
    p = next((d for d in output if d['reported']), None) or next((d for d in output if d['x'] == 0 and d['y'] == 0), None) or output[0]
    p['primary'] = True
    for i, d in enumerate(output): d['index'] = i; d.pop('reported', None)
    return output


def screen_of(rect, entries):
    """Index of the screen that contains the center of the window's rectangle (x, y, width, height), failing that the one it overlaps the most; None if it touches none (or unreadable rectangle)."""
    try: x, y, w, h = [float(v) for v in rect]
    except (TypeError, ValueError): return None
    cx, cy = x + w / 2.0, y + h / 2.0
    for d in entries:
        if d['x'] <= cx < d['x'] + d['width'] and d['y'] <= cy < d['y'] + d['height']: return d['index']
    best, area = None, 0.0
    for d in entries:
        ax, ay = min(x + w, d['x'] + d['width']) - max(x, d['x']), min(y + h, d['y'] + d['height']) - max(y, d['y'])
        if ax > 0 and ay > 0 and ax * ay > area: best, area = d['index'], ax * ay
    return best


def main(entries):
    """Index of the primary screen (0 if the list is empty: never an error)."""
    return next((d['index'] for d in entries if d['primary']), 0)


def target(entries, window=None):
    """Index (in `entries`) of the full screen monitor: the one where the window is (`window`: its index, None if unknown), failing that the primary. Empty list -> None."""
    if not entries: return None
    return window if isinstance(window, int) and not isinstance(window, bool) and 0 <= window < len(entries) else main(entries)
