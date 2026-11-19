"""Scale and screen edge of the game windows in the 16/9 window, kept while they stay open (no game, no window: pure logic, tested by tests/test_dq56_screens.py).

The game windows are laid out in the portrait column (450 x 800 interface units, the column fills the window height). The viewer enlarges them by `zoom` (UI_ZOOM)
and sticks each group of close windows (less than GROUP_GAP units apart) to the bottom, the top or the middle of the screen; the zoom is reduced while a group
goes off the screen or touches another one (`fresh`).

Computed afresh at every frame, that layout depended on what the windows showed at that moment: a button hidden by the game, a window that closed, the message
lowered or not, and every window moved or changed size (the casino tokens when the slot machine starts, the map views, the shop lists...). `Memory` keeps it
while windows stay on the screen: the zoom never grows back and a window keeps the screen edge it got when it appeared; the zoom only goes down when a
window that appears or grows no longer fits (`fits`). Everything is computed afresh once the screen has been without game windows for HOLD_FRAMES engine frames.
"""

GROUP_GAP = 60.0          # interface units: closer windows form one group (same screen edge)
MIN_SPACING = 8.0         # pixels between two groups stuck to different edges
HOLD_FRAMES = 12          # engine frames (0.4 s) without any game window before the layout is computed afresh


def mode_of_group(lo, hi):
    """Screen edge of a group of windows spanning lo..hi (interface units, 0 = middle of the column)."""
    c = (lo + hi) / 2.0
    return 'bottom' if c < -100 else 'top' if c > 100 else 'center'


def screen_y(z, mode, s, height):
    """Pixel height of the interface coordinate z for a window stuck to `mode`, `s` pixels per unit."""
    return (z + 400.0) * s if mode == 'bottom' else height - (400.0 - z) * s if mode == 'top' else height / 2.0 + z * s


def groups(intervals):
    """[(lo, hi)] -> merged groups [[lo, hi]] (windows closer than GROUP_GAP), sorted, and their screen edges."""
    gr = []
    for lo, hi in sorted(intervals):
        if gr and lo - gr[-1][1] < GROUP_GAP: gr[-1][1] = max(gr[-1][1], hi)
        else: gr.append([lo, hi])
    return gr, [mode_of_group(lo, hi) for lo, hi in gr]


def fresh(intervals, width, height, zoom):
    """The layout of a set of windows on its own: (k, groups, modes). k = zoom, reduced (down to 1) while a group goes off the screen or comes within MIN_SPACING of another."""
    base = height / 800.0
    gr, modes = groups(intervals)
    k = min(zoom, width / (450.0 * base))
    while k > 1.0:
        s = base * k; iv = [(screen_y(lo, m, s, height), screen_y(hi, m, s, height)) for (lo, hi), m in zip(gr, modes)]
        if all(a >= -0.5 and b <= height + 0.5 for a, b in iv) and all(iv[i + 1][0] - iv[i][1] >= MIN_SPACING for i in range(len(iv) - 1) if iv[i + 1][0] >= iv[i][0]): break
        k -= 0.01
    return max(k, 1.0), gr, modes


def mode_in(groups_, modes, lo, hi):
    """Screen edge of the group that holds lo..hi ('bottom' when none does)."""
    i = next((j for j, g in enumerate(groups_) if g[0] - 1e-6 <= lo and hi <= g[1] + 1e-6), None)
    return modes[i] if i is not None else 'bottom'


def fits(windows, k, height):
    """Is the scale k right for windows [(lo, hi, mode)] that each keep their screen edge? Every window stays on the screen (as in `fresh`), and two windows stuck to
    different edges keep at least MIN_SPACING pixels between them (or the gap they had at scale 1 when it was smaller; windows that overlapped in the game may).
    The caller stops at k = 1, where the edges no longer matter: the game's own layout."""
    base = height / 800.0; s = base * k
    placed = [(screen_y(lo, m, s, height), screen_y(hi, m, s, height), lo, hi, m) for lo, hi, m in windows]
    if any(a < -0.5 or b > height + 0.5 for a, b, _, _, _ in placed): return False
    for i, (a1, b1, lo1, hi1, m1) in enumerate(placed):
        for a2, b2, lo2, hi2, m2 in placed[i + 1:]:
            if m1 == m2: continue
            if lo2 >= hi1: gap0, gap = (lo2 - hi1) * base, a2 - b1          # window 2 above window 1 in the game
            elif lo1 >= hi2: gap0, gap = (lo1 - hi2) * base, a1 - b2
            else: continue                                                    # (they overlapped in the game)
            if gap < min(MIN_SPACING, gap0) - 1e-6: return False
    return True


class Memory:
    """The layout of the windows on the screen, kept while they stay open. `update` once per drawn frame."""

    def __init__(self):
        self.context = None; self._clear()

    def _clear(self):
        self.k = None; self.modes = {}; self.idle_since = None; self.message_raised = False

    def update(self, context, windows, frame, width, height, zoom, extra=(), cap=None):
        """windows: {key: (lo, hi)} of the windows shown (interface units); extra: [(lo, hi)] zones that always count (battle command menus); frame: engine frame number;
        cap: highest scale allowed (shop pictures: 1). -> (k, {key: screen edge})."""
        if context != self.context: self.context = context; self._clear()
        if not windows:
            if self.idle_since is None: self.idle_since = frame
            elif frame - self.idle_since >= HOLD_FRAMES or frame < self.idle_since: self._clear(); self.idle_since = frame
            k = self.k if self.k is not None else fresh(list(extra), width, height, zoom)[0]
            return (min(k, cap) if cap is not None else k), {}
        self.idle_since = None
        k0, gr, modes = fresh(list(windows.values()) + list(extra), width, height, zoom)
        for key, (lo, hi) in windows.items():
            if key not in self.modes: self.modes[key] = mode_in(gr, modes, lo, hi)
        k = k0 if self.k is None else self.k
        if cap is not None: k = min(k, cap)
        placed = [(lo, hi, self.modes[key]) for key, (lo, hi) in windows.items()] + [(lo, hi, mode_in(gr, modes, lo, hi)) for lo, hi in extra]
        while k > 1.0 and not fits(placed, k, height): k = max(1.0, k - 0.01)
        self.k = k
        return k, {key: self.modes[key] for key in windows}

    def message_offset(self, shown, wanted):
        """Vertical offset of the field message window: `wanted` (lowered to the bottom of the screen, or 0 when a window takes the bottom). Once it had to stay up, it stays up
        until it closes (it came down again, then went up, at every window of a shop or a menu that came and went)."""
        if not shown: self.message_raised = False; return 0.0
        if wanted == 0.0: self.message_raised = True
        return 0.0 if self.message_raised else wanted
