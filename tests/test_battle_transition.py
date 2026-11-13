"""Battle transitions: the battle acceleration applies from the end of the cascade transition and the "enemy appears" message until the final fade to black, and the transition effects at the
start and end of a battle follow the "Transition speed" setting like any other transition.

The transition = start screen effect (the "cascade": 57 game frames), black screen waiting for the scene, battle fade-in, battle exit fades, fade back to the map. Verified rules:
  - DURATION (engine frames): the cascade and each fade last what the game requests divided by "Transition speed" (x1 to x4), like a map change fade (game_priority.fade_duration);
  - CLOCK (real time): the cascade runs on the game clock (30 frames per second) whatever "Battle speed", walking speed and accelerator are; from the end of the cascade (black screen, fade-in,
    "X apparait" message) up to and including the battle-end fade, "Battle speed" (x1, x1, x2, x3) applies; the return to the map runs on the game clock while the player is locked (flag 4); as soon as the player is free (frame 12 of the return, the hero walks from the 13th), accelerated walking and the accelerator take effect (like for a map change).

    python3 tests/test_battle_transition.py        (Linux without a display: pyglet in "headless" mode)
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 -W ignore tests/test_battle_transition.py     (adds the replay of a real engine battle)
The saves are only opened read-only: the engine writes to a temporary folder."""
import itertools, os, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
try:
    import pyglet
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
    from dq4_pc.window import game as F
except Exception as ex:
    F = None; IMPORT_ERROR = ex
from dq4_pc.core import engine as ENGINE
from dq4_pc.core import game_priority as PJ

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
STEP = 1.0 / 30.0
BATTLE_FADE = 0x1000 | 30              # packet 9: exit to black in 30 frames (4126, seen at the end of each battle)
ENTRY_30 = 30                          # packet 9: entry in 30 frames


def state(part=ENGINE.PART_FIELD, fade_speed=1.0):
    e = ENGINE.State(); e.part = part; ENGINE.State.fade_speed = fade_speed; return e


class Fades(unittest.TestCase):
    def tearDown(self): ENGINE.State.fade_speed = 1.0

    def test_outside_battle_setting_always_shortens(self):
        for vf, expected in ((1.0, 30), (2.0, 15), (4.0, 8)):
            e = state(ENGINE.PART_FIELD, vf); e.apply([(9, [ENTRY_30], [])], lambda: ''); self.assertEqual(e.fade['n'], expected, 'x%g' % vf); self.assertFalse(e.fade['battle'])
            self.assertFalse(e.battle_transition())

    def test_battle_arrival_fade_follows_transition_speed(self):
        for vf in (1.0, 2.0, 3.0, 4.0):
            d = PJ.fade_duration(30, vf)
            e = state(ENGINE.PART_FIELD, vf); e.apply([(0, [0x100], []), (9, [ENTRY_30], [])], lambda: 'btl_pl_d')           # loading of the battle scene (bit 8) then fade-in, same engine frame
            self.assertEqual(e.fade['n'], d, 'x%g' % vf); self.assertTrue(e.fade['battle']); self.assertTrue(e.battle_transition())
            e.loading = None                                                                                                      # (the drawing hold after a load delays the START of the fade, not its duration: test_loading)
            for i in range(d - 1): e.tick_fade(); e.tick_transition(); self.assertTrue(e.battle_transition(), 'image %d' % i)
            e.tick_fade(); self.assertEqual(e.fade['n'], 0)
        self.assertEqual([PJ.fade_duration(30, v) for v in (1.0, 2.0, 3.0, 4.0)], [30, 15, 10, 8])

    def test_battle_end_and_map_return_fades_follow_transition_speed(self):
        for vf in (1.0, 2.0, 4.0):
            d, d3 = PJ.fade_duration(30, vf), PJ.fade_duration(3, vf)
            e = state(ENGINE.PART_BATTLE, vf); e.apply([(9, [BATTLE_FADE], [])], lambda: '')
            self.assertEqual(e.fade['n'], d, 'x%g' % vf); self.assertTrue(e.battle_transition())
            for _ in range(d): e.tick_fade(); e.tick_transition()
            self.assertEqual(e.fade['n'], 0); self.assertGreater(e.transition_guard, 0); self.assertTrue(e.battle_transition())       # the engine changes scene 1 to 3 frames later
            e.apply([(9, [0x4000 | 3], [])], lambda: ''); self.assertEqual(e.background_fade['n'], d3 if d3 > 1 else 0)           # background plane fade (still in the battle part): same rule
            e.tick_fade(); e.tick_transition()
            e.part = ENGINE.PART_FIELD; e.return_window = ENGINE.BATTLE_RETURN_WINDOW                                                   # (Engine.step: the part leaves the battle)
            e.apply([(9, [ENTRY_30], [])], lambda: ''); self.assertEqual(e.fade['n'], d, 'retour x%g' % vf); self.assertTrue(e.fade['battle'])
            for _ in range(d): self.assertTrue(e.battle_transition()); e.tick_fade(); e.tick_transition()
            for _ in range(ENGINE.TRANSITION_GUARD + 2): e.tick_fade(); e.tick_transition()
            self.assertFalse(e.battle_transition())                                                                               # the transition is over: walking takes its settings back

    def test_cascade_follows_transition_speed(self):
        """Engine._start_battle_effect / _battle_effect (without an engine: the effect flag is simulated): 57 frames at x1, 57 / factor afterward; the viewer's simulation reaches its 57 frames at the last draw."""
        import math
        for vf in (1.0, 2.0, 3.0, 4.0):
            ENGINE.State.fade_speed = vf; e = ENGINE.State(); eng = types.SimpleNamespace(state=e, _effect_flag=lambda a: None)
            ENGINE.Engine._start_battle_effect(eng, 0); d = PJ.fade_duration(ENGINE.BATTLE_EFFECT_FRAMES, vf); self.assertEqual(e.effect['duration'], d); n = 0; targets = []
            while e.effect is not None:
                targets.append(math.ceil(e.effect['n'] * ENGINE.BATTLE_EFFECT_FRAMES / e.effect['duration'])); ENGINE.Engine._battle_effect(eng); n += 1
            self.assertEqual(n, d, 'x%g' % vf); self.assertEqual(targets[0], 0); self.assertGreaterEqual(targets[-1], ENGINE.BATTLE_EFFECT_FRAMES - math.ceil(ENGINE.BATTLE_EFFECT_FRAMES / d))      # (last draw: the cascade is nearly finished)
            self.assertTrue(all(b >= a for a, b in zip(targets, targets[1:])))
        self.assertEqual([PJ.fade_duration(ENGINE.BATTLE_EFFECT_FRAMES, v) for v in (1.0, 2.0, 4.0)], [57, 28, 14])
        e = ENGINE.State(); e.effect = {'n': 3}; eng = types.SimpleNamespace(state=e, _effect_flag=lambda a: None)           # (state saved before the 'duree' key: 57 frames)
        for _ in range(ENGINE.BATTLE_EFFECT_FRAMES - 4): ENGINE.Engine._battle_effect(eng)
        self.assertIsNotNone(e.effect); ENGINE.Engine._battle_effect(eng); self.assertIsNone(e.effect)

    def test_arrival_window_elapses(self):
        """A fade started well after the battle load (or an ordinary map) remains subject to "Transition speed"."""
        e = state(ENGINE.PART_FIELD, 2.0); e.apply([(0, [0x100], [])], lambda: 'btl_pl_d')
        for _ in range(ENGINE.BATTLE_ENTRY_WINDOW + 1): e.tick_transition()
        e.load_wait = None; e.part = ENGINE.PART_FIELD
        e.apply([(9, [ENTRY_30], [])], lambda: ''); self.assertEqual(e.fade['n'], 15); self.assertFalse(e.fade['battle']); self.assertFalse(e.battle_transition())
        e2 = state(ENGINE.PART_FIELD, 2.0); e2.apply([(0, [0], []), (9, [ENTRY_30], [])], lambda: 'mak1f1'); self.assertEqual(e2.fade['n'], 15)       # an ordinary map change stays shortened
        self.assertFalse(e2.battle_transition())

    def test_script_and_color_fades_unchanged(self):
        e = state(ENGINE.PART_BATTLE, 4.0); e.apply([(9, [0x1000 | 0x800 | 20], [1.0, 0.0, 0.0])], lambda: ''); self.assertEqual(e.fade['n'], 20)
        e = state(ENGINE.PART_FIELD, 4.0); e.apply([(9, [PJ.SCRIPT_FADE_MARK | 0x1000 | 60], [])], lambda: ''); self.assertEqual(e.fade['n'], 60)

    def test_state_stored_before_transition(self):
        e = state(); d = dict(e.__dict__)
        for k in ('entry_window', 'return_window', 'transition_guard'): d.pop(k)
        e2 = ENGINE.State.__new__(ENGINE.State); e2.__setstate__(d); self.assertFalse(e2.battle_transition()); self.assertEqual(e2.transition_guard, 0)
        d['fade'] = {k: v for k, v in d['fade'].items() if k != 'battle'}
        e3 = ENGINE.State.__new__(ENGINE.State); e3.__setstate__(d); self.assertFalse(e3.battle_transition())                       # (fade plane without the 'combat' key)


@unittest.skipIf(F is None, 'window.py non importable ici')
class Clock(unittest.TestCase):
    @staticmethod
    def game(e, battle_speed=1.0, accel=1.0, accel_held=False, direction=True, menu=None, flags=0x28):
        j = types.SimpleNamespace(reg={'battle_speed': battle_speed, 'accel_speed': accel})
        j.engine = types.SimpleNamespace(state=e, msg_visible=False, active_menu=lambda: menu, flags=lambda: flags, ui=types.SimpleNamespace(msg={'feed': False}))
        j.pad = lambda: ENGINE.UP if direction else 0; j._held = lambda a: accel_held and a == 'accel'; j.hud = types.SimpleNamespace(dpad_run=lambda: False); j.pause = types.SimpleNamespace(opened=False)
        for name_str in ('_battle_clock', '_wait_for_player'): setattr(j, name_str, types.MethodType(getattr(F.Game, name_str), j))
        j.factor = lambda: F.Game._speed_factor(j)
        return j

    SETTINGS = list(itertools.product((0.0, 1.0, 2.0, 3.0), (1.0, 1.5, 2.0, 8.0), (False, True)))

    def test_cascade_on_game_clock(self):
        for vc, accel, held_name in self.SETTINGS:
            e = state(ENGINE.PART_FIELD); e.effect = {'n': 5}
            self.assertEqual(self.game(e, vc, accel, held_name).factor(), 1.0, 'cascade %s' % ((vc, accel, held_name),))

    def test_battle_speed_applies_from_cascade_end_through_final_fade(self):
        for vc, accel, held_name in self.SETTINGS:
            expected = max(1.0, vc); r = (vc, accel, held_name)
            e = state(ENGINE.PART_FIELD); e.load_wait = {'base': 0, 'n': 1}
            self.assertEqual(self.game(e, *r).factor(), expected, 'black screen after the cascade %s' % (r,))
            e = state(ENGINE.PART_BATTLE); e.entry_window = 5; e.apply([(9, [ENTRY_30], [])], lambda: '')
            self.assertEqual(self.game(e, *r).factor(), expected, 'arrival fade and "X appears" message %s' % (r,))
            e = state(ENGINE.PART_BATTLE); e.apply([(9, [BATTLE_FADE], [])], lambda: ''); self.assertTrue(e.battle_transition())
            self.assertEqual(self.game(e, *r).factor(), expected, 'fondu au noir de fin de combat %s' % (r,))
            e.transition_guard = 5; e.fade['n'] = 0
            self.assertEqual(self.game(e, *r).factor(), expected, 'frames between two fades, still in the battle part %s' % (r,))

    def test_return_to_map_game_clock_while_player_locked(self):
        """Return fade: game clock while the player is locked (flag 4, frames 1 to 11) and between two fades; as soon as the lock drops, walking and the accelerator take effect."""
        for vc, accel, held_name in self.SETTINGS:
            r = (vc, accel, held_name)
            e = state(ENGINE.PART_FIELD); e.return_window = 5; e.apply([(9, [ENTRY_30], [])], lambda: ''); self.assertTrue(e.battle_transition())
            self.assertEqual(self.game(e, *r, flags=0x2d).factor(), 1.0, 'fondu de retour, joueur verrouille %s' % (r,))
            expected = max(0.25, min(4.0, (accel if held_name else 1.0)))
            self.assertEqual(self.game(e, *r, flags=0x29).factor(), expected, 'fondu de retour, joueur libre %s' % (r,))
            e.fade['n'] = 0; e.transition_guard = 4
            self.assertEqual(self.game(e, *r, flags=0x1).factor(), 1.0, 'between two fades on the map %s' % (r,))

    def test_battle_turns_keep_accelerating(self):
        for vc in (0.0, 1.0, 2.0, 3.0):
            for accel, held_name in ((1.0, False), (2.0, True)):
                self.assertEqual(self.game(state(ENGINE.PART_BATTLE), vc, accel, held_name).factor(), max(1.0, vc))                     # outside a transition: the battle speed applies
                self.assertEqual(self.game(state(ENGINE.PART_BATTLE), vc, accel, held_name, menu=13).factor(), max(1.0, vc))           # (player waits too: the monsters keep their pace)

    def test_walk_keeps_settings_outside_transition(self):
        self.assertEqual(self.game(state(ENGINE.PART_FIELD), 3.0, 1.5, True).factor(), 1.5)
        self.assertEqual(self.game(state(ENGINE.PART_FIELD), 3.0, 8.0, True).factor(), 4.0)          # (x4 at most)

    def test_step_triggering_cascade_stops_catchup(self):
        """Accelerated walking (up to 8 steps per frame): when one of the steps raises the battle start effect, the remaining steps of the frame must not shorten the cascade: the catch-up stops (True = continue)."""
        e = state(ENGINE.PART_FIELD); calls = []
        j = types.SimpleNamespace(engine=types.SimpleNamespace(state=e), _step=lambda mute=False: calls.append(mute))
        self.assertTrue(F.Game._terrain_step(j)); self.assertTrue(F.Game._do_battle_step(types.SimpleNamespace(engine=j.engine, _t_real_step=0.0, _wait_for_player=lambda: False, _step=j._step)))
        def lift(mute=False): e.effect = {'n': 0}
        j._step = lift; self.assertFalse(F.Game._terrain_step(j))                                       # the cascade just started during this step: stop
        self.assertTrue(F.Game._terrain_step(j))                                                         # (already in transition: continue normally)
        e.effect = None
        jc = types.SimpleNamespace(engine=types.SimpleNamespace(state=e), _t_real_step=0.0, _wait_for_player=lambda: False, _step=lift)
        self.assertFalse(F.Game._do_battle_step(jc))                                                  # same during an accelerated battle (exit fade)


@unittest.skipUnless(APK and SAVES and F is not None, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    """Replays real encounters (world map, forced encounter, attack until victory) with "Transition speed" x1, x2 and x4: durations in engine frames; real time simulated with the real function
    Game._speed_factor for all combinations of settings (battle speed x walking x accelerator x held key)."""
    @classmethod
    def setUpClass(cls):
        cls.settings = Clock.SETTINGS
        cls.runs = {vf: cls.replay(vf) for vf in (1.0, 2.0, 4.0)}

    @classmethod
    def replay(cls, fade_speed):
        ENGINE.State.fade_speed = fade_speed
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_trans_'))
        for _ in range(3): eng.step(0, 0)
        eng.load_save(4)
        for i in range(100): eng.step(0, 0x10 if i % 10 == 0 else 0)
        if eng.state.part != ENGINE.PART_FIELD:
            eng.start_field()
            for i in range(120): eng.step(0, 0)
        c = eng.core
        c.call(eng.E('_ZN7Encount12forceEncountEv'), c.call(eng.E('_ZN7Encount12getSingletonEv'), label='enc'), label='force')
        step = []; packets9 = []                                                          # one entry per engine step (state AFTER the step): frame, part, cascade, black screen, foreground plane (n, exit?), transition?, factors per setting
        att = 0; rel = None; end = None; seen_battle = False
        for i in range(6000):
            p = d = 0
            if rel is not None: eng.send_menu(rel, 1, -1, 0); rel = None
            port = eng.active_menu()
            if eng.state.part == ENGINE.PART_BATTLE and port is not None and not eng.msg_visible:
                att += 1
                if att % 4 == 0: eng.send_menu(port, 1, -1, 0x10); rel = port
            elif eng.state.part == ENGINE.PART_BATTLE and eng.msg_visible and eng.message_state()[1] in (3, 5):
                att += 1
                if att > 100 and att % 4 == 0: p = d = ENGINE.A
            else: att = 0
            if not seen_battle: p = [0x4, 0x8][(i // 20) % 2]; d = 0                    # (walking: the forced encounter triggers while walking)
            prev = eng.state.part; pkt = eng.step(p, d); eng.ui.damage = []
            for t, a, f in pkt:
                if t == 9: packets9.append((eng.frames, a[0] & 0x7ff, bool(a[0] & 0x1000), bool(a[0] & 0x4000)))
            if eng.state.part == ENGINE.PART_BATTLE: seen_battle = True
            e = eng.state
            games = [Clock.game(e, vc, accel, held_name, menu=eng.active_menu(), flags=eng.flags()) for vc, accel, held_name in cls.settings]
            step.append(dict(im=eng.frames, part=e.part, effect=e.effect is not None, wait=e.load_wait is not None, fn=e.fade['n'], fade_out=e.fade['end'] >= 1.0, trans=e.battle_transition(), lock=bool(eng.flags() & ENGINE.PLAYER_LOCKED_FLAG), guard=e.transition_guard,
                            factors=[j.factor() for j in games]))
            if seen_battle and prev == ENGINE.PART_BATTLE and e.part != ENGINE.PART_BATTLE: end = eng.frames
            if end and eng.frames > end + 90: break
        assert end is not None, 'the battle did not end'
        ENGINE.State.fade_speed = 1.0
        return dict(step=step, packets9=packets9)

    def tearDown(self): ENGINE.State.fade_speed = 1.0

    @staticmethod
    def suites(step, cond):
        """Runs of consecutive frames that satisfy `cond`: [(index of the first step, number of steps)]."""
        out = []; start_idx = None
        for k, x in enumerate(step):
            if cond(x) and start_idx is None: start_idx = k
            if not cond(x) and start_idx is not None: out.append((start_idx, k - start_idx)); start_idx = None
        if start_idx is not None: out.append((start_idx, len(step) - start_idx))
        return out

    def test_cascade_lasts_57_frames_divided_by_transition_speed(self):
        for vf, parent_idx in self.runs.items():
            casc = self.suites(parent_idx['step'], lambda x: x['effect']); self.assertEqual(len(casc), 1, 'x%g: one cascade per battle (%r)' % (vf, casc))
            self.assertEqual(casc[0][1], PJ.fade_duration(ENGINE.BATTLE_EFFECT_FRAMES, vf), 'Vitesse de transition x%g' % vf)

    def test_battle_end_and_return_fades_follow_transition_speed(self):
        """Ending fade to black (in the battle part): the engine requests it in 30 frames; State replays it in 30 / factor."""
        for vf, parent_idx in self.runs.items():
            d = PJ.fade_duration(30, vf); self.assertIn(30, [x[1] for x in parent_idx['packets9']])
            ends = self.suites(parent_idx['step'], lambda x: x['part'] == ENGINE.PART_BATTLE and x['fade_out'] and x['fn'] >= 1)
            self.assertTrue(ends, 'x%g : fondu de fin non vu' % vf); self.assertEqual(max(n for _, n in ends), d - 1, 'fin de combat, x%g' % vf)          # (after the step that starts it: d - 1 frames remaining)
            back = self.suites(parent_idx['step'], lambda x: x['part'] != ENGINE.PART_BATTLE and not x['effect'] and not x['wait'] and x['fn'] >= 1 and not x['fade_out'] and x['trans'])
            self.assertTrue(back and max(n for _, n in back) in (d - 1, d), 'back to the map, x%g: %r' % (vf, back))

    def test_acceleration_starts_at_cascade_end_lasts_through_end_fade(self):
        for vf, parent_idx in self.runs.items():
            step = parent_idx['step']; casc = self.suites(step, lambda x: x['effect'])[0]; casc_end = casc[0] + casc[1]
            for k in range(casc[0], casc_end):
                for r, regl in enumerate(self.settings): self.assertEqual(step[k]['factors'][r], 1.0, 'cascade, image %d, %s' % (k, regl))
            ends = self.suites(step, lambda x: x['part'] == ENGINE.PART_BATTLE and x['fade_out'] and x['fn'] >= 1)
            for k, x in enumerate(step):
                if k < casc_end or not (x['part'] == ENGINE.PART_BATTLE or x['wait']): continue
                for r, (vc, *_r) in enumerate(self.settings): self.assertEqual(x['factors'][r], max(1.0, vc), 'vf x%g image %d (partie %#x), vitesse de combat %g' % (vf, k, x['part'], vc))
            for start_idx, n in ends:                                                                  # the ending fade to black: still accelerated
                for k in range(start_idx, start_idx + n):
                    for r, (vc, *_r) in enumerate(self.settings): self.assertEqual(step[k]['factors'][r], max(1.0, vc))
            self.assertTrue(any(x['wait'] and not x['effect'] for x in step[casc_end:casc_end + 8]) or step[casc_end]['part'] == ENGINE.PART_BATTLE)      # (the first frame after the cascade is already the black screen or the battle)

    def test_real_time(self):
        """Real time = sum of 1 / (30 x factor): the cascade lasts (57 / transition speed) / 30 s whatever the settings; the battle-end fade, on the other hand, follows the battle speed; the return to the map stays on the game clock while the player is locked, then follows walking."""
        for vf, parent_idx in self.runs.items():
            step = parent_idx['step']; start_idx, n = self.suites(step, lambda x: x['effect'])[0]
            back = self.suites(step, lambda x: x['part'] != ENGINE.PART_BATTLE and not x['effect'] and not x['wait'] and x['trans'])
            ends = self.suites(step, lambda x: x['part'] == ENGINE.PART_BATTLE and x['fade_out'] and x['fn'] >= 1)
            for r, (vc, accel, held_name) in enumerate(self.settings):
                self.assertAlmostEqual(sum(STEP / step[k]['factors'][r] for k in range(start_idx, start_idx + n)), PJ.fade_duration(ENGINE.BATTLE_EFFECT_FRAMES, vf) * STEP, 9, 'cascade %s x%g' % ((vc, accel, held_name), vf))
                for d0, m in ends: self.assertAlmostEqual(sum(STEP / step[k]['factors'][r] for k in range(d0, d0 + m)), m * STEP / max(1.0, vc), 9, 'fondu de fin %s x%g' % ((vc, accel, held_name), vf))
                for d0, m in back:
                    for k in range(d0, d0 + m):                                          # the return to the map: game clock while the player is locked or between two fades; the walking setting as soon as the lock drops
                        expected = 1.0 if step[k]['lock'] or step[k]['guard'] > 0 else max(0.25, min(4.0, (accel if held_name else 1.0)))
                        self.assertEqual(step[k]['factors'][r], expected, 'back to the map, step %d, %s x%g' % (k, (vc, accel, held_name), vf))

if __name__ == '__main__':
    unittest.main()
