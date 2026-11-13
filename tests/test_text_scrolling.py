"""Objective tests (without a window) of the text speed and of the scrolling of battle messages.

The original engine runs under Unicorn; we count ENGINE FRAMES (30 per second), not time:
  - text: frames between the opening of a dialogue message (ui_MsgLoop active) and the end of writing its first page (state 3 or 5: waiting for a key);
  - scrolling: frames during which a battle message waits before moving on to the next one by itself (ui_MsgLoop state 5 without a command menu), according to OptionStatus.battleSpeed.

Usage (from the repository root):
    python3 tests/test_text_scrolling.py --apk "<patched APK folder>" --saves "<saves folder>" [--slot 4]      (or DQ_APK / DQ_SAVES)
Saves are opened read-only: the engine writes to a temporary folder.
"""
import argparse, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import engine as ENGINE

ARGS = None
SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 4000.0)


def start_engine(slot):
    eng = ENGINE.Engine(ARGS.apk, ARGS.saves, tempfile.mkdtemp(prefix='sv_test_texte_'))
    for _ in range(3): eng.step(0, 0)
    eng.load_save(slot)
    return eng


def text_frames(speed, slot):
    """(frames between the opening of the message and the end of its first page, letters of the page)."""
    eng = start_engine(slot); eng.text_speed = speed
    for _ in range(70): eng.step(0, 0)
    eng.step(0, 0x800)                                               # command menu -> "Parler": the scene message opens
    t_open = None; ok = 0
    for i in range(1500):
        p = eng.active_menu()
        if eng.msg_visible: pass
        elif p is not None and i % 14 == 4 and ok < 4: eng.send_menu(p, 1, -1, 0x10); ok += 1
        elif p is not None and i % 14 == 5: eng.send_menu(p, 1, -1, 0)
        eng.step(0, 0)
        active, state, _, end, _ = eng.message_state()
        if active == 1 and t_open is None: t_open = eng.frames
        if t_open is not None and state in (3, 5): return eng.frames - t_open, end
    return None, None


def enter_battle(eng):
    for i in range(100): eng.step(0, 0x10 if i % 10 == 0 else 0)
    if eng.state.part != ENGINE.PART_FIELD:
        eng.start_field()
        for i in range(120): eng.step(0, 0)
    c = eng.core
    c.call(eng.E('_ZN7Encount12forceEncountEv'), c.call(eng.E('_ZN7Encount12getSingletonEv'), label='enc'), label='force')
    for i in range(600):
        eng.step([0x4, 0x8][(i // 20) % 2], 0)
        if eng.state.part == ENGINE.PART_BATTLE: return True
    return False


def battle_waits(code, slot, n=900):
    """Waits (in frames) of battle messages that move on by themselves, forced scrolling = code. Returns (list of waits, game option at the end)."""
    eng = start_engine(slot); eng.impose_scroll_mode(code)
    assert enter_battle(eng), 'no battle'
    t5 = None; menu_seen = False; res = []
    for i in range(n):
        p = eng.active_menu()
        if p is not None and i % 15 == 0: eng.send_menu(p, 1, -1, 0x10)
        elif p is not None and i % 15 == 1: eng.send_menu(p, 1, -1, 0)
        eng.step(0, 0)
        state = eng.message_state()[1]
        if p is not None: menu_seen = True
        if state == 5 and t5 is None: t5 = eng.frames; menu_seen = p is not None
        elif state != 5 and t5 is not None:
            if not menu_seen: res.append(eng.frames - t5)
            t5 = None
        if eng.state.part != ENGINE.PART_BATTLE and i > 100: break
    return res, eng.game_options()[2]


def manual_waits_for_key(slot):
    """Manual scrolling: a battle message stays displayed as long as no key is pressed (150 frames without a key), then moves on at the A key."""
    eng = start_engine(slot); eng.impose_scroll_mode(ENGINE.BATTLE_MANUAL)
    assert enter_battle(eng), 'no battle'
    t5 = None
    for i in range(900):
        p = eng.active_menu()
        if p is not None and i % 15 == 0: eng.send_menu(p, 1, -1, 0x10)
        elif p is not None and i % 15 == 1: eng.send_menu(p, 1, -1, 0)
        eng.step(0, 0)
        if eng.message_state()[1] == 5 and p is None and eng.active_menu() is None:
            t5 = t5 or eng.frames
            if eng.frames - t5 >= 150: break
        else: t5 = None
    else: return None
    for _ in range(150): eng.step(0, 0)                                  # (the message must still not move: the loop above had already waited 150 frames)
    remainder = eng.message_state()[1] == 5
    eng.step(0, 0x10)
    for _ in range(40): eng.step(0, 0)
    return remainder, eng.message_state()[1] != 5 or eng.active_menu() is not None


def dialogue_outside_battle(code, slot):
    """A dialogue message (outside battle) waits for the key for 400 frames even with the save's automatic scrolling: returns True if it did not move on by itself."""
    eng = start_engine(slot); eng.impose_scroll_mode(code)
    for _ in range(70): eng.step(0, 0)
    eng.step(0, 0x800); ok = 0; t5 = None
    for i in range(1500):
        p = eng.active_menu()
        if eng.msg_visible: pass
        elif p is not None and i % 14 == 4 and ok < 4: eng.send_menu(p, 1, -1, 0x10); ok += 1
        elif p is not None and i % 14 == 5: eng.send_menu(p, 1, -1, 0)
        eng.step(0, 0)
        state = eng.message_state()[1]
        if state == 5 and t5 is None: t5 = eng.frames
        if t5 is not None:
            if state != 5: return False
            if eng.frames - t5 >= 400: return True
    return None


class TextAndScroll(unittest.TestCase):
    def test_text_speed(self):
        measures = {v: text_frames(v, ARGS.slot) for v in SPEEDS}
        for v, (n, letters) in measures.items(): print('vitesse %6.1f lettres/image : %4s images (%s lettres)' % (v, n, letters))
        frames = [measures[v][0] for v in SPEEDS]
        self.assertTrue(all(n is not None for n in frames))
        self.assertEqual(frames, sorted(frames, reverse=True), 'the higher the speed, the fewer frames are needed')
        self.assertGreater(frames[0], 4 * frames[3], 'x1/8 of the game speed: at least 4 times longer')
        self.assertLessEqual(frames[-1], frames[3] // 2, 'instant: at most half the game time')
        letters = measures[4.0][1]
        for v in (0.5, 1.0, 2.0):                                         # slow writing: the time is in the letters, to within one frame
            self.assertAlmostEqual(measures[v][0], letters / v, delta=letters / v * 0.08 + 6)

    def test_battle_scrolling(self):
        expected = {0: 12, 1: 22, 2: 32, 3: 42}                            # BattleAutoFeed::setMessageSpeed: wait in frames according to OptionStatus.battleSpeed
        for code, n in expected.items():
            res, option = battle_waits(code, ARGS.slot)
            print('defilement %d : attentes %s' % (code, res))
            self.assertEqual(option, code)
            self.assertGreaterEqual(len(res), 3)
            self.assertEqual(min(res), n)
        res, option = battle_waits(ENGINE.BATTLE_MANUAL, ARGS.slot)
        print('defilement manuel : attentes %s' % (res,))
        self.assertEqual(res, [], 'by hand: no message passes by itself')

    def test_manual_waits_for_key(self):
        r = manual_waits_for_key(ARGS.slot)
        print('manual: message still there after 300 frames without a key = %s, passed with the A key = %s' % r if r else 'manual: no measurable message')
        self.assertIsNotNone(r)
        self.assertTrue(r[0] and r[1])

    def test_dialogue_outside_battle_never_automatic(self):
        for code in (0, 2):
            self.assertTrue(dialogue_outside_battle(code, ARGS.slot), 'scrolling %d: the dialogue must not pass by itself' % code)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apk', default=os.environ.get('DQ_APK')); ap.add_argument('--saves', default=os.environ.get('DQ_SAVES')); ap.add_argument('--slot', type=int, default=4)      # (DQ_APK / DQ_SAVES like the other tests)
    ARGS, remainder = ap.parse_known_args()
    if not (ARGS.apk and ARGS.saves): ap.error('--apk and --saves (or DQ_APK and DQ_SAVES) are required')
    unittest.main(argv=[sys.argv[0]] + remainder, verbosity=2)
