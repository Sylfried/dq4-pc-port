"""Battle: monsters, background, effects, damage, speed and engine steps during a battle."""
import math, os, time
import numpy as np
import pyglet
from pyglet import gl
from dq456_pc.battle import full_screen_effects as EPE
from dq456_pc.battle import battle_speed as VC
from dq456_pc.menus import pre_game as AP
from dq456_pc.world import hd as HD
from dq456_pc.menus import sheets as SH
from dq456_pc.core import engine as ENGINE
from dq456_pc import sound as SOUND
from dq456_pc.persistence import settings as RG
from dq456_pc.window.constants import TITLE_MAP, CB_CAP, CB_MSG_BOTTOM, CH_PX, HD_LEVELS, MODE_PP, ENGINE_STEP, ORTHO_HALF_WIDTH
from dq456_pc.core import phone_scenes as PS
from dq456_pc.window.shaders import BLUR_EFFECT
from dq456_pc.window.helpers import rot_unity


GROUND_SHADER = 4            # DQ V / VI MeshChara shader 4 = Custom/DssaNormal (queue Geometry, ZWrite On, Cull Off, alpha blending): the T'n'T board's squares

class BattleMixin:
    """Battle: monsters, background, effects, damage, speed and engine steps during a battle."""

    def set_battle_speed(self, v):
        """Texte page of the Esc menu: new "Battle speed" (applied immediately, also in the middle of a battle)."""
        self.reg['battle_speed'] = RG.battle_notch(v); self.apply_scroll()

    battle_anchor = None                                                # attachment of the battle speed button (see _anchor_battle_speed and hud_mobile.Buttons.anchor)

    def _anchor_battle_speed(self, entries, msg, dz, s, cx, ref_frame, tf_msg):
        """Battle speed button: it attaches to the bottom LEFT corner of the bottom box (commands, or message), just as "Flee" attaches to the bottom right corner of the commands. Only the message window
        and the command windows (RG.BATTLE_COMMAND_WINDOWS) count: among them, the one whose frame extends lowest; the others (team banner at the top, monster names in the middle) have nothing to do with the bottom of
        the screen (the button jumped below them for one frame between two boxes). The plate has the size of the "Flee" plate (the rectangle attached under the frame, at its right edge) when it is found, otherwise the last known one.
        No visible box (between two boxes): the anchor stays where it was; very first frame of the battle (no anchor yet): the message box at its expected place (the button never appears at the grid's
        default position, on the left of the screen). -> self.battle_anchor = dict(x, y, w, h) in pixels (x: left edge of the frame, y: bottom edge of the frame)."""
        if self.engine.state.part != ENGINE.PART_BATTLE: self.battle_anchor = None; return
        cands = []
        def message_box(dzm, tf):
            c = self.ui_msg.N.get('frame')
            if c and c['vtx']: cands.append((tf[1] + (min(c['pos'][2] + v[1] for v in c['vtx']) + dzm) * tf[2], tf[0] + min(c['pos'][0] + v[0] for v in c['vtx']) * tf[2], None))      # (tf: reference frame without the message offset dzm)
        if msg and self.ui_msg is not None: message_box(dz, tf_msg or (cx, ref_frame('msg')[0], s))
        for _, p in entries:
            wnd = self.ui_g.f[p]
            if p in self.ui_followers or self._menu_hidden(wnd.typ) or self._type_name(wnd.typ) not in RG.BATTLE_COMMAND_WINDOWS: continue
            rs = wnd.rects(); tf = self.ui_tf.get(p)
            if not rs or tf is None: continue
            border_part = max(rs, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))                          # the window frame: the largest rectangle
            flee = [r for r in rs if r is not border_part and r[3] <= border_part[1] + 2.0 and r[2] >= border_part[2] - 12.0]          # plate attached under the frame, at its right edge
            d = (min((r[2] - r[0]) * tf[2] for r in flee), min((r[3] - r[1]) * tf[2] for r in flee)) if flee else None
            cands.append((tf[1] + border_part[1] * tf[2], tf[0] + border_part[0] * tf[2], d))
        if not cands and self.battle_anchor is None and self.ui_msg is not None:
            ov = self.reg['interface_windows'].get('msg'); message_box(CB_MSG_BOTTOM - self.ui_msg.bottom(), self._ui_custom('bottom', s, ov) if ov else (cx, ref_frame('msg')[0], s))
        if not cands: return
        bottom, left, d = min(cands, key=lambda c: c[0])
        d = d or (self.battle_anchor and self.battle_anchor.get('w') and (self.battle_anchor['w'], self.battle_anchor['h'])) or None
        self.battle_anchor = dict(x=left, y=bottom, w=d[0] if d else None, h=d[1] if d else None)

    def _anchor_effects(self, e):
        """Town mesh effects (packets 21 / 22): the engine places the effect on the ray of ITS camera, between the camera and the character (Morph spell, frog splash: exactly halfway,
        measured on packet 22). It has no character in the packet: we find it again, it is the one on this ray. For each effect we keep what is needed to place it back on the same character as seen by the viewer's camera
        (zoom, centering, rotation, tilt): depth ratio and angular offset (in tangents) as seen from the game's camera. With no character on the ray: position as is.
        The ray starts from the camera position the engine holds (g_camera_pos): the one Unity sent back after the last camera packet (Engine._camera_message: the game's camera as drawn),
        or, during the step that moves the camera, the engine's own."""
        anc = {}
        if e.part == ENGINE.PART_TOWN and e.meshes_seen and e.cam_pos is not None and e.cam_target is not None and e.sprites:
            Co, Dr, H, F = self._game_border(e)
            for slot in e.meshes_seen:
                mm = e.meshes.get(slot)
                if mm is None: continue
                P = np.array(mm['pos'], float); best = None
                for C in (np.array(Co, float), np.array(e.cam_pos, float)):
                    d = P - C
                    for k, sp in e.sprites.items():
                        if sp.get('pos') is None or len(sp['pos']) < 3: continue
                        S = np.array(sp['pos'], float); v = S - C; n2 = float(v @ v)
                        if n2 < 1e-6: continue
                        t = float(d @ v) / n2
                        if not 0.05 < t < 1.5: continue
                        spacing = float(np.linalg.norm(d - t * v))
                        if spacing < 0.05 and (best is None or spacing < best[0]): best = (spacing, k, S)
                if best is None: continue
                _, k, S = best
                vs, vp = S - Co, P - Co; zs, zp = float(vs @ F), float(vp @ F)
                if zs < 1.0 or zp < 0.5: continue
                anc[slot] = (k, zp / zs, float(vp @ Dr) / zp - float(vs @ Dr) / zs, float(vp @ H) / zp - float(vs @ H) / zs)
        self.anchor_effect = anc

    def _effect_pos(self, e, slot, pos):
        """Position of a town mesh effect as seen by the viewer's camera: on the same character, at the same depth ratio and the same angular offset as for the game's camera
        (identical to `pos` when the two cameras are the same)."""
        a = self.anchor_effect.get(slot); sp = e.sprites.get(a[0]) if a else None
        if a is None or sp is None or sp.get('pos') is None or self._view_border is None: return pos
        C, Dr, H, F = self._view_border
        v = np.array(sp['pos'], float) - C; zs = float(v @ F)
        if zs < 1.0: return pos
        zp = zs * a[1]
        return tuple(C + Dr * ((float(v @ Dr) / zs + a[2]) * zp) + H * ((float(v @ H) / zs + a[3]) * zp) + F * zp)

    def _calc_hd_monster(self, arr, mid, cid, algo):
        """(background task) HD texture of a monster, read from the disk cache if it exists. Capped at 4096 px per side (fewer passes if needed)."""
        f = os.path.join(self.args.cache, 'hd_%s_v%d_m%d.npy' % (cid, HD.VERSION, mid))
        try:
            if os.path.exists(f): return np.load(f)
        except Exception: pass
        h, w = arr.shape[:2]; passes = 3
        while passes > 0 and max(h, w) * 2 ** passes > 4096: passes -= 1
        if passes == 0: return arr
        a = algo(arr) if passes == 3 else HD.upscale_epx(arr, passes)
        try: np.save(f, a)
        except Exception: pass
        return a

    def _monster_texture(self, mid, sharp=False):
        """Texture of a monster for the selected sprite mode (F2): the original one (sharp pixels) or enlarged by the HD algorithm (computed in a background task, the original is used in the meantime).
        `sharp`: a mesh of a town scene (a character's animation drawn as a mesh, DQ VI's Milly playing the ocarina; DQ V's monsters in town): in the original and pixel-perfect modes it is sampled
        like the sprites around it (nearest texel), not smoothed: the ocarina frames were blurred next to her sprite."""
        if sharp and self.mode in (0, MODE_PP):
            ft = self.cb_tex.get((mid, 'sharp'))
            if ft is None:
                base = self._monster_texture(mid)
                t = self._tex(base['arr'], False, 0); gl.glBindTexture(t.target, t.id)
                gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
                ft = self.cb_tex[(mid, 'sharp')] = dict(base, t=t)
            return ft
        orig = self.cb_tex.get((mid, 0))
        if orig is None:
            try: arr = self.data.texture('m%03d' % mid)
            except Exception as ex:
                print('monster texture not found:', mid, ex, flush=True); arr = None
            else:
                if arr is None: print('monster texture missing from the data:', mid, flush=True)          # 25 numbers have no m<id> texture
            if arr is None: arr = np.zeros((16, 16, 4), np.uint8)               # monster not drawn (transparent texture) rather than stopping the game
            elif ENGINE.ENGINE_V2: arr = HD._dilate(arr, 2)          # DQ V / VI: transparent pixels = the color of the neighboring edge (alpha unchanged); their sheets keep a color under them (DQ VI pure green, DQ V pale pink) that linear filtering showed as a fringe
            t = self._tex(arr, False, 0)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            orig = self.cb_tex[(mid, 0)] = dict(t=t, tw=arr.shape[1], th=arr.shape[0], hd=False, arr=arr)
        if self.mode in (0, MODE_PP): return orig
        lookup_key = (mid, self.mode); jc = ('m',) + lookup_key
        if lookup_key in self.cb_tex: return self.cb_tex[lookup_key]
        fut = self.hd_jobs.get(jc)
        if fut is None:
            _name, cid, algo = HD.MODES[self.mode]
            self.hd_jobs[jc] = self.pool.submit(self._calc_hd_monster, orig['arr'], mid, cid, algo)
            return orig
        if not fut.done(): return orig
        del self.hd_jobs[jc]
        try: a = fut.result()
        except Exception as ex:
            print('HD smoothing failed (monster %d): %s' % (mid, ex), flush=True); self.cb_tex[lookup_key] = orig; return orig
        self.cb_tex[lookup_key] = dict(t=self._tex(a, False, HD_LEVELS), tw=a.shape[1], th=a.shape[0], hd=a is not orig['arr'])
        if not self.smoothing: self._filter_texture(self.cb_tex[lookup_key]['t'], False)
        return self.cb_tex[lookup_key]

    def _paint_particles(self, e, field=False):
        """Particles (ParticleSystem: Custom/Particle, Transparent+400, alpha blending, ZWrite Off, ZTest LEqual, Cull Off; texture etc/particles x vertex color). A town's
        (layer 0) are only seen by the town camera, the world map's (c01_init_field: layer 9) only by the field camera: in pixels there, z = -y, above the map (y = 100)."""
        p = getattr(e, 'particles', None)
        if p is None or bool(p.get('field')) != field: return
        r = ENGINE.particle_vertices(p)
        if r is None: return
        xyz, uv, col = r
        if field: xyz = xyz * np.array([1.0, 1.0, -1.0], np.float32) / CH_PX          # Unity's field (x, height, -y) in pixels -> the viewer's world map (x, height, y) in tiles
        if getattr(self, 'particle_tex', None) is None:
            arr = self.data.texture('particles')
            if arr is None: return
            self.particle_tex = self._tex(arr, False, 0)
            gl.glTexParameteri(self.particle_tex.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(self.particle_tex.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        cap = ENGINE.Engine.PARTICLE_MAX * 6; n = min(len(xyz), cap)          # (one fixed-size list: unused vertices stay degenerate)
        pp = np.zeros((cap, 3), np.float32); pp[:n] = xyz[:n]
        pu = np.zeros((cap, 2), np.float32); pu[:n] = uv[:n]
        pc = np.zeros((cap, 4), np.float32); pc[:n] = col[:n]
        vl = getattr(self, 'particle_vl', None)
        if vl is None: vl = self.particle_vl = self.prog.vertex_list(cap, gl.GL_TRIANGLES, position=('f', pp.ravel()), tex_coords=('f', pu.ravel()), colors=('f', pc.ravel()))
        else: vl.position[:] = pp.ravel(); vl.tex_coords[:] = pu.ravel(); vl.colors[:] = pc.ravel()
        self._linked_domain = None
        self.prog['cutoff'] = 0.0; self.prog['crisp'] = 0.0; self.prog['tsize'] = (128.0, 128.0)
        gl.glDisable(gl.GL_CULL_FACE); gl.glDepthMask(gl.GL_FALSE)
        self._paint(self.particle_tex, vl)
        gl.glDepthMask(gl.GL_TRUE); self.prog['tsize'] = (1.0, 1.0)

    def _battle_meshes(self, e, R=None, town=False, ortho=False, keys=False, ground=False):
        """List of (texture, vertex_list, ...) of the monster meshes of the current frame, in Unity's draw order:
        DssaMonster* shaders = alpha blending, no depth write, no face culling -> parts drawn in packet order;
        between monsters: the shader's render queue (Transparent+150, +200...), then farthest to nearest.
        `ortho`: only the meshes of the orthographic layer (DQ V / VI, packet MESH_ORTHO: logos, title texts), flat and not rotated, at their own position; otherwise only the others.
        `ground` (town): only the DQ V / VI meshes with the Custom/DssaNormal shader (GROUND_SHADER: the T'n'T board's squares), placed as the engine gives them (world coordinates,
        not turned toward the camera) and kept until the engine sends them again (it sends the board once); otherwise only the others."""
        out = []
        if ortho: R = np.eye(3)
        elif R is None: R = self._rot_camera(e)
        Rb = R if ortho else R @ rot_unity(0.0, 180.0, 0.0)            # MeshChara.SetBillboard: camera rotation x SceneCamera.s_yReverse (Euler(0, 180, 0))
        cam = np.zeros(3) if ortho else np.array(e.cam_pos, float); fw = R @ np.array([0.0, 0.0, 1.0])
        phone_width = ortho and town and e.part == ENGINE.PART_TOWN and PS.concerned(ENGINE.GM.profile().key, e.game_map) and not self._whole_phone_height(e)          # (DQ VI's prologue: core/phone_scenes)
        for slot, mm in sorted(e.meshes.items()):
            st0 = e.mesh_state.get(slot) or {}
            on_ground = town and not ortho and ENGINE.ENGINE_V2 and st0.get('shader') == GROUND_SHADER
            if on_ground != ground: continue
            if slot not in e.meshes_seen and not on_ground: continue                # immediate mode: no packet this frame = not drawn (the ground meshes stay: the engine sends them when they change)
            mid = e.models.get(slot)
            if mid is None: continue
            credits = town and mid == 8905 and self.map_name == 'ev01'          # title screen: the credit texts (Yuji Horii...), before the logo; placed by the engine, without correction (1:1 with the mobile game)
            if credits and os.environ.get('DQ_NO_CREDITS'): continue            # (test) without the credits: the difference from the normal capture gives their exact position
            st = e.mesh_state.get(slot) or {'shader': 1, 'visible': True, 'col': (1.0, 1.0, 1.0), 'off': (0.0, 1.0) if ENGINE.ENGINE_V2 else (0.0, 0.0)}
            if not st['visible'] or bool(st.get('ortho')) != ortho: continue
            ft = self._monster_texture(mid, sharp=ENGINE.ENGINE_V2 and town and not ortho and not on_ground and self.map_name != TITLE_MAP); t, tw, th = ft['t'], ft['tw'], ft['th']
            V = np.array(mm['v'], np.float32); ix = np.array(mm['idx'], np.int64)
            if self.cb_order and len(ix) % 6 == 0: ix = ix.reshape(-1, 6)[::-1].ravel()          # (trial) quadrilaterals in reverse order
            P = V[ix]
            loc = P[:, 2:5]
            if not town and not ortho: loc = EPE.widen(loc, mid, self.width / max(1, self.height))          # full-screen quad effect (35): stretched to the width of the 16/9 screen
            if town and not ortho and mid in AP.LOGO_MODELS and self.map_name == TITLE_MAP: loc = self._upscale_title_logo(loc, mm['pos'], Rb)          # title screen: logo and subtitle twice as large (intentional deviation)
            if town and ortho and mid in AP.LOGO_MODELS and self.map_name == TITLE_MAP and e.part == ENGINE.PART_TOWN:          # DQ VI's title logo, as wide as DQ IV's (pre_game.ORTHO_LOGO_SCALE; the logo of the end roll keeps its size)
                try: wanted = float(os.environ['DQ_LOGO_SCALE']) if os.environ.get('DQ_LOGO_SCALE') else None
                except ValueError: wanted = None
                loc = AP.ortho_logo(loc, 1.0 / float(self._ortho_matrix(self.width / max(1.0, float(self.height)), e)[0, 0]), ENGINE.GM.profile().key, wanted)
            if on_ground: xyz = (loc + np.array(mm['pos'], np.float32)).astype(np.float32)          # (MeshChara of the board: its vertices are already in the map's coordinates); 'rot' in the mesh's state (DQ VI's MeshChara523): its own fixed rotation instead of the camera's
            else: xyz = (loc @ (rot_unity(*st['rot']) if st.get('rot') else Rb).T.astype(np.float32)) * np.array([-1 if self.cb_mx and not ortho else 1, 1, 1], np.float32) + np.array(self._effect_pos(e, slot, mm['pos']) if town and not ortho else mm['pos'], np.float32)
            if ENGINE.ENGINE_V2: uv = np.c_[P[:, 0] + st['off'][0], st['off'][1] - P[:, 1]].astype(np.float32)        # DQ V / VI MeshChara: Material texture scale (1, -1), offset (0, 1) until cmd_mesh_tex_offset replaces it
            else: uv = np.c_[P[:, 0] + st['off'][0], 1.0 + P[:, 1] + st['off'][1]].astype(np.float32)
            cq = np.array(mm.get('col') or [255], np.float32) / 255.0   # one byte per quad = opacity of the part (shadows, fade-in appearances, blinking)
            alpha = cq[np.minimum(ix // 4, len(cq) - 1)]
            if ortho and town and phone_width: alpha = alpha * np.array([PS.ortho_alpha(x, ORTHO_HALF_WIDTH) for x in xyz[:, 0]], np.float32)          # (core/phone_scenes: fades out toward the phone's edges)
            clr = np.c_[np.ones((len(ix), 3), np.float32) * np.array(st['col'], np.float32), alpha].astype(np.float32)           # Material.color (packet 25) x vertex color
            n = len(xyz)
            vl = self.cb_vl.get(slot)
            if vl is None or vl[0] < n:                                  # FIXED capacity: recreating a list when the number of vertices changes corrupts the other monsters (glitches/blinking)
                if vl is not None: vl[1].delete()
                cap = max(CB_CAP, n)
                vl = self.cb_vl[slot] = (cap, self.prog.vertex_list(cap, gl.GL_TRIANGLES, position=('f', np.zeros(cap * 3, np.float32)), tex_coords=('f', np.zeros(cap * 2, np.float32)), colors=('f', np.zeros(cap * 4, np.float32))))
            cap = vl[0]
            pp = np.zeros((cap, 3), np.float32); pp[:n] = xyz                  # unused vertices: degenerate triangles (at point 0), never drawn
            pu = np.zeros((cap, 2), np.float32); pu[:n] = uv
            pc = np.zeros((cap, 4), np.float32); pc[:n] = clr
            vl[1].position[:] = pp.ravel(); vl[1].tex_coords[:] = pu.ravel(); vl[1].colors[:] = pc.ravel()
            queue = {0: 2100, 1: 2150, 2: 2200, 3: 3850, GROUND_SHADER: 2000, 5: 3000, 6: 3000, 7: 3001}.get(st['shader'], 2150)       # render queue of the shaders Custom/DssaChara, DssaMonster0, DssaMonster1, DssaCharaTransparent, DssaNormal (Geometry); DQ V / VI: Chara (the town's monsters: TownMonsterDraw), BssaCharaTransparent, BssaEffectTransparent
            center_pos = (xyz.min(0) + xyz.max(0)) / 2
            out.append(((queue, -float((center_pos - cam) @ fw)), t, tw, th, vl[1], st['shader'], ft['hd']))
        out.sort(key=lambda o: o[0])
        return out if keys else [o[1:] for o in out]          # (`keys`: with the sort key (render queue, depth), to merge them with other drawings)

    def _battle_background(self, c):
        """The engine sends no background color in battle, and the scenery leaves a gap between the edge of the floor and the sky:
        we take the average color (texture x vertex color) of the floor at the periphery of the arena, sky excluded."""
        try:
            pts = []
            for iobj, nm in c.get('names', {}).items():
                if 'sora' in nm.lower(): continue
                for key, start_idx, n in c['spans'].get(iobj, []):
                    pos, uv, col = c['groups'][key]; tex = c['textures'].get(key)
                    if tex is None: continue
                    p, u, k = pos[start_idx:start_idx + n], uv[start_idx:start_idx + n], col[start_idx:start_idx + n]
                    h, w = tex.shape[:2]
                    px = tex[np.clip(((1 - u[:, 1]) * (h - 1)).astype(int) % h, 0, h - 1), np.clip((u[:, 0] * (w - 1)).astype(int) % w, 0, w - 1)]
                    rgb = px[:, :3] / 255.0 * k[:, :3]
                    ok = px[:, 3] > 128
                    pts.append(np.c_[np.hypot(p[:, 0], p[:, 2] - 3.0), p[:, 1], rgb][ok])
            a = np.concatenate(pts)
            ground = a[(a[:, 1] < 2.0) & (a[:, 0] >= np.percentile(a[:, 0], 60))]        # ground of the periphery of the arena
            if len(ground) < 20: ground = a[a[:, 0] >= np.percentile(a[:, 0], 85)]
            return tuple(float(x) for x in ground[:, 2:].mean(0))
        except Exception as ex:
            print('battle background not computed:', ex, flush=True); return None

    def _ui_monster_x(self, mask, entries=False):
        """X coordinates (interface units, 450 x 800 portrait column) of the monsters in a mask: slot i = bit i (MeshChara) projected by the battle camera. -> (min, max), or the list of x coordinates (one per monster) if `entries`."""
        M = getattr(self, '_M_battle', None); e = self.engine.state
        if M is None: return None
        ui_scale = self.height / 800.0 * self.ui_k; cx = {'center': self.width / 2, 'right': self.width - 225 * ui_scale, 'left': 225 * ui_scale}.get(self.args.ui_pos, self.width / 2)
        xs = []
        for i in range(32):
            if not (mask >> i) & 1: continue
            mm = e.meshes.get(i)
            if not mm: continue
            P = np.array(list(mm['pos']) + [1.0]); c = M @ P
            if c[3] <= 0: continue
            xs.append((((c[0] / c[3]) * 0.5 + 0.5) * self.width - cx) / ui_scale)
        if entries: return xs
        return (min(xs), max(xs)) if xs else None

    def _draw_effect(self, ef):
        """Battle start effect: black background, pieces of the capture that fall (see battle_effect.py)."""
        sim = self.sim_effect
        target = math.ceil(ef['n'] * ENGINE.BATTLE_EFFECT_FRAMES / ef.get('duration', ENGINE.BATTLE_EFFECT_FRAMES))          # cascade shortened by "Transition speed": the simulation advances by several game frames per engine frame
        while sim.frames < target and not sim.finished: sim.stage()
        gl.glClearColor(0.0, 0.0, 0.0, 1.0); self.clear()
        gl.glViewport(0, 0, *self.get_framebuffer_size())
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        vl = self.effect_vl; vl.position[:] = sim.positions().ravel(); vl.colors[:] = sim.colors().ravel()
        self.program_effect.use(); self.program_effect['lum'] = float(sim.lum); self.program_effect['blur'] = BLUR_EFFECT
        gl.glActiveTexture(gl.GL_TEXTURE0); gl.glBindTexture(self.effect_tex.target, self.effect_tex.id)
        vl.draw(gl.GL_TRIANGLES)
        self.program_effect.stop()

    # jump of the damage digits: upward offset (interface units) at each tick of 2 / 30 s (HoppingNumber.Update)
    DAMAGE_JUMP = (0, 0, 4, 4, 6, 6, 6, 6, 4, 4, 2, 2, 0, 0, 2, 2) + (0,) * 22

    def _digits_tex(self):
        """Digits 0 to 9 (white with shadow, 16 x 16 px) from the menu sheet: separate textures."""
        if self._tex_count is None:
            self._tex_count = []
            try:
                im = SH.rgba(self.args.cache, 'ui_MenuTexture.png'); y0 = 288 + SH.interface_dy(self)          # (the sheet the menus have already decoded; DQ V / VI: their interface block is lower)
                for d in range(10):
                    a = im[y0:y0 + 16, 576 + 16 * d:592 + 16 * d]
                    t = pyglet.image.ImageData(16, 16, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes(), pitch=64).get_texture(); gl.glBindTexture(t.target, t.id)
                    gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
                    self._tex_count.append(pyglet.sprite.Sprite(t))
            except Exception as ex: print('Damage numbers unavailable: %r' % (ex,), flush=True)
        return self._tex_count

    def _draw_damage(self, e):
        """Damage numbers that hop above the monster that was hit (BattleMenu_setHoppingNumbers -> HoppingNumber.Create): four digits at most, a tick (2 / 30 s) of offset between
        two digits, each digit visible for 19 ticks. Position: foot of the monster projected by the battle camera, plus min(height x 1.85 ; 160) interface units."""
        if not self.damage_count: return
        if e.part != ENGINE.PART_BATTLE or getattr(self, '_M_battle', None) is None: self.damage_count = []; return
        sp = self._digits_tex()
        if not sp: self.damage_count = []; return
        img = self.engine.frames + self.alpha                          # engine frame, fraction included
        ui_scale = self.height / 800.0 * self.ui_k; living = []
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        for n in self.damage_count:
            mm = e.meshes.get(n['ch'])
            digits = [int(c) for c in str(max(0, min(9999, n['dm'] & 0xffff)))]
            t = img - n['t0']                                           # ticks elapsed since creation (1 tick = 1 engine frame)
            if t > 21 + 2 * len(digits): continue                     # finished (last digit: wait >= 38)
            living.append(n)
            if not mm: continue
            P = np.array(list(mm['pos']) + [1.0]); c = self._M_battle @ P
            if c[3] <= 0: continue
            px = ((c[0] / c[3]) * 0.5 + 0.5) * self.width; py = ((c[1] / c[3]) * 0.5 + 0.5) * self.height + min(n['h'] * 1.85, 160.0) * ui_scale
            kd = float(self.reg['damage_size']); size_value = 25.6 * ui_scale * kd; step = 12.8 * ui_scale * kd; wid = (len(digits) - 1) * step + size_value              # HoppingNumber.Setup: 16 px digit enlarged x 2 (AddIcon size 2.0), i.e. 32, advance of 16 (PartsInfo[11].m_dps) per digit, all x 0.8 (local scale): the cells overlap by half, the digits (7 px out of 16) stay tight
            for k, d in enumerate(digits):
                wait = -(1 + 4 * k) + 2 * t                                  # digit counter: 2 ticks of offset between digits, 2 per tick
                if not 0 <= wait < 38: continue
                jump = self.DAMAGE_JUMP[int(wait)] * 0.8 * ui_scale
                s = sp[d]; s.update(x=px - wid / 2 + k * step, y=py + jump, scale=size_value / 16.0); s.draw()
        self.damage_count = living

    def _battle_end_box(self):
        """True when a battle's dialogue box must disappear: a fade to black begins and the box is not waiting for a key (no end-of-page cursor: last page confirmed, or a message that closes by itself such as "Ragnar meurt !").
        The engine closes the box only after the fade: it stayed displayed on the screen as it darkens. A box that is still waiting for a key stays displayed. It comes back if a new (opening) fade begins."""
        eng = self.engine; e = eng.state; fd = e.fade; feed = bool(eng.ui.msg.get('feed'))
        fade_rising = e.part == ENGINE.PART_BATTLE and fd['step'] > 0 and (fd['n'] >= 1 or fd['a'] >= 0.999)         # fade to black in progress (or black held)
        if not fade_rising: self._box_hidden = False
        elif not getattr(self, '_prev_fading', False): self._box_hidden = not feed
        self._prev_fading = fade_rising
        if feed: self._box_hidden = False                                  # a page waiting for a key must be visible
        return getattr(self, '_box_hidden', False)

    def _battle_clock(self):
        """Is the game in a battle, in the sense of the engine's clock? The engine's "battle" part (0xd), but also the screen effect that starts it and the black screen waiting for its scene to load (State.effect,
        State.load_wait: only a battle clears them). Outside of that, the battle speed has no effect (walking keeps its settings); in battle, conversely, walking and the accelerator have no effect."""
        e = self.engine.state
        return e.part == ENGINE.PART_BATTLE or e.effect is not None or e.load_wait is not None

    def _battle_won(self):
        """The battle is won and shows its results (battle history's sensor: BattleSensor.won); never during a battle replay."""
        if getattr(self, '_replay', None) is not None: return False
        cc = getattr(self.engine, 'battle_sensor', None)
        return bool(cc is not None and getattr(cc, 'active', False) and cc.won())

    def _wait_for_player(self):
        """Is the engine waiting for the player in battle? A menu that has the input (commands, target, spells, items, Yes / No) or a message that shows its ▼ cursor (Manuel: a key is expected). Keys are then read only at
        normal pace ("silent" steps between two reads, see _do_battle_step): cursor and key repeat unchanged, while the monsters follow the battle speed. (The last message of a battle also waits for a key
        without showing the cursor: not detectable, so its extra steps are read as ordinary steps.)"""
        eng = self.engine
        if getattr(self, '_replay', None) is not None: return bool(eng.msg_visible and eng.ui.msg.get('feed'))          # replay: the recording answers the menus, only the messages wait for the player
        p = eng.active_menu()
        if p is not None: return True          # (monster arena: the "Quit" window has no input, see Engine.ignored_types: it is not a player wait)
        return bool(eng.msg_visible and eng.ui.msg.get('feed'))

    _t_real_step = 0.0                                                  # time of the last step that read the keys (accelerated battle: see _do_battle_step)

    def _do_battle_step(self):
        """One engine step during an accelerated battle. When the engine is waiting for the player, only one step in (f) reads the keys and clicks, at normal pace (one per 1 / 30 real seconds); the others are silent: the engine advances
        (monster idle animation, windows) at the chosen speed, without any cursor or key repeat going faster. -> False when the rest of the frame must not be caught up: the entry cascade begins, or a replay's
        next turn does; otherwise True."""
        t = time.perf_counter()
        mute = self._wait_for_player() and t - self._t_real_step < ENGINE_STEP * VC.TOLERANCE
        if not mute: self._t_real_step = t
        e = self.engine.state; before = e.effect is not None
        skip = getattr(self, '_replay_skipping', False)
        if getattr(self, '_replay', None) is not None: self.replay_skip_step(skip and self.replay_between_turns())          # (the monsters keep the real clock between two turns)
        self._step(mute)
        if skip and not self.replay_between_turns(): return False          # (a replay's next turn has begun: the rest of the frame goes on the battle's clock, not at REPLAY_SKIP)
        return before or e.effect is None          # the entry cascade starts during this step: we stop there, the rest of the frame resumes on the game clock (see _speed_factor)

    def change_battle_speed(self):
        """Key "Change battle speed" or battle screen button: Manual -> Normal -> Fast -> Very fast -> Manual. The setting changes immediately (the text scrolling settings of Affichage reread it), is saved and also governs
        message scrolling (Manuel: by hand). No message on screen (removed): the battle screen button shows the speed, and so does the "Text scrolling" section of the Display page."""
        v = RG.next_battle_speed(self.reg['battle_speed']); self.reg['battle_speed'] = v; self.apply_scroll(); self.reg.store()
        return v
