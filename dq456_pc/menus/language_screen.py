"""Language screen of the start menu: opened by the globe plate between "License" and "Saves"; each language of the port is a card with its flag and its name in its own language.

Does not exist in the original game: window drawn like the "Saves" screen (black frame, the game's plates, back button). Choosing a language does exactly what the "Language" setting of the
Esc menu does: the port's texts switch to it at once, and the game starts again on its title screen, when this window is closed, if the game version of that language (its APK files,
data\\apk\\<game>\\<code>) is another one than the version being played. A language without APK files of its own runs the game version it falls back on (English, otherwise French): its
card says which ("Game: English"). The chosen language is outlined in gold; the cards scroll when there are more than ROWS rows.

"System language": a checkbox above the cards, checked by default (the "Language" setting's `system` value). Checked, the cards are grayed and the port follows the computer's language.

Under the cards, "Add a language" and "Edit its texts" (the chosen language); those buttons and the screens they open are always in English (the texts every translation starts from):
  - adding: the flag is chosen among every flag of the project (`flags`), then the folder code (language-country: `pt-br`) and the language's own name ("Português"); "Create" writes
    the language's file (dq456_pc/languages/<code>.json: every English text, an empty translation; language.create_language) and creates its APK folders;
  - the file panel says where the language's file is and opens its folder; the translator writes the texts into the file itself, then "Load the texts" reads it again and checks it
    (language.check_language: a text that does not fit the English one stays in English, listed in data\\logs\\texts_<code>.txt).
Keys: left / right / up / down move between the items; in the forms, typing writes into the field, Tab or up / down change field, Enter confirms, Esc goes back."""
import os
import subprocess
import sys
import numpy as np
import pyglet
from pyglet import gl
from dq456_pc import games as GM
from dq456_pc import language as LG
from dq456_pc import paths as CH
from dq456_pc.language import N_
from dq456_pc.menus import flags as FL

BORDER = (-200.0, -290.0, 200.0, 290.0)                 # interface units, origin at the center of the 450 x 800 column, Y upward (the back button is under it, outside)
WHITE = (255, 255, 255, 255); GRAY = (128, 128, 128, 255); GOLD = (255, 235, 4); RED = (255, 120, 110, 255)
SFX_BUTTON = 300
TITLE = N_('language.title')
SYSTEM_CAPTION = N_('language.system_language')
GAME_CAPTION = N_('language.game_version')                 # "Game: %s" under a language that runs another language's game version
LANGUAGES = LG.LANGUAGES                                  # (the list itself: it follows the languages added while the game runs)
COLUMNS, ROWS = 3, 4                                      # cards per row, rows shown at once (the others scroll)
CARD_W, CARD_H, GAP_X, GAP_Y = 120.0, 88.0, 8.0, 8.0
CARDS_TOP = 192.0
SYS_Y, SYS_W, SYS_H = 224.0, 320.0, 40.0                  # the "System language" checkbox
FLAG_W, FLAG_H = 66.0, 44.0
BTN_Y, BTN_W, BTN_H = -232.0, 184.0, 44.0                 # "Add a language", "Edit its texts"
BACK_WIDTH, BACK_HEIGHT, BACK_GAP = 62.0, 52.0, 8.0
I_SYSTEM, I_BACK, I_ADD, I_EDIT = -1, -2, -3, -4          # the items that are not cards (cards: 0, 1, 2...)
F_COLUMNS, F_ROWS, F_W, F_H = 6, 7, 58.0, 52.0             # flag picker: cells of a flag (48 x 32) and its code
FORM_CODE, FORM_NAME, FORM_CREATE, FORM_CANCEL = 0, 1, 2, 3
FILES_OPEN, FILES_LOAD, FILES_DONE = 0, 1, 2
HINT = (180, 180, 180, 255)


def _texture(arr):
    """pyglet texture of an RGBA array (top row first)."""
    h, w = arr.shape[:2]
    img = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(arr[::-1]).tobytes())
    t = img.get_texture(); gl.glBindTexture(t.target, t.id)
    gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    return t


def card_center(i, first_row=0):
    """Center (x, y) of the card of language i, in interface units (`first_row`: the first row shown)."""
    row, col = divmod(i, COLUMNS)
    x = (col - (COLUMNS - 1) / 2.0) * (CARD_W + GAP_X)
    return x, CARDS_TOP - CARD_H / 2.0 - (row - first_row) * (CARD_H + GAP_Y)


def english(key):
    """A text of the add-language screens, always in English."""
    return LG.catalog(LG.REFERENCE).get(key, key)


def shown_path(path):
    """`path` from the port's folder (dq456_pc\\languages\\pt-br.json), shorter on screen."""
    try: return os.path.relpath(path, os.path.dirname(os.path.dirname(LG.FOLDER)))
    except ValueError: return path


def open_folder(path):
    """Opens a folder in the file explorer (nothing if it cannot)."""
    try:
        if sys.platform == 'win32': os.startfile(path)
        elif sys.platform == 'darwin': subprocess.Popen(['open', path])
        else: subprocess.Popen(['xdg-open', path])
    except Exception as ex: print('folder not opened (%s): %s' % (ex, path), flush=True)


def create_apk_folders(code):
    """The APK folder of the new language in every game (data\\apk\\<game>\\<code>), with a README.txt saying what goes there. -> the folders."""
    out = []
    for key, prof in GM.GAMES.items():
        folder = CH.FOLDERS.for_game(key).apk_for(code)
        try:
            os.makedirs(folder, exist_ok=True); readme = os.path.join(folder, 'README.txt')
            if not os.path.exists(readme):
                with open(readme, 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write('Put here the 3 APK files of %s for the language %s, taken from your phone:\n    base.apk, split_config.arm64_v8a.apk, split_UnityDataAssetPack.apk\n'
                            'The language chosen in the Esc menu decides which folder is read; without APK files in its folder, the English ones are used, otherwise the French ones.\n' % (prof.name, code))
            out.append(folder)
        except OSError as ex: print('APK folder not created (%s): %s' % (ex, folder), flush=True)
    return out


class LanguageScreen:
    def __init__(self, J, system_reader=None):
        self.J = J; self.zones = []; self.hovered = None; self.flags = {}
        self.needs_reload = False                          # (same interface as the Saves screen: nothing to read again when it closes)
        self.system_language = LG.system_language(system_reader)
        self.cur = I_SYSTEM; self.versions = {}           # language -> language of the game version it runs (the APK folders are looked at once per opening)
        self.mode = 'list'; self.first_row = 0            # 'list', 'flags', 'form', 'files'; first row of cards (or of flags) shown
        self.flag_codes = list(FL.names()); self.flag_cur = 0; self.flag_row = 0
        self.form = {'flag': None, 'code': '', 'name': '', 'error': None}; self.form_cur = FORM_CODE
        self.files = {'code': None, 'lines': []}; self.files_cur = FILES_LOAD

    def follows_system(self): return self.J.reg['language'] == 'system'

    def chosen(self):
        """The language the setting asks for (the system's when "System language" is checked): outlined in gold."""
        return self.system_language if self.follows_system() else self.J.reg['language']

    def game_version(self, lg):
        """The language of the game version that language `lg` runs (its own when its APK folder has the files, otherwise the one it falls back on); `lg` if it cannot be known."""
        if lg not in self.versions:
            target = getattr(self.J, 'game_version_of', None)
            try: self.versions[lg] = target(lg) if callable(target) else lg
            except Exception: self.versions[lg] = lg
        return self.versions[lg]

    def close(self):
        """Back button, Esc, right click: the window closes (from a form: back to the list); if the chosen language runs another game version, the game starts again in it on its title
        screen (the window is on the start menu, not on the title screen where Game._reload_step would do it)."""
        if self.mode != 'list': self.back(); return
        J = self.J; J._close_port_screen()
        pending = getattr(J, 'language_pending', None)
        if callable(pending) and pending(): J.reload_game()

    def back(self):
        """One step back: the flag picker or a form goes back to the list (the form, to the flag picker)."""
        self.mode = 'flags' if self.mode == 'form' else 'list'
        if self.mode == 'list': self.versions = {}

    def choose(self, setting):
        """The "Language" setting takes `setting` (a language code or 'system') and the port switches to it at once, exactly like the Esc menu's setting; nothing restarts before the window
        closes: a small notification says so when the game version will change."""
        J = self.J; J.reg['language'] = setting; LG.select_language(setting)
        pending = getattr(J, 'language_pending', None); toast = getattr(J, 'toast', None)
        if callable(pending) and callable(toast) and pending(): J.toast(N_('language.language_will_change_when_leave'), 3.0)

    def do_update(self): pass

    # ---- adding a language, editing its texts
    def start_adding(self):
        self.mode = 'flags'; self.flag_cur = 0; self.flag_row = 0
        return True

    def pick_flag(self, i):
        """The flag of the new language: the form opens."""
        if not 0 <= i < len(self.flag_codes): return False
        self.form = {'flag': self.flag_codes[i], 'code': '', 'name': '', 'error': None}; self.form_cur = FORM_CODE; self.mode = 'form'
        return True

    def form_error(self):
        """What keeps the form from creating the language (a key of the texts), None if nothing."""
        code = self.form['code'].strip().lower()
        if not LG.CODE.match(code): return 'new_language.code_invalid'
        if code in LG.LANGUAGES or os.path.exists(LG.path_of(code)): return 'new_language.code_taken'
        if not self.form['name'].strip(): return 'new_language.name_missing'
        return None

    def create(self):
        """"Create": the language's file is written (its own name, its flag, the English texts to translate) and its APK folders created; the file panel opens."""
        self.form['error'] = self.form_error()
        if self.form['error']: return False
        code = self.form['code'].strip().lower()
        try: LG.create_language(code, self.form['name'].strip(), self.form['flag'])
        except OSError as ex: self.form['error'] = english('new_language.write_failed') % ex; return False
        create_apk_folders(code)
        return self.edit(code)

    def edit(self, code):
        """The file panel of language `code`: its file is brought up to date first (the keys added since it was written, empty; the English texts of today: language.save_language)."""
        try: LG.save_language(code); lines = []
        except OSError as ex: lines = [(english('new_language.write_failed') % ex, RED)]
        self.files = {'code': code, 'lines': lines}; self.files_cur = FILES_LOAD; self.mode = 'files'
        return True

    def load_texts(self):
        """"Load the texts": the language's file is read again and checked (language.check_language); the result is shown in the panel, the problems written to
        data\\logs\\texts_<code>.txt. The texts on screen follow at once."""
        code = self.files['code']
        done, english_left, problems = LG.check_language(code)
        lines = [(english('new_language.loaded') % (done, english_left), WHITE)]
        report = os.path.join(CH.FOLDERS.logfiles, 'texts_%s.txt' % code)
        try:
            if problems:
                os.makedirs(os.path.dirname(report), exist_ok=True)
                with open(report, 'w', encoding='utf-8', newline='\r\n') as f: f.write('\n'.join(problems) + '\n')
                lines += [(pb, RED) for pb in problems[:3]] + [(english('new_language.problems') % (len(problems), shown_path(report)), RED)]
            elif os.path.exists(report): os.remove(report)
        except OSError: pass
        self.files['lines'] = lines; self.versions = {}
        return True

    # ---- inputs
    def items(self):
        """The items of the list, in keyboard order."""
        return [I_SYSTEM] + list(range(len(LANGUAGES))) + [I_ADD, I_EDIT, I_BACK]

    def press(self, i):
        """An item of the list (a card, the checkbox, the buttons). -> True if something happened (button sound)."""
        if i == I_BACK: self.close(); return True
        if i == I_SYSTEM: return self.toggle_system()
        if i == I_ADD: return self.start_adding()
        if i == I_EDIT: return self.edit(self.chosen())
        if not 0 <= i < len(LANGUAGES) or self.follows_system(): return False
        self.choose(LANGUAGES[i])                             # (the game starts again when the window closes, if its version changes)
        return True

    def toggle_system(self):
        """Checks / unchecks "System language". Checked: the setting follows the computer. Unchecked: the language displayed becomes the setting's own choice and the cursor goes to its card."""
        if self.follows_system():
            lg = LG.current_language(); self.choose(lg)
            self.cur = LANGUAGES.index(lg) if lg in LANGUAGES else 0
            return True
        self.choose('system')
        return True

    def _move(self, dx, dy):
        """Cursor move in the list: dx along a row of cards (or between the two buttons), dy from row to row (-1 up). The cards are skipped while the system's language is followed."""
        n = len(LANGUAGES); last_row = (n - 1) // COLUMNS; c = self.cur; cards = not self.follows_system()
        if c >= 0 and not cards: c = self.cur = I_SYSTEM
        if c == I_SYSTEM:
            if dy > 0 or dx > 0: self.cur = 0 if cards and n else I_ADD
            elif dy < 0 or dx < 0: self.cur = I_BACK
        elif c == I_BACK:
            if dy < 0 or dx < 0: self.cur = I_EDIT
            elif dy > 0 or dx > 0: self.cur = I_SYSTEM
        elif c in (I_ADD, I_EDIT):
            if dx: self.cur = I_EDIT if c == I_ADD else I_ADD
            elif dy < 0: self.cur = min(n - 1, last_row * COLUMNS + (0 if c == I_ADD else COLUMNS - 1)) if cards and n else I_SYSTEM
            elif dy > 0: self.cur = I_BACK
        elif dx:
            k = c + dx
            self.cur = I_SYSTEM if k < 0 else (I_ADD if k >= n else k)
        else:
            row = c // COLUMNS + dy
            if row < 0: self.cur = I_SYSTEM
            elif row > last_row: self.cur = I_ADD
            else: self.cur = min(n - 1, row * COLUMNS + c % COLUMNS)
        if self.cur >= 0: self._follow(self.cur // COLUMNS)

    def _follow(self, row):
        """The cards scroll so that `row` is shown."""
        if row < self.first_row: self.first_row = row
        elif row >= self.first_row + ROWS: self.first_row = row - ROWS + 1

    def _flag_move(self, dx, dy):
        n = len(self.flag_codes)
        if not n: return
        self.flag_cur = max(0, min(n - 1, self.flag_cur + dx + dy * F_COLUMNS)); row = self.flag_cur // F_COLUMNS
        if row < self.flag_row: self.flag_row = row
        elif row >= self.flag_row + F_ROWS: self.flag_row = row - F_ROWS + 1

    def wheel(self, sy):
        """Mouse wheel: the cards or the flags scroll."""
        if self.mode == 'flags':
            rows = (len(self.flag_codes) - 1) // F_COLUMNS + 1
            self.flag_row = max(0, min(max(0, rows - F_ROWS), self.flag_row - int(np.sign(sy))))
        elif self.mode == 'list':
            rows = (len(LANGUAGES) - 1) // COLUMNS + 1
            self.first_row = max(0, min(max(0, rows - ROWS), self.first_row - int(np.sign(sy))))

    def text(self, t):
        """Typed text (on_text): into the field of the form."""
        if self.mode != 'form' or self.form_cur not in (FORM_CODE, FORM_NAME): return
        field = 'code' if self.form_cur == FORM_CODE else 'name'
        t = ''.join(ch for ch in t if ch.isprintable())
        if field == 'code': t = t.lower()[:max(0, 5 - len(self.form['code']))]
        else: t = t[:max(0, 40 - len(self.form['name']))]
        self.form[field] += t; self.form['error'] = None

    def key_press(self, symbol, modifiers=0):
        K = pyglet.window.key; action = self.J.reg.action_of(symbol)
        typing = self.mode == 'form' and self.form_cur in (FORM_CODE, FORM_NAME)
        if symbol == K.ESCAPE or (not typing and (symbol == K.BACKSPACE or action == 'B')): self.close(); return True
        enter = symbol in (K.RETURN, K.ENTER) or (not typing and action in ('A', 'menu'))
        if self.mode == 'form': return self._form_key(symbol, modifiers, enter, typing, action)
        if self.mode == 'flags':
            moves = {'left': (-1, 0), 'cam_left': (-1, 0), 'right': (1, 0), 'cam_right': (1, 0), 'up': (0, -1), 'down': (0, 1)}
            if action in moves: self._flag_move(*moves[action])
            elif symbol == K.PAGEUP: self._flag_move(0, -F_ROWS)
            elif symbol == K.PAGEDOWN: self._flag_move(0, F_ROWS)
            elif enter and self.pick_flag(self.flag_cur): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        if self.mode == 'files':
            if action in ('left', 'cam_left', 'up'): self.files_cur = (self.files_cur - 1) % 3
            elif action in ('right', 'cam_right', 'down') or symbol == K.TAB: self.files_cur = (self.files_cur + 1) % 3
            elif enter: self._files_press(self.files_cur); self.J.sound.play_sfx(SFX_BUTTON)
            return True
        if action in ('left', 'cam_left'): self._move(-1, 0); return True          # (the keys of "Controls"; the camera keys too, as left / right)
        if action in ('right', 'cam_right'): self._move(1, 0); return True
        if action == 'up': self._move(0, -1); return True
        if action == 'down': self._move(0, 1); return True
        if symbol == K.TAB: self._move(-1 if modifiers & K.MOD_SHIFT else 1, 0); return True
        if enter:
            if self.press(self.cur): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        return True

    def _form_key(self, symbol, modifiers, enter, typing, action):
        K = pyglet.window.key
        if typing and symbol == K.BACKSPACE:
            field = 'code' if self.form_cur == FORM_CODE else 'name'; self.form[field] = self.form[field][:-1]; self.form['error'] = None; return True
        if symbol in (K.TAB, K.DOWN) or (not typing and action in ('down', 'right', 'cam_right')): self.form_cur = (self.form_cur + 1) % 4; return True
        if symbol == K.UP or (not typing and action in ('up', 'left', 'cam_left')): self.form_cur = (self.form_cur - 1) % 4; return True
        if enter:
            if self.form_cur == FORM_CANCEL: self.back()
            elif self.form_cur == FORM_CODE: self.form_cur = FORM_NAME
            elif self.create(): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        return True

    def _files_press(self, i):
        if i == FILES_OPEN: open_folder(LG.FOLDER)
        elif i == FILES_LOAD: self.load_texts()
        else: self.mode = 'list'; self.versions = {}

    def click(self, x, y, button):
        if button == pyglet.window.mouse.RIGHT: self.close(); return
        for x0, y0, x1, y1, i in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                if i == I_BACK: self.close(); self.J.sound.play_sfx(SFX_BUTTON); return
                if self.mode == 'flags': self.flag_cur = i; ok = self.pick_flag(i)
                elif self.mode == 'form':
                    self.form_cur = i; ok = True
                    if i == FORM_CREATE: ok = self.create()
                    elif i == FORM_CANCEL: self.back()
                elif self.mode == 'files': self.files_cur = i; self._files_press(i); ok = True
                else: self.cur = i; ok = self.press(i)
                if ok: self.J.sound.play_sfx(SFX_BUTTON)
                return

    def hover(self, x, y):
        self.hovered = None
        for x0, y0, x1, y1, i in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.hovered = i
                if self.mode == 'list' or i == I_BACK: self.cur = i if self.mode == 'list' else self.cur
                elif self.mode == 'flags': self.flag_cur = i
                elif self.mode == 'files': self.files_cur = i
                return

    # ---- drawing
    def _flag_tex(self, code):
        if code not in self.flags: self.flags[code] = _texture(FL.flag(code))
        return self.flags[code]

    def draw_all(self, J, cx, cy, ui_scale):
        P = J.pause
        ui_scale = min(ui_scale, 0.97 * J.height / (BORDER[3] - BORDER[1] + BACK_GAP + BACK_HEIGHT)); k = ui_scale * 800.0 / 900.0
        U = lambda x, y: (cx + x * ui_scale, cy + y * ui_scale)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        background = pyglet.shapes.Rectangle(0, 0, J.width, J.height, color=(0, 0, 0)); background.opacity = 170; background.draw()
        x0, y0 = U(BORDER[0], BORDER[1]); x1, y1 = U(BORDER[2], BORDER[3]); P._border(x0, y0, x1 - x0, y1 - y0, k)
        P._restore_blend()
        mouse = J.last_device == 'mouse'; zones = []

        def text(t, x, y, size_value, clr=WHITE, translate=True, left=False, width=None):
            label = P._label(t, size_value * ui_scale * 0.75, clr, translate); px, py = U(x, y)
            if width is not None and label.content_width > width * ui_scale:            # (a long name or caption: smaller, to stay in its place)
                label = P._label(t, size_value * ui_scale * 0.75 * width * ui_scale / label.content_width, clr, translate)
            label.x = px if left else px - label.content_width / 2; label.y = py - size_value * ui_scale * 0.30; label.draw()

        def wrapped(t, x, y, width, size_value, clr=WHITE, line_h=1.5):
            """A text wrapped to `width` units from (x, y) downward. -> y under its last line."""
            for line in LG.wrap(t, width * ui_scale, lambda s: P._label(s, size_value * ui_scale * 0.75, clr, False).content_width):
                text(line, x, y, size_value, clr, translate=False, left=True); y -= size_value * line_h
            return y

        def button(caption, x, y, w, h, ident, selected, ok=True):
            a, b = U(x - w / 2, y - h / 2); W, H = w * ui_scale, h * ui_scale
            over = mouse and self.hovered == ident
            P._plate(a, b, W, H, k, (over or (selected and not mouse)) and ok, grayed=not ok)
            if selected and not mouse and ok: P._cursor(a - 24 * ui_scale, b + H / 2, 28 * ui_scale)
            P._restore_blend()
            text(caption, x, y, 18, WHITE if ok else GRAY, width=w - 16)
            if ok: zones.append((a, b, a + W, b + H, ident))

        def sprite(tex, x, y, w, h, dim=False):
            fw, fh = w * ui_scale, h * ui_scale; fx, fy = U(x, y)
            spr = pyglet.sprite.Sprite(tex, fx - fw / 2, fy - fh / 2); spr.scale_x = fw / tex.width; spr.scale_y = fh / tex.height
            if dim: spr.color = (115, 115, 115)
            spr.draw()

        if self.mode == 'flags': self._draw_flags(text, sprite, U, ui_scale, k, mouse, zones, P)
        elif self.mode == 'form': self._draw_form(text, wrapped, sprite, button, U, ui_scale, k, zones)
        elif self.mode == 'files': self._draw_files(text, wrapped, button)
        else: self._draw_list(text, sprite, button, U, ui_scale, k, mouse, zones, P)
        a, b = U(BORDER[2] - BACK_WIDTH - BACK_GAP, BORDER[1] - BACK_GAP - BACK_HEIGHT); w, h = BACK_WIDTH * ui_scale, BACK_HEIGHT * ui_scale          # (outside the frame, under its bottom right corner, like the Esc menu's)
        back_selected = self.mode == 'list' and self.cur == I_BACK and not mouse
        P._back_button(a, b, w, h, (mouse and self.hovered == I_BACK) or back_selected)
        if back_selected: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
        zones.append((a, b, a + w, b + h, I_BACK)); self.zones = zones

    def _draw_list(self, text, sprite, button, U, ui_scale, k, mouse, zones, P):
        text(TITLE, 0, BORDER[3] - 30, 26)
        system = self.follows_system()
        a, b = U(-SYS_W / 2, SYS_Y - SYS_H / 2); w, h = SYS_W * ui_scale, SYS_H * ui_scale
        over = mouse and self.hovered == I_SYSTEM; selected = self.cur == I_SYSTEM and not mouse
        P._plate(a, b, w, h, k, over or selected)
        if selected: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
        P._restore_blend()
        cb = 22 * ui_scale; bx, by = a + 16 * ui_scale, b + (h - cb) / 2; clr = GOLD if system else WHITE[:3]
        pyglet.shapes.Rectangle(bx, by, cb, cb, color=(0, 0, 0)).draw()
        pyglet.shapes.Box(bx, by, cb, cb, thickness=max(1.5, 2 * k), color=clr).draw()
        if system:
            pyglet.shapes.Line(bx + cb * 0.2, by + cb * 0.5, bx + cb * 0.42, by + cb * 0.22, thickness=max(2.0, 3 * k), color=GOLD).draw()
            pyglet.shapes.Line(bx + cb * 0.42, by + cb * 0.22, bx + cb * 0.84, by + cb * 0.82, thickness=max(2.0, 3 * k), color=GOLD).draw()
        text(SYSTEM_CAPTION, -SYS_W / 2 + 16 + 22 + 12, SYS_Y, 20, (GOLD + (255,)) if system else WHITE, left=True, width=SYS_W - 60)
        zones.append((a, b, a + w, b + h, I_SYSTEM))
        rows = (len(LANGUAGES) - 1) // COLUMNS + 1; self.first_row = max(0, min(self.first_row, rows - ROWS))
        for i, lg in enumerate(LANGUAGES):
            if not self.first_row <= i // COLUMNS < self.first_row + ROWS: continue
            xc, yc = card_center(i, self.first_row); a, b = U(xc - CARD_W / 2, yc - CARD_H / 2); w, h = CARD_W * ui_scale, CARD_H * ui_scale
            here = lg == self.chosen(); ok = not system
            over = mouse and self.hovered == i; selected = self.cur == i and not mouse
            P._plate(a, b, w, h, k, (over or selected) and ok)
            if here: pyglet.shapes.Box(a, b, w, h, thickness=max(2.0, 3 * k), color=GOLD).draw()          # (the language chosen)
            if selected and ok: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
            P._restore_blend()
            sprite(self._flag_tex(LG.FLAGS.get(lg, lg[3:])), xc, yc + 16, FLAG_W, FLAG_H, dim=not ok)
            name_clr = (GOLD + (255,)) if (here and ok) else (WHITE if ok else GRAY)
            version = self.game_version(lg)
            text(LG.NAMES.get(lg, lg), xc, yc - 17, 17, name_clr, translate=False, width=CARD_W - 10)          # (in its own language)
            if version != lg: text(LG.tr(GAME_CAPTION) % LG.language_name(version), xc, yc - 34, 11, WHITE if ok else GRAY, translate=False, width=CARD_W - 10)     # (in the language displayed)
            if ok: zones.append((a, b, a + w, b + h, i))
        if rows > ROWS:                                       # (more rows below or above: small marks at the right of the cards)
            top = CARDS_TOP; bottom = CARDS_TOP - ROWS * (CARD_H + GAP_Y) + GAP_Y; span = top - bottom
            x = BORDER[2] - 10; y_a = top - span * self.first_row / rows; y_b = top - span * (self.first_row + ROWS) / rows
            a, b = U(x, y_b); _, b2 = U(x, y_a)
            pyglet.shapes.Rectangle(a - 2 * ui_scale, b, 4 * ui_scale, b2 - b, color=(200, 200, 200)).draw()
        button(english('new_language.add'), -(BTN_W / 2 + 6), BTN_Y, BTN_W, BTN_H, I_ADD, self.cur == I_ADD)
        button(english('new_language.edit_texts'), BTN_W / 2 + 6, BTN_Y, BTN_W, BTN_H, I_EDIT, self.cur == I_EDIT)

    def _draw_flags(self, text, sprite, U, ui_scale, k, mouse, zones, P):
        text(english('new_language.title'), 0, BORDER[3] - 30, 26, translate=False)
        text(english('new_language.choose_flag'), 0, BORDER[3] - 62, 18, translate=False)
        top = BORDER[3] - 88; n = len(self.flag_codes); rows = (n - 1) // F_COLUMNS + 1
        self.flag_row = max(0, min(self.flag_row, max(0, rows - F_ROWS)))
        for i in range(self.flag_row * F_COLUMNS, min(n, (self.flag_row + F_ROWS) * F_COLUMNS)):
            row, col = divmod(i, F_COLUMNS); xc = (col - (F_COLUMNS - 1) / 2.0) * (F_W + 4); yc = top - F_H / 2 - (row - self.flag_row) * (F_H + 4)
            a, b = U(xc - F_W / 2, yc - F_H / 2); w, h = F_W * ui_scale, F_H * ui_scale
            selected = i == self.flag_cur and (not mouse or self.hovered == i)
            if selected: pyglet.shapes.Box(a, b, w, h, thickness=max(2.0, 3 * k), color=GOLD).draw()
            code = self.flag_codes[i]
            sprite(self._flag_tex(code), xc, yc + 7, 48, 32)
            text(code.upper(), xc, yc - 17, 11, (GOLD + (255,)) if selected else WHITE, translate=False, width=F_W - 4)
            zones.append((a, b, a + w, b + h, i))
        if 0 <= self.flag_cur < n:
            text('%s  %s' % (self.flag_codes[self.flag_cur].upper(), FL.names().get(self.flag_codes[self.flag_cur], '')), 0, BORDER[1] + 24, 16, GOLD + (255,), translate=False, width=360)

    def _draw_form(self, text, wrapped, sprite, button, U, ui_scale, k, zones):
        f = self.form
        text(english('new_language.title'), 0, BORDER[3] - 30, 26, translate=False)
        if f['flag']: sprite(self._flag_tex(f['flag']), 0, BORDER[3] - 100, 96, 64)
        y = BORDER[3] - 170
        for ident, field, label, hint in ((FORM_CODE, 'code', 'new_language.code', 'new_language.code_hint'), (FORM_NAME, 'name', 'new_language.name', 'new_language.name_hint')):
            text(english(label), -170, y, 18, translate=False, left=True)
            a, b = U(-170, y - 52); w, h = 340 * ui_scale, 34 * ui_scale
            active = self.form_cur == ident
            pyglet.shapes.Rectangle(a, b, w, h, color=(0, 0, 0)).draw()
            pyglet.shapes.Box(a, b, w, h, thickness=max(1.5, 2 * k), color=GOLD if active else (180, 180, 180)).draw()
            text(f[field] + ('_' if active else ''), -160, y - 35, 18, WHITE, translate=False, left=True, width=320)
            zones.append((a, b, a + w, b + h, ident))
            wrapped(english(hint), -170, y - 68, 340, 13, HINT)
            y -= 116
        if f['error']: wrapped(english(f['error']), -170, y + 4, 340, 14, RED)
        button(english('new_language.create'), -95, BORDER[1] + 40, 170, BTN_H, FORM_CREATE, self.form_cur == FORM_CREATE)
        button(english('new_language.cancel'), 95, BORDER[1] + 40, 170, BTN_H, FORM_CANCEL, self.form_cur == FORM_CANCEL)

    def _draw_files(self, text, wrapped, button):
        code = self.files['code']
        text(LG.NAMES.get(code, code or ''), 0, BORDER[3] - 30, 26, translate=False)
        y = wrapped(english('new_language.file_ready'), -180, BORDER[3] - 70, 360, 15)
        text(shown_path(LG.path_of(code)), -180, y - 2, 14, GOLD + (255,), translate=False, left=True, width=360); y -= 25
        y = wrapped(english('new_language.how_to_translate'), -180, y - 8, 360, 14)
        for line, clr in self.files['lines']: y = wrapped(line, -180, y - 6, 360, 13 if clr == RED else 15, clr)
        for i, key in enumerate(('new_language.open_folder', 'new_language.load', 'new_language.done')):
            button(english(key), 0, BORDER[1] + 150 - i * 54, 260, BTN_H, i, self.files_cur == i)
