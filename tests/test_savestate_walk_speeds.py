"""DQ IV: after a savestate is loaded, the hero's walking speeds are the engine's (Engine.reset_speeds, called by savestates.apply through reapply_fixes): they are variables
the engine sets when it starts (0 in the library's file), so they must not be copied from the library's image (the hero could no longer walk). Stand-in core: the CI has no game.

    python3 tests/test_savestate_walk_speeds.py
"""
import os, struct, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
os.environ.setdefault('DQ_GAME', 'dq4')
from dq456_pc.core import engine as ENGINE

BASE = 0x10000000
SYMBOLS = {'_ZN16TownPlayerAction9walkSpeedE': 0x2714bc, '_ZN16TownPlayerAction10walkSpeed2E': 0x2714c0, '_ZN11FieldPlayer5SpeedE': 0x275204}


class Core:
    LIB_BASE = BASE
    def __init__(self):
        self.memory = {}; self.elf = type('E', (), {'img': bytearray(0x280000)})()          # the library's file: .bss = zeros
    def export(self, name): return BASE + SYMBOLS[name] if name in SYMBOLS else None
    def mem_w(self, ad, b): self.memory[ad] = bytes(b)


class WalkSpeeds(unittest.TestCase):
    @unittest.skipIf(ENGINE.ENGINE_V2, 'DQ IV only')
    def test_speeds_after_load(self):
        eng = ENGINE.Engine.__new__(ENGINE.Engine); eng.core = Core()
        eng.reset_speeds()
        got = {ad - BASE: struct.unpack('<i', b)[0] for ad, b in eng.core.memory.items()}
        self.assertEqual(got, {0x2714bc: 819, 0x2714c0: 655, 0x275204: 12288, 0x27520c: 8192, 0x275210: 8192})
        self.assertNotIn(0, got.values())


if __name__ == '__main__':
    unittest.main()
