"""Performance pass: what the window no longer redoes every frame.

  - pyglet's per-call OpenGL check (glGetError after each of about a thousand calls a frame) is off in the game (main.py, before any window module; DQ_GL_DEBUG=1 puts it back);
    the setups that fell back on an OpenGL error (offscreen rendering, blur, mini-games' backdrop) check the error flag themselves (render/gl_errors.py);
  - the menus' "default value" buttons, the red crosses and the key pictures are built once and drawn again (pause.py _shapes / _sprite), the button plate refills one vertex list
    (ui_menu.Render.plate), the D-pad sprites are only moved when they move;
  - the engine's window table is read in one go (Engine.active_menu, several times a frame);
  - on the world map, the objects of the last town are no longer animated (they are not drawn).

  python3 tests/test_draw_caches.py
"""
import os, sys, types, unittest
from unittest import mock
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)


class GlCheck(unittest.TestCase):
    def test_debug_gl_off_before_the_window_modules(self):
        with open(os.path.join(ROOT, 'dq456_pc', 'main.py'), encoding='utf-8') as f: src = f.read()
        i = src.index("pyglet.options['debug_gl'] = bool(os.environ.get('DQ_GL_DEBUG'))"); j = src.index('from dq456_pc.window.game import Game')
        self.assertLess(i, j, 'the option is read when pyglet.gl is imported')

    def test_errors_of_the_setup_only(self):
        from dq456_pc.render import gl_errors as GE
        queue = [0x502, 0]                                                       # an error left by an earlier, unrelated call
        fake = types.SimpleNamespace(glGetError=lambda: queue.pop(0) if queue else 0)
        with mock.patch.object(GE, 'gl', fake):
            GE.clear(); GE.check('setup')                                        # cleared first: the setup's own calls made none
            queue[:] = [0x506]
            with self.assertRaises(RuntimeError): GE.check('setup')

    def test_fallback_setups_check_themselves(self):
        for path, what in (('render/postfx.py', "GE.check('offscreen rendering')"), ('render/screen_blur.py', "GE.check('blur')"), ('window/backdrop.py', "GE.check('backdrop copy')")):
            with open(os.path.join(ROOT, 'dq456_pc', path), encoding='utf-8') as f: self.assertIn(what, f.read(), path)


class Caches(unittest.TestCase):
    def setUp(self):
        try:
            import pyglet; pyglet.options['shadow_window'] = False
            from dq456_pc.menus import pause as PA; self.PA = PA
        except Exception as ex: self.skipTest('window modules need pyglet: %s' % ex)

    def test_shapes_built_once_per_key(self):
        built = []; drawn = []
        fake_batch = lambda: types.SimpleNamespace(draw=lambda: drawn.append(1))
        p = types.SimpleNamespace(); p._shapes = types.MethodType(self.PA.Pause._shapes, p)
        with mock.patch.object(self.PA.pyglet.graphics, 'Batch', fake_batch):
            for _ in range(3): p._shapes(('default', 1.0, 2.0), lambda b: built.append(1) or ['shape'])
            p._shapes(('default', 1.0, 3.0), lambda b: built.append(1) or ['shape'])
        self.assertEqual((len(built), len(drawn)), (2, 4))

    def test_sprites_made_once_per_key(self):
        made = []; drawn = []
        p = types.SimpleNamespace(); p._sprite = types.MethodType(self.PA.Pause._sprite, p)
        make = lambda: made.append(1) or types.SimpleNamespace(draw=lambda: drawn.append(1), delete=lambda: None)
        for _ in range(3): p._sprite(('cross', 1.0), make)
        self.assertEqual((len(made), len(drawn)), (1, 3))


class WorldMapObjects(unittest.TestCase):
    def test_last_town_objects_not_animated_on_the_world_map(self):
        try:
            from dq456_pc.window.field import FieldMixin
            from dq456_pc.core import engine as ENGINE
        except Exception as ex: self.skipTest('window modules need pyglet: %s' % ex)
        ticks = []
        objs = types.SimpleNamespace(tick=lambda: ticks.append(1) or set(), dirty_uv=set(), dirty_col=set(), cur={})
        for part, expected in ((ENGINE.PART_FIELD, 0), (ENGINE.PART_TOWN, 1)):
            ticks.clear()
            w = types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(object_cmds=[], part=part, game_map='x')), objects=objs, palettes=None, ext_map=[], map_vl=[], map_name='x', n=0)
            FieldMixin._map_objects(w); self.assertEqual(len(ticks), expected, part)


if __name__ == '__main__':
    unittest.main()
