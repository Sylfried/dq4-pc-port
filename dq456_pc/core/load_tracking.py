"""Timestamped log of startup and map changes (diagnostic tool, no effect outside tests).

    DQ_TRACKING=1          : one line per event on the console, "SUIVI +12.345s evenement cle=valeur ..." (time since the program was launched)
    DQ_TRACKING=<file>     : the same thing in this file (append)

What is recorded (see window.py and engine.py): window creation, first black frames, window display, logo frames, end of engine loading, first game frame, duration of each map
loading (`_load_map`), frame by frame after a map change (what is drawn: held black or scene, camera, characters placed, fade opacity), drawing hold
(`State.loading`). Without the environment variable, each call costs only a boolean test."""
import os, time

_VAL = os.environ.get('DQ_TRACKING', '')
ACTIVE = bool(_VAL) and _VAL != '0'
_FILE = _VAL if ACTIVE and _VAL != '1' else None
_T0 = time.perf_counter()


def clock():
    """Seconds since the program was launched (monotonic clock)."""
    return time.perf_counter() - _T0


def note(event_code, **fields):
    """A log line (no effect if DQ_TRACKING is not defined)."""
    if not ACTIVE: return
    line = 'TRACE +%.3fs %s' % (clock(), event_code)
    if fields: line += ' ' + ' '.join('%s=%s' % (k, v) for k, v in fields.items())
    try:
        if _FILE:
            with open(_FILE, 'a') as f: f.write(line + '\n')
        else: print(line, flush=True)
    except Exception: pass


def rounded(v, n=2):
    """Tuple of floats rounded for the log (None stays None)."""
    return None if v is None else tuple(round(float(x), n) for x in v)
