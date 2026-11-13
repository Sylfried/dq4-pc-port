"""Messages, game menu windows and interface editor; fades, vignette and small save messages (toasts)."""
import os, random, time
import numpy as np
import pyglet
from pyglet import gl
from pyglet.graphics.shader import Shader
from pyglet.graphics.shader import ShaderProgram
from dq4_pc.battle import battle_effect as EC
from dq4_pc.language import tr, N_
from dq4_pc.window import inputs as EN
from dq4_pc.menus import ui_menu as UI
from dq4_pc.core import engine as ENGINE
from dq4_pc.persistence import settings as RG
from dq4_pc.window.constants import (BTN_LANGUAGE, BTN_SAVES, CB_MSG_BOTTOM, CB_ZONE_MENUS, CENTERED_WINDOWS, MSG_BOTTOM, YESNO_BOX_SPACING, FONTS, SFX_BUTTON,
    UI_ZOOM)
from dq4_pc.window.shaders import FRAG_GRADIENT, FRAG_SIDES, VERTEX_GRADIENT, VERTEX_SIDES
from dq4_pc.window.helpers import background_gradient
from dq4_pc.window import battle_replay as RP

CHARACTER_LIST = 4                 # Make_LeftCharaList: the party on the left of the field menu (Magic, Attributes, Misc > Equipment...)


class MenusMixin:
    """Messages, game menu windows and interface editor; fades, vignette and small save messages (toasts)."""

    def toast(self, text, duration=1.8):
        """Small message at the top of the screen, ONLY for saves (savestates, game save impossible, import): the other notifications (battle speed, full screen, engine memory, settings, sound...) no longer exist;
        the notifications for saves were brought back. tests/test_save_notifications.py keeps the list of allowed calls."""
        self.toasts = [(tr(text), time.time() + duration)]            # (the text is translated here; a text with placeholders must be translated before being formatted: toast(tr('Etat %d') % n))

    def ui_g_reset(self):
        """Rebuilds the original menu windows from the interface memory (after loading a savestate)."""
        if self.ui_g is None: return
        self.ui_g.f.clear(); self.engine.ui.obs = self.ui_g; self.ui_g.replay(self.engine.ui)

    SAMPLE_HEIGHT = 87                                                  # height (canvas pixels) of a message sample: 3 lines of 28 pixels + 3 of margin (see ui_menu.limit_lines)

    SAMPLE_TEXTS = ((N_('menus.message_preview_sentence'),),                                                      # sample texts of the interface editor (1 to 3 lines, like a dialogue box): one at random at each choice of "Dialogue"; each line is translated when drawn
              (N_('menus.test_text'), N_('menus.used_adjust_size'), N_('menus.position_dialogue_boxes')),
              (N_('menus.message_preview'), N_('menus.two_lines')),
              (N_('menus.here_example_dialogue'), N_('menus.move_resize'), N_('menus.window_as_like')),
              (N_('menus.test_text_game_messages'), N_('menus.will_displayed_here_size')))

    def new_sample(self):
        """The editor chooses the sample text shown in the dialogue window: at random among SAMPLE_TEXTS (other than the previous one)."""
        n = len(self.SAMPLE_TEXTS); p = getattr(self, '_trial', None)
        self._trial = random.choice([k for k in range(n) if k != p]); self._sample_seen = None

    def _preview_canvas(self):
        """512 x 512 canvas of the dialogue preview: the chosen sample text, in the game font, laid out from the 1st row."""
        if getattr(self, '_trial', None) is None: self.new_sample()
        cv = np.zeros((512, 512), np.uint8)
        from PIL import Image, ImageDraw, ImageFont
        im = Image.new('L', (512, self.SAMPLE_HEIGHT), 0); dr = ImageDraw.Draw(im)
        try: f = ImageFont.truetype(os.path.join(self.args.cache, 'ui_font.otf'), 22)
        except Exception: f = ImageFont.load_default()
        for j, t in enumerate(self.SAMPLE_TEXTS[self._trial % len(self.SAMPLE_TEXTS)]): dr.text((4, 7 + 28 * j + 20), tr(t), font=f, fill=255, anchor='ls')
        cv[:self.SAMPLE_HEIGHT] = np.asarray(im)
        return cv

    def _update_message(self):
        """Visible text of the message (engine canvas) -> white RGBA image whose opacity is that of the text."""
        if self.ui_msg:                                          # original window: the whole canvas (512 x 512, looping) + scrolling by UV offset
            a = self.engine.read_canvas()
            if a is not None:
                lookup_key = hash(a.tobytes())
                if lookup_key != self.canvas_key:
                    self.canvas_key = lookup_key; self.ui_render.update_canvas(a)
                    if os.environ.get('DQ_UIDBG'):                                  # (test) text lines of the canvas: (first row, last row)
                        r = np.where(a.max(1) > 40)[0]; g = []
                        if len(r):
                            s0 = p0 = r[0]
                            for q in r[1:]:
                                if q > p0 + 3: g.append((int(s0), int(p0))); s0 = q
                                p0 = q
                            g.append((int(s0), int(p0)))
                        print('CANVAS frame %s lines %s msg %s engine (lines, height, scroll) %s' % (self.engine.frames, g, self.engine.ui.msg, self.engine.params_message()), flush=True)
            m = self.engine.ui.msg; typ = m['type']
            if typ == 1 and a is not None and a[(np.arange(102, 164) + (int(m['y']) & 0x1ff)) % 512].max() > 40: typ = 4       # 4-line battle message (4 monster groups): original frame
            self.ui_msg.select_language(typ, m['y'], m['feed'] and not getattr(self.engine, 'hold_messages', False), m.get('speaker', ''))          # (no ▼ while a jingle holds the message)
            return
        a = self.engine.read_message()
        if a is None: self.msg_img = None; return
        h = a.shape[0]
        lookup_key = hash(a.tobytes())
        if lookup_key == self.msg_key: return
        self.msg_key = lookup_key; self.msg_h = h
        rgba = np.empty((h, a.shape[1], 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = a
        self.msg_img = pyglet.image.ImageData(a.shape[1], h, 'RGBA', np.ascontiguousarray(rgba[::-1]).tobytes(), pitch=a.shape[1] * 4)
        t = self.msg_img.get_texture()
        gl.glBindTexture(t.target, t.id)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)

    def _clone_screen(self, battle=True):
        """Copies the frame that has just been drawn into a texture (the capture that the battle start effect shatters into pieces, or that the travel, lamp and Riremito effects deform: `battle` false, see capture_effects.py)."""
        w, h = self.get_framebuffer_size()
        if self.effect_tex is not None: self.effect_tex.delete()
        t = pyglet.image.Texture.create(w, h, internalformat=gl.GL_RGBA8)
        gl.glBindTexture(t.target, t.id)
        gl.glCopyTexSubImage2D(t.target, 0, 0, 0, 0, 0, w, h)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glGenerateMipmap(t.target)
        gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        self.effect_tex = t
        if not battle: return
        self.sim_effect = EC.TilesEffect(self.width / max(1, self.height))
        n = self.sim_effect.rows * EC.COLS * 6
        if self.effect_vl is not None: self.effect_vl.delete()
        self.effect_vl = self.program_effect.vertex_list(n, gl.GL_TRIANGLES, position=('f', self.sim_effect.positions().ravel().tolist()), tex_coords=('f', self.sim_effect.UV.ravel().tolist()), colors=('f', self.sim_effect.colors().ravel().tolist()))

    def _paint_background_gradient(self, topmost, bottom):
        """Town background: vertical gradient from the `topmost` color (top of the frame) to the `bottom` color, as drawn by the game's `BackColor` (see VERTEX_GRADIENT), over the clear (the average of the two) and
        before the scene; depth is neither read nor written. Nothing to do if the two colors are equal (the clear is already that color)."""
        if self.program_gradient is None:
            self.program_gradient = ShaderProgram(Shader(VERTEX_GRADIENT, 'vertex'), Shader(FRAG_GRADIENT, 'fragment'))
            self.gradient_vl = self.program_gradient.vertex_list(6, gl.GL_TRIANGLES, position=('f', [1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0, -1.0]))
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glDisable(gl.GL_BLEND)
        self.program_gradient.use(); self.program_gradient['top'] = tuple(float(c) for c in topmost); self.program_gradient['bottom'] = tuple(float(c) for c in bottom)
        self.gradient_vl.draw(gl.GL_TRIANGLES)
        self.program_gradient.stop()
        gl.glEnable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def _draw_vignette(self):
        """Darkens the edges of the game picture (Vignettage setting), under the fade and the interface: elliptical radial gradient (center untouched up to 45 % of the radius, edges in black
        with opacity = the setting). 512 x 288 texture stretched over the window (linear filter), created once."""
        v = float(self.reg['vignette'])
        if v <= 0.005: return
        t = getattr(self, '_vignette_tex', None)
        if t is None:
            n, m = 512, 288; yy, xx = np.mgrid[0:m, 0:n]; r = np.hypot((xx + 0.5) / n * 2 - 1, (yy + 0.5) / m * 2 - 1)
            k = np.clip((r - 0.45) / (1.3 - 0.45), 0.0, 1.0); k = k * k * (3 - 2 * k)
            a = np.zeros((m, n, 4), np.uint8); a[..., 3] = np.round(255 * k).astype(np.uint8)
            t = self._vignette_tex = self._tex(a, False)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        sp = pyglet.sprite.Sprite(t, x=0, y=0); sp.scale_x = self.width / t.width; sp.scale_y = self.height / t.height; sp.opacity = int(round(255 * min(1.0, v))); sp.draw()

    WIDE_BASE = 16.0 / 9.0          # base shape of the picture: wider windows show more on the sides, which fade into the background

    def _draw_wide_sides(self, e):
        """Window wider than 16:9: the parts of a town or dungeon picture outside the 16:9 base fade into the map's background (the `BackColor` gradient of packet 8, otherwise the clear color),
        smoothly, up to the background alone at the edges of the window. Several maps are a finite plane (water, lava, floor) laid on a black background: from 21:9 its edge showed as a hard line on the
        sides. Under the vignette, the fades and the interface. Nothing at 16:9 or narrower."""
        w, h = float(self.width), float(max(1, self.height))
        inner = self.WIDE_BASE * h / w
        if inner >= 0.999: return
        if getattr(self, 'program_sides', None) is None:
            self.program_sides = ShaderProgram(Shader(VERTEX_SIDES, 'vertex'), Shader(FRAG_SIDES, 'fragment'))
            self.sides_vl = self.program_sides.vertex_list(6, gl.GL_TRIANGLES, position=('f', [1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0, -1.0]))
        if background_gradient(e.top_background, e.bottom_background): topmost, bottom = e.top_background, e.bottom_background
        else: topmost = bottom = self._clear_color(e)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        self.program_sides.use(); self.program_sides['top'] = tuple(float(c) for c in topmost); self.program_sides['bottom'] = tuple(float(c) for c in bottom); self.program_sides['inner'] = float(inner)
        self.sides_vl.draw(gl.GL_TRIANGLES)
        self.program_sides.stop()

    def _background_fade_in_front(self):
        """Is the "FadeForBG" plane drawn in front of the windows? `MenuMessage.SetCanvasMesh(no)` (0xCFA4B4) ends with `Fade.SetFadePriority(1, no == 0)` (0xCD036C), which gives that plane the
        shader `l_shader[priority]`: 1 = Custom/BackFade (behind the windows) for the field message window, 0 = Custom/FrontFade (Overlay queue, in front of everything) for the battle ones (types
        1 to 3). The call is made when the type changes, so the plane follows the last type received ([0, n] on port 1); until the first one, BackFade."""
        t = (getattr(self.engine, 'ui', None) and self.engine.ui.msg.get('type')) or 0
        return (t & 0xffff) != 0

    def _draw_fade(self, background=False):
        """Screen fade planes (Fade.FadePlane, bit 14 of packet 9 = Fade.l_targetLayer): `background` = "FadeForBG" plane (Custom/BackFade, Background queue: in front of the scene, behind the windows and messages);
        otherwise the "FadeForMenu" plane (Custom/FrontFade, Overlay queue: in front of everything, windows and messages included). When the background plane has the FrontFade shader
        (`_background_fade_in_front`), it is drawn with the front plane, just before it, over the windows (the order between the two Overlay planes is assumed)."""
        e = self.engine.state
        if self._background_fade_in_front():
            if background: return
            self._paint_fade(e.background_fade)
        self._paint_fade(e.background_fade if background else e.fade)

    def _paint_fade(self, fd):
        if fd['a'] <= 0.004: return
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        r = pyglet.shapes.Rectangle(0, 0, self.width, self.height, color=tuple(int(round(255 * min(max(c, 0.0), 1.0))) for c in fd['col']))
        r.opacity = int(round(255 * min(fd['a'], 1.0)))
        r.draw()

    def _draw_message(self):
        if self.ui_msg: return                                   # drawn with the original windows (_draw_menus)
        if self.msg_img is None or not self.engine.msg_visible: return
        ui_scale = self.height / 720.0 * 1.3                       # text size: 1 canvas pixel = 1.3 pixels at 720p
        tl, tn = ENGINE.CANVAS_L * ui_scale * 0.78, self.msg_h * ui_scale
        margin = 18 * ui_scale
        bw, bh = tl + 2 * margin, tn + 2 * margin
        bx, by = (self.width - bw) / 2, 22 * ui_scale
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        border = pyglet.shapes.BorderedRectangle(bx, by, bw, bh, border=max(2, int(3 * ui_scale)), color=(8, 12, 70), border_color=(245, 245, 245))
        border.opacity = 235
        border.draw()
        spr = pyglet.sprite.Sprite(self.msg_img, x=bx + margin, y=by + bh - margin - self.msg_h * ui_scale)
        spr.scale = ui_scale
        spr.draw()

    # ---- menus
    def _menu_lines(self, f):
        """Cells of a window -> lines (engine line number, text, label, value, is_title)."""
        rows = {}
        for (r, c), t in f['cells'].items(): rows.setdefault(r, {})[c] = t
        out = []
        for r in sorted(rows):
            cols = rows[r]
            pre, lab, val = cols.get(5, ''), cols.get(2, ''), cols.get(3, '')
            main_part = ' '.join(' '.join(t.split('\n')) for c, t in sorted(cols.items()) if c not in (2, 3, 5) and t)     # line breaks -> spaces (action summary: "Attaquer ▼ cible")
            if not (main_part or val or lab): continue
            out.append((r, (pre + ' ' + main_part).strip(), lab, val, main_part.rstrip().endswith('?')))
        return [l for l in out if l[4]] + [l for l in out if not l[4]]

    def _keyboard_port(self, port):
        """Port that receives the keyboard: that of the engine's active menu, unless it is a single-button window (Divers menu: input goes to "Quick save", opened last) while a fuller visible window exists
        (the page's list): that is the one that is traversed (the touch acts on all windows)."""
        if port is None or not self.ui_g: return port
        eng = self.engine
        sf = getattr(self, 'section_focus', None)   # a camera key has just touched another character: the game gives the input to the character list, the keyboard stays in
        if sf is not None:                          # the character's window (the equipment slots...), which still takes it, until it closes
            if port in sf and sf[1] in eng.input_menus(): return sf[1]
            self.section_focus = None
        def n(q):
            wnd = self.ui_g.f.get(q); return sum(1 for b in wnd.buttons() if b[1] & 0x10) if wnd else 0
        if n(port) > 1: return port
        cand = [q for q, f in eng.ui.f.items() if q > 1 and f['visible'] and f['cells'] and q in self.ui_g.f and n(q) > 1]
        return max(cand, key=lambda q: eng.ui.f[q]['order']) if cand else port

    def _port_for_gamepad(self, port, pad):
        """Port that receives the gamepad key `pad` (up 2, down 1, right 4, left 8, A 16, B 32): that of the active menu if it has a button for it, otherwise the most recent visible window that has one.
        Divers menu: the engine gives the input to the "Quick save" window, but the back button is in the list and the page arrows in a third window."""
        eng = self.engine
        def a(q):
            wnd = self.ui_g.f.get(q) if self.ui_g else None
            return bool(wnd) and any(b[1] & pad for b in wnd.buttons())
        if a(port): return port
        for q in sorted((q for q, f in eng.ui.f.items() if q > 1 and f['visible'] and q in self.ui_g.f), key=lambda q: -eng.ui.f[q]['order']):
            if a(q): return q
        return port

    def _section_target(self, port, d):
        """Camera keys in a game menu (the movement keys go from option to option, the camera keys change the section, looping): what to press for the previous (`d` -1)
        or next (+1) interface. (1) The character: while a character's sub-window waits (spells, equipment, status pages...), the character list on the left (type 4) still takes the
        touch of the other characters (theirs are the buttons in state 0, the chosen one is in state 2; after such a touch the game gives the input back to the list), so the next visible one is touched, the last one leading to the first; grayed
        ones are skipped. (2) Otherwise the page: the window's ◀ ▶ arrows or those of another window (Pageing type 6, battle lists, ...); the game loops them itself (established on the
        status pages: ◀ on 1/4 shows 4/4). -> (port, button, gamepad) to send, or None (no interface to change: the camera keys stay directions)."""
        eng = self.engine
        for q in eng.input_menus():
            w = self.ui_g.f.get(q) if self.ui_g else None
            if w is None or w.typ != CHARACTER_LIST: continue
            members = sorted((n['buttonId'], n['state']) for n in w.N.values() if n['buttonId'] is not None and n['buttonId'] >= 0 and n['pad'] & 0x10 and w.visible(n['id']))
            cur = next((i for i, (b, st) in enumerate(members) if st == UI.STATE_INVISIBLE), None)
            if cur is None: continue                     # (no character chosen yet: choosing one is an option of the list)
            for k in range(1, len(members)):
                b, st = members[(cur + d * k) % len(members)]
                if UI.is_state_active(st): return (q, b, 0x10)
            break                                        # (one character only, or the others grayed: the pages)
        pad = 4 if d > 0 else 8
        fl = self._page_arrow(self._port_for_gamepad(port, pad), pad)
        return (fl[0], fl[1], pad) if fl else None

    def _menu_input(self, port, decl, pages=0):
        """Keys -> active menu, like Unity's MenuPort.Send: [1, button number, gamepad] (game gamepad: down 1, up 2, right 4, left 8, A 16, B 32).
        Engine-cursor menu (message 2: columns x rows, e.g. Yes / No): the keys are passed to it, it moves its cursor (messages 4) and confirms;
        left/right on a single column = previous/next. Touch menu (buttons with no engine cursor): local cursor moved according to the position of the buttons, A = touch."""
        eng = self.engine; f = eng.ui.f[port]
        if decl: self.hover_node = None                                # a key: the cursor takes control again (whole row highlighted)
        dirs = ((ENGINE.UP, 2), (ENGINE.DOWN, 1), (ENGINE.LEFT, 8), (ENGINE.RIGHT, 4))
        wnd = self.ui_g.f.get(port) if self.ui_g else None
        z = {b: ((x0 + x1) / 2, (z0 + z1) / 2) for b, pad, x0, z0, x1, z1, _ in (wnd.buttons() if wnd else []) if b >= 0 and pad & 0x10}
        if not f.get('grid') and len(z) <= 1 and self._step_entry(port, f, wnd, z, decl): return          # numeric entry menu (bet, tokens, amount): arrows = columns and ▲ / ▼
        if pages and not f.get('grid') and len({round(c[0] / 20.0) for c in z.values()}) >= 2:          # L / R (previous / next page) in a multi-column list (bestiary): left / right change column there, so it is the window's page arrows ◀ ▶ that are pressed
            fl = self._page_arrow(port, 8 if pages & 1 else 4)
            if fl: eng.send_menu(fl[0], 1, fl[1], 8 if pages & 1 else 4); self.menu_to_release = fl[0]; return
        if not f.get('grid') and len(z) < 1 and decl & (ENGINE.LEFT | ENGINE.RIGHT):           # window with no engine cursor or A button (Statut pages, types 13-17): left / right (Q, D, L, R) turn the pages with the arrows of another window (type 6), like a touch
            pad = 4 if decl & ENGINE.RIGHT else 8; q = self._port_for_gamepad(port, pad)
            if q != port: eng.send_menu(q, 1, -1, pad); self.menu_to_release = q; return
        if f.get('grid') or len(z) < 1:
            for bit, pad in dirs:
                if decl & bit:
                    if bit in (ENGINE.LEFT, ENGINE.RIGHT) and not f.get('grid') and self._page_arrow(port, pad):         # window with no confirm button but with its page arrows (bestiary sheet): left / right press them
                        fl = self._page_arrow(port, pad); eng.send_menu(fl[0], 1, fl[1], pad); self.menu_to_release = fl[0]; return
                    if bit in (ENGINE.LEFT, ENGINE.RIGHT) and (f.get('grid') or (1, 1, 1))[0] < 2: pad = 2 if bit == ENGINE.LEFT else 1
                    eng.send_menu(port, 1, -1, pad); self.menu_to_release = port; return
            if decl & ENGINE.A:
                action = next((b for b, pd, *_ in (wnd.buttons() if wnd else []) if pd & 0x800), None)          # "Action" of the bestiary sheet (gamepad 0x800): the only window that has one
                if action is not None and not f.get('grid'): eng.send_menu(port, 1, action, 0x800); self.menu_to_release = port; self.sound.play_sfx(SFX_BUTTON)
                else: eng.send_menu(port, 1, -1, 0x10); self.menu_to_release = port; self.sound.play_sfx(SFX_BUTTON)
            elif decl & ENGINE.B: q = self._port_for_gamepad(port, 0x20); eng.send_menu(q, 1, -1, 0x20); self.menu_to_release = q
            return
        lookup_key = (port, f['order']); cur = self.cur_local.get(lookup_key)
        if cur not in z:
            cur = self.cur_local[lookup_key] = f['cur'] if f['cur'] in z else min(z, key=lambda b: (-round(z[b][1]), z[b][0]))       # start: the top left button
        if decl & (ENGINE.LEFT | ENGINE.RIGHT) and wnd and wnd.typ in (58, 59, 63):                       # quantity (types 58 / 59: "Acheter" list, 63: quantity to sell): the cursor's row carries its own arrows (buttons of the same number, gamepad left 8 / right 4: "Acheter" list of a shop, quantity to sell) -> left / right change the quantity of the chosen row (like touching an arrow); the cursor keeps the whole row
            pad = 4 if decl & ENGINE.RIGHT else 8
            if any(b == cur and pd & pad for b, pd, *_ in wnd.buttons()): eng.send_menu(port, 1, cur, pad); self.menu_to_release = port; return
        if len({round((x0 + x1) / 20.0) for b, pad, x0, z0, x1, z1, _ in (wnd.buttons() if wnd else []) if b >= 0 and pad & 0x10}) <= 1 and decl & (ENGINE.LEFT | ENGINE.RIGHT):       # a single column: left / right turn the pages if another window carries the arrows
            pad = 4 if decl & ENGINE.RIGHT else 8; q = self._port_for_gamepad(port, pad)
            if q != port: eng.send_menu(q, 1, -1, pad); self.menu_to_release = q; return
        for bit, _ in dirs:
            if decl & bit: cur = self.cur_local[lookup_key] = self._neighbor(z, cur, bit)
        if decl and os.environ.get('DQ_MENUDBG'): print('MENU local cursor frame %d port %d decl %d -> %s ; buttons %s' % (self.n, port, decl, cur, {b: (round(c[0]), round(c[1])) for b, c in z.items()}), flush=True)
        if decl & ENGINE.A and cur == BTN_SAVES and self._is_start_menu(port): self.sound.play_sfx(SFX_BUTTON); self._open_saves()
        elif decl & ENGINE.A and cur == BTN_LANGUAGE and self._is_start_menu(port): self.sound.play_sfx(SFX_BUTTON); self.open_language_screen()          # language plate: never sent to the engine
        elif decl & ENGINE.A: eng.send_menu(port, 1, cur, 0x10); self.menu_to_release = port; self.sound.play_sfx(SFX_BUTTON)
        elif decl & ENGINE.B: q = self._port_for_gamepad(port, 0x20); eng.send_menu(q, 1, -1, 0x20); self.menu_to_release = q

    def _page_arrow(self, port, pad):
        """Page arrow ◀ (gamepad 8) or ▶ (gamepad 4) of the `port` window: (port, button number), or None. The shop quantity arrows (types 58, 59, 63: one per row) are not page arrows."""
        wnd = self.ui_g.f.get(port) if self.ui_g else None
        if wnd is None or wnd.typ in (58, 59, 63): return None
        for b, pd, *_ in wnd.buttons():
            if pd & pad: return (port, b)
        return None

    def _step_columns(self, wnd):
        """▲ / ▼ columns of a numeric entry menu (slot machine and poker bet, tokens, bank amount, arena bet: Make_Casino_*, Make_Bank*): button numbers >= 0 that have
        both a gamepad 0x2 element (▲, value + 1 place) and a gamepad 0x1 one (▼), from left to right. Empty for the other windows (the ▲ / ▼ of number -1 are page arrows)."""
        if wnd is None: return []
        bs = wnd.buttons(); topmost = {b for b, pad, *_ in bs if b >= 0 and pad & 0x2}; bottom = {b for b, pad, *_ in bs if b >= 0 and pad & 0x1}
        cx = {b: (x0 + x1) / 2 for b, pad, x0, z0, x1, z1, _ in bs if b in topmost & bottom and pad & 0x3}
        return sorted(cx, key=lambda b: cx[b])

    def _active_step(self, port):
        """▲ / ▼ column chosen with the keyboard in a numeric entry menu (the rightmost at the start: the units), or None if the window has none (or has several confirm buttons: ordinary cursor)."""
        wnd = self.ui_g.f.get(port) if self.ui_g else None; f = self.engine.ui.f.get(port)
        if wnd is None or f is None or f.get('grid'): return None
        cols = self._step_columns(wnd)
        if not cols or sum(1 for b in wnd.buttons() if b[0] >= 0 and b[1] & 0x10) > 1: return None
        c = self.cursor_step.get((port, f['order'])); return c if c in cols else cols[-1]

    def _step_entry(self, port, f, wnd, z, decl):
        """Numeric entry menu with the keyboard (the ▲ / ▼ buttons are gamepad keys 0x2 / 0x1, outside the local cursor): left / right choose the column (tens, units...), up / down = ▲ / ▼ of the column
        (sent to the engine like a button touch), A = the confirm button (Lancer, Donner, Valider), B = back. False if the window is not of this kind or if no useful key is pressed."""
        if not decl & (ENGINE.UP | ENGINE.DOWN | ENGINE.LEFT | ENGINE.RIGHT | ENGINE.A | ENGINE.B): return False
        cols = self._step_columns(wnd)
        if not cols: return False
        eng = self.engine; lookup_key = (port, f['order']); action = self._active_step(port)
        if action is None: return False
        self.hover_node = None                                                       # a key: the cursor takes control again
        if decl & (ENGINE.LEFT | ENGINE.RIGHT):
            i = cols.index(action) + (1 if decl & ENGINE.RIGHT else -1); self.cursor_step[lookup_key] = cols[min(max(i, 0), len(cols) - 1)]
        elif decl & (ENGINE.UP | ENGINE.DOWN): eng.send_menu(port, 1, action, 2 if decl & ENGINE.UP else 1); self.menu_to_release = port
        elif decl & ENGINE.A: eng.send_menu(port, 1, next(iter(z), -1), 0x10); self.menu_to_release = port; self.sound.play_sfx(SFX_BUTTON)
        else: q = self._port_for_gamepad(port, 0x20); eng.send_menu(q, 1, -1, 0x20); self.menu_to_release = q
        return True

    @staticmethod
    def _neighbor(z, cur, bit):
        """Neighboring button in the pressed direction (z: number -> center in interface units, Z pointing up); at the edge it wraps around to the other end of the row/column."""
        x, y = z[cur]
        if bit in (ENGINE.LEFT, ENGINE.RIGHT):
            direction = 1.0 if bit == ENGINE.RIGHT else -1.0
            before = [(b, (c[0] - x) * direction + 3.0 * abs(c[1] - y)) for b, c in z.items() if (c[0] - x) * direction > 4.0]
            if before: return min(before, key=lambda t: t[1])[0]
            candidates = [(b, abs(c[1] - y) * 100.0 - (c[0] - x) * direction) for b, c in z.items() if b != cur and abs(c[1] - y) < 12.0]
        else:
            direction = 1.0 if bit == ENGINE.UP else -1.0
            before = [(b, (c[1] - y) * direction + 3.0 * abs(c[0] - x)) for b, c in z.items() if (c[1] - y) * direction > 4.0]
            if before: return min(before, key=lambda t: t[1])[0]
            candidates = [(b, abs(c[0] - x) * 100.0 - (c[1] - y) * direction) for b, c in z.items() if b != cur and abs(c[0] - x) < 12.0]
        return min(candidates, key=lambda t: t[1])[0] if candidates else cur

    def _lbl(self, text, size_value, color=(255, 255, 255, 255), fonts=()):
        """Text label (cached); `fonts`: families tried before the system fonts (the game font for the Esc menu)."""
        k = (text, round(size_value, 1), color, fonts)
        l = self.lbl_menu.get(k)
        if l is None:
            if len(self.lbl_menu) > 400: self.lbl_menu.clear()
            l = self.lbl_menu[k] = pyglet.text.Label(text, font_name=tuple(fonts) + FONTS, font_size=size_value, color=color, anchor_x='left', anchor_y='baseline')
        return l

    def _helptext_margin(self):
        """(side, width) of the F1 info block: at the top RIGHT of the screen by default; width = the free margin next to the interface column (centered 450 x 800 portrait), so as not to hide the game windows (see inputs.info_zone)."""
        return EN.info_zone(self.width, self.height, bool(self.ui_render), UI_ZOOM, self.args.ui_pos)

    def _cursor(self, port):
        """Highlighted button of the active menu: the engine's cursor (messages 4) or, without an engine cursor, the local arrow-key cursor."""
        f = self.engine.ui.f[port]
        if f.get('grid'): return f['cur']
        step = self._active_step(port)
        if step is not None: return step                                  # numeric entry menu: the chosen ▲ / ▼ column
        return self.cur_local.get((port, f['order']), f['cur'])

    def _ui_reference(self):
        """Game interface column (centered 450 x 800 portrait, window height): (center x, center y, pixels per unit)."""
        ui_scale = self.height / 800.0 * self.ui_k
        return {'center': self.width / 2, 'right': self.width - 225 * ui_scale, 'left': 225 * ui_scale}.get(self.args.ui_pos, self.width / 2), self.height / 2.0, ui_scale

    def window_names(self):
        """Names (Make_* from MenuPortItemTable, without the prefix) of the game windows that have a layout: {name: [type numbers]} (interface editor)."""
        if getattr(self, '_make_names', None) is None:
            self._make_names = {}
            if self.ui_g is not None:
                for num, t in self.ui_g.ml.types.items():
                    if t.get('err') not in (None, 'None') or not t.get('nodes'): continue
                    self._make_names.setdefault(t.get('name', '').replace('Make_', '').replace('()', '') or 'type%s' % num, []).append(int(num))
        return self._make_names

    def _type_name(self, typ):
        m = getattr(self, '_type_names', None)
        if m is None: m = self._type_names = {n: name_str for name_str, nums in self.window_names().items() for n in nums}          # type number -> Make_* name (once per game: called for each window at every frame)
        return m.get(typ)

    def _menu_hidden(self, typ):
        """Game window hidden by the player (interface editor: "Show this interface on screen" = Non)?"""
        ms = self.reg['interface_hidden']
        return bool(ms) and self._type_name(typ) in ms

    def _yesno_on_message(self, msg, wnd):
        """Yes / No stack placed on the top right corner of the dialogue box: -> (vertical offset in units that places the VISIBLE bottom edge of the stack YESNO_BOX_SPACING above the visible top edge of the box,
        (visible right edge of the box, visible right edge of the stack)). The frames have different transparent margins (6 units on the right for the box): we align what is seen, not the mesh cells. None if a measurement is missing."""
        mv = msg.visible_extent() if msg is not None else None; ev = wnd.visible_extent()
        if not mv or not ev: return None
        return float(mv[3] + YESNO_BOX_SPACING - ev[2]), (float(mv[1]), float(ev[1]))

    def _ui_yesno(self, base, D, e0, v, edges=None):
        """Yes / No (type 1) adjusted by the player: it follows the message window as usual (base = (cx, cy, s) of the latter, D = vertical offset in units that attaches it to it, e0 = its bottom edge in units),
        then its size v[0] is changed around its bottom edge and its right edge, and it is shifted by v[1], v[2] (fractions of the screen).
        edges = (right edge of the message window, right edge of the Yes / No) in units: the Yes / No stack has its right edge on that of the dialogue box. -> (cx, cy, s) for drawing."""
        bx, by, bs = base; s2 = bs * float(v[0]); y_bottom = by + (D + e0) * bs + float(v[2]) * self.height
        x = bx + float(v[1]) * self.width + ((edges[0] * bs - edges[1] * s2) if edges else 0.0)
        return x, y_bottom - e0 * s2, s2

    def _ui_custom(self, mode, s, v):
        """Reference frame (cx, cy, s) of a window modified by the player (interface editor): size v[0] around the edge of its group (bottom, top or middle of the screen), then shift v[1], v[2] as a fraction of the screen."""
        s2 = s * float(v[0]); H = float(self.height)
        cy = 400.0 * s2 if mode == 'bottom' else (H - 400.0 * s2 if mode == 'top' else H / 2.0)
        return self._ui_reference()[0] + float(v[1]) * self.width, cy + float(v[2]) * H, s2

    def _update_preview_canvas(self, wnd):
        if getattr(self, '_trial', None) is None: self.new_sample()
        if getattr(self, '_sample_seen', None) != self._trial:
            self._sample_seen = self._trial; self.ui_render.update_canvas(self._preview_canvas(), 'msg_apercu')
            wnd.select_language(0, 0, False)

    def _preview_window(self, lookup_key):
        """Interface editor preview window (kept): 'msg' = dialogues (sample text), otherwise the Make_* name; None if it has no layout."""
        if not hasattr(self, '_previews'): self._previews = {}
        wnd = self._previews.get(lookup_key)
        if wnd is None:
            if lookup_key == 'msg':
                wnd = UI.MessageWindow(self.ui_g.ml); wnd.select_language(0, 0, False); wnd.N['canvas']['mats'][0]['sheet'] = 'msg_apercu'          # (sample text: separate canvas, not the engine's)
            else:
                nums = self.window_names().get(lookup_key)
                if not nums: return None
                wnd = UI.Window(self.ui_g.ml, nums[0])
                if wnd.extent() is None:                                                    # parts hidden as long as the engine does not ask for them (party banner in battle, stadium tokens...): the preview shows them all
                    for node in wnd.N.values(): node['act'] = True
            self._previews[lookup_key] = wnd
        return wnd

    def preview_interface(self, lookup_key):
        """Interface editor: preview of window `lookup_key` ('msg' = dialogues, otherwise the Make_* name) at its size and position (original layout, without game state) -> (x0, y0, x1, y1) in pixels, or None."""
        if self.ui_render is None or self.ui_g is None: return None
        wnd = self._preview_window(lookup_key)
        if wnd is None: return None
        if lookup_key == 'msg': self._update_preview_canvas(wnd)
        e = wnd.extent()
        if not e: return None
        if lookup_key == 'YesNo': return self._yesno_preview(wnd, e)
        dz = (MSG_BOTTOM - wnd.bottom()) if lookup_key == 'msg' else 0.0
        k, gr, modes = self._ui_scale([(e[0] + dz, e[1] + dz)]); s = self.height / 800.0 * k
        mode = modes[0] if modes else 'bottom'
        v = self.reg['interface_windows'].get(lookup_key) or RG.default_window(lookup_key)
        cx, cy, s2 = self._ui_custom(mode, s, v)
        wnd.selected = None; wnd.selected_node = None; wnd.press_node = None
        self.ui_render.draw_all([wnd], cx, cy + dz * s2, s2, (self.width, self.height))
        x0, x1 = cx - 225 * s2, cx + 225 * s2; y0, y1 = cy + (e[0] + dz) * s2, cy + (e[1] + dz) * s2          # yellow frame: footprint of the window
        pyglet.shapes.Box(x0, y0, x1 - x0, y1 - y0, thickness=2, color=(255, 235, 130)).draw()
        return x0, y0, x1, y1

    def _yesno_preview(self, wnd, e):
        """Yes / No preview: as in the game, the stack (Yes above No) is placed on the top right corner of the message window (shown in place, with its settings), right edges aligned; its yellow frame is that of the element being adjusted."""
        fm = self._preview_window('msg'); self._update_preview_canvas(fm); em = fm.extent()
        if not em: return None
        pose = self._yesno_on_message(fm, wnd); dzm = MSG_BOTTOM - fm.bottom(); D = dzm + (pose[0] if pose else em[1] + YESNO_BOX_SPACING - e[0])
        k, gr, modes = self._ui_scale([(em[0] + dzm, em[1] + dzm), (e[0] + D, e[1] + D)]); s = self.height / 800.0 * k
        mode = modes[0] if modes else 'bottom'; ov = self.reg['interface_windows']
        cxm, cym, sm = self._ui_custom(mode, s, ov.get('msg') or RG.DEFAULT_WINDOW)
        fm.selected = None; fm.selected_node = None; wnd.selected = None; wnd.selected_node = None
        self.ui_render.draw_all([fm], cxm, cym + dzm * sm, sm, (self.width, self.height))
        cx, cy, s2 = self._ui_yesno((cxm, cym, sm), D, e[0], ov.get('YesNo') or RG.DEFAULT_WINDOW, pose[1] if pose else None)
        self.ui_render.draw_all([wnd], cx, cy, s2, (self.width, self.height))
        ex = wnd.extent_x(); x0, x1 = (cx + ex[0] * s2, cx + ex[1] * s2) if ex else (cx - 225 * s2, cx + 225 * s2); y0, y1 = cy + e[0] * s2, cy + e[1] * s2          # (yellow frame: the Yes / No stack)
        pyglet.shapes.Box(x0, y0, x1 - x0, y1 - y0, thickness=2, color=(255, 235, 130)).draw()
        return x0, y0, x1, y1

    def _ui_scale(self, intervals):
        """Window enlargement: intervals [(bottom, top)] in interface units -> (k, mode of each group).
        Close windows (less than 60 units apart) form a group; a bottom (resp. top, resp. middle) group is enlarged around the bottom
        (top, center) edge of the screen, to stay attached to that edge. k = UI_ZOOM, reduced (down to 1) while a group goes off the screen or overlaps another."""
        H = float(self.height); ui_scale = H / 800.0
        gr = []
        for lo, hi in sorted(intervals):
            if gr and lo - gr[-1][1] < 60.0: gr[-1][1] = max(gr[-1][1], hi)
            else: gr.append([lo, hi])
        modes = ['bottom' if (lo + hi) / 2 < -100 else 'top' if (lo + hi) / 2 > 100 else 'center' for lo, hi in gr]
        def y(z, mode, s): return (z + 400.0) * s if mode == 'bottom' else H - (400.0 - z) * s if mode == 'top' else H / 2 + z * s
        kmax = min(UI_ZOOM, self.width / (450.0 * ui_scale))
        k = kmax
        while k > 1.0:
            s = ui_scale * k; iv = [(y(lo, m, s), y(hi, m, s)) for (lo, hi), m in zip(gr, modes)]
            if all(a >= -0.5 and b <= H + 0.5 for a, b in iv) and all(iv[i + 1][0] - iv[i][1] >= 8.0 for i in range(len(iv) - 1) if iv[i + 1][0] >= iv[i][0]): break
            k -= 0.01
        return max(k, 1.0), gr, modes

    def _dz_message(self, ports):
        """Field message window: the original places it above the bottom menu area (portrait); in 16/9 it is lowered to the bottom of the screen,
        unless another window occupies the bottom (it would stay underneath)."""
        m = self.ui_msg
        battle = self.engine.state.part == ENGINE.PART_BATTLE          # battle: the message is placed at the same spot as the command menu (same bottom edge, same scale)
        if self.args.original_message or not m or (m.type != 0 and not battle): return 0.0
        b = m.bottom()
        if any(self.ui_g.f[p].typ != 1 and self.ui_g.f[p].bottom() < b - 2 for p in ports): return 0.0
        return (CB_MSG_BOTTOM if battle else MSG_BOTTOM) - b

    def _zones(self, port):
        """Touch zones of a port's window: [(number, gamepad, x0, y0, x1, y1, depth, element identifier)] in pixels."""
        wnd = self.ui_g.f.get(port) if self.ui_g else None
        if not wnd or self._menu_hidden(wnd.typ): return []
        cx, cy, ui_scale = self.ui_tf.get(port) or self._ui_reference(); dz = getattr(self, 'ui_dzp', {}).get(port, 0.0)
        return [(b, pad, cx + x0 * ui_scale, cy + (z0 + dz) * ui_scale, cx + x1 * ui_scale, cy + (z1 + dz) * ui_scale, pr, nid) for b, pad, x0, z0, x1, z1, pr, nid in wnd.buttons(True)]

    def _draw_menus(self):
        if self.pause.opened and self.pause.screen_page == 'interface': return       # interface editor: only the chosen element is shown (through the Esc menu), not the game's windows
        eng = self.engine
        active = self._keyboard_port(eng.active_menu())
        if os.environ.get('DQ_UIDBG'):                      # (test) state of the windows at each change: port, type, visible, original window or simple menu
            state = tuple(sorted((p, f['type'], f['visible'], p in (self.ui_g.f if self.ui_g else ()), len(f['cells'])) for p, f in eng.ui.f.items() if f['visible'] or f['type'] is not None))
            if state != getattr(self, '_ui_state', None):
                self._ui_state = state; print('UI frame %d active=%s : %s' % (self.n, active, ' '.join('%d:t%s%s%s c%d' % (p, t, '' if v else '(cache)', '[O]' if o else '[simple]', c) for p, t, v, o, c in state)), flush=True)
        if self.ui_render:
            entries = sorted((f['order'], p) for p, f in eng.ui.f.items() if f['visible'] and p in self.ui_g.f and f['type'] not in eng.ignored_types)          # (arena "Quit": replaced by the back button, see arena_abort.py)
            if eng.state.part == ENGINE.PART_BATTLE and max(float(eng.state.fade['a']), float(eng.state.background_fade['a'])) >= 0.6: entries = []       # end of battle: the game closes the fade to black while the status window is still "visible" (the message stays: "Ragnar meurt !" can be read on the black): otherwise the black screen shows a lone box at the top left
            if self.port_screen is not None: entries = []                                 # Sauvegardes screen open: the start menu is hidden (otherwise it can be guessed at through the translucent frame)
            replay = getattr(self, '_replay', None) is not None
            self.ui_render.hidden_cells = RP.HIDDEN_CELLS if replay else None          # (no action labels under the status boxes during a replay)
            self.ui_render.hide_up_cursor = replay                                         # (nor the arrow that goes from member to member while the recording answers the command menus)
            if replay:                                                                     # battle replay: the recording answers the menus; only the party's status is shown, never the command phase windows (monster names...)
                waiting = set(eng.input_menus()); entries = [(o, p) for o, p in entries if p not in waiting and self.ui_g.f[p].typ in RP.KEEP_WINDOWS]
            wins_v = [self.ui_g.f[p] for _, p in entries]; self.ui_render.neighbors = wins_v
            for wnd in wins_v:
                if wnd.typ == 53: wnd.center_menu(); wnd.auto_plate(); self._language_plate(wnd)          # start menu: group vertically centered, in a black frame (drawn further down); "Sauvegarde automatique" plate always visible, grayed out and inactive without a readable data5.dat; flag of the language plate
            should_hide = self._battle_end_box()
            msg = bool(self.ui_msg and (eng.msg_visible or (replay and self.replay_between_turns())) and 'msg' in self.ui_render.tex and not should_hide)          # (replay between two turns: the message window stays)
            dz = self._dz_message([p for _, p in entries]) if msg else 0.0
            self.ui_dz = dz; self.ui_followers = {p for _, p in entries if self.ui_g.f[p].typ == 1} if msg else set()      # the Yes/No (type 1) follows the message window (always, in its original place or lowered)
            self.ui_dzp = {}; ui_edges = {}                   # vertical offset of each window that follows the message: the same as the message's, plus what it takes to place the Yes/No stack on the top edge of the message; right edges to be aligned
            for p in self.ui_followers:
                pose = self._yesno_on_message(self.ui_msg, self.ui_g.f[p]) if msg else None
                self.ui_dzp[p] = dz + (pose[0] if pose else 0.0); ui_edges[p] = pose[1] if pose else None
            ivs = {}
            for _, p in entries:
                e = self.ui_g.f[p].extent()
                if e: ivs[p] = (e[0] + self.ui_dzp.get(p, 0.0), e[1] + self.ui_dzp.get(p, 0.0))
            if msg:
                e = self.ui_msg.extent()
                if e: ivs['msg'] = (e[0] + dz, e[1] + dz)
            k, gr, modes = self._ui_scale(list(ivs.values()) + ([CB_ZONE_MENUS] if self.engine.state.part == ENGINE.PART_BATTLE else [])); self.ui_k = k       # battle: constant scale (the command menu zone always counts), otherwise the windows change size at every message
            H = float(self.height); s = H / 800.0 * k; cx = self._ui_reference()[0]
            def mode_of(lookup_key):                                 # 'bottom', 'top' or 'center': screen edge the window is stuck to
                if lookup_key not in ivs: return 'bottom'
                lo, hi = ivs[lookup_key]; i = next((j for j, g in enumerate(gr) if g[0] - 1e-6 <= lo and hi <= g[1] + 1e-6), 0); return modes[i] if modes else 'bottom'
            def ref_frame(lookup_key):                                  # (cy, scale) of the window group that contains this window
                m = mode_of(lookup_key)
                return (400.0 * s if m == 'bottom' else H - 400.0 * s if m == 'top' else H / 2), s
            self.ui_tf = {p: (cx,) + ref_frame(p) for _, p in entries}
            ov = self.reg['interface_windows']; tf_msg = None; custom = {}; yes_no = {}           # windows modified by the player (size, position): drawn separately, with their own frame of reference (the touch zones follow it)
            mask = set(self.reg['interface_hidden'])                                  # hidden interfaces ("Show this interface on screen" = Non): computed like the others (the layout does not move), only their drawing is omitted
            if ov and msg and ov.get('msg'): tf_msg = self._ui_custom(mode_of('msg'), s, ov['msg'])
            for _, p in entries:
                fe1 = self.ui_g.f[p]
                if fe1.typ != 1: continue
                name_str = self._type_name(1) or ''; v = ov.get(name_str) if (ov and name_str not in RG.REMOVED_WINDOWS) else None
                e1 = fe1.extent()
                if not e1: continue
                if p in self.ui_followers:                                                        # Yes / No: placed on the top right corner of the dialogue box (the player's settings are relative to it)
                    D = self.ui_dzp.get(p, 0.0); base = tf_msg or (cx, ref_frame('msg')[0], s)
                    t2 = self._ui_yesno(base, D, e1[0], v or RG.DEFAULT_WINDOW, ui_edges.get(p))
                    self.ui_tf[p] = (t2[0], t2[1] - D * t2[2], t2[2]); yes_no[p] = t2
                elif v:                                                                      # no dialogue box: in its place, with the player's settings
                    t2 = self._ui_yesno((cx,) + ref_frame(p), 0.0, e1[0], v); self.ui_tf[p] = (t2[0], t2[1], t2[2]); custom[p] = t2
            if ov:
                for _, p in entries:
                    if self.ui_g.f[p].typ == 1 or p in self.ui_followers: continue
                    name_str = self._type_name(self.ui_g.f[p].typ) or ''; v = ov.get(name_str) if name_str not in RG.REMOVED_WINDOWS else None
                    if v: custom[p] = self.ui_tf[p] = self._ui_custom(mode_of(p), s, v)
            for _, p in entries:
                if self.ui_g.f[p].typ in CENTERED_WINDOWS and p not in custom:         # adventure log list, gender choice: centered on screen in a black frame (the dialogue boxes, for their part, stay in place)
                    c = self.ui_g.f[p].center_visible()
                    if c: custom[p] = self.ui_tf[p] = (cx - c[0] * s, H / 2 - c[1] * s, s)
            for _, p in entries:
                if self.ui_g.f[p].typ == 25: self._plan_window(self.ui_g.f[p], eng.ui.f[p])
                elif self.ui_g.f[p].typ == 26: self._world_plan_window(self.ui_g.f[p], eng.ui.f[p])
            topmost, bottom = ([self.ui_msg] if msg else []), {}
            for _, p in entries:
                wnd = self.ui_g.f[p]
                wnd.selection(self.press_state[1] if self.press_state and self.press_state[0] == p else (self._cursor(p) if p == active else None))
                if self.press_state and self.press_state[0] == p:           # press in progress: the element is dark while the pointer is on it; if the pointer leaves, nothing (MenuPortItem.Update, state 2: SetPush(key)), if it comes back, it darkens again
                    h = self._button_under(p, *self.mouse); over = bool(h) and h[3] == self.press_node
                    wnd.selected_node = self.press_node if over else -1; wnd.press_node = self.press_node if over else None
                else:
                    wnd.press_node = None
                    wnd.selected_node = self.hover_node[1] if self.hover_node and self.hover_node[0] == p else (-1 if self.hover_node else None)       # mouse: only the pointed element (-1: window not hovered, nothing is lit by number)
                if p in self.ui_followers: topmost.append(wnd)
                elif p not in custom: bottom.setdefault(self.ui_tf[p][1], []).append(wnd)
            for wnd in topmost:                                   # the message first, then each window that follows it (Yes/No) with its own offset
                pf = next((p for _, p in entries if self.ui_g.f[p] is wnd), None); dzf = self.ui_dzp.get(pf, dz)
                if ('msg' in mask) if pf is None else self._menu_hidden(self.ui_g.f[pf].typ): continue
                if pf in yes_no: self.ui_render.draw_all([wnd], yes_no[pf][0], yes_no[pf][1], yes_no[pf][2], (self.width, self.height))
                elif tf_msg: self.ui_render.draw_all([wnd], tf_msg[0], tf_msg[1] + dzf * tf_msg[2], tf_msg[2], (self.width, self.height))
                else: self.ui_render.draw_all([wnd], cx, ref_frame('msg')[0] + dzf * s, s, (self.width, self.height))
            for cy, wins_g in bottom.items():
                for wnd in wins_g:
                    if wnd.typ == 53: self._initial_border(wnd, cx, cy, s)
                self.ui_render.draw_all([wnd for wnd in wins_g if not self._menu_hidden(wnd.typ)], cx, cy, s, (self.width, self.height))
            for p, tf in custom.items():
                if self._menu_hidden(self.ui_g.f[p].typ): continue
                if self.ui_g.f[p].typ in CENTERED_WINDOWS: self._initial_border(self.ui_g.f[p], tf[0], tf[1], tf[2], True)
                self.ui_render.draw_all([self.ui_g.f[p]], tf[0], tf[1], tf[2], (self.width, self.height))
            self._anchor_battle_speed(entries, msg, dz, s, cx, ref_frame, tf_msg)
        wins = [(p, f) for p, f in eng.ui.visible_ones() if not (self.ui_g and p in self.ui_g.f)]
        if not wins: return
        ui_scale = self.height / 720.0; W, H = self.width, self.height
        size_value = 17 * ui_scale; rh = 36 * ui_scale; pad = 16 * ui_scale; gap = 18 * ui_scale
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        x_main = 40 * ui_scale
        for port, f in wins:
            lines = self._menu_lines(f)
            if not lines: continue
            # width: widest text + label/value area
            left_width = max(self._lbl(l[1], size_value).content_width for l in lines)
            def stack(l): return bool((l[2] and '\n' in l[2]) or (l[3] and '\n' in l[3]))        # labels/values on several lines (PV / PM / Nv.)
            def block_width(l):
                if stack(l):
                    wl = max([self._lbl(t, size_value * 0.8).content_width for t in (l[2] or '').split('\n')] + [0]); wv = max([self._lbl(t, size_value).content_width for t in (l[3] or '').split('\n')] + [0])
                    return wl + 10 * ui_scale + wv
                return max(self._lbl(l[2], size_value * 0.8).content_width if l[2] else 0, self._lbl(l[3], size_value).content_width if l[3] else 0)
            right_width = max([block_width(l) for l in lines] + [0])
            tops = [rh * (0.3 + 0.62 * max(len((l[2] or '').split('\n')), len((l[3] or '').split('\n'))) if stack(l) else (1.5 if (l[2] and l[3]) else 1)) for l in lines]
            w = pad * 2 + 26 * ui_scale + left_width + (right_width + 24 * ui_scale if right_width else 0); h = pad * 2 + sum(tops)
            if port == 3: x, ytop = W - w - 24 * ui_scale, H - 24 * ui_scale
            elif port == 2: x, ytop = W - w - 40 * ui_scale, H * 0.62
            else: x, ytop = x_main, H - 24 * ui_scale; x_main += w + gap
            y = ytop - h
            background = pyglet.shapes.BorderedRectangle(x, y, w, h, border=max(2, int(3 * ui_scale)), color=(8, 12, 70), border_color=(255, 255, 255) if port == active else (150, 150, 170))
            background.opacity = 235; background.draw()
            cy = ytop - pad
            for (idx, left, lab, val, title_screen), hl in zip(lines, tops):
                base = cy - rh * 0.72
                if stack((idx, left, lab, val, title_screen)):
                    labs, vals = (lab or '').split('\n'), (val or '').split('\n')
                    wv = max([self._lbl(t, size_value).content_width for t in vals] + [0]); wl = max([self._lbl(t, size_value * 0.8).content_width for t in labs] + [0])
                    for i in range(max(len(labs), len(vals))):
                        yy = cy - rh * 0.62 * (i + 1) - rh * 0.05
                        if i < len(vals): e = self._lbl(vals[i], size_value); e.x = x + w - pad - e.content_width; e.y = yy; e.draw()
                        if i < len(labs): e = self._lbl(labs[i], size_value * 0.8); e.x = x + w - pad - wv - 10 * ui_scale - wl; e.y = yy; e.draw()
                    gy = cy - rh * 0.62 - rh * 0.05
                elif lab and val:
                    base = cy - rh * 0.72
                    e = self._lbl(lab, size_value * 0.8); e.x = x + w - pad - e.content_width; e.y = base; e.draw()
                    e = self._lbl(val, size_value); e.x = x + w - pad - e.content_width; e.y = base - rh * 0.5; e.draw()
                    gy = cy - rh * 0.95
                elif val:
                    e = self._lbl(val, size_value); e.x = x + w - pad - e.content_width; e.y = base; e.draw(); gy = base
                else: gy = base
                e = self._lbl(left, size_value, (255, 235, 130, 255) if title_screen else (255, 255, 255, 255)); e.x = x + pad + (0 if title_screen else 26 * ui_scale); e.y = gy if not (lab and val) or stack((idx, left, lab, val, title_screen)) else cy - rh * 0.72 - rh * 0.25; e.draw()
                if not title_screen and port == active and idx == f['cur']:
                    ty = (cy - hl / 2) if not (lab and val) else cy - rh * 0.6
                    pyglet.shapes.Triangle(x + pad, ty + 9 * ui_scale, x + pad, ty - 9 * ui_scale, x + pad + 15 * ui_scale, ty, color=(255, 235, 130)).draw()
                cy -= hl

    def _draw_helptext(self):
        """Information lines (F1), at the top right by default. Drawn once per frame, last, over everything (menus, history, screen buttons, toasts), whatever the scene (black screens and
        the battle start effect included: without this they flicker at every scene change)."""
        if not self.helptext: self.helptext_width = 0.0; return
        self._info()
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        stats = self.stats and bool(self.spacings)
        if stats:
            if self.n % 10 == 0 or not self.lbl_stats.text: self.lbl_stats.text = tr('menus.frames_s_engine_steps_s') % (len(self.spacings) / max(1e-6, sum(self.spacings)), (len(self.step_times) - 1) / max(1e-6, self.step_times[-1] - self.step_times[0]) if len(self.step_times) > 2 else 0.0, self.dt_engine * 1000, max(self.spacings) * 1000, self.dt_drawing * 1000)
        lines = [self.tag_label, self.lbl_hd] + ([self.lbl_stats] if stats else [])
        side, margin = self._helptext_margin()
        if (side, margin) != self.helptext_key: self.helptext_key = (side, margin); self.helptext_width = 0.0          # (window resized, full screen, other layout: the width is recomputed)
        y = self.height - 10
        for l in lines:                                 # information lines stacked, wrapping within the margin left free by the interface column
            if l.width != margin: l.width = margin
            l.y = y; y -= l.content_height + 3
        bottom = y - 3                                       # translucent black frame behind the text (readable over the scenery)
        self.helptext_width = max(self.helptext_width, max(l.content_width for l in lines) + 16)       # (the width only grows as long as F1 stays displayed: the left edge of the block, stuck to the right, and the text do not move when a digit changes)
        x0 = self.width - 4 - self.helptext_width if side == 'right' else 4
        self.helptext_border.x, self.helptext_border.y = x0, bottom
        self.helptext_border.width, self.helptext_border.height = self.helptext_width, self.height - 4 - bottom
        self.helptext_border.draw()
        for l in lines: l.x = x0 + 6; l.draw()
