"""The direction keys sent to a menu window of the game (MenuPort.Send gamepad, read by MenuItem::check50_NEW_PAD_UP to check80_NEW_PAD_RIGHT on MenuItem + 0x4a) are those of the
game: DQ IV up 2, down 1, left 8, right 4; DQ V / VI up 1, down 2, left 4, right 8 (sent the DQ IV way, the Yes / No and the other engine cursors of DQ V / VI went the other way).

1. the keyboard, the gamepad and the mouse hover send them through engine.MENU_DIRS (no direction number written in the code);
2. (real data, DQ_APK_DQ4 or DQ_APK, DQ_APK_DQ5, DQ_APK_DQ6) MENU_DIRS of each game is the bit its MenuItem::check* functions test.

    python3 tests/test_menu_directions.py
"""
import os, struct, subprocess, sys, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)

CHECKS = (('UP', 'check50_NEW_PAD_UP'), ('DOWN', 'check60_NEW_PAD_DOWN'), ('LEFT', 'check70_NEW_PAD_LEFT'), ('RIGHT', 'check80_NEW_PAD_RIGHT'))


def source(rel):
    with open(os.path.join(ROOT, 'dq456_pc', rel), encoding='utf-8') as f: return f.read()


class NoNumberInTheCode(unittest.TestCase):
    def test_menu_input(self):
        s = source('window/menu_display.py')
        self.assertIn('ENGINE.MENU_DIRS[bit]', s)
        for old in ('(ENGINE.UP, 2)', 'pad = 2 if bit == ENGINE.LEFT else 1', 'else pad); self.menu_to_release'): self.assertNotIn(old, s)

    def test_hover(self):
        s = source('window/keyboard_mouse.py')
        self.assertIn('ENGINE.MENU_DIRS', s); self.assertNotIn('(1 if tr > cr else 2)', s)


def library(game):
    folder = os.environ.get('DQ_APK_' + game.upper()) or (os.environ.get('DQ_APK') if game == 'dq4' else None) or ''
    apk = os.path.join(folder, 'split_config.arm64_v8a.apk')
    if not os.path.isfile(apk): return None
    from dq456_pc.core.emu_core import Elf
    return Elf(zipfile.ZipFile(apk).read('lib/arm64-v8a/lib%score.so' % game))


def menu_dirs(game):
    """engine.MENU_DIRS of `game` (the game is chosen before the engine is imported: another process)."""
    code = "from dq456_pc.core import engine as E; print(*[E.MENU_DIRS[getattr(E, d)] for d in ('UP', 'DOWN', 'LEFT', 'RIGHT')])"
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=dict(os.environ, DQ_GAME=game), capture_output=True, text=True, check=True).stdout
    return dict(zip(('UP', 'DOWN', 'LEFT', 'RIGHT'), map(int, out.split())))


class RealCode(unittest.TestCase):
    def check(self, game):
        elf = library(game)
        if elf is None: self.skipTest('no %s APK (DQ_APK_%s)' % (game, game.upper()))
        found = {}
        for d, fn in CHECKS:
            name = next(n for n in ('_ZN8MenuItem%d%sEv' % (len(fn), fn), '_ZN4ardq8MenuItem%d%sEv' % (len(fn), fn)) if n in elf.exports)
            a = elf.exports[name]
            for i in range(12):                                                  # the first tbnz of the function (on the halfword at + 0x4a)
                w = struct.unpack_from('<I', elf.img, a + 4 * i)[0]
                if w & 0x7f000000 == 0x37000000: found[d] = 1 << (((w >> 31) << 5) | ((w >> 19) & 0x1f)); break
        self.assertEqual(found, menu_dirs(game))

    def test_dq4(self): self.check('dq4')
    def test_dq5(self): self.check('dq5')
    def test_dq6(self): self.check('dq6')


if __name__ == '__main__':
    unittest.main(verbosity=2)
