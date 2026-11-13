"""Language screen of the start menu: opened by the globe plate between "License" and "Saves"; each game language is a large flag with its name, chosen by its picture.

Does not exist in the original game: window drawn like the "Saves" screen (black frame, the game's plates, back button). Choosing a language does exactly what the "Language" setting of the
Esc menu does: the tool switches to it at once (the names of the languages are written in the language displayed: "French" / "English", "French" / "English") and the game starts again
in that language, on its title screen, when this window is closed. The chosen language is outlined in gold; a language whose APK files are missing is grayed.

"System language": a checkbox above the flags, checked by default (the "Language" setting's `system` value, its default). Checked, the flags are grayed and the game follows the computer's
language (checking it switches to that language if another one is played); unchecked, a flag can be chosen, the cursor starting on the system's language."""
import numpy as np
import pyglet
from pyglet import gl
from dq4_pc import language as LG
from dq4_pc.language import N_
from dq4_pc.menus import flags as FL

BORDER = (-200.0, -120.0, 200.0, 190.0)                 # interface units, origin at the center of the 450 x 800 column, Y upward (the back button is under it, outside)
WHITE = (255, 255, 255, 255); GRAY = (128, 128, 128, 255); GOLD = (255, 235, 4)
SFX_BUTTON = 300
TITLE = N_('settings.language')
SYSTEM_CAPTION = N_('menus.system_language')
LANGUAGES = (('fr', N_('settings.french')), ('en', N_('settings.english')))      # (in the language displayed, like the "Language" setting's values)
CARD_W, CARD_H, CARD_X, CARD_Y = 150.0, 150.0, 85.0, -20.0  # the two cards (flag above, name below), centered at x = -CARD_X and +CARD_X
SYS_Y, SYS_W, SYS_H = 108.0, 320.0, 44.0                  # the "System language" checkbox
FLAG_PX = (120, 80)                                       # texture of each flag (pixels, 3:2); drawn 108 x 72 units
BACK_WIDTH, BACK_HEIGHT, BACK_GAP = 62.0, 52.0, 8.0
I_SYSTEM, I_BACK = len(LANGUAGES), len(LANGUAGES) + 1
ORDER = (I_SYSTEM, 0, 1, I_BACK)                          # keyboard order: the checkbox, the flags, the back button


def _texture(arr):
    """pyglet texture of an RGBA array (top row first)."""
    h, w = arr.shape[:2]
    img = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(arr[::-1]).tobytes())
    t = img.get_texture(); gl.glBindTexture(t.target, t.id)
    gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    return t


class LanguageScreen:
    def __init__(self, J, system_reader=None):
        self.J = J; self.zones = []; self.hovered = None; self.flags = {}
        self.needs_reload = False                          # (same interface as the Sauvegardes screen: nothing to read again when it closes)
        self.available = {lg: (lg == J.game_language or J.other_game_language() == lg) for lg, _ in LANGUAGES}
        self.system_language = LG.system_language(system_reader)
        self.cur = I_SYSTEM

    def follows_system(self): return self.J.reg['language'] == 'system'

    def chosen(self):
        """The language the setting asks for (the system's when "System language" is checked): outlined in gold; the game starts in it when the window closes."""
        return self.system_language if self.follows_system() else self.J.reg['language']

    def close(self):
        """Back button, Esc, right click: the window closes; if another language was chosen, the game starts again in it on its title screen (the window is on the start menu, not on
        the title screen where Game._reload_step would do it)."""
        J = self.J; J._close_port_screen()
        pending = getattr(J, 'language_pending', None)
        if callable(pending) and pending(): J.reload_game()

    def choose(self, setting):
        """The "Language" setting takes `setting` ('fr', 'en' or 'system') and the tool switches to it at once, exactly like the Esc menu's setting; nothing restarts before the window closes:
        a small notification says so when the game's language will change."""
        J = self.J; J.reg['language'] = setting; LG.select_language(setting)
        pending = getattr(J, 'language_pending', None); toast = getattr(J, 'toast', None)
        if callable(pending) and callable(toast) and pending(): J.toast(N_('menus.language_will_change_when_leave'), 3.0)

    def do_update(self): pass

    # ---- inputs
    def press(self, i):
        """A card, the checkbox or the back button. -> True if something happened (button sound)."""
        if i == I_BACK: self.close(); return True
        if i == I_SYSTEM: return self.toggle_system()
        if not 0 <= i < len(LANGUAGES) or self.follows_system(): return False
        lg = LANGUAGES[i][0]
        if not self.available[lg]: return False
        self.choose(lg)                                       # (the game starts again in it when the window closes)
        return True

    def toggle_system(self):
        """Checks / unchecks "System language". Checked: the setting follows the computer (if the game is played in another language, it starts again in the system's one when the window
        closes). Unchecked: the language being played becomes the setting's own choice and the cursor goes to the system's language flag."""
        if self.follows_system():
            self.choose(self.J.game_language)
            self.cur = next((i for i, (lg, _) in enumerate(LANGUAGES) if lg == self.system_language), 0)
            return True
        self.choose('system')
        return True

    def _move(self, d):
        """Next / previous item in ORDER, skipping the flags while the system's language is followed."""
        order = [i for i in ORDER if not (0 <= i < len(LANGUAGES) and self.follows_system())]
        k = order.index(self.cur) if self.cur in order else 0
        self.cur = order[(k + d) % len(order)]

    def key_press(self, symbol, modifiers=0):
        K = pyglet.window.key; action = self.J.reg.action_of(symbol)
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': self.close(); return True
        if action in ('left', 'up', 'cam_left'): self._move(-1); return True          # (the keys of "Controls"; the camera keys too, as left / right)
        if action in ('right', 'down', 'cam_right') or symbol == K.TAB: self._move(1); return True
        if symbol in (K.RETURN, K.ENTER) or action in ('A', 'menu'):
            if self.press(self.cur): self.J.sound.play_sfx(SFX_BUTTON)
            return True
        return True

    def click(self, x, y, button):
        if button == pyglet.window.mouse.RIGHT: self.close(); return
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
    def draw_all(self, J, cx, cy, ui_scale):
        P = J.pause
        ui_scale = min(ui_scale, 0.97 * J.height / (BORDER[3] - BORDER[1] + BACK_GAP + BACK_HEIGHT)); k = ui_scale * 800.0 / 900.0
        U = lambda x, y: (cx + x * ui_scale, cy + y * ui_scale)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        background = pyglet.shapes.Rectangle(0, 0, J.width, J.height, color=(0, 0, 0)); background.opacity = 170; background.draw()
        x0, y0 = U(BORDER[0], BORDER[1]); x1, y1 = U(BORDER[2], BORDER[3]); P._border(x0, y0, x1 - x0, y1 - y0, k)
        P._restore_blend()

        def text(t, x, y, size_value, clr=WHITE, translate=True, left=False):
            label = P._label(t, size_value * ui_scale * 0.75, clr, translate); px, py = U(x, y); label.x = px if left else px - label.content_width / 2; label.y = py - size_value * ui_scale * 0.30; label.draw()
        text(TITLE, 0, BORDER[3] - 36, 26)
        mouse = J.last_device == 'mouse'; zones = []; system = self.follows_system()
        # "System language": a plate with a box (checked: a gold mark) and the label
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
        text(SYSTEM_CAPTION, -SYS_W / 2 + 16 + 22 + 12, SYS_Y, 20, (GOLD + (255,)) if system else WHITE, left=True)
        zones.append((a, b, a + w, b + h, I_SYSTEM))
        for i, (lg, name) in enumerate(LANGUAGES):
            xc = (i * 2 - 1) * CARD_X; a, b = U(xc - CARD_W / 2, CARD_Y - CARD_H / 2); w, h = CARD_W * ui_scale, CARD_H * ui_scale
            here = lg == self.chosen(); ok = self.available[lg] and not system
            over = mouse and self.hovered == i; selected = self.cur == i and not mouse
            P._plate(a, b, w, h, k, (over or selected) and ok)
            if here: pyglet.shapes.Box(a, b, w, h, thickness=max(2.0, 3 * k), color=GOLD).draw()          # (the language chosen: the game's after the window closes)
            if selected and ok: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
            P._restore_blend()
            if lg not in self.flags: self.flags[lg] = _texture(FL.flag(lg, *FLAG_PX))
            t = self.flags[lg]; fw, fh = 108 * ui_scale, 72 * ui_scale; fx, fy = U(xc, CARD_Y + 22)
            spr = pyglet.sprite.Sprite(t, fx - fw / 2, fy - fh / 2); spr.scale_x = fw / t.width; spr.scale_y = fh / t.height
            if not ok: spr.color = (115, 115, 115)
            spr.draw()
            text(name, xc, CARD_Y - CARD_H / 2 + 26, 22, (GOLD + (255,)) if (here and ok) else (WHITE if ok else GRAY))          # (in the language displayed)
            if ok: zones.append((a, b, a + w, b + h, i))
        a, b = U(BORDER[2] - BACK_WIDTH - BACK_GAP, BORDER[1] - BACK_GAP - BACK_HEIGHT); w, h = BACK_WIDTH * ui_scale, BACK_HEIGHT * ui_scale          # (outside the frame, under its bottom right corner, like the Esc menu's)
        over = mouse and self.hovered == I_BACK
        P._back_button(a, b, w, h, over or (self.cur == I_BACK and not mouse))
        if self.cur == I_BACK and not mouse: P._cursor(a - 24 * ui_scale, b + h / 2, 28 * ui_scale)
        zones.append((a, b, a + w, b + h, I_BACK)); self.zones = zones
