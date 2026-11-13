"""Entry of the hero's name (InputName class of the original Unity layer, "Enter a name" screen of adventure log creation).

In the game, Unity holds this keyboard: the engine opens the type 55 window (port 15), sends `[12,0,8]` (8 characters at most) then `[12,1,1]` (keyboard visible) and waits:
  - OK: `[2, n]` then the n UTF-8 bytes of the name packed two by two (little-endian), sent in the SAME frame (otherwise the engine crashes);
  - Back: `[1, -1, 32]` (B key on the window).
The character sets are those of InputName (cctor) for the French language: alphabet (lowercase / uppercase, + space - , . ! ?) and accented letters, in pages of 5 columns x 7 lines.
The exact positions of the original (grid origin, function buttons) were not found in the code: the layout is drawn here in the style of the game windows.
The computer keyboard also works (any character of the grid), like the mouse and the arrows + Enter."""
import time
import pyglet
from pyglet import gl
from dq4_pc.language import N_

EMPTY_CELL = '＠'                           # empty grid cell (C_NA)
ALPHABET = ('abcdefghijklmnopqrstuvwxyz -,.!?' + EMPTY_CELL * 3, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ -,.!?' + EMPTY_CELL * 3)       # C_ALPHABET: lowercase, uppercase
ACCENTS = ('àáâäçèéêëìíîïñòóôöùúûüß' + EMPTY_CELL * 12, 'ÀÁÂÄÇÈÉÊËÌÍÎÏÑÒÓÔÖÙÚÛÜß' + EMPTY_CELL * 12)                      # C_AA
PAGES = (ALPHABET, ACCENTS)           # C_LOCALIZE
FUNCTIONS = ('Alphabet', 'à À', 'Maj.', 'Suppr.', 'OK')                   # C_ALPHABET_ETC (not localized in the game)
TITLE = N_('menus.enter_name')                      # (drawn by Pause._label, which translates them; the FUNCTIONS labels are the game's: we leave them untouched)
KEYBOARD_HELPTEXT = (N_('menus.keyboard_type_name'), N_('menus.enter_confirm_esc_back'))
COLS, LINES = 5, 7
SFX_BUTTON = 300                       # press sound effect of a menu button (like window.SFX_BUTTON)
GRID_COUNT = COLS * LINES               # 35 cells; then 35 to 39 = function buttons; 40 = Back
I_ALPHA, I_ACC, I_SHIFT, I_DELETE, I_OK, I_BACK = 35, 36, 37, 38, 39, 40
CHARS = {c for p in PAGES for page in p for c in page if c != EMPTY_CELL}      # characters accepted from the keyboard

# layout (interface units, origin at the center of the 450 x 800 column, Y upward)
BORDER = (-215.0, -345.0, 215.0, 330.0)
TITLE_Y = 292.0
SLOTS_Y, SLOT_L, SLOT_H, SLOT_STEP = 238.0, 40.0, 46.0, 46.0
GRID_Y0, GRID_STEP_Y, GRID_STEP_X, CELL_L, CELL_H = 172.0, 45.0, 72.0, 64.0, 37.0
FUNC_Y, FUNC_STEP, FUNC_L, FUNC_H = -158.0, 83.0, 79.0, 40.0
BACK_WIDTH, BACK_HEIGHT, BACK_GAP = 62.0, 52.0, 8.0          # (the back button is outside the frame, right of its bottom right corner: the frame takes almost the whole height)
WHITE = (255, 255, 255, 255); GOLD = (255, 235, 4, 255); GRAY = (128, 128, 128, 255); HELPTEXT = (170, 170, 170, 255); RED = (255, 90, 90, 255)
YELLOW = (255, 235, 4)


class NameEntry:
    def __init__(self, game):
        self.J = game; self.active = False; self.text = ''; self.max = 8; self.mode = 0; self.do_update = 0; self.cur = 0
        self.zones = []; self.mouse = None; self.t0 = 0.0

    # ---- state
    def open_menu(self, maximum=8):
        self.active = True; self.text = ''; self.max = max(1, min(30, maximum)); self.mode = 0; self.do_update = 0; self.cur = 0; self.t0 = time.time(); self.mouse = None

    def shutdown(self): self.active = False

    def page(self): return PAGES[self.mode][self.do_update]

    def _add(self, c):
        if c == EMPTY_CELL or len(self.text.encode('utf-8')) + len(c.encode('utf-8')) > 30 or len(self.text) >= self.max: return False
        self.text += c; return True

    def _delete(self):
        if not self.text: return False
        self.text = self.text[:-1]; return True

    def _validate(self):
        if self.text: self.J._name_entry_ok(self.text); return True
        return False

    def press(self, i):
        """Press on cell i (grid, function button or Back). -> true if something changed (button sound)."""
        if i < GRID_COUNT: return self._add(self.page()[i])
        if i == I_ALPHA: ok = self.mode != 0; self.mode = 0; return ok
        if i == I_ACC: ok = self.mode != 1; self.mode = 1; return ok
        if i == I_SHIFT: self.do_update ^= 1; return True
        if i == I_DELETE: return self._delete()
        if i == I_OK: return self._validate()
        if i == I_BACK: self.J._name_entry_back(); return True
        return False

    # ---- inputs
    def _step(self, i, dx, dy):
        """Neighbor cell of i in the direction (dx, dy; dy > 0 = upward): the 5 x 7 grid, then the row of function buttons, then Back; it wraps around."""
        if i < GRID_COUNT:
            r, c = divmod(i, COLS)
            if dx: return r * COLS + (c + dx) % COLS
            r -= dy
            return I_ALPHA + c if (r < 0 or r >= LINES) else r * COLS + c
        if i < I_BACK:
            f = i - I_ALPHA
            if dx: return I_ALPHA + (f + dx) % 5
            if dy > 0: return (LINES - 1) * COLS + f
            return I_BACK if f >= 3 else f                         # downward: Back (on the right) or the top of the grid
        return I_OK if dy > 0 else (I_ALPHA + 3 if dx < 0 else (I_ALPHA if dx > 0 else 0))

    def move_by(self, dx, dy):
        """Arrows: skips the empty cells of the page."""
        i = self.cur
        for _ in range(GRID_COUNT + 2):
            i = self._step(i, dx, dy)
            if i >= GRID_COUNT or self.page()[i] != EMPTY_CELL: break
        self.cur = i

    def key_press(self, symbol, modifiers=0):
        """Physical key. -> true if it was taken (letters arrive through text())."""
        K = pyglet.window.key
        d = {K.LEFT: (-1, 0), K.RIGHT: (1, 0), K.UP: (0, 1), K.DOWN: (0, -1)}.get(symbol)
        if d: self.mouse = None; self.move_by(*d); return True
        if symbol in (K.RETURN, K.ENTER):
            if self.press(self.cur): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        if symbol == K.BACKSPACE:
            if self._delete(): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        if symbol == K.ESCAPE: self.J._name_entry_back(); self.J.sound.play_sfx(SFX_BUTTON); return True
        if symbol == K.TAB: self.mouse = None; self.mode = 1 - self.mode; return True
        return True                                             # the keyboard is in text entry: no other key acts on the game

    def text_entered(self, t):
        """Characters typed on the keyboard: those of the grid are added (the cursor moves to OK so that a single Enter confirms); each added letter plays the button sound effect, like the click on the letter."""
        for c in t:
            if c in CHARS and self._add(c): self.cur = I_OK; self.mouse = None; self.J.sound.play_sfx(SFX_BUTTON)
        return True

    def click(self, x, y, button):
        M = pyglet.window.mouse
        if button == M.RIGHT: self._delete() and self.J.sound.play_sfx(SFX_BUTTON); return
        for x0, y0, x1, y1, i in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.cur = i; self.mouse = i
                if self.press(i): self.J.sound.play_sfx(SFX_BUTTON)
                return

    def hovered(self, x, y):
        for x0, y0, x1, y1, i in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                if self.mouse != i: self.mouse = i; self.cur = i
                return
        self.mouse = None

    # ---- drawing
    def draw_all(self, cx, cy, ui_scale):
        """(cx, cy, scale): frame of the interface column (Game._ui_reference); the window is reduced to fit the height of the screen."""
        ui_scale = min(ui_scale, 0.97 * self.J.height / (BORDER[3] - BORDER[1]))
        P = self.J.pause; k = ui_scale * 800.0 / 900.0
        U = lambda x, y: (cx + x * ui_scale, cy + y * ui_scale)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        x0, y0 = U(BORDER[0], BORDER[1]); x1, y1 = U(BORDER[2], BORDER[3]); P._border(x0, y0, x1 - x0, y1 - y0, k)
        def text(t, x, y, size_value, clr=WHITE, anchor=1):
            """Text of `size_value` units high, centered (anchor 1), left-aligned (0) or right-aligned (2) at (x, y) (units)."""
            label = P._label(t, size_value * ui_scale * 0.75, clr); w = label.content_width; px, py = U(x, y)
            label.x = px - (w / 2 if anchor == 1 else (w if anchor == 2 else 0)); label.y = py - size_value * ui_scale * 0.30; label.draw()
        P._restore_blend(); text(TITLE, 0, TITLE_Y, 26)
        # field: one slot per possible character
        n = self.max; x_begin = -(n * SLOT_STEP - (SLOT_STEP - SLOT_L)) / 2
        t = time.time() - self.t0
        for j in range(n):
            xc = x_begin + j * SLOT_STEP + SLOT_L / 2; a, b = U(xc - SLOT_L / 2, SLOTS_Y - SLOT_H / 2)
            r = pyglet.shapes.BorderedRectangle(a, b, SLOT_L * ui_scale, SLOT_H * ui_scale, border=max(1, int(1.5 * ui_scale)), color=(14, 16, 22), border_color=(200, 200, 196) if j == len(self.text) else (112, 114, 110)); r.draw()
            if j < len(self.text): text(self.text[j], xc, SLOTS_Y, 28)
            elif j == len(self.text) and int(t * 2) % 2 == 0:
                u, v = U(xc - 10, SLOTS_Y - SLOT_H / 2 + 6); pyglet.shapes.Rectangle(u, v, 20 * ui_scale, max(2, 2.5 * ui_scale), color=YELLOW).draw()
        P._restore_blend()
        zones = []; page = self.page()
        mouse_mode = self.J.last_device == 'mouse'       # last device used: mouse = yellow outline on the hovered key; keyboard / gamepad = gold cursor (arrow) on the chosen key
        def button(i, xc, yc, w, h, tag_label, size_value, pressed=False, grayed=False):
            a, b = U(xc - w / 2, yc - h / 2); selected = (i == self.cur) and not mouse_mode; over = mouse_mode and self.mouse == i
            P._plate(a, b, w * ui_scale, h * ui_scale, k, pressed or selected or over)                  # (mouse: the plate under the pointer darkens, no yellow outline)
            if selected: P._cursor(max(a - 24 * ui_scale, U(BORDER[0] + 3, 0)[0]), b + h * ui_scale / 2, 28 * ui_scale)          # (the arrow does not leave the frame: "Alphabet" sits flush against its edge)
            P._restore_blend(); text(tag_label, xc, yc, size_value, GRAY if grayed else WHITE)
            zones.append((a, b, a + w * ui_scale, b + h * ui_scale, i))
        for i in range(GRID_COUNT):
            r, c = divmod(i, COLS); ch = page[i]
            if ch == EMPTY_CELL: continue
            button(i, (c - 2) * GRID_STEP_X, GRID_Y0 - r * GRID_STEP_Y, CELL_L, CELL_H, ch if ch != ' ' else '␣', 22, False, len(self.text) >= self.max)
        for f, lib in enumerate(FUNCTIONS):
            i = I_ALPHA + f; active = (f == 0 and self.mode == 0) or (f == 1 and self.mode == 1) or (f == 2 and self.do_update == 1)
            button(i, (f - 2) * FUNC_STEP, FUNC_Y, FUNC_L, FUNC_H, lib, 16, active, f == 4 and not self.text)
        a, b = U(BORDER[2] + BACK_GAP, BORDER[1]); w, h = BACK_WIDTH * ui_scale, BACK_HEIGHT * ui_scale
        over = mouse_mode and self.mouse == I_BACK; selected = self.cur == I_BACK and not mouse_mode
        P._back_button(a, b, w, h, selected or over)
        if selected: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
        zones.append((a, b, a + w, b + h, I_BACK)); self.zones = zones
        P._restore_blend(); text(KEYBOARD_HELPTEXT[0], BORDER[0] + 18, BORDER[1] + 44, 13, HELPTEXT, 0); text(KEYBOARD_HELPTEXT[1], BORDER[0] + 18, BORDER[1] + 26, 13, HELPTEXT, 0)
