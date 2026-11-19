"""Dragon Quest V's title screen: what its Unity layer does that DQ IV's title did not need (no window, no engine, no APK; DQ_APK_DQ5 for the part on real data).

  python3 tests/test_dq5_title.py

1. map camera movements (FEMV, `fld.emv`): keys = frame, position, target, up vector, each with y negated (ChunkFile.readPosition); FETC background color (`fld.background`);
2. packet 6 >= 0x1000 (FldObject.SetCameraNo): an order 'camera' for DQ V / VI only; `MapObjects.event_camera` / `camera_view`: number n = FEMV entry n - 1, keys interpolated
   on the movement's clock (2 per frame), 0 = the engine's camera again, a number outside the table changes nothing, map reload = no movement, savestate round trip;
3. packet 0 of DQ V / VI: mode 2 (value >> 8) = free camera; the map's own background color until a packet 8; packet MESH_ORTHO marks the slot's mesh as orthographic;
   DQ V / VI meshes: texture offset (0, 1) at load (Material texture scale (1, -1));
4. the window: `_event_view` (LookAt: forward toward the target, up made perpendicular), `_ortho_matrix` (x from -128.5 to +128.5 across the phone's short side);
5. (real data) ev17: its 5 camera movements, number 1 at (0, -2.09, -38.18) looking at the origin, its light blue background.
"""
import math, os, struct, sys, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.world import fld
from dq456_pc.world import map_objects as OC
from dq456_pc.core import engine as ENGINE
from dq456_pc.core import engine_layout as LY

APK5 = os.environ.get('DQ_APK_DQ5', '')


def chunk(tag, body):
    b = struct.pack('<4sI', tag, 8 + len(body)) + body
    return b + b'\0' * (-len(b) % 16)


def femv(motions, start=0):
    """FEMV chunk (placed at offset `start` of the file): count, offsets, then each movement: 6 int16 (flag, nkey, repeat, delay, loop delay, key size), int32 end at +16, keys at +0x20 (40 bytes)."""
    n = len(motions); bodies = []
    for end, keys, repeat in motions:
        h = bytearray(0x20); struct.pack_into('<6h', h, 0, 0, len(keys), repeat, 0, 0, 40); struct.pack_into('<i', h, 16, end)
        for frame, pos, tag, up in keys: h += struct.pack('<i9f', frame, *pos, *tag, *up)
        bodies.append(bytes(h))
    offsets = []; p = start + 12 + 4 * n
    for b in bodies: offsets.append(p); p += len(b)
    return chunk(b'FEMV', struct.pack('<i', n) + struct.pack('<%di' % n, *offsets) + b''.join(bodies))


TWO = [(60, [(0, (0.0, 2.0, -38.0), (0.0, 0.0, 0.0), (0.0, -1.0, 0.0)), (60, (6.0, 2.0, -38.0), (0.0, -6.0, 0.0), (0.0, -1.0, 0.0))], -1),
       (0, [], -1)]


def objects(cameras):
    return OC.MapObjects({'objects': [], 'groups': {}, 'cameras': cameras})


class Reading(unittest.TestCase):
    def test_emv_keys(self):
        cams = fld.emv(femv(TWO))
        self.assertEqual(len(cams), 2); self.assertEqual(cams[0]['end'], 60); self.assertEqual(cams[0]['repeat'], -1)
        frame, pos, target, up = cams[0]['keys'][1]
        self.assertEqual(frame, 60); self.assertEqual(pos, (6.0, -2.0, -38.0)); self.assertEqual(target, (0.0, 6.0, 0.0)); self.assertEqual(up, (0.0, 1.0, 0.0))
        self.assertEqual(cams[1]['keys'], [])

    def test_no_emv(self): self.assertEqual(fld.emv(chunk(b'FETC', b'\0' * 8)), [])

    def test_background(self):
        self.assertEqual(fld.background(chunk(b'FETC', bytes((0x68, 0x8c, 0xff, 0)) + b'\0' * 28)), (0x68 / 255.0, 0x8c / 255.0, 1.0))
        self.assertIsNone(fld.background(chunk(b'FEAN', b'\0' * 8)))


class Packets(unittest.TestCase):
    def setUp(self): self.v2 = ENGINE.ENGINE_V2; ENGINE.ENGINE_V2 = True
    def tearDown(self): ENGINE.ENGINE_V2 = self.v2

    def state(self, packets):
        e = ENGINE.State(); e.apply(packets, lambda *a: 'ev17'); return e

    def test_camera_order(self):
        self.assertEqual(self.state([(6, [0x4001], [])]).object_cmds, [('camera', 1)])
        self.assertEqual(self.state([(6, [0x4000], [])]).object_cmds, [('camera', 0)])
        self.assertEqual(self.state([(6, [3], [])]).object_cmds, [('event', 3)])

    def test_dq4_keeps_ignoring_the_camera(self):
        ENGINE.ENGINE_V2 = False
        self.assertEqual(self.state([(6, [0x4001], [])]).object_cmds, [])

    def test_map_load_mode_2_is_a_free_camera(self):
        self.assertTrue(self.state([(0, [0x200], [])]).cam_free)
        self.assertFalse(self.state([(0, [0x100], [])]).cam_free)
        ENGINE.ENGINE_V2 = False
        self.assertFalse(self.state([(0, [0x200], [])]).cam_free)

    def test_map_background_until_packet_8(self):
        self.assertTrue(self.state([(0, [0x200], [])]).map_background)
        self.assertFalse(self.state([(0, [0x200], []), (8, [], [0.0] * 6)]).map_background)
        ENGINE.ENGINE_V2 = False
        self.assertFalse(self.state([(0, [0x200], [])]).map_background)

    def test_ortho_mesh(self):
        e = self.state([(21, [31, 8901], []), (LY.MESH_ORTHO, [31], []), (21, [30, 8905], [])])
        self.assertTrue(e.mesh_state[31]['ortho']); self.assertFalse(e.mesh_state[30].get('ortho', False))
        self.assertEqual(e.mesh_state[30]['off'], (0.0, 1.0))                     # MeshChara: texture scale (1, -1), offset (0, 1)
        e = self.state([(21, [31, 8901], []), (LY.MESH_ORTHO, [31], []), (21, [31, 8905], [])])
        self.assertFalse(e.mesh_state[31].get('ortho', False))                    # a new mesh in the slot: layer 0 again until the next packet


class EventCamera(unittest.TestCase):
    def setUp(self): self.mo = objects(fld.emv(femv(TWO)))

    def test_none_at_load(self): self.assertIsNone(self.mo.camera_view())

    def test_first_key_then_interpolation(self):
        mo = self.mo; mo.event_camera(1)
        self.assertEqual(mo.camera_view(), ((0.0, -2.0, -38.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        for _ in range(15): mo.tick()                                              # 30 sixtieths of a second: halfway
        pos, target, up = mo.camera_view()
        self.assertAlmostEqual(pos[0], 3.0); self.assertAlmostEqual(target[1], 3.0); self.assertEqual(up, (0.0, 1.0, 0.0))

    def test_zero_and_unknown_numbers(self):
        mo = self.mo; mo.event_camera(1); mo.event_camera(7)
        self.assertEqual(mo.camera_no, 1)                                          # SetCameraNo: a number outside the table keeps the one in progress
        held = mo.camera_view(); mo.event_camera(0)
        self.assertEqual(mo.camera_view(), held)                                   # update_emv no longer touches Camera.main: the last pose stays (the start menu keeps the castle behind it)
        mo.camera_engine(); self.assertIsNone(mo.camera_view())                    # until the engine's next camera packet

    def test_view_between_steps(self):
        mo = self.mo; mo.event_camera(1); mo.tick(); a = mo.camera_view(); mo.tick(); b = mo.camera_view()
        mid = mo.camera_view(0.5)
        for u, v, m in zip(a, b, mid):
            for x, y, z in zip(u, v, m): self.assertAlmostEqual(z, (x + y) / 2, places=5)          # the screen draws between two engine steps: the camera movement is interpolated too
        self.assertEqual(mo.camera_view(1.0), b)

    def test_movement_without_keys(self):
        mo = self.mo; mo.event_camera(2)
        self.assertEqual(mo.camera_view(), ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))

    def test_reload_and_savestate(self):
        mo = self.mo; mo.event_camera(1)
        for _ in range(10): mo.tick()
        copy = objects(fld.emv(femv(TWO))); copy.reinit(); copy.restore(mo.state, mo.auto, mo.event_state())
        self.assertEqual(copy.camera_view(), mo.camera_view())
        self.assertEqual(len(objects([]).event_state()), 2)                        # without a movement: the format of the savestates recorded before
        mo.reinit(); self.assertIsNone(mo.camera_view())


class Window(unittest.TestCase):
    """The window's methods called on stand-ins (no OpenGL)."""
    @classmethod
    def setUpClass(cls):
        try:
            from dq456_pc.window import camera as CAM
        except Exception as ex: raise unittest.SkipTest('window modules not importable here: %s' % ex)
        cls.CAM = CAM

    def stand_in(self, view, map_name='ev17'):
        mo = objects([dict(end=0, repeat=-1, delay=0, loop_delay=0, keys=[(0,) + view])]); mo.event_camera(1)
        return type('W', (), {'objects': mo, 'map_name': map_name})()

    def test_event_view_looks_at_the_target(self):
        e = ENGINE.State(); e.part = ENGINE.PART_TOWN; e.game_map = 'ev17'
        pos, fw, up = self.CAM.CameraMixin._event_view(self.stand_in(((0.0, -2.0, -38.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))), e)
        np.testing.assert_allclose(fw, np.array([0.0, 2.0, 38.0]) / math.hypot(2.0, 38.0), atol=1e-9)
        self.assertAlmostEqual(float(fw @ up), 0.0); self.assertGreater(up[1], 0.99)
        self.assertIsNone(self.CAM.CameraMixin._event_view(self.stand_in(((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)), 'other'), e))      # another map loaded in the window

    def test_ortho_matrix(self):
        w = type('W', (), {'map_name': 'ev17'})()
        M = self.CAM.CameraMixin._ortho_matrix(w, 16.0 / 9.0)
        title = self.CAM.TITLE_MAP == 'ev17'
        half_h = 128.53125 / (0.5625 if title else 1.0)
        np.testing.assert_allclose(M @ np.array([0.0, half_h, 6.0, 1.0]), [0.0, 1.0, 0.0, 1.0], atol=1e-9)
        np.testing.assert_allclose(M @ np.array([half_h * 16.0 / 9.0, 0.0, 0.0, 1.0]), [1.0, 0.0, 0.0, 1.0], atol=1e-9)


@unittest.skipUnless(os.path.isfile(os.path.join(APK5, 'split_UnityDataAssetPack.apk')), 'DQ_APK_DQ5 not set (folder of the 3 APK files of Dragon Quest V)')
class RealTitle(unittest.TestCase):
    def test_ev17(self):
        from dq456_pc.world import data as D
        import tempfile
        d = D.Data(os.path.join(APK5, 'split_UnityDataAssetPack.apk'), tempfile.mkdtemp(prefix='ev17_'), log=lambda *a: None)
        raw = d._map_text('ev17')
        cams = fld.emv(raw)
        self.assertEqual(len(cams), 5)
        frame, pos, target, up = cams[0]['keys'][0]
        np.testing.assert_allclose(pos, (0.0, -2.0948, -38.178), atol=1e-3); self.assertEqual(target, (0.0, 0.0, 0.0)); self.assertEqual(up, (0.0, 1.0, 0.0))
        self.assertEqual(fld.background(raw), (0x68 / 255.0, 0x8c / 255.0, 1.0))


if __name__ == '__main__':
    unittest.main()
