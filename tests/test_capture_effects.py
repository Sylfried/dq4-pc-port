"""Screen effects of the `Capture` class (packet 34, values 3: travel / ailes de Chimere, 5: lamp / Ranaruta, 6: Riremito):

1. pure modules (render/tabi_effect.py, lamp_effect.py, riremito_effect.py): number of MoveNext calls (64, 45 at arrival, 64, 63), moment when rendering turns on and off, control values read from the
   specification (Tabi vertices, lamp bytes, Riremito displacements), blur passes (one per frame, two textures alternating, the first reads "nothing") and drawing buffers;
2. engine (Engine._start_screen_effect / _screen_effect, without an engine: the flag is simulated): bit 7 of the value (arrival, morning), duration that follows "Transition speed", immediate black of the lamp and of Riremito
   (State.sharp_black_fade), fade-in and end of the black screen at the arrival of a trip, safeguards, only one effect at a time, a state saved before the fix.

  python3 tests/test_capture_effects.py
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
from dq456_pc.core import engine as ENGINE
from dq456_pc.core import game_priority as PJ
from dq456_pc.render import capture_effects as EF
from dq456_pc.render.lamp_effect import LampEffect
from dq456_pc.render.riremito_effect import RiremitoEffect
from dq456_pc.render.tabi_effect import TabiEffect


def play(effect, toward=None):
    """Runs the effect to its end (or until call `toward`); returns the list of (call, render_active)."""
    savestates = []
    while not effect.finished and (toward is None or effect.frames < toward):
        effect.stage(); savestates.append((effect.frames, effect.render_active))
    return savestates


class Durations(unittest.TestCase):
    def test_move_next_call_count(self):
        for name_str, factory, expected in (('tabi', lambda: TabiEffect(False), 64), ('tabi_return', lambda: TabiEffect(True), 45), ('lamp', LampEffect, 64), ('riremito', RiremitoEffect, 63)):
            e = factory(); savestates = play(e)
            self.assertEqual(e.frames, expected, name_str); self.assertEqual(EF.FRAMES[name_str], expected); self.assertTrue(e.finished); self.assertEqual(e.duration, expected)
        self.assertEqual(EF.frames_of('tabi', True), 45); self.assertEqual(EF.frames_of('tabi', False), 64); self.assertEqual(EF.frames_of('lamp', True), 64)       # (bit 7: no effect outside of travel)
        self.assertEqual(EF.KINDS, {3: 'tabi', 5: 'lamp', 6: 'riremito', 9: 'pegasus', 10: 'ido'}); self.assertEqual(EF.V2_ONLY, ('pegasus', 'ido'))      # (9 and 10: DQ VI only)

    def test_game_stays_normal_first_two_calls(self):
        for factory in (lambda: TabiEffect(False), LampEffect, RiremitoEffect):
            e = factory(); savestates = play(e, 3)
            self.assertEqual(savestates, [(1, False), (2, False), (3, True)])                              # rendering turns on at the 3rd call (the capture was taken at the start of the 2nd)

    def test_render_end(self):
        e = TabiEffect(False); savestates = play(e); self.assertTrue(savestates[-1][1])                          # the departure turns nothing off: the screen stays black (both materials at alpha 0)
        d = {n: c for n, p, u, c in e.drawings()}; self.assertTrue(np.all(d['blur'] == 0) and np.all(d['capture'] == 0))
        e = TabiEffect(True); savestates = play(e); self.assertTrue(savestates[-2][1]); self.assertFalse(savestates[-1][1]); self.assertEqual(e.drawings(), [])         # the arrival restores the game: last call = rendering off
        e = LampEffect(); savestates = play(e); self.assertEqual([a for a, r in savestates if r], list(range(3, 64))); self.assertFalse(savestates[-1][1])
        e = RiremitoEffect(); savestates = play(e); self.assertEqual([a for a, r in savestates if r], list(range(3, 63))); self.assertFalse(savestates[-1][1])

    def test_calls_made_follow_transition_speed(self):
        self.assertEqual([EF.calls_made(n, 64, 64) for n in (0, 1, 62, 63, 64)], [1, 2, 63, 64, 64])                       # x1: one call per engine frame (the first at the packet's frame)
        d = PJ.fade_duration(64, 2.0); self.assertEqual(d, 32)
        v = [EF.calls_made(n, d, 64) for n in range(d)]
        self.assertEqual(v[0], 2); self.assertEqual(v[-1], 64); self.assertTrue(all(b >= a for a, b in zip(v, v[1:])))


class Tabi(unittest.TestCase):
    def test_control_vertices(self):
        """Specification array (16:9 screen: 9 rows, 170 vertices): top-left corner (vertex 0) and bottom-right (last) at the cited calls."""
        for inv, call, s0, sn in ((False, 3, (-1.0, 1.0), (1.0, -1.0)), (False, 4, (-0.97416, 1.00887), (0.97416, -1.00887)), (False, 33, (-0.27309, 1.02490), (0.27309, -1.02490)),
                                   (False, 63, (0.18492, 0.68250), (-0.18492, -0.68250)), (True, 3, (-0.08043, 0.93937), (0.08043, -0.93937)), (True, 43, (-1.0, 1.0), (1.0, -1.0))):
            e = TabiEffect(inv, 9); self.assertEqual(e.num, 170); play(e, call)
            np.testing.assert_allclose(e._vt[0], s0, atol=2e-5, err_msg='%s appel %d' % ('arrivee' if inv else 'depart', call)); np.testing.assert_allclose(e._vt[-1], sn, atol=2e-5)

    def test_alphas(self):
        """Rise over 4 frames (bAlpha: 0.23125 per step at departure, cAlpha: 0.70625 then -0.0625 per step), then decay from counter 30 (departure only); arrival: 0.24375 / +0.0625."""
        e = TabiEffect(False); play(e, 3); self.assertAlmostEqual(float(e.alpha_blur), 0.23125, 5); self.assertAlmostEqual(float(e.alpha_capture), 0.70625, 5)
        play(e, 6); self.assertAlmostEqual(float(e.alpha_blur), 0.925, 5); self.assertAlmostEqual(float(e.alpha_capture), 0.51875, 5)
        play(e); self.assertEqual(float(e.alpha_capture), 0.0); self.assertAlmostEqual(float(e.alpha_blur), 0.6925, 4)                  # cAlpha drops to 0 before the end, bAlpha does not
        a = TabiEffect(True); play(a, 6); self.assertAlmostEqual(float(a.alpha_blur), 0.975, 5); self.assertAlmostEqual(float(a.alpha_capture), 0.25, 5); play(a, 44); self.assertAlmostEqual(float(a.alpha_blur), 0.975, 5)

    def test_default_mobile_mesh(self):
        """28 rows (m_divY = 56 of the original portrait screen): 17 x 29 vertices, 2 x 16 x 28 triangles; the uv cover the capture."""
        e = TabiEffect(False); self.assertEqual((e.lines, e.num), (28, 17 * 29)); play(e, 3)
        name_str, pos, uv, rgba = e.drawings()[1]; self.assertEqual(name_str, 'capture'); self.assertEqual(pos.shape, (2 * 3 * 16 * 28, 2)); self.assertEqual(uv.shape, pos.shape)
        self.assertEqual((float(uv.min()), float(uv.max())), (0.0, 1.0)); self.assertLessEqual(float(np.abs(pos).max()), 1.0 + 1e-5)         # at call 3: the grid is regular, the whole screen


class Lamp(unittest.TestCase):
    def follow(self, morning):
        l = LampEffect(morning); suite = []
        while not l.finished:
            l.stage()
            if l.render_active: suite.append((int(l.cl[3, 8, 0 if not morning else 2]), int(l.cl[3, 0, 0 if not morning else 2]), float(l.bias), l.cl[3, 8].tolist(), l.cl[3, 0].tolist()))
        return l, suite

    def test_night_values(self):
        l, s = self.follow(False); c8 = [x[0] for x in s]; c0 = [x[1] for x in s]
        self.assertEqual(c8[:9], [251, 246, 240, 233, 225, 216, 206, 195, 183]); self.assertEqual(c8.index(0), 19)                         # center column: drops to 0 at counter 19
        self.assertEqual(c0[0], 254); self.assertEqual(c0.index(0), 57)                                                                       # edge columns: very slowly, 0 at counter 57
        self.assertEqual(s[0][3], [251, 251, 255, 255]); self.assertEqual(s[-1][3], [0, 0, 255, 255])                                       # night: red and green go down, blue (and alpha) stay at 255
        self.assertAlmostEqual(min(x[2] for x in s), 0.5880126953125, 12); self.assertAlmostEqual(max(x[2] for x in s), 1.091552734375, 12)         # "eyelid": bias from 1 to 0.588 (counter 27), then up to 1.09
        self.assertAlmostEqual(float(l.b_alpha), 0.875, 5); self.assertAlmostEqual(float(l.c_alpha), 0.8125, 5); self.assertEqual(float(l.fade), 0.0)

    def test_morning_values(self):
        l, s = self.follow(True)
        self.assertEqual([x[3] for x in s[:4]], [[255, 255, 255, 255], [255, 255, 254, 255], [255, 255, 252, 255], [255, 255, 249, 255]])           # morning: only blue goes down (yellow tint); cbias starts at 0: nothing is subtracted at the 1st update
        self.assertEqual(s[-1][3], [255, 255, 0, 255]); self.assertTrue(0 < s[-1][4][2] <= 8)                                                      # end: center at 0, edge columns never at 0 (7)
        self.assertEqual(s[0][0], 255)

    def test_pinch(self):
        """Columns 0 and 16: y unchanged; top row (y = 1): the center column takes the value of `bias`, its neighbor 0.1 + 0.9 bias; `bias` oscillates between 0.588 and 1.09."""
        l = LampEffect(False); seen = []; orig = l._update
        def do_update(): seen.append(float(l.bias)); orig()
        l._update = do_update; play(l, 3 + 28)
        self.assertEqual(l.counter, 28)
        np.testing.assert_array_equal(l.g[:, 0, 1], l.pt); np.testing.assert_array_equal(l.g[:, 16, 1], l.pt)
        self.assertAlmostEqual(float(l.g[0, 8, 1]), seen[-1], 5); self.assertAlmostEqual(float(l.g[0, 7, 1]), 0.1 + 0.9 * seen[-1], 5); self.assertAlmostEqual(float(l.g[0, 9, 1]), float(l.g[0, 7, 1]), 7)
        self.assertEqual(l.h_div_y, 14); self.assertEqual(l.g.shape, (15, 17, 3)); self.assertAlmostEqual(min(seen), 0.5880126953125, 12)


class Riremito(unittest.TestCase):
    def test_movements_at_last_update(self):
        r = RiremitoEffect(); play(r, 2 + 59); self.assertEqual(r.counter, 59)
        avg = [r.vt[4 * i:4 * i + 4, :2].mean(0) for i in range(4)]                                                                           # center of each copy: (+-3 u, +-u), u = 0.0005 (i + 1) c
        np.testing.assert_allclose(avg, [(0.0885, -0.0295), (0.177, 0.059), (-0.2655, 0.0885), (-0.354, -0.118)], atol=1e-5)
        self.assertAlmostEqual(float(r.rot), 6.49, 4)                                                                                         # 0.11 degrees per frame
        np.testing.assert_allclose(r.background_mat, (0.9, 0.9, 0.9, 1.0), atol=1e-6); np.testing.assert_allclose(r.mat_capture, (0.0, 0.0, 0.0, 0.18), atol=1e-6)      # background (b, b, b, 1); copies: blackened, opacity 0.18

    def test_first_step_and_blackening(self):
        r = RiremitoEffect(); play(r, 3)
        np.testing.assert_allclose(r.vt[0:4, :2].mean(0), (0.0015, -0.0005), atol=1e-6); np.testing.assert_allclose(r.mat_capture, (1, 1, 1, 0.82), atol=1e-6)      # c = 1: u = 0.0005, copy 0 toward the right and down
        play(r, 2 + 29); self.assertEqual(r.counter, 29); self.assertEqual(float(r.fade), 1.0)
        play(r, 2 + 30); self.assertAlmostEqual(float(r.fade), 1 - 1 / 30, 6)                                                                # the blackening starts at counter 30


class Blur(unittest.TestCase):
    def test_blur_passes(self):
        """The pass takes place before each call as long as SetBlur is true (from the 2nd); two textures alternating; the first pass reads "nothing"; rendering goes back to the state of the PREVIOUS frame."""
        for factory, last_one in ((lambda: TabiEffect(False), 64), (LampEffect, 63), (RiremitoEffect, 62)):
            e = factory(); was_seen = []
            e.on_blur = lambda ef, i: was_seen.append((ef.frames + 1, i, ef.blur_read, bool(ef.drawings())))
            play(e)
            self.assertEqual([a for a, i, l, d in was_seen], list(range(2, last_one + 1)))
            self.assertEqual([i for a, i, l, d in was_seen], [k % 2 for k in range(len(was_seen))]); self.assertIsNone(was_seen[0][2]); self.assertEqual([l for a, i, l, d in was_seen[1:]], [1 - i for a, i, l, d in was_seen[1:]])
            self.assertFalse(was_seen[0][3]); self.assertFalse(was_seen[1][3]); self.assertTrue(was_seen[2][3])               # calls 2 and 3: rendering is not yet on in the state of the previous frame

    def test_drawing_buffers(self):
        """Background first (blurred texture x color, replaces the screen), then the capture; positions in normalized screen coordinates; one color per vertex."""
        for e in (TabiEffect(False), LampEffect(False), LampEffect(True), RiremitoEffect()):
            self.assertEqual(e.drawings(), []); play(e, 20); d = e.drawings()
            self.assertEqual([n for n, p, u, c in d], ['blur', 'capture'])
            for n, p, u, c in d: self.assertEqual((p.shape[1], u.shape[1], c.shape[1]), (2, 2, 4)); self.assertEqual(len(p), len(u)); self.assertEqual(len(p), len(c)); self.assertTrue(np.isfinite(p).all())
            np.testing.assert_array_equal(d[0][1], [(-1, 1), (1, 1), (-1, -1), (1, 1), (1, -1), (-1, -1)])              # background: the whole screen
            self.assertEqual(len(d[0][1]), 6)
        e = RiremitoEffect(); play(e, 20); self.assertEqual(len(e.drawings()[1][1]), 24)                                 # four copies
        e = LampEffect(False); play(e, 5); r = e.drawings()[1][3]; self.assertTrue(np.all(r[:, 2] == 1.0)); play(e, 40); self.assertTrue(np.all(e.drawings()[1][3][:, 3] == e.grid_mat[3]))


def mock_engine(speed=1.0):
    ENGINE.State.fade_speed = speed; e = ENGINE.State(); flag = []
    return types.SimpleNamespace(state=e, _effect_flag=lambda a: flag.append(a), flag=flag, frames=0)


def launch(eng, value):
    ENGINE.Engine._start_screen_effect(eng, value)


def step(eng):
    ENGINE.Engine._screen_effect(eng); eng.frames += 1; eng.state.tick_fade()


class Engine(unittest.TestCase):
    def tearDown(self): ENGINE.State.fade_speed = 1.0

    def test_packet_values(self):
        for value, kind, inverse, morning, frames in ((3, 'tabi', False, False, 64), (0x83, 'tabi', True, False, 45), (5, 'lamp', False, False, 64), (0x85, 'lamp', False, True, 64), (6, 'riremito', False, False, 63), (0x86, 'riremito', False, False, 63)):
            eng = mock_engine(); launch(eng, value); ef = eng.state.screen_effect
            self.assertEqual((ef['kind'], ef['inverse'], ef['morning'], ef['frames'], ef['duration'], ef['n']), (kind, inverse, morning, frames, frames, 0), hex(value)); self.assertEqual(eng.flag, [True])
        for value in (0, 1, 2, 4, 7, 0x84):
            eng = mock_engine(); launch(eng, value); self.assertIsNone(eng.state.screen_effect, hex(value)); self.assertEqual(eng.flag, [])        # 4: battle start (another effect, Engine._start_battle_effect)
        eng = mock_engine(); launch(eng, 5); launch(eng, 6); self.assertEqual(eng.state.screen_effect['kind'], 'lamp'); self.assertEqual(eng.flag, [True])              # only one effect at a time

    def test_flag_falls_back_after_duration(self):
        for value, frames in ((3, 64), (0x83, 45), (5, 64), (6, 63)):
            for speed in (1.0, 2.0, 4.0):
                eng = mock_engine(speed); launch(eng, value); d = PJ.fade_duration(frames, speed); self.assertEqual(eng.state.screen_effect['duration'], d); n = 0
                while eng.state.screen_effect is not None: self.assertEqual(eng.flag, [True]); step(eng); n += 1
                self.assertEqual(n, d, 'valeur %s x%g' % (hex(value), speed)); self.assertEqual(eng.flag, [True, False])
        self.assertFalse(mock_engine().state.battle_transition())                                                                    # (this is not a battle transition)
        eng = mock_engine(); launch(eng, 3); self.assertFalse(eng.state.battle_transition()); self.assertIsNone(eng.state.effect)

    def test_immediate_black_for_lamp_and_riremito(self):
        for value, call in ((5, 63), (6, 62)):
            eng = mock_engine(); launch(eng, value); self.assertEqual(eng.state.fade['a'], 0.0); n = 0
            while eng.state.screen_effect is not None:
                step(eng); n += 1
                self.assertEqual(eng.state.fade['a'], 1.0 if n + 1 >= call else 0.0, (value, n))                                   # original call = n + 1 (the first at the packet's frame)
            self.assertEqual((eng.state.fade['a'], eng.state.fade['n'], eng.state.fade['col']), (1.0, 0, (0.0, 0.0, 0.0))); self.assertFalse(eng.state.fade_in_progress())          # opaque, black, immediate; it stays that way
            self.assertIsNone(eng.state.black_screen)

    def test_trip_departure_and_arrival(self):
        eng = mock_engine(); launch(eng, 3)
        for _ in range(63): step(eng); self.assertIsNone(eng.state.black_screen)
        step(eng); self.assertIsNone(eng.state.screen_effect); self.assertEqual(eng.state.black_screen, {'n': 0})                              # end of the departure: the screen stays black
        for _ in range(100): step(eng)
        self.assertEqual(eng.state.black_screen['n'], 100); self.assertEqual(eng.state.fade['a'], 0.0)                                    # (the black is not a fade plane: the interface stays drawn)
        eng.state.fade['a'] = 0.5; launch(eng, 0x83)
        for n in range(1, 46):
            step(eng)
            if n == 1: self.assertEqual(eng.state.fade['n'], 0)
            if n == 2: self.assertEqual((eng.state.fade['n'], round(eng.state.fade['step'], 6), eng.state.fade['end']), (EF.FADE_IN - 1, round(-0.5 / 30, 6), 0.0))     # Fade.SetFadeIn(30) at call 3: from the current opacity to 0 (30 frames, one already elapsed by the end of this frame)
            if n < 44: self.assertIsNotNone(eng.state.black_screen, n)
            if n == 44: self.assertIsNone(eng.state.black_screen); self.assertIsNotNone(eng.state.screen_effect)                             # last call (state 4): the scene reappears; the flag drops at the next frame
        self.assertIsNone(eng.state.screen_effect); self.assertEqual(eng.flag, [True, False, True, False])

    def test_entry_fade_from_transparent_plane(self):
        e = ENGINE.State(); e.current_fade_in(30); self.assertEqual((e.fade['a'], e.fade['n'], e.fade['step']), (0.0, 30, -0.0))
        for _ in range(30): e.tick_fade()
        self.assertEqual((e.fade['a'], e.fade['n']), (0.0, 0)); self.assertFalse(e.fade_in_progress())

    def test_black_screen_guardrails(self):
        eng = mock_engine(); eng.state.black_screen = {'n': 0}
        for _ in range(ENGINE.BLACK_SCREEN_MAX): step(eng)
        self.assertIsNotNone(eng.state.black_screen); step(eng); self.assertIsNone(eng.state.black_screen)                                        # no arrival ever: the game is reopened after 60 s
        for cond in ({'game_map': ENGINE.TITLE_MAP}, {'part': ENGINE.PART_INITIAL}):
            eng = mock_engine(); eng.state.black_screen = {'n': 0}
            for k, v in cond.items(): setattr(eng.state, k, v)
            step(eng); self.assertIsNone(eng.state.black_screen, cond)                                                                    # return to the title screen: no more black

    def test_state_stored_before_fix(self):
        e = ENGINE.State(); e.__dict__.pop('screen_effect', None); e.__dict__.pop('black_screen', None); self.assertIsNone(e.screen_effect); self.assertIsNone(e.black_screen)      # class attributes


if __name__ == '__main__':
    unittest.main(verbosity=2)
