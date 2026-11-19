"""Behaviors of Dragon Quest V / VI's Unity layer that differ from DQ IV's (no window, no engine, no APK).

  python3 tests/test_dq56_screens.py

1. monster name plates (Make_MonsterName b__1, the three games): plates of one row that overlap are set 166 units apart, held within +-142;
2. the title's "Touchez l'ecran" (TapToStart): per-game waits, its window found by its type (DQ VI: port 13), the copyright texture's name, no chapter banner in DQ V / VI;
3. DQ VI's small world map: its two pictures and the exploration blocks (ICityMap b__2);
4. DQ VI's large world map: the pieces of MAP_DIFF fit in the two TextAssets (sizes of the game's data);
5. the touch pad's input modes (TouchPad.SetInputMode): field buttons per mode, DQ VI's extra button (vehicle command) and the static the engine keeps the mode in;
6. the layout of the game windows kept while they stay open (window_layout): a window that hides a part, closes or opens does not move the others (three games);
7. DQ VI's world map tiles (world_mesh: FieldData::setMeshInfo redone with numpy) against a tile by tile reading of the routine, on a made-up map in a made-up memory;
8. the raised flat triangles of a map kept in a file (flat_sceneries.shift): the same scenery from the file as from the search.
"""
import os, struct, sys, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core.plates import separate_plates
from dq456_pc.world import plans as PL
from dq456_pc.core import pad_modes as PM
from dq456_pc.core import window_layout as WL
from dq456_pc.core import world_mesh as WM
from dq456_pc.world import flat_sceneries as DP


class PadModes(unittest.TestCase):
    def test_dq4_has_no_modes(self):
        self.assertEqual(PM.shown('dq4', -1), {'map': True, 'menu': True, 'chat': True, 'bar': True, 'extra': False}); self.assertIsNone(PM.extra_icon('dq4', 3))

    def test_dq5_board_and_scope(self):
        self.assertEqual(PM.shown('dq5', -1), PM.shown('dq5', 0))
        self.assertEqual(PM.shown('dq5', 0), {'map': True, 'menu': True, 'chat': True, 'bar': True, 'extra': False})
        self.assertEqual(PM.shown('dq5', 1), {'map': False, 'menu': False, 'chat': False, 'bar': False, 'extra': False})          # T'n'T board, moving
        self.assertEqual(PM.shown('dq5', 3), {'map': False, 'menu': False, 'chat': False, 'bar': True, 'extra': False})           # scope
        self.assertEqual(PM.shown('dq5', 4), {'map': True, 'menu': False, 'chat': False, 'bar': True, 'extra': False})

    def test_dq6_vehicles(self):
        self.assertEqual([PM.extra_icon('dq6', m) for m in range(-1, 6)], [None, None, 52, None, 53, None, 54])            # Gourd Island, submarine, Pegasus
        self.assertEqual(PM.shown('dq6', 2), {'map': True, 'menu': False, 'chat': False, 'bar': True, 'extra': False})           # flying bed: no button
        self.assertEqual(PM.shown('dq6', 3), {'map': True, 'menu': True, 'chat': True, 'bar': True, 'extra': True})
        self.assertEqual(PM.shown('dq6', 5), {'map': True, 'menu': False, 'chat': True, 'bar': True, 'extra': True})
        self.assertEqual(PM.EXTRA_KEY, 0x2000)

    def test_static_address(self):
        # DQ VI: 23ff44 adrp x9, 0x32d000; ldrh w10, [x9, #0x10c] -> 0x32d10c. DQ V: 2986f4 -> 0x31607c
        self.assertEqual(PM.static_address((0xd0000769).to_bytes(4, 'little') + (0x7942192a).to_bytes(4, 'little'), 0x23ff44), 0x32d10c)
        self.assertEqual(PM.static_address((0xd00003e9).to_bytes(4, 'little') + (0x7940f92a).to_bytes(4, 'little'), 0x2986f4), 0x31607c)
        self.assertIsNone(PM.static_address(b'\x00' * 8, 0x1000))

    def test_adrp_add(self):
        # DQ V, TownSugorokuManager::getSingleton: 1feb9c adrp x8, 0x32d000; add x8, x8, #0x700 (guard); 1febac adrp x0, 0x32c000; add x0, x0, #0x50 (the manager)
        self.assertEqual(PM.adrp_add(0x1feb9c, 0xf0000968, 0x911c0108), 0x32d700)
        self.assertEqual(PM.adrp_add(0x1febac, 0xd0000960, 0x91014000), 0x32c050)
        self.assertIsNone(PM.adrp_add(0x1000, 0, 0))


class Plates(unittest.TestCase):
    def test_two_plates_apart(self):
        xs, zs = {0: -10.0, 1: 10.0}, {0: 105.0, 1: 105.0}
        separate_plates([0, 1], xs, zs); self.assertEqual(xs, {0: -83.0, 1: 83.0})

    def test_held_at_the_limit(self):
        xs, zs = {0: -130.0, 1: -120.0}, {0: 105.0, 1: 105.0}
        separate_plates([0, 1], xs, zs); self.assertEqual(xs, {0: -142.0, 1: 24.0})
        xs = {0: 120.0, 1: 130.0}
        separate_plates([0, 1], xs, zs); self.assertEqual(xs, {0: -24.0, 1: 142.0})

    def test_order_kept_when_reversed(self):
        xs, zs = {0: 10.0, 1: -10.0}, {0: 105.0, 1: 105.0}
        separate_plates([0, 1], xs, zs); self.assertEqual(xs, {0: 83.0, 1: -83.0})

    def test_other_rows_untouched(self):
        xs, zs = {0: -20.0, 1: 0.0, 2: 20.0}, {0: 69.0, 1: 127.0, 2: 69.0}
        separate_plates([0, 1, 2], xs, zs); self.assertEqual(xs, {0: -83.0, 1: 0.0, 2: 83.0})

    def test_far_apart(self):
        xs, zs = {0: -100.0, 1: 100.0}, {0: 105.0, 1: 105.0}
        separate_plates([0, 1], xs, zs); self.assertEqual(xs, {0: -100.0, 1: 100.0})


class TitleTouch(unittest.TestCase):
    def setUp(self): self.old = os.environ.get('DQ_GAME')

    def tearDown(self):
        if self.old is None: os.environ.pop('DQ_GAME', None)
        else: os.environ['DQ_GAME'] = self.old

    def test_waits_per_game(self):
        from dq456_pc.menus import pre_game as AP
        for g, w in (('dq4', 720), ('dq5', 799), ('dq6', 810)):
            os.environ['DQ_GAME'] = g; t = AP.TitleTouch(0, {})
            self.assertEqual(t.first_wait, w)
            for f in range(w): t.do_update(f)
            self.assertEqual(t.alpha, 0.0); t.do_update(w); self.assertGreater(t.alpha, 0.0)          # nothing before c_firstWait without the engine's CountReset

    def test_copyright_stays(self):
        from dq456_pc.menus import pre_game as AP
        os.environ['DQ_GAME'] = 'dq5'; t = AP.TitleTouch(0, {})
        for f in range(3000): t.do_update(f)
        self.assertEqual(t.alpha_c, 1.0)                                         # c_copyrightSecondWait 999999: DQ V / VI never fade it out
        os.environ['DQ_GAME'] = 'dq4'; t = AP.TitleTouch(0, {})
        for f in range(3000): t.do_update(f)
        self.assertEqual(t.alpha_c, 0.0)

    def test_resources(self):
        from dq456_pc.menus import pre_game as AP
        os.environ['DQ_GAME'] = 'dq6'; r = AP.resources()
        self.assertNotIn('ap_hyodai1.png', r)                                   # no chapter banner: the extraction no longer runs again at every launch
        self.assertEqual(r['ap_copyright.png'][2], 'Retro%d_copyright')
        os.environ['DQ_GAME'] = 'dq4'; self.assertIn('ap_hyodai1.png', AP.resources())
        self.assertEqual(AP.TITLE_TOUCH_TYPE, 73)


class Dq6WorldMap(unittest.TestCase):
    def test_small_map_blocks(self):
        first = np.zeros((192, 256, 3), np.uint8); second = np.full((192, 256, 3), 200, np.uint8)
        raw = first.tobytes() + second.tobytes()
        a = PL.dq6_world_picture(raw, (10 << 16) | 16, [0xffff] * 2 + [0xffbf] + [0xffff] * 13)
        self.assertEqual(a.shape, (192, 256, 4))
        self.assertEqual(a[16, 48, 0], 200)                                     # bit set: the second picture
        self.assertEqual(a[36, 108, 0], 0); self.assertEqual(a[45, 117, 0], 0)   # row 2, bit 6 clear: the first one
        self.assertEqual(a[5, 5, 0], 0); self.assertEqual(a[180, 250, 0], 0)    # outside the blocks: the first one
        self.assertIsNone(PL.dq6_world_picture(b'\0' * 10, 0, ()))

    def test_large_map_pieces(self):
        from dq456_pc.world import data as DO
        ends = {}
        for i, (off, x, y, w, h) in enumerate(DO.Data.WORLD_DIFF_DQ6):
            self.assertLessEqual(x + w, 1024); self.assertLessEqual(y + h, 1024)
            ends[i] = off + w * h * 3
        self.assertEqual(max(ends[i] for i in range(7)), 3222528)               # dq6ds_ulmap0: its 7 pieces fill the bytes after the 1024 x 1024 picture
        self.assertEqual(ends[7], 3151872)                                      # dq6ds_dlmap0: one piece


class LyingPose(unittest.TestCase):
    def test_square_quad_v2(self):
        from dq456_pc.core import lying_pose as PC
        r, u, f = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])            # camera looking along +z: the quad seen from straight on
        cam = np.array([0.0, 0.0, -20.0])
        for g, ratio in (('dq4', 0.75), ('dq5', 1.0), ('dq6', 1.0)):
            q = PC.vertices((0.0, 0.0, 0.0), 180.0, 0, 0.0, 1.0, (r, u, f), cam, g)
            w = abs(q[1] @ r - q[0] @ r); h = abs(q[2] @ u - q[1] @ u)
            self.assertAlmostEqual(w / h, ratio, delta=0.02)                 # DQ V / VI: a square lying mesh (+-0.32), DQ IV's 0.48 x 0.64 (its flat body: a little perspective)
        q = PC.vertices((0.0, 0.0, 0.0), 180.0, 0, 0.0, 1.0, (r, u, f), cam, 'dq5')
        zs = {round(float((v - cam) @ f), 4) for v in q}; self.assertEqual(len(zs), 1)          # one depth: the quad faces the camera

    def test_heights(self):
        from dq456_pc.core import lying_pose as PC
        self.assertAlmostEqual(PC.packet_height(0, 'dq5'), 0.194); self.assertAlmostEqual(PC.packet_height(4096, 'dq6'), 1.0)
        self.assertAlmostEqual(PC.packet_height(0), 0.3104)
        self.assertEqual(PC.OFFSETS_V2['dq5'][0], (0.0, 0.25)); self.assertEqual(PC.OFFSETS_V2['dq6'][0], (0.0, -0.125))


class WindowLayout(unittest.TestCase):
    W, H = 1280, 720

    def update(self, m, wins, frame, extra=(), cap=None):
        return m.update('field', wins, frame, self.W, self.H, 1.12, extra=extra, cap=cap)

    def test_fresh_is_the_former_layout(self):
        self.assertEqual(WL.fresh([(-398.0, -250.0)], self.W, self.H, 1.12)[0], 1.12)                 # one bottom window: full zoom
        k, gr, modes = WL.fresh([(-398.0, -250.0), (-185.0, 390.0)], self.W, self.H, 1.12)
        self.assertEqual(modes, ['bottom', 'top']); self.assertLess(k, 1.12)                            # two groups that would touch: smaller
        self.assertEqual(WL.fresh([(-400.0, 400.0)], self.W, self.H, 1.12)[0], 1.0)                    # the whole column: no zoom

    def test_window_that_hides_a_part_keeps_its_place(self):
        m = WL.Memory()
        k1, e1 = self.update(m, {(3, 47): (-398.0, 116.0)}, 10)                                         # slot machine: buttons and tokens (bottom group)
        k2, e2 = self.update(m, {(3, 47): (-300.0, 116.0)}, 11)                                         # reels started: buttons hidden, its middle would make it a centered group
        self.assertEqual((k1, e1), (k2, e2)); self.assertEqual(e1[(3, 47)], 'bottom')

    def test_closing_never_moves_the_others(self):
        m = WL.Memory()
        k1, e1 = self.update(m, {(1, 2): (-30.0, 380.0), (2, 11): (-398.0, -100.0)}, 10)              # two groups that make the scale smaller
        k2, e2 = self.update(m, {(1, 2): (-30.0, 380.0)}, 11)                                           # the bottom one closes: the other keeps its scale and its edge
        self.assertLess(k1, WL.fresh([(-30.0, 380.0)], self.W, self.H, 1.12)[0])
        self.assertEqual(k1, k2); self.assertEqual(e1[(1, 2)], e2[(1, 2)])

    def test_new_window_that_fits_moves_nothing_that_does_not_fit_shrinks(self):
        m = WL.Memory()
        k1, _ = self.update(m, {(1, 2): (300.0, 380.0)}, 10)
        k2, e2 = self.update(m, {(1, 2): (300.0, 380.0), (2, 0): (-398.0, -250.0)}, 11)              # fits at the same scale
        self.assertEqual(k1, k2)
        k3, _ = self.update(m, {(1, 2): (300.0, 380.0), (2, 0): (-398.0, -250.0), (4, 9): (-240.0, 290.0)}, 12)          # does not: smaller, for good
        self.assertLess(k3, k2)
        k4, _ = self.update(m, {(1, 2): (300.0, 380.0)}, 13); self.assertEqual(k4, k3)

    def test_afresh_after_a_pause_without_windows(self):
        m = WL.Memory()
        self.update(m, {(1, 2): (300.0, 380.0), (4, 9): (-240.0, 290.0)}, 10)
        k, _ = self.update(m, {}, 11); self.update(m, {}, 11 + WL.HOLD_FRAMES - 1)
        self.assertLess(self.update(m, {(1, 2): (300.0, 380.0)}, 11 + WL.HOLD_FRAMES - 1)[0], 1.12)          # (a short gap: kept)
        self.update(m, {}, 30); self.update(m, {}, 30 + WL.HOLD_FRAMES)
        self.assertEqual(self.update(m, {(1, 2): (300.0, 380.0)}, 30 + WL.HOLD_FRAMES)[0], 1.12)
        self.assertEqual(m.update('battle', {(1, 2): (300.0, 380.0)}, 99, self.W, self.H, 1.12)[0], 1.12)     # (another context: afresh)

    def test_cap_and_fits_at_scale_one(self):
        m = WL.Memory()
        self.assertEqual(self.update(m, {(5, 107): (-100.0, 200.0)}, 1, cap=1.0)[0], 1.0)              # shop picture: original scale
        self.assertTrue(WL.fits([(-398.0, 0.0, 'bottom'), (-10.0, 398.0, 'top')], 1.0, self.H))        # (the game's own layout: always right, even overlapping)
        self.assertFalse(WL.fits([(-398.0, 0.0, 'bottom'), (20.0, 380.0, 'top')], 1.12, self.H))

    def test_message_stays_up_until_it_closes(self):
        m = WL.Memory()
        self.assertEqual(m.message_offset(True, -40.0), -40.0)                                           # lowered
        self.assertEqual(m.message_offset(True, 0.0), 0.0)                                               # a window takes the bottom: up
        self.assertEqual(m.message_offset(True, -40.0), 0.0)                                             # the window went: still up
        self.assertEqual(m.message_offset(False, 0.0), 0.0); self.assertEqual(m.message_offset(True, -40.0), -40.0)     # a new message: lowered


class WorldMeshTiles(unittest.TestCase):
    """A made-up FieldData and CWorldMap in a made-up memory (dict of blocks), read by world_mesh.tile_uvs and by a plain transcription of setMeshInfo (0x22e778, libdq6core.so)."""
    LIB, FD, HDR, CELLS, ENTRIES, KINDS, NIBS = 0x10000000, 0x20000000, 0x21000000, 0x22000000, 0x23000000, 0x24000000, 0x25000000

    def setUp(self):
        rnd = np.random.RandomState(7); self.blocks = {}
        w, h, bw, bh = 6, 8, 8, 8; self.W, self.H = w * bw, h * bh          # (48 x 64 tiles: more rows than the 53 of a mesh, as the real maps)
        self.cells = rnd.randint(1, 40, size=(self.H, self.W)).astype(np.uint16)
        ent = np.zeros((40, 6), np.uint8); ent[:, 1] = rnd.choice([0, 8, 0x18, 3], size=40)
        ent[:, 2:4] = rnd.randint(-40, 900, size=40).astype('<i2').view(np.uint8).reshape(40, 2); ent[:, 4:6] = rnd.randint(0, 900, size=40).astype('<i2').view(np.uint8).reshape(40, 2)
        self.ent = ent; self.kinds = np.zeros((16, 8), np.uint8); self.kinds[:, 0] = rnd.randint(0, 6, size=16)
        self.nibs = rnd.randint(0, 256, size=self.W * self.H // 2 + 2).astype(np.uint8)
        self.corners = rnd.rand(256, 8).astype(np.float32)
        self.put(self.LIB + WM.CORNERS, self.corners.tobytes()); self.put(self.LIB + WM.ANIM_24, struct.pack('<h', 3)); self.put(self.LIB + WM.ANIM_8, struct.pack('<h', -2))
        for m in (0x638, 0x680): self.put(self.FD + m, struct.pack('<QQQQQQQ', self.HDR, 0, self.CELLS, 0, self.ENTRIES, self.KINDS, self.NIBS))
        self.put(self.HDR, bytes([w, h, bw, bh])); self.put(self.CELLS, self.cells.tobytes()); self.put(self.ENTRIES, ent.tobytes()); self.put(self.KINDS, self.kinds.tobytes()); self.put(self.NIBS, self.nibs.tobytes())
        self.put(self.FD + 0x6dc, struct.pack('<ii', 5, 7))

    def put(self, a, raw): self.blocks[a] = bytes(raw)

    def mem(self, a, n):
        for b, raw in self.blocks.items():
            if b <= a and a + n <= b + len(raw): return raw[a - b:a - b + n]
        raise KeyError(hex(a))

    def reference(self, opt, x0, y0):
        """setMeshInfo tile by tile, as read in the routine."""
        if opt == 0x301: x0 = y0 = 0
        def wrap(v, n): return v + n if v < 0 else v - n if v >= n else v
        out = np.zeros((53, 25, 8), np.float32)
        for r in range(53):
            y = wrap(y0 - 10 + r, self.H)
            for col in range(25):
                x = wrap(x0 - 4 + col, self.W)
                if opt == 0x201: tile = 3 + 7 + ((x & 3) | ((y & 3) << 2)); kind = 0          # (anim 3 + FieldData[0x6e0] 7)
                else:
                    e = self.ent[(int(self.cells[y, x]) - 1) & 0x3ff]; t2 = int(e[2:4].view('<i2')[0]); t4 = int(e[4:6].view('<i2')[0])
                    tile = t4 if e[1] == 0 else t2 + ((3 + 7) if e[1] == 0x18 else (-2 + 5) if e[1] == 8 else 0)          # (FieldData[0x6dc] 5, [0x6e0] 7)
                    i = y * self.W + x; b = int(self.nibs[i >> 1]); kind = int(self.kinds[(b >> 4) if i % 2 == 0 else (b & 15), 0])
                u = np.float32((tile & 31) / 32.0); v = np.float32(int(tile / 32) / 32.0) if tile >= 0 else np.float32(-((-tile) // 32) / 32.0)
                T = self.corners[kind]
                out[r, col] = [T[0] + u, T[1] + v, T[6] + u, T[7] + v, T[4] + u, T[5] + v, T[2] + u, T[3] + v]
        return out.reshape(53, 25, 4, 2)

    def test_like_the_routine(self):
        for opt, x0, y0 in ((0, 3, 4), (0x8001, 45, 38), (0x100, -2, 1), (0x201, 10, 20), (0x301, 30, 30)):
            self.put(self.FD + 0x6f4, struct.pack('<ii', x0, y0))
            sides = (0,) if opt == 0x301 else (-1, 0, 1)                    # (0x301: the origin 0, no neighbors: Engine._world_mesh)
            got = WM.tile_uvs(self.mem, self.LIB, self.FD, opt, sides)
            for k in sides:
                self.assertTrue(np.array_equal(got[k], self.reference(opt, x0 + 25 * k, y0)), (hex(opt), x0, y0, k))


class FlatScenery(unittest.TestCase):
    def scenery(self):
        """Two groups: an opaque lawn and a cut-out flower bed laid on it at the same height, plus a raised tile."""
        lawn = np.array([[0, 0, 0], [4, 0, 0], [0, 0, 4], [4, 0, 0], [4, 0, 4], [0, 0, 4]], np.float32)
        bed = np.array([[1, 0, 1], [3, 0, 1], [1, 0, 3], [5, 2, 5], [6, 2, 5], [5, 2, 6]], np.float32)
        tex_a = np.full((4, 4, 4), 255, np.uint8); tex_b = tex_a.copy(); tex_b[0, 0, 3] = 0
        z = lambda n: (np.zeros((n, 2), np.float32), np.ones((n, 4), np.float32))
        return {'groups': {'lawn': (lawn,) + z(6), ('tr', 'bed'): (bed,) + z(6)}, 'textures': {'lawn': tex_a, ('tr', 'bed'): tex_b}}

    def test_file_gives_the_same_scenery(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'flat.npy')
        a, b, c = self.scenery(), self.scenery(), self.scenery()
        self.assertEqual(DP.shift(a), 1); self.assertEqual(DP.shift(b, path), 1); self.assertTrue(os.path.exists(path)); self.assertEqual(DP.shift(c, path), 1)
        for k in a['groups']:
            self.assertTrue(np.array_equal(a['groups'][k][0], b['groups'][k][0])); self.assertTrue(np.array_equal(a['groups'][k][0], c['groups'][k][0]))
        self.assertAlmostEqual(float(a['groups'][('tr', 'bed')][0][0, 1]), DP.STEP)


if __name__ == '__main__':
    unittest.main()
