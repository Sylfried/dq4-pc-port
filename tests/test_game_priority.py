"""Test of the game's priority over the player's settings: "when the game itself sets a value by script, it takes precedence over the player's setting".

  1. pure rules (game_priority.py): effective_value, effective_factor, letters_per_frame, fade_duration;
  2. walking speed (`Game._speed_factor`, on a fake object): no effect during an event (player lock, including the exit fade), applied on the free field and during the arrival fade;
  3. original engine (if --apk and --saves are given): text speed set by the game (the message's speed word is modified along the way); fade started by a game script command
     (save --slot-fade, default 2: start of the prologue, fade_out command of 30 frames) not shortened, engine fade shortened.

    python3 tests/test_game_priority.py [--apk "<folder of the patched APKs>" --saves "<folder of the saves>" [--slot 4] [--slot-fade 2]]
The saves are only opened read-only: the engine writes to a temporary folder.
"""
import argparse, os, sys, tempfile, types, unittest


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq4_pc)
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.core import game_priority as PJ
from dq4_pc.core import engine as ENGINE
from dq4_pc.window import game as F

ARGS = None


class PureRules(unittest.TestCase):
    def test_effective_value(self):
        for player, game in ((4.0, None), (16.0, None), (0.5, 8), (4000.0, 0), (0, 0.0), (None, 3)):
            self.assertEqual(PJ.effective_value(player, game), player if game is None else game, (player, game))
        self.assertEqual(PJ.effective_value(16.0), 16.0)
        self.assertEqual(PJ.effective_value(16.0, 0), 0, 'a game value equal to zero is a game value')

    def test_effective_factor(self):
        self.assertEqual(PJ.effective_factor(2.0, False), 2.0)
        self.assertEqual(PJ.effective_factor(2.0, True), 1.0)
        self.assertEqual(PJ.effective_factor(0.5, True), 1.0)
        self.assertEqual(PJ.effective_factor(3.0, True, neutral=1.5), 1.5)

    def test_letters_per_frame(self):
        for player in (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 4000.0):
            self.assertEqual(PJ.letters_per_frame(player, PJ.STANDARD_LETTERS), player, "ordinary dialogue: the player's setting")
            self.assertEqual(PJ.letters_per_frame(player, 400), 400, "battle window (speed 100): the game's")
            self.assertEqual(PJ.letters_per_frame(player, 8), 8, "speed set by the game (word 2): the game's, whatever the setting")
            self.assertEqual(PJ.letters_per_frame(player, 2), 2, 'speed set by the game (word 0.5): slower than the standard, it wins too')
        self.assertEqual(PJ.letters_per_frame(16.0, 8, standard=8), 16.0, 'another standard (another game): the setting applies to that one')

    def test_fade_duration(self):
        for duration, factor, expected in ((30, 1.0, 30), (30, 2.0, 15), (45, 2.0, 22), (60, 4.0, 15), (1, 4.0, 1), (0, 4.0, 0), (3, 4.0, 1), (30, 0.5, 30)):
            self.assertEqual(PJ.fade_duration(duration, factor), expected, (duration, factor))
            self.assertEqual(PJ.fade_duration(duration, factor, script=True), duration, 'script fade: duration of the script')
        self.assertEqual(PJ.fade_duration(30, 2.0, script=False), 15)

    def test_mark_outside_packet_fields(self):
        """The script fade mark overlaps no field of packet 9's integer (duration 0x7ff, color 0x800, exit 0x1000, white 0x2000, background plane 0x4000)."""
        self.assertEqual(PJ.SCRIPT_FADE_MARK & 0x7fff, 0)
        e = ENGINE.State(); ENGINE.State.fade_speed = 2.0
        try:
            e._fade(0x1000 | 30, ()); self.assertEqual(e.fade['n'], 15, 'engine fade shortened')
            e._fade(0x1000 | 30 | PJ.SCRIPT_FADE_MARK, ()); self.assertEqual(e.fade['n'], 30, 'fondu de script : intact')
            e._fade(0x5000 | 30 | PJ.SCRIPT_FADE_MARK, ()); self.assertEqual(e.background_fade['n'], 30); self.assertEqual(e.background_fade['end'], 1.0, 'the other fields are read as before')
            e._fade(0x1000 | 0x800 | 30, (0.1, 0.2, 0.3)); self.assertEqual(e.fade['n'], 30, 'fondu en couleur : jamais raccourci'); self.assertEqual(e.fade['col'], (0.1, 0.2, 0.3))
        finally: ENGINE.State.fade_speed = 1.0


def fake_game_walk(accel=1.5, flags=0x28, msg=False, part=ENGINE.PART_TOWN, direction=ENGINE.RIGHT, accel_held=False, transition_guard=0):
    eng = types.SimpleNamespace(state=types.SimpleNamespace(part=part, effect=None, load_wait=None, transition_guard=transition_guard, battle_transition=lambda: False), msg_visible=msg, active_menu=lambda: None, flags=lambda: flags)
    return types.SimpleNamespace(reg={'accel_speed': accel}, engine=eng, pad=lambda: direction, _held=lambda a: accel_held and a == 'accel', hud=types.SimpleNamespace(dpad_run=lambda: False), pause=types.SimpleNamespace(opened=False), _battle_clock=lambda: False)           # (outside battle: the "battle speed" branch of Game._speed_factor does not apply)


class WalkSpeed(unittest.TestCase):
    def factor(self, **kw): return F.Game._speed_factor(fake_game_walk(**kw))

    def test_free_field(self):
        self.assertEqual(self.factor(), 1.0, 'accelerateur non tenu')
        self.assertEqual(self.factor(accel_held=True), 1.5, 'accelerateur tenu : x1,5')
        self.assertEqual(self.factor(flags=0x28 | 0x40, accel_held=True), 1.5, 'interface lock only (bit 0x40): no effect here')

    def test_game_has_control(self):
        self.assertEqual(self.factor(flags=0x28 | 0x4), 1.0, 'player lock (event, scene) without a message: walking not accelerated')
        self.assertEqual(self.factor(flags=0x3c, accel_held=True), 1.0)
        self.assertEqual(self.factor(flags=0x28 | 0x5), 1.0, 'fondu de sortie (joueur verrouille) : non acceleree')
        self.assertEqual(self.factor(flags=0x3d), 1.0)

    def test_arrival_fade_player_free(self):
        """the arrival fade on a map (flag 1 alone, the hero is already walking) no longer prevents accelerated walking (measured: flags 0x39 during the 30 frames, 0x3d + lock during the exit fade)."""
        self.assertEqual(self.factor(flags=0x39), 1.0)
        self.assertEqual(self.factor(flags=0x39, accel_held=True), 1.5, 'accelerator held from the first frame after the door')

    def test_return_from_battle_player_free(self):
        """on return from a battle the return fade lasts 30 frames but the player is free from frame 12 (measured on the real engine: flags 0x2d until frame 11, then 0x29, the hero walks from frame 13):
        accelerated walking and the accelerator (run) take effect as soon as the lock drops, not at the end of the fade."""
        self.assertEqual(self.factor(flags=0x29), 1.0)
        self.assertEqual(self.factor(flags=0x29, accel_held=True), 1.5, 'running held from the end of the lock, return fade still in progress')
        self.assertEqual(self.factor(flags=0x2d, accel_held=True), 1.0, 'player locked (frames 1 to 11 of the return): game clock')

    def test_between_two_battle_fades(self):
        """The engine changes scene 1 to 3 frames after the exit to black (State.transition_guard): game clock, even if the lock is not yet set (frame 0 of the return: flags 0x1)."""
        self.assertEqual(self.factor(flags=0x1, transition_guard=5, accel_held=True), 1.0)
        self.assertEqual(self.factor(flags=0x29, transition_guard=0, accel_held=True), 1.5)

    def test_unchanged(self):
        self.assertEqual(self.factor(msg=True), 1.0)
        self.assertEqual(self.factor(part=ENGINE.PART_BATTLE), 1.0)
        self.assertEqual(self.factor(direction=0), 1.0, 'no direction held')
        self.assertEqual(self.factor(accel=1.0, accel_held=True), 1.0)


def text_word_frames(speed, game_word, slot):
    """Like test_text_scrolling.text_frames, but the speed word of the message window is written to `game_word` (a game script that sets the speed) as soon as the message opens; None = untouched.
    Returns (frames between the opening of the message and the end of its first page, letters of the page)."""
    eng = ENGINE.Engine(ARGS.apk, ARGS.saves, tempfile.mkdtemp(prefix='sv_test_prio_'))
    for _ in range(3): eng.step(0, 0)
    eng.load_save(slot); eng.text_speed = speed
    for _ in range(70): eng.step(0, 0)
    eng.step(0, 0x800)
    t_open = None; ok = 0
    for i in range(1500):
        p = eng.active_menu()
        if eng.msg_visible: pass
        elif p is not None and i % 14 == 4 and ok < 4: eng.send_menu(p, 1, -1, 0x10); ok += 1
        elif p is not None and i % 14 == 5: eng.send_menu(p, 1, -1, 0)
        if game_word is not None and t_open is not None: eng.core.mem_w(eng.L + ENGINE.MSG_SPEED, int(game_word).to_bytes(2, 'little'))
        eng.step(0, 0)
        active, state, _, end, word = eng.message_state()
        if active == 1 and t_open is None:
            t_open = eng.frames
            if game_word is not None: eng.core.mem_w(eng.L + ENGINE.MSG_SPEED, int(game_word).to_bytes(2, 'little'))
        if t_open is not None and state in (3, 5): return eng.frames - t_open, end
    return None, None


def prologue_fades(factor, slot, n=450):
    """[(frame, original duration, applied duration, script fade?)] of the engine's fades to black since the loading of save `slot`."""
    eng = ENGINE.Engine(ARGS.apk, ARGS.saves, tempfile.mkdtemp(prefix='sv_test_prio_'))
    for _ in range(3): eng.step(0, 0)
    res = []; orig = ENGINE.State._fade
    def spy(self, v, f):
        r = orig(self, v, f)
        if not v & (0x800 | 0x2000): res.append((eng.frames, v & 0x7ff, (self.background_fade if v & 0x4000 else self.fade)['n'] if (v & 0x7ff) > 1 else 0, bool(v & PJ.SCRIPT_FADE_MARK)))
        return r
    ENGINE.State._fade = spy; ENGINE.State.fade_speed = factor
    try:
        eng.load_save(slot)
        for i in range(n): eng.step(0, 0x10 if i % 40 == 0 else 0)
    finally: ENGINE.State._fade = orig; ENGINE.State.fade_speed = 1.0
    return res


@unittest.skipIf(ARGS is None and '--apk' not in sys.argv, 'original engine: --apk and --saves required')
class Engine(unittest.TestCase):
    def test_text_fixed_by_the_game(self):
        """Speed word set by the game (2 = 8 letters per frame): same duration whatever the player's setting; without it, the setting applies."""
        without = {v: text_word_frames(v, None, ARGS.slot)[0] for v in (0.5, 16.0)}
        has_tab = {v: text_word_frames(v, 2, ARGS.slot) for v in (0.5, 4.0, 16.0, 4000.0)}
        print('setting only: %s; word set to 2 by the game: %s' % (without, has_tab))
        self.assertGreater(without[0.5], 3 * without[16.0], 'without a game value, the setting changes the duration')
        self.assertEqual(len({n for n, _ in has_tab.values()}), 1, "the game set its speed: the player's setting changes nothing")
        equivalent = text_word_frames(8.0, None, ARGS.slot)                  # player setting = 8 letters per frame, nothing fixed by the game: the same duration as the game's word 2
        self.assertEqual(has_tab[4.0], equivalent, "the game's speed (word 2 = 8 letters per frame) is the one that applies: %s versus %s" % (has_tab[4.0], equivalent))

    def test_script_fade(self):
        raw_value = prologue_fades(1.0, ARGS.slot_fade); fast = prologue_fades(4.0, ARGS.slot_fade)
        print('fondus x1 : %s\nfondus x4 : %s' % (raw_value, fast))
        self.assertTrue(any(s for _, _, _, s in raw_value), 'a fade started by a game script is recognized (fade_out at the start of the prologue)')
        self.assertTrue(any(not s and d > 4 for _, d, _, s in raw_value), 'and engine fades too')
        for (_, d, ap, s), (_, d4, ap4, s4) in zip(raw_value, fast):
            self.assertEqual((d, s), (d4, s4))
            self.assertEqual(ap, d if d > 1 else 0, 'x1 : duree d\'origine')
            if s: self.assertEqual(ap4, ap, 'fondu de script : jamais raccourci')
            elif d > 1: self.assertEqual(ap4, max(1, round(d / 4.0)), 'engine fade: divided by 4')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apk'); ap.add_argument('--saves'); ap.add_argument('--slot', type=int, default=4); ap.add_argument('--slot-fade', type=int, default=2, dest='slot_fade')
    ARGS, remainder = ap.parse_known_args()
    if not (ARGS.apk and ARGS.saves): ARGS = None
    unittest.main(argv=[sys.argv[0]] + remainder, verbosity=2)
