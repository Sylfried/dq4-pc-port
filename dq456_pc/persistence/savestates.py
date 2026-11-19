"""Savestates: everything that keeps the game alive, at a moment between two frames.

The original engine runs in the emulator (emu_core): its state = memory (heap, data, modified pages of the library) + a few
loader counters. To this is added what the viewer decoded from the packets (State: camera, sprites, fades...) and the memory of the menu windows
(Interface). A state weighs a few hundred KB compressed; the stack is not kept (it is empty between two engine calls).

File: b'DQ4ETAT1' | size + JSON of the info | size + PNG of the thumbnail | compressed pickle (zlib).
The states contain NO game file: they only work with the APK that produced them (same version of the library)."""
import hashlib, io, json, os, pickle, re, struct, time, zlib

from dq456_pc.persistence import write_dir as WD
from dq456_pc.core.legacy_state import renamed_file, renamed_info, renamed_python, renamed_viewer

# Old module names (before the tidy-up: everything was flat in dq456_pc) -> current names: the savestates saved before this date
# keep the module name `moteur` (or another) in their pickle; they are read back without changing them.
OLD_MODULES = {
    'emu_core': 'dq456_pc.core.emu_core', 'moteur': 'dq456_pc.core.engine', 'pktlog': 'dq456_pc.core.pktlog', 'rencontres': 'dq456_pc.core.encounters',
    'priorite_jeu': 'dq456_pc.core.game_priority', 'suivi_charge': 'dq456_pc.core.load_tracking', 'pose_couchee': 'dq456_pc.core.lying_pose', 'historique': 'dq456_pc.core.history',
    'effet_combat': 'dq456_pc.battle.battle_effect', 'battle_speed': 'dq456_pc.battle.battle_speed', 'historique_combat': 'dq456_pc.battle.battle_history',
    'donnees': 'dq456_pc.world.data', 'fld': 'dq456_pc.world.fld', 'fbx': 'dq456_pc.world.fbx', 'hd': 'dq456_pc.world.hd', 'objets_carte': 'dq456_pc.world.map_objects',
    'decors_plats': 'dq456_pc.world.flat_sceneries', 'contours_decor': 'dq456_pc.world.scenery_outlines', 'teinte_carte': 'dq456_pc.world.map_tint',
    'postfx': 'dq456_pc.render.postfx', 'ciel_titre': 'dq456_pc.render.title_sky',
    'ui_menu': 'dq456_pc.menus.ui_menu', 'pause': 'dq456_pc.menus.pause', 'ui_historique': 'dq456_pc.menus.ui_history', 'hud_mobile': 'dq456_pc.menus.hud_mobile',
    'ecran_sauvegardes': 'dq456_pc.menus.saves_screen', 'avant_partie': 'dq456_pc.menus.pre_game', 'saisie_nom': 'dq456_pc.menus.name_entry',
    'reglages': 'dq456_pc.persistence.settings', 'sauvegardes': 'dq456_pc.persistence.saves', 'etats': 'dq456_pc.persistence.savestates',
    'entrees': 'dq456_pc.window.inputs', 'ecrans': 'dq456_pc.window.screens', 'son': 'dq456_pc.sound',
    'dq4_pc.noyau.moteur': 'dq456_pc.core.engine',       # savestates saved between the tidy-up and the switch to English
}
OLD_PACKAGE, PACKAGE = 'dq4_pc.', 'dq456_pc.'                  # the package's name before it covered three games: `dq4_pc.core.engine` is read as `dq456_pc.core.engine`
# Old class names (same date): `Etat` became `State`.
OLD_CLASSES = {'Etat': 'State'}


# Whitelist of the classes allowed when reading a savestate: a `.dqs` received from another person must not be able to execute code on
# load. A pickle can call any function of an importable module (os.system, eval...); only the data types that `snapshot` / `write` writes are accepted: the port's
# two classes (`State`, `Interface`), the basic containers, numpy arrays (both namespaces, `numpy.core` before numpy 2 and `numpy._core` since) and three `collections`
# containers. Survey done on real savestates (world, town, battle): nothing else.
ALLOWED_CLASSES = {
    'dq456_pc.core.engine': {'State', 'Interface'},
    'builtins': {'bool', 'bytearray', 'bytes', 'complex', 'dict', 'float', 'frozenset', 'int', 'list', 'range', 'set', 'slice', 'str', 'tuple'},
    'collections': {'OrderedDict', 'defaultdict', 'deque'},
    'numpy': {'dtype', 'ndarray'},
    'numpy.core.multiarray': {'_reconstruct', 'scalar'}, 'numpy._core.multiarray': {'_reconstruct', 'scalar'},
    'numpy.core.numeric': {'_frombuffer'}, 'numpy._core.numeric': {'_frombuffer'},
}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        module = OLD_MODULES.get(module, module)
        if module.startswith(OLD_PACKAGE): module = PACKAGE + module[len(OLD_PACKAGE):]
        name = OLD_CLASSES.get(name, name) if module == 'dq456_pc.core.engine' else name
        if name not in ALLOWED_CLASSES.get(module, ()):
            raise pickle.UnpicklingError('state file refused: it asks for "%s.%s", which a state of the port never contains (file from elsewhere or damaged; it was not executed)' % (module, name))
        return super().find_class(module, name)


def _load(raw):
    """pickle.loads that also recognizes the old module names and refuses any class outside ALLOWED_CLASSES (nothing is executed: a booby-trapped file is rejected beforehand)."""
    return _Unpickler(io.BytesIO(raw)).load()

MAGIC = b'DQ4ETAT1'
VERSION = 1
PAGE = 4096


def lib_fingerprint(core):
    """Fingerprint of the engine library (image after relocation): a state only makes sense with the library that produced it."""
    return hashlib.sha256(bytes(core.elf.img)).hexdigest()[:16]


def apk_fingerprint(apk_folder):
    """The same fingerprint, computed from the APK files of a folder without starting the engine: the library is only loaded and relocated, which takes about 50 ms. It tells which game version (language) a state
    belongs to. None if the folder has no readable library."""
    import zipfile
    from dq456_pc.core import engine
    class Mute:
        def __call__(self, *a, **k): pass
        def __getattr__(self, name): return lambda *a, **k: None
    try:
        pack = os.path.join(apk_folder, 'split_UnityDataAssetPack.apk')
        lib = zipfile.ZipFile(os.path.join(apk_folder, 'split_config.arm64_v8a.apk')).read(engine.LIB_APK)
        return lib_fingerprint(engine.GameCore(lib, engine.T.ApkFs([pack]), Mute(), real_files={'/dq/assets.apk': pack}))
    except Exception:
        return None


class OtherEngine(ValueError):
    """The state was saved with another version of the engine library (another APK: the other language's, or an update). `lib_sha`: its fingerprint."""
    def __init__(self, lib_sha):
        super().__init__('state saved with another version of the engine library (different APK): it cannot be loaded')
        self.lib_sha = lib_sha


class OtherLanguage(OtherEngine):
    """The state belongs to the game version of the other language ('fr' or 'en'), whose APK files are in the folder of that language: loading it means switching the game to that language first."""
    def __init__(self, lib_sha, language):
        super().__init__(lib_sha); self.language = language


def check(m, d):
    """Raises OtherEngine if state `d` does not come from the library of engine `m` (nothing is touched). Savestates have no fingerprint: accepted."""
    if d.get('lib_sha') and d['lib_sha'] != lib_fingerprint(m.core): raise OtherEngine(d['lib_sha'])


def _modified_pages(core):
    """Library pages (data, patches) that differ from the image after relocation: [(number, bytes)]."""
    cur = core.mem(core.LIB_BASE, core.elf.size); ini = bytes(core.elf.img)
    n = (len(cur) + PAGE - 1) // PAGE
    return [(i, cur[i * PAGE:(i + 1) * PAGE]) for i in range(n) if cur[i * PAGE:(i + 1) * PAGE] != ini[i * PAGE:(i + 1) * PAGE]]


def snapshot(m, viewer=None):
    """State of engine `m` (Engine) -> serializable dictionary. To be called between two frames. `viewer`: additional serializable object (state of the map's animated objects...) returned by apply."""
    c = m.core
    ui = m.ui; obs, ui.obs = ui.obs, None
    try:
        python = pickle.dumps({'state': m.state, 'ui': ui, 'frames': m.frames, 'anims': list(m.anims), 'msg_visible': m.msg_visible, 'fielddata': m.fielddata,
                               'fldobj': m.fldobj, 'grid': m._grid, 'grid_frame': m._grid_frame, 'orient': getattr(m, '_orient', None), 'msgs_ui': m.msgs_ui, 'end_roll': m.end_roll}, protocol=pickle.HIGHEST_PROTOCOL)
    finally:
        ui.obs = obs
    return {
        'version': VERSION, 'lib_sha': lib_fingerprint(c),
        'heap': c.mem(c.HEAP_BASE, c.heap_ptr - c.HEAP_BASE), 'heap_ptr': c.heap_ptr,
        'data': c.mem(c.DATA_BASE, c.DATA_SIZE), 'tls': c.mem(c.TLS_BASE, c.TLS_SIZE), 'data_ptr': c.data_ptr,
        'lib': _modified_pages(c), 'next_file': c.next_file,
        'files': {h: {k: v for k, v in f.items() if k in ('name', 'pos', 'w', 'persist')} for h, f in c.files.items()},
        'python': python, 'viewer': pickle.dumps(viewer, protocol=pickle.HIGHEST_PROTOCOL),
    }


def apply(m, d):
    """Puts engine `m` back into state `d` -> `viewer` object given to snapshot. The resources tied to the window (original menu windows, textures) must be rebuilt by the caller (see Game.load_state)."""
    if d.get('version') != VERSION: raise ValueError('state from another version (%s)' % d.get('version'))
    c = m.core; uc = c.uc
    check(m, d)
    d = renamed_file(d); p = renamed_python(_load(d['python'])); viewer = renamed_viewer(_load(d['viewer'])) if d.get('viewer') else None            # EVERYTHING is read before writing anything into the engine: a damaged file leaves the game intact
    journal = m.journal() if getattr(m, 'journal_chosen', False) else None      # the adventure log chosen in this session (start menu, church) stays the church's log in cyan
    uc.mem_write(c.LIB_BASE, bytes(c.elf.img))
    for i, b in d['lib']: uc.mem_write(c.LIB_BASE + i * PAGE, b)
    if c.heap_ptr > d['heap_ptr']: uc.mem_write(c.HEAP_BASE + (d['heap_ptr'] - c.HEAP_BASE), bytes(c.heap_ptr - d['heap_ptr']))
    uc.mem_write(c.HEAP_BASE, d['heap']); c.heap_rewind(d['heap_ptr'])          # (the pointer moves back, and the pool of returned blocks forgets everything that lived above it)
    uc.mem_write(c.DATA_BASE, d['data']); uc.mem_write(c.TLS_BASE, d['tls']); c.data_ptr = d['data_ptr']; c.next_file = d['next_file']
    c.files = {}
    for h, f in d['files'].items():             # open files: they are tracked only if the engine had opened some (not seen between two frames until now)
        m.log('savestate: open file not restored (%s)' % (f.get('name'),))
    old = m.ui.obs
    m.state = p['state']; m.ui = p['ui']; m.ui.obs = old
    if not hasattr(m.ui, 'damage'): m.ui.damage = []              # savestate saved by an older version (before the damage numbers)
    m.frames = p['frames']; m.anims = p['anims']; m.msg_visible = p['msg_visible']; m.fielddata = p['fielddata']; m.fldobj = p['fldobj']
    m._grid = p['grid']; m._grid_frame = p['grid_frame']; m._orient = p.get('orient'); m.msgs_ui = p['msgs_ui']
    m.end_roll = p.get('end_roll')                      # the end of the game under way (credits, "The End"); a savestate saved by an older version has none
    m.fbx_playing = [k for k, v in sorted(m.state.fbx.items()) if v.get('anim')]          # 3D model animations of the loaded state: the engine waits for their end (setMotionEnd); the list of the game before the load
                                                                  # named other models, so an effect saved while playing stayed on screen; a finished one gets its end at the next step
    m.reapply_fixes()                                    # original hero speeds (a savestate saved by an old version during a run contains them inflated), "Settings" button -> Pause menu (a savestate saved
                                                                  # before this redirection put the original instruction back), widened places window and "Sauv. cloud" removed (same: the original image is reloaded above)
    if journal is not None: m.set_journal(journal)
    m.pk.begin()
    return viewer


GAME_SYMBOL, UID_OFFSET = '_ZN6status6g_GameE', 8                # status::g_Game + 8: the game's unique ID (Engine.game_uid)


def game_folder(folder, uid):
    """The savestates of the game `uid` (its unique ID, kept in the adventure log): <savestates>/<ID in 8 hexadecimal digits>; no ID: the folder itself."""
    return folder if uid is None else os.path.join(folder, '%08x' % uid)


def journal_games(paths):
    """The games the adventure logs hold (`paths`: {name: path}, saves.effective_files): {1 .. 5 (data<n>.dat): game ID}; an empty or deleted bank: absent.
    None if one of them cannot be read or is not an adventure log of the game: what it holds is unknown (nothing is to be deleted then)."""
    from dq456_pc.persistence import logfile_format as LF
    out = {}
    for name_str, p in (paths or {}).items():
        m = re.fullmatch(r'data([1-5])\.dat', name_str.lower())
        if not m: continue
        try:
            with open(p, 'rb') as f: uid = LF.game_uid(f.read())
        except FileNotFoundError: continue                                          # (no file: no game there)
        except (OSError, LF.Unreadable): return None
        if uid is not None: out[int(m.group(1))] = uid
    return out


def game_folders(folder):
    """{game ID: its savestates folder} of the savestates folder (sub-folders named by an 8-digit hexadecimal ID)."""
    try: names = os.listdir(folder)
    except OSError: return {}
    return {int(n, 16): os.path.join(folder, n) for n in names if re.fullmatch(r'[0-9a-f]{8}', n) and os.path.isdir(os.path.join(folder, n))}


def drop_game(folder, uid, log=print):
    """Deletes the savestates of the game `uid` (its folder, game_folder): no adventure log holds that game any more. -> True if there were some."""
    import shutil
    d = game_folder(folder, uid)
    if uid is None or d == folder or not os.path.isdir(d): return False
    try: shutil.rmtree(d); return True
    except OSError as ex: log('savestates of game %08x not deleted: %s' % (uid, ex)); return False


def uid_of(d, core):
    """The unique ID of the game a state `d` holds (status::g_Game + 8 in its library pages), or None (state of another library: the address may differ)."""
    if d.get('lib_sha') != lib_fingerprint(core): return None
    a = core.export(GAME_SYMBOL)
    if not a: return None
    off = a - core.LIB_BASE + UID_OFFSET; pages = dict(d.get('lib') or ()); img = bytes(core.elf.img)
    raw = bytes((pages[i // PAGE][i % PAGE] if i // PAGE in pages else img[i]) for i in range(off, off + 4))
    return struct.unpack('<I', raw)[0]


def sort_by_game(folder, core, log=print):
    """States saved before the states of each game (<savestates>/state_NN.dqs): each goes into the folder of its game (game_folder), its number kept (or the first free one).
    A state of another library (the game's other language) stays where it is, until that version sorts it. -> number of states moved."""
    import glob
    moved = 0
    for p in sorted(glob.glob(os.path.join(folder, 'state_??.dqs'))):
        try: uid = uid_of(read(p), core)
        except Exception as ex: log('savestate %s not sorted: %s' % (os.path.basename(p), ex)); continue
        if uid is None: continue
        dest = game_folder(folder, uid); os.makedirs(dest, exist_ok=True)
        name_str = os.path.basename(p)
        if os.path.exists(os.path.join(dest, name_str)):
            name_str = next((n for n in ('state_%02d.dqs' % i for i in range(1, 10)) if not os.path.exists(os.path.join(dest, n))), None)
            if name_str is None: continue
        try: os.replace(p, os.path.join(dest, name_str)); moved += 1
        except OSError as ex: log('savestate %s not sorted: %s' % (os.path.basename(p), ex))
    return moved


def write(path, d, info, thumbnail_png=b''):
    """Saves the state `d` to `path`, the same way as saves and adventure logs (`write_dir.atomic_write`): temporary file, `fsync`, replacement in one go, TWO tries, and the `.tmp` removed
    if it fails. Before, the write was atomic but without fsync or retry, and a half-written `.tmp` stayed next to the state when the disk was full or an antivirus locked the file
    (common on Windows) —. Raises the error of the last attempt, as before: the caller displays "echec d'enregistrement" and the old state stays intact."""
    info = dict(info, date=time.strftime('%Y-%m-%d %H:%M:%S'), version=VERSION)
    ent = json.dumps(info).encode('utf-8')
    raw = b''.join((MAGIC, struct.pack('<I', len(ent)), ent, struct.pack('<I', len(thumbnail_png)), thumbnail_png,
                    zlib.compress(pickle.dumps(d, protocol=pickle.HIGHEST_PROTOCOL), 3)))          # (a state weighs 0.3 to 0.5 MB: holding it in memory while it is written costs nothing)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    ex = WD.atomic_write(os.path.abspath(path), raw)
    if ex is not None: raise ex


def info(path):
    """-> (info, PNG thumbnail) of a state file, without reading the state itself; None if the file does not exist or is not valid."""
    try:
        with open(path, 'rb') as f:
            if f.read(len(MAGIC)) != MAGIC: return None
            n, = struct.unpack('<I', f.read(4)); ent = renamed_info(json.loads(f.read(n).decode('utf-8')))
            k, = struct.unpack('<I', f.read(4)); png = f.read(k)
        return ent, png
    except Exception:
        return None


def read(path):
    """-> state dictionary (to pass to apply)."""
    with open(path, 'rb') as f:
        if f.read(len(MAGIC)) != MAGIC: raise ValueError('this is not a state file of this port')
        n, = struct.unpack('<I', f.read(4)); f.read(n)
        k, = struct.unpack('<I', f.read(4)); f.read(k)
        return _load(zlib.decompress(f.read()))
