"""the settings / hooks that the engine of a DIFFERENT APK does not let install are no longer silent: `Engine.missing_hooks` (console line + list without duplicates), then the window
notes them in `window_errors.log` and displays a message (Game._report_missing_hooks). Without engine: fake engine (simulated memory). With the game's APK (DQ_APK, DQ_SAVES): the original engine misses none of them.
    PYGLET_HEADLESS=1 python3 tests/test_missing_hooks.py"""
import os, shutil, struct, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import language as _LANGUAGE; _LANGUAGE.select_language('fr')          # (these tests expect the French texts, whatever the computer's language)
from dq456_pc.core import engine as ENGINE
APK = os.environ.get('DQ_APK', '')
SAVES = os.environ.get('DQ_SAVES', '')

BASE = 0x10000                                                     # address of the simulated function
ORIGINAL = (0x11000120 | (0xc0 << 10), 0x11000120 | (0x1c0 << 10), 0x11000120 | (0x314 << 10))       # add w0, w9, #imm of the three drawSymbol constants (mask 0xffc003e0 = 0x11000120)


def fake_engine(words=ORIGINAL, cmp_param=0x71001d1f):
    """Engine without an emulator: memory is a dictionary of bytes; export() returns BASE; LIB_BASE = 0 (cmp of the Settings button against CMP_PARAMS)."""
    mem = bytearray(0x200000)
    for dec, w in zip((0x44, 0x48, 0x4c), words): mem[BASE + dec:BASE + dec + 4] = struct.pack('<I', w)
    mem[ENGINE.Engine.CMP_PARAMS:ENGINE.Engine.CMP_PARAMS + 4] = struct.pack('<I', cmp_param)
    def write(a, d): mem[a:a + len(d)] = d
    core = types.SimpleNamespace(LIB_BASE=0, export=lambda n: BASE, mem=lambda a, n: bytes(mem[a:a + n]), mem_w=write)
    m = ENGINE.Engine.__new__(ENGINE.Engine); m.core = core; m.missing_hooks = []; m.mem = mem
    return m


def word(m, a): return struct.unpack('<I', bytes(m.mem[a:a + 4]))[0]


class WithoutEngine(unittest.TestCase):
    def test_missing_without_duplicate(self):
        m = fake_engine(); m._record_missing('a'); m._record_missing('b'); m._record_missing('a')
        self.assertEqual(m.missing_hooks, ['a', 'b'])

    def test_normal_locations_window(self):
        m = fake_engine(); m._widen_symbols()
        self.assertEqual(m.missing_hooks, [])
        for dec in (0x44, 0x48, 0x4c): self.assertEqual((word(m, BASE + dec) >> 10) & 0xfff, 1600)
        m._widen_symbols(); self.assertEqual(m.missing_hooks, [])               # already widened (after loading a savestate): neither error nor message

    def test_locations_window_dq5_dq6(self):
        """DQ V and DQ VI: other constants, another base register and another place in the function; DQ VI (21 icon slots) only grows to a 21:9 screen."""
        for imms, dec, base, wide in (((0x80, 0x180, 0x248), 0x90, 21, (1600,) * 3), ((0x60, 0x160, 0x26e), 0x48, 9, (0xf0, 0x1b0, 0x190))):
            m = fake_engine((0, 0, 0))
            for k, imm in enumerate(imms): m.mem[BASE + dec + 4 * k:BASE + dec + 4 * k + 4] = struct.pack('<I', 0x11000000 | (imm << 10) | (base << 5) | (24 + k))
            m._widen_symbols()
            self.assertEqual(m.missing_hooks, [])
            for k in range(3):
                w = word(m, BASE + dec + 4 * k)
                self.assertEqual(((w >> 10) & 0xfff, (w >> 5) & 0x1f, w & 0x1f), (wide[k], base, 24 + k))
            m._widen_symbols(); self.assertEqual(m.missing_hooks, [])

    def test_locations_window_other_version(self):
        other = (ORIGINAL[0], ORIGINAL[1], 0x11000120 | (0x555 << 10))
        m = fake_engine(other); m._widen_symbols()
        self.assertEqual(len(m.missing_hooks), 1); self.assertIn('places window', m.missing_hooks[0])
        self.assertEqual(word(m, BASE + 0x44), ORIGINAL[0])                             # nothing was touched
        m._widen_symbols(); self.assertEqual(len(m.missing_hooks), 1)           # no duplicate

    def test_params_button(self):
        m = fake_engine(); m.patch_params()
        self.assertEqual(m.missing_hooks, []); self.assertEqual(word(m, ENGINE.Engine.CMP_PARAMS), 0x713ffd1f)
        m.patch_params(); self.assertEqual(m.missing_hooks, [])               # already patched
        m = fake_engine(cmp_param=0xd503201f); m.patch_params()                  # other version: nop instead of the comparison
        self.assertEqual(len(m.missing_hooks), 1); self.assertIn('Settings button', m.missing_hooks[0])
        self.assertEqual(word(m, ENGINE.Engine.CMP_PARAMS), 0xd503201f)

    def test_installers_report_their_failure(self):
        """An engine whose functions cannot be found: each installer says so instead of staying silent."""
        def not_found(n): raise KeyError(n)
        for name_str in ('_text_hooks', '_fade_hooks', '_level_hooks', '_game_time_hooks', '_magic_hooks', '_divert_params', '_widen_symbols'):
            m = fake_engine(); m.core.export = not_found
            getattr(m, name_str)()
            self.assertTrue(m.missing_hooks, name_str + ' : echec silencieux')


class Window(unittest.TestCase):
    def setUp(self):
        try: from dq456_pc.window import game as F
        except Exception as ex: raise unittest.SkipTest('fenetre non importable ici (%r)' % (ex,))
        self.F = F; d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        self.logfile = os.environ['DQ_WINDOW_LOG'] = os.path.join(d, 'logs', 'window_errors.log')
        self.addCleanup(os.environ.pop, 'DQ_WINDOW_LOG', None)

    def read(self):
        with open(self.logfile, encoding='utf-8') as f: return f.read()

    def test_report_once_then_only_new_ones(self):
        j = types.SimpleNamespace(_reported_hooks=0)                                  # (without `toast`: no message on screen, only the log)
        eng = types.SimpleNamespace(missing_hooks=['text speed not installed', 'encounters: unexpected CountDown::exec'])
        self.F.Game._report_missing_hooks(j, eng)
        self.assertEqual(j._reported_hooks, 2)
        txt = self.read()
        self.assertIn('text speed', txt); self.assertIn('CountDown', txt); self.assertEqual(txt.count('\n'), 2)
        eng.missing_hooks.append('spells without effect: unexpected Magic menu')            # found after loading a savestate
        self.F.Game._report_missing_hooks(j, eng)
        self.assertEqual(j._reported_hooks, 3)
        txt = self.read(); self.assertEqual(txt.count('\n'), 3); self.assertIn('Magic menu', txt)


@unittest.skipUnless(os.path.exists(os.path.join(APK, 'split_UnityDataAssetPack.apk')) and os.path.isdir(SAVES), 'no game APK')
class RealEngine(unittest.TestCase):
    def test_original_engine_misses_none(self):
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_crochets_'))
        self.assertEqual(eng.missing_hooks, [])
        self.assertTrue(eng.sensor.active); self.assertTrue(eng.battle_sensor.active)
        eng.reapply_fixes(); self.assertEqual(eng.missing_hooks, [])           # loading a savestate: still nothing


if __name__ == '__main__': unittest.main(verbosity=1)
