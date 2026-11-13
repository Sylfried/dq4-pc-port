"""Decoding of AKB files (sound.py): clipped Ogg, sound effect loop.
Run from the root: PYTHONPATH=. python3 tests/test_sound_decoding.py (no sound card; soundfile is needed for the Ogg cases)."""
import io, os, shutil, struct, sys, tempfile, threading, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from dq4_pc import sound as S

try: import soundfile as sf
except Exception: sf = None


def overmodulated_ogg():
    """An Ogg Vorbis of an almost full-scale square signal: after decoding it exceeds +-1.0 (normal Vorbis overmodulation)."""
    sr = 44100; t = np.arange(sr * 2) / sr
    x = np.sign(np.sin(2 * np.pi * 440 * t)) * 0.999
    x = np.stack([x, x], 1).astype('float32')
    b = io.BytesIO(); sf.write(b, x, sr, format='OGG', subtype='VORBIS'); return b.getvalue()


@unittest.skipIf(sf is None, 'soundfile absent')
class ClippedOgg(unittest.TestCase):
    def test_overmodulated_signal_does_exceed_in_float(self):
        f, _ = sf.read(io.BytesIO(overmodulated_ogg()), dtype='float32', always_2d=True)
        self.assertGreater(float(np.abs(f).max()), 1.05)                       # (the test case is indeed an overflow case)

    def test_no_overflow(self):
        d = overmodulated_ogg(); f, _ = sf.read(io.BytesIO(d), dtype='float32', always_2d=True)
        pcm = S.decode_ogg(d)
        self.assertEqual(pcm.dtype, np.int16); self.assertEqual(pcm.shape, f.shape)
        ref = np.clip(np.rint(f * 32767.0), -32768, 32767)
        self.assertEqual(int(np.abs(pcm.astype(np.int64) - ref.astype(np.int64)).max()), 0)
        # a positive peak stays positive (reading directly as int16 flipped it into a negative peak)
        i = int(np.argmax(f[:, 0])); self.assertGreater(int(pcm[i, 0]), 30000)
        i = int(np.argmin(f[:, 0])); self.assertLess(int(pcm[i, 0]), -30000)
        self.assertEqual(int(pcm.max()), 32767); self.assertEqual(int(pcm.min()), -32768)

    def test_normal_signal_unchanged_within_one(self):
        sr = 22050; t = np.arange(sr) / sr; x = (0.3 * np.sin(2 * np.pi * 330 * t)).astype('float32')[:, None]
        b = io.BytesIO(); sf.write(b, x, sr, format='OGG', subtype='VORBIS')
        direct, _ = sf.read(io.BytesIO(b.getvalue()), dtype='int16', always_2d=True)
        self.assertLessEqual(int(np.abs(S.decode_ogg(b.getvalue()).astype(np.int64) - direct.astype(np.int64)).max()), 1)

    def test_decode_akb_goes_through_decode_ogg(self):
        header = bytearray(S.DATA_START); header[:4] = b'AKB '
        ogg = overmodulated_ogg(); struct.pack_into('<BBHIII', header, 0x0c, 5, 2, 44100, 88200, 0, 0); struct.pack_into('<f', header, 0x20, 1.0)
        r = S.decode_akb(bytes(header) + ogg)
        self.assertEqual(r['pcm'].dtype, np.int16); self.assertEqual(int(r['pcm'].max()), 32767); self.assertFalse(r['loop'])


def akb_ogg(n_samples=4000, begin=0, end=0, volume=1.0):
    """A minimal AKB (codec 5 = Ogg): a sound of n_samples samples, with a loop start and end declared in the header."""
    sr = 22050; x = (0.3 * np.sin(2 * np.pi * 330 * np.arange(n_samples) / sr)).astype('float32')[:, None]
    b = io.BytesIO(); sf.write(b, x, sr, format='OGG', subtype='VORBIS')
    header = bytearray(S.DATA_START); header[:4] = b'AKB '
    struct.pack_into('<BBHIII', header, 0x0c, 5, 1, sr, n_samples, begin, end); struct.pack_into('<f', header, 0x20, volume)
    return bytes(header) + b.getvalue()


@unittest.skipIf(sf is None, 'soundfile absent')
class LoopThatOverruns(unittest.TestCase):
    """a loop end that overshoots the end of the data by a few samples (leftover of an ADPCM block) is brought back to the end of the data."""
    def test_end_just_after_data_loops_until_end(self):
        n = len(S.decode_akb(akb_ogg(4000))['pcm'])
        r = S.decode_akb(akb_ogg(4000, begin=100, end=n + 5))
        self.assertTrue(r['loop']); self.assertEqual(r['start'], 100); self.assertEqual(r['end'], n)

    def test_end_exactly_at_end_unchanged(self):
        n = len(S.decode_akb(akb_ogg(4000))['pcm']); r = S.decode_akb(akb_ogg(4000, begin=0, end=n))
        self.assertTrue(r['loop']); self.assertEqual(r['end'], n)

    def test_end_far_beyond_stays_without_loop(self):
        n = len(S.decode_akb(akb_ogg(4000))['pcm'])
        r = S.decode_akb(akb_ogg(4000, begin=0, end=n + S.LOOP_END_TOLERANCE + 1))
        self.assertFalse(r['loop']); self.assertEqual((r['start'], r['end']), (0, 0))

    def test_without_loop_and_start_after_the_end(self):
        self.assertFalse(S.decode_akb(akb_ogg(4000, begin=0, end=0))['loop'])
        n = len(S.decode_akb(akb_ogg(4000))['pcm']); self.assertFalse(S.decode_akb(akb_ogg(4000, begin=n + 3, end=n + 4))['loop'])


@unittest.skipIf(sf is None, 'soundfile absent')
class SfxCache(unittest.TestCase):
    """The disk cache of the sound effects (sound_SE*.npz) from an old version (without the loops) is redone."""
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        self.apk = os.path.join(self.d, 'sons.apk')
        n = len(S.decode_akb(akb_ogg(4000))['pcm'])
        with zipfile.ZipFile(self.apk, 'w') as z: z.writestr('assets/sound/SE0001.akb', akb_ogg(4000, begin=0, end=n + 5))
        self.cache = os.path.join(self.d, 'cache'); os.makedirs(self.cache)
        self.sound = object.__new__(S.Sound); self.sound.apk, self.sound.cache, self.sound.log = self.apk, self.cache, print; self.sound.lock = threading.Lock(); self.sound.zip = None
        self.n = n

    def test_old_cache_rebuilt(self):
        f = os.path.join(self.cache, 'sound_SE0001.npz')
        np.savez(f, pcm=np.zeros((self.n, 1), np.int16), p=np.array([22050, 0, 0, 0], np.int64), v=np.array([1.0], np.float32))          # old format: 4 values, no loop
        r = self.sound._decode('SE0001')
        self.assertTrue(r['loop']); self.assertEqual(r['end'], self.n); self.assertGreater(int(np.abs(r['pcm']).max()), 100)     # re-decoded (not the cache's zeros)
        self.assertEqual(int(np.load(f)['p'][4]), S.SOUND_CACHE_VERSION)                                                              # and cache rewritten at the current version

    def test_current_cache_reread(self):
        self.sound._decode('SE0001'); os.remove(self.apk); self.sound.zip = None                                                         # no more source: only the cache can answer
        r = self.sound._decode('SE0001'); self.assertTrue(r['loop']); self.assertEqual(r['end'], self.n)


if __name__ == '__main__': unittest.main(verbosity=1)
