"""Hidden faces of the scenery ("indoors the walls must become transparent ... the outer faces have no textures, if we rotate the camera we must be able to see through the walls"):

The shaders of the game's map scenery (Custom/fld_normal, fld_atest, fld_trans, fld_transz and their sepia variants) are "Cull Back" (ShaderLab culling = 2, read from the data package); only the world map (Custom/Field)
has no culling. `Game._scenery_culling` therefore turns on back-face culling (front face = clockwise on screen, Unity being left-handed) for each scenery group, except the title sky (its own vertices);
without window or GL: the GL calls are recorded.

    python3 tests/test_scenery_culling.py

  1. default mode: back-face culling, front face = clockwise (GL_CW); DQ_SCENERY_CULL = 0: nothing (the old rendering); 2: opposite winding (trial); `active` = False: always off and winding restored;
  2. `_paint_scenery`: culling is set group by group (never for the title sky) and turned off after the groups (shadows, sprites, effects, 3D models keep their own setting);
  3. the GL settings of the 3D models (Custom/ImdChara), shadows and effects are unchanged.
"""
import inspect, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F


class FakeGL:
    GL_CULL_FACE, GL_BACK, GL_CW, GL_CCW = 'CULL', 'BACK', 'CW', 'CCW'
    def __init__(self): self.calls = []
    def glEnable(self, x): self.calls.append(('enable', x))
    def glDisable(self, x): self.calls.append(('disable', x))
    def glCullFace(self, x): self.calls.append(('cullface', x))
    def glFrontFace(self, x): self.calls.append(('frontface', x))


class TestCulling(unittest.TestCase):
    def setUp(self):
        self.f = FakeGL(); self.restore_gl = _paths.set_global('gl', self.f); self.env0 = os.environ.pop('DQ_SCENERY_CULL', None)
    def tearDown(self):
        self.restore_gl()
        os.environ.pop('DQ_SCENERY_CULL', None)
        if self.env0 is not None: os.environ['DQ_SCENERY_CULL'] = self.env0

    def test_default_back_faces_hidden_clockwise(self):
        F.Game._scenery_culling(True)
        self.assertEqual(self.f.calls, [('enable', 'CULL'), ('cullface', 'BACK'), ('frontface', 'CW')])

    def test_culling_off(self):
        F.Game._scenery_culling(False); self.assertEqual(self.f.calls, [('disable', 'CULL'), ('frontface', 'CCW')])         # culling off and OpenGL's default winding restored

    def test_trial_variable(self):
        os.environ['DQ_SCENERY_CULL'] = '0'; F.Game._scenery_culling(True); self.assertEqual(self.f.calls, [('disable', 'CULL'), ('frontface', 'CCW')])         # the old rendering
        self.f.calls.clear(); os.environ['DQ_SCENERY_CULL'] = '2'; F.Game._scenery_culling(True); self.assertEqual(self.f.calls, [('enable', 'CULL'), ('cullface', 'BACK'), ('frontface', 'CCW')])
        self.f.calls.clear(); os.environ['DQ_SCENERY_CULL'] = 'x'; F.Game._scenery_culling(True); self.assertEqual(self.f.calls[-1], ('frontface', 'CW'))        # unreadable: like the default


class TestUsage(unittest.TestCase):
    def test_group_by_group_except_title_sky(self):
        src = inspect.getsource(F.Game._paint_scenery)
        group = 'if (key != sky_key) is not culled: culled = key != sky_key; self._scenery_culling(culled)'             # each scenery group (sent to the graphics card when it changes); never the title sky
        self.assertIn(group, src)
        self.assertIn("sky_key = self.flat_sky['key'] if self.flat_sky is not None else (self.zoom_sky['key'] if self.zoom_sky is not None else None)", src)
        self.assertIn('self._scenery_culling(False); culled = False', src)                                             # (the mirrored copies switch it off: the next group sets it again)
        i, j = src.index(group), src.rindex('self._scenery_culling(False)')
        self.assertLess(i, j)                                                                                         # culling off after the groups: the sky strips / copies and what follows keep their own setting
        self.assertLess(j, src.index('for tex, vl, key, start_idx, n, dx in self.ext_map'))

    def test_other_gl_settings_unchanged(self):
        src = _paths.source('window.py')
        self.assertIn("cull = os.environ.get('DQ_FBX_CULL', '1')", src)                                               # 3D models: Custom/ImdChara, Cull Back, their own variable
        self.assertEqual(src.count('gl.glEnable(gl.GL_CULL_FACE)'), 2)                                                # 3D models + _scenery_culling: nothing else turns it on


if __name__ == '__main__':
    unittest.main(verbosity=1)
