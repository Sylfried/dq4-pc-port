"""Animated 3D models of Unity (FbxObject: NativeManager.cmd_fbx_load = packet 31, cmd_fbx = packet 32).
The engine loads a model "fbx/c<number>" (Resources prefab: skinned mesh + "legacy"-style Animation component), places it (world position / rotation / scale), colors it
(Material.color of all its materials), starts its animations ("Take 001"...) and shows or hides it. Here: the data extracted once from the data pack (`Data.fbx_model`),
the evaluation of the animation curves (AnimationCurve Hermite interpolation), bone posing, skinning (each vertex follows its bone) and a player that reproduces Animation.Play / PlayQueued / CrossFade.
Everything is in Unity world coordinates (left-handed), like the rest of the viewer."""
import math
import numpy as np

ENGINE_FPS = 30.0            # the engine counts in frames of 1/30 s; Unity's animation advances in seconds (the duration of the dragon's "Take 001", 21.98 s, equals the 659 frames the engine waits before "Take 002")
ANIM_FADE = 0.3             # FbxObject.m_blend_time: duration of the cross-fade (Animation.CrossFade) when the previous animation is a loop
LOOP = 2                     # WrapMode.Loop


def quat_mat(q):
    """Rotation matrices (n, 3, 3) of quaternions (n, 4) x y z w (Unity's formula)."""
    q = np.atleast_2d(np.asarray(q, float)); n = np.linalg.norm(q, axis=1, keepdims=True); q = q / np.where(n > 0, n, 1.0)
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    R = np.empty((len(q), 3, 3))
    R[:, 0, 0] = 1 - 2 * (y * y + z * z); R[:, 0, 1] = 2 * (x * y - z * w); R[:, 0, 2] = 2 * (x * z + y * w)
    R[:, 1, 0] = 2 * (x * y + z * w); R[:, 1, 1] = 1 - 2 * (x * x + z * z); R[:, 1, 2] = 2 * (y * z - x * w)
    R[:, 2, 0] = 2 * (x * z - y * w); R[:, 2, 1] = 2 * (y * z + x * w); R[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def rot_euler(ex, ey, ez):
    """Quaternion.Euler (degrees): rotation about z, then x, then y (left-handed), like `window.rot_unity`."""
    cx, sx, cy, sy, cz, sz = (math.cos(math.radians(ex)), math.sin(math.radians(ex)), math.cos(math.radians(ey)), math.sin(math.radians(ey)), math.cos(math.radians(ez)), math.sin(math.radians(ez)))
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]); Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]); Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def object_matrix(pos, euler, scale_factor):
    """Transform.position / rotation (Quaternion.Euler) / localScale of an object without a parent -> 4x4 object -> world matrix."""
    M = np.eye(4); M[:3, :3] = rot_euler(*euler) @ np.diag(scale_factor); M[:3, 3] = pos
    return M


class Curve:
    """AnimationCurve (keys: time, value, in-slope, out-slope): cubic Hermite interpolation; an infinite slope = step."""
    def __init__(self, t, v, ent, sor):
        self.t = np.asarray(t, float); self.v = np.asarray(v, float); self.ent = np.asarray(ent, float); self.sor = np.asarray(sor, float)

    def value(self, x):
        t = self.t
        if len(t) == 1 or x <= t[0]: return self.v[0]
        if x >= t[-1]: return self.v[-1]
        i = int(np.searchsorted(t, x, side='right')) - 1
        dt = t[i + 1] - t[i]
        if dt <= 0: return self.v[i + 1]
        s = (x - t[i]) / dt
        m0, m1 = self.sor[i], self.ent[i + 1]
        if not (np.all(np.isfinite(m0)) and np.all(np.isfinite(m1))): return self.v[i]
        s2 = s * s; s3 = s2 * s
        return (2 * s3 - 3 * s2 + 1) * self.v[i] + (s3 - 2 * s2 + s) * dt * m0 + (-2 * s3 + 3 * s2) * self.v[i + 1] + (s3 - s2) * dt * m1


class FbxModel:
    """A model (data of `Data.fbx_model`): bone hierarchy, meshes (skinned or rigid), groups of triangles with one texture each, animations."""
    def __init__(self, d):
        self.d = d
        self.parent = list(d['parent']); self.n_t = len(self.parent)
        self.p0 = np.asarray(d['pos'], float); self.q0 = np.asarray(d['rot'], float); self.s0 = np.asarray(d['scl'], float)
        self.names = d['names']
        self.v = np.asarray(d['v'], np.float32); self.uv = np.asarray(d['uv'], np.float32)
        self.bi = np.asarray(d['bi'], np.int64).reshape(len(self.v), -1); self.bw = np.asarray(d['bw'], np.float32).reshape(len(self.v), -1)
        self.bind = np.asarray(d['bind'], float); self.os = np.asarray(d['bones'], np.int64)
        self.tri_indices = np.asarray(d['tri'], np.int64).reshape(-1, 3)
        self.groups = [(g['tex'], np.asarray(g['tri'], np.int64).reshape(-1, 3)) for g in d['groups']] if d.get('groups') else [(d['tex'], self.tri_indices)]          # (texture, triangles): one texture per material; previous cache: a single one
        self.tex = self.groups[0][0]
        raw = 'uv0' in d                                                  # (raw UVs + each material's texture placement, animated by the clips; before: UVs already placed)
        self.uv0 = np.asarray(d['uv0'] if raw else d['uv'], np.float32)
        self.materials0 = [(g.get('node', -1), g.get('mat', 0), tuple(g.get('col', (1.0, 1.0, 1.0, 1.0))), tuple(g['st']) if raw and 'st' in g else (1.0, 1.0, 0.0, 0.0)) for g in (d.get('groups') or [{}])]          # per group: renderer node, material slot, _Color, _MainTex scale x y / offset x y
        self.effect = d.get('shader', 'Custom/ImdChara') == 'Custom/Effect0'          # Effect0 (battle attacks): transparent, no culling or depth write; otherwise ImdChara (opaque scenery)
        self.vh = np.c_[self.v.astype(float), np.ones(len(self.v))]
        self.clips = {}
        for name_str, c in d['clips'].items():
            mc = {}                                                        # (group, 'col' / 'st', channel) -> Curve: the clip's material curves, on the groups of that renderer and slot
            for node, slot, prop, ch, t, v, ent, sor in c.get('mcurves', ()):
                for gi, (gn, gm, _, _) in enumerate(self.materials0):
                    if gn == node and slot in (gm, -1): mc[(gi, prop, ch)] = Curve(t, v, ent, sor)          # (slot -1: a renderer property, on all its materials)
            self.clips[name_str] = {'dur': float(c['dur']), 'wrap': int(c['wrap']), 'curves': [(i, kind, Curve(t, v, ent, sor)) for i, kind, t, v, ent, sor in c['curves']], 'mcurves': mc}

    def local(self, poses):
        """Local pose of each transform: rest, replaced by the animation curves. `poses` = [(clip name, time in seconds, weight)] (weights sum to 1: cross-fade)."""
        p = self.p0.copy(); q = self.q0.copy(); s = self.s0.copy()
        poses = [x for x in poses if x[0] in self.clips]
        if not poses: return p, q, s
        wtot = sum(w for _, _, w in poses) or 1.0
        rest_pose = {'pos': self.p0, 'rot': self.q0, 'scl': self.s0}; targets = {'pos': p, 'rot': q, 'scl': s}
        vals = []                                                      # a {(bone, kind): value} table per clip
        for name_str, t, w in poses: vals.append({(i, kind): cb.value(t) for i, kind, cb in self.clips[name_str]['curves']})
        for lookup_key in set().union(*[v.keys() for v in vals]):
            i, kind = lookup_key
            terms = [(w, np.asarray(v.get(lookup_key, rest_pose[kind][i]), float)) for (_, _, w), v in zip(poses, vals)]
            if kind == 'rot' and len(terms) > 1:                  # q and -q are the same rotation: the blend stays on the same side of the sphere (shortest path), otherwise the average cancels out or makes a half turn
                ref = terms[0][1]; terms = [(w, x if float(np.dot(x, ref)) >= 0 else -x) for w, x in terms]
            targets[kind][i] = sum(w * x for w, x in terms) / wtot
        return p, q, s

    def materials(self, poses, color=None):
        """[(color rgba, texture placement (scale x, y, offset x, y))] of each group at these poses. Base: the material's _Color, or the color the engine gave to all the materials (packet 32,
        FbxObject.SetColor); the clip then writes the channels it animates (the legacy Animation samples after the scripts: its values win), like the texture placement (UV scrolling of the tornadoes)."""
        poses = [x for x in poses if x[0] in self.clips]; wtot = sum(w for _, _, w in poses) or 1.0
        out = []
        for gi, (_, _, col0, st0) in enumerate(self.materials0):
            base = {'col': list(color) if color is not None else list(col0), 'st': list(st0)}
            for prop in ('col', 'st'):
                for ch in range(4):
                    terms = [(w, self.clips[n]['mcurves'].get((gi, prop, ch))) for n, t, w in poses]
                    if not any(cb is not None for _, cb in terms): continue
                    base[prop][ch] = sum(w * (float(cb.value(t)[0]) if cb is not None else base[prop][ch]) for (w, cb), (_, t, _) in zip(terms, poses)) / wtot
            out.append((tuple(base['col']), tuple(base['st'])))
        return out

    def vertices(self, M_obj, poses):
        """World positions (n, 3) of the skinned mesh's vertices; M_obj = world matrix of the model's root (position, rotation, scale given by the engine)."""
        p, q, s = self.local(poses)
        R = quat_mat(q)
        W = np.empty((self.n_t, 4, 4))
        for i in range(self.n_t):
            L = np.eye(4); L[:3, :3] = R[i] * s[i][None, :]; L[:3, 3] = p[i]
            W[i] = M_obj if self.parent[i] < 0 else (W[self.parent[i]] @ L)          # the root is the object the engine places (FbxObject: Transform.position / rotation / localScale): its own place in the prefab is replaced (Gigaglace c13: 20 units up)
        BM = W[self.os] @ self.bind                                    # skinning matrix of each bone: bone in the world x bind pose
        out = np.zeros((len(self.v), 3))
        for k in range(self.bi.shape[1]):
            w = self.bw[:, k]
            if not np.any(w): continue
            out += w[:, None] * np.einsum('nij,nj->ni', BM[self.bi[:, k]], self.vh)[:, :3]
        return out.astype(np.float32)


class ScreenOverlay:
    """A model of the interface camera's layer (data.Data._screen_overlay: c2000, the dream filter): a textured plane seen from above by the orthographic interface camera, so a picture over
    the screen; drawn by the window (Game._draw_screen_models), not with the scene's models."""
    overlay = True; effect = None

    def __init__(self, d):
        self.size = tuple(d['size']); self.tex = d['tex']; self.col = tuple(d['col']); self.st = tuple(d['st']); self.clips = {}
        a = self.tex[..., 3] < 255; rows, cols = np.where(a.any(1))[0], np.where(a.any(0))[0]; h, w = a.shape
        self.area_uv = (cols[0] / w, 1 - (rows[-1] + 1) / h, (cols[-1] + 1) / w, 1 - rows[0] / h) if len(rows) else (0.0, 0.0, 1.0, 1.0)          # (the effect's area, where the picture is not opaque)

    def plane(self, scale=None):
        """(width, height) of the plane in interface units: Unity's built-in plane is 10 x 10, times the engine's scale (packet 32) or the prefab's."""
        sx, sz = (self.size[0] / 10.0, self.size[1] / 10.0) if scale is None else (float(scale[0]), float(scale[2]))
        return 10.0 * sx, 10.0 * sz

    def area(self, scale=None, pos=(0.0, 0.0, 0.0)):
        """The effect's area (the part of the picture that is not opaque; the dream: u 0.25 to 0.75, v 0.28 to 0.72, 450 x 437.5 units): (width, height) in units, and the position to give
        `window` so that the window is centered on it."""
        pw, ph = self.plane(scale); u0, v0, u1, v1 = self.area_uv
        return ((u1 - u0) * pw, (v1 - v0) * ph), (pos[0] - ((u0 + u1) / 2 - 0.5) * pw, pos[1], pos[2] - ((v0 + v1) / 2 - 0.5) * ph)

    def window(self, scale=None, pos=(0.0, 0.0, 0.0), column=(450.0, 800.0)):
        """(u0, v0, u1, v1): the part of the texture the phone's column shows (the interface camera frames the 450 x 800 column; the plane is centered on the model's position, x to the right and z up).
        `scale`: the one the engine gave (packet 32), otherwise the prefab's (FbxObject never resets localScale). Unity's built-in plane has u = 0.5 - x / 10 and v = 0.5 - z / 10; the rotation (0, 180, 0)
        of cmd_fbx_load turns both back, so u and v grow toward the right and the top of the screen."""
        sx, sz = (self.size[0] / 10.0, self.size[1] / 10.0) if scale is None else (float(scale[0]), float(scale[2]))
        u = lambda x: 0.5 + (x - pos[0]) / (10.0 * sx); v = lambda z: 0.5 + (z - pos[2]) / (10.0 * sz)
        hw, hh = column[0] / 2.0, column[1] / 2.0
        return u(-hw), v(-hh), u(hw), v(hh)


class AnimPlayer:
    """Animation of an object (UnityEngine.Animation, what FbxObject.PlayAnimation does) driven by the engine's frames:
    * no animation started: model in its rest pose;
    * Play (forced, or nothing is playing): the clip restarts from the beginning; otherwise, if the current animation is a loop (m_mode = Loop): CrossFade (0.3 s cross-fade); otherwise PlayQueued (the clip waits for the end of the current one);
    * clip time: Once / Default / ClampForever = stuck on the last frame, Loop = modulo the duration."""
    def __init__(self, clips):
        self.clips = clips                       # {name: {'dur', 'wrap'}}
        self.cur = None                          # [name, start frame (float)]
        self.file = []                           # queued clips (PlayQueued)
        self.fade = None                        # (previous clip [name, start], cross-fade start frame)
        self.mode = 0                            # wrapMode of the last clip started (FbxObject.m_mode)

    @staticmethod
    def name_str(seq): return 'Take %03d' % (seq + 1)

    def _finished(self, c, image):
        cl = self.clips.get(c[0])
        return cl is not None and cl['wrap'] != LOOP and (image - c[1]) / ENGINE_FPS >= cl['dur']

    def play(self, seq, force, image):
        name_str = self.name_str(seq)
        if name_str not in self.clips: return
        self.do_update(image)
        played = self.cur is not None and not self._finished(self.cur, image)
        if force or not played:
            self.cur = [name_str, float(image)]; self.file = []; self.fade = None
        elif self.mode == LOOP:
            self.fade = (list(self.cur), float(image)); self.cur = [name_str, float(image)]; self.file = []
        else:
            self.file.append(name_str)
        self.mode = self.clips[name_str]['wrap']

    def do_update(self, image):
        """Moves on to the queued clips when the current one is finished (the next one starts exactly at the end of the previous one)."""
        while self.cur is not None and self.file and self._finished(self.cur, image):
            end = self.cur[1] + self.clips[self.cur[0]]['dur'] * ENGINE_FPS
            self.cur = [self.file.pop(0), end]
        if self.fade is not None and (image - self.fade[1]) / ENGINE_FPS >= ANIM_FADE: self.fade = None

    def poses(self, image):
        """[(clip, time in seconds, weight)] at the engine's (floating-point) frame."""
        self.do_update(image)
        if self.cur is None: return []
        def clock(c):
            cl = self.clips[c[0]]; t = max(0.0, (image - c[1]) / ENGINE_FPS)
            if cl['wrap'] == LOOP and cl['dur'] > 0: t %= cl['dur']
            return min(t, cl['dur'])
        if self.fade is not None and self.fade[0][0] in self.clips:
            w = min(1.0, max(0.0, (image - self.fade[1]) / ENGINE_FPS / ANIM_FADE))
            return [(self.fade[0][0], clock(self.fade[0]), 1.0 - w), (self.cur[0], clock(self.cur), w)]
        return [(self.cur[0], clock(self.cur), 1.0)]
