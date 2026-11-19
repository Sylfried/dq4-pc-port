"""Dragon Quest V / VI music orders (sound.MUSIC_V2): Sound.PlayBGM of their Unity layer reads the track in value & 0xff (the fade bits 8-11 do not change the track),
bit 13 plays a track over the current one, which is paused and resumes where it stopped when asked again (or at the end of a layer track with bit 12); a stop drops it;
a stop with bit 12 (0x5000 | n) only sets the level of the current track (n / 127).
Without window or sound card (fake players).
    python3 tests/test_sound_music_v2.py"""
import os, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_sound_failures as TF          # (fake players, decoded tracks; this module also hides pyglet)
SOUND = TF.SOUND


class MusicV2(unittest.TestCase):
    def setUp(self):
        self.old = SOUND.MUSIC_V2; SOUND.MUSIC_V2 = True
        self.s, _, _ = TF.new_sound()
        self.s.dec['BGM23'] = TF.data(60.0, True); self.s.dec['BGM06'] = TF.data(2.0, False)

    def tearDown(self): SOUND.MUSIC_V2 = self.old

    def test_fade_bits_keep_the_track(self):
        self.s.play_bgm(0x317)                                          # the start menu's order: BGM 23 after a 0.3 s fade
        self.assertEqual(self.s.bgm_id, 23); self.assertTrue(self.s.bgm.playing)

    def test_layer_pauses_then_resumes_the_same_player(self):
        s = self.s; s.play_bgm(2); first = s.bgm
        s.play_bgm(0x2005)
        self.assertEqual(s.bgm_id, 5); self.assertFalse(first.playing); self.assertIs(s.bgm_layer['p'], first)
        s.play_bgm(2)
        self.assertIs(s.bgm, first); self.assertTrue(first.playing); self.assertEqual(s.bgm_id, 2); self.assertIsNone(s.bgm_layer)

    def test_layer_with_restart_resumes_at_its_end(self):
        s = self.s; s.play_bgm(2); first = s.bgm
        s.play_bgm(0x3006)                                              # a short track over the music, bit 12: the music comes back by itself
        self.assertEqual((s.bgm_id, s.resume), (6, 2))
        s.bgm_end = time.time() - 1; s.tick()
        self.assertIs(s.bgm, first); self.assertTrue(first.playing)

    def test_other_track_or_stop_drops_the_paused_one(self):
        s = self.s; s.play_bgm(2); first = s.bgm
        s.play_bgm(0x2005); s.play_bgm(23)
        self.assertIsNone(s.bgm_layer); self.assertEqual(s.bgm_id, 23); self.assertFalse(first.playing)
        s.play_bgm(0x2005); s.play_bgm(0x4000)
        self.assertIsNone(s.bgm_layer); self.assertIsNone(s.bgm)

    def test_level_of_the_current_track(self):
        s = self.s; s.play_bgm(23); p = s.bgm; full = p.volume
        s.play_bgm(0x507f); self.assertIs(s.bgm, p); self.assertAlmostEqual(p.volume, full)       # Sound.StopBGM bit 12: a level, never a stop (DQ VI's Murdaw castle)
        s.play_bgm(0x5040); self.assertAlmostEqual(p.volume, full * 0x40 / 127.0); self.assertTrue(p.playing)
        s.play_bgm(0x5000); self.assertEqual(p.volume, 0.0); self.assertIs(s.bgm, p); self.assertEqual(s.bgm_id, 23)
        s.play_bgm(0x5080); self.assertAlmostEqual(p.volume, full)                                   # (above 0x107e: the music volume)
        s.play_bgm(0x5000); s.play_bgm(2); self.assertAlmostEqual(s.bgm.volume, full)               # a new track starts at the music volume
        self.assertEqual(s.bgm_state()['level'], 1.0)

    def test_jingle_detection(self):
        self.assertTrue(self.s.is_jingle(0x3006)); self.assertFalse(self.s.is_jingle(0x317)); self.assertFalse(self.s.is_jingle(0x4000))


if __name__ == '__main__':
    unittest.main(verbosity=1)
