"""World map scale in a balloon (packet 30, `cmd_field_scale`):

1. `State`: a negative integer followed by a float sets the field scale (Field.SetScale: 1.0 to 1.25 in a balloon) ; an integer >= 0 registers the character of that slot as a "floating object"
   (Field.SetFloatingObject: the balloon, slot 12) ; no duplicates ; aberrant values (0, negative, NaN, infinity, missing) ignored, extreme values clamped ;
2. reload: the loading of a map (packet 0) resets the scale to 1 and empties the floating objects ; the loading of the world map (packet 27) too (the engine registers the balloon again just after) ;
3. a state saved before this fix (without these attributes) behaves like a fresh one: scale 1, no floating object ;
4. world map camera: the phone's area turned on its side in 16:9, the visible height multiplied by the game scale (no more player zoom ; skipped without pyglet).

  python3 tests/test_balloon_scale.py
"""
import math, os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import engine as ENGINE

try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq4_pc.window import camera as CAM
    from dq4_pc.window.constants import CH_PHONE_SHORT
except Exception as ex:          # window/camera.py needs pyglet (the import alone is enough)
    CAM = None


def send(e, *packets):
    e.apply(list(packets), lambda: 'ev01')


class Packet30(unittest.TestCase):
    def test_default_values(self):
        e = ENGINE.State(); self.assertEqual(e.field_scale, 1.0); self.assertEqual(e.floats, ())

    def test_scale(self):
        e = ENGINE.State()
        send(e, (30, [-1], [1.25])); self.assertAlmostEqual(e.field_scale, 1.25)
        send(e, (30, [-1], [1.1015625])); self.assertAlmostEqual(e.field_scale, 1.1015625)          # 1 + 13 / 128
        send(e, (30, [-1], [1.0])); self.assertEqual(e.field_scale, 1.0)                           # landing: the balloon goes back down to scale 1

    def test_floating_item(self):
        e = ENGINE.State()
        send(e, (30, [12], [])); self.assertEqual(e.floats, (12,))
        send(e, (30, [12], [])); self.assertEqual(e.floats, (12,))          # no duplicate
        send(e, (30, [3], [])); self.assertEqual(e.floats, (12, 3))
        self.assertEqual(e.field_scale, 1.0)                                    # registering an object does not touch the scale

    def test_outlier_values(self):
        e = ENGINE.State(); send(e, (30, [-1], [1.25]))
        for f in ([], [0.0], [-2.0], [math.nan], [math.inf]):
            send(e, (30, [-1], f)); self.assertEqual(e.field_scale, 1.25, f)
        send(e, (30, [-1], [1000.0])); self.assertEqual(e.field_scale, ENGINE.FIELD_SCALE[1])
        send(e, (30, [-1], [1e-6])); self.assertEqual(e.field_scale, ENGINE.FIELD_SCALE[0])
        send(e, (30, [], [1.25]))                                              # empty packet: ignored without error

    def test_map_loading(self):
        e = ENGINE.State(); send(e, (30, [12], []), (30, [-1], [1.25]))
        send(e, (0, [], [])); self.assertEqual(e.field_scale, 1.0); self.assertEqual(e.floats, ())

    def test_world_map_loading(self):
        e = ENGINE.State(); send(e, (30, [12], []), (30, [-1], [1.25]))
        send(e, (27, [1], []), (30, [12], []))          # what the real engine sends on entering the world map (verified on save 4: frame 31)
        self.assertEqual(e.field_scale, 1.0); self.assertEqual(e.floats, (12,))

    def test_old_state(self):
        e = ENGINE.State.__new__(ENGINE.State)           # a saved state without these attributes (neither __init__, nor a filled __dict__)
        self.assertEqual(e.field_scale, 1.0); self.assertEqual(e.floats, ())


@unittest.skipIf(CAM is None, 'no pyglet')
class WorldCamera(unittest.TestCase):
    def make_view(self, scale_factor):
        fake = types.SimpleNamespace(mode=0)
        e = ENGINE.State(); e.field_scale = scale_factor; e.field = {'x0': 0, 'y0': 0, 'cols': 25, 'tiles': [], 'cam': (160.0, 320.0)}
        CAM.CameraMixin._field_camera(fake, e, 16 / 9)
        return fake._field_view

    def test_visible_height(self):
        cx, cz, dl, dh = self.make_view(1.0)
        self.assertAlmostEqual(dh, 8.0); self.assertAlmostEqual(dl, 128.0 / 9)          # 16:9 shows the phone's portrait area turned on its side, 28.4 tiles across and 16 up (its own zoom again)
        self.assertAlmostEqual(CH_PHONE_SHORT, 16.0)
        self.assertAlmostEqual(self.make_view(1.25)[3], dh * 1.25)             # 25 % more terrain

    def test_other_shapes_keep_the_base(self):
        """wider than 16:9, the same 16 tiles up and more across; narrower, the same 28.4 tiles across and more up; in portrait 9:16 exactly the phone (16 across, 28.4 up)."""
        fake = types.SimpleNamespace(mode=0); e = ENGINE.State(); e.field = {'x0': 0, 'y0': 0, 'cols': 25, 'tiles': [], 'cam': (0.0, 0.0)}
        for aspect, across, up in ((21 / 9, 16 * 21 / 9, 16.0), (16 / 10, 256 / 9, 256 / 9 / 1.6), (4 / 3, 256 / 9, 256 / 9 * 0.75), (1.0, 256 / 9, 256 / 9), (9 / 16, 16.0, 256 / 9), (0.5, 16.0, 32.0)):
            CAM.CameraMixin._field_camera(fake, e, aspect); _, _, dl, dh = fake._field_view
            self.assertAlmostEqual(2 * dl, across, msg=aspect); self.assertAlmostEqual(2 * dh, up, msg=aspect)

    def test_center_unchanged(self):
        cx, cz, dl, dh = self.make_view(1.25); self.assertAlmostEqual(cx, 10.0); self.assertAlmostEqual(cz, 20.0)

    def test_state_without_scale(self):
        fake = types.SimpleNamespace(mode=0); e = types.SimpleNamespace(field=None)        # object without the attribute (another kind of state): scale 1
        CAM.CameraMixin._field_camera(fake, e, 16 / 9); self.assertAlmostEqual(fake._field_view[3], CH_PHONE_SHORT / 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
