"""Test helper: finding the source code again after the reorganization (dq456_pc is now a package with subfolders ; the old window.py is a folder of modules)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CODE = os.path.join(ROOT, 'dq456_pc')
PURE_LOGIC = ('inputs.py', 'screens.py')          # modules of dq456_pc/fenetre that were not part of the old window.py


def find_file(name_str):
    """Path of the module `name_str` (e.g. 'pause.py') in dq456_pc, whatever its subfolder."""
    for folder, _, files in os.walk(CODE):
        if '__pycache__' in folder: continue
        if name_str in files: return os.path.join(folder, name_str)
    raise FileNotFoundError(name_str)


def source(name_str):
    """Text of the module `name_str` ; 'window.py' = the whole old file: the Game class, its modules by theme, the constants and the functions (dq456_pc/window/*.py except the two pure-logic modules)."""
    if name_str == 'window.py':
        folder = os.path.join(CODE, 'window'); chunks = []
        for f in sorted(os.listdir(folder)):
            if f.endswith('.py') and f not in PURE_LOGIC and f != '__init__.py':
                with open(os.path.join(folder, f), encoding='utf-8') as fh: chunks.append(fh.read())
        return '\n'.join(chunks)
    with open(find_file(name_str), encoding='utf-8') as fh: return fh.read()


def set_global(name_str, value):
    """Replaces the value of the global `name_str` in all the dq456_pc.window modules that carry it (the old window.py was a single module: a `F.time = fake` acted everywhere). -> function that restores the old values."""
    import sys
    old_dirs = [(m, getattr(m, name_str)) for n, m in list(sys.modules.items()) if n.startswith('dq456_pc.window') and m is not None and hasattr(m, name_str)]
    for m, _ in old_dirs: setattr(m, name_str, value)
    def reset():
        for m, v in old_dirs: setattr(m, name_str, v)
    return reset


def ui_cache(default='/tmp/uicache'):
    """Folder of the game interface cache (`ui_layout.json`, `ui_garrir.json` / `.png`), produced by `tools/ui_il2cpp/generate_ui.py`.

    Every test reads it through this function (variable `DQ_UI_CACHE`).
    """
    import os
    return os.environ.get('DQ_UI_CACHE') or default
