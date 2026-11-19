"""Web panel of the debug mode (dq456_pc/debug/panel.py): served on 127.0.0.1 only, its API reads through DebugService.call (between two engine steps, on the
window's thread), its commands pause, step, change the speed, read and write memory. Stand-in window and engine: the CI has neither.

    python3 tests/test_debug_panel.py
"""
import json, os, sys, threading, time, unittest, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.debug import panel as PN
from dq456_pc.debug import service as DS
sys.path.insert(0, HERE)
from test_debug_recorder import Game


class Core:
    LIB_BASE = 0x10000000
    def __init__(self): self.ram = bytearray(0x100); self.elf = type('E', (), {'size': 0x100})()
    def export(self, name): return self.LIB_BASE + 0x40 if name == 'sym' else None
    def mem(self, a, n): return bytes(self.ram[a - self.LIB_BASE:a - self.LIB_BASE + n])
    def mem_w(self, a, b): self.ram[a - self.LIB_BASE:a - self.LIB_BASE + len(b)] = b


class PanelTest(unittest.TestCase):
    def setUp(self):
        self.g = Game(); self.g.args.debug_port = 0               # (no panel made by the service itself: one on a free port below)
        self.g.engine.core = Core(); self.g.engine.mesh_state = {}
        self.g.engine.state.sprites = {0: {'id': 109, 'pos': (0.0, 0.05, 0.78), 'visible': True, 'pose': 2, 'dir': 0, 'scale': 1.0}}
        self.g.state_info = lambda n: ({'date': 'd', 'map': 'm', 'frames': 5}, b'') if n == 2 else None
        self.d = DS.DebugService(self.g); self.p = PN.Panel(self.d, port=0)
        self.d.main_thread = -1                                    # (the test plays the window: a loop thread runs the queued commands)
        self.stop = False
        def loop():
            while not self.stop:
                if not self.d.gate(): self.g.engine.step(0, 0)
                time.sleep(0.005)
        self.t = threading.Thread(target=loop, daemon=True); self.t.start()

    def tearDown(self):
        self.stop = True; self.t.join(1.0); self.p.stop()

    def get(self, path): return json.loads(urllib.request.urlopen(self.p.url().rstrip('/') + path, timeout=5).read())
    def post(self, c): return json.loads(urllib.request.urlopen(urllib.request.Request(self.p.url() + 'api/cmd', data=json.dumps(c).encode(), method='POST'), timeout=5).read())

    def test_api(self):
        self.assertTrue(self.p.url().startswith('http://127.0.0.1:'))
        page = urllib.request.urlopen(self.p.url(), timeout=5).read()
        self.assertIn(b'/api/state', page)
        s = self.get('/api/state'); self.assertEqual(s['map'], 'mbk1f1'); self.assertIn('speeds', s)
        self.assertEqual(self.post({'cmd': 'pause'}), {'ok': True}); f0 = self.get('/api/state')['frame']; time.sleep(0.1)
        self.assertEqual(self.get('/api/state')['frame'], f0)
        self.post({'cmd': 'step', 'n': 3}); time.sleep(0.2); self.assertEqual(self.get('/api/state')['frame'], f0 + 3)
        self.post({'cmd': 'speed', 'value': 4}); self.assertEqual(self.d.speed, 4.0)
        self.post({'cmd': 'resume'}); time.sleep(0.1)
        self.assertTrue(self.get('/api/packets?since=-1'))
        self.assertEqual(self.get('/api/objects')['sprites'][0]['id'], 109)
        self.post({'cmd': 'write_memory', 'where': 'sym', 'bytes': '33 03 00 00'})
        m = self.get('/api/memory?where=sym&len=4'); self.assertEqual(m['u32'], [819]); self.assertEqual(m['lib_offset'], 0x40)
        self.assertIn('error', self.get('/api/memory?where=nothing'))
        self.assertEqual([x['slot'] for x in self.get('/api/savestates') if x['info']], [2])
        self.assertIn('error', self.post({'cmd': 'nothing'}))

    def test_hex_lines(self):
        line = PN.hex_lines(0x10, b'AB\x00')[0]
        self.assertTrue(line.startswith('0x00000010  41 42 00 ')); self.assertTrue(line.endswith('  AB.'))


if __name__ == '__main__':
    unittest.main()
