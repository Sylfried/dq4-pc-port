"""Savestates (save / load at any moment)."""
import os
import numpy as np
import pyglet
from pyglet import gl
from dq4_pc import paths as CH
from dq4_pc.language import N_
from dq4_pc.core import engine as ENGINE
from dq4_pc.persistence import savestates as SS


class SnapshotsMixin:
    """Savestates (save / load at any moment)."""

    @staticmethod
    def _state_number(symbol):
        K = pyglet.window.key
        digits = {K._1: 1, K._2: 2, K._3: 3, K._4: 4, K._5: 5, K._6: 6, K._7: 7, K._8: 8, K._9: 9,
                    K.NUM_1: 1, K.NUM_2: 2, K.NUM_3: 3, K.NUM_4: 4, K.NUM_5: 5, K.NUM_6: 6, K.NUM_7: 7, K.NUM_8: 8, K.NUM_9: 9}
        return digits.get(symbol)

    # ---- savestates
    def state_path(self, n): return os.path.join(CH.FOLDERS.savestates_folder(self.args.saves_write), 'state_%02d.dqs' % n)

    def state_info(self, n):
        """(info, PNG thumbnail) of savestate n, or None."""
        return SS.info(self.state_path(n))

    def _location(self):
        """Location noted in the savestate file: a catalog key (N_ marker), never translated here; the Pause menu's savestate page translates it when displaying it (Pause._label)."""
        e = self.engine.state
        if e.part == ENGINE.PART_CASINO: return N_('settings.casino_poker') if e.game_map == 'ev04' else (N_('settings.casino_slot_machine') if e.game_map == 'ev05' else N_('settings.casino'))          # (maps ev04 / ev05: see Global::setMinigame)
        if e.part == ENGINE.PART_BESTIARY: return N_('settings.bestiary')
        return N_('settings.world_map') if e.part == ENGINE.PART_FIELD else (N_('settings.battle') if e.part == ENGINE.PART_BATTLE else (e.game_map or '?'))

    def _complete_savestate(self):
        """Savestate of the engine + the viewer (including the map's animated objects)."""
        viewer = {'object_states': self.objects.state if self.objects is not None else None, 'auto_objects': self.objects.auto if self.objects is not None else None, 'event_objects': self.objects.event_state() if self.objects is not None else None, 'sra_clocks': self.objects.sra_state() if self.objects is not None else None,
                  'palettes': self.palettes.state() if self.palettes is not None else None, 'map_name': self.map_name, 'pattern_n': self.pattern_n, 'acc_pattern': self.acc_pattern.copy(), 'music': self.sound.bgm_state(),
                  'history_adventure': getattr(self.history, 'adventure', None)}          # (loading the state gives back the history of its adventure)
        return SS.snapshot(self.engine, viewer)

    def save_state(self, n, thumbnail_png=b''):
        """Records the game state in slot n."""
        d = self._complete_savestate()
        SS.write(self.state_path(n), d, {'location': self._location(), 'map': self.engine.state.game_map, 'part': self.engine.state.part, 'frames': self.engine.frames}, thumbnail_png)

    def state_language(self, lib_sha):
        """Language ('fr' or 'en') of the game version whose APK folder holds the library with this fingerprint, or None (the APK files of that version are not there, or it is another update)."""
        for lg in ('fr', 'en'):
            folder = CH.FOLDERS.apk_for(lg)
            if os.path.isfile(os.path.join(folder, 'base.apk')) and SS.apk_fingerprint(folder) == lib_sha: return lg
        return None

    def load_state(self, n):
        """Reloads slot n; the state from before the loading is kept in memory (cancel_loading). A state of the game's other language raises SS.OtherLanguage (nothing touched): the caller offers to switch the game to that language (reload_game)."""
        d = SS.read(self.state_path(n))
        try: SS.check(self.engine, d)
        except SS.OtherEngine as ex:
            lg = self.state_language(ex.lib_sha)
            if lg is not None and lg != self.game_language: raise SS.OtherLanguage(ex.lib_sha, lg)
            raise
        try: self.undo_state = self._complete_savestate()
        except Exception as ex: self.undo_state = None; print('state before loading not kept:', ex, flush=True)
        self._apply_savestate(d)

    def cancel_loading(self):
        """Goes back to the state just before the last loading (a second call redoes the loading)."""
        if self.undo_state is None: self.toast(N_('window.no_load_undo')); return False
        current = self._complete_savestate(); d, self.undo_state = self.undo_state, current
        self._apply_savestate(d); self.toast(N_('window.load_undone'))
        return True

    def _apply_savestate(self, d):
        """Puts the engine back into state `d`, then everything the window derived from it (menu windows, map, animated objects, music)."""
        eng = self.engine
        viewer = SS.apply(eng, d)
        self.ui_g_reset()
        self.map_name = None; self._orders = None; self.field_key = None; self.prev = None; self.canvas_key = None; self.msg_key = None
        self.pad_prev = 0; self.rep = {}; self.menu_to_release = None; self.hovered = None; self.press_state = None; self.hover_node = None; self.cur_local = {}; self.cursor_step = {}; self.ref_effect = None; self.effect_tex_ready = False
        self.acc = 0.0; self.t_loop = None; self.anchor_effect = {}
        self.n_battle = 0 if eng.state.part != ENGINE.PART_BATTLE else self.n_battle
        e = eng.state
        if e.game_map and e.part != ENGINE.PART_FIELD and not e.game_map.startswith('btl_'):
            self._load_map(e.game_map)
        elif e.game_map and e.part == ENGINE.PART_BATTLE: self._load_map(e.game_map)
        if viewer and 'acc_pattern' in viewer: self.pattern_n = viewer['pattern_n']; self.acc_pattern[:] = viewer['acc_pattern']; self.field_acc_seen = None          # animated water of the world map
        if viewer and (viewer.get('object_states') or viewer.get('sra_clocks')) and self.objects is not None and viewer.get('map_name', self.map_name) == self.map_name:      # (only onto the map they were taken from: a state of the world map taken after leaving a town carries that town's objects)
            self.objects.reinit(); self.objects.restore(viewer.get('object_states') or {}, viewer.get('auto_objects'), viewer.get('event_objects'), viewer.get('sra_clocks'))
            for tex, vl, key in self.map_vl:
                vl.position[:] = self.objects.cur[key].ravel(); vl.tex_coords[:] = self.objects.uv(key).ravel(); vl.colors[:] = self.objects.col(key).ravel()
            self.objects.dirty = set(); self.objects.dirty_uv = set(); self.objects.dirty_col = set()
        if viewer and viewer.get('palettes') and self.palettes is not None: self.palettes.select_language(viewer['palettes'])
        for sp in list(e.sprites.values()): self._sheet(sp['id'] - 4096 if (e.part == ENGINE.PART_FIELD and sp['id'] >= 4096) else sp['id'], self.mode)
        self.sound.restore_bgm(viewer.get('music') if viewer else None, e.music)         # the music restarts from the recorded moment
        self._deferred_jingle = []                                                       # (a level-up jingle waiting for its message belonged to the game before the load)
        self._backdrop_forget()                                                          # (the blurred scenery of the mini-games belonged to the game before the load)
        if viewer and viewer.get('history_adventure') and hasattr(self.history, 'set_adventure') and not getattr(self.history, 'replaying', False): self.history.set_adventure(viewer['history_adventure'])          # (a state keeps the history in use)
        e.sounds = []

    def _clone_thumbnail(self):
        """Copies the game image (without the menu) into a texture, on the graphics card only: the menu opens without waiting for a readback; the PNG is only made when a state is recorded."""
        try:
            w, h = self.get_framebuffer_size()
            t = pyglet.image.Texture.create(w, h, internalformat=gl.GL_RGBA8)
            gl.glBindTexture(t.target, t.id); gl.glCopyTexSubImage2D(t.target, 0, 0, 0, 0, 0, w, h)
            return t
        except Exception as ex:
            print('thumbnail failed:', ex, flush=True); return None

    def _png_thumbnail(self, t):
        """Texture from _clone_thumbnail -> reduced PNG (savestate thumbnail)."""
        if t is None: return b''
        try:
            import io
            from PIL import Image
            img = t.get_image_data()
            a = np.frombuffer(img.get_data('RGB', img.width * 3), np.uint8).reshape(img.height, img.width, 3)[::-1]
            im = Image.fromarray(np.ascontiguousarray(a)); im.thumbnail((320, 180)); b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()
        except Exception as ex:
            print('thumbnail failed:', ex, flush=True); return b''
