"""File writing that never leaves a half-written file (game saves, save imports)."""
import os
import time


def atomic_write(path, raw, attempts=2, pause=0.25):
    """Writes `raw` to `path`: temporary file alongside, then replaced in one step (never a half-written file); on an I/O error (antivirus locking the file, full disk, read-only
    folder) the whole thing is retried `attempts` times, spaced `pause` s apart. -> None if all goes well, otherwise the exception of the last attempt; the old file then remains intact."""
    last = None
    for i in range(max(1, attempts)):
        tmp = path + '.tmp'
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, 'wb') as fh: fh.write(raw); fh.flush(); os.fsync(fh.fileno())
            os.replace(tmp, path); return None
        except OSError as ex:
            last = ex
            try: os.remove(tmp)
            except OSError: pass
            if i + 1 < attempts: time.sleep(pause)
    return last
