"""Test of the battle speed (Manuel / Normal / Rapide / Tres rapide): setting, cycle, engine clock, independence from the accelerator, music and sound effects not accelerated, battle screen button.
Without a window or an engine (fake objects); the "real engine" part is optional: DQ_APK=<APKs folder> DQ_SAVES=<saves folder> runs it (replay of a battle at 1, 2 and 3 steps per frame).

    python3 tests/test_battle_speed.py       (Linux without a display: pyglet in "headless" mode)
"""
import json, math, os, random, re, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq4_pc)
from dq4_pc.persistence import settings as RG
from dq4_pc.battle import battle_speed as VC

try:
    import pyglet
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
    from dq4_pc.window import game as F
    from dq4_pc.menus import hud_mobile as HM
    from dq4_pc.core import engine as ENGINE
    from dq4_pc.battle import battle_effect as EC
except Exception as ex:                                                     # (no pyglet / engine here: the tests that need them are skipped)
    F = HM = ENGINE = None; IMPORT_ERROR = ex

STEP = VC.ENGINE_STEP


def load(content):
    f = os.path.join(tempfile.mkdtemp(prefix='rg_test_'), 'settings.json')
    with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
    return RG.Settings(f), f


class Setting(unittest.TestCase):
    def test_default_normal(self):
        r = RG.Settings(None); self.assertEqual(r['battle_speed'], 1.0); self.assertEqual(RG.DEFAULT['battle_speed'], 1.0)
        self.assertEqual(RG.BATTLE_SPEEDS, (0.0, 1.0, 2.0, 3.0))

    def test_labels_never_x(self):
        self.assertEqual([RG.BATTLE_SPEED_NAMES[v] for v in RG.BATTLE_SPEEDS], ['settings.manual', 'settings.normal', 'settings.fast', 'settings.very_fast'])
        self.assertFalse(any(re.search(r'\bx\d', n) for n in RG.BATTLE_SPEED_NAMES.values()))

    def test_validation(self):
        for raw_value, expected in ((0, 0.0), (1, 1.0), (2, 2.0), (3, 3.0), (1.0, 1.0), (2.4, 2.0), (1.5, 2.0), (2.5, 3.0), (0.4, 0.0), (0.5, 1.0), (-4, 0.0), (4, 3.0), (99, 3.0), (float('inf'), 3.0), (float('-inf'), 0.0),
                              (float('nan'), 1.0), ('2', 1.0), ('x', 1.0), (None, 1.0), (True, 1.0), (False, 1.0), ([2], 1.0), ({'a': 2}, 1.0)):
            self.assertEqual(RG.battle_notch(raw_value), expected, repr(raw_value))
            r, _ = load({'battle_speed': raw_value}); self.assertEqual(r['battle_speed'], expected, 'fichier : %r' % (raw_value,))
        r, _ = load({'sound': False}); self.assertEqual(r['battle_speed'], 1.0)                      # absent: Normal

    def test_cycle(self):
        v = 1.0; seen = []
        for _ in range(9): v = RG.next_battle_speed(v); seen.append(v)
        self.assertEqual(seen, [2.0, 3.0, 0.0, 1.0, 2.0, 3.0, 0.0, 1.0, 2.0])                         # Normal -> Fast -> Very fast -> Manual -> Normal
        self.assertEqual(RG.next_battle_speed('x'), 2.0); self.assertEqual(RG.next_battle_speed(None), 2.0)    # invalid value: read as Normal

    def test_storage(self):
        r, f = load({}); r['battle_speed'] = 3.0; r.store()
        self.assertEqual(RG.Settings(f)['battle_speed'], 3.0)
        with open(f, encoding='utf-8') as fh: self.assertEqual(json.load(fh)['battle_speed'], 3.0)

    def test_default_key_free(self):
        d = RG.DEFAULT_KEYS['battle_speed']; self.assertEqual(d, ['V', None])
        for a, ts in RG.DEFAULT_KEYS.items():
            if a != 'battle_speed': self.assertNotIn('V', ts, a)                                      # no conflict with the existing keys
        self.assertNotIn('V', RG.RESERVED)
        self.assertIn('battle_speed', dict(RG.ACTIONS)); self.assertEqual(dict(RG.ACTIONS)['battle_speed'], 'settings.change_battle_speed')
        r = RG.Settings(None); self.assertEqual(r['keys']['battle_speed'], ['V', None]); self.assertEqual(r.action_of(RG.key_symbol('V')), 'battle_speed')

    def test_old_file_takes_default_key(self):
        r, _ = load({'keys_version': 4, 'keys': {'map': ['M', None]}}); self.assertEqual(r['keys']['battle_speed'], ['V', None])
        r, _ = load({'keys_version': 4, 'keys': {'map': ['V', None]}})                            # another action already took V: the new action has no key (and the other action's key is kept)
        self.assertEqual(r['keys']['battle_speed'], [None, None]); self.assertEqual(r['keys']['map'], ['V', None])

    def test_interface_classification(self):
        self.assertNotIn('battle_speed', RG.INTERFACE_KEYS)                                         # a game setting, not an interface one; the button has its own interface (RG.SPEED_TARGET: speed_button, _taille, _pos)


class Factor(unittest.TestCase):
    def test_outside_battle_nothing(self):
        for v in (0.0, 1.0, 2.0, 3.0): self.assertIsNone(VC.factor(v, False))

    def test_battle(self):
        self.assertEqual([VC.factor(v, True) for v in (0.0, 1.0, 2.0, 3.0)], [1.0, 1.0, 2.0, 3.0])            # Manuel and Normal: the game clock

    def test_absurd_values(self):
        self.assertEqual(VC.factor(9, True), 3.0); self.assertEqual(VC.factor(0.2, True), 1.0)
        for v in (None, 'x', float('nan')): self.assertEqual(VC.factor(v, True), 1.0)


class MessageScrolling(unittest.TestCase):
    """The "Battle speed" also sets OptionStatus.battleSpeed: 4 (manual) in Manuel, 0 (12 frames, the shortest) otherwise."""
    def test_imposed_code(self):
        self.assertEqual([RG.scroll_code(v) for v in (0.0, 1.0, 2.0, 3.0)], [4, 0, 0, 0])
        self.assertEqual(RG.scroll_code('x'), 0); self.assertEqual(RG.scroll_code(None), 0)             # invalid value: Normal

    def test_game_changes_message_speed(self):
        self.assertEqual(RG.speed_after_game_code(4, 2.0), 0.0)                                              # Manuel chosen in the game
        self.assertEqual(RG.speed_after_game_code(0, 0.0), 1.0); self.assertEqual(RG.speed_after_game_code(3, 0.0), 1.0)      # other value: leaves Manuel (Normal)
        self.assertEqual(RG.speed_after_game_code(0, 3.0), 3.0); self.assertEqual(RG.speed_after_game_code(2, 2.0), 2.0)      # outside Manuel: the notch is kept
        self.assertEqual(RG.speed_after_game_code('x', 2.0), 2.0)

    def test_old_setting_messages_in_battle(self):
        r, _ = load({'defilement_force': True, 'defilement_combat': 4, 'battle_speed': 3.0}); self.assertEqual(r['battle_speed'], 0.0)           # old "Manual": becomes the Manuel speed
        for old in (0, 2, 3):                                                                              # other notches: no equivalent anymore, the saved battle speed remains
            r, _ = load({'defilement_force': True, 'defilement_combat': old, 'battle_speed': 2.0}); self.assertEqual(r['battle_speed'], 2.0)
        r, _ = load({'defilement_force': False, 'defilement_combat': 4, 'battle_speed': 2.0}); self.assertEqual(r['battle_speed'], 2.0)       # not forced: the game's save decided, not the player
        r, _ = load({'defilement_auto': False, 'defilement_force': True}); self.assertEqual(r['battle_speed'], 0.0)      # any old "Automatic scrolling: no" forced
        r, _ = load({'defilement_auto': False}); self.assertEqual(r['battle_speed'], 1.0)                 # (nothing was forced: the game's save decided)
        r, _ = load({'defilement_force': True, 'defilement_combat': 4}); r.store()
        with open(r.path, encoding='utf-8') as fh: d = json.load(fh)
        self.assertEqual(d['battle_speed'], 0.0); self.assertNotIn('defilement_force', d); self.assertNotIn('defilement_combat', d)           # the old keys disappear from the file


class Clock(unittest.TestCase):
    @staticmethod
    def simulate(f, seconds=10.0, cost=0.0, fps=60.0, waiting=None, budget=VC.STEP_BUDGET):
        """Replays `seconds` of displayed frames at `fps` with a dummy engine of `cost` seconds per step -> (number of steps, maximum step time in a frame, number of cut frames)."""
        h = [0.0]; acc = 0.0; step = [0]; max_img = 0.0; cuts = 0
        def perform():
            step[0] += 1; h[0] += cost
            return not (waiting and waiting(step[0]))
        for _ in range(int(seconds * fps)):
            t0 = h[0]; h[0] += 0.0                                                  # (display time is not part of the step budget)
            acc, n, cut = VC.advance_time(acc, 1.0 / fps, f, perform, lambda: h[0], STEP, budget)
            max_img = max(max_img, h[0] - t0); cuts += cut; h[0] += 1.0 / fps
        return step[0], max_img, cuts

    def test_step_count_per_second(self):
        for f in (1.0, 2.0, 3.0):
            n, _, _ = self.simulate(f); self.assertAlmostEqual(n / 10.0, 30.0 * f, delta=0.6, msg='x%g' % f)       # 30, 60, 90 steps per real second (60 Hz)

    def test_other_display_rates(self):
        for fps in (30.0, 75.0, 144.0, 240.0):
            for f in (1.0, 2.0, 3.0):
                n, _, _ = self.simulate(f, fps=fps); self.assertAlmostEqual(n / 10.0, 30.0 * f, delta=0.04 * 30.0 * f + 0.6, msg='x%g a %g Hz' % (f, fps))

    def test_compute_budget_bounded(self):
        """Engine steps more expensive than the PC can handle: the computation time of a frame stays bounded (budget + one step), the game slows down instead of freezing the display."""
        n, max_img, cuts = self.simulate(3.0, cost=0.012); self.assertAlmostEqual(n / 10.0, 90.0, delta=0.6); self.assertEqual(cuts, 0)         # cheap step (12 ms): full rate, nothing is cut
        n, max_img, cuts = self.simulate(3.0, cost=0.035)                                                                                        # heavy step (35 ms): only one step per frame, so 60 steps per second (x2 instead of x3)
        self.assertLessEqual(max_img, VC.STEP_BUDGET + 0.035 + 1e-9); self.assertAlmostEqual(n / 10.0, 60.0, delta=0.6); self.assertGreater(cuts, 0)
        n, max_img, cuts = self.simulate(2.0, cost=0.035); self.assertAlmostEqual(n / 10.0, 60.0, delta=0.6)                                     # x2 needs one step per frame at 60 Hz: holds even with a heavy step
        for f in (2.0, 3.0):
            for cost in (0.012, 0.02, 0.035, 0.08):
                n, max_img, _ = self.simulate(f, cost=cost); self.assertLessEqual(max_img, VC.STEP_BUDGET + cost + 1e-9, 'x%g %g s' % (f, cost)); self.assertGreaterEqual(n / 10.0, 59.4, 'x%g %g s' % (f, cost))     # never below x2 per displayed frame

    def test_smooth_display(self):
        """the displayed instant (engine steps + Game.alpha) advances by the real time of each frame, at every refresh rate and walking / battle speed, with or without a little timing jitter:
        no early step that makes it jump then stall (ev09's clouds shook). The 15 % tolerance stays: at 60 Hz, exactly one step every 2 frames."""
        for fps in (60.0, 75.0, 120.0, 144.0, 165.0, 240.0):
            for f in (1.0, 2.0, 3.0, 4.0):
                for jitter in (0.0, 0.05):
                    rnd = random.Random(3); acc = 0.0; steps = [0]; shown = []; dts = []
                    def perform(): steps[0] += 1
                    for _ in range(int(3 * fps)):
                        dt = 1.0 / fps * (1.0 + rnd.uniform(-jitter, jitter)); dts.append(dt)
                        acc, _, _ = VC.advance_time(acc, dt, f, perform, lambda: 0.0, STEP)
                        shown.append(steps[0] - 1 + VC.display_fraction(acc, STEP))         # what Game._loop draws: previous step + alpha
                    for k in range(20, len(shown) - 1):
                        self.assertAlmostEqual(shown[k + 1] - shown[k], dts[k + 1] * f / STEP, places=6, msg='%g Hz x%g jitter %g' % (fps, f, jitter))
        acc = 0.0; steps = [0]; per = []
        def perform60(): steps[0] += 1
        for k in range(600):
            dt = 1.0 / 60.0 + (0.002 if k % 3 == 0 else -0.001)                     # 60 Hz with a little jitter: still one step every 2 frames
            before = steps[0]; acc, _, _ = VC.advance_time(acc, dt, 1.0, perform60, lambda: 0.0, STEP); per.append(steps[0] - before)
        self.assertTrue(all(a + b == 1 for a, b in zip(per[10::2], per[11::2])) or all(a + b == 1 for a, b in zip(per[11::2], per[12::2])))

    def test_budget_no_effect_at_normal_speed(self):
        n, _, cuts = self.simulate(1.0, cost=0.05); self.assertEqual(cuts, 0); self.assertAlmostEqual(n / 10.0, 30.0, delta=0.6)      # (at x1 the budget does not apply: as before)

    def test_engine_waits_for_player(self):
        """When a step opens a menu (do_step returns False) no further steps are chained in the same frame, and the rest of the clock is forgotten."""
        acc, n, cut = VC.advance_time(0.0, 0.05, 3.0, lambda: False, lambda: 0.0)       # 0.15 s of engine work to do (4 steps): only one is done
        self.assertEqual((n, acc, cut), (1, 0.0, False))
        tally = [0]
        def perform(): tally[0] += 1; return tally[0] != 2                            # the 2nd step opens a menu
        acc, n, _ = VC.advance_time(0.0, 0.05, 3.0, perform, lambda: 0.0); self.assertEqual((n, acc), (2, 0.0))

    def test_identical_to_old_loop(self):
        """The loop moved into VC.advance_time does exactly what Game._loop did (including accelerated walking)."""
        def old_version(acc, dt, f, perform, clock, budget):
            acc += min(dt * f, 3 * STEP * max(1.0, f)); n = 0; nmax = 3 * max(1, math.ceil(f)); cut = False; t0 = clock()
            while acc >= STEP * 0.85 and n < nmax:
                perform(); acc -= STEP; n += 1
                if f > 1.0 and clock() - t0 > budget: cut = True; break
            if n == nmax or cut: acc = 0.0
            return acc, n, cut
        rnd = random.Random(7)
        for f in (0.25, 1.0, 1.5, 2.0, 3.0, 4.0, 8.0):
            for cost in (0.0, 0.004, 0.02):
                a1 = a2 = 0.0; h1 = [0.0]; h2 = [0.0]
                for _ in range(400):
                    dt = rnd.choice((1 / 60.0, 1 / 60.0, 1 / 30.0, 1 / 144.0, 0.1, 0.4))
                    def f1(): h1[0] += cost
                    def f2(): h2[0] += cost
                    r1 = old_version(a1, dt, f, f1, lambda: h1[0], VC.STEP_BUDGET); r2 = VC.advance_time(a2, dt, f, f2, lambda: h2[0], STEP, VC.STEP_BUDGET)
                    self.assertEqual(r1[1:], r2[1:]); self.assertAlmostEqual(r1[0], r2[0], places=12); a1, a2 = r1[0], r2[0]; h1[0] += dt; h2[0] += dt


class Sounds(unittest.TestCase):
    def test_no_duplicate_in_frame(self):
        already = set()
        step1 = VC.sounds_to_play([(35, 412), (37, 30)], already); step2 = VC.sounds_to_play([(35, 412), (35, 402)], already); step3 = VC.sounds_to_play([(35, 402), (35, 412)], already)
        self.assertEqual(step1, [(35, 412), (37, 30)]); self.assertEqual(step2, [(35, 402)]); self.assertEqual(step3, [])
        self.assertEqual(VC.sounds_to_play([(35, 412)], set()), [(35, 412)])                       # next frame: played again

    def test_a_frame_filters_only_sfx(self):
        already = set(); self.assertEqual(VC.sounds_to_play([(37, 30), (37, 30), (36, 412), (36, 412)], already), [(37, 30), (37, 30), (36, 412), (36, 412)])     # music and stops: intact

    def test_start_stop_start(self):
        already = set(); self.assertEqual(VC.sounds_to_play([(35, 311), (36, 311), (35, 311)], already), [(35, 311), (36, 311), (35, 311)])                    # a stop releases the sound effect

    def test_without_filter_everything_passes(self):
        evts = [(35, 412), (35, 412), (37, 5)]; self.assertEqual(VC.sounds_to_play(evts, None), evts)

    def test_playback_speed_and_duration_unchanged(self):
        """A frame displayed at x3 sends several steps: the sound effect is started only once, with the duration of its file (no notion of speed in the sound module); the music keeps its real clock."""
        try:
            sys.modules.setdefault('pyglet', None)
            from dq4_pc import sound as SOUND
        except Exception as ex: self.skipTest('sound.py non importable ici (%r)' % (ex,))
        launched = []
        class Player:
            def __init__(self): self.volume = 1.0; self.playing = False
            def queue(self, src): pass
            def play(self): self.playing = True; launched.append(self)
            def pause(self): self.playing = False
            def delete(self): self.playing = False
        s = SOUND.Sound('inexistant.apk', '/tmp', log=lambda *a: None)
        s.ok = True; s.ogg = True; s.media = types.SimpleNamespace(Player=Player, Source=object); s.AudioFormat = lambda **kw: kw; s.AudioData = None; SOUND.LoopSource = lambda *a: None
        s.dec['SE0412'] = dict(pcm=__import__('numpy').zeros((11025, 1), 'int16'), frequency=22050, start=0, end=0, volume=0.5, loop=False)       # 0,5 s
        import time
        for f in (1.0, 3.0):
            launched.clear(); s.sfx.clear(); already = set() if f > 1.0 else None
            t0 = time.time()
            for _ in range(3): s.events(VC.sounds_to_play([(35, 412)], already))                # three engine steps in the same displayed frame
            self.assertEqual(len(launched), 1 if f > 1.0 else 3, 'x%g' % f)
            for x in s.sfx: self.assertAlmostEqual(x.end - t0, 0.5 + 0.5, delta=0.1)          # file duration (0.5 s) + release margin: the same at all speeds
        with open(SOUND.__file__, encoding='utf-8') as fh: src = fh.read()
        for word in ('battle_speed', 'accel_speed', 'import battle_speed'): self.assertNotIn(word, src, word)         # the sound module does not know the accelerated clock


@unittest.skipIf(F is None, 'window.py non importable ici')
class AcceleratorIndependence(unittest.TestCase):
    @staticmethod
    def fake(part, battle_speed=1.0, accel=1.0, accel_held=False, direction=True, effect=None, waiting=None, menu=None, msg=False, feed=False):
        j = types.SimpleNamespace(reg={'battle_speed': battle_speed, 'accel_speed': accel})
        state = ENGINE.State(); state.part = part; state.effect = effect; state.load_wait = waiting           # (the real State: battle_transition() decides the clock of the cascade and the fades)
        j.engine = types.SimpleNamespace(state=state, msg_visible=msg, active_menu=lambda: menu, flags=lambda: 0x28, ui=types.SimpleNamespace(msg={'feed': feed}))
        j.pad = lambda: ENGINE.UP if direction else 0
        j._held = lambda a: accel_held and a == 'accel'; j.hud = types.SimpleNamespace(dpad_run=lambda: False); j.pause = types.SimpleNamespace(opened=False)
        for name_str in ('_battle_clock', '_wait_for_player', '_jingle_wait'): setattr(j, name_str, types.MethodType(getattr(F.Game, name_str), j))
        j.sound = None                                                                                        # (no sound: no jingle to wait for)
        j.factor = lambda: F.Game._speed_factor(j)
        return j

    def test_jingle_in_battle_keeps_the_battle_speed(self):
        """a jingle or the victory fanfare holds the message, not the battle's speed."""
        j = self.fake(ENGINE.PART_BATTLE, 3.0); j.sound = types.SimpleNamespace(jingle_playing=lambda: True); self.assertEqual(j.factor(), 3.0)
        j.sound = types.SimpleNamespace(jingle_playing=lambda: False); self.assertEqual(j.factor(), 3.0)
        j = self.fake(ENGINE.PART_FIELD, 1.0, 2.0, True); j.sound = types.SimpleNamespace(jingle_playing=lambda: True); self.assertEqual(j.factor(), 2.0)

    def test_accelerator_does_not_accelerate_battle(self):
        for v in (0.0, 1.0, 2.0, 3.0):
            for accel, held_name in ((1.0, False), (8.0, True), (8.0, False), (2.0, True), (1.5, True)):
                j = self.fake(ENGINE.PART_BATTLE, v, accel, held_name); self.assertEqual(j.factor(), max(1.0, v), 'combat x%g, accelerateur x%g tenu=%s' % (v, accel, held_name))      # neither stacked nor applied

    def test_outside_battle_walk_keeps_its_settings(self):
        for part in (ENGINE.PART_TOWN, ENGINE.PART_FIELD):
            self.assertEqual(self.fake(part, 3.0, 1.0).factor(), 1.0)                                        # the battle speed has no effect on the field
            self.assertEqual(self.fake(part, 3.0, 1.5).factor(), 1.0)                                        # accelerateur non tenu : x1
            self.assertEqual(self.fake(part, 1.0, 1.5, accel_held=True).factor(), 1.5)                       # accelerateur x1,5 tenu
            self.assertEqual(self.fake(part, 1.0, 8.0, accel_held=True).factor(), 4.0)                       # (x4 at most)
            self.assertEqual(self.fake(part, 3.0, 1.5, accel_held=True, direction=False).factor(), 1.0)      # (stop: normal speed)

    def test_cascade_on_game_clock_then_battle_speed_from_black_screen(self):
        """the battle entry cascade runs on the game clock (x1 whatever the battle speed, walking speed or accelerator; its duration follows "Transition speed": see tests/test_battle_transition.py);
        as soon as it is finished, the black screen waiting for the scene (then the arrival fade and the "X apparait" message) runs at the battle speed."""
        for v in (0.0, 1.0, 2.0, 3.0):
            self.assertEqual(self.fake(ENGINE.PART_FIELD, v, 8.0, True, effect={'n': 3}).factor(), 1.0)             # effect that shatters the screen
            self.assertEqual(self.fake(ENGINE.PART_FIELD, v, 8.0, True, waiting={'base': 0, 'n': 3}).factor(), max(1.0, v))      # black screen before the battle scene

    def test_input_waits_keep_chosen_speed(self):
        """Monsters follow the battle speed even during menus: the clock stays that of the setting; only the key reading is at normal rate (silent steps: next test)."""
        self.assertEqual(self.fake(ENGINE.PART_BATTLE, 3.0, menu=13).factor(), 3.0)                              # command menu, target menu...
        self.assertEqual(self.fake(ENGINE.PART_BATTLE, 3.0, msg=True, feed=True).factor(), 3.0)                  # message waiting for a key (▼ cursor)
        self.assertEqual(self.fake(ENGINE.PART_BATTLE, 3.0, msg=True, feed=False).factor(), 3.0)                 # message that scrolls on its own
        self.assertEqual(self.fake(ENGINE.PART_BATTLE, 2.0).factor(), 2.0); self.assertEqual(self.fake(ENGINE.PART_BATTLE, 0.0, menu=13).factor(), 1.0)      # Manuel: the game clock

    def test_not_muted_during_waits(self):
        """Engine waiting for the player: only one step out of f reads the keys (one per 1 / 30 real seconds), the others are silent; otherwise all steps are ordinary."""
        from unittest import mock
        is_waiting = [True]; calls = []; h = [100.0]
        j = types.SimpleNamespace(_t_real_step=0.0, _wait_for_player=lambda: is_waiting[0], _step=lambda mute=False: calls.append(mute), engine=types.SimpleNamespace(state=ENGINE.State()))
        with mock.patch.object(F.time, 'perf_counter', lambda: h[0]):
            for _ in range(3): self.assertTrue(F.Game._do_battle_step(j))                                      # 1st step: reads the keys; the next 2 (same displayed frame): silent
            self.assertEqual(calls, [False, True, True]); h[0] += STEP; F.Game._do_battle_step(j); self.assertEqual(calls[-1], False)       # 1 / 30 s later: a step that reads the keys
            is_waiting[0] = False; calls.clear()
            for _ in range(3): F.Game._do_battle_step(j)
            self.assertEqual(calls, [False, False, False])                                                     # the engine does not hold the player: all steps are ordinary

    def test_can_be_changed_without_leaving_battle(self):
        """Key or button: the setting changes, is saved, the message scrolling follows (Manuel: manual); no message on screen (removed: the fake game has no `toast`)."""
        r = RG.Settings(None); saved = []; r.store = lambda: saved.append(r['battle_speed']); imposed = []
        vis = [()]
        j = types.SimpleNamespace(reg=r, hud=types.SimpleNamespace(visible_ones=lambda: vis[0]), apply_scroll=lambda: imposed.append(RG.scroll_code(r['battle_speed'])))
        for expected in (2.0, 3.0, 0.0, 1.0, 2.0): F.Game.change_battle_speed(j); self.assertEqual(r['battle_speed'], expected)
        self.assertEqual(saved, [2.0, 3.0, 0.0, 1.0, 2.0]); self.assertEqual(imposed, [0, 0, 4, 0, 0])
        vis[0] = (HM.BATTLE,); F.Game.change_battle_speed(j); F.Game.change_battle_speed(j)                      # (on-screen button or not: never a message)
        vis[0] = (); F.Game.change_battle_speed(j); self.assertEqual(saved[-3:], [3.0, 0.0, 1.0])


@unittest.skipIf(F is None, 'window.py non importable ici')
class EngineClock(unittest.TestCase):
    """Everything the viewer animates during a battle must follow the engine steps (engine.frames + alpha), not the real clock: otherwise, at x2 / x3, they get out of sync with the actions."""
    def test_battle_animations_without_real_clock(self):
        import inspect
        for item in (F.Game._draw_damage, F.Game._paint_fbx, F.Game._draw_effect, F.Game._draw_fade, F.Game._battle_meshes, EC.TilesEffect, ENGINE.State.tick_fade):
            src = inspect.getsource(item)
            self.assertIsNone(re.search(r'time\.(time|perf_counter|monotonic)\(', src), item.__name__)
        self.assertIn('engine.frames', inspect.getsource(F.Game._draw_damage)); self.assertIn('engine.frames', inspect.getsource(F.Game._paint_fbx))

    def test_only_real_clock_of_battle_ui_is_the_target_arrow(self):
        """ui_menu: the target arrow blinks in real time (BattleUpCursor, 0.7 s): it is a wait for player input, which is not accelerated (the speed has no effect when a menu has the input)."""
        src = _paths.source('ui_menu.py')
        self.assertEqual(sorted(set(re.findall(r'time\.(?:time|perf_counter|monotonic)\(\)', src))), ['time.monotonic()'])
        lines = [l.strip() for l in src.splitlines() if 'time.monotonic' in l]
        self.assertEqual(len(lines), 3)                                                                        # target cursor (2) and blinking of the world map locations (1)


@unittest.skipIf(HM is None, 'hud_mobile.py non importable ici')
class ScreenButton(unittest.TestCase):
    @staticmethod
    def fake(W=1280, H=720, buttons=True, part=None, effect=None, waiting=None, fade=None, pause=False, pos=None, flag=0x28, game_map=False):
        MOd = ENGINE or types.SimpleNamespace(PART_BATTLE=13)
        plan = lambda **k: dict(dict(a=0.0, end=0.0, step=0.0, n=0, col=(0, 0, 0), black=0), **k)
        f = fade or {}
        state = types.SimpleNamespace(part=MOd.PART_BATTLE if part is None else part, effect=effect, load_wait=waiting, fade=plan(**f.get('front', {})), background_fade=plan(**f.get('back', {})))
        J = types.SimpleNamespace(width=W, height=H, reg={'buttons': True, 'speed_button': buttons, 'speed_button_size': 1.0, 'speed_button_pos': pos or [], 'dpad': True, 'rotation_bar': True, 'buttons_size': 1.0, 'dpad_size': 1.0, 'buttons_pos': {}, 'buttons_snap': True},
                                  pause=types.SimpleNamespace(opened=pause), map_open=game_map, args=types.SimpleNamespace(cache='/inexistant'))
        J.engine = types.SimpleNamespace(state=state, flags=lambda: flag, dpad_size=lambda: 1)
        return J, HM.Buttons(J)

    def test_in_battle_only_the_speed_button(self):
        J, b = self.fake(); self.assertEqual(b.visible_ones(), (HM.BATTLE,))

    def test_on_the_field_not_the_speed_button(self):
        J, b = self.fake(part=12); vis = b.visible_ones(); self.assertNotIn(HM.BATTLE, vis); self.assertEqual(set(vis), {'map', 'menu', 'chat', HM.DPAD, HM.BAR})
        J, b = self.fake(part=14); self.assertNotIn(HM.BATTLE, b.visible_ones())

    def test_mask_like_the_others(self):
        self.assertEqual(self.fake(buttons=False)[1].visible_ones(), ())                                               # "Show this interface" = Non (that of the speed button: "Battle: speed button")
        self.assertEqual(self.fake(pause=True)[1].visible_ones(), ())                                                  # Pause menu open

    def test_not_during_black_screen_nor_fades_to_black(self):
        self.assertEqual(self.fake(waiting={'base': 0, 'n': 5})[1].visible_ones(), ())
        self.assertEqual(self.fake(effect={'n': 5})[1].visible_ones(), ())
        self.assertEqual(self.fake(fade={'front': dict(a=0.3, step=0.03, n=20)})[1].visible_ones(), ())                  # fade to black building up (end of battle)
        self.assertEqual(self.fake(fade={'front': dict(a=1.0)})[1].visible_ones(), ())                                  # black screen
        self.assertEqual(self.fake(fade={'back': dict(a=0.5, step=0.03, n=5)})[1].visible_ones(), ())                      # (background plane too)
        self.assertEqual(self.fake(fade={'front': dict(a=0.5, step=-0.03, n=15)})[1].visible_ones(), (HM.BATTLE,))        # fade-in: the button appears

    def test_click(self):
        J, b = self.fake(); x, y, w, h = b.rect(HM.BATTLE)
        self.assertEqual(b.press(x + w / 2, y + h / 2, (HM.BATTLE,)), HM.BATTLE); self.assertEqual(b.let_go(x + w / 2, y + h / 2, (HM.BATTLE,)), HM.BATTLE)
        self.assertEqual(b.press(x + w / 2, y + h / 2, (HM.BATTLE,)), HM.BATTLE); self.assertIsNone(b.let_go(x + w + 40, y + h / 2, (HM.BATTLE,)))     # released elsewhere: no click
        self.assertIsNone(b.under(x + w / 2, y + h / 2, ('map', 'menu')))                                          # not visible: not reachable
        self.assertNotIn(HM.BATTLE, HM.DECL)                                                                        # passes nothing to the engine

    def test_default_position_hides_no_game_element(self):
        """To the left of the portrait column (450 x 800, centered) of the game windows, at the usual formats; without covering the other buttons shown in the editor."""
        for W, H in ((1280, 720), (1920, 1080), (2560, 1080), (3440, 1440), (1366, 768), (1600, 900), (1280, 800)):
            J, b = self.fake(W, H); x, y, w, h = b.rect(HM.BATTLE); col0 = (W - 450.0 * H / 800.0) / 2.0
            self.assertGreaterEqual(x, 0); self.assertLessEqual(x + w, col0 - 4, '%dx%d: the button touches the column of the game windows' % (W, H)); self.assertTrue(0 <= y and y + h <= H)
            for n in ('map', 'menu', 'chat', HM.DPAD):
                a = b.rect(n); self.assertFalse(x < a[0] + a[2] and a[0] < x + w and y < a[1] + a[3] and a[1] < y + h, '%dx%d : recouvre %s' % (W, H, n))

    def test_movable_in_editor_and_restorable(self):
        J, b = self.fake(); x, y, w, h = b.rect(HM.BATTLE); self.assertIn(HM.BATTLE, HM.EDITOR_NAMES)
        self.assertEqual(b.take(x + 5, y + 5, HM.editor_names(RG.SPEED_TARGET)), HM.BATTLE); b.move_to(x + 5 + 400, y + 5 - 100); b.place()
        self.assertEqual(len(J.reg['speed_button_pos']), 2); self.assertEqual(J.reg['buttons_pos'], {}); x2, y2, _, _ = b.rect(HM.BATTLE); self.assertGreater(x2, x + 300); self.assertLess(y2, y)        # (own position: no longer in 'buttons_pos')
        r = RG.Settings(None); r['speed_button_pos'] = list(J.reg['speed_button_pos']); r.reset_interface(RG.SPEED_TARGET); self.assertEqual(r['speed_button_pos'], [])        # "Restore this interface" puts it back in place

    def test_editor_caption(self):
        self.assertEqual(HM.CAPTION[HM.BATTLE], 'settings.battle_speed')


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES') and ENGINE is not None, 'real engine: DQ_APK and DQ_SAVES required')
class EngineReplay(unittest.TestCase):
    """Real engine: same battle (same inputs per engine step) replayed at 1, 2 and 3 steps per displayed frame with the viewer's loop (VC.advance_time): same packets, same messages, same end; only the time changes."""
    MAX_STEPS = int(os.environ.get('DQ_STEP_MAX') or 1100)                       # engine steps compared (1100 = 37 s of battle, about thirty seconds of test)

    def replay(self, f):
        sys.path.insert(0, os.environ.get('DQ_TOOLS', HERE))
        wdir = tempfile.mkdtemp(prefix='sv_vc_'); eng = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], wdir); eng.load_save(4)
        for _ in range(200): eng.step(0, 0)
        eng.impose_scroll_mode(2)
        dirs = [ENGINE.LEFT, ENGINE.UP, ENGINE.RIGHT, ENGINE.DOWN]; n = 0
        while eng.state.part != ENGINE.PART_BATTLE and n < 6000: d = dirs[(n // 24) % 4]; eng.step(d, d if n % 24 == 0 else 0); n += 1
        self.assertEqual(eng.state.part, ENGINE.PART_BATTLE)
        trace = []; state = {'rel': None, 'pending': 0, 'k': 0}
        def input_buf():
            p = decl = 0
            if state['rel'] is not None: eng.send_menu(state['rel'], 1, -1, 0); state['rel'] = None
            port = eng.active_menu()
            if port is not None and not eng.msg_visible:
                state['pending'] += 1
                if state['pending'] % 4 == 0: eng.send_menu(port, 1, -1, 0x10); state['rel'] = port
            elif eng.msg_visible and eng.ui.msg.get('feed'):
                state['pending'] += 1
                if state['pending'] % 4 == 0: p = decl = ENGINE.A
            else: state['pending'] = 0
            return p, decl
        def perform():
            p, decl = input_buf(); pkt = eng.step(p, decl); state['k'] += 1
            trace.append((state['k'], [(t, tuple(a[:6]), tuple(round(x, 3) for x in fl[:6])) for t, a, fl in pkt if t not in (22, 28, 29)], tuple(sorted(eng.ui.msg.items())), eng.state.part, eng.msg_visible, eng.active_menu(), tuple(eng.ui.damage)))      # (+ damage numbers, which the viewer takes then empties at each step)
            eng.ui.damage = []
            return not (eng.active_menu() is not None or (eng.msg_visible and eng.ui.msg.get('feed')))
        h = [0.0]; acc = 0.0; frames = 0
        while eng.state.part == ENGINE.PART_BATTLE and state['k'] < self.MAX_STEPS:
            fac = VC.factor(f, True); fac = 1.0 if (eng.active_menu() is not None or bool(eng.msg_visible and eng.ui.msg.get('feed'))) else fac      # (the replay reads the keys at each step: waiting = normal speed, as before the silent steps)
            acc, _, _ = VC.advance_time(acc, 1.0 / 60.0, fac, perform, lambda: h[0]); h[0] += 1.0 / 60.0; frames += 1
        return trace[:self.MAX_STEPS], frames

    def test_same_battle_at_all_speeds(self):
        ref, im1 = self.replay(1.0)
        for f in (2.0, 3.0):
            tr, im = self.replay(f); n = min(len(ref), len(tr)); self.assertGreater(n, self.MAX_STEPS * 0.7)
            self.assertEqual(tr[:n], ref[:n], 'x%g: the battle is not identical' % f)                       # same packets (excluding meshes), same messages, same state, step for step
            self.assertLess(im, im1, 'x%g: not faster' % f)


@unittest.skipIf(F is None, 'window.py non importable ici')
class LevelJingleWithItsMessage(unittest.TestCase):
    """the level-up jingle and "X passe au niveau N !" start together. The engine asks for the jingle, then waits 90 frames before the message (ui_MsgLoop state
    MSG_PAUSE): the jingle's music orders are kept until the message starts (the page beep is not delayed); during that wait the battle clock is JINGLE_SKIP and the keys are held."""

    def fake(self, state=None, decoded=False):
        from dq4_pc import sound as SOUND
        snd = SOUND.Sound('inexistant.apk', '/tmp', log=lambda *a: None); snd.ok = True; snd.active = True
        if decoded: snd.dec['BGM47'] = dict(pcm=[0] * 3117, frequency=1000, loop=False)
        st = ENGINE.State(); st.part = ENGINE.PART_BATTLE
        self.ms = [1, state if state is not None else ENGINE.MSG_PAUSE, 0, 0, 100]
        eng = types.SimpleNamespace(state=st, msg_visible=True, message_state=lambda: tuple(self.ms), active_menu=lambda: None, flags=lambda: 0x28, ui=types.SimpleNamespace(msg={'feed': False}))
        j = types.SimpleNamespace(engine=eng, sound=snd, _deferred_jingle=[], reg={'battle_speed': 3.0, 'accel_speed': 1.0})
        for name_str in ('_sync_level_jingle', '_jingle_wait', '_battle_clock', '_wait_for_player'): setattr(j, name_str, types.MethodType(getattr(F.Game, name_str), j))
        j.pad = lambda: 0; j._held = lambda a: False; j.hud = types.SimpleNamespace(dpad_run=lambda: False); j.pause = types.SimpleNamespace(opened=False)
        return j

    def test_is_jingle(self):
        j = self.fake()
        self.assertTrue(j.sound.is_jingle(47)); self.assertTrue(j.sound.is_jingle(0x1005)); self.assertFalse(j.sound.is_jingle(30)); self.assertFalse(j.sound.is_jingle(0x4000))
        self.assertTrue(self.fake(decoded=True).sound.is_jingle(47))

    def test_jingle_kept_until_its_message(self):
        j = self.fake(); evs = [(35, 300), (37, 0x4000), (37, 47)]
        self.assertEqual(j._sync_level_jingle(j.engine, evs), [(35, 300)], 'the page beep goes at once, the music waits')
        self.assertEqual(j._deferred_jingle, [(37, 0x4000), (37, 47)]); self.assertTrue(j._jingle_wait())
        self.assertEqual(F.Game._speed_factor(j), F.JINGLE_SKIP, "the engine's wait before the message passes at once")
        self.assertEqual(j._sync_level_jingle(j.engine, []), []); self.assertEqual(len(j._deferred_jingle), 2)
        self.ms[1] = 1                                                                       # the message starts
        self.assertEqual(j._sync_level_jingle(j.engine, []), [(37, 0x4000), (37, 47)]); self.assertEqual(j._deferred_jingle, [])

    def test_nothing_kept_otherwise(self):
        j = self.fake(state=5); evs = [(37, 0x4000), (37, 47)]
        self.assertEqual(j._sync_level_jingle(j.engine, evs), evs, 'message deja affiche : rien a attendre')
        j = self.fake(); self.assertEqual(j._sync_level_jingle(j.engine, [(37, 30)]), [(37, 30)], 'a music track (not a jingle)')
        j = self.fake(); j.sound.mix.active['jingles'] = False; self.assertEqual(j._sync_level_jingle(j.engine, [(37, 47)]), [(37, 47)], 'jingles coupes')
        j = self.fake(); j.engine.state.part = ENGINE.PART_FIELD; self.assertEqual(j._sync_level_jingle(j.engine, [(37, 47)]), [(37, 47)], 'hors combat')


if __name__ == '__main__':
    unittest.main(verbosity=2)
