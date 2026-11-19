"""Unity -> engine messages (camera position: the three games; map object positions: DQ VI), the other orders of packet FLD_ETC of DQ V / VI, DQ VI's character hues, and the sound mix.

  python3 tests/test_v2_object_positions.py

1. packet FLD_ETC (NativeManager.cmd_fld_etc), DQ VI: case 1: the object number (value >> 8) | 0x4000 joins the requests, kept until the next map load (cmd_fld_load clears the list);
   case 3: FldObject.Pause(value & 0x1000); the other cases change nothing. DQ V: bit 30 = Chara.SetPriorityShader(value & 0xffff), put back to 0 by the next map load; its values
   never become DQ VI's cases (0x40000001 is a priority of 1, not an object request). DQ IV has no such packet;
   packet 15 in DQ VI: bit 15 = Chara.SetupHue(ice = bit 14, amount), bit 14 alone = Chara.SetHue(amount); packet 30 >= 0x4000 = Field.RemoveFloatingObject;
2. Engine._map_object_messages: message (2, identifier, x, y, -z) in 1/4096 for each request, Vector3.zero when the window knows no such object (FldObject.GetMapObjDispPos);
3. MapObjects.display_position: the transform's position (original place, then its movement in progress), None for an object the game's table does not point to;
4. Mixer: a sound's gain is its file's own volume times the volume settings, in the three games (no per-game balance);
5. packet FLD_ETC case 0 in DQ VI (FldObject.MoveToEventCameraFirstKey(step, steps)): an order 'camera_key', and 'camera_engine' at the engine's next camera packet;
   MapObjects.camera_first_key: step 1 notes the camera's position and the point in front of it at the key's distance to its target, both then go in a straight line to the first key of the map's
   first camera movement (step / steps), up vector = the key's; the view holds until camera_engine, a camera movement or the map's reload; nothing on a map without camera movement.
7. DQ V: cmd_fld_etc's kept value 0 = the first character rides map object 38 (MapObjects.rider_position: the transform's position, moved along the cart's axes while it leans);
   DQ VI: case 2 = Chara.ChangeBillboardCalc for the characters loaded at that moment (engine.billboard2_pull);
6. the three games: the frame after a camera packet (cmd_camera), message (0, x, y, -z) in 1/4096 = Camera.main's position after SceneCamera.Update (engine.scene_camera_position):
   with a target, the engine's position advanced by 4 units along the axis turned toward the target and raised by lookDownAdjust; free camera, battle, casino: the engine's position.
"""
import math, os, struct, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper)
from dq456_pc.core import engine as ENGINE
from dq456_pc.core import engine_layout as LY
from dq456_pc.world import map_objects as OC
from dq456_pc import sound as SOUND


class Requests(unittest.TestCase):
    def setUp(self): self.game = ENGINE.FLD_ETC_GAME
    def tearDown(self): ENGINE.FLD_ETC_GAME = self.game

    def test_case_1_adds_until_the_next_map(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(LY.FLD_ETC, [0x1601], []), (LY.FLD_ETC, [0x1402], []), (LY.FLD_ETC, [0x1501], [])], lambda: 'c00df2d')
        self.assertEqual(s.obj_requests, (0x4016, 0x4015))
        s.apply([(0, [0], [])], lambda: 'm01um4f1')
        self.assertEqual(s.obj_requests, ())

    def test_pause_dq6(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(LY.FLD_ETC, [0x1003], [])], lambda: 'm01uout'); self.assertTrue(s.fld_paused)
        s.apply([(LY.FLD_ETC, [3], [])], lambda: 'm01uout'); self.assertFalse(s.fld_paused)
        s.apply([(LY.FLD_ETC, [0x1003], [])], lambda: 'm01uout'); s.apply([(0, [0], [])], lambda: 'm01um4f1'); self.assertFalse(s.fld_paused)

    def test_character_queue_dq5(self):
        ENGINE.FLD_ETC_GAME = 'dq5'
        s = ENGINE.State()
        s.apply([(LY.FLD_ETC, [0x4000000b], [])], lambda: 'mdout'); self.assertEqual(s.chara_queue, 11)
        s.apply([(LY.FLD_ETC, [0x40000001], []), (LY.FLD_ETC, [0x2000005b], [])], lambda: 'mdout')
        self.assertEqual(s.chara_queue, 1); self.assertEqual(s.obj_requests, ()); self.assertFalse(s.fld_paused)
        s.apply([(0, [0], [])], lambda: 'mdf1'); self.assertEqual(s.chara_queue, 0)

    def test_dq4_ignores_the_packet(self):
        ENGINE.FLD_ETC_GAME = 'dq4'
        s = ENGINE.State()
        s.apply([(LY.FLD_ETC, [0x1601], []), (LY.FLD_ETC, [0x4000000b], []), (LY.FLD_ETC, [0x1003], [])], lambda: 'cbf2')
        self.assertEqual((s.obj_requests, s.chara_queue, s.fld_paused), ((), 0, False))

    def test_hue_dq6(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(12, [3, 7], [])], lambda: 'x')
        s.apply([(15, [3 | 0x4000], [0.5])], lambda: 'x'); self.assertIsNone(s.sprites[3].get('hue'))          # (SetHue before any SetupHue: the material has no such value)
        s.apply([(15, [3 | 0xc000], [0.25])], lambda: 'x'); self.assertEqual(s.sprites[3]['hue'], (True, 0.25))
        s.apply([(15, [3 | 0x4000], [1.0])], lambda: 'x'); self.assertEqual(s.sprites[3]['hue'], (True, 1.0))
        s.apply([(15, [3 | 0x8000 | 0x2000], [0.5, 0.75])], lambda: 'x'); self.assertEqual(s.sprites[3]['hue'], (False, 0.75)); self.assertEqual(s.sprites[3]['shadow_alpha'], 0.5)
        self.assertNotIn('shadow_field', s.sprites[3])

    def test_billboard2_dq6(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(12, [0, 7], []), (12, [8, 9], []), (16, [8 | 0x100], []), (LY.FLD_ETC, [2], []), (12, [9, 9], [])], lambda: 'e01din2')
        self.assertTrue(s.sprites[0].get('billboard2')); self.assertFalse(s.sprites[8].get('billboard2')); self.assertFalse(s.sprites[9].get('billboard2'))          # (lying; loaded after)
        s.apply([(16, [0 | 0x200], [])], lambda: 'e01din2'); self.assertFalse(s.sprites[0].get('billboard2'))          # (SetSleepPose(false): Chara.normalBillboard again)
        s.apply([(LY.FLD_ETC, [2], []), (12, [0, 7], [])], lambda: 'e01din2'); self.assertFalse(s.sprites[0].get('billboard2'))          # (loaded again: a new Chara)
        self.assertAlmostEqual(ENGINE.billboard2_pull(35.55), 0.375); self.assertAlmostEqual(ENGINE.billboard2_pull(39.55), 0.5); self.assertAlmostEqual(ENGINE.billboard2_pull(79.1), 2.8)
        ENGINE.FLD_ETC_GAME = 'dq5'
        s = ENGINE.State(); s.apply([(12, [0, 7], []), (LY.FLD_ETC, [2], [])], lambda: 'x'); self.assertFalse(s.sprites[0].get('billboard2'))

    def test_mesh_523_dq6(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(24, [0x40000000 | 7], [])], lambda: 'x')
        self.assertEqual(s.models[7], 523); self.assertEqual(s.mesh_state[7]['rot'], (323.5, 180.0, -5.33921)); self.assertEqual(s.mesh_state[7]['col'], (1.0, 1.0, 1.0))
        s.apply([(21, [7, 40], [])], lambda: 'x'); self.assertNotIn('rot', s.mesh_state[7])          # (loaded again: an ordinary MeshChara)
        ENGINE.FLD_ETC_GAME = 'dq5'
        s = ENGINE.State(); s.apply([(24, [0x40000000 | 7], [])], lambda: 'x'); self.assertNotIn(7, s.models)

    def test_rider_dq5(self):
        ENGINE.FLD_ETC_GAME = 'dq5'
        s = ENGINE.State()
        s.apply([(LY.FLD_ETC, [0x4000000b], [])], lambda: 'dkb3cev'); self.assertIsNone(s.rider_object)
        s.apply([(LY.FLD_ETC, [0], [])], lambda: 'dkb3cev'); self.assertEqual(s.rider_object, 38)
        s.apply([(LY.FLD_ETC, [0x2000005b], [])], lambda: 'dkb3cev'); self.assertEqual(s.rider_object, 38)          # (FixProblems leaves the kept value alone)
        s.apply([(0, [0], [])], lambda: 'dkb3c'); self.assertIsNone(s.rider_object)
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State(); s.apply([(LY.FLD_ETC, [0], [])], lambda: 'x'); self.assertIsNone(s.rider_object)

    def test_floating_object_removed_dq6(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(30, [12], []), (30, [5], [])], lambda: 'x'); self.assertEqual(s.floats, (12, 5))
        s.apply([(30, [0x4000 | 12], [])], lambda: 'x'); self.assertEqual(s.floats, (5,))

    def test_messages(self):
        fake = types.SimpleNamespace(state=types.SimpleNamespace(obj_requests=(0x4014, 0x4016)), map_obj_pos=lambda i: (1.5, 0.25, -2.0) if i == 0x14 else None)
        data = ENGINE.Engine._map_object_messages(fake)
        self.assertEqual(struct.unpack('<10i', data), (2, 0x4014, 6144, 1024, 8192, 2, 0x4016, 0, 0, 0))
        fake.state.obj_requests = ()
        self.assertEqual(ENGINE.Engine._map_object_messages(fake), b'')


def one_object(pmv=-1, words=()):
    import numpy as np
    o = dict(i=0, id=0, pos=(1.0, 2.0, 3.0), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0), model=1, com=65535, uid=0, flag=0, prio=0, sequence_object=-1, pmv=pmv, canim=-1)
    pos = np.zeros((3, 3), np.float32) + np.array([1.0, 2.0, 3.0], np.float32)
    c = dict(groups={7: (pos, np.zeros((3, 2), np.float32), np.ones((3, 4), np.float32))}, textures={}, objects=[o], nobj=1, spans={0: [(7, 0, 3)]}, motions=list(words))
    return OC.MapObjects(c)


class DisplayPosition(unittest.TestCase):
    def test_original_place(self):
        self.assertEqual(one_object().display_position(0), (1.0, 2.0, 3.0))

    def test_rider_on_a_level_object(self):
        m = one_object()
        self.assertEqual(m.rider_position(0), (1.0, 2.0, 3.0)); self.assertIsNone(m.rider_position(5))

    def test_rider_on_a_leaning_object(self):
        import numpy as np
        m = one_object(); a = math.radians(30.0); c, s_ = math.cos(a), math.sin(a)
        m._rot = lambda rot: np.array([[1.0, 0.0, 0.0], [0.0, c, -s_], [0.0, s_, c]])          # (its up vector leans toward +z: (0, cos 30, sin 30); forward (0, -sin 30, cos 30))
        x, y, z = m.rider_position(0); dz = s_ * 0.3; k = dz * 0.15 / 0.212
        self.assertAlmostEqual(x, 1.0); self.assertAlmostEqual(y, 2.0 + c * 0.3 * dz / 0.212 - s_ * k); self.assertAlmostEqual(z, 3.0 + dz + c * k)
        m._rot = lambda rot: np.array([[1.0, 0.0, 0.0], [0.0, c, s_], [0.0, -s_, c]])          # (leaning toward -z: the transform's position as is)
        self.assertEqual(m.rider_position(0), (1.0, 2.0, 3.0))

    def test_movement_in_progress(self):
        word = dict(flag=1, nkey=2, repeat=-1, delay=0, loop_delay=0, end=10, keys=[(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), (10, (2.0, 0.0, -4.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))])
        m = one_object(0, [word])
        st = m.state[0]; st['motion_time'] = 5
        x, y, z = m.display_position(0)
        self.assertAlmostEqual(x, 2.0); self.assertAlmostEqual(y, 2.0); self.assertAlmostEqual(z, 1.0)

    def test_unknown_or_hidden(self):
        m = one_object()
        self.assertIsNone(m.display_position(5))
        m.tbl_hidden.add(0)
        self.assertIsNone(m.display_position(0))


class FirstKey(unittest.TestCase):
    KEY = (0, (10.0, 4.0, -6.0), (10.0, 0.0, -3.0), (0.0, 1.0, 0.0))                  # (position - target: 5 units)

    def setUp(self): self.game = ENGINE.FLD_ETC_GAME
    def tearDown(self): ENGINE.FLD_ETC_GAME = self.game

    def objects(self, cameras):
        return OC.MapObjects({'objects': [], 'groups': {}, 'cameras': cameras})

    def test_orders(self):
        ENGINE.FLD_ETC_GAME = 'dq6'
        s = ENGINE.State()
        s.apply([(LY.FLD_ETC, [1 << 18 | 4 << 8], []), (LY.FLD_ETC, [2 << 18 | 4 << 8], [])], lambda: 'x')
        self.assertEqual(s.object_cmds, [('camera_key', 1, 4), ('camera_key', 2, 4)])
        s.object_cmds = []
        s.apply([(10, [1], [1.0, 2.0, 3.0])], lambda: 'x'); self.assertEqual(s.object_cmds, [('camera_engine',)])
        s.object_cmds = []
        s.apply([(10, [1], [1.0, 2.0, 3.0])], lambda: 'x'); self.assertEqual(s.object_cmds, [])          # (only after a first-key view)
        ENGINE.FLD_ETC_GAME = 'dq5'
        s = ENGINE.State(); s.apply([(LY.FLD_ETC, [1 << 18 | 4 << 8], []), (10, [1], [1.0, 2.0, 3.0])], lambda: 'x'); self.assertEqual(s.object_cmds, [])

    def test_straight_line_to_the_key(self):
        mo = self.objects([dict(end=0, repeat=-1, delay=0, loop_delay=0, keys=[self.KEY])])
        self.assertIsNone(mo.camera_view())
        mo.camera_first_key(1, 4, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        pos, target, up = mo.camera_view()
        self.assertEqual(pos, (2.5, 1.0, -1.5)); self.assertEqual(target, (2.5, 0.0, 3.0)); self.assertEqual(up, (0.0, 1.0, 0.0))          # (start target: 5 units in front)
        mo.camera_first_key(2, 4, (99.0, 99.0, 99.0), (1.0, 0.0, 0.0))                                   # (the start is only read at step 1)
        self.assertEqual(mo.camera_view(), ((5.0, 2.0, -3.0), (5.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
        mo.camera_first_key(4, 4, None, None); self.assertEqual(mo.camera_view(), (self.KEY[1], self.KEY[2], self.KEY[3]))
        mo.camera_first_key(9, 4, None, None); self.assertEqual(mo.camera_view()[0], self.KEY[1])        # (held at 1)
        mo.camera_engine(); self.assertIsNone(mo.camera_view())

    def test_at_once(self):
        mo = self.objects([dict(end=0, repeat=-1, delay=0, loop_delay=0, keys=[self.KEY])])
        mo.camera_first_key(1, 1, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        self.assertEqual(mo.camera_view(), (self.KEY[1], self.KEY[2], self.KEY[3]))

    def test_movement_and_reload_end_it(self):
        mo = self.objects([dict(end=10, repeat=-1, delay=0, loop_delay=0, keys=[self.KEY, (10, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))])])
        mo.camera_first_key(1, 2, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)); mo.event_camera(1)
        self.assertEqual(mo.camera_view()[0], self.KEY[1])
        mo.event_camera(0); self.assertEqual(mo.camera_view()[0], self.KEY[1])                    # (camera 0: the movement's last pose holds until the engine's next camera packet)
        mo.camera_engine(); self.assertIsNone(mo.camera_view())
        mo.camera_first_key(1, 2, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)); mo.reinit(); self.assertIsNone(mo.camera_view())

    def test_no_movement_no_key(self):
        for cameras in ([], [dict(end=0, repeat=-1, delay=0, loop_delay=0, keys=[])]):
            mo = self.objects(cameras); mo.camera_first_key(1, 1, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)); self.assertIsNone(mo.camera_view())


class CameraMessage(unittest.TestCase):
    def state(self, **kw):
        d = dict(cam_pos=(0.0, 0.0, -83.0), cam_target=(4.099853515625, 0.0, 0.0), cam_rot=None, cam_free=False, cam_down=3.019360065460205, part=ENGINE.PART_BESTIARY, cam_sent=True)
        d.update(kw); return types.SimpleNamespace(**d)

    def test_position_with_a_target(self):
        x, y, z = ENGINE.scene_camera_position(self.state())                      # (the monster book's camera)
        self.assertAlmostEqual(x, 0.197, places=3); self.assertAlmostEqual(y, 0.211, places=3); self.assertAlmostEqual(z, -79.010, places=3)
        x, y, z = ENGINE.scene_camera_position(self.state(cam_pos=(0.0, 30.0, -30.0), cam_target=(0.0, 0.0, 0.0), cam_down=None, part=ENGINE.PART_TOWN))
        self.assertAlmostEqual(x, 0.0); self.assertAlmostEqual(math.hypot(y - 30.0, z + 30.0), 4.0)
        self.assertAlmostEqual(math.degrees(math.atan2(30.0 - y, z + 30.0)), 45.0 - 0.2, places=4)          # (pitch raised by 0.2 degree)

    def test_tall_screen_dq6(self):
        game = ENGINE.FLD_ETC_GAME
        try:
            ENGINE.FLD_ETC_GAME = 'dq6'
            self.assertEqual(ENGINE.scene_distance_adjust('e13din6', True), 7.0)
            self.assertEqual(ENGINE.scene_distance_adjust('e13din6', False), 4.0); self.assertEqual(ENGINE.scene_distance_adjust('e12din1', True), 4.0)
            st = self.state(cam_pos=(0.0, 0.0, -30.0), cam_target=(0.0, 0.0, 0.0), cam_down=0.0, part=ENGINE.PART_TOWN, game_map='e13din1', tall_screen=True)
            self.assertAlmostEqual(ENGINE.scene_camera_position(st)[2], -23.0)
            ENGINE.FLD_ETC_GAME = 'dq5'
            self.assertEqual(ENGINE.scene_distance_adjust('e13din6', True), 4.0)
        finally: ENGINE.FLD_ETC_GAME = game

    def test_position_without_target(self):
        for kw in (dict(cam_free=True), dict(cam_target=None), dict(part=ENGINE.PART_BATTLE), dict(part=ENGINE.PART_CASINO, cam_rot=(10.0, 0.0, 0.0))):
            self.assertEqual(ENGINE.scene_camera_position(self.state(**kw)), (0.0, 0.0, -83.0))
        self.assertIsNone(ENGINE.scene_camera_position(self.state(cam_pos=None)))

    def test_message_once_after_a_camera_packet(self):
        s = ENGINE.State(); self.assertFalse(s.cam_sent)
        s.apply([(10, [3], [0.0, 30.0, -30.0, 0.0, 0.0, 0.0])], lambda: 'x'); self.assertTrue(s.cam_sent)
        fake = types.SimpleNamespace(state=self.state(cam_free=True, cam_pos=(1.5, 0.25, -2.0)))
        self.assertEqual(struct.unpack('<4i', ENGINE.Engine._camera_message(fake)), (0, 6144, 1024, 8192))
        self.assertFalse(fake.state.cam_sent); self.assertEqual(ENGINE.Engine._camera_message(fake), b'')
        fake = types.SimpleNamespace(state=self.state(cam_pos=None)); self.assertEqual(ENGINE.Engine._camera_message(fake), b'')


class OriginalMix(unittest.TestCase):
    """The three games play each sound at its file's own volume (header x snd_vol.dat) times the game's volume option, as the original does (SoundControl.Play): the port adds only the
    player's own volume settings, the same for every game (a per-game balance between the categories was tried and removed)."""
    def test_gain_is_the_files_volume_times_the_settings(self):
        m = SOUND.Mixer()
        for category, own in (('effects', 0.25), ('interface', 0.3), ('jingles', 0.5), ('music', 0.8)): self.assertAlmostEqual(m.gain(category, own), own, msg=category)
        m = SOUND.Mixer(general=0.5, effects=0.5); self.assertAlmostEqual(m.gain('effects', 0.4), 0.1)
        self.assertFalse(hasattr(SOUND, 'GAME_BALANCE')); self.assertFalse(hasattr(m, 'balance'))


if __name__ == '__main__':
    unittest.main()
