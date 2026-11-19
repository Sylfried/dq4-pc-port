"""Test of the sound mixing (categories, volumes, switches) without window or sound card: pyglet's players are replaced by fake players that keep their volume.

python3 tests/test_sound_mixing.py
"""
import os, sys, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.modules['pyglet'] = None                                             # (no pyglet: neither window nor audio driver; Sound takes it for "sound unavailable" and we give it fake players)
from dq456_pc import sound as SOUND


class FakePlayer:
    def __init__(self): self.volume = 1.0; self.playing = False; self.deleted = False
    def queue(self, src): pass
    def play(self): self.playing = True
    def pause(self): self.playing = False
    def delete(self): self.deleted = True; self.playing = False


class FakeSource:
    def __init__(self, *a): self.pos = 0


class FakeMedia:
    Player = FakePlayer
    Source = object


def data(seconds, looping, volume=1.0, frequency=1000):
    n = int(seconds * frequency)
    return dict(pcm=np.zeros((n, 1), np.int16), frequency=frequency, start=0 if not looping else n // 4, end=0 if not looping else n, volume=volume, loop=looping)


def new_sound():
    s = SOUND.Sound('inexistant.apk', '/tmp', log=lambda *a: None)
    s.ok = True; s.ogg = True; s.media = FakeMedia; s.AudioFormat = lambda **kw: kw; s.AudioData = None
    SOUND.LoopSource = FakeSource
    for i in (300, 316, 400, 500): s.dec['SE%04d' % i] = data(1.0, False, volume=0.5)
    s.dec['SE0500'] = data(2.0, True, volume=1.0)                      # looping sound effect
    s.dec['BGM02'] = data(60.0, True, volume=0.8)                       # music (loop)
    s.dec['BGM08'] = data(5.0, False, volume=1.0)                       # jingle (short, no loop)
    s.dec['BGM01'] = data(111.0, False, volume=1.0)                     # long track without loop: music
    return s


class Categories(unittest.TestCase):
    def test_sfx_category(self):
        for i in range(300, 305): self.assertEqual(SOUND.category_sfx(i), 'interface')
        for i in (299, 305, 316, 408, 501, 1129): self.assertEqual(SOUND.category_sfx(i), 'effects')
        self.assertEqual(SOUND.category_sfx(409), 'jingles', 'fanfare de victoire')

    def test_bgm(self):
        self.assertEqual(SOUND.category_bgm(False, True, 60.0), 'music')               # looping
        self.assertEqual(SOUND.category_bgm(False, False, 5.0), 'jingles')               # short without loop
        self.assertEqual(SOUND.category_bgm(True, False, 5.0), 'jingles')                # request with resume of the previous music
        self.assertEqual(SOUND.category_bgm(False, False, 111.0), 'music')             # long without loop
        self.assertEqual(SOUND.category_bgm(True, True, 5.0), 'music')                 # looping: we never go back to the previous music

    def test_game_option(self):
        self.assertEqual([round(SOUND.game_option_volume(i), 2) for i in range(5)], [0.2, 0.4, 0.6, 0.8, 1.0])
        self.assertEqual(SOUND.game_option_volume(9), 1.0); self.assertEqual(SOUND.game_option_volume(-3), 0.2)


class Gain(unittest.TestCase):
    def test_default(self):
        m = SOUND.Mixer()
        for c in SOUND.CATEGORIES: self.assertEqual(m.gain(c), 1.0)

    def test_product(self):
        m = SOUND.Mixer(general=0.5, music=0.8, jingles=0.6, effects=0.4, interface=0.2)
        self.assertAlmostEqual(m.gain('music'), 0.4); self.assertAlmostEqual(m.gain('jingles'), 0.3)
        self.assertAlmostEqual(m.gain('effects'), 0.2); self.assertAlmostEqual(m.gain('interface'), 0.1)
        self.assertAlmostEqual(m.gain('music', 0.5), 0.2)                                 # volume specific to the file
        m.game['music'] = 0.6; m.game['effects'] = 0.2                                      # the game's "volume" options: music + jingles / sound effects + interface
        self.assertAlmostEqual(m.gain('music'), 0.24); self.assertAlmostEqual(m.gain('jingles'), 0.18)
        self.assertAlmostEqual(m.gain('effects'), 0.04); self.assertAlmostEqual(m.gain('interface'), 0.02)

    def test_switch_and_bounds(self):
        m = SOUND.Mixer(); m.active['effects'] = False
        self.assertEqual(m.gain('effects'), 0.0); self.assertEqual(m.gain('interface'), 1.0)
        m.general = 3.0; self.assertEqual(m.gain('music'), 1.0)                          # never more than 1
        m.general = -1.0; self.assertEqual(m.gain('music'), 0.0)


class Reading(unittest.TestCase):
    def test_volumes_applied_immediately(self):
        s = new_sound()
        s.play_bgm(2); s.play_sfx(300); s.play_sfx(316)
        self.assertEqual(s.bgm_category, 'music'); self.assertAlmostEqual(s.bgm.volume, 0.8)
        v = {x.ident: x for x in s.sfx}
        self.assertEqual(v[300].category, 'interface'); self.assertEqual(v[316].category, 'effects')
        self.assertAlmostEqual(v[300].p.volume, 0.5); self.assertAlmostEqual(v[316].p.volume, 0.5)
        s.set_mix(general=0.5, volumes={'music': 0.5, 'effects': 0.2, 'interface': 1.0})
        self.assertAlmostEqual(s.bgm.volume, 0.5 * 0.5 * 0.8)                              # the current music changes
        self.assertAlmostEqual(v[316].p.volume, 0.5 * 0.2 * 0.5)                           # the current sound effects too
        self.assertAlmostEqual(v[300].p.volume, 0.5 * 1.0 * 0.5)

    def test_switches(self):
        s = new_sound()
        s.play_bgm(2); s.play_sfx(316)
        s.set_mix(active_flags={'music': False, 'effects': False})
        self.assertEqual(s.bgm.volume, 0.0); self.assertEqual(s.sfx[0].p.volume, 0.0)
        s.play_sfx(316); s.play_sfx(316)
        self.assertEqual(len(s.sfx), 1, 'a short sound effect is not played when its category is muted')
        s.play_sfx(300); self.assertEqual(len(s.sfx), 2, 'the interface sounds stay active')
        s.set_mix(active_flags={'music': True, 'effects': True})
        self.assertAlmostEqual(s.bgm.volume, 0.8); self.assertAlmostEqual(s.sfx[0].p.volume, 0.5)

    def test_just_launched_sfx_never_released_by_next_steps(self):
        """Accelerated walking: the engine makes several steps (hence several tick() calls) in a row in the same displayed frame, just after the door or village-exit sound effect order; a player that does not yet
        report itself as "playing" must not cause the sound effect to be lost. Past the grace period, a stopped player is released as before."""
        s = new_sound(); s.play_sfx(316); x = s.sfx[0]
        x.p.playing = False                                                  # (the player does not report itself yet)
        for _ in range(8): s.tick()                                          # eight steps in a row
        self.assertEqual(len(s.sfx), 1); self.assertFalse(x.p.deleted)
        x.begin -= SOUND.SFX_GRACE + 0.01; s.tick()                             # grace period over: player stopped = sound effect released
        self.assertEqual(s.sfx, []); self.assertTrue(x.p.deleted)

    def test_playing_sfx_kept_until_its_end(self):
        s = new_sound(); s.play_sfx(316); x = s.sfx[0]
        x.begin -= 10.0; s.tick(); self.assertEqual(len(s.sfx), 1)             # playing: kept
        x.end = 0.0; s.tick(); self.assertEqual(s.sfx, [])                    # duration exceeded: released

    def test_transition_sfx_played_in_full(self):
        """Door (309) then map transition (305, requested by the engine between the start of the fade and the loading: see test_transition_sfx): the map loading blocks the loop for up to 0.5 s and the engine
        makes several steps in a row (accelerated walking); both sound effects keep playing, at their volume, until the end of their original duration, then are released."""
        s = new_sound(); s.dec['SE0309'] = data(1.5, False, volume=0.4); s.dec['SE0305'] = data(1.0, False, volume=0.5)
        s.events([(35, 309)]); [s.tick() for _ in range(6)]
        s.events([(35, 305)]); [s.tick() for _ in range(6)]
        self.assertEqual([x.ident for x in s.sfx], [309, 305]); self.assertEqual([x.category for x in s.sfx], ['effects', 'effects'])
        self.assertEqual([round(x.p.volume, 3) for x in s.sfx], [0.4, 0.5])
        for x in s.sfx: x.begin -= 0.5; x.end -= 0.5                          # the map loading blocked the loop for 0.5 s
        s.tick()
        self.assertEqual([x.ident for x in s.sfx], [309, 305]); self.assertFalse(any(x.p.deleted for x in s.sfx))
        for x in s.sfx: x.begin -= 0.9; x.end -= 0.9                          # 1.4 s elapsed: 305 (1.0 s + 0.5 s margin) is still there, 309 (1.5 s) too
        s.tick(); self.assertEqual([x.ident for x in s.sfx], [309, 305])
        for x in s.sfx: x.end = 0.0                                           # duration exceeded: released
        s.tick(); self.assertEqual(s.sfx, [])

    def test_loop_cut_then_reopened(self):
        s = new_sound(); s.set_mix(active_flags={'effects': False})
        s.play_sfx(500)
        self.assertEqual(len(s.sfx), 1, 'a looping sound effect is started even when muted (zero volume)')
        self.assertEqual(s.sfx[0].p.volume, 0.0)
        s.set_mix(active_flags={'effects': True}); self.assertAlmostEqual(s.sfx[0].p.volume, 1.0)

    def test_jingle_and_resume(self):
        s = new_sound()
        s.play_bgm(2); music = s.bgm
        s.play_bgm(SOUND.BGM_RESTART + 8)
        self.assertEqual(s.bgm_category, 'jingles'); self.assertEqual(s.resume, 2)
        s.set_mix(volumes={'jingles': 0.25, 'music': 0.5}); self.assertAlmostEqual(s.bgm.volume, 0.25)
        s.set_mix(active_flags={'jingles': False}); self.assertEqual(s.bgm.volume, 0.0)
        self.assertIsNot(s.bgm, music)
        s.set_mix(active_flags={'jingles': True})
        s.play_bgm(1)                                                                       # long track without loop: music
        self.assertEqual(s.bgm_category, 'music'); self.assertAlmostEqual(s.bgm.volume, 0.5)

    def test_victory_fanfare_is_a_jingle(self):
        """SE 409 (victory): volume and switch of "Jingles and fanfares", but the game's "bruitages" option (not the music one)."""
        s = new_sound(); s.dec['SE0409'] = data(2.9, False, volume=0.6)
        s.set_mix(volumes={'jingles': 0.5, 'effects': 0.1}, game={'music': 1.0, 'effects': 0.4})
        s.play_sfx(409); x = s.sfx[-1]
        self.assertEqual(x.category, 'jingles'); self.assertAlmostEqual(x.p.volume, 0.5 * 0.6 * 0.4)
        s.set_mix(game={'music': 0.2, 'effects': 1.0}); self.assertAlmostEqual(x.p.volume, 0.5 * 0.6, msg='set at once, with the sound effects option')
        s.set_mix(active_flags={'jingles': False}); self.assertEqual(x.p.volume, 0.0)
        n = len(s.sfx); s.play_sfx(409); self.assertEqual(len(s.sfx), n, 'jingles muted: the fanfare is not played')
        s.set_mix(active_flags={'jingles': True, 'effects': False}); s.play_sfx(409); self.assertEqual(len(s.sfx), n + 1, 'sound effects muted: the fanfare plays')

    def test_listening_during_pause(self):
        s = new_sound(); s.play_bgm(2); s.play_sfx(316)
        players = [s.bgm] + [x.p for x in s.sfx]
        s.set_paused(True); self.assertTrue(all(not p.playing for p in players))
        s.listen(True); self.assertTrue(all(p.playing for p in players), 'Sound page: the sounds resume')
        s.set_mix(volumes={'music': 0.5}); self.assertAlmostEqual(s.bgm.volume, 0.4)
        s.listen(False); self.assertTrue(all(not p.playing for p in players), 'leaving the page: paused again')
        s.set_paused(False); self.assertTrue(all(p.playing for p in players))
        s.set_paused(True); s.listen(True); s.set_paused(False)
        self.assertFalse(s.listening); self.assertTrue(all(p.playing for p in players))

    def test_old_names(self):
        s = new_sound(); s.set_volumes(0.3, 0.6)
        self.assertAlmostEqual(s.vol_music, 0.3); self.assertAlmostEqual(s.vol_sfx, 0.6)
        self.assertAlmostEqual(s.mix.vol['music'], 0.3); self.assertAlmostEqual(s.mix.vol['effects'], 0.6)


def wait(s):
    """Lets the background decodings finish, then tick() (the decoding runs in a thread)."""
    for name_str, (fut, rap) in list(s.jobs.items()): fut.result()
    s.tick()


class Preload(unittest.TestCase):
    """SN: the music tracks that the engine requests then immediately stops in battle (BGM 23: party defeat; jingles) are decoded in advance and kept in memory."""

    def sound(self):
        s = new_sound(); s.decoded = []
        def decode(name_str): s.decoded.append(name_str); return data(113.0 if name_str == 'BGM23' else 4.0, name_str == 'BGM03')       # (BGM 3: the current music, with loop)
        s._decode = decode
        return s

    def test_nothing_before_the_first_music(self):
        s = self.sound(); s.preload_music((23, 47))
        for _ in range(3): wait(s)
        self.assertEqual(s.decoded, [], 'as long as no music plays, nothing is decoded in advance')
        s.play_bgm(3); wait(s)                                                 # the game's music goes first
        self.assertEqual(s.decoded[0], 'BGM03'); self.assertIsNotNone(s.bgm)

    def test_one_music_at_a_time_then_all_in_memory(self):
        s = self.sound(); s.play_bgm(3); wait(s); s.preload_music((47, 23, 9))
        wait(s); self.assertEqual(len(s.jobs), 1, 'one music track at a time')
        for _ in range(5): wait(s)
        self.assertEqual(s.decoded, ['BGM03', 'BGM47', 'BGM23', 'BGM09'], 'in the order requested')
        for name_str in ('BGM47', 'BGM23', 'BGM09'): self.assertIn(name_str, s.dec)

    def test_not_ahead_of_requested_decoding(self):
        s = self.sound(); s.play_bgm(3); wait(s); s.preload_music((23,))
        s.play_bgm(5)                                                              # decoding requested by the engine: the preload waits
        s.tick(); self.assertEqual(list(s.jobs), ['BGM05'], 'preloading does not go before a requested sound')
        for _ in range(4): wait(s)
        self.assertIn('BGM23', s.dec)

    def test_pinned_never_evicted(self):
        s = self.sound(); s.play_bgm(3); wait(s); s.preload_music((23,))
        for _ in range(3): wait(s)
        self.assertIn('BGM23', s.dec)
        for i in range(200): s.dec['SE%04d' % (1000 + i)] = data(0.1, False)
        s._purge()
        self.assertIn('BGM23', s.dec, 'a pinned music track stays')
        self.assertLessEqual(len([k for k in s.dec if k not in s.pinned]), 80, 'the rest follows the 80 sounds rule')

    def test_defeat_requested_then_stopped_is_played(self):
        """The engine requests BGM 23 (the whole party is defeated): the music starts right away, without waiting for a decoding that the engine's stop would cancel."""
        s = self.sound(); s.play_bgm(3); wait(s); s.preload_music((23,))
        for _ in range(3): wait(s)
        s.play_bgm(SOUND.BGM_STOP); self.assertIsNone(s.bgm)
        s.play_bgm(23); self.assertIsNotNone(s.bgm, 'played in the very frame of the order'); self.assertEqual(s.bgm_id, 23)
        self.assertEqual(s.jobs, {})

    def test_without_preloading_stop_cancels_decoding(self):
        """What the preload avoids: undecoded music, order then stop before the end of the decoding -> nothing plays."""
        s = self.sound(); s.play_bgm(23); s.play_bgm(SOUND.BGM_STOP); wait(s)
        self.assertIsNone(s.bgm)

    def test_disabled(self):
        s = self.sound(); s.ok = False; s.preload_music((23,)); self.assertEqual(s.background, [])


class ProtectionJingle(unittest.TestCase):
    """SN: an accelerated game (battle x2, x3) chains the engine's music orders faster: the fanfare was cut (level up, BGM 47 of 3.1 s: 1.75 s at x3). An order that would have arrived after the jingle
    at normal speed waits for the time at which it would have arrived (engine frame, 30 per second) or the end of the jingle; without an engine frame, nothing changes. Simulated clock; jingle = BGM 8 (5 s), music = BGM 2 (loop)."""

    def setUp(self):
        import types
        self.h = 1000.0; self.old = SOUND.time
        SOUND.time = types.SimpleNamespace(time=lambda: self.h)
        self.s = new_sound()

    def tearDown(self): SOUND.time = self.old

    def order(self, v, e, dt=0.0):
        self.h += dt; self.s.events([(37, v)], engine_frame=e); self.s.tick()

    def advance(self, dt): self.h += dt; self.s.tick()

    def launch_jingle(self, v=8, e=100, restart=False):
        s = self.s; self.order(2, 0); self.assertEqual(s.bgm_id, 2)
        self.order(v | (SOUND.BGM_RESTART if restart else 0), e); self.assertEqual(s.bgm_category, 'jingles'); self.t0 = self.h

    def test_normal_speed_nothing_changes(self):
        s = self.s; self.launch_jingle()
        self.order(SOUND.BGM_STOP, 160, dt=2.0)                                      # frame 160 = 2 s after frame 100: the time it is
        self.assertIsNone(s.bgm); self.assertEqual(len(s.bgm_queue), 0)

    def test_x3_stop_held_until_normal_time(self):
        s = self.s; self.launch_jingle()
        self.order(SOUND.BGM_STOP, 160, dt=0.7)                                      # at x3: the order of frame 160 arrives at 0.7 s instead of 2 s
        self.assertEqual(s.bgm_id, 8); self.assertIsNotNone(s.bgm); self.assertEqual(len(s.bgm_queue), 1)
        self.advance(1.2); self.assertIsNotNone(s.bgm, '1.9 s: not yet')
        self.advance(0.15); self.assertIsNone(s.bgm, '2,05 s : l\'ordre part a l\'heure normale'); self.assertEqual(len(s.bgm_queue), 0)

    def test_order_after_jingle_end_leaves_at_jingle_end(self):
        s = self.s; self.launch_jingle()
        self.order(SOUND.BGM_STOP, 400, dt=1.0); self.order(2, 430, dt=0.1)               # frames 400 and 430: 10 s and 11 s later (the jingle lasts 5 s)
        self.assertEqual(len(s.bgm_queue), 2)
        self.advance(3.8); self.assertEqual(len(s.bgm_queue), 2, '4.9 s: the jingle still plays')
        self.advance(0.2)
        self.assertEqual(len(s.bgm_queue), 0); self.assertEqual(s.bgm_id, 2, 'the orders go in order: stop then music 2'); self.assertEqual(s.bgm_category, 'music')

    def test_sfx_never_retained(self):
        s = self.s; self.launch_jingle()
        self.order(SOUND.BGM_STOP, 300, dt=0.5); s.events([(35, 316)], engine_frame=301)
        self.assertEqual([x.ident for x in s.sfx], [316])

    def test_without_engine_frame_or_jingle_or_cut_jingles(self):
        s = self.s; self.launch_jingle()
        s.events([(37, SOUND.BGM_STOP)]); self.assertIsNone(s.bgm, 'without an engine frame: at once')
        self.order(2, 0); self.order(5, 10, dt=0.1); self.assertEqual(len(s.bgm_queue), 0, 'a looping music track is not a jingle')
        s.set_mix(active_flags={'jingles': False}); self.order(8, 100); self.order(SOUND.BGM_STOP, 500, dt=0.1)
        self.assertIsNone(s.bgm, 'jingles coupes : rien a proteger')

    def test_jingle_with_resume_then_next_jingle(self):
        s = self.s; self.launch_jingle(restart=True); self.assertEqual(s.resume, 2)
        self.order(SOUND.BGM_RESTART + 8, 400, dt=1.0)                                  # 2nd fanfare, after the end of the 1st at normal speed
        self.assertEqual(len(s.bgm_queue), 1); self.assertEqual(s.bgm_id, 8)
        self.advance(4.1)
        self.assertEqual(len(s.bgm_queue), 0); self.assertEqual(s.bgm_id, 8); self.assertEqual(s.resume, 2, 'the previous music resumed, then the 2nd jingle kept it to resume (not the 1st jingle)')

    def test_pause_releases_nothing(self):
        s = self.s; self.launch_jingle()
        self.order(SOUND.BGM_STOP, 160, dt=0.5)
        s.set_paused(True); self.advance(100.0); self.assertEqual(len(s.bgm_queue), 1)
        s.set_paused(False); self.assertEqual(len(s.bgm_queue), 1, 'the pause shifts the deadlines')
        self.advance(1.0); self.assertEqual(len(s.bgm_queue), 1); self.advance(0.6); self.assertEqual(len(s.bgm_queue), 0)

    def test_loading_a_state_empties_the_queue(self):
        s = self.s; self.launch_jingle(); self.order(SOUND.BGM_STOP, 300, dt=0.2); self.assertEqual(len(s.bgm_queue), 1)
        s.restore_bgm({'id': 2, 'pos': 0.0, 'reprise': None}); self.assertEqual(len(s.bgm_queue), 0); self.assertEqual(s.bgm_id, 2)


class ProtectionFanfare(unittest.TestCase):
    """the victory fanfare is a sound effect (409, 2.9 s) and was not protected: at x3 the map music came 2.2 s over it (0.65 s at x1, measured on the real engine: orders at frames
    688 (409), 724 (stop) and 756 (music 5)). The orders that follow it now wait for the time at which they would have arrived at normal speed, as for a music jingle. Simulated clock."""

    def setUp(self):
        import types
        self.h = 1000.0; self.old = SOUND.time
        SOUND.time = types.SimpleNamespace(time=lambda: self.h)
        self.s = new_sound(); self.s.dec['SE0409'] = data(2.914, False, volume=0.6)
        self.s.events([(37, 2)], engine_frame=0); self.assertEqual(self.s.bgm_id, 2)               # battle music (here BGM 2)

    def tearDown(self): SOUND.time = self.old

    def advance(self, dt): self.h += dt; self.s.tick()

    def victory(self, speed):
        """The real engine's orders, arriving `speed` times faster: -> time (from the fanfare) at which the map music actually started."""
        s = self.s; s.events([(35, 409)], engine_frame=688); t0 = self.h
        self.advance(36 / 30 / speed); s.events([(37, SOUND.BGM_STOP)], engine_frame=724); s.tick()
        self.advance(32 / 30 / speed); s.events([(37, 5)], engine_frame=756); s.tick()
        for _ in range(400):
            if s.bgm_id == 5: return self.h - t0
            self.advance(0.01)
        self.fail('the map music never starts')

    def test_x1_unchanged(self):
        self.assertAlmostEqual(self.victory(1), 68 / 30, delta=0.02)                      # (2.27 s: the 0.65 s of overlap of the original)

    def test_x2_x3_like_x1(self):
        for speed in (2, 3):
            self.setUp(); t = self.victory(speed)
            self.assertAlmostEqual(t, 68 / 30, delta=0.02, msg='x%d' % speed); self.tearDown()

    def test_stop_order_held_too(self):
        s = self.s; s.events([(35, 409)], engine_frame=688)
        self.advance(0.4); s.events([(37, SOUND.BGM_STOP)], engine_frame=724); s.tick()
        self.assertEqual(s.bgm_id, 2, 'x3: the battle music stops at the normal time (1.2 s), not at 0.4 s'); self.assertEqual(len(s.bgm_queue), 1)
        self.advance(0.81); self.assertIsNone(s.bgm)

    def test_never_beyond_the_fanfare(self):
        s = self.s; s.events([(35, 409)], engine_frame=688)
        self.advance(0.2); s.events([(37, 5)], engine_frame=688 + 30 * 10); s.tick()                  # order 10 s later at normal speed: it waits for the end of the fanfare only
        self.advance(2.6); self.assertEqual(s.bgm_id, 2); self.advance(0.2); self.assertEqual(s.bgm_id, 5)

    def test_jingles_off_or_fanfare_stopped_holds_nothing(self):
        s = self.s; s.set_mix(active_flags={'jingles': False}); s.events([(35, 409)], engine_frame=688)
        self.advance(0.3); s.events([(37, 5)], engine_frame=756); self.assertEqual(s.bgm_id, 5, 'jingles coupes : rien a proteger')
        s.set_mix(active_flags={'jingles': True}); s.events([(35, 409)], engine_frame=800); s.events([(36, 409)], engine_frame=801)
        self.advance(0.1); s.events([(37, 2)], engine_frame=900); self.assertEqual(s.bgm_id, 2, 'fanfare stopped by the engine: nothing held any more')

    def test_pause_shifts_the_fanfare(self):
        s = self.s; s.events([(35, 409)], engine_frame=688)
        self.advance(0.3); s.events([(37, 5)], engine_frame=756); self.assertEqual(len(s.bgm_queue), 1)
        s.set_paused(True); self.advance(50.0); s.set_paused(False); self.assertEqual(len(s.bgm_queue), 1, 'the pause shifts the fanfare')
        self.advance(1.8); self.assertEqual(s.bgm_id, 2); self.advance(0.2); self.assertEqual(s.bgm_id, 5)

    def test_menu_click_never_protects(self):
        s = self.s; s.play_sfx(409)                                                       # (no engine frame: not an engine order)
        s.events([(37, 5)], engine_frame=10); self.assertEqual(s.bgm_id, 5)


class Loops(unittest.TestCase):
    """a looping sound effect has no time limit, as in the original (until the engine's stop); loading a savestate stops it."""

    def test_no_time_limit_then_stop_order(self):
        import types
        h = [1000.0]; old = SOUND.time; SOUND.time = types.SimpleNamespace(time=lambda: h[0])
        try:
            s = new_sound(); s.events([(35, 500)]); h[0] += 3600.0; s.tick()
            self.assertEqual([x.ident for x in s.sfx], [500], 'an hour later: still there'); self.assertTrue(s.sfx[0].looping)
            s.events([(36, 500)]); self.assertEqual(s.sfx, [])
        finally: SOUND.time = old

    def test_loading_a_state_stops_loops_only(self):
        s = new_sound(); s.play_sfx(500); s.play_sfx(300)
        s.restore_bgm(None, 2); self.assertEqual([x.ident for x in s.sfx], [300]); self.assertEqual(s.bgm_id, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
