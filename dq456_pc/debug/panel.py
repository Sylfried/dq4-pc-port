"""Web panel of the debug mode: a page served on this computer only (http://127.0.0.1:8765, `--debug-port` to change it; F9 opens it in the browser), to keep on a
second screen beside the game.

Tabs: state (with the time control), engine -> interface packets of the last steps, the menu windows, the characters and objects, the engine's memory (by symbol or
address), the savestates. The page asks the server every half second; the server never touches the engine itself: what needs it goes through `DebugService.call`
(applied between two engine steps on the window's thread). Only reachable from this computer (127.0.0.1)."""
import collections, json, os, struct, threading, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dq456_pc import games as GM
from dq456_pc import language as LG

DEFAULT_PORT = 8765
PACKET_STEPS = 240                  # engine steps whose packets are kept (8 s)
PACKET_INTS, PACKET_FLOATS = 12, 8  # values kept per packet
MEMORY_MAX = 4096                   # bytes read at once
SAVESTATE_SLOTS = range(1, 10)
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'panel.html')


def hex_lines(base, data):
    """Bytes -> ['0x20001000  00 01 ...  ....'] (16 per line)."""
    out = []
    for i in range(0, len(data), 16):
        b = data[i:i + 16]
        out.append('%#010x  %-47s  %s' % (base + i, ' '.join('%02x' % x for x in b), ''.join(chr(x) if 32 <= x < 127 else '.' for x in b)))
    return out


def parse_address(core, text):
    """'0x1234' (address), '+0x1234' (offset in the engine's library) or a symbol name (exported, mangled or not) -> absolute address, or None."""
    t = (text or '').strip()
    if not t: return None
    try:
        if t.startswith('+'): return core.LIB_BASE + int(t[1:], 0)
        return int(t, 0)
    except ValueError: pass
    a = core.export(t)
    if a: return a
    return None


class Panel:
    """The panel of a debug service: its packets ring and its HTTP server."""

    def __init__(self, service, port=None):
        self.d = service; self.g = service.g
        self.packets = collections.deque(maxlen=PACKET_STEPS)
        self.lock = threading.Lock()
        service.after_step.append(self._keep_packets)
        self.port = None; self.server = None
        self._start(port or DEFAULT_PORT)

    # --- data (window thread) --------------------------------------------------------------------------------------------------------------------------------------
    def _keep_packets(self, pkts):
        frame = self.g.engine.frames
        row = [(int(t), [int(x) for x in a[:PACKET_INTS]], [round(float(x), 4) for x in f[:PACKET_FLOATS]], len(a), len(f)) for t, a, f in (pkts or ())]
        with self.lock: self.packets.append((frame, row))

    def state(self):
        try: v = self.d.values()
        except Exception as ex:                                   # (a scene being changed: the next request reads it again)
            eng = self.g.engine
            v = {'speed': self.d.speed, 'paused': self.d.paused, 'frame': eng.frames, 'loop': self.g.n_loop, 'part': eng.state.part, 'part_name': '?', 'map': eng.state.game_map,
                 'flags': 0, 'fade': None, 'background_fade': None, 'menu': 'state not readable: %s' % ex, 'message': False, 'steps_per_s': 0.0, 'step_ms': 0.0, 'draw_ms': 0.0, 'notes': [], 'panel': None}
        v = {k: (list(x) if isinstance(x, tuple) else x) for k, x in v.items()}
        g = self.g; eng = g.engine
        v.update(game=GM.profile().key, game_name=GM.profile().name, language=LG.current_language(), speeds=list(self.d.SPEEDS), replaying=self.d.recorder.replay is not None,
                 log=[str(l) for l in getattr(eng.log, 'lines', [])[-30:]], fade=_plain(v.get('fade')), background_fade=_plain(v.get('background_fade')))
        return v

    def menus(self):
        g = self.g; eng = g.engine; out = []
        active = eng.active_menu()
        for port, f in sorted(eng.ui.f.items()):
            wnd = g.ui_g.f.get(port) if getattr(g, 'ui_g', None) else None
            try: name = g._type_name(f.get('type'))
            except Exception: name = None
            buttons = [[b, pd, round((x0 + x1) / 2, 1), round((z0 + z1) / 2, 1)] for b, pd, x0, z0, x1, z1, *_ in (wnd.buttons() if wnd else []) if b >= 0]
            out.append({'port': port, 'type': f.get('type'), 'name': name, 'visible': bool(f.get('visible')), 'order': f.get('order'), 'grid': _plain(f.get('grid')),
                        'cursor': f.get('cur'), 'local_cursor': g.cur_local.get((port, f.get('order'))) if hasattr(g, 'cur_local') else None, 'active': port == active,
                        'lines': [str(l[1]) if isinstance(l, (tuple, list)) and len(l) > 1 else str(l) for l in (g._menu_lines(f) if hasattr(g, '_menu_lines') else [])][:24], 'buttons': buttons})
        return out

    def objects(self):
        e = self.g.engine.state
        sprites = [{'slot': k, 'id': sp.get('id'), 'pos': _plain(sp.get('pos')), 'visible': sp.get('visible'), 'pose': sp.get('pose'), 'dir': sp.get('dir'), 'scale': sp.get('scale')}
                   for k, sp in sorted(e.sprites.items())]
        meshes = [{'slot': k, 'visible': st.get('visible'), 'shader': st.get('shader')} for k, st in sorted(getattr(self.g.engine, 'mesh_state', {}).items())]
        return {'sprites': sprites, 'meshes': meshes, 'camera': _plain(getattr(e, 'cam_pos', None)), 'map': e.game_map}

    def memory(self, where, length):
        core = self.g.engine.core
        a = parse_address(core, where)
        if a is None: return {'error': 'unknown address or symbol: %s' % where}
        n = max(1, min(int(length), MEMORY_MAX))
        try: data = bytes(core.mem(a, n))
        except Exception as ex: return {'error': str(ex)}
        return {'address': a, 'lib_offset': a - core.LIB_BASE if core.LIB_BASE <= a < core.LIB_BASE + core.elf.size else None, 'lines': hex_lines(a, data),
                'u32': list(struct.unpack('<%dI' % (len(data) // 4), data[:len(data) // 4 * 4]))[:64]}

    def write_memory(self, where, hex_bytes):
        core = self.g.engine.core
        a = parse_address(core, where)
        if a is None: return {'error': 'unknown address or symbol: %s' % where}
        data = bytes.fromhex(hex_bytes.replace(' ', ''))
        core.mem_w(a, data); self.d.note('memory %#x <- %s' % (a, data.hex()))
        return {'written': len(data)}

    def savestates(self):
        out = []
        for n in SAVESTATE_SLOTS:
            info = None
            try: r = self.g.state_info(n); info = r[0] if r else None
            except Exception: pass
            out.append({'slot': n, 'info': {k: info.get(k) for k in ('date', 'map', 'frames', 'location')} if info else None})
        return out

    def command(self, c):
        """A command of the page (window thread) -> result dictionary."""
        d = self.d; g = self.g; kind = c.get('cmd')
        if kind == 'pause': d.set_paused(True)
        elif kind == 'resume': d.set_paused(False)
        elif kind == 'step': d.step(max(1, min(int(c.get('n', 1)), 600)))
        elif kind == 'speed': d.set_speed(float(c.get('value', 1.0)))
        elif kind == 'overlay': d.overlay = bool(c.get('on', not d.overlay))
        elif kind == 'report': d.report_requested = True
        elif kind == 'save_state': g.save_state(int(c['slot'])); d.note('savestate %d saved' % int(c['slot']))
        elif kind == 'load_state': g.load_state(int(c['slot'])); d.note('savestate %d loaded' % int(c['slot']))
        elif kind == 'write_memory': return self.write_memory(c.get('where'), c.get('bytes', ''))
        else:
            extra = getattr(d, 'panel_commands', {}).get(kind)
            if extra is None: return {'error': 'unknown command %s' % kind}
            return extra(c) or {'ok': True}
        return {'ok': True}

    # --- server ----------------------------------------------------------------------------------------------------------------------------------------------
    def _start(self, port):
        panel = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _send(self, code, body, kind='application/json; charset=utf-8'):
                raw = body if isinstance(body, bytes) else json.dumps(body, default=str).encode('utf-8')
                self.send_response(code); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(raw))); self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(raw)

            def _local(self):
                return self.client_address[0] in ('127.0.0.1', '::1')

            def do_GET(self):
                if not self._local(): return self._send(403, {'error': 'local only'})
                u = urllib.parse.urlparse(self.path); q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
                try:
                    if u.path in ('/', '/index.html'):
                        with open(PAGE, 'rb') as f: return self._send(200, f.read(), 'text/html; charset=utf-8')
                    if u.path == '/favicon.ico': return self._send(204, b'', 'image/x-icon')
                    if u.path == '/api/state': return self._send(200, panel.d.call(panel.state))
                    if u.path == '/api/packets':
                        since = int(q.get('since', -1))
                        with panel.lock: rows = [r for r in panel.packets if r[0] > since]
                        return self._send(200, rows)
                    if u.path == '/api/menus': return self._send(200, panel.d.call(panel.menus))
                    if u.path == '/api/objects': return self._send(200, panel.d.call(panel.objects))
                    if u.path == '/api/memory': return self._send(200, panel.d.call(lambda: panel.memory(q.get('where'), q.get('len', 256))))
                    if u.path == '/api/savestates': return self._send(200, panel.d.call(panel.savestates))
                    extra = getattr(panel.d, 'panel_pages', {}).get(u.path)
                    if extra is not None: return self._send(200, panel.d.call(lambda: extra(q)))
                    return self._send(404, {'error': 'not found'})
                except Exception as ex: return self._send(500, {'error': '%s: %s' % (type(ex).__name__, ex)})

            def do_POST(self):
                if not self._local(): return self._send(403, {'error': 'local only'})
                try:
                    n = int(self.headers.get('Content-Length', 0)); c = json.loads(self.rfile.read(n) or b'{}')
                    if self.path != '/api/cmd': return self._send(404, {'error': 'not found'})
                    return self._send(200, panel.d.call(lambda: panel.command(c)))
                except Exception as ex: return self._send(500, {'error': '%s: %s' % (type(ex).__name__, ex)})

        for p in (port, 0):                       # the usual port, or any free one if it is taken
            try: self.server = ThreadingHTTPServer(('127.0.0.1', p), Handler); break
            except OSError: continue
        if self.server is None: return
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, name='debug panel', daemon=True).start()

    def url(self):
        return 'http://127.0.0.1:%d/' % self.port if self.port else None

    def open(self):
        u = self.url()
        if u: webbrowser.open(u)
        return u

    def stop(self):
        if self.server is not None: self.server.shutdown(); self.server.server_close(); self.server = None


def _plain(x):
    """Tuples, numpy arrays and numbers -> JSON values."""
    if x is None or isinstance(x, (bool, int, str)): return x
    if isinstance(x, float): return round(x, 4)
    if isinstance(x, dict): return {str(k): _plain(v) for k, v in x.items()}
    try: return [_plain(v) for v in list(x)]
    except TypeError: return float(x) if hasattr(x, '__float__') else str(x)
