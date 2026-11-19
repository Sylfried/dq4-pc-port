"""Bug reports of the debug mode: a recording kept in memory, written to a zip file by F8, replayed with `--debug-replay <file.zip>`.

Recording (always on in debug mode): a savestate of the engine every SNAPSHOT_STEPS steps (the KEEP last ones, in memory: 3 to 6 MB each, about 10 ms to take), and for each
engine step since the oldest one, what the window gave the engine: the keys (held, just pressed), the menu messages sent between two steps, and the interface -> engine
messages of the step (camera, map objects, ends of animations: they come from the window's clock and camera, which a replay does not have).

F8: `data/logs/bug_<game>_<date>.zip` with the oldest savestate kept (10 to 40 s before), the steps since, a savestate of the moment, the screenshot, the settings,
the end of the engine's log and of the window's error log, and a short summary. Replayed in debug mode (`--debug-replay`): the bundle's settings are used, the savestate
is loaded at the first frame, then each step gets the recorded keys and messages (the window's own menu messages are dropped meanwhile: the recording has them);
at the end of the recording the game is paused. Same engine state at each step as long as nothing outside these inputs changed it (the Esc menu, savestates)."""
import datetime, io, json, os, tempfile, time, zipfile

import pyglet

from dq456_pc import games as GM
from dq456_pc.core import engine as ENGINE
from dq456_pc.language import N_, tr
from dq456_pc.persistence import savestates as SS

SNAPSHOT_STEPS = int(os.environ.get('DQ_DEBUG_SNAPSHOT_STEPS', '300'))            # engine steps between two savestates in memory (10 s of game clock)
KEEP = 4                         # savestates kept: a report starts 10 to 40 s before F8
FORMAT = 1
LOG_LINES = 300                  # last engine log lines in a report
WINDOW_LOG_BYTES = 200000        # end of the window's error log in a report


class Recorder:
    """The recording of the debug service (`service.recorder`); `step_begin` / `step_end` are called around each engine step, `between_steps` at each loop frame."""

    def __init__(self, service):
        self.d = service; self.g = service.g
        self.snapshots = []                 # [(engine frame, index in steps, savestate)]
        self.steps = []                      # one dict per engine step: frame, held, decl, menus (sent before it), data (interface -> engine messages of the step)
        self.base = 0                        # index of steps[0] in the whole recording
        self.pending_menus = []              # menu messages sent since the last step (outside a step)
        self.current = None                  # the step being run
        self.replay = None                   # replay in progress: {'steps': [...], 'i': next step, 'mismatch': frames that differ}
        self._wrap_engine()

    # --- recording ------------------------------------------------------------------------------------------------------------------------------------------
    def _wrap_engine(self):
        eng = self.g.engine; send_menu = eng.send_menu; send_messages = eng._send_messages
        def menu(port, *args):
            if self.current is not None: return send_menu(port, *args)            # (sent by the engine's own code during a step: part of the step, not an input)
            if self.replay is not None and not self.replay.get('injecting'): return None          # replay: the window's messages are replaced by the recorded ones
            self.pending_menus.append([port] + list(args))
            return send_menu(port, *args)
        def messages(data):
            st = self.current
            if st is not None and self.replay is not None: data = bytes.fromhex(st.get('data', ''))          # (the recorded messages, none if the step had none)
            elif st is not None and data: st['data'] = data.hex()
            return send_messages(data)
        eng.send_menu = menu; eng._send_messages = messages
        self._send_menu = send_menu

    def step_begin(self, args, kwargs):
        """Before an engine step: its inputs -> the (held, decl) the engine must get."""
        held = args[0] if args else kwargs.get('held', 0); decl = args[1] if len(args) > 1 else kwargs.get('decl')
        if self.replay is not None: return self._replay_inputs(held, decl)
        self.current = {'frame': self.g.engine.frames, 'held': held, 'decl': decl, 'menus': self.pending_menus}
        self.pending_menus = []
        return held, decl

    def step_end(self):
        if self.replay is not None: self.current = None; return
        if self.current is not None: self.steps.append(self.current)
        self.current = None

    def between_steps(self):
        """Each loop frame (window thread, between two steps): a savestate every SNAPSHOT_STEPS steps; the steps older than the oldest savestate are dropped."""
        if self.replay is not None: self._replay_check_end(); return
        eng = self.g.engine; idx = self.base + len(self.steps); e = eng.state
        if getattr(e, 'load_wait', None) is not None or getattr(e, 'loading', None) is not None: return          # (not in the middle of a load)
        if not self.snapshots and (e.part not in (ENGINE.PART_TOWN, ENGINE.PART_FIELD) or eng.flags() & ENGINE.FADE_FLAG or getattr(self.g, 'map_name', None) != e.game_map): return          # the first one: once a map is shown
        if self.snapshots and eng.frames - self.snapshots[-1][0] < SNAPSHOT_STEPS and eng.frames >= self.snapshots[-1][0]: return
        try: snap = self.g._complete_savestate()
        except Exception as ex: self.d.note('snapshot: %s' % ex); return
        self.snapshots.append((eng.frames, idx, snap))
        if len(self.snapshots) > KEEP:
            self.snapshots.pop(0)
            first = self.snapshots[0][1]
            del self.steps[:first - self.base]; self.base = first

    # --- report ---------------------------------------------------------------------------------------------------------------------------------------------
    def report(self, screenshot_png, folder):
        """Writes the bug report -> its path."""
        g = self.g; eng = g.engine
        if not self.snapshots: raise RuntimeError('nothing recorded yet')
        frame0, idx0, snap0 = self.snapshots[0]
        steps = self.steps[idx0 - self.base:]
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, 'bug_%s_%s.zip' % (GM.profile().key, stamp))
        e = eng.state
        info = {'format': FORMAT, 'game': GM.profile().key, 'date': stamp, 'version': version(), 'frame_start': frame0, 'frame_end': eng.frames, 'steps': len(steps),
                'map': e.game_map, 'part': e.part, 'flags': eng.flags(), 'language': getattr(g, 'game_language', None)}
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, d in (('start.dqs', snap0), ('now.dqs', g._complete_savestate())):
                p = os.path.join(tmp, name); SS.write(p, d, {'location': info['map'], 'map': e.game_map, 'part': e.part, 'frames': eng.frames})
                z.write(p, name)
            z.writestr('steps.json', json.dumps(steps))
            z.writestr('info.json', json.dumps(info, indent=1))
            if screenshot_png: z.writestr('screenshot.png', screenshot_png)
            z.writestr('engine_log.txt', '\n'.join(str(l) for l in getattr(eng.log, 'lines', [])[-LOG_LINES:]))
            settings_file = getattr(getattr(g, 'args', None), 'settings', None)
            if settings_file and os.path.isfile(settings_file): z.write(settings_file, 'settings.json')
            wl = window_log()
            if wl and os.path.isfile(wl):
                with open(wl, 'rb') as f: f.seek(max(0, os.path.getsize(wl) - WINDOW_LOG_BYTES)); z.writestr('window_errors.log', f.read())
        return path

    # --- replay ---------------------------------------------------------------------------------------------------------------------------------------------
    def start_replay(self, path):
        """Loads the report's first savestate and replays its steps (called at the first loop frame)."""
        with zipfile.ZipFile(path) as z:
            steps = json.loads(z.read('steps.json'))
            with tempfile.TemporaryDirectory() as tmp:
                z.extract('start.dqs', tmp); d = SS.read(os.path.join(tmp, 'start.dqs'))
        SS.check(self.g.engine, d)
        self.g._apply_savestate(d)
        self.replay = {'steps': steps, 'i': 0, 'mismatch': 0, 'path': path}
        self.d.note(tr(N_('debug.replay_started')) % len(steps))

    def _replay_inputs(self, held, decl):
        r = self.replay; i = r['i']
        if i >= len(r['steps']): return held, decl
        st = r['steps'][i]; r['i'] = i + 1
        if st['frame'] != self.g.engine.frames: r['mismatch'] += 1
        r['injecting'] = True
        try:
            for m in st['menus']: self._send_menu(*m)
        finally: r['injecting'] = False
        self.current = st
        return st['held'], st['decl']

    def _replay_check_end(self):
        r = self.replay
        if r['i'] < len(r['steps']): return
        self.replay = None
        self.d.set_paused(True)
        self.d.note(tr(N_('debug.replay_over')) % (self.g.engine.frames, r['mismatch']))


def version():
    """The port's commit (git HEAD of the folder the port runs from), or None."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        with open(os.path.join(root, '.git', 'HEAD')) as f: head = f.read().strip()
        if head.startswith('ref: '):
            ref = os.path.join(root, '.git', *head[5:].split('/'))
            if os.path.isfile(ref):
                with open(ref) as f: return f.read().strip()
            with open(os.path.join(root, '.git', 'packed-refs')) as f:
                for l in f:
                    if l.strip().endswith(head[5:]): return l.split()[0]
        return head
    except OSError: return None


def window_log():
    try:
        from dq456_pc import paths as CH
        return CH.FOLDERS.window_logfile
    except Exception: return None


def capture_png():
    """The picture just drawn (back buffer, before the overlay) -> PNG bytes, or None."""
    try:
        buf = io.BytesIO()
        pyglet.image.get_buffer_manager().get_color_buffer().save('screenshot.png', file=buf)
        return buf.getvalue()
    except Exception: return None


def settings_from(path):
    """The settings file of a report, copied to a temporary file -> its path (None if the report has none)."""
    with zipfile.ZipFile(path) as z:
        if 'settings.json' not in z.namelist(): return None
        fd, p = tempfile.mkstemp(suffix='_settings.json'); os.close(fd)
        with open(p, 'wb') as f: f.write(z.read('settings.json'))
        return p
