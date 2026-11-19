"""Export and import of the save files ("Saves" button of the start menu, in place of "Sauv. cloud").

What is exported: the six game files (data1.dat to data3.dat = adventure logs, data4.dat = suspend save, data5.dat = auto-save, data9.dat = most recent adventure log) as the engine reads them
(the write folder first, otherwise the read folder), the port's savestates (savestates/<game ID>/state_NN.dqs: those of each game) and the rules of each game (rules/<ID>.json, see game_rules.py). A .zip file contains them flat (`data1.dat`, `savestates/state_01.dqs`).
What is imported: a .zip of this kind, or standalone dataN.dat files (for example those copied from an Android phone); the names are recognized even in subfolders of the .zip.
Nothing is ever overwritten without a copy: before the import, the files in the write folder that are about to be replaced are copied into `data\\saves\\dq4\\before_import_<date>\\`; the read folders (your original saves) are never modified.
The files are not interpreted here, only checked: size (adventure log: 15,360 bytes; data9: 512) and checksum of an adventure log (logfile_format: a damaged file, or one that is not a game adventure log, is rejected, with the reason, instead of giving an "empty bank" at load time); each file is written in full or not at all (temporary file then replacement)."""
import glob
import os
import re
import shutil
import threading
import time
import zipfile

from dq456_pc import paths as CH
from dq456_pc.language import tr
from dq456_pc.persistence import game_rules as GR
from dq456_pc.persistence import logfile_format as FJ
from dq456_pc.persistence.write_dir import atomic_write

NAMES = CH.LOGFILE_NAMES
SIZES = {'data1.dat': 0x3c00, 'data2.dat': 0x3c00, 'data3.dat': 0x3c00, 'data4.dat': 0x3c00, 'data5.dat': 0x3c00, 'data9.dat': 512}
RE_LOGFILE = re.compile(r'(?:^|[\\/])(data[1-59]\.dat)$', re.I)
RE_SAVESTATE = re.compile(r'(?:^|[\\/])(?:savestates|etats)[\\/]((?:[0-9a-f]{8}[\\/])?(?:state|etat)_\d\d\.dqs)$', re.I)          # (savestates/<game ID>/state_NN.dqs: the states of each game; `etats/etat_NN.dqs` from earlier .zip files is also recognized)
RE_SAVESTATE_ISOLATED = re.compile(r'^((?:state|etat)_\d\d\.dqs)$', re.I)


def savestate_name(name_str):
    """The name of a savestate as it is written now, relative to the savestates folder: `etat_03.dqs` (old name) -> `state_03.dqs`; `0000abcd\\state_03.dqs` -> `0000abcd/state_03.dqs`."""
    return re.sub(r'(^|/)etat_', r'\1state_', name_str.lower().replace('\\', '/'))


def timestamp():
    return time.strftime('%Y%m%d_%H%M%S')


def effective_files(write_dir, read_dir):
    """The adventure log files that the engine reads: {name: path} (the write folder takes precedence over the read folder, like GameCore.h_fopen)."""
    out = {}
    for name_str in NAMES:
        for d in (write_dir, read_dir):
            if d and os.path.isfile(os.path.join(d, name_str)): out[name_str] = os.path.join(d, name_str); break
    return out


def savestates(write_dir):
    """The port's savestates: {name relative to the savestates folder (`<game ID>/state_NN.dqs`, or `state_NN.dqs` not sorted by game yet): path}."""
    f = CH.FOLDERS.savestates_folder(write_dir)
    found = glob.glob(os.path.join(f, 'state_??.dqs')) + [p for p in glob.glob(os.path.join(f, '*', 'state_??.dqs')) if re.match(r'^[0-9a-f]{8}$', os.path.basename(os.path.dirname(p)))]
    return {os.path.relpath(p, f).replace(os.sep, '/'): p for p in sorted(found)}


def default_export_name():
    from dq456_pc import games as GM
    return '%s_saves_%s.zip' % (GM.profile().key, timestamp())


def export_saves(write_dir, read_dir, destination):
    """Writes the .zip. -> (number of adventure logs, number of savestates). Raises ValueError if there is nothing to export."""
    j = effective_files(write_dir, read_dir); e = savestates(write_dir)
    if not j and not e: raise ValueError(tr('saves.nothing_export_no_adventure_log'))
    folder = os.path.dirname(os.path.abspath(destination))
    if folder: os.makedirs(folder, exist_ok=True)
    tmp = destination + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for name_str, p in j.items(): z.write(p, name_str)
        for name_str, p in e.items(): z.write(p, 'savestates/' + name_str)
        for name_str, p in GR.files(write_dir).items(): z.write(p, GR.FOLDER + '/' + name_str)          # (the rules of the games: small files, not counted)
    os.replace(tmp, destination)
    return len(j), len(e)


def read_sources(paths):
    """Files to import: -> ({adventure log name: bytes}, {savestate name: bytes}, [problems]). Paths: .zip, folders (adventure logs / savestates inside) or standalone files."""
    jr, label, pb = {}, {}, []

    def add(full_name, read, origin):
        m = RE_LOGFILE.search(full_name)
        if m:
            name_str = m.group(1).lower(); d = read()
            if len(d) != SIZES[name_str]: pb.append(tr('saves.size_instead') % (name_str, len(d), SIZES[name_str], origin)); return
            reason = FJ.check(name_str, d)
            if reason: pb.append(tr('saves.name_value_detail') % (name_str, reason, origin)); return
            jr[name_str] = d; return
        m = RE_SAVESTATE.search(full_name) or RE_SAVESTATE_ISOLATED.match(os.path.basename(full_name))
        if m:
            d = read()
            if len(d) < 1024: pb.append(tr('saves.file_too_small') % (savestate_name(m.group(1)), origin)); return
            label[savestate_name(m.group(1))] = d

    for c in paths:
        if os.path.isdir(c):
            for root, _, files in os.walk(c):
                for f in files:
                    p = os.path.join(root, f); add(os.path.relpath(p, c), lambda p=p: open(p, 'rb').read(), c)
        elif c.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(c) as z:
                    for i in z.infolist():
                        if not i.is_dir() and i.file_size < 64 * 1024 * 1024: add(i.filename, lambda i=i, z=z: z.read(i), os.path.basename(c))
            except zipfile.BadZipFile: pb.append(tr('saves.not_valid_zip_file') % os.path.basename(c))
        else: add(os.path.basename(c), lambda c=c: open(c, 'rb').read(), os.path.dirname(c))
    return jr, label, pb


def import_saves(paths, write_dir, read_dir):
    """Copies the adventure logs / savestates found into the write folder, after copying those they replace into `before_import_<date>`. -> (number of adventure logs, number of savestates, copy folder or None, problems).
    Raises ValueError if nothing usable was found."""
    jr, label, pb = read_sources(paths)
    if not jr and not label: raise ValueError(tr('saves.no_save_file_recognized') % ('; '.join(pb) if pb else tr('saves.expected_data1_dat_data5_dat')))
    os.makedirs(write_dir, exist_ok=True)
    savestates_folder = CH.FOLDERS.savestates_folder(write_dir)
    copied = os.path.join(CH.FOLDERS.clones_folder(write_dir), 'before_import_' + timestamp()); n_clone = 0
    existing = {name_str: os.path.join(write_dir, name_str) for name_str in NAMES if os.path.isfile(os.path.join(write_dir, name_str))}        # (the read folder is never modified: its files stay intact, no need to copy them)
    for name_str in jr:
        if name_str in existing:
            os.makedirs(copied, exist_ok=True); shutil.copy2(existing[name_str], os.path.join(copied, name_str)); n_clone += 1
    for name_str in label:
        p = os.path.join(savestates_folder, *name_str.split('/'))
        if os.path.isfile(p):
            q = os.path.join(copied, 'savestates', *name_str.split('/')); os.makedirs(os.path.dirname(q), exist_ok=True); shutil.copy2(p, q); n_clone += 1
    written_j = written_e = 0
    for name_str, d in jr.items():
        ex = atomic_write(os.path.join(write_dir, name_str), d)
        if ex is None: written_j += 1
        else: pb.append(tr('saves.could_not_written_current_file') % (name_str, ex))
    for name_str, d in label.items():
        p = os.path.join(savestates_folder, *name_str.split('/')); os.makedirs(os.path.dirname(p), exist_ok=True)
        ex = atomic_write(p, d)
        if ex is None: written_e += 1
        else: pb.append(tr('saves.could_not_written_current_file') % (name_str, ex))
    if not written_j and not written_e: raise ValueError(tr('saves.no_file_could_written') % '; '.join(pb))
    for name_str, d in rules_in(paths).items(): atomic_write(os.path.join(GR.folder(write_dir), name_str), d)          # (the rules of the games come with their logs: one file per game ID, the same game whatever the copy)
    return written_j, written_e, (copied if n_clone else None), pb


def rules_in(paths):
    """The rules files (rules/<ID>.json, game_rules.py) of the .zip files and folders to import: {name: bytes}."""
    out = {}
    def add(full_name, read):
        m = GR.RE_IN_ARCHIVE.search(full_name.replace('\\', '/'))
        if m:
            d = read()
            if len(d) < 64 * 1024: out[m.group(1).lower()] = d
    for c in paths:
        if os.path.isdir(c):
            for root, _, fs in os.walk(c):
                for f in fs: p = os.path.join(root, f); add(os.path.relpath(p, c), lambda p=p: open(p, 'rb').read())
        elif c.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(c) as z:
                    for i in z.infolist():
                        if not i.is_dir(): add(i.filename, lambda i=i, z=z: z.read(i))
            except zipfile.BadZipFile: pass
    return out


# ---- file dialog boxes (tkinter, in a separate thread so the game window stays responsive)
class Dialogue:
    """A "Save As" or "Open" box; `result` stays None while it is open, then a list of paths (empty = canceled); `unavailable` true without tkinter."""
    def __init__(self, mode, title_screen, initial_folder=None, initial_name=None):
        self.result = None; self.unavailable = False; self.error = None
        threading.Thread(target=self._body, args=(mode, title_screen, initial_folder, initial_name), daemon=True, name='dialogue').start()

    def _body(self, mode, title_screen, folder, name_str):
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as ex:
            self.unavailable = True; self.error = repr(ex); self.result = []; return
        root = None
        try:
            root = tk.Tk(); root.withdraw()
            try: root.attributes('-topmost', True)
            except Exception: pass
            kw = dict(parent=root, title=title_screen)
            if folder and os.path.isdir(folder): kw['initialdir'] = folder
            if mode == 'save':
                p = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[(tr('saves.zip_archive'), '*.zip')], initialfile=name_str or default_export_name(), **kw)
                self.result = [p] if p else []
            else:
                ps = filedialog.askopenfilenames(filetypes=[(tr('saves.saves_zip_data_dat_state'), '*.zip *.dat *.dqs'), (tr('saves.all_files'), '*.*')], **kw)
                self.result = list(ps) if ps else []
        except Exception as ex:
            self.unavailable = True; self.error = repr(ex); self.result = []
        finally:
            try:
                if root is not None: root.destroy()
            except Exception: pass
