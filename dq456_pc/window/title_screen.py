"""Pre-game screens: title (sky, logo), license, name entry, saves."""
import os
import numpy as np
import pyglet
from pyglet import gl
from dq456_pc.language import N_
from dq456_pc.menus import pre_game as AP
from dq456_pc.menus import saves_screen as ES
from dq456_pc.menus import language_screen as LS
from dq456_pc.render import title_sky as CT
from dq456_pc.render import postfx as PF
from dq456_pc import paths as CH
from dq456_pc.menus import flags as FL
from dq456_pc.menus import ui_menu as UI
from dq456_pc.window.constants import EXTENDED_SKIES, SCENERY_BIAS, SFX_BUTTON
from dq456_pc.core import engine as ENGINE


class TitleMixin:
    """Pre-game screens: title (sky, logo), license, name entry, saves."""

    def _upscale_title_logo(self, loc, pos, Rb):
        """Title screen: logo (model 8901: "DRAGON QUEST", "IV", subtitle) and animated glint (8900) enlarged by AP.LOGO_SCALE around a common point (pre_game.upscale_logo), without depth offset.
        INTENTIONAL DEVIATION from the APK. The factor is reduced if the enlarged logo would exceed the window width (very narrow window); DQ_LOGO_SCALE=1: the original logo."""
        try: wanted = float(os.environ.get('DQ_LOGO_SCALE', AP.LOGO_SCALE))
        except ValueError: wanted = AP.LOGO_SCALE
        if wanted == 1.0: return loc
        wid = 0.0; M = self._M_town
        if M is not None:
            try:
                xs = []
                for sx in (-1.0, 1.0):
                    q = np.array(pos, float) + Rb @ np.array([sx * AP.LOGO_HALF_WIDTH, 0.0, 0.0]); c = M @ np.append(q, 1.0); xs.append(c[0] / c[3])
                wid = abs(xs[1] - xs[0]) / 2.0                              # width of the APK logo, as a fraction of the window width (NDC: -1 to 1)
            except Exception: wid = 0.0
        try: y0 = float(os.environ.get('DQ_LOGO_Y', AP.LOGO_Y_FIXED))
        except ValueError: y0 = AP.LOGO_Y_FIXED
        return AP.upscale_logo(loc, AP.logo_factor(wid, wanted), y0)

    def _title_sky(self, c, src):
        """Title screen: the sky (identical scrolling cloud tiles) is designed for the portrait screen; in 16/9 its edges would enter the field of view and the same tile would repeat 3 to 6 times.
        Solution (default): the portrait area keeps the original sky; on each side, bands of the same geometry continue it exactly, and a variant of the cloud tile (one per side) is laid over
        them with an alpha rising from the edge of the area (title_sky.py: no seam, scrolling followed, the sides do not repeat the middle). DQ_SKY_BANDS=1: bands whose texture is stretched by a
        variable amount instead; DQ_SKY_FLAT=1: the flat sky; DQ_SKY_ENLARGED=1: trial.
        Fallback (unexpected structure, or DQ_SKY_COPIES: old behavior, for comparison): two copies of the sky offset by its width, which extend the pattern as is."""
        for iobj, nm in self.names.items():
            if 'kumo' not in nm.lower(): continue
            for key, start_idx, n in self.spans.get(iobj, []):
                if key not in c['textures']: continue
                if not os.environ.get('DQ_SKY_COPIES'):
                    try:
                        bands = bool(os.environ.get('DQ_SKY_BANDS'))
                        cl = CT.WideSky(self.map_pos[key][start_idx:start_idx + n], self.objects.uv(key)[start_idx:start_idx + n], self.objects.col(key)[start_idx:start_idx + n], deform=bands)
                        only = start_idx == 0 and n == len(self.map_pos[key])                                                 # (the sky is alone in its texture group)
                        if (os.environ.get('DQ_SKY_ENLARGED') or os.environ.get('DQ_SKY_FLAT')) and only:
                            if os.environ.get('DQ_SKY_ENLARGED'): self.zoom_sky = {'key': key}                          # trial: sky enlarged around the screen center, without bands
                            else: self.flat_sky = {'key': key, 'sky': cl, 'vl': None, 'nv': 0, 'gradient': None, 'gradient_key': None}      # flat sky, texture height = window height, repeated across the width, wave effect
                            continue
                        self.ext_sky = {'sky': cl, 'tex': self.tex_gl[(src, key)], 'key': key, 'start': start_idx, 'vl': None, 'nv': 0, 'var': None, 'var_vl': {}}
                        if not bands and key in c['textures']:                                                     # (default): the original sky in the portrait area, each side turning into its own variant
                            var = []
                            for seed in CT.VARIANT_SEEDS:
                                t = self._tex(CT.variant_tile(c['textures'][key], seed), True, 99); self._filter_texture(t, self.smoothing); var.append(t)
                            self.ext_sky['var'] = var
                        continue
                    except Exception as ex: print('Title sky: %s (using offset copies instead)' % ex, flush=True)
                cur = self.objects.cur[key][start_idx:start_idx + n]; wid = float(cur[:, 0].max() - cur[:, 0].min())
                for dx in (-wid, wid):
                    vl = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', CT.cloned_positions(cur, dx).ravel()), tex_coords=('f', self.objects.uv(key)[start_idx:start_idx + n].ravel()), colors=('f', self.objects.col(key)[start_idx:start_idx + n].ravel()))
                    self.ext_map.append((self.tex_gl[(src, key)], vl, key, start_idx, n, dx))

    def _extended_sky(self, c, src, name_str):
        """Sky plane of the EXTENDED_SKIES maps (dpout, ev09): designed for the portrait screen, it stops before the window edges in 16/9 (black corners). On either side, a SYMMETRIC copy of the plane (left and right edges
        act as a mirror, same texture coordinates: the image continues seamlessly, like the title sky copies); the central portrait area keeps exactly the original sky. Added to `ext_map` (drawn and updated like the title copies)."""
        words = EXTENDED_SKIES.get(name_str, ())
        for iobj, nm in self.names.items():
            if not any(m in nm.lower() for m in words): continue
            spans = [(key, start_idx, n) for key, start_idx, n in self.spans.get(iobj, []) if key in c['textures'] and (src, key) in self.tex_gl and n]
            edges = {(float(self.objects.cur[k][a:a + m][:, 0].min()), float(self.objects.cur[k][a:a + m][:, 0].max())) for k, a, m in spans}
            whole = (min(e[0] for e in edges), max(e[1] for e in edges)) if len(edges) > 1 else None          # (parts of one plane that stop at different places, DQ VI's world map: one axis for the whole plane)
            for key, start_idx, n in spans:
                cur = self.objects.cur[key][start_idx:start_idx + n]
                for i, side in enumerate(('min', 'max')):                     # the SIDE, not the x coordinate: the ev09 layer scrolls, the mirror axis must follow it
                    dx = ('mirror', whole[i] if whole else side)
                    vl = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', CT.cloned_positions(cur, dx).ravel()), tex_coords=('f', self.objects.uv(key)[start_idx:start_idx + n].ravel()), colors=('f', self.objects.col(key)[start_idx:start_idx + n].ravel()))
                    self.ext_map.append((self.tex_gl[(src, key)], vl, key, start_idx, n, dx))

    def _paint_flat_sky(self, t):
        """Flat title screen sky, in place of the original sky group: the texture has the window's height and repeats across the width, with the wave effect (title_sky.screen_sky; scrolling of the tracked object,
        tint gradient of the original rows). -> True if it was drawn; any error: False (the caller draws the original sky) and the flat rendering is turned off."""
        c = self.flat_sky
        if c is None or self._M_town is None: return False
        try:
            key = c['key']; cl = c['sky']; phi = float(self.objects.cur[key][0, 0] - self.map_pos[key][0, 0])
            lookup_key = (np.asarray(self._M_town, float).tobytes(), float(self._town_aspect))
            if c['gradient_key'] != lookup_key: c['gradient'] = CT.screen_gradient(self._M_town, cl.rows, cl.x_mil); c['gradient_key'] = lookup_key
            P, U, C = CT.screen_sky(self._town_aspect, phi / cl.period, c['gradient']); n = len(P)
            if c['vl'] is None or c['nv'] != n:
                if c['vl'] is not None: c['vl'].delete()
                c['vl'] = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', P.ravel()), tex_coords=('f', U.ravel()), colors=('f', C.ravel())); c['nv'] = n
            else: c['vl'].position[:] = P.ravel(); c['vl'].tex_coords[:] = U.ravel(); c['vl'].colors[:] = C.ravel()
            self._linked_domain = None                          # vertices rewritten AFTER the first draw of the frame: without rebind + commit() they are not sent (see _paint_sky)
            gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)
            self.prog['mvp'] = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)          # normalized screen coordinates: no projection
            self._paint(t, c['vl'])
            self.prog['mvp'] = tuple(float(x) for x in self._M_town.T.ravel())
            gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
            return True
        except Exception as ex:
            self.flat_sky = None; self.prog['mvp'] = tuple(float(x) for x in self._M_town.T.ravel()); gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
            print('Title sky (flat) disabled: %s' % ex, flush=True)
            return False

    def _paint_sky(self, r, sharp_o):
        """Title screen sky bands (after the opaque scenery, same plane as the original sky: depth offset to pass in front of its part outside the portrait area). Any error: the original sky alone is kept."""
        c = self.ext_sky
        if c is None or self._M_town is None: return
        try:
            key = c['key']; phi = float(self.objects.cur[key][c['start'], 0] - self.map_pos[key][c['start'], 0])
            b = c['sky'].bands(self._M_town, self._town_aspect, phi)
            if b is None: return
            P, U, C = b; n = len(P)
            if c['vl'] is None or c['nv'] != n:
                if c['vl'] is not None: c['vl'].delete()
                c['vl'] = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', P.ravel()), tex_coords=('f', U.ravel()), colors=('f', C.ravel())); c['nv'] = n
            else: c['vl'].position[:] = P.ravel(); c['vl'].tex_coords[:] = U.ravel(); c['vl'].colors[:] = C.ravel()
            t = r.get(key, c['tex']) if r else c['tex']
            layers = []
            for side, a, z, cc in (c['sky'].side_layers(C) if c.get('var') else []):                    # each side's variant over the continued original (alpha: its share)
                vs = c['var_vl'].get(side)
                if vs is None or vs[1] != z - a:
                    if vs is not None: vs[0].delete()
                    vs = c['var_vl'][side] = (self.prog.vertex_list(z - a, gl.GL_TRIANGLES, position=('f', P[a:z].ravel()), tex_coords=('f', U[a:z].ravel()), colors=('f', cc.ravel())), z - a)
                else: vs[0].position[:] = P[a:z].ravel(); vs[0].tex_coords[:] = U[a:z].ravel(); vs[0].colors[:] = cc.ravel()
                layers.append((c['var'][side], vs[0]))
            self._linked_domain = None                          # vertices created or rewritten AFTER the first draw of the frame (the opaque scenery has just been drawn): without rebind + commit() they are not sent: on the title's first frame the bands were missing (black sides), then they were one frame behind
            gl.glEnable(gl.GL_POLYGON_OFFSET_FILL); gl.glPolygonOffset(0.0, -SCENERY_BIAS * (len(self.map_vl) + 2))
            self.prog['crisp'] = sharp_o if (r is None or key not in r) else 0.0; self.prog['tsize'] = (float(t.width), float(t.height)); self._paint(t, c['vl'])
            if layers:                                          # (blended over: alpha blending, not the MSAA alpha-to-coverage of the opaque scenery, which would dither the share; depth equal to the bands')
                cutoff0 = self.prog['cutoff']; self.prog['cutoff'] = 0.0; self.prog['crisp'] = sharp_o
                was_blend, was_a2c = gl.glIsEnabled(gl.GL_BLEND), gl.glIsEnabled(PF.SAMPLE_ALPHA_TO_COVERAGE)
                if was_a2c: self.prog['a2c'] = 0.0; gl.glDisable(PF.SAMPLE_ALPHA_TO_COVERAGE)
                gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA); gl.glDepthFunc(gl.GL_LEQUAL); gl.glDepthMask(gl.GL_FALSE)
                for vt, vl in layers: self.prog['tsize'] = (float(vt.width), float(vt.height)); self._paint(vt, vl)
                gl.glDepthMask(gl.GL_TRUE); gl.glDepthFunc(gl.GL_LESS); self.prog['cutoff'] = cutoff0
                if was_a2c: self.prog['a2c'] = 1.0; gl.glEnable(PF.SAMPLE_ALPHA_TO_COVERAGE)
                if not was_blend: gl.glDisable(gl.GL_BLEND)
            gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)
        except Exception as ex:
            gl.glDisable(gl.GL_POLYGON_OFFSET_FILL); self.ext_sky = None
            print('Title sky (strips) disabled: %s' % ex, flush=True)

    def _is_start_menu(self, port):
        """True if this port is the start menu (type 53, Make_StartMenuSecond)."""
        wnd = self.ui_g.f.get(port) if self.ui_g else None
        return bool(wnd and wnd.typ == 53)

    # ---- language plate of the start menu
    def other_game_language(self):
        """The game language the language plate switches to ('en' from French, 'fr' from English), or None if its APK files are missing (or the APK files are forced: --apk, tests)."""
        other = 'en' if self.game_language == 'fr' else 'fr'
        if getattr(self.args, 'apk_forced', False): return None
        try: return other if CH.FOLDERS.choose_apk(other)[1] == other else None
        except Exception: return None

    def _language_plate(self, wnd):
        """Every frame of the start menu: the globe on the language plate (texture drawn once), grayed if the other language cannot be loaded."""
        if 'globe' not in self.ui_render.tex: self.ui_render.add_texture('globe', FL.globe(UI.GLOBE_PX))
        if getattr(self, '_other_language', 0) == 0: self._other_language = self.other_game_language()          # (the APK folders are looked at once per game)
        wnd.set_language_globe(self._other_language is not None)

    def open_language_screen(self):
        """Language plate confirmed (click, Enter, A): the language screen, where each language is chosen by its flag; nothing when the other language cannot be loaded."""
        if self.other_game_language() is None: return
        self.port_screen = LS.LanguageScreen(self); self.press_state = None; self.hover_node = None

    def _open_saves(self):
        if self.initial_status is None: self.initial_status = self.engine.catalog_status()          # state of the adventure logs when the engine built the start menu (its grayed-out / absent buttons depend on it)
        self.port_screen = ES.SavesScreen(self); self.press_state = None; self.hover_node = None

    def _close_port_screen(self):
        s, self.port_screen = self.port_screen, None
        if s is not None and s.needs_reload: self._after_import()

    def _after_import(self):
        """Adventure logs have just been imported (the engine's catalog was already re-read by the "Saves" screen)."""
        self.toast(N_('menus.saves_imported'))                      # (N_: marks the text, which toast() translates)

    def _initial_border(self, wnd, cx, cy, s, visible_ones=False):
        """Black frame (like the port's other menus) behind the whole start menu (or the centered pre-game window)."""
        r = wnd.menu_border(22.0, visible_ones)
        if r is None: return
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        self.pause._border(cx + r[0] * s, cy + r[1] * s, (r[2] - r[0]) * s, (r[3] - r[1]) * s, s * 800.0 / 900.0)
        self.pause._restore_blend()

    flat_sky = None                                                   # (DQ_SKY_FLAT=1, the default): {'key': title sky group, 'sky': WideSky, 'vl', 'nv', 'gradient', 'gradient_key'} when the sky is drawn flat at screen scale (title_sky.screen_sky)

    zoom_sky = None                                                   # trial (DQ_SKY_ENLARGED=1): {'key': title sky group} when the sky is enlarged (title_sky.screen_zoom) instead of being extended by bands

    def _update_title(self):
        """The window of type 73 (Make_TitleTouch; port 12 in DQ IV / V, 13 in DQ VI): the engine gives it no cell, "Touchez l'ecran" and the copyright are drawn by Unity (TapToStart); code 0 is CountReset."""
        eng = self.engine; f = next((w for w in eng.ui.f.values() if w.get('type') == AP.TITLE_TOUCH_TYPE and w.get('act')), None)
        if f is not None:
            if self.title_screen is None: self.title_screen = AP.TitleTouch(eng.frames, self.pre_game_files); self.title_n = f.get('n_codes', {}).get(0, 0)
            n = f.get('n_codes', {}).get(0, 0)
            if n > self.title_n: self.title_screen.reset()
            self.title_n = n
            self.title_screen.do_update(eng.frames)
        else: self.title_screen = None
        self._update_name_entry(); self._update_license()
        if self.port_screen is not None: self.port_screen.do_update()

    def _update_license(self):
        """Window of type 80 (Make_License) on port 15: the license text is drawn by Unity (LicenseNobu)."""
        eng = self.engine; port = next((q for q, f in eng.ui.f.items() if f.get('type') == 80 and not f.get('closed')), None)
        if port is None: self.license_panel = None; return
        if self.license_panel is None: self.entry_port = port; self.license_panel = AP.License(self.pre_game_files.get('licence'))
        eng.state.fade['black'] = 0                                         # (the screen stays black as long as the window is open: no automatic reopening after 6 s)

    def _license_back(self):
        self.engine.send_menu(self.entry_port, 1, -1, 0x20); self.menu_to_release = self.entry_port                  # (back: gamepad 0x20, silent as in MenuPortItem.Update)

    def _license_click(self, x, y, button):
        lic = self.license_panel; name_str = lic.zone(x, y)
        if button == pyglet.window.mouse.RIGHT: self._license_back(); return
        if lic.on_bar(x, y): lic.dragging = True; lic.drag_to(y); return                 # scroll bar: the cursor slides with the pointer
        if name_str == 'retour': self._license_back()
        elif name_str == 'politique':
            self.sound.play_sfx(SFX_BUTTON)
            try: import webbrowser; webbrowser.open(AP.PRIVACY_URL)
            except Exception as ex: print('Could not open the privacy policy page: %r' % (ex,), flush=True)

    def _draw_saves(self):
        if self.port_screen is None: return
        self._blur_window()                                                   # (the title blurred behind the Sauvegardes and language screens)
        cx, cy, ui_scale = self._ui_reference(); self.port_screen.draw_all(self, cx, cy, ui_scale)

    def _draw_license(self):
        if self.license_panel is None: return
        cx, cy, ui_scale = self._ui_reference(); self.license_panel.draw_all(self, cx, cy, ui_scale)

    def _update_name_entry(self):
        """Window of type 55 (StartNameEntry): the name entry keyboard is handled by Unity; it is visible as long as the engine has sent [12, 1, 1] (message [12, 0, 8] gives the number of characters).
        On the start menu, the name entry is the start of a new game (MaterielMenu_LOAD::makeDiary follows it): the "new game" panel of the Esc menu opens with it. After the name, the game asks the
        hero's gender in the same window (MaterielMenu_NameEdit, state 3: buttons 0 Masculin, 1 Féminin): the gender chosen in the panel is answered for the player (`auto_gender`), the window
        is not drawn until it closes."""
        eng = self.engine; port = next((q for q, f in eng.ui.f.items() if f.get('type') == 55 and not f.get('closed')), None)
        f = eng.ui.f.get(port) if port is not None else None
        keyboard_on = bool(f and f['indicators'].get(1) == 1)
        if keyboard_on and not self.name_entry.active:
            self.entry_port = port; self.name_entry.open_menu((f['indicators'].get(0, 8) & 0xff) or 8); self.auto_gender = None
            if eng.state.part == ENGINE.PART_INITIAL: self.pause.open_menu(new_game=True)          # a new game: its panel (Difficulty, Randomizer, the name entry on its right, the gender (not DQ V / VI), "Start the adventure")
        elif not keyboard_on and self.name_entry.active: self.name_entry.shutdown()
        if self.auto_gender is not None:
            if f is None: self.auto_gender = None
            elif self.auto_gender >= 0 and not keyboard_on and f['visible'] and f.get('input'):
                eng.send_menu(port, 1, self.auto_gender, 0x10); self.menu_to_release = port; self.auto_gender = -1          # (-1: answered, the window stays hidden until it closes)

    def _name_entry_in_progress(self):
        return self.name_entry.active and not self.name_entry.handed and not self.engine.msg_visible and not self.pause.opened

    auto_gender = None                       # gender to answer for the player when the game asks it after the name (0 male, 1 female), -1 once answered; None: the player answers

    def _name_entry_ok(self, name_str, gender=None):
        """OK: [2, number of bytes] then the UTF-8 bytes of the name (two per number, little-endian), both before the engine's next frame. `gender`: answered for the player (the "new game" panel)."""
        import struct
        b = name_str.encode('utf-8'); n = len(b); b += b'\0' * (n % 2)
        self.engine.send_menu(self.entry_port, 2, n); self.engine.send_menu(self.entry_port, *struct.unpack('<%dh' % (len(b) // 2), b))
        self.auto_gender = gender

    def _name_entry_back(self):
        """Back: like the B key on window 55, [1, -1, 32] (the engine returns to the adventure log list)."""
        self.engine.send_menu(self.entry_port, 1, -1, 0x20); self.menu_to_release = self.entry_port

    def _draw_name_entry(self):
        if not self.name_entry.active or self.name_entry.handed or (self.pause.opened and self.pause.new_game): return          # (the panel of a new game draws it on its right; once handed to the engine, nothing until it closes)
        cx, cy, ui_scale = self._ui_reference(); self.name_entry.draw_all(cx, cy, ui_scale)

    def _draw_title(self):
        if self.title_screen is None: return
        cx, cy, ui_scale = self._ui_reference(); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        self.title_screen.draw_all(cx, cy, ui_scale, self.height)
