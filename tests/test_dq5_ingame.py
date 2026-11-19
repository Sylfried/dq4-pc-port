"""Dragon Quest V / VI in the game, without a window, an engine or an APK (DQ_APK_DQ5 / DQ_SAVES_DQ5 for the parts on real data):

1. adventure logs (logfile_format.FORMATS): DQ V (another version word, checksum over 0x2b78 bytes, the game's ID at + 0xc), DQ VI (an 8-byte header before "rate", checksum at
   + 0x10 over 0x2ee8 bytes, ID not known); DQ IV unchanged;
2. the message window's fields (engine_layout.msg_fields / canvas_fields): DQ IV's offsets, DQ V / VI's moved;
3. characters (packet 12): DQ V / VI keep texture, rows and mesh in their identifier; helpers.sheet_id; hd.pack_sheet_v2 cuts the cells where Chara.SetPattern puts them;
4. the start menu's simple windows: the "@cN" color codes are not shown;
5. the world map: the tile orientation of DQ V / VI (bits 12-15) turns the corners of the cell, orientation 0 is DQ IV's drawing; the animation offsets of drawBlock are the
   halfwords it reads with `ldrsh` from an `adrp` page that is still live; the end of an object animation uses each engine's table entry size; DQ VI's tile meshes (packet 28)
   and place icons (their own 512 x 512 texture);
6. battles: DQ VI's camera has no half turn;
7. particles (cmd_particle): read from the engine's arrays only once the system exists, placed like Unity's Transform, uvs brought back into the texture;
8. screen effects: DQ V / VI read the effect number and its flag elsewhere in the value; the game's sepia; the spotlight (its packet, its square on the window); DQ VI's mask; DQ VI's well (its calls, grid, texture coordinates, fades) and Pegasus (calls, lens, not awaited by the engine);
9. betting lines (MenuPortItemTable.IBetText): the codes @0 to @7 become Unity color tags;
10. end credits (EndrollPort / Endroll): layout of a section, shown on [0], scrolling, [1] at the end, DQ V's events at mid-screen; the port of category 3 is an EndrollPort in DQ V / VI.

    python3 tests/test_dq5_ingame.py
"""
import os, struct, sys, types, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.persistence import logfile_format as FJ
from dq456_pc.core import engine_layout as LY
from dq456_pc.core import engine as ENGINE
from dq456_pc.world import hd as HD

SAVES5 = os.environ.get('DQ_SAVES_DQ5', '')


def logfile(game, uid=0x1234, word0=FJ.MAGIC1):
    """A valid adventure log of `game` (plaintext, then encrypted)."""
    f = FJ.FORMATS[game]
    c = bytearray(FJ.LOGFILE_SIZE); c[:f.header] = b'\xd5' * f.header
    struct.pack_into('<II', c, f.header, word0, f.magic2)
    if f.uid is not None: struct.pack_into('<I', c, f.uid, uid)
    c[0x100] = 7
    struct.pack_into('<I', c, f.checksum, FJ.checksum(bytes(c), game)); return FJ.decrypt(bytes(c))


class Logfiles(unittest.TestCase):
    def test_each_game_reads_its_own(self):
        for game in ('dq4', 'dq5', 'dq6'):
            raw = logfile(game)
            self.assertIsNone(FJ.check('data1.dat', raw, game), game)
            for other in set(FJ.FORMATS) - {game}: self.assertIsNotNone(FJ.check('data1.dat', raw, other), (game, other))

    def test_damaged(self):
        for game in ('dq5', 'dq6'):
            raw = bytearray(logfile(game)); raw[0x100] ^= 1
            self.assertIsNotNone(FJ.check('data1.dat', bytes(raw), game))

    def test_game_ids(self):
        self.assertEqual(FJ.game_uid(logfile('dq5', 219), 'dq5'), 219)
        self.assertEqual(FJ.game_uid(logfile('dq4', 0x12345678), 'dq4'), 0x12345678)
        self.assertEqual(FJ.game_uid(logfile('dq6', 0x87654321), 'dq6'), 0x87654321)          # (DQ VI: at 0x14, the ID the port gives a new game)

    def test_empty_banks(self):
        for game in ('dq5', 'dq6'):
            f = FJ.FORMATS[game]; c = bytearray(FJ.LOGFILE_SIZE); struct.pack_into('<I', c, f.header, FJ.NEW)
            raw = FJ.decrypt(bytes(c))
            self.assertIsNone(FJ.check('data2.dat', raw, game)); self.assertIsNone(FJ.game_uid(raw, game))

    def test_dq4_unchanged(self):
        self.assertEqual(FJ.FORMATS['dq4'], (0, FJ.MAGIC2, 8, FJ.SUM_SIZE, FJ.UID_OFFSET))

    @unittest.skipUnless(os.path.isfile(os.path.join(SAVES5, 'data1.dat')), 'DQ_SAVES_DQ5 not set (a folder of Dragon Quest V saves)')
    def test_real_dq5_saves(self):
        for n in range(1, 6):
            p = os.path.join(SAVES5, 'data%d.dat' % n)
            if os.path.isfile(p):
                with open(p, 'rb') as fh: self.assertIsNone(FJ.check('data%d.dat' % n, fh.read(), 'dq5'), p)


class MessageFields(unittest.TestCase):
    def test_dq4(self):
        self.assertEqual(LY.msg_fields(False), {'active': 2, 'lines': 0x14, 'speed': 0x24, 'current': 0x40, 'end': 0x42})
        self.assertEqual(LY.canvas_fields(False), {'buffer': 0x10, 'port': 0x30, 'line_height': 0x42, 'cursor': 0x46, 'scroll': 0x4a})

    def test_dq5(self):                                        # ui_MsgLoop / ui_MsgSetup, CanvasSetup, SDrawCTRL::PutChar of libdq5core
        self.assertEqual(LY.msg_fields(True), {'active': 2, 'lines': 0x18, 'speed': 0x28, 'current': 0x44, 'end': 0x46})
        self.assertEqual(LY.canvas_fields(True), {'buffer': 0x18, 'port': 0x38, 'line_height': 0x4a, 'cursor': 0x4e, 'scroll': 0x52})
        self.assertEqual(LY.canvas_fields(8), LY.canvas_fields(True)); self.assertEqual(LY.canvas_fields(0), LY.canvas_fields(False))

    def test_canvas_shift_read_in_canvas_setup(self):          # DQ IV and VI: ldr x8, [x20, #0x30]; DQ V: ldr x8, [x20, #0x38]
        class Core: pass
        for word, shift in ((0xf9401a88, 0), (0xf9401e88, 8)):
            c = Core(); c.mem = lambda a, n, w=word: struct.pack('<4I', 0xaa0003f4, 0x94000000, w, 0xd65f03c0)[:n]
            self.assertEqual(LY.canvas_shift(c, 0), shift)

    def test_fixed_layout_is_dq4(self):
        lay = LY.Layout.fixed(0x10000000)
        self.assertEqual(lay.msg, LY.msg_fields(False)); self.assertEqual(lay.canvas, LY.canvas_fields(False))


class Characters(unittest.TestCase):
    def setUp(self): self.v2 = ENGINE.ENGINE_V2; ENGINE.ENGINE_V2 = True
    def tearDown(self): ENGINE.ENGINE_V2 = self.v2

    def test_identifier(self):
        e = ENGINE.State(); e.apply([(12, [8, 0x400CE], []), (12, [0, 0x9800C8], [])], lambda *a: '')
        self.assertEqual(e.sprites[8]['id'], 0x400CE); self.assertEqual(e.sprites[0]['id'], 0x1800C8)          # (bit 23, the shader, dropped)
        from dq456_pc.window.helpers import sheet_id
        self.assertEqual(sheet_id(e.sprites[8], False), HD.V2_KEY | 0x400CE)
        self.assertEqual(HD.sheet_key_v2(sheet_id(e.sprites[0], False)), (0xC8, 8, 1))
        e.apply([(12, [9, 0x41000 | 25], [])], lambda *a: '')
        self.assertEqual(sheet_id(e.sprites[9], True), HD.V2_KEY | 0x40019)          # (field mode, bit 12: not part of the sheet)

    def test_dq4_identifier(self):
        ENGINE.ENGINE_V2 = False
        from dq456_pc.window.helpers import sheet_id
        self.assertEqual(sheet_id({'id': 4096 + 12}, True), 12); self.assertEqual(sheet_id({'id': 4096 + 12}, False), 4108)

    def test_pack_four_rows(self):
        """Mesh 0 (0.64 x 0.64 panel, 32 x 32 cells): a 128 x 128 sheet, 4 rows of 4 columns, cut on the grid."""
        a = np.zeros((128, 128, 4), np.uint8)
        for y in range(4):
            for x in range(4): a[y * 32:(y + 1) * 32, x * 32:(x + 1) * 32] = (x, y, 0, 255)
        out, geo = HD.pack_sheet_v2(a, HD.V2_KEY | 4 << 16 | 25)
        self.assertEqual((geo['width'], geo['height'], geo['cols'], geo['nl']), (32, 32, 4, 4))
        self.assertAlmostEqual(geo['pw'], 0.64 / 0.48); self.assertAlmostEqual(geo['ph'], 1.0)
        self.assertEqual(tuple(out[2 * 32 + 5, 1 * 32 + 5, :2]), (1, 2))

    def test_pack_cell_smaller_than_its_step(self):
        """Mesh 3 (cells of 32 x 24 every 32 x 32 on a 256 x 256 sheet): each cell sits at the bottom of its box (Unity's v from the bottom: pv * (rows - 1 - y))."""
        a = np.zeros((256, 256, 4), np.uint8); a[32 + 8:64, 0:32] = (9, 9, 9, 255)          # row 1, bottom 24 pixels of its box
        out, geo = HD.pack_sheet_v2(a, HD.V2_KEY | 3 << 20 | 8 << 16 | 1)
        self.assertEqual((geo['width'], geo['height'], geo['nl']), (32, 24, 8))
        self.assertTrue((out[24:48, 0:32, 3] == 255).all()); self.assertFalse(out[0:24, 0:32, 3].any())


class SimpleMenus(unittest.TestCase):
    def test_color_codes_hidden(self):
        try: from dq456_pc.window import menu_display as MD
        except Exception as ex: raise unittest.SkipTest('window modules not importable here: %s' % ex)
        f = {'cells': {(0, 1): '@c51: Abel@c0', (0, 2): '@c5    Niv. 1\n Prologue@c0', (3, 0): 'Continuer'}}
        lines = MD.MenusMixin._menu_lines(None, f)
        self.assertTrue(all('@c' not in l[1] for l in lines))



class WorldMap(unittest.TestCase):
    def uv(self, g, v2):
        from dq456_pc.window import field as FI
        old = ENGINE.ENGINE_V2; ENGINE.ENGINE_V2 = v2
        try: return FI.FieldMixin._tile_uv(None, np.array([[g]], np.int32)).reshape(6, 2)
        finally: ENGINE.ENGINE_V2 = old

    def test_orientation_zero_is_dq4(self):
        for g in (0, 65, 1234, 4095): np.testing.assert_allclose(self.uv(g, True), self.uv(g, False))

    def test_orientation_turns_the_corners(self):
        base = self.uv(65, False); corners = base[[0, 1, 2, 5]]                     # NW, NE, SE, SW of the cell (two triangles: 0 1 2, 0 2 3)
        flipped = self.uv(65 | 1 << 12, True)[[0, 1, 2, 5]]                         # orientation 1: left and right edges swapped
        np.testing.assert_allclose(flipped, corners[[1, 0, 3, 2]])

    def test_halfword_refs_forget_overwritten_pages(self):
        class Core: LIB_BASE = 0
        words = [0x90000009 | (1 << 29),          # adrp x9, #0x1000 (from page 0)
                 0x79c00128 | (8 << 10),           # ldrsh w8, [x9, #0x10]
                 0x9ba92028,                       # umaddl x8, w1, w9, x8 (x8 rewritten)
                 0x79c00109 | (1 << 10),           # ldrsh w9, [x8, #2]: x8 is no longer a page
                 0xd65f03c0]
        c = Core(); c.mem = lambda a, n: struct.pack('<%dI' % len(words), *words)[:n]
        self.assertEqual(LY.halfword_refs(c, 0), [0x1010])

    def test_animation_entry_sizes(self):
        self.assertEqual(ENGINE.ANIM_ENTRY, (0x20, 0x24))

    def test_dq6_world_mesh_packet(self):
        """DQ VI's packet 28 (a = [opt]): bit 0 clear, the camera then the mesh position; bit 0 set, the mesh position only. Packet 27 starts another world (type, no mesh)."""
        e = ENGINE.State()
        e.apply([(27, [3], []), (28, [0x0], [100.0, 200.0, 8.0, -49.0, -16.0]), (28, [0x101], [408.0, -49.0, -16.0])], lambda: 'w')
        self.assertEqual((e.field_type, e.field_cam), (3, (100.0, 200.0)))
        self.assertEqual(e.field_meshes, {0x0: (8.0, -49.0, -16.0), 0x101: (408.0, -49.0, -16.0)})
        e.apply([(27, [1], [])], lambda: 'w')
        self.assertEqual((e.field_type, e.field_cam, e.field_meshes), (1, None, {}))

    def test_dq6_icons_fit_their_texture(self):
        """DQ VI's place icons: (ox, bottom, w, h) inside the 512 x 512 `symbol` texture; (u0, v0) as FieldSymbol.SetUV gives it for icon 0 (0, 0, 0.125, 0.125)."""
        from dq456_pc.window import constants as CO
        icons = CO.CH_ICONS_V2['dq6']
        self.assertEqual(len(icons), 52)
        for ox, bottom, w, h in icons.values(): self.assertTrue(0 <= ox and ox + w <= 512 and 0 <= bottom - h and bottom <= 512)
        ox, bottom, w, h = icons[0]
        self.assertEqual((ox / 512, 1 - bottom / 512, (ox + w) / 512, 1 - (bottom - h) / 512), (0.0, 0.0, 0.125, 0.125))



class Battles(unittest.TestCase):
    def test_dq6_camera_has_no_half_turn(self):
        """SceneCamera.Update without a target: Euler(-x, -(y + 180), z) in DQ IV and V; DQ VI's engine sends the yaw already turned (0 where DQ V sends 180)."""
        self.assertEqual(ENGINE.battle_camera_euler((-0.703, 180.0, 0.0), 180.0), (0.703, -360.0, 0.0))
        self.assertEqual(ENGINE.battle_camera_euler((-0.703, 0.0, 0.0), 0.0), (0.703, -0.0, 0.0))
        self.assertEqual(ENGINE.BATTLE_YAW, 180.0 if ENGINE.GM.profile().key != 'dq6' else 0.0)


class Particles(unittest.TestCase):
    """DQ V / VI ParticleSystem: the engine writes the particles in the five arrays given to ParticleSystemInit, then sends cmd_particle (func | count << 8)."""
    def engine(self):
        mem = bytearray(0x40000)
        bases = [0x1000 + 0x8000 * k for k in range(5)]                    # position and scale, indices, vertices, uvs, colors
        struct.pack_into('<6f', mem, bases[0], 0.0, 0.0, 1.2, 1.0, 1.0, -1.0)
        struct.pack_into('<12i', mem, bases[1], 0, 3, 1, 1, 3, 2, 4, 7, 5, 5, 7, 6)
        struct.pack_into('<12f', mem, bases[2], -1.0, 4.0, -9.0, -0.8, 4.0, -9.0, -0.8, 3.8, -8.8, -1.0, 3.8, -8.8)
        struct.pack_into('<8f', mem, bases[3], 0.0, -0.375, 0.125, -0.375, 0.125, -0.5, 0.0, -0.5)
        mem[bases[4]:bases[4] + 16] = bytes([255, 255, 255, 251] * 4)
        core = types.SimpleNamespace(particles=bases, mem=lambda a, n: bytes(mem[a:a + n]))
        m = ENGINE.Engine.__new__(ENGINE.Engine); m.core = core; m.state = ENGINE.State()
        return m

    def test_nothing_without_init(self):
        m = self.engine(); m._particle(3)                             # c03_update before any c00 / c01: Unity's s_self is null, nothing is drawn
        self.assertIsNone(m.state.particles)

    def test_init_update_release(self):
        m = self.engine(); m._particle(0 | 6 << 8)                    # c00_init_town: one particle (6 indices)
        p = m.state.particles
        self.assertEqual((p['field'], p['pos'], p['scale'], list(p['idx'])), (False, (0.0, 0.0, 1.2000000476837158), (1.0, 1.0, -1.0), [0, 3, 1, 1, 3, 2]))
        xyz, uv, col = ENGINE.particle_vertices(p)
        np.testing.assert_allclose(xyz[0], (-1.0, 4.0, 10.2), atol=1e-5)          # position + scale x vertex (z turned over)
        np.testing.assert_allclose(sorted(set(uv[:, 1].round(4))), (0.5, 0.625))     # uvs below 0 moved up by one texture: the same rows
        self.assertAlmostEqual(float(col[0, 3]), 251 / 255.0)
        m._particle(1 | 6 << 8); self.assertTrue(m.state.particles['field'])          # c01_init_field: layer 9
        m._particle(4); self.assertIsNone(m.state.particles)


class ScreenEffects(unittest.TestCase):
    def test_v2_effect_number_and_flag(self):
        """Capture.ScreenEffect: DQ IV reads the effect in value & 0xf and bReverse / bMorning in bit 7; DQ V / VI in value & 0xff and bit 15 (the arrival of a trip is 0x8003)."""
        self.assertEqual((ENGINE.EFFECT_KIND, ENGINE.EFFECT_FLAG), (0xff, 0x8000) if ENGINE.ENGINE_V2 else (0xf, 0x80))
        old = ENGINE.EFFECT_KIND, ENGINE.EFFECT_FLAG
        try:
            for (kind, flag), value in (((0xf, 0x80), 0x83), ((0xff, 0x8000), 0x8003)):
                ENGINE.EFFECT_KIND, ENGINE.EFFECT_FLAG = kind, flag
                m = ENGINE.Engine.__new__(ENGINE.Engine); m.state = ENGINE.State(); m._effect_flag = lambda active: None
                m._start_screen_effect(value)
                self.assertEqual((m.state.screen_effect['kind'], m.state.screen_effect['inverse']), ('tabi', True))
        finally: ENGINE.EFFECT_KIND, ENGINE.EFFECT_FLAG = old

    def test_spotlight_packet(self):
        """Effect 7: bit 8 creates (x, y, z, torch = bit 11), bit 9 side color, bit 10 light color, in that order of the floats; size = value >> 16, visible = bit 12; bit 15 releases."""
        m = ENGINE.Engine.__new__(ENGINE.Engine); m.state = ENGINE.State()
        m._spotlight(0x400 | 0x200 | 7, [0.1] * 8); self.assertIsNone(m.state.spotlight)                  # no Create yet: nothing
        m._spotlight((48 << 16) | 0x1000 | 0x800 | 0x400 | 0x100 | 7, [1.0, 2.0, 3.0, 0.9, 0.8, 0.7, 0.5])
        sp = m.state.spotlight
        self.assertEqual((sp['pos'], sp['torch'], sp['size'], sp['visible'], sp['light'], sp['side']), ((1.0, 2.0, 3.0), True, 48, True, (0.9, 0.8, 0.7, 0.5), (1.0, 1.0, 1.0, 1.0)))
        m._spotlight((20 << 16) | 0x100 | 0x200 | 7, [9.0, 9.0, 9.0, 0.0, 0.0, 0.0, 1.0])                    # a second Create keeps the first one (its floats are skipped)
        self.assertEqual((sp['pos'], sp['side'], sp['size'], sp['visible']), ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0), 20, False))
        m._spotlight(0x8007, []); self.assertIsNone(m.state.spotlight)

    def test_spotlight_square(self):
        from dq456_pc.render import spotlight as SP
        M = np.eye(4)
        (cx, cy), h = SP.square((0.0, 0.0, 0.0), 54, M, 1280, 720, 1.0)
        self.assertAlmostEqual(cx, 640.0); self.assertAlmostEqual(cy, 360.0 + 0.04 * 16 / 9 * 720)       # raised by 0.04 of the phone's height
        self.assertAlmostEqual(h, 64 / 256.0 * 360.0)                                                      # (54 + 10) / 256 of half the phone's short side
        rects = SP.side_rects((cx, cy), h, 1280, 720)
        self.assertAlmostEqual(sum(w * hh for x, y, w, hh in rects) + (2 * h) ** 2, 1280 * 720)
        self.assertIsNone(SP.square((0.0, 0.0, 0.0), 54, np.diag([1.0, 1.0, 1.0, -1.0]), 1280, 720, 1.0))

    def test_mask(self):
        """DQ VI effect 11: its picture puts the texture's bottom right corner at the center, mirrored; its square is as wide as the phone."""
        self.assertEqual(ENGINE.SCREEN_MASK, 11)
        from dq456_pc.render import spotlight as SP
        q = np.zeros((4, 4, 4), np.uint8); q[3, 3] = (1, 2, 3, 4)
        pic = SP.mask_picture(q)
        self.assertEqual(pic.shape, (8, 8, 4))
        self.assertEqual([tuple(pic[y, x]) for y, x in ((3, 3), (3, 4), (4, 3), (4, 4))], [(1, 2, 3, 4)] * 4)
        self.assertEqual(SP.mask_square(1280, 720, 1.0), ((640.0, 360.0), 360.0))

    def test_well(self):
        from dq456_pc.render import ido_effect as ID
        from dq456_pc.render import capture_effects as EC
        self.assertEqual((ID.div_y(9 / 16), ID.div_y(16 / 9)), (56, 18))                                   # (int)(32 / aspect): the phone, a 16:9 window
        vt, idx = ID.grid(2, 2)
        self.assertEqual((len(vt), len(idx)), (16, 24))
        self.assertEqual([tuple(v) for v in vt[:4]], [(-1.0, 1.0, 0.5), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.5)])        # even cell
        self.assertEqual([tuple(v) for v in vt[4:8]], [(0.0, 0.0, 0.0), (0.0, 1.0, 0.5), (1.0, 0.0, 0.5), (1.0, 1.0, 0.0)])         # odd cell
        uv = ID.texture_coords(np.array([[1.0, 1.0, 0.5], [1.0, 1.0, 0.0], [-1.0, -1.0, 0.5]], np.float32), 0.25, -0.5)
        np.testing.assert_allclose(uv, [[1.25, 1.25], [0.5, 0.5], [0.0, 0.0]])
        for arrival, calls in ((False, 64), (True, 65)):
            sim = ID.IdoEffect(arrival, 16 / 9); n = 0
            while sim.stage(): n += 1
            self.assertEqual((n + 1, EC.frames_of('ido', arrival)), (calls, calls))
        sim = ID.IdoEffect(False, 16 / 9)
        for _ in range(3): sim.stage()
        self.assertTrue(sim.render_active); self.assertEqual((sim.ca, float(sim.trail_alpha)), (0, 0.0))
        for _ in range(15): sim.stage()
        self.assertAlmostEqual(float(sim.strength()), 1.0); self.assertAlmostEqual(float(sim.trail_alpha), 0.6, places=6)
        self.assertEqual(EC.IDO_FADES[False], ((43, 'out', 20),))
        m = ENGINE.Engine.__new__(ENGINE.Engine); m.state = ENGINE.State(); m._effect_flag = lambda active: None
        m._start_screen_effect(0x800a if ENGINE.ENGINE_V2 else 0x8a)
        if ENGINE.ENGINE_V2: self.assertEqual((m.state.screen_effect['kind'], m.state.screen_effect['inverse'], m.state.screen_effect['frames']), ('ido', True, 65))
        else: self.assertIsNone(m.state.screen_effect)                                                    # DQ IV has no effect 10

    def test_pegasus(self):
        import math
        from dq456_pc.render import pegasus_effect as PG
        from dq456_pc.render import capture_effects as EC
        self.assertEqual((PG.call_count(False), PG.call_count(True)), (82, 43))                              # 2 + 71 + 9 afterimage steps; 2 + 41
        self.assertEqual((EC.frames_of('pegasus', False), EC.frames_of('pegasus', True)), (82, 43))
        vt, idx = PG.grid(2, 2)
        self.assertAlmostEqual(float(vt[0, 2]), (math.cos(1.0) + math.cos(-1.0)) * 0.5 - 0.3, places=6)
        uv = PG.texture_coords(np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 0.5]], np.float32), 0.2)
        np.testing.assert_allclose(uv, [[0.8, 0.5], [0.5, 0.5]], atol=1e-6)                             # the lens pulls the edges in; the center stays
        sim = PG.PegasusEffect(False, 16 / 9)
        for _ in range(2): sim.stage()
        self.assertEqual((sim.ca, float(sim.grid_color), float(sim.trail_alpha)), (0, 1.0, 0.0))
        for _ in range(70): sim.stage()
        self.assertEqual((sim.ca, float(sim.grid_color)), (70, 0.0)); self.assertAlmostEqual(float(sim.trail_alpha), 0.9, places=6)
        while sim.stage(): pass
        self.assertEqual(sim.final_fade, 'black')
        m = ENGINE.Engine.__new__(ENGINE.Engine); m.state = ENGINE.State(); flags = []; m._effect_flag = flags.append
        m._start_screen_effect(0x0009 if ENGINE.ENGINE_V2 else 0x09)
        if ENGINE.ENGINE_V2:
            self.assertEqual((m.state.screen_effect['kind'], m.state.screen_effect['duration'], flags), ('pegasus', 82, []))      # not awaited: no flag, not shortened
            ENGINE.State.fade_speed, old = 3.0, ENGINE.State.fade_speed
            try:
                m.state.screen_effect = None; m._start_screen_effect(0x8009); self.assertEqual(m.state.screen_effect['duration'], 43)
            finally: ENGINE.State.fade_speed = old
        else: self.assertIsNone(m.state.screen_effect)

    def test_sepia_final_pass(self):
        """DQ V / VI effect 8 (Custom/Sepia): gray = mean of r, g, b, plus (0.109375; -0.0546875; 0), in the final pass, before the player's display settings (read as text: the module needs a window)."""
        with open(os.path.join(HERE, '..', 'dq456_pc', 'render', 'postfx.py'), encoding='utf-8') as fh: src = fh.read()
        self.assertIn('vec3((c.r + c.g + c.b) * 0.333333343) + vec3(0.109375, -0.0546875, 0.0)', src)
        self.assertLess(src.index('game_sepia > 0.5'), src.index('filtered > 0.5'))
        self.assertEqual(ENGINE.SCREEN_SEPIA, 8)


class BettingLines(unittest.TestCase):
    def test_codes(self):
        try: from dq456_pc.menus import ui_menu as UI
        except Exception as ex: raise unittest.SkipTest('window modules not importable here: %s' % ex)
        self.assertEqual(UI.bet_text('@11@0-@22@0 x3'), '<color=#ff84ffff>1</color>-<color=#31ceffff>2</color> x3')
        self.assertEqual(UI.bet_text('7.5'), '7.5')


class EndCredits(unittest.TestCase):
    """Endroll (core/endroll.py): a fake section of three lines, the second one flagged (an event in DQ V) and light blue."""
    @staticmethod
    def layout(lines, height=2400):
        return struct.pack('<3H', len(lines), 512, height) + b''.join(struct.pack('<7H', *ln) for ln in lines)

    def assets(self, game='dq5'):
        a = {'Retro%s_endroll_en_01.bin' % game[-1]: self.layout([(0, 100, 20, 206, 950, 2, 2), (3, 200, 22, 156, 1000, 2, 30), (0, 120, 20, 196, 1040, 2, 60)])}
        return a.get

    def test_layout(self):
        from dq456_pc.core import endroll as ER
        st = ER.setup('dq5', 0, self.assets())
        self.assertEqual(len(st['lines']), 3)
        self.assertEqual((st['lines'][0]['x'], st['lines'][0]['y'], st['lines'][1]['color'], st['lines'][0]['color']), (-50, 950, ER.BLUE, ER.WHITE))
        self.assertAlmostEqual(st['counter'], 0.5 * 2400 - 2 * ER.START_Y, places=3)
        self.assertEqual(len(st['timers']), 1)
        self.assertIsNone(ER.setup('dq5', 1, self.assets()))                          # no layout: nothing
        self.assertEqual(ER.setup('dq6', 0, self.assets('dq6'))['timers'], [])        # DQ VI: no events

    def test_scroll_events_end(self):
        from dq456_pc.core import endroll as ER
        st = ER.setup('dq5', 0, self.assets())
        self.assertEqual(ER.update(st), [])                                          # hidden until the engine sends [0]: does not move
        ER.notice(st, [5]); self.assertFalse(st['shown'])
        ER.notice(st, [0]); self.assertTrue(st['shown'])
        sent = []
        for frame in range(1, 450):
            for m in ER.update(st): sent.append((frame, m))
        ev = (0.5 * 1000 - ER.START_Y) / 1.82; end = (0.5 * 2400 - 2 * ER.START_Y) / 1.82
        self.assertEqual([m for _, m in sent], [(0, ER.EVENTS[0]), (1,)])
        self.assertLessEqual(abs(sent[0][0] - ev), 1); self.assertLessEqual(abs(sent[1][0] - end), 1)
        self.assertAlmostEqual(st['pos'], ER.START_Y + 449 * 1.82, places=2)

    def test_visible_lines(self):
        from dq456_pc.core import endroll as ER
        st = ER.setup('dq5', 0, self.assets()); st['shown'] = True
        self.assertEqual(ER.visible_lines(st, 228.5), [])                             # the column starts under the screen
        st['pos'] = 0.5 * 1000                                                       # the flagged line at mid-screen
        vis = ER.visible_lines(st, 228.5)
        self.assertIn(1000, [ln['y'] for ln, x, top, s in vis])
        self.assertTrue(any(abs(top) < 1e-6 for ln, x, top, s in vis if ln['y'] == 1000))

    def test_port_of_category_3(self):
        ui = ENGINE.Interface(); ui.obs = None
        ui.apply([(0, [12, 1, 3, 2])])
        if ENGINE.ENGINE_V2: self.assertEqual((ui.endroll['port'], ui.endroll['type'], ui.staff), (12, 2, None))
        else: self.assertEqual((ui.staff['port'], ui.endroll), (12, None))
        ui.apply([(12, [0])])
        if ENGINE.ENGINE_V2: self.assertEqual(ui.endroll['pending'], [[0]])         # the layouts are read by the engine's next frame
        ui.apply([(0, [12, 2])])
        self.assertFalse((ui.endroll if ENGINE.ENGINE_V2 else ui.staff)['live'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
