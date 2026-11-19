"""Tests of the lying poses (packets 16 / 17 / 18): packet decoding (State.apply, no engine) and geometry (lying_pose.py, no window); with the real engine (if DQ_APK and DQ_SAVES
are given): the map taf1 (green-tiled castle, soldier in blue armor in slot 8) does send packet 16 0x0c000508 and packet 17 [1040, 1863].

    python3 tests/test_lying_pose.py
    DQ_APK=... DQ_SAVES=... python3 tests/test_lying_pose.py      (adds the real engine test)
"""
import os, sys, math, shutil, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _saves as SV
from dq456_pc.core import engine as ENGINE
from dq456_pc.core import lying_pose as PC


def map_name(): return 'carte_test'


def camera(pitch_deg=47.03, yaw_deg=0.0, position=(0.0, 28.94, -26.96)):
    """Town camera: (right, up, forward) and position; pitch looks downward, yaw turns toward +X."""
    t, l = math.radians(pitch_deg), math.radians(yaw_deg)
    f = np.array([math.sin(l) * math.cos(t), -math.sin(t), math.cos(l) * math.cos(t)])
    r = np.cross([0.0, 1.0, 0.0], f); r /= np.linalg.norm(r)
    u = np.cross(f, r)
    return (r, u, f), np.array(position, float)


def screen_page(P, cam, border):
    """Screen coordinates (focal length 1) of a world point and depth."""
    r, u, f = border; v = np.asarray(P, float) - cam; z = float(v @ f)
    return float(v @ r) / z, float(v @ u) / z, z


class TestPackets(unittest.TestCase):
    def setUp(self): self.e = ENGINE.State(); self.e.apply([(12, [8, 18], []), (12, [9, 7], [])], map_name)

    def apply(self, *p): self.e.apply(list(p), map_name)

    def test_real_values_of_taf1(self):
        self.apply((17, [1040, 1863], []), (16, [0x0c000508], []))
        s = self.e.sprites[8]
        self.assertTrue(s['sleeping'])
        self.assertAlmostEqual(s['sleeping_rot'][0], -90.0, places=3)             # 0xc000 / -182,0444 + 180
        self.assertEqual(s['sleeping_rot'][1], 3)
        self.assertAlmostEqual(self.e.sleeping_height, 1863 * 1.6 / 8192, places=6)

    def test_mlb1a_values(self):
        self.apply((16, [0x500], []), (16, [0x501], []))                    # lie down with no precise angle: 0 -> 180 degrees
        self.assertNotIn('sleeping', self.e.sprites[8])                              # (no packet for slot 8)
        self.apply((12, [0, 106], []), (12, [1, 130], []), (16, [0x0c000500], []), (16, [0x08000501], []))
        self.assertAlmostEqual(self.e.sprites[0]['sleeping_rot'][0], -90.0, places=3); self.assertEqual(self.e.sprites[0]['sleeping_rot'][1], 3)
        self.assertAlmostEqual(self.e.sprites[1]['sleeping_rot'][0], 0.0, places=3); self.assertEqual(self.e.sprites[1]['sleeping_rot'][1], 2)

    def test_get_back_up(self):
        self.apply((16, [0x0c000508], []))
        self.assertTrue(self.e.sprites[8]['sleeping'])
        self.apply((16, [0x208], []))                                       # DisplayCharacter::setSleepFlag(0)
        self.assertFalse(self.e.sprites[8]['sleeping'])

    def test_direction_change_while_dormant(self):
        self.apply((16, [0x0c000508], []), (16, [0x08000408], []))          # DisplayCharacter::draw: 0x400 | angle << 12 (without bits 8 / 9: the sleep continues)
        s = self.e.sprites[8]
        self.assertTrue(s['sleeping']); self.assertAlmostEqual(s['sleeping_rot'][0], 0.0, places=3)

    def test_default_height_and_persistence(self):
        self.assertEqual(self.e.sleeping_height, 0.0)                                 # Chara..cctor: y = 0 as long as there is no packet 17
        self.apply((17, [1105, 0], []))
        self.assertAlmostEqual(self.e.sleeping_height, 0.3104, places=6)
        self.apply((17, [1105, 794], []))
        self.assertAlmostEqual(self.e.sleeping_height, 794 * 1.6 / 8192, places=6)
        self.apply((0, [], []))                                             # new map: the Chara static remains
        self.assertAlmostEqual(self.e.sleeping_height, 794 * 1.6 / 8192, places=6)

    def test_pose_changes_sheet(self):
        self.apply((18, [8 | (21 << 8)], []))
        self.assertEqual(self.e.sprites[8]['id'], 21)
        self.apply((18, [9 | (4 << 8)], []))
        self.assertEqual(self.e.sprites[9]['id'], 4)
        self.apply((18, [77 | (4 << 8)], []))                               # unknown slot: no effect, no crash
        self.assertNotIn(77, self.e.sprites)

    def test_packet_without_sprite(self):
        self.apply((16, [0x0c000563], []))                                  # unknown slot
        self.assertNotIn(0x63, self.e.sprites)

    def test_old_state_without_dormant_top(self):
        e = ENGINE.State(); d = dict(e.__dict__); d.pop('sleeping_height'); e2 = ENGINE.State.__new__(ENGINE.State); e2.__setstate__(d)
        self.assertEqual(e2.sleeping_height, 0.0)


class TestGeometry(unittest.TestCase):
    def test_decoding(self):
        self.assertEqual(PC.packet_direction(0x500), (180.0, 0))
        a, q = PC.packet_direction(0x0c000500); self.assertAlmostEqual(a, -90.0, places=3); self.assertEqual(q, 3)
        a, q = PC.packet_direction(0x04000500); self.assertAlmostEqual(a, 90.0, places=3); self.assertEqual(q, 1)
        a, q = PC.packet_direction(0x08000500); self.assertAlmostEqual(a, 0.0, places=3); self.assertEqual(q, 2)

    def test_head_on_screen(self):
        # direction 0 = head up, 0x4000 = left, 0x8000 = down, 0xc000 = right
        for d16, expected in ((0x0, 0), (0xc000, 90), (0x8000, 180), (0x4000, 270)):
            a, _ = PC.packet_direction(0x400 | (d16 << 12)); self.assertAlmostEqual(PC.head_on_screen(a), expected, places=2)

    def corners(self, d16, tang=47.03, yaw=0.0, topmost=0.0, ui_scale=2.25, pos=(0.0, 0.0, 0.0)):
        border, cam = camera(tang, yaw); a, q = PC.packet_direction(0x400 | (d16 << 12))
        return PC.vertices(pos, a, q, topmost, ui_scale, border, cam), border, cam

    def test_screen_size_without_shortcut(self):
        # the flat body keeps its sheet size on screen: width 0.48 x 2.25 = 1.08, height 1.44, whatever the camera tilt
        for tang in (30.0, 47.03, 70.0):
            for d16 in (0, 0x8000):
                (a, b, c, d), border, cam = self.corners(d16, tang)
                pa, pb, pc, pd = (np.array(screen_page(P, cam, border)[:2]) for P in (a, b, c, d))
                z = float(np.mean([screen_page(P, cam, border)[2] for P in (a, b, c, d)]))           # depth of the body's center
                self.assertAlmostEqual(np.linalg.norm(pb - pa) * z, 1.08, delta=0.02)          # bottom left -> bottom right
                self.assertAlmostEqual(np.linalg.norm(pd - pa) * z, 1.44, delta=0.02)          # bottom left -> top left
                self.assertAlmostEqual(float((pb - pa) @ (pd - pa)), 0.0, delta=1e-3)          # rectangle, no shear

    def test_head_up_for_direction_0(self):
        (a, b, c, d), border, cam = self.corners(0)
        pa, pd = np.array(screen_page(a, cam, border)[:2]), np.array(screen_page(d, cam, border)[:2])
        self.assertGreater(pd[1], pa[1] + 0.01); self.assertAlmostEqual(pd[0], pa[0], delta=1e-3)         # the top of the sheet is at the top of the screen

    def test_four_directions(self):
        expected = {0x0: (0, 1), 0xc000: (1, 0), 0x8000: (0, -1), 0x4000: (-1, 0)}           # "feet -> head" vector on screen
        for d16, v in expected.items():
            (a, b, c, d), border, cam = self.corners(d16)
            pa, pd = np.array(screen_page(a, cam, border)[:2]), np.array(screen_page(d, cam, border)[:2]); w = (pd - pa) / np.linalg.norm(pd - pa)
            self.assertAlmostEqual(w[0], v[0], delta=0.01, msg=hex(d16)); self.assertAlmostEqual(w[1], v[1], delta=0.01, msg=hex(d16))

    def test_no_mirror(self):
        # bottom left -> bottom right then bottom left -> top left: same rotation direction as the standing sheet (positive cross product on screen)
        for d16 in (0, 0x4000, 0x8000, 0xc000):
            (a, b, c, d), border, cam = self.corners(d16)
            pa, pb, pd = (np.array(screen_page(P, cam, border)[:2]) for P in (a, b, d))
            v1, v2 = pb - pa, pd - pa; self.assertGreater(v1[0] * v2[1] - v1[1] * v2[0], 0.0, msg=hex(d16))

    def test_turned_camera_turns_body(self):
        # the camera turns 90 degrees: the body (world) turns the other way on screen: head right (0xc000) becomes head up when the camera turns 90 degrees
        (a, b, c, d), border, cam = self.corners(0xc000, yaw=90.0, pos=(0.0, 0.0, 0.0))
        pa, pd = np.array(screen_page(a, cam, border)[:2]), np.array(screen_page(d, cam, border)[:2]); w = (pd - pa) / np.linalg.norm(pd - pa)
        self.assertAlmostEqual(abs(w[0]) + abs(w[1]), 1.0, delta=0.05)            # remains an exact quarter turn (not an arbitrary angle)
        self.assertGreater(abs(w[1]), 0.99)

    def test_flat_body_depth(self):
        # z-buffer: the depth of the 4 corners is that of the flat rectangle (at 0.1 + ground height), not that of a standing panel
        (a, b, c, d), border, cam = self.corners(0, topmost=0.3639)
        zs = [screen_page(P, cam, border)[2] for P in (a, b, c, d)]
        border_, cam_ = border, cam
        flat = [float((np.array([0.0 + dx, 0.3639 + 0.1, 0.2 + dz]) - cam_) @ border_[2]) for dx, dz in ((-0.54, -0.72), (0.54, -0.72), (0.54, 0.72), (-0.54, 0.72))]
        for z, p in zip(zs, flat): self.assertAlmostEqual(z, p, delta=1e-3)

    def test_behind_camera(self):
        border, cam = camera(); self.assertIsNone(PC.vertices((0.0, 0.0, -100.0), 0.0, 0, 0.0, 2.25, border, cam))

    def test_height_shifted_upward(self):
        (a0, *_), border, cam = self.corners(0, topmost=0.0); (a1, *_), _, _ = self.corners(0, topmost=0.36)
        self.assertGreater(screen_page(a1, cam, border)[1], screen_page(a0, cam, border)[1])


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'DQ_APK and DQ_SAVES required (real engine)')
class TestRealEngine(unittest.TestCase):
    def test_taf1(self):
        wdir = '/tmp/sv_test_pose_couchee'; shutil.rmtree(wdir, ignore_errors=True); os.makedirs(wdir)
        m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], wdir)
        SV.load_any(m)
        for _ in range(10): m.step(0, 0)
        SV.force_chapter(m, 1)                                               # the lying soldier of taf1 exists only in chapter 1: we impose it instead of hoping the save is there
        m.start_town('taf1'); seen = []
        for _ in range(80):
            for t, a, f in m.step(0, 0):
                if t in (16, 17) and a: seen.append((t, list(a)))
        self.assertIn((17, [1040, 1863]), seen)
        self.assertIn((16, [0x0c000508]), seen)
        s = m.state.sprites[8]
        self.assertEqual(s['id'], 18)                                        # soldier in blue armor
        self.assertTrue(s['sleeping']); self.assertAlmostEqual(s['sleeping_rot'][0], -90.0, places=3)
        self.assertAlmostEqual(m.state.sleeping_height, 1863 * 1.6 / 8192, places=6)

    def test_group_lies_down_like_script_cmd_set_player_sleep(self):
        """The hero and his companions (slots 0, 1...) lie down through the same packet 16 as the NPCs: TownPartyDraw::setSleep(true) (called by the script command cmd_set_player_sleep) sends
        0x500 | angle << 12 for each, then 0x200 to get up. The hook on setPosition gives the TownPartyDraw object (Unicorn: flush the already translated blocks)."""
        import unicorn
        wdir = '/tmp/sv_test_pose_couchee_groupe'; shutil.rmtree(wdir, ignore_errors=True); os.makedirs(wdir)
        m = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], wdir)
        SV.load_any(m)
        for _ in range(10): m.step(0, 0)
        m.start_town('mak1f1'); c = m.core; here = []
        ad = c.export('_ZN13TownPartyDraw11setPositionEiRKN3dss12Fix32Vector3E')
        c.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, sz, u: here.append(uc.reg_read(c.XREG[0])), None, ad, ad); c.uc.ctl_flush_tb()
        for _ in range(60): m.step(0, 0)
        self.assertTrue(here)
        group = SV.party(m)                                                                          # the party comes from the save: 2 members in chapter 1, 3 in chapter 2...
        self.assertTrue(group, 'no party member on screen')
        m.pk.begin(); c.call(c.export('_ZN13TownPartyDraw8setSleepEb'), here[-1], 1); pkt = m.pk.packets()
        self.assertEqual(sorted(a[0] & 0xfff for t, a, f in pkt if t == 16), [0x500 + k for k in group])   # lying (bits 8 and 10): one packet per slot, the hero (0) first
        m.state.apply(pkt, map_name)
        for k in group:
            self.assertTrue(m.state.sprites[k]['sleeping'])
        for _ in range(30): m.step(0, 0)
        m.pk.begin(); c.call(c.export('_ZN13TownPartyDraw8setSleepEb'), here[-1], 0); pkt = m.pk.packets()
        self.assertEqual(sorted(a[0] & 0x3ff for t, a, f in pkt if t == 16), [0x200 + k for k in group])   # get up (bit 9, no direction)
        m.state.apply(pkt, map_name)
        for k in group:
            self.assertFalse(m.state.sprites[k]['sleeping'])


if __name__ == '__main__': unittest.main(verbosity=1)
