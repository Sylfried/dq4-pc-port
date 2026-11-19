""""Saves" screen of the start menu (in place of the mobile game's "Sauv. cloud" slot): export and import save files.

Does not exist in the original game: window drawn in the style of the other menus (black frame, the game's plates and back button). The file logic is in `saves.py`.
The file is chosen through the Windows dialog box (tkinter, in a separate thread: the game window stays responsive); without tkinter, falls back to port folders (`saves/export`, `saves/import`)."""
import os
import pyglet
from pyglet import gl
from dq456_pc.persistence import saves as S
from dq456_pc import language as LG
from dq456_pc.language import tr, N_

BORDER = (-215.0, -215.0, 215.0, 215.0)                 # interface units, origin at the center of the 450 x 800 column, Y upward
WHITE = (255, 255, 255, 255); HELPTEXT = (170, 170, 170, 255); GRAY = (128, 128, 128, 255); RED = (255, 110, 110, 255); GREEN = (150, 235, 160, 255)
YELLOW = (255, 235, 4)
SFX_BUTTON = 300                                          # press sound effect of a menu button (like window.SFX_BUTTON)
TITLE = N_('saves.saves')
BUTTONS = (N_('saves.export'), N_('saves.import'))                # (drawn by Pause._label, which translates them)
BTN_Y, BTN_L, BTN_H, BTN_X = -42.0, 180.0, 50.0, 100.0
BACK_WIDTH, BACK_HEIGHT, BACK_GAP = 62.0, 52.0, 8.0          # (the back button is under the frame, outside)
I_BACK = 2
EXPLANATION = (N_('saves.export_saves_adventure_logs_data1'),
               N_('saves.import_reads_zip_like_data1'),
               N_('saves.replaced_files_first_copied_before'))           # (translated line by line when drawn: see draw_all)
FILES = (N_('saves.save_file'), N_('saves.save_files'))             # (singular, plural): English has its own templates
SAVESTATES = (N_('saves.save_state'), N_('saves.save_states'))


def _pluralize(n, models):
    """"1 fichier de sauvegarde", "3 fichiers de sauvegarde": `models` = (singular template, plural template). The language's plural rule: in French 0 and 1 are singular ("0 etat instantane"), in English only 1 is ("0 save states")."""
    singular = LG.plural_one(n)
    return tr(models[0] if singular else models[1]) % n


class SavesScreen:
    def __init__(self, J):
        self.J = J; self.cur = 0; self.zones = []; self.hovered = None; self.dialogue = None; self.action = None; self.msg = []; self.msg_clr = WHITE
        self.needs_reload = False                          # true after a successful import: the game window rereads the adventure logs

    # ---- logic
    def _folders(self):
        a = self.J.args
        return a.saves_write, a.saves_read

    def export_saves(self):
        if self.dialogue is not None: return
        wdir, _ = self._folders()
        self.action = 'export'; self.dialogue = S.Dialogue('save', tr('saves.export_saves'), wdir if os.path.isdir(wdir) else None, S.default_export_name())
        self._say([tr('saves.choose_where_save_file_window')], HELPTEXT)

    def import_saves(self):
        if self.dialogue is not None: return
        wdir, _ = self._folders()
        self.action = 'import'; self.dialogue = S.Dialogue('open', tr('saves.import_saves'), None)
        self._say([tr('saves.choose_zip_save_files_window')], HELPTEXT)

    def _say(self, lines, clr=WHITE):
        self.msg = list(lines); self.msg_clr = clr

    def do_update(self):
        """Called every frame: handles the dialog box's response."""
        d = self.dialogue
        if d is None or d.result is None: return
        self.dialogue = None; wdir, rdir = self._folders(); action, self.action = self.action, None
        try:
            if action == 'export':
                if d.unavailable:                                     # no dialog box: a port folder
                    path = os.path.join(wdir, 'export', S.default_export_name())
                elif not d.result: self._say([tr('saves.export_canceled')], HELPTEXT); return
                else: path = d.result[0]
                nj, n_savestates = S.export_saves(wdir, rdir, path)
                self._say([tr('saves.exported') % (_pluralize(nj, FILES), _pluralize(n_savestates, SAVESTATES)), path], GREEN)
            elif action == 'import':
                if d.unavailable:
                    folder = os.path.join(wdir, 'import'); os.makedirs(folder, exist_ok=True)
                    if not any(os.scandir(folder)):
                        try: os.startfile(folder)                      # (Windows) opens the folder in Explorer
                        except Exception: pass
                        self._say([tr('saves.no_file_dialog_available_put'), folder, tr('saves.then_click_import_again')], RED); return
                    sources = [folder]
                elif not d.result: self._say([tr('saves.import_canceled')], HELPTEXT); return
                else: sources = d.result
                nj, n_savestates, copied, pb = S.import_saves(sources, wdir, rdir)
                self.needs_reload = True; eng = self.J.engine
                new = eng.reread_savefiles()                         # the lists ("Continuer", "Resume", "Supprimer", "Auto") immediately show the new adventure logs
                if hasattr(self.J, 'follow_journals'): self.J.follow_journals(prune=False)           # (nothing deleted by the import itself: its logs are kept as they are)
                lines = [tr('saves.imported') % (_pluralize(nj, FILES), _pluralize(n_savestates, SAVESTATES))]
                if copied: lines.append(tr('saves.previous_files_copied') % copied)
                if pb: lines.append(tr('saves.skipped') % '; '.join(pb))
                if eng.initial_buttons_state(new) != eng.initial_buttons_state(self.J.initial_status):
                    lines.append(tr('saves.update_grayed_out_buttons_start'))
                self._say(lines, GREEN)
        except Exception as ex:
            self._say([tr('saves.failed') % (ex,)], RED)

    # ---- inputs
    def press(self, i):
        if i == 0: self.export_saves(); return True
        if i == 1: self.import_saves(); return True
        if i == I_BACK: self.J._close_port_screen(); return True
        return False

    def key_press(self, symbol, modifiers=0):
        K = pyglet.window.key; action = self.J.reg.action_of(symbol)
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': self.J._close_port_screen(); return True
        if action in ('left', 'up', 'cam_left'): self.cur = (self.cur - 1) % 3; return True          # (the keys of "Controls", no more fixed arrows)
        if action in ('right', 'down', 'cam_right') or symbol == K.TAB: self.cur = (self.cur + 1) % 3; return True
        if symbol in (K.RETURN, K.ENTER, K.SPACE) or action == 'A':
            if self.press(self.cur): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        return True

    def click(self, x, y, button):
        if button == pyglet.window.mouse.RIGHT: self.J._close_port_screen(); return
        for x0, y0, x1, y1, i in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.cur = i
                if self.press(i): self.J.sound.play_sfx(SFX_BUTTON)
                return

    def hover(self, x, y):
        self.hovered = None
        for x0, y0, x1, y1, i in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1: self.hovered = i; self.cur = i; return

    # ---- drawing
    def _lines(self, P, text, width_px, size_value):
        """Text wrapped at words (and at characters for a path without spaces) to fit within `width_px` pixels."""
        out = []
        for para in text.split('\n'):
            cur = ''
            for word in para.split(' '):
                attempt = (cur + ' ' + word) if cur else word
                if P._label(attempt, size_value).content_width <= width_px: cur = attempt; continue
                if cur: out.append(cur)
                while P._label(word, size_value).content_width > width_px and len(word) > 1:       # word too long (path): cut at the last character that fits
                    n = len(word)
                    while n > 1 and P._label(word[:n], size_value).content_width > width_px: n -= 1
                    out.append(word[:n]); word = word[n:]
                cur = word
            out.append(cur)
        return out

    def draw_all(self, J, cx, cy, ui_scale):
        P = J.pause; k = ui_scale * 800.0 / 900.0
        ui_scale = min(ui_scale, 0.97 * J.height / (BORDER[3] - BORDER[1] + BACK_GAP + BACK_HEIGHT)); k = ui_scale * 800.0 / 900.0
        U = lambda x, y: (cx + x * ui_scale, cy + y * ui_scale)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        background = pyglet.shapes.Rectangle(0, 0, J.width, J.height, color=(0, 0, 0)); background.opacity = 170; background.draw()           # the start menu stays visible, darkened
        x0, y0 = U(BORDER[0], BORDER[1]); x1, y1 = U(BORDER[2], BORDER[3]); P._border(x0, y0, x1 - x0, y1 - y0, k)
        P._restore_blend()

        def text(t, x, y, size_value, clr=WHITE, anchor=1):
            label = P._label(t, size_value * ui_scale * 0.75, clr); w = label.content_width; px, py = U(x, y)
            label.x = px - (w / 2 if anchor == 1 else (w if anchor == 2 else 0)); label.y = py - size_value * ui_scale * 0.30; label.draw()
        text(TITLE, 0, BORDER[3] - 40, 26)
        y = BORDER[3] - 82; wid = (BORDER[2] - BORDER[0] - 40) * ui_scale
        for line in EXPLANATION:
            for l in self._lines(P, tr(line), wid, 13 * ui_scale * 0.75):          # (translated as a whole before being wrapped at words)
                text(l, BORDER[0] + 20, y, 13, HELPTEXT, 0); y -= 17
            y -= 4
        mouse = J.last_device == 'mouse'; zones = []
        for i, lib in enumerate(BUTTONS):
            xc = (i * 2 - 1) * BTN_X; a, b = U(xc - BTN_L / 2, BTN_Y - BTN_H / 2); w, h = BTN_L * ui_scale, BTN_H * ui_scale
            selected = self.cur == i; over = mouse and self.hovered == i; occupied = self.dialogue is not None
            P._plate(a, b, w, h, k, over or (selected and not mouse))                    # (mouse: the plate under the pointer darkens, no yellow outline)
            if selected and not mouse: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
            P._restore_blend(); text(lib, xc, BTN_Y, 20, GRAY if occupied else WHITE)
            zones.append((a, b, a + w, b + h, i))
        # result message
        y = BTN_Y - BTN_H / 2 - 30; msg_width = wid
        for line in self.msg:
            for l in self._lines(P, line, msg_width, 14 * ui_scale * 0.75):
                text(l, BORDER[0] + 20, y, 14, self.msg_clr, 0); y -= 18
        a, b = U(BORDER[2] - BACK_WIDTH - BACK_GAP, BORDER[1] - BACK_GAP - BACK_HEIGHT); w, h = BACK_WIDTH * ui_scale, BACK_HEIGHT * ui_scale          # (outside the frame, under its bottom right corner, like the Esc menu's)
        over = mouse and self.hovered == I_BACK
        P._back_button(a, b, w, h, over or (self.cur == I_BACK and not mouse))
        if self.cur == I_BACK and not mouse: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
        zones.append((a, b, a + w, b + h, I_BACK)); self.zones = zones
