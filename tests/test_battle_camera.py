"""Camera effects in battle: some enemies change the camera angle during their attack.

What the original game does (read in the disassembly of libdq4core.so and verified on the real engine):
  - `BattleMonster::startAnimation(action, variante)` looks up the `param::MonsterAnim` record (monster, action, variant) and calls `BattleCamera::setCameraAnimation(camA, camB, waiting)` with the
    bytes +0x13 / +0x14 / +0xe of that record ; spells go through `BattleEffectUnit::waitStart` (`BattleCamera::setFilename`) ;
  - `EffectParam::getCameraFile(n)` gives the file `camera/<name_str>.cam` (position and angle keyframes, read by `CameraControl::calc`) ; two files add up (A = movement, B = shake) ;
  - on each frame `BattleCamera::executeForMap` computes position and angle, `dss::Camera::send_unity` sends them in ONE packet 10 (bit 0 position, bit 2 angle): nothing else drives the camera.
The viewer therefore has nothing to replay: it applies each packet 10 (`State.apply`) and `_battle_camera` makes the matrix from it. This test proves it:
  - without engine: application of the packets 10 in chunks, roll and pitch / yaw in the matrix ;
  - real engine (optional, DQ_APK + DQ_SAVES): a real battle against a monster whose attack has a camera (index 7: `setCameraAnimation(25, 0, 0)`, the camera goes up then comes back), and four
    injected cameras (shake, big boss movement, dive of a final spell): they all come back exactly to their starting point and the roll sent is always 0.

    python3 tests/test_battle_camera.py
    DQ_APK=... DQ_SAVES=... python3 tests/test_battle_camera.py        (about a minute)
"""
import math, os, struct, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
import numpy as np
from dq4_pc.window import game as F
from dq4_pc.core import engine as ENGINE

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
BASE_POS, BASE_ROT = (0.0, 4.75, -39.8125), (-0.703125, 180.0, 0.0)          # battle camera at rest (after the approach at the start)


def packet10(flags, floats): return (10, [flags], list(floats))


# ------------------------------------------------------------------------------------------------------------------------------ without engine
class PacketApplication(unittest.TestCase):
    def setUp(self):
        self.e = ENGINE.State(); self.e.apply([packet10(5, BASE_POS + BASE_ROT)], lambda: 'btl_pl_d')

    def test_position_and_angle_of_first_packet(self):
        self.assertEqual(tuple(self.e.cam_pos), BASE_POS); self.assertEqual(tuple(self.e.cam_rot), BASE_ROT)

    def test_position_only_packet_keeps_angle(self):
        self.e.apply([packet10(1, (0.0, 7.1, -39.8125))], lambda: 'btl_pl_d')
        self.assertEqual(tuple(self.e.cam_pos), (0.0, 7.1, -39.8125)); self.assertEqual(tuple(self.e.cam_rot), BASE_ROT)

    def test_angle_only_packet_keeps_position(self):
        self.e.apply([packet10(4, (5.5, 170.0, 0.0))], lambda: 'btl_pl_d')
        self.assertEqual(tuple(self.e.cam_pos), BASE_POS); self.assertEqual(tuple(self.e.cam_rot), (5.5, 170.0, 0.0))

    def test_several_packets_in_frame_last_wins(self):
        self.e.apply([packet10(1, (0.0, 5.0, -39.0)), packet10(1, (0.0, 6.0, -38.0)), packet10(4, (1.0, 181.0, 0.0))], lambda: 'btl_pl_d')
        self.assertEqual(tuple(self.e.cam_pos), (0.0, 6.0, -38.0)); self.assertEqual(tuple(self.e.cam_rot), (1.0, 181.0, 0.0))


class CameraMatrix(unittest.TestCase):
    """`_battle_camera`: the battle camera is that of Unity (euler (-x, -(y + 180), z)) ; position, pitch, yaw AND roll change the image."""
    def game(self): return types.SimpleNamespace(cb_mx=False, _rot_camera=lambda e: F.Game._rot_camera(None, e))

    def project(self, pos, rot, point):
        e = types.SimpleNamespace(cam_pos=pos, cam_rot=rot, cam_fov=None)
        M, _ = F.Game._battle_camera(self.game(), e, 16 / 9)
        v = M @ np.array([point[0], point[1], point[2], 1.0]); return v[0] / v[3], v[1] / v[3], v[3]

    def test_rest_looks_toward_positive_z(self):
        x, y, w = self.project(BASE_POS, BASE_ROT, (0.0, 4.75, 0.0))
        self.assertGreater(w, 0); self.assertAlmostEqual(x, 0.0, places=3)

    def test_yaw_moves_image_horizontally(self):
        x0, _, _ = self.project(BASE_POS, BASE_ROT, (0.0, 4.75, 0.0))
        x1, _, _ = self.project(BASE_POS, (BASE_ROT[0], BASE_ROT[1] + 10.0, 0.0), (0.0, 4.75, 0.0))
        self.assertGreater(abs(x1 - x0), 0.15)

    def test_pitch_moves_the_image_vertically(self):
        _, y0, _ = self.project(BASE_POS, BASE_ROT, (0.0, 4.75, 0.0))
        _, y1, _ = self.project(BASE_POS, (BASE_ROT[0] + 5.0, BASE_ROT[1], 0.0), (0.0, 4.75, 0.0))
        self.assertGreater(abs(y1 - y0), 0.1)

    def test_position_moves_image(self):
        x0, y0, _ = self.project(BASE_POS, BASE_ROT, (0.0, 4.75, 0.0))
        x1, y1, _ = self.project((0.0, 7.1, -39.8125), BASE_ROT, (0.0, 4.75, 0.0))
        self.assertGreater(abs(y1 - y0), 0.05)

    def test_roll_rotates_the_image(self):
        """The game never sends a roll in battle (see the real-engine test), but if it sent one, the viewer would apply it (G-073: nothing to add)."""
        R0 = F.Game._rot_camera(None, types.SimpleNamespace(cam_rot=BASE_ROT)); R1 = F.Game._rot_camera(None, types.SimpleNamespace(cam_rot=(BASE_ROT[0], BASE_ROT[1], 20.0)))
        self.assertAlmostEqual(float((R0 @ [0.0, 1.0, 0.0])[0]), 0.0, places=3)
        self.assertAlmostEqual(abs(float((R1 @ [0.0, 1.0, 0.0])[0])), math.sin(math.radians(20.0)), places=3)
        x0, y0, _ = self.project(BASE_POS, BASE_ROT, (3.0, 4.75, 0.0)); x1, y1, _ = self.project(BASE_POS, (BASE_ROT[0], BASE_ROT[1], 20.0), (3.0, 4.75, 0.0))
        self.assertGreater(abs(y1 - y0), 0.03)                                                 # a point to the right of the center goes up or down when the camera rolls

    def test_field_of_view_of_packet_11(self):
        e = types.SimpleNamespace(cam_pos=BASE_POS, cam_rot=BASE_ROT, cam_fov=30.0)
        M, _ = F.Game._battle_camera(self.game(), e, 16 / 9); e2 = types.SimpleNamespace(cam_pos=BASE_POS, cam_rot=BASE_ROT, cam_fov=None); M2, _ = F.Game._battle_camera(self.game(), e2, 16 / 9)
        self.assertGreater(abs(M[1, 1] - M2[1, 1]), 0.05)


# ------------------------------------------------------------------------------------------------------------------------------ real engine
@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    MONSTER = 7                                                      # monster whose basic attack has a camera (file "m007_at"): the camera goes up by ~2.35 units then comes back

    @classmethod
    def setUpClass(cls):
        import unicorn; from dq4_pc.persistence import savestates as SS
        from unicorn.arm64_const import UC_ARM64_REG_W1, UC_ARM64_REG_W2, UC_ARM64_REG_W3
        cls.SS = SS; eng = cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_camcb_')); c = cls.c = eng.core
        sys.path.insert(0, HERE); import _saves as SV
        SV.load_any(eng); SV.settle(eng)                            # (the save's welcome message closed first: left open, it held the battle's first message)
        enc = c.call(c.export('_ZN7Encount12getSingletonEv'), label='enc')
        def force(u, addr, sz, ud):                                  # encounter composition: a single monster (Encount + 0x34 / 0x44, like test_battle_history)
            for j in range(4):
                c.mem_w(enc + 0x34 + 4 * j, struct.pack('<I', cls.MONSTER if j == 0 else 0)); c.mem_w(enc + 0x44 + 4 * j, struct.pack('<I', 1 if j == 0 else 0))
        a = c.export('_ZN10BattleRoot12setupMonsterEv'); c.uc.hook_add(unicorn.UC_HOOK_CODE, force, None, a, a)
        cls.calls = []                                              # BattleCamera::setCameraAnimation(camA, camB, waiting): (frame, camA, camB, waiting)
        a = c.export('_ZN12BattleCamera18setCameraAnimationEhht')
        c.uc.hook_add(unicorn.UC_HOOK_CODE, lambda u, ad, sz, ud: cls.calls.append((eng.frames, u.reg_read(UC_ARM64_REG_W1) & 0xff, u.reg_read(UC_ARM64_REG_W2) & 0xff, u.reg_read(UC_ARM64_REG_W3) & 0xffff)), None, a, a)
        c.uc.ctl_flush_tb()
        c.call(c.export('_ZN6Global11startBattleEv'), eng._global(), label='startBattle')
        n = 0
        while eng.state.part != ENGINE.PART_BATTLE and n < 1500: eng.step(); n += 1
        assert eng.state.part == ENGINE.PART_BATTLE
        cls.cam = c.call(c.export('_ZN12BattleCamera12getSingletonEv'), label='cam')
        cls.sca = c.export('_ZN12BattleCamera18setCameraAnimationEhht'); cls.isa = c.export('_ZN12BattleCamera17isCameraAnimationEv')
        for i in range(600):                                         # up to the command menu: camera at rest, nothing has attacked yet
            k = ENGINE.A if (i % 4 == 0 and eng.msg_visible and eng.message_state()[1] in (3, 5)) else 0          # (a save whose battle messages wait for A: "Un archer vert apparaît !" held the menu)
            eng.step(k, k); eng.ui.damage = []
            if eng.active_menu() is not None: break
        assert eng.active_menu() is not None
        cls.initial = SS.snapshot(eng)

    def step(self, p=0, d=0):
        pkt = self.eng.step(p, d); self.eng.ui.damage = []; return pkt

    def test_1_real_battle_monster_attack_moves_camera(self):
        """A real battle, played like test_battle_speed: the monster's attack launches `setCameraAnimation(25, 0, 0)` ; the camera of the viewer (State.cam_pos) follows the packets, goes up, then comes back exactly."""
        eng = self.eng; st = {'rel': None, 'pending': 0}; series = []; begin = None
        self.SS.apply(eng, self.initial); e = eng.state                                     # (apply replaces the State object: reread it afterwards)
        for i in range(3000):
            p = d = 0
            if st['rel'] is not None: eng.send_menu(st['rel'], 1, -1, 0); st['rel'] = None
            port = eng.active_menu()
            if port is not None and not eng.msg_visible:
                st['pending'] += 1
                if st['pending'] % 4 == 0: eng.send_menu(port, 1, -1, 0x10); st['rel'] = port
            elif eng.msg_visible and (eng.ui.msg.get('feed') or eng.message_state()[1] in (3, 5)):
                st['pending'] += 1
                if st['pending'] % 4 == 0: p = d = ENGINE.A
            else: st['pending'] = 0
            prev = e.part; self.step(p, d)
            if any(a[1] == 25 for a in self.calls) and begin is None: begin = i
            if begin is not None: series.append((tuple(e.cam_pos), tuple(e.cam_rot)))
            if begin is not None and i - begin > 60: break
            if e.part != ENGINE.PART_BATTLE and prev == ENGINE.PART_BATTLE: break
        self.assertIsNotNone(begin, 'the monster did not launch an attack with a camera (calls: %r)' % (self.calls[:6],))
        self.assertIn((25, 0, 0), [a[1:] for a in self.calls])
        ys = [s[0][1] for s in series]; base_y = BASE_POS[1]
        self.assertGreater(max(ys) - base_y, 2.0, 'the camera must rise by at least 2 units')
        self.assertAlmostEqual(ys[-1], base_y, delta=0.01)                                  # returns to its starting point
        for s in series:
            self.assertAlmostEqual(s[0][0], BASE_POS[0], delta=1e-3); self.assertAlmostEqual(s[0][2], BASE_POS[2], delta=1e-3)       # only the height changes
            self.assertEqual(s[1], BASE_ROT)                                                                                              # the angle does not change for this attack
        self.assertGreater(len(set(ys)), 15, 'un mouvement continu, image par image (un paquet 10 par image)')

    def inject(self, cam_a, cam_b, waiting, maximum=700):
        """Puts the battle back at rest (command menu), starts the camera (like BattleMonster::startAnimation) and follows State.cam_pos / cam_rot until the end of the animation."""
        SS, eng, c = self.SS, self.eng, self.c
        SS.apply(eng, self.initial); e = eng.state                                           # (apply replaces the State object: reread it afterwards)
        for _ in range(3): self.step()
        c.call(self.sca, self.cam, 0, 0, 0, label='sca0')
        for _ in range(4): self.step()
        base = (tuple(e.cam_pos), tuple(e.cam_rot)); series = []
        c.call(self.sca, self.cam, cam_a, cam_b, waiting, label='sca')
        for j in range(maximum):
            self.step(); series.append((tuple(e.cam_pos), tuple(e.cam_rot)))
            if not (c.call(self.isa, self.cam, label='isanim') & 1) and j > 3: break
        return base, series

    def spacings(self, base, series):
        dp = [max(abs(s[0][k] - base[0][k]) for s in series) for k in range(3)]; da = [max(abs(s[1][k] - base[1][k]) for s in series) for k in range(3)]
        return dp, da

    def check_back(self, base, series):
        for k in range(3):
            self.assertAlmostEqual(series[-1][0][k], base[0][k], delta=0.01); self.assertAlmostEqual(series[-1][1][k], base[1][k], delta=0.01)       # returns to its starting point
        self.assertTrue(all(s[1][2] == 0.0 for s in series), 'roll sent by the game: always 0')

    def test_2_vertical_shake(self):
        """Camera 158 "tateyure1" (pitch shake, the most common): ~1 degree of pitch, neither position nor yaw, ~13 frames."""
        base, series = self.inject(0, 158, 30); dp, da = self.spacings(base, series)
        self.assertGreater(da[0], 0.8); self.assertLess(da[0], 1.5); self.assertLess(max(dp), 0.01); self.assertLess(da[1], 0.01); self.assertTrue(20 <= len(series) <= 40, len(series)); self.check_back(base, series)

    def test_3_attack_with_marked_pitch(self):
        """Camera 21 "m000_at" (slime attack, variant 1): pitch of ~6.5 degrees, nothing else."""
        base, series = self.inject(21, 0, 0); dp, da = self.spacings(base, series)
        self.assertGreater(da[0], 6.0); self.assertLess(da[0], 7.0); self.assertLess(max(dp), 0.01); self.check_back(base, series)

    def test_4_large_boss_movement(self):
        """Camera 127 "m255_tai" (special forms with index >= 250): the camera slides by ~14.6 units in x and z and turns by ~19 degrees in yaw, for ~230 frames (7 s), then comes back."""
        base, series = self.inject(127, 0, 0, maximum=800); dp, da = self.spacings(base, series)
        self.assertGreater(dp[0], 14.0); self.assertGreater(dp[2], 14.0); self.assertGreater(da[1], 18.0); self.assertGreater(len(series), 200); self.check_back(base, series)

    def test_5_final_spell_dive(self):
        """Camera 140 "madante_evi": the camera goes up by ~31.6 units in height and dives by ~54 degrees, ~180 frames, then comes back."""
        base, series = self.inject(140, 0, 0, maximum=800); dp, da = self.spacings(base, series)
        self.assertGreater(dp[1], 30.0); self.assertGreater(da[0], 50.0); self.assertGreater(len(series), 150); self.check_back(base, series)

    def test_6_viewer_projects_sent_camera(self):
        """At the top of the boss movement (127), the matrix of the viewer is no longer the rest one: a point of the scenery is projected elsewhere."""
        base, series = self.inject(127, 0, 0, maximum=800)
        peak = max(series, key=lambda s: abs(s[1][1] - base[1][1]))
        game = types.SimpleNamespace(cb_mx=False, _rot_camera=lambda e: F.Game._rot_camera(None, e)); pt = np.array([0.0, 4.75, 0.0, 1.0])
        proj = lambda pos, rot: (lambda v: v[:2] / v[3])(F.Game._battle_camera(game, types.SimpleNamespace(cam_pos=pos, cam_rot=rot, cam_fov=None), 16 / 9)[0] @ pt)
        self.assertGreater(float(np.abs(proj(*peak) - proj(*base)).max()), 0.1)


if __name__ == '__main__':
    unittest.main()
