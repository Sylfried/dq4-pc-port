"""3D models of battle attacks: the engine requests fbx (packet 31) during battle actions (c103: Matoeil, spell Reflexion; c217: Psaro, Aamon) and the viewer
drew none (the decoder rejected the Custom/Effect0 shader, and `_paint_fbx` was only called in the town branch).

    python3 tests/test_fbx_battle.py                                  (DQ_APK=<folder of the patched APKs> for the part on real data)

  1. a model with the Custom/Effect0 shader is recognized (`FbxModel.effect`), a model without a "shader" field (old cache) stays opaque;
  2. `_paint_fbx(e)` draws only the opaque models (town: the dragon of the title screen), `_paint_fbx(e, True)` only those of Effect0, and those without culling (Cull Off);
  3. battle branch of `_draw_scene`: the Effect0 models come after the monsters (queues 2100 to 2200) and before DssaCharaTransparent (shader 3, queue 3850), then as a fallback after the loop;
  3b. animation end (`Engine._finish_fbx_anims`): message to the engine when the non-looping clip is finished, none while it plays or loops;
  4. (real data) c103 and c217 decode as Effect0, c1018 (the dragon) stays opaque; the material's texture offset (c103: 0.16 in v) is applied to the UVs.
"""
import os, re, sys, tempfile, shutil, types, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq4_pc)
import pyglet
pyglet.options['shadow_window'] = False
from dq4_pc.world import fbx as FX
from dq4_pc.window import field as FI
from dq4_pc.window import game as GA

APK = os.environ.get('DQ_APK', '')
PACK = os.path.join(APK, 'split_UnityDataAssetPack.apk')


def tiny(shader=None):
    """Minimal model data (one bone, one triangle, 2 x 2 texture), in the shape of `Data.fbx_model`."""
    d = {'names': ['Bone01'], 'parent': [-1], 'pos': [(0, 0, 0)], 'rot': [(0, 0, 0, 1)], 'scl': [(1, 1, 1)],
         'v': np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32), 'uv': np.array([[0, 0], [1, 0], [0, 1]], np.float32),
         'bi': np.zeros((3, 1), np.int64), 'bw': np.ones((3, 1), np.float32), 'tri': np.array([[0, 1, 2]]), 'bind': np.eye(4)[None], 'bones': [0],
         'tex': np.full((2, 2, 4), 255, np.uint8), 'clips': {}}
    if shader: d['shader'] = shader
    return d


class Materials(unittest.TestCase):
    """the clips animate the materials (color, texture placement); the engine places the model's root."""
    def model(self, mcurves=(), color=(1.0, 1.0, 1.0, 1.0)):
        d = tiny(); d['uv0'] = d['uv']; d['groups'] = [{'tex': d['tex'], 'tri': d['tri'], 'node': 0, 'mat': 0, 'col': color, 'st': (2.0, 1.0, 0.5, 0.0)}]
        d['clips'] = {'Take 001': {'dur': 1.0, 'wrap': 0, 'curves': [], 'mcurves': list(mcurves)}}
        return FX.FbxModel(d)

    def test_targets(self):
        from dq4_pc.world.data import material_target as T
        self.assertEqual(T(137, 'material._Color.a'), (-1, 'col', 3)); self.assertEqual(T(23, 'material._Color.r'), (-1, 'col', 0))
        self.assertEqual(T(21, '_Color.g'), (0, 'col', 1)); self.assertEqual(T(21, '[2]._Color.b'), (2, 'col', 2))
        self.assertEqual(T(21, '_MainTex.offset.y'), (0, 'st', 3)); self.assertEqual(T(21, '[1]._MainTex.scale.x'), (1, 'st', 0))
        self.assertIsNone(T(21, '_TintColor.a')); self.assertIsNone(T(4, 'm_LocalPosition.x')); self.assertIsNone(T(137, 'm_Enabled'))

    def test_base_engine_and_clip(self):
        m = self.model(color=(1.0, 0.5, 1.0, 0.8))
        self.assertEqual(m.materials([]), [((1.0, 0.5, 1.0, 0.8), (2.0, 1.0, 0.5, 0.0))])                     # the material's own color and placement
        self.assertEqual(m.materials([], (0.2, 0.2, 0.2, 1.0))[0][0], (0.2, 0.2, 0.2, 1.0))                   # the engine's color replaces it (FbxObject.SetColor)
        m = self.model([(0, -1, 'col', 3, [0.0, 1.0], [[1.0], [0.0]], [[0.0], [0.0]], [[0.0], [0.0]]), (0, 0, 'st', 3, [0.0, 1.0], [[0.0], [-1.0]], [[-1.0], [-1.0]], [[-1.0], [-1.0]])])
        col, st = m.materials([('Take 001', 0.5, 1.0)], (0.2, 0.2, 0.2, 1.0))[0]
        self.assertEqual(col[:3], (0.2, 0.2, 0.2)); self.assertAlmostEqual(col[3], 0.5)                     # the clip writes only the channels it animates
        self.assertAlmostEqual(st[3], -0.5); self.assertEqual(st[:3], (2.0, 1.0, 0.5))

    def test_root_placed_by_the_engine(self):
        d = tiny(); d['pos'] = [(0, 20, 0)]; m = FX.FbxModel(d)
        M = np.eye(4); M[:3, 3] = (1, 2, 3)
        self.assertTrue(np.allclose(m.vertices(M, [])[0], (1, 2, 3)))                                       # (not 20 units above)

    def test_old_cache_without_materials(self):
        m = FX.FbxModel(tiny()); self.assertEqual(m.materials([]), [((1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 0.0, 0.0))])


class FakeGL:
    GL_CULL_FACE, GL_BACK, GL_CW, GL_CCW = 'CULL', 'BACK', 'CW', 'CCW'
    def __init__(self): self.calls = []
    def glEnable(self, x): self.calls.append(('enable', x))
    def glDisable(self, x): self.calls.append(('disable', x))
    def glCullFace(self, x): self.calls.append(('cullface', x))
    def glFrontFace(self, x): self.calls.append(('frontface', x))


class Shader(unittest.TestCase):
    def test_effect_flag(self):
        self.assertTrue(FX.FbxModel(tiny('Custom/Effect0')).effect)
        self.assertFalse(FX.FbxModel(tiny('Custom/ImdChara')).effect)
        self.assertFalse(FX.FbxModel(tiny()).effect)                    # (old cache: without a "shader" field, the dragon)


class AnimationEnd(unittest.TestCase):
    """End of 3D model animation: NativeManager.Update sends the engine (message 1, 0x1000 | slot) when FbxObject.IsEndAnimation; without it the engine never hides or frees the effect (the ice spell stays on screen)."""
    CLIPS = {'Take 001': {'dur': 1.0, 'wrap': 1}, 'Take 002': {'dur': 1.0, 'wrap': FX.LOOP}}

    def engine(self, clips, anim, frames):
        from dq4_pc.core import engine as EN
        buf = bytearray(b'\xff\xff\xff\xff' + bytes(60)); head = bytearray(16)
        core = types.SimpleNamespace(inp=0, mem=lambda a, n: bytes(head[a - 0x1000:a - 0x1000 + n]) if a >= 0x1000 else bytes(buf[a:a + n]), mem_w=lambda a, b: buf.__setitem__(slice(a, a + len(b)), b))
        head[:8] = (0).to_bytes(8, 'little')                                               # [L + MESSAGE_BUFFER] = pointeur vers buf (0)
        e = EN.Engine.__new__(EN.Engine); e.L = 0x1000 - EN.MESSAGE_BUFFER; e.core = core; e.frames = frames; e._messages_sent = False
        e.state = types.SimpleNamespace(fbx={2: {'id': 10, 'anim': anim}}); e.fbx_playing = [2]; e.fbx_clips = (lambda no: clips) if clips != 'absent' else None
        return e, buf

    def messages(self, buf): return [int.from_bytes(buf[i:i + 4], 'little', signed=True) for i in range(0, 16, 4)]

    def test_no_message_while_the_clip_plays_then_one_at_its_end(self):
        e, buf = self.engine(self.CLIPS, [(100, 0, False)], 100 + 29)                      # 29 / 30 s: playback goes on
        e._finish_fbx_anims(); self.assertEqual(e.fbx_playing, [2]); self.assertEqual(self.messages(buf)[0], -1)
        e.frames = 130; e._finish_fbx_anims()                                              # 1 s : fini
        self.assertEqual(e.fbx_playing, []); self.assertEqual(self.messages(buf), [1, 0x1002, -1, 0]); self.assertTrue(e._messages_sent)

    def test_loop_never_ends_and_unknown_model_waits(self):
        e, buf = self.engine(self.CLIPS, [(0, 1, False)], 10000); e._finish_fbx_anims(); self.assertEqual(e.fbx_playing, [2]); self.assertEqual(self.messages(buf)[0], -1)
        e, buf = self.engine(None, [(0, 0, False)], 10000); e._finish_fbx_anims(); self.assertEqual(e.fbx_playing, [2])            # model not read yet: wait
        e, buf = self.engine('absent', [(0, 0, False)], 5); e._finish_fbx_anims(); self.assertEqual(e.fbx_playing, [])              # no provider (no window): immediate end

    def test_freed_model_keeps_its_entry(self):
        e, buf = self.engine(self.CLIPS, [(0, 0, False)], 10000); e.state.fbx.clear(); e._finish_fbx_anims()
        self.assertEqual(e.fbx_playing, [2]); self.assertEqual(self.messages(buf)[0], -1)             # m_model[slot] null: the m_anim_list entry is skipped, not removed


class LoadedTurned(unittest.TestCase):
    """NativeManager.cmd_fbx_load ends with FbxObject.SetRotation(0, 180, 0) (0xD13610); a packet 32 with bit 14 replaces it (the title dragon), the battle spells keep it."""
    def test_packet_31_turns_the_model(self):
        from dq4_pc.core import engine as ENGINE
        e = ENGINE.State(); e.apply([(31, [0, 13], [])], lambda: 'btl_pl_d')
        self.assertEqual(e.fbx[0]['rot'], (0.0, 180.0, 0.0))
        e.apply([(32, [0x2900], [1.5, 1.5, 1.5, 0.0, 3.5, -29.9])], lambda: 'btl_pl_d')            # scale + position, no rotation: the half turn stays
        self.assertEqual(e.fbx[0]['rot'], (0.0, 180.0, 0.0)); self.assertEqual(e.fbx[0]['pos'], (0.0, 3.5, -29.9))
        e.apply([(32, [0x4100], [0.0, 349.45, 0.0])], lambda: 'btl_pl_d')                            # the engine's own rotation replaces it
        self.assertEqual(e.fbx[0]['rot'], (0.0, 349.45, 0.0))


class Groups(unittest.TestCase):
    def test_groups_of_the_model(self):
        d = tiny(); t2 = np.zeros((2, 2, 4), np.uint8)
        d['groups'] = [{'tex': d['tex'], 'tri': np.array([[0, 1, 2]])}, {'tex': t2, 'tri': np.array([[2, 1, 0], [0, 1, 2]])}]
        m = FX.FbxModel(d)
        self.assertEqual([len(t) for _, t in m.groups], [1, 2])
        self.assertIs(m.tex, d['tex'])

    def test_old_cache_is_one_group(self):
        m = FX.FbxModel(tiny()); self.assertEqual(len(m.groups), 1); self.assertEqual(len(m.groups[0][1]), 1)


class Painting(unittest.TestCase):
    def setUp(self):
        self.gl = FakeGL(); self.restore_gl = _paths.set_global('gl', self.gl)
        self.models = {10: FX.FbxModel(tiny('Custom/ImdChara')), 20: FX.FbxModel(tiny('Custom/Effect0'))}
        self.painted = []
        mod = lambda n: {'id': n, 'visible': True, 'pos': (0.0, 0.0, 0.0), 'rot': (0.0, 0.0, 0.0), 'scl': (1.0, 1.0, 1.0), 'col': (1.0, 1.0, 1.0, 1.0), 'anim': []}
        self.e = types.SimpleNamespace(fbx={0: mod(10), 1: mod(20)})
        self.j = types.SimpleNamespace(engine=types.SimpleNamespace(frames=5), alpha=0.0, fbx_player={}, prog={}, smoothing=True, _linked_domain=None,
                                       _fbx_ready=lambda no: {'m': self.models[no], 'groups': [self.group('tex%d' % no, [0, 1, 2], 3)]},
                                       _paint=lambda tex, vl: self.painted.append(tex))

    @staticmethod
    def group(tex, idx, n):
        return {'tex': tex, 'raw': np.zeros((4, 8, 4), np.uint8), 'idx': np.array(idx), 'vl': types.SimpleNamespace(position=np.zeros(3 * n), colors=np.zeros(4 * n), tex_coords=np.zeros(2 * n)), 'n': n}

    def tearDown(self): self.restore_gl()

    def test_one_pass_per_texture_in_order(self):
        """Glace with two textures: one triangle group per texture, drawn in the order of the sub-meshes, with its own vertices and texture size."""
        gs = [self.group('a', [0, 1, 2], 3), self.group('b', [2, 1, 0], 3)]; sizes = []
        self.j._fbx_ready = lambda no: {'m': self.models[no], 'groups': gs}
        self.j._paint = lambda tex, vl: (self.painted.append(tex), sizes.append(tuple(self.j.prog['tsize'])))
        FI.FieldMixin._paint_fbx(self.j, self.e, True)
        self.assertEqual(self.painted, ['a', 'b']); self.assertEqual(sizes, [(8.0, 4.0), (8.0, 4.0)])
        self.assertEqual(gs[0]['vl'].position[:3].tolist(), [0.0, 0.0, 0.0]); self.assertEqual(gs[1]['vl'].position[3:6].tolist(), gs[0]['vl'].position[3:6].tolist())          # (V[idx] : sommets inverses)

    def test_every_group_is_committed_before_its_draw(self):
        """`_paint` rebinds the OpenGL domain (rebind + commit) only if it changed since the last draw; the vertices of a group, written AFTER the draw of the previous group, therefore went out with those of the previous frame
        (pyglet: a written buffer stays "dirty" until the commit). Glace with two groups: at the 1st draw of a re-cast spell, the 2nd group showed at its last pose from the previous cast. The domain must be released before EACH group."""
        gs = [self.group('a', [0, 1, 2], 3), self.group('b', [2, 1, 0], 3)]; seen = []
        self.j._fbx_ready = lambda no: {'m': self.models[no], 'groups': gs}
        def paint(tex, vl): seen.append((tex, self.j._linked_domain)); self.j._linked_domain = 'domaine'          # (like `_paint`: the domain stays bound after a draw)
        self.j._paint = paint; self.j._linked_domain = 'domaine'                                               # (a monster's mesh has just been drawn)
        FI.FieldMixin._paint_fbx(self.j, self.e, True)
        self.assertEqual(seen, [('a', None), ('b', None)])

    def test_opaque_only_by_default(self):
        FI.FieldMixin._paint_fbx(self.j, self.e)
        self.assertEqual(self.painted, ['tex10'])
        self.assertIn(('enable', 'CULL'), self.gl.calls)                # Custom/ImdChara : Cull Back

    def test_effects_only_without_culling(self):
        FI.FieldMixin._paint_fbx(self.j, self.e, True)
        self.assertEqual(self.painted, ['tex20'])
        self.assertNotIn(('enable', 'CULL'), self.gl.calls)             # Custom/Effect0 : Cull Off

    def test_spell_cast_again_restarts_its_animation(self):
        """a re-cast spell reloads its model (new engine dictionary) in the same slot, with a cast list of the same length; the player from the previous time stayed (it played nothing of the new cast) and the model
        was already displayed in its final pose: "faster and faster" with each cast."""
        clip = {'Take 001': {'dur': 2.0, 'wrap': 1, 'curves': []}}
        self.models[20] = FX.FbxModel(dict(tiny('Custom/Effect0'), clips=clip))
        mod = lambda img: {'id': 20, 'visible': True, 'pos': (0.0, 0.0, 0.0), 'rot': (0.0, 0.0, 0.0), 'scl': (1.0, 1.0, 1.0), 'col': (1.0, 1.0, 1.0, 1.0), 'anim': [(img, 0, False)]}
        first = mod(10); self.j.engine.frames = 12; FI.FieldMixin._paint_fbx(self.j, types.SimpleNamespace(fbx={1: first}), True)
        self.assertEqual(self.j.fbx_player[1]['a'].cur, ['Take 001', 10.0])
        self.j.engine.frames = 40; FI.FieldMixin._paint_fbx(self.j, types.SimpleNamespace(fbx={1: first}), True)               # (the rest of the same cast: the player stays, it replays nothing)
        self.assertEqual(self.j.fbx_player[1]['a'].cur, ['Take 001', 10.0])
        # (model freed: `_paint_fbx` is no longer called while no model exists, so the window's player stays in place)
        self.j.engine.frames = 202; FI.FieldMixin._paint_fbx(self.j, types.SimpleNamespace(fbx={1: mod(200)}), True)
        self.assertEqual(self.j.fbx_player[1]['a'].cur, ['Take 001', 200.0])


class BattleBranch(unittest.TestCase):
    def test_effects_between_monsters_and_transparent_character(self):
        src = open(GA.__file__, encoding='utf-8').read(); i = src.index('monster_meshes = self._battle_meshes(e)'); j = src.index('        else:\n            self._M_town = M', i)
        branch = src[i:j]
        loop = branch.index('for tex, tw, th, vl, shader, hd in monster_meshes:')
        inside = branch.index('if fbx_pending and shader == 3: self._paint_fbx(e, True); fbx_pending = False')
        self.assertLess(loop, inside)
        self.assertLess(inside, branch.index('self.prog[\'crisp\'] = 0.0 if hd'))              # before drawing the first mesh of shader 3
        self.assertLess(branch.index('if fbx_pending: self._paint_fbx(e, True)'), branch.index('gl.glDepthMask(gl.GL_TRUE)'))      # fallback: without shader 3, after the loop (depth writing still off)
        self.assertEqual(len(re.findall(r'_paint_fbx\(e\)', src)), 1)                       # the town keeps its previous call (opaque models)


@unittest.skipUnless(os.path.exists(PACK), 'no game data pack (DQ_APK=<folder of the patched APKs>)')
class RealModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.world import data as DO
        cls.cache = tempfile.mkdtemp(prefix='cache_test_fbx_combat_')
        cls.d = DO.Data(PACK, cls.cache, log=lambda *a: None)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.cache, ignore_errors=True)

    def test_battle_models_are_effects(self):
        for no, triangles in ((103, 60), (217, 24)):
            m = FX.FbxModel(self.d.fbx_model(no))
            self.assertTrue(m.effect, no); self.assertEqual(len(m.tri_indices), triangles, no)

    def test_title_dragon_stays_opaque(self):
        self.assertFalse(FX.FbxModel(self.d.fbx_model(1018)).effect)

    def test_texture_offset_applied(self):
        """The c103 material shifts the texture by 0.16 in v (Material.mainTextureOffset): without this the ring sampled a transparent area and was not visible."""
        v = FX.FbxModel(self.d.fbx_model(103)).uv[:, 1]
        self.assertAlmostEqual(float(v.min()), -0.3 + 0.16, delta=0.02); self.assertAlmostEqual(float(v.max()), 0.16, delta=0.02)

    def test_all_combat_models_decode(self):
        """all the fbx that the engine effects request in battle (Glace c10 to c12, Mégaflamme c3, Gigaglace c13 to c15, Tornade c16, Gigalame c20, Explosion magique c42, c609...) decode, as Effect0, with no vertex outside the bones."""
        from dq4_pc.world import data as DO
        for no in DO.FBX_COMBAT:
            m = FX.FbxModel(self.d.fbx_model(no)); self.assertTrue(m.effect, no)
            self.assertTrue(len(m.groups) >= 1 and sum(len(t) for _, t in m.groups) == len(m.tri_indices) > 0, no)
            self.assertLess(int(m.tri_indices.max()), len(m.v), no); self.assertLess(int(m.bi.max()), len(m.os), no)
            self.assertTrue(np.isfinite(m.vertices(np.eye(4), [])).all(), no)

    def test_ice_has_two_textures_and_keeps_its_order(self):
        for no in (10, 11, 12):
            m = FX.FbxModel(self.d.fbx_model(no)); self.assertGreaterEqual(len(m.groups), 2, no)          # one group per material slot, two different textures (12578 and 12635)
            self.assertEqual(len({t.tobytes() for t, _ in m.groups}), 2, no)

    # ----: material curves of the clips, root placed by the engine, clip length
    def test_clip_length_counts_the_material_curves(self):
        """The length of a clip is the last key of ALL its curves: Gigaglace c13 1.667 s (its bones stop at 1.267), Réflexion c103 0.967 s (no bone curve: it ended at once before)."""
        self.assertAlmostEqual(FX.FbxModel(self.d.fbx_model(13)).clips['Take 001']['dur'], 1.6667, 3)
        self.assertAlmostEqual(FX.FbxModel(self.d.fbx_model(103)).clips['Take 001']['dur'], 0.9667, 3)

    def test_megaflamme_ball_fades_out(self):
        """Mégaflamme c3: the clip fades the ball's three materials (a renderer property, on all its slots) from 0.75 to 0.01 when it lands; before, it stayed on screen after the explosion."""
        m = FX.FbxModel(self.d.fbx_model(3)); self.assertEqual(len(m.groups), 3)
        for t, alpha in ((0.0, 0.75), (0.5, 0.75), (0.8, 0.01)):
            for col, _ in m.materials([('Take 001', t, 1.0)]): self.assertAlmostEqual(col[3], alpha, 2)

    def lens_angles(self):
        """Mégaflamme c3, placed as in battle (turned by the engine, scale 1.5): angle in degrees between the ball's flat axis (its two domes) and the battle camera's axis, along the clip."""
        m = FX.FbxModel(self.d.fbx_model(3))
        dome = np.unique(np.concatenate([np.asarray(t).ravel() for _, t in (m.groups[0], m.groups[2])]))
        out = []
        for t in np.arange(0.0, 0.8, 1.0 / 30.0):
            P = m.vertices(FX.object_matrix((0.0, 3.562, -29.875), (0.0, 180.0, 0.0), (1.5, 1.5, 1.5)), [('Take 001', float(t), 1.0)])[dome].astype(float)
            axis = np.linalg.eigh(np.cov((P - P.mean(0)).T))[1][:, 0]                              # thinnest direction of the domes
            out.append(float(np.degrees(np.arccos(min(1.0, abs(axis @ np.array([0.0, 0.0, 1.0])))))))
        return out

    def test_megaflamme_ball_read_as_the_data(self):
        """the ball (a slightly flat sphere and its ring of flames) turns about its locator's axis exactly as the clip says: it tips over and shows its flat side (near 90 degrees from facing the
        camera) several times. On the phone the ball is a little flat there too; the reading in the joint's frame is withdrawn."""
        self.assertGreater(max(self.lens_angles()), 80.0)

    def test_tornado_texture_scrolls(self):
        """Tornade c14: the clip scrolls the texture (offset y -0.025 per 1/60 s) of its first renderer."""
        m = FX.FbxModel(self.d.fbx_model(14))
        a, b = m.materials([('Take 001', 0.0, 1.0)]), m.materials([('Take 001', 0.1, 1.0)])
        self.assertTrue(any(abs((sb[3] - sa[3]) + 0.15) < 0.01 for (_, sa), (_, sb) in zip(a, b)), (a, b))

    def test_gigaglace_root_placed_by_the_engine(self):
        """Gigaglace c13: its root sits 20 units up in the prefab; the engine places the root itself (FbxObject), so the spikes start at the engine's position, not 20 units above it."""
        m = FX.FbxModel(self.d.fbx_model(13)); V = m.vertices(np.eye(4), [('Take 001', 1.0, 1.0)])
        self.assertLess(float(np.median(V[:, 1])), 10.0)

    def test_several_meshes_and_rigid_mesh(self):
        m13 = FX.FbxModel(self.d.fbx_model(13)); self.assertEqual(len(m13.os), 16); self.assertEqual(len(m13.bind), 16)          # Gigaglace : plusieurs maillages skinnes, os bout a bout
        m609 = FX.FbxModel(self.d.fbx_model(609)); self.assertEqual(len(m609.os), 1); self.assertTrue(np.allclose(m609.bind[0], np.eye(4)))          # maillage non skinne : un os rigide, pose de liaison = identite
        self.assertEqual(len(m609.tri_indices), 2)

    def test_combat_models_prepared_in_the_background(self):
        from dq4_pc.world import data as DO
        files = {f for _, _, f in self.d._elements({'maps': [], 'sheets': [], 'monsters': [], 'plans': [], 'effects': []})}
        for no in DO.FBX_COMBAT + (1018,): self.assertIn(DO.FBX_PREFIX + 'c%04d.pkl' % no, files, no)


if __name__ == '__main__':
    unittest.main(verbosity=1)
