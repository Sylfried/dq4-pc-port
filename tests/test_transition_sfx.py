"""Test of the map transition sound effect (door, village exit / entry, stairs, world map <-> town) with the viewer's "Transition speed".

The map transition sound effect 305 is not launched by Unity nor by the door (which plays 309 on opening) but by
Global::NativeExec, 15 frames after startTown / startField launched the 30-frame fade to black (countdown of the byte at LIB + 0x258254); it is played only if the old scene is still alive. The next map load
happens at the end of the fade: in the original game, the sound effect is requested at mid-fade. With a shortened fade (x3: 10 frames, x4: 8 frames; marginal at x2: 15 frames), the old scene was destroyed before the 15 frames
and the engine no longer requested anything. Engine._exit_countdown resets the countdown to the same proportion as the fade; the fade durations do not change.

  1. pure calculation: fade proportion remembered by State.fade_ratio, countdown adjustment (fake core);
  2. original engine (DQ_APK + DQ_SAVES, chapter 1 imposed, first save that reaches the door): the church door and the village exit to the world map, in both directions, at each "Transition speed" (x1 to x4): a single sound effect 305, requested between the start of the fade and
     the map load, after the door's 309; fade of the set duration;
  3. viewer (Sound, fake players): both sound effects keep playing to their end when the map load blocks the loop (see test_sound_mixing).

    DQ_APK=... DQ_SAVES=... python3 tests/test_transition_sfx.py
"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
SPEEDS = (1.0, 1.5, 2.0, 3.0, 4.0)       # "Transition speed": 1.0 = as in the game; 4.0 = the menu's maximum
GAME_FADE = 30                              # frames of the fade to black of startTown / startField (UnitySetFade(0x101e))


class FakeCountdownCore:
    """Engine memory reduced to the countdown byte."""
    def __init__(self): self.byte = 0; self.written_items = []
    def mem(self, addr, n): return bytes([self.byte])
    def mem_w(self, addr, data): self.byte = data[0]; self.written_items.append(data[0])


def dummy_engine():
    from dq456_pc.core import engine as ENGINE
    m = ENGINE.Engine.__new__(ENGINE.Engine)
    m.core = FakeCountdownCore(); m.L = 0; m.state = ENGINE.State(); m.frames = 0; m._countdown = 0; m._countdown_armed = -99; m._countdown_done = True
    return m


class Calc(unittest.TestCase):
    def setUp(self):
        from dq456_pc.core import engine as ENGINE
        self.ENGINE = ENGINE; self.speed = ENGINE.State.fade_speed

    def tearDown(self): self.ENGINE.State.fade_speed = self.speed

    def fade(self, v, part=None, image=7):
        e = self.ENGINE.State(); e.image = image
        if part is not None: e.part = part
        e.apply([(9, [v], [])], lambda: 'x')
        return e

    def test_proportion_remembered_per_state(self):
        from dq456_pc.core import game_priority as PJ
        for vf in SPEEDS:
            self.ENGINE.State.fade_speed = vf
            e = self.fade(0x1000 | GAME_FADE)
            self.assertEqual(e.fade_ratio[0], 7)
            self.assertAlmostEqual(e.fade_ratio[1], PJ.fade_duration(GAME_FADE, vf) / GAME_FADE, 6, 'x%s' % vf)
        self.ENGINE.State.fade_speed = 1.0
        self.assertEqual(self.fade(0x1000 | GAME_FADE).fade_ratio[1], 1.0, "x1: the game's duration")

    def test_shortened_battle_like_others_entry_without_countdown(self):
        from dq456_pc.core import game_priority as PJ
        self.ENGINE.State.fade_speed = 4.0
        self.assertAlmostEqual(self.fade(0x1000 | GAME_FADE, part=self.ENGINE.PART_BATTLE).fade_ratio[1], PJ.fade_duration(GAME_FADE, 4.0) / GAME_FADE, 6, 'battle fade: follows "Transition speed"')
        self.assertEqual(self.fade(GAME_FADE).fade_ratio[1], 1.0, 'fade-in (to the scene): no countdown to adjust')

    def arm(self, m, byte, ratio, fade_frame=None):
        """A step where the engine arms the countdown (15, already decremented once: 14) and where the fade of this exit arrives."""
        m.state.fade_ratio = (m.frames if fade_frame is None else fade_frame, ratio)
        m.core.byte = byte; m._exit_countdown()

    def test_countdown_reset_to_fade_proportion(self):
        for r, expected in ((1.0, 14), (0.5, 7), (10 / 30, 5), (8 / 30, 4)):
            m = dummy_engine(); self.arm(m, 14, r)
            self.assertEqual(m.core.byte, expected, 'rapport %.2f' % r)
            m.frames += 1; m._exit_countdown(); self.assertEqual(m.core.byte, expected, 'only once')
        m = dummy_engine(); self.arm(m, 1, 0.1); self.assertEqual(m.core.byte, 1, 'never 0: the sound effect is requested at the next frame, not cancelled')

    def test_ratio_one_changes_nothing(self):
        m = dummy_engine(); self.arm(m, 14, 1.0); self.assertEqual(m.core.written_items, [], 'no write into the engine')

    def test_fade_arrives_one_frame_after_arming(self):
        m = dummy_engine(); m.core.byte = 14; m._exit_countdown(); self.assertEqual(m.core.byte, 14, 'no known fade: nothing')
        m.frames += 1; m.core.byte = 13; m.state.fade_ratio = (m.frames, 0.5); m._exit_countdown()
        self.assertEqual(m.core.byte, 6, 'the exit fade came just after: remaining countdown (13) brought back to the ratio (13 x 0.5 rounded)')

    def test_fade_unrelated_to_countdown(self):
        m = dummy_engine(); m.state.fade_ratio = (-50, 0.25); m.core.byte = 14; m._exit_countdown()
        self.assertEqual(m.core.byte, 14, 'an old fade is not the one of this exit')
        m.frames += 3; m.state.fade_ratio = (m.frames, 0.25); m._exit_countdown()
        self.assertEqual(m.core.byte, 14, 'passe 2 images, plus d\'ajustement')


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE; from dq456_pc.persistence import savestates as SS
        cls.ENGINE, cls.SS = ENGINE, SS

        def at_the_church_door(eng):
            """The test walks to the church door of `mak1f1`, then leaves the village: it needs chapter 1 (which is imposed) and a party
            placed close enough to the door. The position, however, comes from the save and is not imposed: we check by really walking, then
            put the party back where it was (no more hard-coded save number)."""
            SV.settle(eng); SV.force_chapter(eng, 1); eng.start_town('mak1f1')
            for _ in range(90): eng.step(0, 0)
            if eng.state.game_map != 'mak1f1': return False
            start = SS.snapshot(eng); reached = False
            for i in range(600):
                if any(t in (0, 27) for t, a, f in eng.step(ENGINE.DOWN, ENGINE.DOWN if i == 0 else 0)): reached = True; break
            SS.apply(eng, start)
            return reached

        cls.eng, cls.slot = SV.pick_save(lambda: ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_bruit_trans_')), at_the_church_door,
                                         "une sauvegarde dont le groupe peut atteindre la porte de l'eglise de `mak1f1` (le chapitre 1 est impose)")
        cls.initial = SS.snapshot(cls.eng)
        cls.speed = ENGINE.State.fade_speed

    @classmethod
    def tearDownClass(cls): cls.ENGINE.State.fade_speed = cls.speed

    def route(self, direction):
        """Walks in `direction` up to the door (or the village exit) then lets the next map load. -> [(frame, kind, value)]: SE (packet 35), FONDU (duration, packet 9 toward black), CHARGE (first packet 0 or 27:
        town scenery or world map), N (fade frames after its 1st step: set duration - 1)."""
        eng, e = self.eng, self.eng.state; after = None; log = []; do_load = False
        for i in range(1500):
            pkt = eng.step(direction if after is None else 0, direction if i == 0 else 0)
            for t, a, f in pkt:
                if t == 35: log.append((eng.frames, 'SE', a[0]))
                elif t == 9 and a[0] & 0x1000: log.append((eng.frames, 'FONDU', a[0] & 0x7ff)); log.append((eng.frames, 'N', e.fade['n']))
                elif t in (0, 27) and not do_load: log.append((eng.frames, 'CHARGE', t)); do_load = True
            if do_load and after is None: after = 0
            if after is not None:
                after += 1
                if after > 30: return log
        self.fail('the transition did not happen: %r' % (log,))

    def reset(self, vf):
        self.SS.apply(self.eng, self.initial); self.ENGINE.State.fade_speed = vf
        self.eng._countdown = 0; self.eng._countdown_armed = -99; self.eng._countdown_done = True

    def check(self, log, vf, name_str):
        from dq456_pc.core import game_priority as PJ
        im = {g: [x[0] for x in log if x[1] == g] for g in ('FONDU', 'CHARGE')}
        sfxs = [(x[0], x[2]) for x in log if x[1] == 'SE']
        self.assertEqual(len(im['FONDU']), 1, name_str); self.assertEqual(len(im['CHARGE']), 1, name_str)
        fade, do_load = im['FONDU'][0], im['CHARGE'][0]
        n = next(x[2] for x in log if x[1] == 'N')
        self.assertEqual(n + 1, PJ.fade_duration(GAME_FADE, vf), '%s: the fade keeps the set duration (x%s)' % (name_str, vf))
        outputs = [i for i, v in sfxs if v == 305]
        self.assertEqual(len(outputs), 1, '%s (x%s) : un bruitage de transition 305 demande : %r' % (name_str, vf, log))
        self.assertTrue(fade <= outputs[0] < do_load, '%s (x%s): requested between the start of the fade (%d) and the loading (%d), not after: %d' % (name_str, vf, fade, do_load, outputs[0]))
        return sfxs

    def test_church_door_in_both_directions(self):
        for vf in SPEEDS:
            self.reset(vf)
            go_to = self.route(self.ENGINE.DOWN)
            sfxs = self.check(go_to, vf, 'eglise > village')
            self.assertEqual([v for _, v in sfxs], [309, 305], 'x%s: the door (309) then the transition (305)' % vf)
            for _ in range(80): self.eng.step(0, 0)
            back = self.route(self.ENGINE.UP)
            self.check(back, vf, 'village > eglise')
            self.assertEqual(self.eng.state.game_map, 'mak1f1')

    def test_exit_village_to_world_map_and_back(self):
        """The village (`maout`) opens onto the world map on the right: exit (startField, TownSystem::playTownExitSE) then return (startTown, FieldSystem::playFieldExitSE), same 305 sound effects."""
        for vf in SPEEDS:
            self.reset(vf)
            self.route(self.ENGINE.DOWN)
            for _ in range(80): self.eng.step(0, 0)
            self.check(self.route(self.ENGINE.RIGHT), vf, 'village > world map')
            self.assertEqual(self.eng.state.part, self.ENGINE.PART_FIELD)
            for _ in range(120): self.eng.step(self.ENGINE.RIGHT, 0)               # (a few steps on the world map, the village entrance is on the left)
            for _ in range(40): self.eng.step(0, 0)
            self.check(self.route(self.ENGINE.LEFT), vf, 'world map > village')
            self.assertEqual(self.eng.state.part, self.ENGINE.PART_TOWN)

    def test_x1_like_the_game(self):
        """Without a shortened fade, nothing changes: sound effect 305 is requested 14 frames after the fade, as before."""
        self.reset(1.0)
        log = self.route(self.ENGINE.DOWN)
        fade = next(x[0] for x in log if x[1] == 'FONDU'); sfx = next(x[0] for x in log if x[1:] == ('SE', 305))
        self.assertEqual(sfx - fade, 14)


if __name__ == '__main__':
    unittest.main(verbosity=2)
