"""Full screen, window, resolution and monitors."""
import os, sys, time
import pyglet
from pyglet import gl
from dq456_pc import games as GM
from dq456_pc import paths as CH
from dq456_pc.language import tr
from dq456_pc.window import screens as EK
from dq456_pc.core import load_tracking as SV
from dq456_pc.persistence import settings as RG
from dq456_pc.window.constants import RESOLUTIONS
from dq456_pc.window.helpers import adjust_size, keep_row_above, pause_transitions_dwm, row_above_screen, transitions_dwm, useful_zone


# the message when a window <-> full screen switch fails: (requested mode is full screen, kept mode is full screen) -> whole sentence (English does not
# have the same word order)
TOGGLE_FAILURE_MESSAGES = {(True, True): 'Full screen failed (%r): full screen kept', (True, False): 'Full screen failed (%r): windowed mode kept',
                         (False, True): 'Windowed mode failed (%r): full screen kept', (False, False): 'Windowed mode failed (%r): windowed mode kept'}


class FullScreenMixin:
    """Full screen, window, resolution and monitors."""

    def _create_window(self, args, cfg, requested):
        """Creates the window directly in the stored mode (0 window, 1 full screen), with a fallback on any error, reported in the console: full screen -> window.
        It stays hidden until a first black frame (no white flash). -> mode obtained."""
        try:
            screen_page = pyglet.display.get_display().get_default_screen(); self.desktop = (int(screen_page.width), int(screen_page.height))      # (the desktop size)
        except Exception as ex: print('Main screen unreadable (%r)' % (ex,), flush=True)
        for mode in range(requested, -1, -1):
            try:
                self._simulated_failure(mode)
                if mode == 1: self._create_fullscreen(cfg)
                else:
                    super().__init__(args.width_px, args.height_px, caption=tr(self.WINDOW_TITLE) % GM.profile().name, resizable=True, config=cfg, vsync=True, visible=False)
                    if getattr(args, 'reload_location', None):            # game started again (language change): the window reappears where the closed one was
                        try: self.set_location(*args.reload_location)
                        except Exception as ex: print('Window position not restored (%r)' % (ex,), flush=True)
            except Exception as ex:
                if mode == 0: raise
                print('Full screen failed at launch (%r): windowed mode' % (ex,), flush=True)
                continue
            self.win_mode = mode
            SV.note('window created (hidden)', mode=mode, size_value='%dx%d' % (self.width, self.height))
            if SV.ACTIVE:
                for ev in ('on_resize', 'on_show', 'on_hide', 'on_expose', 'on_move', 'on_activate', 'on_deactivate'):
                    self.push_handlers(**{ev: (lambda *a, _e=ev: SV.note('event ' + _e, args=a))})
            try: self.switch_to(); gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear(); self.flip()
            except Exception: pass
            SV.note('black frame presented (window hidden)')
            self.dwm_cut = transitions_dwm(self, False)    # Windows: no window manager opening animation (re-enabled by on_draw, 2 s after the game's 1st frame)
            self.set_visible(True); self.activate()          # (what Window.__init__ does for a visible window: here after the black frame)
            try: self.switch_to(); gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear(); self.flip()      # Windows: the black frame presented while the window is hidden is not necessarily displayed; a 2nd one, with the window shown, avoids the class background (white) during loading
            except Exception: pass
            SV.note('window shown', size_value='%dx%d' % (self.width, self.height), dwm_cut=self.dwm_cut)
            return mode

    def _create_fullscreen(self, cfg):
        """Window created in full screen, on the primary screen: it does not exist yet, so there is no screen where it is located to detect (afterwards, F11 or the toggle put it in full screen on the screen where it is)."""
        super().__init__(caption=tr(self.WINDOW_TITLE) % GM.profile().name, resizable=True, config=cfg, vsync=True, fullscreen=True, visible=False); self._note_full_zone(); row_above_screen(self)          # (Windows: overlays of the system on top of the game)

    # ---- settings applied from the Esc menu
    def set_mode(self, m): self.mode = RG.valid_sprites_mode(m)

    @property
    def is_fullscreen(self):
        """Full screen (borderless window at the desktop resolution)?"""
        return self.win_mode == 1

    def resolutions(self):
        """Proposed sizes (16/9, 720p to 4K), sorted by width then height: window = those that fit on the screen with its borders; full screen = those of the desktop (the row is grayed out: the window always takes
        the desktop resolution, the choice is used for the next return to window mode). The current size is added to them if it is free."""
        entries = list(RESOLUTIONS); cur = self.current_resolution()
        lim = self.desktop if self.is_fullscreen else useful_zone()
        if lim: entries = [r for r in entries if r[0] <= lim[0] and r[1] <= lim[1]]
        if cur not in entries: entries.append(cur)
        return sorted(entries)                # by width, then by height

    def current_resolution(self): return (int(self.width), int(self.height))

    def set_resolution(self, v):
        """Window: changes the size (brought back to the screen if it is too large). Full screen: no effect, the window keeps the desktop resolution; the choice is used for the next return to window mode."""
        w, h = int(v[0]), int(v[1])
        if self.is_fullscreen: self.window_size = adjust_size(w, h)
        else:
            w, h = adjust_size(w, h)
            self.window_size = (w, h); self.set_size(w, h); self._check_real_size()

    def _check_real_size(self):
        """Windows: compares the drawing area given by the system with the one pyglet believes it has and gives it to pyglet again if they differ (window shrunk by Windows: otherwise the drawing is too large and the scene seems zoomed until the first resize)."""
        if sys.platform != 'win32' or self.is_fullscreen: return
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if not ctypes.windll.user32.GetClientRect(self._hwnd, ctypes.byref(r)): return
            w, h = r.right - r.left, r.bottom - r.top
            if w <= 0 or h <= 0 or (w, h) == (self._width, self._height): return
            print('Window: drawing area %d x %d corrected (the system reports %d x %d)' % (self._width, self._height, w, h), flush=True)
            self._width, self._height = w, h
            self._update_view_location(w, h)
            self.dispatch_event('_on_internal_resize', w, h)
        except Exception as ex: print('size check failed:', ex, flush=True)

    def set_info(self, yes): self.helptext = bool(yes)

    def set_full_screen(self, yes):
        """"Fullscreen" toggle of the Esc menu, F11 and Alt + Enter: switches from window to full screen (borderless window at the monitor's resolution, the monitor's display does not change) and back, in a single
        switch (see _set_full_screen). The full screen monitor is the one where the window is (see _screen_for_fullscreen).
        The obtained mode is stored in the settings (`window_mode`). On any error: initial state kept, reported in the console and by an on-screen message. -> true if the window is in full screen."""
        target = 1 if yes else 0; R = self.reg
        if target == self.win_mode: R['window_mode'] = target; return self.is_fullscreen
        if self._toggling: return self.is_fullscreen
        self._toggling = True
        try:
            error = None
            try:
                screen_page = None
                if target == 1:
                    screen_page = self._screen_for_fullscreen()[0]
                    if screen_page is not None and not self.fullscreen and self._already_on(screen_page): screen_page = None          # (this is already pyglet's monitor: set_fullscreen(True) as before)
                self._set_full_screen(target == 1, screen_page)
            except Exception as ex: error = ex
            self.win_mode = 1 if self.fullscreen else 0           # (the actual state of the window)
            R['window_mode'] = self.win_mode
            self._log_window('full screen' if self.win_mode else 'window')
            if error is not None:
                print(TOGGLE_FAILURE_MESSAGES[(bool(target), bool(self.win_mode))] % (error,), flush=True)
                self._note_toggle_failure(target, error)
        finally: self._toggling = False
        return self.is_fullscreen

    def _note_toggle_failure(self, target, error):
        """Failure of a full screen <-> window switch: the FULL error (the call stack, not only its text) with the state of the window and the monitors, in the console and in `window_errors.log` (next to the settings;
        ignored by git; `DQ_WINDOW_LOG`: another file). The "Window failed (...)" line does not say where it failed. Never raises an error."""
        try:
            import traceback
            state = []
            try: state.append('window: full screen = %s, %d x %d, remembered size %s, previous position %s, desktop %s' % (self.fullscreen, self.width, self.height, getattr(self, 'window_size', None), getattr(self, '_windowed_location', None), getattr(self, 'desktop', None)))
            except Exception as ex: state.append('window unreadable (%r)' % (ex,))
            try: ec = self.screen; state.append('window screen according to pyglet: %d x %d at (%d, %d)' % (ec.width, ec.height, ec.x, ec.y))
            except Exception as ex: state.append('window screen unreadable (%r)' % (ex,))
            try: state.append('monitors: %s' % ' ; '.join(('%d x %d at (%d, %d) (primary)' if d['primary'] else '%d x %d at (%d, %d)') % (d['width'], d['height'], d['x'], d['y']) for d in self._read_screens(True)[1]))
            except Exception as ex: state.append('monitors unreadable (%r)' % (ex,))
            state.append('pyglet %s, Python %s, %s' % (pyglet.version, sys.version.split()[0], sys.platform))
            text = ('--- %s: switch to full screen failed ---\n%s%s\n' if target else '--- %s: switch to windowed mode failed ---\n%s%s\n') % (time.strftime('%Y-%m-%d %H:%M:%S'), ''.join(traceback.format_exception(error)), '\n'.join(state))
            print(text, flush=True)
            path = CH.FOLDERS.errors_logfile(); os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f: f.write(text + '\n')
        except Exception as ex: print('Switch error not logged (%r)' % (ex,), flush=True)

    def toggle_full_screen(self):
        """F11 / Alt + Enter: window <-> full screen."""
        return self.set_full_screen(not self.is_fullscreen)

    def _set_full_screen(self, full, screen_page=None):
        """The switch, in a single step (pyglet: one set_fullscreen, which on Windows hides the window, changes its style and size, then shows it again and repositions it):
        - the window's size is stored before leaving it (`window_size`, the position is stored by pyglet) and restored all at once on returning, never through an intermediate state (no more set_fullscreen(False) followed by set_fullscreen(True));
        - the window is hidden BEFORE, so it is shown again only once, at its final size and place, and not shown at the wrong place and then moved;
        - a game frame is drawn at the final size while it is hidden (the off-screen rendering buffers, postfx.py, are only rebuilt if the size changed, once, here: no more forced rebuild at each
          switch), then displayed, then the window is shown and the same frame redrawn right away (in case the system did not keep that of the hidden window): no frame of unstable size nor empty buffer.
        `screen_page`: pyglet Screen object of the full screen (None: the one pyglet already has). Already in full screen, another `screen_page` moves the window to that monitor (same step: hidden, one set_fullscreen, one frame, shown);
        the starting monitor is restored if the move fails.
        Raises an error if the mode could not be taken (the initial state is then restored). DQ_SIMPLE_TOGGLE=1: (debugging) a single set_fullscreen without anything else, as before."""
        before = bool(self.fullscreen)
        if before == full and not (full and screen_page is not None and not self._already_on(screen_page)): return
        self._refresh_screen()          # (BEFORE anything: the monitor pyglet keeps may no longer be valid, see _refresh_screen)
        pause_transitions_dwm(self)          # Windows: no fade-out / fade-in of the window manager around the hide and show of the switch
        if not before: self.window_size = (int(self.width), int(self.height))          # (the size of the window, to be restored on return)
        screen_before = getattr(self, 'screen', None) if before else None              # (the monitor to restore if the move fails)
        size_value = adjust_size(*self.window_size)              # (a stored size larger than the usable area of the screen is brought back to the screen)
        if os.environ.get('DQ_SIMPLE_TOGGLE'): self._apply_full_screen(full, size_value, screen_page); self._simulated_failure(1 if full else 0); return
        is_hidden = False; error = None
        try:
            if getattr(self, '_visible', True): is_hidden = True; self.set_visible(False)          # (hidden before the call: a half-successful hide is still followed by a set_visible(True))
            self._apply_full_screen(full, size_value, screen_page)
            self._simulated_failure(1 if full else 0)          # (test: the failure happens after the change, to try the return to the initial state)
        except Exception as ex:
            error = ex
            try: self._apply_full_screen(before, size_value, screen_before)          # (return to the initial state, window still hidden, on the starting monitor)
            except Exception as ex2:
                print("Return to the starting state failed (%r)" % (ex2,), flush=True)
                try: error.add_note("Return to the starting state failed too: %r" % (ex2,))
                except Exception: pass
        self._toggle_frame()
        if is_hidden:
            try: self.set_visible(True)
            except Exception as ex: print('Window not shown again (%r)' % (ex,), flush=True)
            else: self._toggle_frame()          # (assumed: the system may not keep what is displayed while the window is hidden; the same frame is redrawn as soon as it is visible, without waiting for the loop)
        if error is not None: raise error

    def _apply_full_screen(self, full, size_value, screen_page=None):
        """The switch's set_fullscreen (a single call), on monitor `screen_page` (pyglet Screen object; None: the one the window has). When returning to window mode it gets back its size (`size_value`) and its previous place
        (position stored by pyglet, on its original monitor, whichever one the full screen was on); with no stored position (launched in full screen) or if its monitor is no longer there, it is centered on the full screen
        monitor."""
        self._row_above = False                                            # (the extra row of the full screen is put back after the change, row_above_screen)
        if full:
            if screen_page is not None: self.set_fullscreen(True, screen=screen_page)
            else: self.set_fullscreen(True)
            self._note_full_zone(); row_above_screen(self)          # (Windows: overlays of the system on top of the game)
        else:
            self.set_fullscreen(False, width=int(size_value[0]), height=int(size_value[1]))          # (pyglet's signature: set_fullscreen(fullscreen, screen, mode, width, height))
            loc = getattr(self, '_windowed_location', None); zone = getattr(self, 'full_zone', None) or ((0, 0) + tuple(self.desktop) if self.desktop else None)
            seen = self._read_screens(True)[1]
            if loc and zone and seen and EK.screen_of((loc[0], loc[1], self.width, self.height), seen) is None: loc = None          # (its monitor was unplugged: it would be outside all screens)
            if not loc and zone:
                try: self.set_location(int(zone[0] + max(0, (zone[2] - self.width) // 2)), int(zone[1] + max(32, (zone[3] - self.height) // 2)))
                except Exception as ex: print('Window not centered (%r)' % (ex,), flush=True)
        if sys.platform == 'win32' and not full: self._check_real_size()          # (Windows can shrink the window without warning)

    def on_resize(self, width, height):
        """Windows, full screen: the game's view keeps its row above the monitor after every resize (see helpers.keep_row_above)."""
        keep_row_above(self)

    def _toggle_frame(self):
        """Hidden window, at its final size: a game frame is drawn and displayed in it (during the logos and the loadings: black), so that the first thing seen is a complete frame."""
        try:
            self.switch_to()
            if self._ready: self.on_draw()
            else: gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear()
            self.flip()
        except Exception as ex:
            print('Switch frame failed (%r): black' % (ex,), flush=True)
            try: gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear(); self.flip()
            except Exception: pass

    # ---- full screen monitor: the window's (no setting; pure logic in screens.py)
    def _read_screens(self, fresh=False):
        """-> (pyglet Screen objects, descriptions from screens.listing) of the detected monitors (`display.get_screens()`). The list is kept for 1.5 s (the Display page reads it at every frame and, on Windows, the enumeration queries the
        system); `fresh` rereads it (switch, change of choice). Unreadable -> ([], [])."""
        t = time.perf_counter(); c = getattr(self, '_screen_cache', None)
        if c is not None and not fresh and t - c[0] < 1.5: return c[1], c[2]
        try:
            screens = list((getattr(self, 'display', None) or pyglet.display.get_display()).get_screens())
            res = (t, screens, EK.listing(screens))
        except Exception as ex:
            print('Monitors unreadable (%r)' % (ex,), flush=True); res = (t, [], [])
        self._screen_cache = res
        return res[1], res[2]

    def _refresh_screen(self):
        """Updates the monitor pyglet keeps for the window (`_screen`) before a switch. On Windows, this Screen keeps the handle (HMONITOR) of the monitor as it was when the window was created;
        when a screen is plugged in (or unplugged), Windows may assign others and the kept handle is no longer valid: `set_fullscreen` then recreates the window (`Win32Window._create`), which reads the monitor density
        (`Screen.get_dpi` -> GetDpiForMonitor) and fails with "Descripteur non valide" (seen on a real machine: full screen, then an external screen plugged in, then no way back to windowed mode).
        The monitor is looked up in a fresh enumeration: the one with the same position and dimensions as the old one, otherwise the one where the window is, otherwise the primary. Never raises an error.
        -> true if a valid monitor was put in place."""
        try:
            current = getattr(self, '_screen', None); screens, desc = self._read_screens(True)
            if current is None or not screens or not desc: return False
            old = (int(current.x), int(current.y), int(current.width), int(current.height))
            i = next((k for k, d in enumerate(desc) if (d['x'], d['y'], d['width'], d['height']) == old), None)
            if i is None: i = EK.target(desc, self._window_screen_index(desc))
            if i is None: return False
            fresh = screens[desc[i]['source']]
            if (int(fresh.x), int(fresh.y), int(fresh.width), int(fresh.height)) != old:
                print('Window monitor refreshed: %d x %d at (%d, %d) (before: %d x %d at (%d, %d))' % (fresh.width, fresh.height, fresh.x, fresh.y, old[2], old[3], old[0], old[1]), flush=True)
            self._screen = fresh; return True
        except Exception as ex:
            print('Window monitor not refreshed (%r)' % (ex,), flush=True); return False

    def _window_screen_index(self, desc):
        """Index (in `desc`) of the monitor where the window is (that of its center); None if it does not exist yet or if its place is unreadable."""
        try:
            x, y = self.get_location(); return EK.screen_of((x, y, self.width, self.height), desc)
        except Exception: return None

    def _screen_for_fullscreen(self, fresh=True):
        """-> (pyglet Screen object, description) of the full screen monitor: the one where the window is (that of its center), failing that the primary. (None, None) if the monitors are unreadable: pyglet then keeps its own.
        Not a player choice (removed at the player's request: full screen is always done on the window's screen). Never raises an error."""
        screens, desc = self._read_screens(fresh)
        try:
            i = EK.target(desc, self._window_screen_index(desc))
            if i is None: return None, None
            return screens[desc[i]['source']], desc[i]
        except Exception as ex:
            print('Full screen monitor unreadable (%r)' % (ex,), flush=True); return None, None

    def _already_on(self, screen_page):
        """Is the window (in full screen) already on this monitor? (same position and same dimensions as pyglet's monitor.)"""
        try:
            ec = self.screen; return (ec.x, ec.y, ec.width, ec.height) == (screen_page.x, screen_page.y, screen_page.width, screen_page.height)
        except Exception: return False

    def _note_full_zone(self):
        """Stores the rectangle of the full screen monitor (centering on return to window mode when the window has no previous place: launched in full screen)."""
        try: ec = self.screen; self.full_zone = (int(ec.x), int(ec.y), int(ec.width), int(ec.height))
        except Exception: pass

    def _window_shortcut(self, symbol, modifiers):
        """F11 or Alt + Enter, from anywhere (logos, title, game, Esc menu, name entry, battle): switches window <-> full screen. The key is swallowed (neither confirmation nor game action) and, with Alt, Alt no longer counts as
        "party chat" (see _edges). -> True if consumed."""
        K = pyglet.window.key
        t = getattr(self, 'key_list', None)
        alt = bool(modifiers & K.MOD_ALT) or (t is not None and bool(t[K.LALT] or t[K.RALT]))          # (the system flag, or the state of the Alt keys: either one is enough)
        if not (symbol == K.F11 or (alt and symbol in (K.RETURN, K.ENTER))): return False
        if getattr(self.pause, 'capture', None) is not None: return False                    # Commandes menu waiting for a key: F11 is "reserved" there (settings.RESERVED)
        self.swallowed.add(symbol)
        if alt: self.alt_cand = False
        if self._toggling or not hasattr(self, 'post'): return True
        try: self.toggle_full_screen()
        except Exception as ex: print('Full screen switch failed: %r' % (ex,), flush=True)
        return True

    def _log_window(self, when):
        """A log line: state and size of the window (full screen or not), drawing area and screen; written at creation, at the 1st frame drawn and at each switch."""
        try:
            ec = self.screen; fb = self.get_framebuffer_size()
            name_str = ('window', 'FULL SCREEN')[self.win_mode] + ('' if bool(self.fullscreen) == (self.win_mode > 0) else ' [INCONSISTENT: fullscreen=%s]' % self.fullscreen)
            n = EK.screen_of((ec.x, ec.y, ec.width, ec.height), self._read_screens()[1]); n = '' if n is None else ' (screen %d)' % (n + 1)
            print('Window (%s): %s, %d x %d, drawing area %d x %d, screen %d x %d%s' % (when, name_str, self.width, self.height, fb[0], fb[1], ec.width, ec.height, n), flush=True)
        except Exception as ex: print('Window (%s): state unreadable (%r)' % (when, ex), flush=True)
