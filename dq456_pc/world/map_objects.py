"""Animated objects of town maps: doors that open, jars and barrels that break, chests that open, objects hidden or moved by the engine.

Reproduces on the Python side what the game's Unity layer (FldObject) does from the engine packets:
  * packet 5 (cmd_fld_common_anim): object | number << 16 -> SetCommonAnimation: the object's common animation table (FCAN, objet.canim)
    gives, for each number, the model to display (door, intact or broken jar...), a mesh sequence (FSEQ/FSQD: the model deforms
    from one frame to the next, e.g. the bursting jar) and a motion (FPMV: position, rotation and scale added to those of the object, e.g. door leaf);
    number 0 = original model, motionless;
  * packet 7 (cmd_fld_on_off): object | flag << 16 -> GameObject.SetActive(flag == 0);
  * packet 2 (cmd_fld_alpha): object | level (0..31) << 16; level 0 = invisible;
  * packet 6 (cmd_fld_event_anim): event animation number (v < 0x1000; otherwise FldObject.SetCameraNo: camera movement of the map, see `event_camera`) -> SetEventAnimation: the FEAN table gives the range of event objects to show
    (they are hidden at start, like FldObject.m_obj_tbl = -1); the map objects with the same `uid` are then hidden, and the animation of the shown objects restarts from the beginning; number 0 = everything put back to the original;
  * packets 3 and 4 (cmd_fld_pos, cmd_fld_rot): new position / rotation of the object.
Times are in sixtieths of a second in the data; FldObject.Update advances by 2 per game frame (30 frames/s).

Animations played continuously, without an engine order (FldObject.update_seq / update_pmv / update_plp):
  * mesh sequence (FMAP: seq_obj_id -> FSEQ entry): flowing water, flickering lamps... The mesh is interpolated from one frame to the next
    (vertices, UVs and colors: FldObject.seq_build_mesh); the entry gives the start delay, the delay between two rounds and the number of rounds (-1: endless);
  * motion (FMAP: pmv_id -> FPMV): spinning, swinging objects...
  * animated palettes (FPLP / FPAM): a surface's texture (sparkling water, swamp, damaging floor) changes from frame to frame (class MapPalettes);
  * material colors (FSRA, FldObject.update_sra): the diffuse color (in practice the alpha: steam, glows, fades) of all the materials whose name contains the entry's, from key to key.
    Same clock as the motions (`_clock`). Entry tied to an event (number >= 1): acts only during that event animation, restarts from the beginning when it is launched; otherwise the original color
    comes back (FldObject.update_material_color rewrites it every frame before update_sra).

Scenery billboards (FldObject, flags FLD_OBJ_FLAG_BILLBOARD_Y = 4 and FLD_OBJ_FLAG_BILLBOARD_XYZ = 32: trees, candles, torches, barrels, chairs...): a quad whose origin is the foot;
it pivots around the vertical axis (4) or takes the camera's whole rotation (32) to stay facing it. The vertices are baked at the original orientation; `orient` recomputes them
when the camera rotates (camera rotation keys, towns and dungeons)."""
import math
import numpy as np
from dq456_pc.world.data import euler_mat

STEP = 2                      # FldObject.Update: s_seq_frame_rate_step = 2 per frame
CAM_JUMP = 8.0                # town units in one step: beyond that a camera movement jumped (loop, cut), its view is not interpolated


def _interp(lookup_keys, t):
    """Sorted TzKeys [(frame, ...)] -> (index before, index after, fraction) at frame t (held on the last key)."""
    if t >= lookup_keys[-1][0]: return len(lookup_keys) - 1, len(lookup_keys) - 1, 0.0
    for i in range(len(lookup_keys) - 1):
        f1, f2 = lookup_keys[i][0], lookup_keys[i + 1][0]
        if f1 <= t < f2: return i, i + 1, (t - f1) / float(f2 - f1)
    return 0, 0, 0.0


FLD_OBJ_FLAG_LOOP = 2        # FldObject.FLD_OBJ_FLAG_LOOP: the object's mesh sequence goes back to its first frame at the end of a round


def sequence_keys(seq, obj_flag):
    """Keys of a mesh sequence as FldObject.update_seq_one (0xCDA55C) hands them to fld_motion_update: the data's last key is a terminator (frame = end, value = number of frames).
    Sequence flag bit 0 = 0: that key is left out (nkey - 1, put back after the update); bit 0 = 1: it keeps its frame and takes the frame number of the key before it, or of the first
    key if the object has FLD_OBJ_FLAG_LOOP. (Read as is, the terminator showed a wrong frame once per round: the raft of Estuaria jumped every two seconds.)"""
    ks = seq['keys']
    if not seq['flag'] & 1: return ks[:-1]
    if len(ks) < 2: return ks
    return ks[:-1] + [(ks[-1][0], (ks[0] if obj_flag & FLD_OBJ_FLAG_LOOP else ks[-2])[1])]


def _clock(delay, loop_delay, loops, end):
    """Counter of an animation (one FldObject.FLD_MOTION: cur_frame, start_delay, repeat_delay, repeat_num, end_frame): each movement (FPMV) and each mesh sequence (FSQD) has ITS own clock,
    with its own duration and number of loops (fld_motion_update 0xCD69DC, called once per motion). Two animations of the same object (e.g. the healing ray: 84-frame sequence, rotation of 800) share nothing."""
    return {'delay': delay, 'loop_delay': loop_delay, 'loops': loops, 'end': end, 'time': 0, 'finished': False}


def _advance(h):
    """One game frame for one clock (FldObject.fld_motion_update): start delay, then the time advances by STEP; past the end: one loop fewer (rep = -1: endless), return to the start
    (remainder of the overshoot) after the delay between two loops, or stop on the last key when the loops are exhausted."""
    if h['finished']: return
    if h['delay'] >= 1: h['delay'] -= STEP; h['time'] = 0
    else:
        h['time'] += STEP
        if h['time'] > h['end']:
            remainder = h['time'] - h['end']
            if h['loops'] >= 1: h['loops'] -= 1
            if h['loops'] == 0: h['time'] = h['end']; h['finished'] = True
            else: h['time'] = remainder
            h['delay'] = h['loop_delay']


def _migrate_auto(a):
    """State recorded by an old version: a single clock (the sequence's, otherwise the movement's) for the object's two animations. The two clocks resume the recorded time
    (the movement's with its own modulo)."""
    if 'sequence_clock' in a or 'motion_clock' in a: return a
    h = {k: a.get(k, d) for k, d in (('delay', 0), ('loop_delay', 0), ('loops', -1), ('end', 0), ('time', 0), ('finished', False))}
    n = {'sequence': a.get('sequence'), 'motion': a.get('motion'), 'sequence_clock': None, 'motion_clock': None}
    if n['sequence'] is not None: n['sequence_clock'] = dict(h)
    if n['motion'] is not None:
        if n['sequence'] is None: n['motion_clock'] = dict(h)
        else:
            eng = n['motion']; n['motion_clock'] = _clock(eng['delay'], eng['loop_delay'], eng['repeat'], eng['end'])
            if eng['end'] > 0: n['motion_clock']['time'] = h['time'] % eng['end']
    return n


RIDER_UP, RIDER_SLOPE, RIDER_FORWARD = 0.3, 0.212, 0.15          # DQ V, NativeManager.Update: constants of the character carried by a map object (see MapObjects.rider_position)

class MapObjects:
    def __init__(self, c):
        self.objs = c['objects']; self.spans = c.get('spans', {}); self.var = c.get('var', {}); self.tabs = c.get('tabs', [])
        self.nbase = c.get('nobj', len(self.objs)); self.ean = c.get('ean', [])                  # map objects (FLD_MAP.nobj), then event objects (up to mobj); FEAN
        self.extra = frozenset(range(self.nbase, len(self.objs)))                               # event objects: hidden until an event animation asks for them
        self.tbl_hidden = set(self.extra); self.event = 0                                        # objects hidden by the game's object table (FldObject.m_obj_tbl = -1); event animation in progress
        self.words = c.get('motions', []); self.sequences = c.get('sequences', []); self.sequence_entries = c.get('sequence_entries', [])
        self.orig = c['groups'] and {k: g[0] for k, g in c['groups'].items()} or {}
        self.cur = {k: p.copy() for k, p in self.orig.items()}                      # displayed positions (modified in place)
        self.var_of = {}                                                             # object -> [model, ...] of the variants
        for (i, m) in self.var: self.var_of.setdefault(i, []).append(m)
        for pl in (v['spans'] for v in self.var.values()):                        # variants hidden as long as no animation asks for them
            for key, d, n in pl: self.cur[key][d:d + n] = 0.0
        self._hide_extras()
        self.imgobj = c.get('imgobj', {})                                            # object -> frames (positions, UV, colors) of its mesh sequence, per sub-mesh
        self.uv0 = {k: g[1] for k, g in c['groups'].items()}; self.col0 = {k: g[2] for k, g in c['groups'].items()}
        self.cur_uv = {}; self.cur_col = {}                                          # displayed UV and colors: copies created on demand (groups where either one changes)
        self.dirty_uv = set(); self.dirty_col = set()
        self.state = {}; self.dirty = set(); self._inv = {}; self.auto = {}
        self.bill = {i: o['flag'] for i, o in enumerate(self.objs) if o.get('flag', 0) & 36 and self.valid(i)}     # scenery panels: object -> flags
        self.PITCH_DIRECTION = 1.0
        self._rb = {4: np.eye(3), 32: np.eye(3)}; self.bill_ok = False                  # current orientation (around Y / full camera); false as long as the vertices do not follow it
        self._o64 = {}; self._keys = {}; self._emat = {}; self._seq_keys = {}          # caches: original position/rotation/scale, movement keys as arrays, rotation matrices, sequence keys
        self.fac = {}; self.sra_h = {}; self.sra_col = {}                              # FSRA colors (see `_sra_setup`), before the first `_place`
        self.cameras = c.get('cameras', []); self.camera_no = 0; self.camera_clock = None; self.key_start = None; self.key_view = None     # FEMV camera movements; the one in progress (`event_camera`)
        self._init_seed()
        self._sra_setup(c)

    def reinit(self):
        """Reloading of the same map: all objects return to their original state."""
        self.state = {}; self.fac = {}
        for k in self.cur: self.cur[k][:] = self.orig[k]
        for k in self.cur_uv: self.cur_uv[k][:] = self.uv0[k]
        for k in self.cur_col: self.cur_col[k][:] = self.col0[k]
        for pl in (v['spans'] for v in self.var.values()):
            for key, d, n in pl: self.cur[key][d:d + n] = 0.0
        self.tbl_hidden = set(self.extra); self.event = 0; self._hide_extras(); self.camera_no = 0; self.camera_clock = None; self.key_start = None; self.key_view = None; self.prev_view = None
        self.dirty = set(self.cur); self.dirty_uv = set(self.cur_uv); self.dirty_col = set(self.cur_col); self.bill_ok = False
        self._init_seed(); self._sra_start()

    def _init_seed(self):
        """Starting animations: mesh sequences and movements of the objects that have one continuously (FMAP seq_obj_id / pmv_id). Each has its own clock (see `_clock`)."""
        self.auto = {}
        for i, o in enumerate(self.objs):
            if not self.valid(i) or i in self.extra: continue                                       # (event objects restart from the beginning when the animation shows them: `event_anim`)
            self._seed_one(i, o)

    def _seed_one(self, i, o):
        """Starting animation of an object (its mesh sequence, its movement), reset to the beginning: FldObject.MapObjAnimReset + update_pmv_one when an event animation shows an object."""
        sq = eng = sequence_clock = motion_clock = None; so = o.get('sequence_object', -1)
        if 0 <= so < len(self.sequence_entries) and i in self.imgobj:
            e = self.sequence_entries[so]
            if 0 <= e[1] < len(self.sequences) and e[7] != 0 and self.sequences[e[1]]['keys'] and self.sequences[e[1]]['end'] > 0:     # original number of loops 0: never started by itself
                sq = self.sequences[e[1]]; sequence_clock = _clock(e[3], e[4], e[5], sq['end'])
        mp = o.get('pmv', -1)
        if 0 <= mp < len(self.words) and self.words[mp]['keys'] and self.words[mp]['repeat'] != 0 and self.words[mp]['end'] > 0:
            eng = self.words[mp]; motion_clock = _clock(eng['delay'], eng['loop_delay'], eng['repeat'], eng['end'])
        if sq is None and eng is None: self.auto.pop(i, None); return
        self.auto[i] = dict(sequence=sq, motion=eng, sequence_clock=sequence_clock, motion_clock=motion_clock)
        st = self._st(i); st['sequence'] = sq; st['motion'] = eng; st['time'] = st['sequence_time'] = st['motion_time'] = 0; st['finished'] = False; self._place(i)

    def _hide_extras(self):
        """Event objects hidden at start: their vertices are collapsed to zero (like the variants of the common animations)."""
        for i in self.tbl_hidden:
            for key, d, n in self.spans.get(i, []): self.cur[key][d:d + n] = 0.0

    def restore(self, state, auto=None, event=None, sra=None):
        """Puts the objects back in a recorded state (savestates); `auto` absent (old format): continuous animations restarted from the beginning; `event`: (event animation number, hidden objects)
        from `event_state`, absent (old format): event objects hidden as at load; `sra`: clocks from `sra_state`, absent: FSRA colors restarted from the beginning."""
        self.state = state
        if event is not None: self.event = event[0]; self.tbl_hidden = set(event[1])
        if event is not None and len(event) >= 4: self.camera_no = event[2]; self.camera_clock = dict(event[3]) if event[3] else None
        if sra is not None:
            for m, h in sra.items():
                if m in self.sra_h: self.sra_h[m] = dict(h)
        for i in self.tbl_hidden ^ self.extra: self._st(i)                                        # (objects whose display differs from the load: their vertices are taken up again below)
        if auto is not None: self.auto = {i: _migrate_auto(a) for i, a in auto.items()}
        for i, a in self.auto.items():
            st = self._st(i); st['sequence'] = a['sequence']; st['motion'] = a['motion']
        for i in list(self.state): self._place(i)
        self._sra_refresh()
        self.dirty |= set(self.cur); self.dirty_uv |= set(self.cur_uv); self.dirty_col |= set(self.cur_col); self.bill_ok = False

    def orient(self, yaw, base, pitch=0.0):
        """Turns the scenery panels toward the camera. `yaw`: camera heading (radians, 0 = toward +Z, positive toward +X); `base`: camera (right, up, forward); `pitch`: tilt added to the camera
        (degrees, 0 = game view): panels that only rotate around Y (barrels, jars...) tilt by the same amount, to stay facing the camera when it is raised or lowered. -> True if vertices have changed."""
        if not self.bill: return False
        c, s = math.cos(yaw), math.sin(yaw)
        ry = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])                      # Quaternion.Euler(0, yaw, 0)
        if pitch:
            a = math.radians(pitch) * self.PITCH_DIRECTION; ca, sa = math.cos(a), math.sin(a)
            ry = ry @ np.array([[1.0, 0.0, 0.0], [0.0, ca, -sa], [0.0, sa, ca]])         # then tilted around the panel's horizontal axis (its foot stays in place)
        rf = np.column_stack([np.asarray(b, np.float64) for b in base])                   # full camera rotation (the object's x, y, z axes = right, up, forward)
        if self.bill_ok and np.allclose(ry, self._rb[4], atol=1e-5) and np.allclose(rf, self._rb[32], atol=1e-5): return False
        self._rb = {4: ry, 32: rf}; self.bill_ok = True
        for i in self.bill: self._place(i)
        return True

    def uv(self, key): return self.cur_uv.get(key, self.uv0[key])

    def col(self, key): return self.cur_col.get(key, self.col0[key])

    def _array_copy(self, tab, orig, key):
        if key not in tab: tab[key] = orig[key].copy()
        return tab[key]

    # ---- engine commands
    def _st(self, i):
        o = self.objs[i]
        return self.state.setdefault(i, {'model': o['model'], 'off': False, 'alpha': 31, 'pos': None, 'rot': None, 'motion': None, 'sequence': None, 'time': 0, 'motion_time': 0, 'sequence_time': 0})

    def valid(self, i):
        return 0 <= i < len(self.objs) and (i in self.spans or i in self.var_of)

    def reachable(self, i):
        """FldObject.GetMapObjPtr: an object the game's object table does not point to (m_obj_tbl = -1: an event object not shown yet, a map object an event object replaced) is null, and the
        orders sent to it (on / off, opacity, position, rotation, common animation) do nothing. DQ VI's dragon flight: the castle (event object) was switched off before its event animation showed it."""
        return self.valid(i) and i not in self.tbl_hidden

    def common_anim(self, i, no):
        if not self.reachable(i): return
        o = self.objs[i]; st = self._st(i)
        self.auto.pop(i, None); st['motion'] = st['sequence'] = None; st['time'] = st['motion_time'] = st['sequence_time'] = 0; st['finished'] = False
        if no <= 0: st['model'] = o['model']
        else:
            tab = self.tabs[o['canim']] if 0 <= o['canim'] < len(self.tabs) else []
            if no > len(tab): return
            m, sq, mp = tab[no - 1]; st['model'] = m
            if 0 <= mp < len(self.words): st['motion'] = self.words[mp]
            if 0 <= sq < len(self.sequence_entries) and 0 <= self.sequence_entries[sq][1] < len(self.sequences): st['sequence'] = self.sequences[self.sequence_entries[sq][1]]
        self._place(i)

    def duration(self, i, no):
        """Game frames during which the engine must wait for the animation to finish, or None if the object does not have this animation."""
        if not 0 <= i < len(self.objs): return None
        o = self.objs[i]; tab = self.tabs[o['canim']] if 0 <= o['canim'] < len(self.tabs) else []
        if not 1 <= no <= len(tab): return None
        m, sq, mp = tab[no - 1]; end = 0
        if 0 <= mp < len(self.words): end = max(end, self.words[mp]['end'])
        if 0 <= sq < len(self.sequence_entries) and 0 <= self.sequence_entries[sq][1] < len(self.sequences): end = max(end, self.sequences[self.sequence_entries[sq][1]]['end'])
        return max(1, -(-end // STEP)) + 1

    def on_off(self, i, flag):
        if self.reachable(i): self._st(i)['off'] = flag != 0; self._place(i)

    def alpha(self, i, level):
        if self.reachable(i): self._st(i)['alpha'] = level; self._place(i)

    def position(self, i, p):
        if self.reachable(i): self._st(i)['pos'] = tuple(p); self._place(i)

    def rotation(self, i, r):
        if self.reachable(i): self._st(i)['rot'] = tuple(r); self._place(i)

    def event_anim(self, no):
        """Packet 6 (FldObject.SetEventAnimation): event animation `no` (1 = first FEAN entry; 0 = put everything back as at load). Each object start .. end - 1 of the entry is shown
        and its animation restarts from the beginning (MapObjAnimReset); the map objects (indices < nobj) with the same non-zero `uid` are hidden: the event object replaces them (lit cell, narrated scene...).
        The objects shown by a previous animation stay shown (the engine sends 0 to put everything back). Without FEAN, or with a number outside the table: nothing."""
        if no < 0 or not self.ean or no > len(self.ean): return
        self.event = no; before = set(self.tbl_hidden); shown = []
        if no == 0: self.tbl_hidden = set(self.extra)
        else:
            start, end = self.ean[no - 1]
            for k in range(max(start, 0), min(end, len(self.objs))):
                self.tbl_hidden.discard(k); shown.append(k)
                uid = self.objs[k].get('uid', 0)
                if uid: self.tbl_hidden.update(j for j in range(self.nbase) if self.objs[j].get('uid', 0) == uid)
        for k in shown: self._seed_one(k, self.objs[k])
        for m in self.sra_h:                                                                         # FldObject.SetEventAnimation: the FSRA colors of this animation restart from the beginning
            s = self.sra[m]
            if s['event'] >= 1 and s['event'] == no: self.sra_h[m] = _clock(s['delay'], s['loop_delay'], s['repeat'], s['end'])
        self._sra_refresh()
        for i in (before ^ self.tbl_hidden) - set(shown):
            if self.valid(i): self._place(i)
        for k in shown:
            if self.valid(k): self._place(k)

    def event_state(self):
        """(event animation number, objects hidden by the object table[, camera movement number, its clock]): to be recorded in the savestates (the camera only while one is in progress)."""
        if self.camera_no: return (self.event, sorted(self.tbl_hidden), self.camera_no, dict(self.camera_clock) if self.camera_clock else None)
        return (self.event, sorted(self.tbl_hidden))

    # ---- event cameras (FEMV)
    def event_camera(self, no):
        """Packet 6 with a value >= 0x1000 (FldObject.SetCameraNo(value & 0x3fff, 0)): from now on, camera movement `no` of the map (FEMV entry no - 1) places the view,
        whatever the engine's camera: FldObject.Update (update_emv), which runs after SceneCamera.Update, gives Camera.main the movement's position and turns it toward its target
        (LookAt, with the movement's up vector). 0 = the movement stops: update_emv no longer touches Camera.main, which keeps the movement's last pose until the engine's next camera packet
        (SceneCamera.Update only places the camera when a packet arrived): the view is held in key_view (DQ V's start menu keeps the title's castle above the clouds behind its windows).
        A number outside the table changes nothing (SetCameraNo keeps the number in progress)."""
        if no == 0:
            if self.camera_no: self.key_view = self.camera_view(); self.key_start = None
            self.camera_no = 0; self.camera_clock = None; return
        if not 1 <= no <= len(self.cameras): return
        m = self.cameras[no - 1]
        self.camera_no = no; self.camera_clock = _clock(m['delay'], m['loop_delay'], m['repeat'], m['end']); self.key_start = None; self.key_view = None; self.prev_view = None

    def camera_first_key(self, step, steps, pos, forward):
        """DQ VI, cmd_fld_etc case 0 (FldObject.MoveToEventCameraFirstKey(step, steps, false), sent by script::CmdSetEventCamera every frame of its move): the view goes from where the camera
        stands to the first key of the map's first camera movement. Step 1 notes the start: the camera's position (`pos`) and the point in front of it (`forward`) at the distance that separates the
        key's position from its target; position and target then advance in a straight line (step / steps, held in 0..1) and the camera looks at the target with the key's up vector. The view
        stays there until the engine's next camera packet (camera_engine) or a camera movement (event_camera). A map without camera movement, or a first movement without key: nothing."""
        if not self.cameras or not self.cameras[0]['keys']: return
        key = self.cameras[0]['keys'][0]
        if step == 1 or self.key_start is None:
            if pos is None or forward is None: return
            d = math.dist(key[1], key[2])
            self.key_start = (tuple(float(x) for x in pos), tuple(float(p + f * d) for p, f in zip(pos, forward)))
        t = min(1.0, max(0.0, step / steps)) if steps else 1.0
        self.key_view = tuple(tuple(float(x + (y - x) * t) for x, y in zip(a, b)) for a, b in zip(self.key_start, (key[1], key[2]))) + (tuple(float(x) for x in key[3]),)

    def camera_engine(self):
        """The engine places its camera again (packet 10, SceneCamera.Update): the view left by camera_first_key ends."""
        self.key_start = None; self.key_view = None

    prev_view = None

    def camera_view(self, alpha=1.0):
        """(position, target, up vector) of the camera movement in progress (else of the view camera_first_key placed), None without one. A movement without keys: the values SetCameraNo starts from
        (position 0, target (0, 0, 1), up (0, 1, 0)). `alpha` < 1: the instant between the previous step's view and this one (the screen draws more often than the engine's 30 steps a second:
        the map objects are interpolated, a camera that moved by 30 Hz jerks shook the scene, DQ VI's flight over the clouds); a jump (the movement looping, more than CAM_JUMP units) is not."""
        if not self.camera_no: return self.key_view
        if alpha < 1.0 and self.prev_view is not None:
            p, c = self.prev_view, self.camera_view()
            if max(abs(x - y) for x, y in zip(p[0], c[0])) <= CAM_JUMP and max(abs(x - y) for x, y in zip(p[1], c[1])) <= CAM_JUMP:
                a = max(0.0, alpha)
                return tuple(tuple(float(x + (y - x) * a) for x, y in zip(u, v)) for u, v in zip(p, c))
            return c
        keys = self.cameras[self.camera_no - 1]['keys']
        if not keys: return (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
        a, b, f = _interp(keys, self.camera_clock['time'] if self.camera_clock else 0)
        return tuple(tuple(float(x + (y - x) * f) for x, y in zip(keys[a][k], keys[b][k])) for k in (1, 2, 3))

    # ---- frames
    def tick(self):
        """One game frame: advances the movements and sequences in progress. -> set of groups modified since the last call."""
        for i, a in self.auto.items():                      # continuous animations: start delay, loops, delay between two loops (FldObject.fld_motion_update), one clock per animation
            if i not in self.state: continue
            st = self.state[i]; alive = False
            for h, lookup_key in ((a.get('sequence_clock'), 'sequence_time'), (a.get('motion_clock'), 'motion_time')):
                if h is None or h['finished']: continue
                _advance(h); st[lookup_key] = h['time']; alive = True
            if alive: self._place(i)
        for i, st in self.state.items():
            if i in self.auto: continue
            if st.get('finished'): continue
            if not (st['motion'] or st['sequence']): continue
            for x, lookup_key in ((st['motion'], 'motion_time'), (st['sequence'], 'sequence_time')):         # common animation: each movement and each sequence counts its own time (FldObject.fld_motion_update: repetition, repeat = -1: endless, otherwise held on the last key)
                if not x: continue
                t = st.get(lookup_key, st['time']) + STEP
                if t > x['end'] and x['repeat'] == -1 and x['end'] > 0: t -= x['end']
                st[lookup_key] = t
            if all(st[lookup_key] >= x['end'] and x['repeat'] != -1 for x, lookup_key in ((st['motion'], 'motion_time'), (st['sequence'], 'sequence_time')) if x): st['finished'] = True
            self._place(i)
        if self.sra_h: self._sra_refresh(advance=True)
        self.prev_view = self.camera_view() if self.camera_no else None                  # (the view of the step before: the screen draws between two steps, see camera_view)
        if self.camera_clock is not None: _advance(self.camera_clock)                     # (FldObject.update_emv: the camera movement advances with the other movements)
        s = self.dirty; self.dirty = set(); return s

    # ---- couleurs de materiaux animees (FSRA)
    def _sra_setup(self, c):
        """FSRA entries of the map (`fld.sra`) and vertex ranges of their materials (`Data`); `fac`: current factor of each range (absent: original color)."""
        self.sra = c.get('sra', []); spans = c.get('sra_plages', []); self.sra_cover = {}; self.sra_info = {}; self.sra_var = {}
        for m, lst in enumerate(spans[:len(self.sra)]):
            for key, d, n, a in lst: self.sra_cover.setdefault((key, d), []).append(m); self.sra_info[(key, d)] = (n, a)
        self.sra_spans = spans
        for i, imgs in self.imgobj.items():                                  # ranges whose mesh sequence varies the color: the factor is multiplied in `_place`
            for k, (key, d, n) in enumerate(self.spans.get(i, [])):
                if (key, d) in self.sra_info and imgs[k] and imgs[k]['col'] is not None: self.sra_var[(key, d)] = i
        self._sra_keys = [np.array([k[1] for k in s['keys']], np.float64) if s['keys'] else None for s in self.sra]
        self._sra_start()

    def _sra_start(self):
        """All the clocks at start (one per entry that acts: keys, ranges, rounds and duration non-zero; FldObject.fld_motion_update returns -1 otherwise), original colors, then colors of frame 0."""
        self.sra_h = {}; self.sra_col = {}; self.fac = {}
        for m, s in enumerate(self.sra):
            if m < len(self.sra_spans) and self.sra_spans[m] and s['keys'] and s['repeat'] != 0 and s['end'] > 0: self.sra_h[m] = _clock(s['delay'], s['loop_delay'], s['repeat'], s['end'])
        self._sra_refresh()

    def sra_state(self):
        """Clocks of the FSRA colors, to be recorded in the savestates."""
        return {m: dict(h) for m, h in self.sra_h.items()}

    def _sra_diffuse(self, m):
        """Couleur diffuse (r, v, b, a) de l'entree `m` a l'instant de son horloge (FldObject.sra_func : cles voisines, fraction bornee a [0, 1])."""
        a, b, f = _interp(self.sra[m]['keys'], self.sra_h[m]['time']); k = self._sra_keys[m]
        return k[a] if a == b or f == 0.0 else k[a] + (k[b] - k[a]) * f

    def _sra_refresh(self, advance=False):
        """One frame of the FSRA colors (FldObject.update_sra): only the entries without an event, or whose event is running, act (`advance`: their clock first advances by one game frame);
        the others leave the original color. A range covered by several entries takes the last one."""
        new = {}
        for m, h in self.sra_h.items():
            e = self.sra[m]['event']
            if e >= 1 and e != self.event: continue
            if advance: _advance(h)
            new[m] = self._sra_diffuse(m)
        changed = [m for m in set(new) | set(self.sra_col) if m not in new or m not in self.sra_col or not np.array_equal(new[m], self.sra_col[m])]
        self.sra_col = new; owners = set()
        for key, d in {(k, d) for m in changed for k, d, n, a in self.sra_spans[m]}:
            on = [m for m in self.sra_cover[(key, d)] if m in new]; n, a = self.sra_info[(key, d)]
            if on: dm = new[on[-1]]; self.fac[(key, d)] = np.array((dm[0], dm[1], dm[2], dm[3] / a), np.float32)
            else: self.fac.pop((key, d), None)
            if (key, d) in self.sra_var: owners.add(self.sra_var[(key, d)]); continue
            f = self.fac.get((key, d)); base = self.col0[key][d:d + n]
            self._array_copy(self.cur_col, self.col0, key)[d:d + n] = base if f is None else base * f; self.dirty_col.add(key)
        for i in owners: self._place(i)

    def _origin(self, i):
        r = self._o64.get(i)
        if r is None:
            o = self.objs[i]; r = self._o64[i] = (np.array(o['pos'], np.float64), np.array(o['rot'], np.float64), np.array(o['scl'], np.float64))
        return r

    def _motion_keys(self, word):
        """Positions, rotations and scales of a movement's keys, as (n, 3) arrays."""
        r = self._keys.get(id(word))
        if r is None or r[0] is not word:                                           # (identity is checked: a freed number could be reused)
            ks = word['keys']; r = self._keys[id(word)] = (word,) + tuple(np.array([k[j] for k in ks], np.float64) for j in (1, 2, 3))
        return r[1:]

    def _rot(self, rot):
        k = (float(rot[0]), float(rot[1]), float(rot[2])); m = self._emat.get(k)
        if m is None:
            if len(self._emat) > 20000: self._emat.clear()
            m = self._emat[k] = euler_mat(*k)
        return m

    def _matrix(self, i):
        if i not in self._inv:
            o = self.objs[i]; S = np.diag(o['scl']).astype(np.float64)
            try: A = np.linalg.inv(euler_mat(*o['rot']) @ S)
            except np.linalg.LinAlgError: A = np.eye(3)
            self._inv[i] = A
        return self._inv[i]

    def _pose(self, i, st):
        """Position, rotation and scale of object i's transform: its original ones, the engine's position / rotation orders, plus its movement in progress. -> (pos, rot, scl, movement)"""
        pos0, rot0, scl0 = self._origin(i); pos, rot, scl = pos0, rot0, scl0
        if st['pos'] is not None: pos = np.array(st['pos'], np.float64)
        if st['rot'] is not None: rot = np.array([st['rot'][0], st['rot'][1], 0.0], np.float64)
        word = st['motion']; t = st.get('motion_time', st['time'])                                  # (state from an old version: a single clock)
        if word is not None and word['keys']:
            a, b, f = _interp(word['keys'], t); cp, cr, cs = self._motion_keys(word)
            dp = cp[a] if a == b or f == 0.0 else cp[a] * (1 - f) + cp[b] * f
            if word['flag'] & 4: pos = pos + self._rot(rot) @ (scl * dp)                      # common movement (FldObject.c_pmv_func): the displacement is read in the object's frame, MultiplyPoint(TRS(position, rotateXZY(rotation), scale)) of the object before the movement (a drawer that slides out of ITS piece of furniture, whatever its heading)
            else: pos = pos + dp                                                              # ordinary movement (FldObject.pmv_func): the displacement is added as is
            rot = rot + (cr[a] if a == b or f == 0.0 else cr[a] * (1 - f) + cr[b] * f)
            scl = scl * (cs[a] if a == b or f == 0.0 else cs[a] * (1 - f) + cs[b] * f)
        return pos, rot, scl, word

    def display_position(self, i):
        """FldObject.GetMapObjDispPos: the world position of object i's transform as displayed (movement included); None when FldObject.GetMapObjPtr finds no object (the game then answers Vector3.zero)."""
        if not self.reachable(i): return None
        return tuple(float(x) for x in self._pose(i, self._st(i))[0])

    def rider_position(self, i):
        """DQ V, NativeManager.Update while cmd_fld_etc's kept value is 0 (map dkb3cev, the mine cart ride): where the first character stands on map object i (38, the cart), i.e. its
        transform's position. While the cart leans (its up vector has a z part: z = up.z x 0.3 >= 0.0001) the character is moved by (up.x x 0.3, up.y x 0.3 x z / 0.212, z), then by the cart's
        forward vector x z x 0.15 / 0.212. None: no such object on the map."""
        if not self.valid(i): return None
        pos, rot, scl, word = self._pose(i, self._st(i)); R = self._rot(rot)
        up, fw = R[:, 1], R[:, 2]; z = float(up[2]) * RIDER_UP
        p = np.array(pos, np.float64)
        if z >= 1e-4: p = p + np.array([up[0] * RIDER_UP, up[1] * RIDER_UP * z / RIDER_SLOPE, z]) + fw * (z * RIDER_FORWARD / RIDER_SLOPE)
        return tuple(float(x) for x in p)

    def _place(self, i):
        o = self.objs[i]; st = self._st(i)
        base = [(None, self.spans.get(i, []), self.imgobj.get(i))]
        for m in self.var_of.get(i, []): base.append((m, self.var[(i, m)]['spans'], self.var[(i, m)]['images']))
        pos0, rot0, scl0 = self._origin(i)
        pos, rot, scl, word = self._pose(i, st)
        panel = self.bill.get(i) if self.bill_ok else None
        identity = st['pos'] is None and st['rot'] is None and word is None and panel is None       # the model stays at its original place
        if not identity:
            R = self._rot(rot) if panel is None else self._rb[32 if panel & 32 else 4] @ self._rot(rot - rot0)       # panel: the orientation comes from the camera (the rest of the movement is added to it)
            T = R @ (scl[:, None] * self._matrix(i))                                    # original world -> current world: (v - pos0) -> T, then + pos  (= R . diag(scl) . inv(R0 . diag(scl0)))
        for m, spans, frames in base:
            alive = (m is None and st['model'] == o['model']) or (m is not None and st['model'] == m)
            alive = alive and not st['off'] and st['alpha'] > 0 and i not in self.tbl_hidden
            for k, (key, d, n) in enumerate(spans):
                img = frames[k] if frames else None
                if not alive: v = np.zeros((n, 3), np.float32)
                else:
                    src, uv, col = self._src_seq(key, d, n, img, st, o.get('flag', 0))
                    v = src if identity else ((src.astype(np.float64) - pos0) @ T.T + pos).astype(np.float32)
                    if img is not None:                                                  # UV and colors that change from one frame of the sequence to the next
                        if img['uv'] is not None: self._array_copy(self.cur_uv, self.uv0, key)[d:d + n] = self.uv0[key][d:d + n] if uv is None else uv; self.dirty_uv.add(key)
                        if img['col'] is not None:
                            cc = self.col0[key][d:d + n] if col is None else col; f = self.fac.get((key, d))
                            self._array_copy(self.cur_col, self.col0, key)[d:d + n] = cc if f is None else cc * f; self.dirty_col.add(key)
                self.cur[key][d:d + n] = v; self.dirty.add(key)

    def _sequence_keys(self, seq, obj_flag):
        """`sequence_keys`, kept per sequence and LOOP flag."""
        loop = obj_flag & FLD_OBJ_FLAG_LOOP; k = (id(seq), loop); r = self._seq_keys.get(k)
        if r is None or r[0] is not seq: r = self._seq_keys[k] = (seq, sequence_keys(seq, loop))
        return r[1]

    def _src_seq(self, key, d, n, img, st, obj_flag=0):
        """(vertices, UVs, colors) of a sub-mesh: original (UV and colors None), or interpolated by the mesh sequence in progress (FldObject.seq_build_mesh: between the frames
        of the two keys around the current frame; a key's value is the model's child number)."""
        seq = st['sequence']; ks = self._sequence_keys(seq, obj_flag) if seq is not None else None
        if not ks or img is None: return self.orig[key][d:d + n], None, None
        a, b, f = _interp(ks, st.get('sequence_time', st['time'])); n_img = len(img['pos'])
        va = min(max(ks[a][1], 0), n_img - 1); vb = min(max(ks[b][1], 0), n_img - 1)
        mix = lambda x: None if x is None else (x[va] if va == vb or f == 0.0 else x[va] * (1 - f) + x[vb] * f)
        return mix(img['pos']), mix(img['uv']), mix(img['col'])


class MapPalettes:
    """Animated palettes of the map (FldObject.update_plp): each animation (FPAM) chains its keys; a key's duration is in 1/60 s, counted in steps of 2 per game frame.
    The surfaces concerned ('pam' texture groups, see Data.game_map) take the texture of the current key. Event-linked animation (number >= 1): frame 0 as long as the event is not in progress."""

    def __init__(self, c):
        self.defs = c.get('pamdef', {})
        self.pams = [{'frame': p['frame'], 'key': p['key'], 'durations': p['durations']} for p in c.get('pam', [])]

    def tick(self):
        """One game frame."""
        for p in self.pams:
            d = p['durations']
            if not d: continue
            p['frame'] += STEP
            if p['frame'] - d[min(p['key'], len(d) - 1)] >= 0:
                p['frame'] -= d[min(p['key'], len(d) - 1)]; p['key'] = 0 if len(d) <= p['key'] + 1 else p['key'] + 1

    def image(self, key, event_code=0):
        """Number of the current frame (texture) of group `key`."""
        dd = self.defs[key]
        if dd['event'] >= 1 and dd['event'] != event_code: return 0
        p = self.pams[dd['pam']]
        return min(max(p['key'], 0), len(dd['images']) - 1)

    def start_event(self, no):
        """Event animation `no` started (FldObject.SetEventAnimation): the palettes tied to that event restart from frame 0 of their clock (FLD_PAM_DATA._cur_frame = 0)."""
        for dd in self.defs.values():
            if dd['event'] == no and 0 <= dd['pam'] < len(self.pams): self.pams[dd['pam']]['frame'] = 0

    def state(self): return [(p['frame'], p['key']) for p in self.pams]

    def select_language(self, state):
        for p, (f, k) in zip(self.pams, state): p['frame'] = f; p['key'] = k
