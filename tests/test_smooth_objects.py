"""In the town with the 3D boat, the boat moved in jerks: the map objects and the 3D models of the scene move once per engine step (30 Hz) while the characters and the camera
are interpolated between two steps; they are now drawn at the same in-between instant.
  - map objects (field.py `_note_movements` / `_smooth_objects`): the vertices that moved during the step are drawn between their two positions; a vertex that appears, disappears or jumps is not;
  - 3D models (game.py `_interpolate`): position and rotation (shortest way) between the two steps, put back after the drawing."""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq456_pc.window.field import FieldMixin
    from dq456_pc.window import game as G
    from dq456_pc.core import engine as ENGINE
except Exception as ex:          # (pyglet, numpy, unicorn...: the import alone is enough)
    FieldMixin = None; ERROR = ex


class VL:
    def __init__(self, n): self.position = np.zeros(n * 3, np.float32)


def fake(cur):
    f = types.SimpleNamespace(objects=types.SimpleNamespace(cur=cur), ext_map=[])
    f.map_vl = [(None, VL(len(v)), k) for k, v in cur.items()]
    f.obj_shown = {k: v.copy() for k, v in cur.items()}; f.obj_moving = {}
    for name_str in ('_note_movements', '_smooth_objects'): setattr(f, name_str, getattr(FieldMixin, name_str).__get__(f))
    return f


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class MapObjects(unittest.TestCase):
    def test_moving_object_drawn_between_two_steps(self):
        boat = np.array([[0.0, 0.0, 10.0], [1.0, 0.0, 10.0], [0.0, 1.0, 10.0]], np.float32); f = fake({'g': boat.copy()})
        f.objects.cur['g'] = boat + np.array([0.6, 0.0, 0.0], np.float32); f._note_movements({'g'})               # one step: the boat moved 0.6 unit east
        f._smooth_objects(0.5); v = f.map_vl[0][1].position.reshape(-1, 3)
        np.testing.assert_allclose(v, boat + [0.3, 0.0, 0.0], atol=1e-6)
        f._smooth_objects(1.0); np.testing.assert_allclose(f.map_vl[0][1].position.reshape(-1, 3), boat + [0.6, 0.0, 0.0], atol=1e-6)
        f._note_movements(set()); self.assertEqual(f.obj_moving, {})                                                     # it stopped: nothing more to interpolate

    def test_appearing_hidden_and_jumping_vertices_are_not_interpolated(self):
        a = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 5.0], [2.0, 0.0, 2.0]], np.float32); f = fake({'g': a.copy()})
        b = np.array([[3.0, 1.0, 3.0], [0.0, 0.0, 0.0], [40.0, 0.0, 2.0]], np.float32)                     # appears (was hidden: zeros), disappears, jumps 38 units
        f.objects.cur['g'] = b; f._note_movements({'g'}); f._smooth_objects(0.5)
        self.assertNotIn('g', f.obj_moving); np.testing.assert_allclose(f.map_vl[0][1].position.reshape(-1, 3), np.zeros((3, 3)))          # (nothing moving: the step's own upload stands)


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class TurnedPanels(unittest.TestCase):
    """DQ V, breaking a barrel made the other barrels blink once the camera had been turned: the panels facing the camera are re-placed when it turns, but the positions kept from the last step
    (obj_shown) stayed those of the old orientation; the first change in their group (the broken barrel hidden) then saw every other panel as "moved" and drew it between the two orientations."""
    def window(self):
        a = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [5.0, 0.0, 0.0], [6.0, 0.0, 0.0], [5.0, 1.0, 0.0]], np.float32)          # two panels of one group
        f = fake({'barrels': a.copy()}); turned = a.copy(); turned[:, 2] += turned[:, 0] * 0.3                                                     # the camera turns: both panels re-placed
        def orient(yaw, base, pitch): f.objects.cur['barrels'] = turned.copy(); f.objects.dirty = {'barrels'}; return True
        f.objects.orient = orient; f.objects.dirty = set()
        f._orient_scenery = FieldMixin._orient_scenery.__get__(f)
        return f, turned

    def test_other_panels_stay_still_when_one_changes(self):
        f, turned = self.window()
        f._orient_scenery((np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])))
        np.testing.assert_allclose(f.obj_shown['barrels'], turned)                                   # (the reference follows the new orientation)
        broken = turned.copy(); broken[:3] = 0.0                                                    # the first barrel is broken: its panel is hidden
        f.objects.cur['barrels'] = broken; f._note_movements({'barrels'})
        self.assertEqual(f.obj_moving, {}); f._smooth_objects(0.2)                                    # (nothing moves: the second barrel is drawn where it stands)

    def test_a_moving_panel_keeps_its_interpolation(self):
        f, turned = self.window()
        old = f.objects.cur['barrels'].copy(); mask = np.array([True] * 3 + [False] * 3)
        f.obj_moving = {'barrels': (old, old.copy(), mask)}
        f._orient_scenery((np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])))
        np.testing.assert_allclose(f.obj_moving['barrels'][1], turned); np.testing.assert_allclose(f.obj_shown['barrels'], old)          # (ends on the new orientation; its step reference is untouched)


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class FbxModels(unittest.TestCase):
    def test_position_and_rotation_between_two_steps(self):
        st = types.SimpleNamespace(part=ENGINE.PART_TOWN, game_map='mndoc', sprites={}, cam_pos=None, cam_target=None, field=None, loading=None,
                                   fbx={3: {'pos': (0.0, 0.0, 0.0), 'rot': (0.0, 350.0, 0.0)}})
        g = types.SimpleNamespace(engine=types.SimpleNamespace(state=st), mode=None)
        g.prev = G.Game._snapshot(g); st.fbx[3] = {'pos': (1.0, 0.0, 0.0), 'rot': (0.0, 10.0, 0.0)}; g.alpha = 0.5
        g._interpolate_camera = lambda pr, a: None
        saved = G.Game._interpolate(g)
        self.assertEqual(st.fbx[3]['pos'], (0.5, 0.0, 0.0)); self.assertAlmostEqual(st.fbx[3]['rot'][1] % 360.0, 0.0)          # (350 -> 10 by 0, not by 180)
        self.assertEqual(len(saved), 2)


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class TownMeshes(unittest.TestCase):
    """a monster drawn as a mesh in a town scene (DQ IV's last boss rising into the sky after the fight) shook: its position moved at 30 Hz while the camera following it was interpolated"""
    def state(self):
        st = types.SimpleNamespace(part=ENGINE.PART_TOWN, game_map='dab1', sprites={}, cam_pos=None, cam_target=None, field=None, loading=None, fbx={},
                                   models={2: 255}, meshes={2: {'pos': (0.0, 1.0, 0.0), 'v': []}})
        g = types.SimpleNamespace(engine=types.SimpleNamespace(state=st), mode=None); g._interpolate_camera = lambda pr, a: None
        return st, g

    def test_position_between_two_steps(self):
        st, g = self.state()
        g.prev = G.Game._snapshot(g); st.meshes[2]['pos'] = (0.0, 2.0, 0.0); g.alpha = 0.5
        saved = G.Game._interpolate(g)
        self.assertEqual(st.meshes[2]['pos'], (0.0, 1.5, 0.0))
        for obj, name, old, attr in saved: obj[name] = old
        self.assertEqual(st.meshes[2]['pos'], (0.0, 2.0, 0.0), 'put back after the drawing')

    def test_other_model_not_interpolated(self):
        st, g = self.state()
        g.prev = G.Game._snapshot(g); st.models[2] = 146; st.meshes[2]['pos'] = (5.0, 0.0, 0.0); g.alpha = 0.5
        G.Game._interpolate(g)
        self.assertEqual(st.meshes[2]['pos'], (5.0, 0.0, 0.0))


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class RisingIcons(unittest.TestCase):
    """the item that rises out of a chest, a jar, a wardrobe (packets 19/20, Riseup: 0.25 up per step for 6 steps, then a fade) went up by jerks of 30 Hz: drawn between two steps now"""
    def state(self, icons):
        st = types.SimpleNamespace(part=ENGINE.PART_TOWN, game_map='dab1', sprites={}, cam_pos=None, cam_target=None, field=None, loading=None, fbx={}, icons=icons)
        g = types.SimpleNamespace(engine=types.SimpleNamespace(state=st), mode=None); g._interpolate_camera = lambda pr, a: None
        return st, g

    def test_rise_and_fade_between_two_steps(self):
        st, g = self.state({0: {'id': 111, 'pos': (2.5, 0.971, -9.318), 'alpha': 0.032}})
        g.prev = G.Game._snapshot(g); st.icons[0] = {'id': 111, 'pos': (2.5, 1.218, -9.321), 'alpha': 0.613}; g.alpha = 0.5
        saved = G.Game._interpolate(g)
        p = st.icons[0]['pos']; self.assertAlmostEqual(p[1], (0.971 + 1.218) / 2); self.assertAlmostEqual(st.icons[0]['alpha'], (0.032 + 0.613) / 2)
        for obj, name, old, attr in saved: obj[name] = old
        self.assertEqual(st.icons[0], {'id': 111, 'pos': (2.5, 1.218, -9.321), 'alpha': 0.613}, 'put back after the drawing')

    def test_new_or_other_icon_not_interpolated(self):
        st, g = self.state({0: {'id': 188, 'pos': (0.0, 1.294, 0.0), 'alpha': 1.0}})
        g.prev = G.Game._snapshot(g); st.icons[0] = {'id': 111, 'pos': (0.0, 0.971, 0.0), 'alpha': 0.032}; st.icons[1] = {'id': 111, 'pos': (1.0, 1.0, 1.0), 'alpha': 1.0}; g.alpha = 0.5
        G.Game._interpolate(g)
        self.assertEqual(st.icons[0]['pos'], (0.0, 0.971, 0.0)); self.assertEqual(st.icons[1]['pos'], (1.0, 1.0, 1.0))


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class EngineShadows(unittest.TestCase):
    def test_balloon_shadow_with_its_balloon(self):
        """the balloon's shadow (packet 15 bit 14, map pixels, 2 tiles south) and a separate town shadow (bit 12) move between two steps with their character, not at 30 Hz."""
        sp = {'pos': (100.0, 200.0, 0.0), 'shadow_field': (100.0, 232.0, 0.0), 'col': (1, 1, 1, 1)}
        st = types.SimpleNamespace(part=ENGINE.PART_FIELD, game_map='field', sprites={0: sp}, cam_pos=None, cam_target=None, field=None, loading=None, fbx={})
        g = types.SimpleNamespace(engine=types.SimpleNamespace(state=st), mode=None)
        g.prev = G.Game._snapshot(g); sp['pos'] = (102.0, 200.0, 0.0); sp['shadow_field'] = (102.0, 232.0, 0.0); g.alpha = 0.5
        saved = G.Game._interpolate(g)
        self.assertEqual((sp['pos'][0], sp['shadow_field'][0]), (101.0, 101.0))
        for obj, k, old, attr in saved: obj[k] = old
        self.assertEqual(sp['shadow_field'], (102.0, 232.0, 0.0))
        st.part = ENGINE.PART_TOWN; sp.update(pos=(1.0, 0.0, 1.0), shadow_pos=(1.0, 0.0, 1.0)); del sp['shadow_field']
        g.prev = G.Game._snapshot(g); sp.update(pos=(1.2, 0.0, 1.0), shadow_pos=(1.2, 0.0, 1.0)); g._interpolate_camera = lambda pr, a: None
        G.Game._interpolate(g); self.assertAlmostEqual(sp['shadow_pos'][0], 1.1)

    def test_balloon_height_change_keeps_the_interpolation(self):
        """on the world map the 3rd value is a height for the stacking (the balloon: 20 over the sea, 60 over land); its change between two steps no longer stops the interpolation of
        the balloon (it jumped ahead of its shadow and of the camera for one frame: a tremble at the coast)."""
        sp = {'pos': (100.0, 200.0, 60.0), 'col': (1, 1, 1, 1)}
        st = types.SimpleNamespace(part=ENGINE.PART_FIELD, game_map='field', sprites={0: sp}, cam_pos=None, cam_target=None, field=None, loading=None, fbx={})
        g = types.SimpleNamespace(engine=types.SimpleNamespace(state=st), mode=None)
        g.prev = G.Game._snapshot(g); sp['pos'] = (102.0, 198.0, 20.0); g.alpha = 0.5
        G.Game._interpolate(g); self.assertEqual(sp['pos'], (101.0, 199.0, 20.0))

    def test_shadow_offset_drops_the_one_step_jump(self):
        """the engine moves the balloon's shadow one step late when the balloon turns: the offset jumps for one step and comes back; the median of three steps keeps it still."""
        import collections
        from dq456_pc.window.helpers import shadow_offset
        d = collections.deque(maxlen=3)
        seen = []
        for off in ((0, 32), (0, 32), (-3, 35), (0, 32), (0, 32), (3, 29), (0, 32)): d.append(off); seen.append(shadow_offset(d, off))
        self.assertEqual(set(seen), {(0, 32)})
        d.clear(); seen = []
        for off in ((0, 0), (0, 3), (0, 7), (0, 10), (0, 13)): d.append(off); seen.append(shadow_offset(d, off)[1])
        self.assertEqual(seen, [0, 3, 3, 7, 10])                                   # (taking off: followed one step later)
        self.assertEqual(shadow_offset(None, (1, 2)), (1, 2))

    def test_shadows_go_out_with_their_frame(self):
        """the shadows' vertices are written after the frame's first draws (the map, the scenery): unless the vertex buffers are bound and sent again, the GPU drew the previous frame's,
        so the balloon's shadow trailed its balloon (by its last move, a staircase in diagonal), and a walker's shadow its walker. Each shadow drawing now forces that (_linked_domain None)."""
        import types as T
        from dq456_pc.window import field as FD
        class SVL:
            def __init__(s): s.position = [0.0] * 18; s.tex_coords = [0.0] * 12; s.colors = [0.0] * 24
        stub = T.SimpleNamespace(glDepthMask=lambda *a: None, glDepthFunc=lambda *a: None, GL_FALSE=0, GL_TRUE=1, GL_LEQUAL=0, GL_LESS=0)
        for name, args in (('_draw_field_shadows', (1.0,)), ('_draw_character_shadows', ((np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])),))):
            seen = []; o = T.SimpleNamespace(_shadow_tex=object(), _shadow_vl={12: SVL()}, prog={}, _linked_domain='bound since the map', SHADOW_FIELD=(10.0, 5.9),
                                              SHADOW_HALF_SIZE=(0.2, 0.1), SHADOW_OFFSET=0.0, SHADOW_HEIGHT=0.01)
            o._paint = lambda t, vl, o=o, seen=seen: seen.append((o._linked_domain, list(vl.position[:3])))
            real = FD.gl; FD.gl = stub
            try: getattr(FD.FieldMixin, name)(o, [(12, np.array([1.0, 0.0, 2.0]), 1.0)], *args)
            finally: FD.gl = real
            self.assertEqual(len(seen), 1, name); self.assertIsNone(seen[0][0], name)                  # (bound again: the new vertices are sent)
            self.assertNotEqual(seen[0][1], [0.0, 0.0, 0.0], name)                                       # (written before the draw)


if __name__ == '__main__':
    unittest.main(verbosity=1)
