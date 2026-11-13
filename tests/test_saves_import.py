"""the saves import checks the checksum of each adventure log (a damaged file, or one that is not a game adventure log, is refused with its reason instead of giving "banque vide" at load) and writes each
file whole or not at all (temporary file then replacement: a failure leaves the old file intact). Without window or engine; the real saves (DQ_SAVES) are also checked if present.
    python3 tests/test_saves_import.py"""
import os, shutil, struct, sys, tempfile, unittest, zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc import language as LG
LG.select_language('fr')          # (the expectations of this test are in French, whatever the language of the computer)
from dq4_pc import paths as CH
from dq4_pc.persistence import write_dir as EC
from dq4_pc.persistence import logfile_format as FJ
from dq4_pc.persistence import saves as S
SAVES = os.environ.get('DQ_SAVES', '')


def logfile(n=0, word0=FJ.MAGIC1):
    """Game adventure log in plaintext then encrypted; `n` distinguishes it from the others; word0 = FJ.NEW / FJ.DELETED for an empty bank."""
    c = bytearray(FJ.LOGFILE_SIZE); struct.pack_into('<II', c, 0, word0, FJ.MAGIC2); c[0x30] = n
    struct.pack_into('<I', c, 8, FJ.checksum(bytes(c))); return FJ.decrypt(bytes(c))


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(content)


def read(path):
    with open(path, 'rb') as f: return f.read()


class Check(unittest.TestCase):
    def test_valid(self): self.assertIsNone(FJ.check('data1.dat', logfile(1)))

    def test_empty_banks(self):                                       # new bank (DWEN) or deleted (DLED): valid, without checksum
        for m in (FJ.NEW, FJ.DELETED):
            c = bytearray(FJ.LOGFILE_SIZE); struct.pack_into('<I', c, 0, m); self.assertIsNone(FJ.check('data3.dat', FJ.decrypt(bytes(c))), hex(m))

    def test_a_byte_changed(self):
        j = bytearray(logfile(1)); j[0x500] ^= 1; self.assertIn('somme', FJ.check('data1.dat', bytes(j)))

    def test_checksum_changed(self):
        c = bytearray(FJ.decrypt(logfile(1))); c[8] ^= 0xff; self.assertIn('somme', FJ.check('data2.dat', FJ.decrypt(bytes(c))))

    def test_noise_and_empty_file(self):
        self.assertIn('pas un journal', FJ.check('data1.dat', bytes(range(256)) * 60)); self.assertIn('pas un journal', FJ.check('data1.dat', bytes(FJ.LOGFILE_SIZE)))

    def test_data9_and_sizes_out_of_scope(self):                         # data9 (512 bytes): no checksum; the size is checked elsewhere
        self.assertIsNone(FJ.check('data9.dat', bytes(512))); self.assertIsNone(FJ.check('data1.dat', b'xx'))


@unittest.skipUnless(os.path.isdir(SAVES), 'no original saves')
class RealSaves(unittest.TestCase):
    def test_all_accepted(self):
        n = 0
        for name_str in S.NAMES:
            p = os.path.join(SAVES, name_str)
            if os.path.isfile(p): self.assertIsNone(FJ.check(name_str, read(p)), name_str); n += 1
        self.assertGreater(n, 0)


class Import(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='sv_imp_'); self.d = CH.Folders(self.t, env={}); self.before = CH.FOLDERS; CH.FOLDERS = self.d
        self.wdir = self.d.portage; self.zip = os.path.join(self.t, 'i.zip')

    def tearDown(self): CH.FOLDERS = self.before; shutil.rmtree(self.t, ignore_errors=True)

    def make_zip(self, **files):
        with zipfile.ZipFile(self.zip, 'w') as z:
            for name_str, d in files.items(): z.writestr(name_str.replace('__', '/'), d)

    def test_a_damaged_save_file_is_refused_the_others_pass(self):
        write(os.path.join(self.wdir, 'data1.dat'), logfile(1)); bad = bytearray(logfile(3)); bad[100] ^= 1
        self.make_zip(**{'data1.dat': logfile(2), 'data2.dat': bytes(bad), 'data9.dat': bytes(512)})
        nj, n_savestates, copied, pb = S.import_saves([self.zip], self.wdir, self.d.mobile)
        self.assertEqual((nj, n_savestates), (2, 0)); self.assertEqual(len(pb), 1); self.assertTrue(pb[0].startswith('data2.dat : fichier abime')); self.assertIn('somme', pb[0])
        self.assertEqual(read(os.path.join(self.wdir, 'data1.dat')), logfile(2)); self.assertFalse(os.path.exists(os.path.join(self.wdir, 'data2.dat')))      # the damaged file is not written
        self.assertEqual(read(os.path.join(copied, 'data1.dat')), logfile(1))

    def test_everything_refused(self):
        self.make_zip(**{'data1.dat': bytes(FJ.LOGFILE_SIZE)})
        with self.assertRaises(ValueError) as cm: S.import_saves([self.zip], self.wdir, self.d.mobile)
        self.assertIn('pas un journal', str(cm.exception)); self.assertFalse(os.path.exists(os.path.join(self.wdir, 'data1.dat')))

    def test_write_failure_leaves_the_old_file(self):
        write(os.path.join(self.wdir, 'data1.dat'), logfile(1)); write(os.path.join(self.wdir, 'data2.dat'), logfile(1))
        self.make_zip(**{'data1.dat': logfile(2), 'data2.dat': logfile(2)})
        actual = os.replace
        def fake_replace(src, dst, *a, **k):
            if os.path.basename(dst) == 'data1.dat': raise PermissionError('verrouille par un antivirus')
            return actual(src, dst, *a, **k)
        with mock.patch('time.sleep'), mock.patch('os.replace', fake_replace): nj, n_savestates, copied, pb = S.import_saves([self.zip], self.wdir, self.d.mobile)
        self.assertEqual(nj, 1); self.assertTrue(any(p.startswith('data1.dat : ecriture impossible') for p in pb))
        self.assertEqual(read(os.path.join(self.wdir, 'data1.dat')), logfile(1))                    # unchanged
        self.assertEqual(read(os.path.join(self.wdir, 'data2.dat')), logfile(2))                    # the other one went through
        self.assertEqual(sorted(f for f in os.listdir(self.wdir) if f.endswith('.tmp')), [])        # no temporary file left behind

    def test_no_file_written(self):
        self.make_zip(**{'data1.dat': logfile(2)})
        with mock.patch('time.sleep'), mock.patch('os.replace', side_effect=PermissionError('non')):
            with self.assertRaises(ValueError) as cm: S.import_saves([self.zip], self.wdir, self.d.mobile)
        self.assertIn('data1.dat', str(cm.exception))


class AtomicWrite(unittest.TestCase):
    def test_written_and_replaced(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'sous', 'f.dat'); self.assertIsNone(EC.atomic_write(p, b'abc')); self.assertEqual(read(p), b'abc')
            self.assertIsNone(EC.atomic_write(p, b'de')); self.assertEqual(read(p), b'de'); self.assertEqual(os.listdir(os.path.dirname(p)), ['f.dat'])

    def test_engine_uses_same_function(self):
        try: from dq4_pc.core import engine as ENGINE
        except ImportError: self.skipTest('unicorn absent')
        self.assertIs(ENGINE.GameCore.atomic_write, EC.atomic_write)


if __name__ == '__main__': unittest.main(verbosity=1)
