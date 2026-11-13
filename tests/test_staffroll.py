"""End credits: the staff roll of the ending (TownEndrollManager::setup ... isStaffRollEnd, then startTheEnd) is drawn by the window.

    DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> PYGLET_HEADLESS=1 python3 tests/test_staffroll.py

  1. the port of category 3 (StaffrollPort): creation, visibility, scroll offset (a float in two shorts), closing, in `Interface` (no data needed);
  2. the emulator's GL hooks copy what the engine uploads (glTexSubImage2D, RGBA / UNSIGNED_BYTE) into the textures the host has registered;
  3. `StaffrollMixin._draw_staffroll` in a real GL window (headless): black everywhere, quad A (second texture) over quad B (first) in the interface column, each texture shifted by the
     offset (rows that leave at the top come back at the bottom of the same quad), the credits' last picture no longer drawn once "The End" has started;
  4. (real engine) the whole sequence of Engine.start_the_end: the credits (port created, textures filled by the engine's own upload calls, offset +1/256 per frame), then startTheEnd (the packets
     21 of its three models are kept, the meshes appear), then the title screen.
"""
import os, struct, sys, types, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _paths          # (test helper)
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True
pyglet.options['shadow_window'] = False
from dq4_pc.core import engine as ENGINE
from dq4_pc.core import emu_core as EC
from dq4_pc.window import staffroll as SR

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def f2s(x):
    """A float as the two shorts the engine puts in a message (low one first)."""
    lo, hi = struct.unpack('<HH', struct.pack('<f', x)); return [lo, hi]


class PortMessages(unittest.TestCase):
    def test_create_show_scroll_close(self):
        ui = ENGINE.Interface(); self.assertIsNone(ui.staff)
        ui.apply([(0, [12, 1, 3, 0])])
        self.assertEqual((ui.staff['port'], ui.staff['live'], ui.staff['visible']), (12, True, False))
        ui.apply([(0, [12, 3, 1]), (12, [1]), (12, f2s(0.01171875))])
        self.assertTrue(ui.staff['visible']); self.assertEqual(ui.staff['offset'], 0.01171875)
        ui.apply([(12, [1]), (12, [0, 15360])])                                                 # (the engine's own pair of messages: 15360 << 16 = 1 / 128)
        self.assertEqual(ui.staff['offset'], 0.0078125)
        ui.apply([(12, [0, 16000])]); self.assertEqual(ui.staff['offset'], 0.0078125)           # (a float is read only after [1])
        ui.apply([(0, [12, 2])])
        self.assertEqual((ui.staff['live'], ui.staff['visible']), (False, False))

    def test_other_categories_are_not_the_credits(self):
        ui = ENGINE.Interface(); ui.apply([(0, [12, 1, 1, 21]), (0, [13, 1, 2, 3])]); self.assertIsNone(ui.staff)

    def test_old_savestate_has_no_attribute(self):
        ui = ENGINE.Interface(); st = dict(ui.__dict__); st.pop('staff', None); ui2 = ENGINE.Interface.__new__(ENGINE.Interface); ui2.__setstate__(st); self.assertIsNone(ui2.staff)


class GLHooks(unittest.TestCase):
    def fake(self, mem):
        return types.SimpleNamespace(gl_count={}, gl_calls=[], gl_textures={}, gl_bound=0, gl_serial=0, stack_arg=lambda n: 0x1000, mem=lambda a, n: mem[:n])

    def test_upload_into_registered_texture(self):
        band = np.arange(512 * 16 * 4, dtype=np.uint32).astype(np.uint8).tobytes()
        c = self.fake(band); img = np.zeros((512, 512, 4), np.uint8); c.gl_textures[7] = img
        EC.Core.h_glBindTexture(c, 3553, 7); EC.Core.h_glTexSubImage2D(c, 3553, 0, 0, 96, 512, 16, 6408, 5121)
        self.assertTrue((img[96:112] == np.frombuffer(band, np.uint8).reshape(16, 512, 4)).all()); self.assertFalse(img[:96].any()); self.assertFalse(img[112:].any()); self.assertEqual(c.gl_serial, 1)

    def test_other_texture_format_or_size_is_only_counted(self):
        c = self.fake(bytes(512 * 16 * 4)); img = np.zeros((512, 512, 4), np.uint8); c.gl_textures[7] = img
        EC.Core.h_glBindTexture(c, 3553, 9); EC.Core.h_glTexSubImage2D(c, 3553, 0, 0, 0, 512, 16, 6408, 5121); self.assertEqual(c.gl_serial, 0)          # (not registered)
        EC.Core.h_glBindTexture(c, 3553, 7); EC.Core.h_glTexSubImage2D(c, 3553, 0, 0, 500, 512, 16, 6408, 5121); self.assertEqual(c.gl_serial, 0)          # (past the end of the texture)
        EC.Core.h_glTexSubImage2D(c, 3553, 0, 0, 0, 512, 16, 6407, 5121); self.assertEqual(c.gl_serial, 0)                                                # (RGB)
        self.assertEqual(c.gl_count['glTexSubImage2D'], 3)


class Rows(unittest.TestCase):
    def test_visible_rows(self):
        self.assertEqual(SR.visible_rows(0.0), [(0, 512)]); self.assertEqual(SR.visible_rows(1.0), [(0, 512)])
        self.assertEqual(SR.visible_rows(0.25), [(128, 512), (0, 128)]); self.assertEqual(SR.visible_rows(0.30078125), [(154, 512), (0, 154)])
        self.assertEqual(SR.visible_rows(3.25), [(128, 512), (0, 128)])


def expected(y, hh, s, a_first=True):
    """Row of the picture (0-511) and of which texture (1 = engine's second texture, quad A, above the middle; 0 = the first) the window row `y` (pixels from the window's top, 800 high, unit = 1 pixel) shows."""
    d = y - hh / 2                                                  # pixels under the middle of the column
    zq = SR.QUAD_H; row_h = zq / 512
    if d < 0: tex, t = 1, zq + d                                    # quad A: t = distance from its top
    else: tex, t = 0, d
    k = int(t / row_h)                                               # displayed row index from the top of the quad
    return tex, (s + k) % 512


@unittest.skipUnless(os.environ.get('DISPLAY') or pyglet.options.get('headless'), 'needs a GL context (headless EGL or a display)')
class Drawing(unittest.TestCase):
    def setUp(self):
        from dq4_pc.window import field as FI
        try: self.win = pyglet.window.Window(1280, 800, visible=False)
        except Exception as ex: self.skipTest('no GL window: %s' % ex)
        w = self.win; self.ui = ENGINE.Interface(); self.ui.staff = {'port': 12, 'live': True, 'visible': True, 'offset': 100 / 512, 'ready': True, 'float_next': False, 'tex': []}
        for t in (0, 1):
            img = np.zeros((512, 512, 4), np.uint8); r = np.arange(512)
            img[..., 0] = (r // 2)[:, None]; img[..., 1] = 10 + 190 * t; img[..., 2] = 0; img[..., 3] = 255; self.ui.staff['tex'].append(img)          # (red = row / 2, green = which texture)
        self.over = False
        class Fake(SR.StaffrollMixin):
            _tex = FI.FieldMixin._tex
            width, height = 1280, 800
            def __init__(s): s.engine = types.SimpleNamespace(ui=self.ui, core=types.SimpleNamespace(gl_serial=1), the_end_started=lambda: self.over)
            def _ui_reference(s): return 640.0, 400.0, 1.0
            def clear(s): w.clear()
        self.fake = Fake()

    def tearDown(self): self.win.close()

    def shot(self):
        self.win.switch_to(); pyglet.gl.glViewport(0, 0, 1280, 800); pyglet.gl.glClearColor(0.5, 0.5, 0.5, 1.0); self.win.clear()
        self.win.projection = pyglet.math.Mat4.orthogonal_projection(0, 1280, 0, 800, -1, 1)
        self.fake._draw_staffroll()
        data = pyglet.image.get_buffer_manager().get_color_buffer().get_image_data().get_data('RGBA', 1280 * 4)
        return np.frombuffer(data, np.uint8).reshape(800, 1280, 4)[::-1]          # (row 0 = top of the window)

    def test_layout_and_offset(self):
        a = self.shot(); s = 100
        self.assertTrue((a[:, :100, :3] == 0).all() and (a[:, -100:, :3] == 0).all())                       # black beyond the column (the credits cover the whole window)
        for y in (3, 100, 300, 395, 404, 500, 700, 796):                                                    # inside the column: the expected row, expected texture
            tex, row = expected(y, 800, s); px = a[y, 640]
            self.assertAlmostEqual(int(px[1]), 10 + 190 * tex, delta=8, msg='y=%d texture' % y)              # green: which texture
            self.assertAlmostEqual(int(px[0]), row // 2, delta=7, msg='y=%d row %d' % (y, row))             # red: its row

    def test_no_picture_once_the_end_has_started(self):
        self.over = True; a = self.shot(); self.assertTrue((a[:, :, :3] == 0).all())                       # black only


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def test_whole_sequence(self):
        import tempfile, _saves as SV
        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_staff_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e): SV.settle(e, 200, 600); return e.state.part == ENGINE.PART_FIELD and SV.chapter(e) >= 5
        eng, _ = SV.pick_save(make, wanted, 'a save at chapter 5 or later')
        eng.start_town('caf2a')
        for _ in range(400): eng.step(0, 0)
        eng.start_the_end()
        self.assertEqual(eng.end_roll, 'credits'); self.assertFalse(eng.the_end_started())
        for _ in range(60): eng.step(ENGINE.A, ENGINE.A)                                              # (the keys do nothing during the end)
        st = eng.ui.staff
        self.assertTrue(st['live'] and st['visible'] and st['ready']); self.assertEqual(st['port'], 12)
        o1 = st['offset']
        for _ in range(100): eng.step(0, 0)
        self.assertAlmostEqual((st['offset'] - o1) % 1.0, 100 / 256, places=5)                         # 2 pixels of the 512 per frame
        n = eng.frames
        while eng.end_roll == 'credits' and eng.frames - n < 12000: eng.step(0, 0)
        self.assertEqual(eng.end_roll, 'the end'); self.assertTrue(7000 < eng.frames - n < 10000, eng.frames - n)          # (about 8800 frames: the whole credits)
        lit = [int((t[..., :3].sum(-1) > 0).sum()) for t in st['tex']]
        self.assertTrue(all(v > 1000 for v in lit), lit)                                                # both textures hold the engine's text (white and cyan)
        self.assertTrue((st['tex'][0][..., 3] == 255).all())                                           # opaque
        self.assertTrue(eng.the_end_started()); self.assertEqual(eng.state.models.get(1), 9951); self.assertEqual(eng.state.models.get(2), 9952)          # (the packets 21 of startTheEnd are kept)
        self.assertTrue(eng.state.cam_free)
        for _ in range(250): eng.step(0, 0)
        self.assertTrue(eng.state.meshes_seen)                                                          # the calligraphy's meshes are drawn
        while eng.end_roll is not None: eng.step(0, 0)
        for _ in range(240): eng.step(0, 0)
        self.assertEqual(eng.state.game_map, ENGINE.TITLE_MAP)                                          # back at the title screen
        self.assertFalse(eng.ui.staff['live'])                                                          # the port is closed


if __name__ == '__main__':
    unittest.main(verbosity=1)
