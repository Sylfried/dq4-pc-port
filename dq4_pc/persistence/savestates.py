"""Savestates: everything that keeps the game alive, at a moment between two frames.

The original engine runs in the emulator (emu_core): its state = memory (heap, data, modified pages of the library) + a few
loader counters. To this is added what the viewer decoded from the packets (State: camera, sprites, fades...) and the memory of the menu windows
(Interface). A state weighs a few hundred KB compressed; the stack is not kept (it is empty between two engine calls).

File: b'DQ4ETAT1' | size + JSON of the info | size + PNG of the thumbnail | compressed pickle (zlib).
The states contain NO game file: they only work with the APK that produced them (same version of the library)."""
import hashlib, io, json, os, pickle, struct, time, zlib

from dq4_pc.persistence import write_dir as WD
from dq4_pc.core.legacy_state import renamed_file, renamed_info, renamed_python, renamed_viewer

# Old module names (before the tidy-up: everything was flat in dq4_pc) -> current names: the savestates saved before this date
# keep the module name `moteur` (or another) in their pickle; they are read back without changing them.
OLD_MODULES = {
    'emu_core': 'dq4_pc.core.emu_core', 'moteur': 'dq4_pc.core.engine', 'pktlog': 'dq4_pc.core.pktlog', 'rencontres': 'dq4_pc.core.encounters',
    'priorite_jeu': 'dq4_pc.core.game_priority', 'suivi_charge': 'dq4_pc.core.load_tracking', 'pose_couchee': 'dq4_pc.core.lying_pose', 'historique': 'dq4_pc.core.history',
    'effet_combat': 'dq4_pc.battle.battle_effect', 'battle_speed': 'dq4_pc.battle.battle_speed', 'historique_combat': 'dq4_pc.battle.battle_history',
    'donnees': 'dq4_pc.world.data', 'fld': 'dq4_pc.world.fld', 'fbx': 'dq4_pc.world.fbx', 'hd': 'dq4_pc.world.hd', 'objets_carte': 'dq4_pc.world.map_objects',
    'decors_plats': 'dq4_pc.world.flat_sceneries', 'contours_decor': 'dq4_pc.world.scenery_outlines', 'teinte_carte': 'dq4_pc.world.map_tint',
    'postfx': 'dq4_pc.render.postfx', 'ciel_titre': 'dq4_pc.render.title_sky',
    'ui_menu': 'dq4_pc.menus.ui_menu', 'pause': 'dq4_pc.menus.pause', 'ui_historique': 'dq4_pc.menus.ui_history', 'hud_mobile': 'dq4_pc.menus.hud_mobile',
    'ecran_sauvegardes': 'dq4_pc.menus.saves_screen', 'avant_partie': 'dq4_pc.menus.pre_game', 'saisie_nom': 'dq4_pc.menus.name_entry',
    'reglages': 'dq4_pc.persistence.settings', 'sauvegardes': 'dq4_pc.persistence.saves', 'etats': 'dq4_pc.persistence.savestates',
    'entrees': 'dq4_pc.window.inputs', 'ecrans': 'dq4_pc.window.screens', 'son': 'dq4_pc.sound',
    'dq4_pc.noyau.moteur': 'dq4_pc.core.engine',       # savestates saved between the tidy-up and the switch to English
}
# Old class names (same date): `Etat` became `State`.
OLD_CLASSES = {'Etat': 'State'}


# Whitelist of the classes allowed when reading a savestate: a `.dqs` received from another person must not be able to execute code on
# load. A pickle can call any function of an importable module (os.system, eval...); only the data types that `snapshot` / `write` writes are accepted: the port's
# two classes (`State`, `Interface`), the basic containers, numpy arrays (both namespaces, `numpy.core` before numpy 2 and `numpy._core` since) and three `collections`
# containers. Survey done on real savestates (world, town, battle): nothing else.
ALLOWED_CLASSES = {
    'dq4_pc.core.engine': {'State', 'Interface'},
    'builtins': {'bool', 'bytearray', 'bytes', 'complex', 'dict', 'float', 'frozenset', 'int', 'list', 'range', 'set', 'slice', 'str', 'tuple'},
    'collections': {'OrderedDict', 'defaultdict', 'deque'},
    'numpy': {'dtype', 'ndarray'},
    'numpy.core.multiarray': {'_reconstruct', 'scalar'}, 'numpy._core.multiarray': {'_reconstruct', 'scalar'},
    'numpy.core.numeric': {'_frombuffer'}, 'numpy._core.numeric': {'_frombuffer'},
}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        module = OLD_MODULES.get(module, module)
        name = OLD_CLASSES.get(name, name) if module == 'dq4_pc.core.engine' else name
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
    from dq4_pc.core import engine
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
                               'fldobj': m.fldobj, 'grid': m._grid, 'grid_frame': m._grid_frame, 'msgs_ui': m.msgs_ui, 'end_roll': m.end_roll}, protocol=pickle.HIGHEST_PROTOCOL)
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
    m._grid = p['grid']; m._grid_frame = p['grid_frame']; m.msgs_ui = p['msgs_ui']
    m.end_roll = p.get('end_roll')                      # the end of the game under way (credits, "The End"); a savestate saved by an older version has none
    m.fbx_playing = [k for k, v in sorted(m.state.fbx.items()) if v.get('anim')]          # 3D model animations of the loaded state: the engine waits for their end (setMotionEnd); the list of the game before the load
                                                                  # named other models, so an effect saved while playing stayed on screen; a finished one gets its end at the next step
    m.reapply_fixes()                                    # original hero speeds (a savestate saved by an old version during a run contains them inflated), "Settings" button -> Pause menu (a savestate saved
                                                                  # before this redirection put the original instruction back), widened places window and "Sauv. cloud" removed (same: the original image is reloaded above)
    m.pk.begin()
    return viewer


def write(path, d, info, thumbnail_png=b''):
    """Saves the state `d` to `path`, the same way as saves and adventure logs (`write_dir.atomic_write`): temporary file, `fsync`, replacement in one go, TWO tries, and the `.tmp` removed
    if it fails. Before, the write was atomic but without fsync or retry, and a half-written `.tmp` stayed next to the state when the disk was full or an antivirus locked the file
    (common on Windows) —. Raises the error of the last attempt, as before: the caller displays "echec d'enregistrement" and the old state stays intact."""
    info = dict(info, date=time.strftime('%Y-%m-%d %H:%M:%S'), version=VERSION)
    ent = json.dumps(info).encode('utf-8')
    raw = b''.join((MAGIC, struct.pack('<I', len(ent)), ent, struct.pack('<I', len(thumbnail_png)), thumbnail_png,
                    zlib.compress(pickle.dumps(d, protocol=pickle.HIGHEST_PROTOCOL), 3)))          # (a state weighs 0.3 to 0.5 MB: holding it in memory while it is written costs nothing)
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
