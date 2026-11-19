"""(survey: "align with the original"): the volume of each sound is the file header's volume multiplied by `assets/sound/snd_vol.dat` (1171 floats, indices = BGM
file number or sound effect number), like Unity's `SoundControl.Play`: 49 music tracks from 0.7 to 0.95 and the SE0409 fanfare at 0.6. Missing file or index outside the table: 1.0.
Without window or sound card (fake players, fake APK).
    python3 tests/test_sound_volumes.py"""
import os, sys, tempfile, unittest, zipfile
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


def apk_with(table):
    """A fake APK (zip) that contains assets/sound/snd_vol.dat (or nothing if table is None)."""
    f = os.path.join(tempfile.mkdtemp(prefix='apk_vol_'), 'faux.apk')
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('assets/readme.txt', 'x')
        if table is not None: z.writestr('assets/sound/snd_vol.dat', np.asarray(table, '<f4').tobytes())
    return f


def table_standard():
    t = np.ones(1171, np.float32); t[1] = 0.7; t[2] = 0.8; t[14] = 1.0; t[409] = 0.6
    return t


def new_sound(apk, **kw):
    s = SOUND.Sound(apk, tempfile.mkdtemp(prefix='cache_son_'), log=lambda *a: None, logfile=lambda *a: None, alert=lambda *a: None, **kw)
    s.ok = True; s.ogg = True; s.media = FakeMedia; s.AudioFormat = lambda **kw: kw; s.AudioData = None
    SOUND.LoopSource = FakeSource
    return s


def data(volume, looping=True, seconds=2.0):
    n = int(seconds * 1000)
    return dict(pcm=np.zeros((n, 1), np.int16), frequency=1000, start=0, end=n if looping else 0, volume=volume, loop=looping)


class VolumeTable(unittest.TestCase):
    def test_read(self):
        s = new_sound(apk_with(table_standard()))
        for ident, v in ((1, 0.7), (2, 0.8), (14, 1.0), (409, 0.6), (300, 1.0), (1170, 1.0)): self.assertAlmostEqual(s.vol_snd(ident), v, 6, ident)

    def test_outside_table(self):
        s = new_sound(apk_with(table_standard()))
        for ident in (-1, 1171, 5000): self.assertEqual(s.vol_snd(ident), 1.0, ident)

    def test_missing_or_unreadable_file(self):
        self.assertEqual(new_sound(apk_with(None)).vol_snd(1), 1.0)
        self.assertEqual(new_sound('inexistant.apk').vol_snd(409), 1.0)
        self.assertEqual(new_sound(apk_with([0.5, 0.5, 0.5])).vol_snd(1), 0.5)               # (shorter table: valid for its indices, 1.0 beyond)
        self.assertEqual(new_sound(apk_with([0.5, 0.5, 0.5])).vol_snd(500), 1.0)

    def test_absurd_value_ignored(self):
        t = table_standard(); t[3] = 0.0; t[4] = 7.5; t[5] = float('nan'); t[6] = -1.0; s = new_sound(apk_with(t))
        for ident in (3, 4, 5, 6): self.assertEqual(s.vol_snd(ident), 1.0, ident)            # (0, > 1, nan, negative: no silence or gain)

    def test_read_only_once(self):
        s = new_sound(apk_with(table_standard())); s.vol_snd(1); t = s._table_vol; s.vol_snd(2); self.assertIs(s._table_vol, t)


class PlayedVolume(unittest.TestCase):
    def test_music(self):
        s = new_sound(apk_with(table_standard()))
        s.bgm_request = 1; s._launch_bgm(1, data(0.65))
        self.assertAlmostEqual(s.bgm.volume, 0.65 * 0.7, 6); self.assertAlmostEqual(s.bgm_own_volume, 0.65 * 0.7, 6)
        s.bgm_request = 14; s._launch_bgm(14, data(0.9))
        self.assertAlmostEqual(s.bgm.volume, 0.9, 6)                                         # (BGM14: 1.0, unchanged)

    def test_fanfare_sfx(self):
        s = new_sound(apk_with(table_standard()))
        s._launch_sfx(409, data(1.0, False)); self.assertAlmostEqual(s.sfx[-1].p.volume, 0.6, 6); self.assertAlmostEqual(s.sfx[-1].own, 0.6, 6)
        s._launch_sfx(300, data(1.0, False)); self.assertAlmostEqual(s.sfx[-1].p.volume, 1.0, 6)

    def test_sliders_and_options_stay_multiplied(self):
        s = new_sound(apk_with(table_standard()), music_volume=0.5)
        s.mix.game['music'] = 0.8
        s.bgm_request = 2; s._launch_bgm(2, data(0.75))
        self.assertAlmostEqual(s.bgm.volume, 0.5 * 0.8 * 0.75 * 0.8, 6)                       # slider x game option x header x snd_vol
        s.mix.vol['music'] = 1.0; s._apply_volumes(); self.assertAlmostEqual(s.bgm.volume, 1.0 * 0.8 * 0.75 * 0.8, 6)      # (a setting changed later keeps the file's factor)

    def test_without_table_nothing_changes(self):
        s = new_sound(apk_with(None)); s.bgm_request = 1; s._launch_bgm(1, data(0.65)); self.assertAlmostEqual(s.bgm.volume, 0.65, 6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
