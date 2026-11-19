""""Settings" chosen in the game's Misc menu opens the port's menu and closes the game's menu behind it, completely (two back presses: Misc, then the root menu), not just back to
the items / magic / attributes choice or to the Misc screen (the closing used to stop when the engine had no menu with the input for a frame, between two windows).

Real window (DQ_APK, DQ_SAVES): save 4 (world map), Enter opens the game's menu, "Miscellaneous", next page, "Settings": the "Settings" menu is open and no game menu waits behind it any more.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_params_closes_menu.py        (about 20 s)
"""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _paths

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
OPEN, DIVERS, NEXT_PAGE, PARAMS, CHECK = 300, 330, 355, 362, 420


def probe(out):
    import pyglet
    pyglet.options['shadow_window'] = False
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True
    from dq456_pc.window import game as F
    from dq456_pc import main
    sys.argv = ['window.py', '--apk', APK, '--saves-read', SAVES, '--saves-write', tempfile.mkdtemp(prefix='sv_params_'), '--settings', os.path.join(tempfile.mkdtemp(prefix='rg_params_'), 'r.json'),
                '--slot', '4', '--cache', _paths.ui_cache('/tmp/uicache_params'), '--msaa', '0', '--width', '1280', '--height', '720', '--no-preparation', '--no-sound', '--no-logos',
                '--test-keys', '%d:RETURN' % OPEN, '--shot', os.path.join(tempfile.gettempdir(), 'params.png'), '--images', str(CHECK + 5)]
    loop = F.Game._loop; res = {}
    def visible(eng): return [q for q, f in eng.ui.f.items() if f.get('visible') and q > 1]
    def loop2(self, dt):
        eng = self.engine; n = self.n_loop
        if n == DIVERS:
            root = [q for q, f in eng.ui.f.items() if f.get('visible') and f.get('type') == 3]
            if root: eng.send_menu(root[0], 1, 5, 16)
        if n == NEXT_PAGE: eng.send_menu(7, 1, -1, 4)
        if n == PARAMS:
            cells = [t for _, t in sorted(eng.ui.f[8]['cells'].items())]
            row = next((i for i, t in enumerate(cells) if 'Param' in t), None); res['row'] = row
            if row is not None: eng.send_menu(8, 1, row, 16); self.menu_to_release = 8          # (as Enter or a click does: the release goes on the next step; the closing waits for it)
            res['before'] = visible(eng)
        if n == CHECK:
            res.update(pause=self.pause.opened, stack=list(self.pause.stack) if self.pause.opened else None, active=eng.active_menu(), after=visible(eng))
            with open(out, 'w') as f: json.dump(res, f)
        return loop(self, dt)
    F.Game._loop = loop2
    main.main()


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class ParamsClosesMenu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = os.path.join(tempfile.mkdtemp(prefix='params_'), 'r.json')
        env = dict(os.environ, PYGLET_HEADLESS='1', PYGLET_AUDIO='silent')
        r = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__), '--sonde', out], capture_output=True, text=True, timeout=900, env=env)
        if not os.path.exists(out): raise RuntimeError('probe without a result: ' + r.stdout[-600:] + r.stderr[-600:])
        cls.r = json.load(open(out))

    def test_divers_was_open(self):
        self.assertIsNotNone(self.r['row'], 'Settings found on the 2nd page of Misc')
        self.assertTrue(len(self.r['before']) >= 3, self.r)

    def test_params_open_game_menu_closed(self):
        self.assertTrue(self.r['pause']); self.assertEqual(self.r['stack'], ['root', 'display'])          # (the menu's root, Display open on the right, as Esc opens it)
        self.assertIsNone(self.r['active'], self.r); self.assertEqual(self.r['after'], [], self.r)


if __name__ == '__main__':
    if '--sonde' in sys.argv: probe(sys.argv[sys.argv.index('--sonde') + 1])
    else: unittest.main(verbosity=2)
