"""two edge cases of the music, as in the original game (Sound.StopBGM / PlayBGM of SoundControl).
- A music stop DURING a jingle started with resume (0x1000 | n) does not reset the jingle state in Unity: the previous music restarts (from the start). Without a jingle in progress, the stop stops.
- A track without loop that reaches its end is no longer "in progress": requesting it again restarts it. A track that is playing (looping or not) and is requested again is not restarted (the engine does not request it again).
Without window or sound card (fake players).
    python3 tests/test_sound_music_limits.py"""
import os, sys, time, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.modules['pyglet'] = None                                             # no pyglet: Sound takes it for "sound unavailable", the test gives it fake players
from dq456_pc import sound as SOUND


class FakePlayer:
    def __init__(self): self.playing = False; self.volume = 1.0
    def queue(self, src): pass
    def play(self): self.playing = True
    def pause(self): self.playing = False
    def delete(self): self.playing = False


class FakeMedia:
    Player = FakePlayer


class FakeSource:
    def __init__(self, *a): self.pos = 0


def data(seconds, looping):
    n = int(seconds * 1000)
    return dict(pcm=np.zeros((n, 1), np.int16), frequency=1000, start=n // 4 if looping else 0, end=n if looping else 0, volume=1.0, loop=looping)


def new_sound():
    s = SOUND.Sound('inexistant.apk', '/tmp', log=lambda *a: None, logfile=lambda *a: None, alert=lambda *a: None)
    s.ok = True; s.ogg = True; s.media = FakeMedia; s.AudioFormat = lambda **kw: kw; s.AudioData = None
    SOUND.LoopSource = FakeSource
    s.dec['BGM02'] = data(60.0, True)                    # looping music
    s.dec['BGM01'] = data(5.0, False)                    # music without loop (like BGM 1 and 34)
    s.dec['BGM48'] = data(3.0, False)                    # jingle (chest)
    return s


RESTART = SOUND.BGM_RESTART; STOP = SOUND.BGM_STOP


class StopDuringJingle(unittest.TestCase):
    def test_stop_during_jingle_with_resume_previous_music_restarts(self):
        s = new_sound(); s.play_bgm(2); s.play_bgm(RESTART | 48)
        self.assertEqual(s.bgm_id, 48); self.assertEqual(s.resume, 2)
        p = s.bgm; s.play_bgm(STOP | 4)
        self.assertEqual(s.bgm_id, 2); self.assertIsNotNone(s.bgm); self.assertIsNot(s.bgm, p); self.assertIsNone(s.resume); self.assertIsNone(s.bgm_end)      # (the previous music, looping, from the start)

    def test_stop_without_jingle_stops(self):
        s = new_sound(); s.play_bgm(2); s.play_bgm(STOP | 4)
        self.assertIsNone(s.bgm_id); self.assertIsNone(s.bgm); self.assertIsNone(s.resume)

    def test_stop_after_jingle_end_stops_resumed_music(self):
        s = new_sound(); s.play_bgm(2); s.play_bgm(RESTART | 48)
        s.bgm_end = time.time() - 1.0; s.tick()                                    # end of the jingle: the previous music resumes on its own
        self.assertEqual(s.bgm_id, 2); self.assertIsNone(s.resume)
        s.play_bgm(STOP | 4); self.assertIsNone(s.bgm_id); self.assertIsNone(s.bgm)

    def test_jingle_without_prior_music_then_stop_stays_mute(self):
        s = new_sound(); s.play_bgm(RESTART | 48); self.assertIsNone(s.resume)
        s.play_bgm(STOP | 4); self.assertIsNone(s.bgm_id); self.assertIsNone(s.bgm)

    def test_two_stops_in_a_row(self):
        s = new_sound(); s.play_bgm(2); s.play_bgm(RESTART | 48); s.play_bgm(STOP | 4); s.play_bgm(STOP | 4)          # (the first restarts the music, the second stops it)
        self.assertIsNone(s.bgm_id); self.assertIsNone(s.bgm)

    def test_a_new_order_after_the_stop(self):
        s = new_sound(); s.play_bgm(2); s.play_bgm(RESTART | 48); s.play_bgm(STOP | 4); s.play_bgm(1)
        self.assertEqual(s.bgm_id, 1); self.assertIsNone(s.resume)


class SameMusicRequestedAgain(unittest.TestCase):
    def test_playing_loop_is_not_restarted(self):
        s = new_sound(); s.play_bgm(2); p = s.bgm; s.play_bgm(2); self.assertIs(s.bgm, p)

    def test_without_loop_a_running_music_is_not_restarted(self):
        s = new_sound(); s.play_bgm(1); p = s.bgm; s.play_bgm(1); self.assertIs(s.bgm, p)

    def test_without_loop_a_finished_music_is_restarted(self):
        s = new_sound(); s.play_bgm(1); p = s.bgm; s.bgm_end = time.time() - 1.0
        s.play_bgm(1); self.assertIsNot(s.bgm, p); self.assertEqual(s.bgm_id, 1); self.assertGreater(s.bgm_end, time.time() + 3.0)

    def test_paused_track_is_not_finished(self):
        s = new_sound(); s.play_bgm(1); p = s.bgm; s.bgm_end = time.time() - 1.0; s.t_pause = time.time()
        s.play_bgm(1); self.assertIs(s.bgm, p)

    def test_another_music_always_replaces(self):
        s = new_sound(); s.play_bgm(2); p = s.bgm; s.play_bgm(1); self.assertEqual(s.bgm_id, 1); self.assertIsNot(s.bgm, p)


if __name__ == '__main__':
    unittest.main(verbosity=1)
