"""a battle waits for the end of a jingle (level up, BGM 47, 3.1 s) and of the victory fanfare (sound effect 409, 2.9 s) before its next message.

Spamming "next" at the end of a battle won with level ups brought the player back to the field with 2 or 3 level-up jingles still to play; and the victory fanfare must end before the
result messages; then the battle keeps its speed, only the message must not move on, by itself or by hand. Measured on the real engine (A pressed every other frame): the engine itself
waits 90 frames (3.0 s at x1) between a level-up jingle and its message, but the result message comes 0.37 s after the fanfare (the original does not wait for it). At x2 / x3 the 90 frames went by in
1 to 1.5 s and the jingles piled up behind each other ('s protection holds the music orders). Measured too: the message speed option set to "manual" (4) in the middle of an automatic wait holds the
message (BattleAutoFeed reads it at each frame): that is how `Engine.hold_messages` holds it.

1. Without APK: `Sound.jingle_playing` (music jingle, fanfare, held order, jingles turned off) and `_jingle_wait` (battle only).
2. Real engine (DQ_APK, DQ_SAVES): a battle won by a party one point from its next level, played at x3 with A every other frame, with the real `Sound` module (fake players, clock of the
   loop: 30 frames per second) and the window's rule (`_jingle_wait` -> `Engine.hold_messages`, no key on a message while a jingle plays; the battle stays at x3). Each level-up jingle is heard in full,
   at most the message on screen when it starts is shown during it, the first result message comes after the end of the fanfare, and nothing is left to play when the battle ends.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_jingle_wait.py        (about a minute)
"""
import os, struct, sys, tempfile, types, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.modules.setdefault('pyglet', None)                                   # (no pyglet: Sound gets fake players)
from dq4_pc import sound as SOUND
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class FakePlayer:
    def __init__(self): self.volume = 1.0; self.playing = False
    def queue(self, src): pass
    def play(self): self.playing = True
    def pause(self): self.playing = False
    def delete(self): self.playing = False


class FakeMedia:
    Player = FakePlayer


def data(seconds, looping):
    n = int(seconds * 1000)
    return dict(pcm=np.zeros((n, 1), np.int16), frequency=1000, start=n // 4 if looping else 0, end=n if looping else 0, volume=1.0, loop=looping)


def new_sound(clock):
    SOUND.time = types.SimpleNamespace(time=lambda: clock[0])
    s = SOUND.Sound('inexistant.apk', '/tmp', log=lambda *a: None)
    s.ok = True; s.ogg = True; s.media = FakeMedia; s.AudioFormat = lambda **kw: kw; s.AudioData = None
    SOUND.LoopSource = lambda *a: types.SimpleNamespace(pos=0)
    s.dec['BGM47'] = data(3.117, False); s.dec['SE0409'] = data(2.914, False); s.dec['BGM08'] = data(5.0, False)
    for i in (2, 5, 14, 30): s.dec['BGM%02d' % i] = data(60.0, True)
    return s


def jingle_wait(engine, sound):
    """The window's rule (BattleSceneMixin._jingle_wait calls Sound.battle_waits with "the engine is in its battle part")."""
    from dq4_pc.core import engine as ENGINE
    return SOUND.Sound.battle_waits(sound, engine.state.part == ENGINE.PART_BATTLE)


class WithoutApk(unittest.TestCase):
    def setUp(self): self.old = SOUND.time; self.h = [1000.0]; self.s = new_sound(self.h)
    def tearDown(self): SOUND.time = self.old

    def test_music_jingle(self):
        s = self.s; s.events([(37, 2)], engine_frame=0); self.assertFalse(s.jingle_playing(), 'musique en boucle : rien a attendre')
        s.events([(37, SOUND.BGM_STOP)], engine_frame=1); s.events([(37, 47)], engine_frame=2); self.assertTrue(s.jingle_playing())
        self.h[0] += 3.0; self.assertTrue(s.jingle_playing()); self.h[0] += 0.2; self.assertFalse(s.jingle_playing())

    def test_fanfare_and_held_order(self):
        s = self.s; s.events([(37, 30)], engine_frame=0); s.events([(35, 409)], engine_frame=10); self.assertTrue(s.jingle_playing())
        self.h[0] += 0.5; s.events([(37, 5)], engine_frame=10 + 60); self.assertEqual(len(s.bgm_queue), 1)          # (an order 2 s later at normal speed, arrived after 0.5 s)
        self.h[0] += 2.5; self.assertTrue(s.jingle_playing(), 'order held behind the fanfare'); s.tick(); self.assertFalse(s.jingle_playing())

    def test_jingles_off_or_sound_off(self):
        s = self.s; s.set_mix(active_flags={'jingles': False}); s.events([(37, 47)], engine_frame=0); self.assertFalse(s.jingle_playing())
        s.set_mix(active_flags={'jingles': True}); s.events([(35, 409)], engine_frame=1); self.assertTrue(s.jingle_playing())
        s.active = False; self.assertFalse(s.jingle_playing())

    def test_battle_only(self):
        from dq4_pc.core import engine as ENGINE
        s = self.s; s.events([(37, 47)], engine_frame=0)
        eng = types.SimpleNamespace(state=types.SimpleNamespace(part=ENGINE.PART_BATTLE))
        self.assertTrue(jingle_wait(eng, s)); eng.state.part = ENGINE.PART_FIELD; self.assertFalse(jingle_wait(eng, s))
        self.assertFalse(jingle_wait(types.SimpleNamespace(state=types.SimpleNamespace(part=ENGINE.PART_BATTLE)), None))


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    SPEED = 3

    @classmethod
    def setUpClass(cls):
        import unicorn; from dq4_pc.core import engine as ENGINE; from dq4_pc.persistence import savestates as SS; import _saves as SV
        cls.ENGINE, cls.SS = ENGINE, SS
        eng = cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_jingle_')); c = cls.c = eng.core
        SV.load_any(eng); SV.settle(eng)
        eng.impose_scroll_mode(0)                                                       # (the viewer's default: battle messages fed after 12 frames)
        enc = c.call(c.export('_ZN7Encount12getSingletonEv'), label='enc')
        def force(u, a, s, d):                                                          # a single weak monster (londuleux)
            for j in range(4):
                c.mem_w(enc + 0x34 + 4 * j, struct.pack('<I', 3 if j == 0 else 0)); c.mem_w(enc + 0x44 + 4 * j, struct.pack('<I', 1 if j == 0 else 0))
        a = c.export('_ZN10BattleRoot12setupMonsterEv'); c.uc.hook_add(unicorn.UC_HOOK_CODE, force, None, a, a); c.uc.ctl_flush_tb()
        orig = c.export('_ZN6status9PartyData15originalPlayer_E')
        for i in range(12):                                                              # every member one point from its next level: one jingle each
            hs = orig + 0x530 * i + 0x58; need = struct.unpack_from('<I', c.mem(hs, 0x30), 0x18)[0]
            if need > 0: c.mem_w(hs + 8, struct.pack('<I', need - 1))
        cls.initial = SS.snapshot(eng)

    def play(self, rule, speed=None):
        """Battle at x3, A every other loop frame on a message; `rule` = the window's rule applied (messages held and no key while a jingle plays). -> log, sound, clock."""
        ENGINE, eng, c = self.ENGINE, self.eng, self.c
        self.SS.apply(eng, self.initial)
        h = [1000.0]; old = SOUND.time; snd = new_sound(h)
        try:
            c.call(c.export('_ZN6Global11startBattleEv'), eng._global(), label='startBattle')
            n = 0
            while eng.state.part != ENGINE.PART_BATTLE and n < 1500: eng.step(0, 0); n += 1
            st = {'rel': None, 'k': 0}; log = []; frame = 0
            for frame in range(6000):
                h[0] += 1 / 30.0; wait = rule and jingle_wait(eng, snd); eng.hold_messages = wait
                skip = wait and eng.msg_visible and eng.message_state()[1] == self.ENGINE.MSG_PAUSE          # (the window's JINGLE_SKIP: the engine's wait before the jingle's message goes by at once; ~10 steps per frame here)
                for k in range(10 if skip else (speed or self.SPEED)):
                    p = d = 0
                    if k == 0:
                        if st['rel'] is not None: eng.send_menu(st['rel'], 1, -1, 0); st['rel'] = None
                        port = eng.active_menu()
                        if port is not None and not eng.msg_visible:
                            st['k'] += 1
                            if st['k'] % 4 == 0: eng.send_menu(port, 1, -1, 0x10); st['rel'] = port
                        elif eng.msg_visible and frame % 2 == 0 and not wait: p = d = ENGINE.A
                    eng.state.sounds = []; prev = eng.state.part; eng.step(p, d); eng.ui.damage = []
                    snd.events(eng.state.sounds, engine_frame=eng.frames)
                    for t, v in eng.state.sounds:
                        if t == 37 or (t == 35 and v == 409): log.append((h[0], 'order', (t, hex(v))))
                    for r in eng.sensor.drain(): log.append((h[0], 'msg', r['text']))
                    if eng.state.part != ENGINE.PART_BATTLE and prev == ENGINE.PART_BATTLE: log.append((h[0], 'end', None)); break
                snd.tick()
                if snd.bgm_id == 47 and snd.bgm_t0 is not None and snd.bgm_t0 != st.get('t47'): st['t47'] = snd.bgm_t0; log.append((snd.bgm_t0, 'bgm', 47))          # (a level-up jingle has just started)
                if snd.fanfare is not None and not any(l[1] == 'fanfare' for l in log): log.append((snd.fanfare[0], 'fanfare', snd.fanfare[1]))
                if log and log[-1][1] == 'end': break
            return log, snd, h
        finally: SOUND.time = old; eng.hold_messages = False

    def test_with_the_rule(self):
        log, snd, h = self.play(True)
        ends = [t for t, k, v in log if k == 'end']; self.assertTrue(ends, 'the battle does not end')
        jingles = [t for t, k, v in log if k == 'bgm']; self.assertGreaterEqual(len(jingles), 2, 'no level up')
        for a, b in zip(jingles, jingles[1:]): self.assertGreaterEqual(b - a, 3.1 - 2 / 30.0, 'a jingle cut by the next one')
        self.assertFalse(snd.jingle_playing(), 'a jingle is left to play at the end of the battle'); self.assertEqual(len(snd.bgm_queue), 0)
        fan = next(v for t, k, v in log if k == 'fanfare')
        first_result = next(t for t, k, v in log if k == 'msg' and "expérience" in v)
        self.assertGreaterEqual(first_result, fan - 1 / 30.0, 'the first result message comes before the end of the fanfare')
        msgs = [t for t, k, v in log if k == 'msg']
        for j in jingles: self.assertLessEqual(len([t for t in msgs if j + 1 / 30.0 < t < j + 3.1]), 1, 'messages scroll during a jingle')

    def test_level_message_comes_with_its_jingle(self):
        """level-up jingle + the "{name} reaches level X" message, then the dialogue is passed once the jingle is over. At x1 the engine waits 90 frames (the whole
        jingle) before that message; the wait now goes by at once: the message comes with the jingle, at x1 as at x3."""
        for speed in (1, 3):
            log, snd, h = self.play(True, speed)
            jingles = [t for t, k, v in log if k == 'bgm']; levels = [t for t, k, v in log if k == 'msg' and 'passe au niveau' in v]
            self.assertTrue(jingles and len(jingles) == len(levels), (speed, jingles, levels))
            for j, l in zip(jingles, levels): self.assertLess(l - j, 1.0, 'x%d: the level message comes %.2f s after its jingle' % (speed, l - j))

    def test_without_the_rule_the_jingles_pile_up(self):
        """(What happened before: kept as a measurement of the defect.)"""
        log, snd, h = self.play(False)
        self.assertTrue(snd.jingle_playing() or len(snd.bgm_queue) > 0, 'before: jingles were left to play at the end of the battle')


if __name__ == '__main__':
    unittest.main(verbosity=2)
