"""The engine's memcpy / memmove (and strncmp, strcmp, strlen) run as ARM64 code inside the emulator (emu_core.Core.MEMCPY_NATIVE, STRINGS_NATIVE) instead of a Python handler called through a code hook.

  python3 tests/test_native_memcpy.py

1. the routine, run by Unicorn alone: every size from 0 to 40 and a few large ones, every relative position of source and destination (apart, overlapping forward, overlapping backward,
   the same place) gives what memmove gives, returns the destination, and touches nothing outside the destination; strncmp / strcmp give the sign of the Python handlers
   (unsigned bytes, the end of a string, n = 0, n past both ends), strlen the length;
2. the library is relocated exactly as before (its image after relocation is the fingerprint that ties a savestate to its engine: every existing state stays valid); the import's slot
   holds a branch to the routine and is left out of the ranges the Python hook watches; DQ_NO_NATIVE_IMPORTS=1 puts every import back through its Python handler."""
import os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import emu_core as EC
try:
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL
    import unicorn.arm64_const as C
except Exception:
    Uc = None


@unittest.skipIf(Uc is None, 'unicorn not installed')
class Routine(unittest.TestCase):
    CODE, MEM, RET = 0x10000, 0x200000, 0x20000

    def setUp(self):
        uc = self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.mem_map(self.CODE, 0x1000, UC_PROT_ALL); uc.mem_map(self.RET, 0x1000, UC_PROT_ALL); uc.mem_map(self.MEM, 0x10000, UC_PROT_ALL); uc.mem_map(0x300000, 0x1000, UC_PROT_ALL)
        uc.mem_write(self.CODE, EC.Core.native_code())

    def run_copy(self, image, d, s, n):
        uc = self.uc; uc.mem_write(self.MEM, bytes(image))
        uc.reg_write(C.UC_ARM64_REG_X0, self.MEM + d); uc.reg_write(C.UC_ARM64_REG_X1, self.MEM + s); uc.reg_write(C.UC_ARM64_REG_X2, n)
        uc.reg_write(C.UC_ARM64_REG_X30, self.RET); uc.reg_write(C.UC_ARM64_REG_SP, 0x300800)
        uc.emu_start(self.CODE, self.RET)
        self.assertEqual(uc.reg_read(C.UC_ARM64_REG_X0), self.MEM + d)
        return bytes(uc.mem_read(self.MEM, len(image)))

    def test_like_memmove(self):
        rnd = random.Random(5); image = bytes(rnd.randrange(256) for _ in range(0x600))
        cases = [(d, s, n) for n in list(range(0, 41)) + [63, 64, 65, 255, 256, 300] for d, s in ((0x100, 0x300), (0x300, 0x100), (0x100, 0x101), (0x101, 0x100), (0x100, 0x107), (0x107, 0x100),
                                                                                           (0x100, 0x108), (0x108, 0x100), (0x100, 0x100 + max(n - 1, 0)), (0x100 + max(n - 1, 0), 0x100), (0x100, 0x100))]
        for d, s, n in cases:
            want = bytearray(image); want[d:d + n] = image[s:s + n]
            self.assertEqual(self.run_copy(image, d, s, n), bytes(want), (hex(d), hex(s), n))

    def test_random(self):
        rnd = random.Random(11)
        for _ in range(300):
            image = bytes(rnd.randrange(256) for _ in range(0x400)); n = rnd.randrange(0, 0x180); d = rnd.randrange(0, 0x400 - n); s = rnd.randrange(0, 0x400 - n)
            want = bytearray(image); want[d:d + n] = image[s:s + n]
            self.assertEqual(self.run_copy(image, d, s, n), bytes(want), (d, s, n))


    def run_routine(self, name, *args):
        uc = self.uc
        for i, v in enumerate(args): uc.reg_write(C.UC_ARM64_REG_X0 + i, v)
        uc.reg_write(C.UC_ARM64_REG_X30, self.RET); uc.reg_write(C.UC_ARM64_REG_SP, 0x300800)
        uc.emu_start(self.CODE + EC.Core.NATIVE_TARGETS[name], self.RET)
        return uc.reg_read(C.UC_ARM64_REG_X0)

    @staticmethod
    def sign(v): return 0 if v == 0 else (1 if (v & 0xffffffff) < 0x80000000 else -1)

    def test_strings(self):
        rnd = random.Random(3); A, B = self.MEM, self.MEM + 0x800
        words = [b'', b'a', b'ab', b'abc', b'abd', b'abc\xff', b'abc\x01', b'\xfe', b'zz', b'scene_btl', b'scene_btlx', b'SE0300', b'SE0301']
        pairs = [(x, y) for x in words for y in words] + [(bytes(rnd.choice(b'ab\x80\xff') for _ in range(rnd.randrange(6))), bytes(rnd.choice(b'ab\x80\xff') for _ in range(rnd.randrange(6)))) for _ in range(400)]
        for x, y in pairs:
            self.uc.mem_write(A, x + b'\0' + b'Q' * 8); self.uc.mem_write(B, y + b'\0' + b'R' * 8)
            self.assertEqual(self.sign(self.run_routine('strcmp', A, B)), (x > y) - (x < y), (x, y))
            for n in (0, 1, 2, 3, 4, 7, 100):
                self.assertEqual(self.sign(self.run_routine('strncmp', A, B, n)), (x[:n] > y[:n]) - (x[:n] < y[:n]), (x, y, n))
            self.assertEqual(self.run_routine('strlen', A), len(x))


class Slots(unittest.TestCase):
    class FakeUc:
        def __init__(self): self.written = {}
        def mem_write(self, a, raw): self.written[a] = bytes(raw)

    def core(self, native):
        c = EC.Core.__new__(EC.Core); c.stub_names = ['<retour>']; c.stub_idx = {}; c.native = native; c.native_base = c.STUB_BASE + c.STUB_SIZE - c.NATIVE_SIZE; c.uc = self.FakeUc(); return c

    def test_relocation_unchanged(self):
        """The library is relocated to the same slots as before (its image is the savestates' fingerprint): only the slots' own code and the hook's ranges change."""
        names = ['malloc', 'memcpy', 'free', 'memmove', 'strlen', '__memcpy_chk', 'sin']
        a = self.core(True); b = self.core(False)
        ra = [a.stub_for(n, 1) for n in names]; rb = [b.stub_for(n, 1) for n in names]
        self.assertEqual(ra, rb); self.assertEqual(ra, [a.STUB_BASE + 4 * (i + 1) for i in range(len(names))]); self.assertEqual(a.stub_names, b.stub_names)

    def test_slots_branch_to_the_routine_and_leave_the_hook(self):
        import struct
        names = ['malloc', 'memcpy', 'free', 'memmove', 'strlen', '__memcpy_chk', 'sin']
        a = self.core(True)
        for n in names: a.stub_for(n, 1)
        slots = a._native_slots(); B = a.STUB_BASE
        self.assertEqual(slots, [B + 8, B + 16, B + 20, B + 24])
        for s, target in zip(slots, (0, 0, EC.Core.NATIVE_TARGETS['strlen'], 0)):
            w, = struct.unpack('<I', a.uc.written[s]); self.assertEqual(w >> 26, 0x14000000 >> 26)                 # b
            self.assertEqual(s + ((w & 0x3ffffff) << 2), a.native_base + target)
        self.assertEqual(a._hook_ranges(slots), [(B + 4, B + 7), (B + 12, B + 15), (B + 28, a.native_base - 1)])
        b = self.core(False)
        for n in names: b.stub_for(n, 1)
        self.assertEqual(b._native_slots(), []); self.assertEqual(b.uc.written, {})                                   # DQ_NO_NATIVE_IMPORTS: every import through its Python handler
        self.assertEqual(b._hook_ranges([]), [(B + 4, b.native_base - 1)])

    def test_routine(self):
        self.assertEqual(len(EC.Core.MEMCPY_NATIVE), 120); self.assertLessEqual(len(EC.Core.MEMCPY_NATIVE), EC.Core.NATIVE_SIZE)
        self.assertEqual(EC.Core.MEMCPY_NATIVE[-4:], bytes.fromhex('c0035fd6'))             # ends with "ret"
        code = EC.Core.native_code(); self.assertLessEqual(len(code), EC.Core.NATIVE_SIZE); self.assertEqual(code[-4:], bytes.fromhex('c0035fd6'))
        self.assertEqual(len(EC.Core.MEMCPY_NATIVE), 120); self.assertLessEqual(len(EC.Core.MEMCPY_NATIVE), EC.Core.NATIVE_TARGETS['strncmp'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
