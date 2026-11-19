"""Scenery tint (packet 33, `cmd_map_color_rate`): which scenery groups receive it.

Unity side (read in libil2cpp, RVA 0xD14E44 `NativeManager.cmd_map_color_rate`, 0xCD79F4 `FldObject.update_material_color`, 0xCD811C `FldObject.save_org_color`):
  - the packet gives three floats r, g, b: `FldObject.m_color` = (r, g, b, 1) (world map: `Field.SetColor` = color of the tile material and of each symbol);
  - `FldObject.Update` calls `update_material_color` every frame: for each material of each Renderer of the map, `Material.color` = `_OrgColor` x `m_color`, EXCEPT if the material has no
    main texture or if the NAME of that texture contains "tz_" (lamps, candles, torches, waves, damaging floors: `tz_akari1`, `tz_rousoku1`, `tz_nami`, `tz_damg01`...): those
    keep `_OrgColor` alone (the day / evening tint does not touch them: they stay lit);
  - `_OrgColor` is NOT the asset's `_Color`: `FldObject.save_org_color` (RVA 0xCD811C, called at the end of `init_fld`) rereads `Material.color` then writes `_OrgColor` = (1, 1, 1, original alpha) for each
    material of each Renderer (s0 to s2 rewritten to 1.0 in the disassembly). So `Material.color` = (m_color.rgb, alpha) every frame: the RGB color `_Color` stored in the asset is never used in the game
    (point clarified by the coordinator; the fix to the map cache, `data.py`, is done on another branch: this module and the `tint` uniform assume a cache without that asset color);
  - the scenery shaders (`Custom/fld_normal`, `fld_atest`, `fld_trans`: texture x vertex color x `_Color`); the world map (`Custom/Field`: texture x `_Color`).
Characters (`Chara`), shadows, bubbles and the interface are not touched.

This module contains only what is needed to recognize the "tz_" groups: the map cache does not keep the texture name, only its identifier (path_id); the list of identifiers whose
name contains "tz_" is read from the data pack ONCE (half a second after the pack is loaded, which itself takes a few seconds) and kept in `tz_cles.json` in the cache.
"""
import json, os, threading

FILE = 'tz_cles.json'
MARK = 'tz_'                              # FldObject.update_material_color: Texture.name.IndexOf("tz_") != -1 -> no tint


def neutral_tint(t):
    """True if the tint changes nothing (1, 1, 1): nothing to do, the drawing stays identical to the pixel."""
    return t is None or (abs(t[0] - 1.0) < 1e-6 and abs(t[1] - 1.0) < 1e-6 and abs(t[2] - 1.0) < 1e-6)


def group_tz(lookup_key, ids_tz, names_pam=None):
    """True if the scenery group `lookup_key` (map cache key: texture identifier, ('tr', priority, key[, 'z']) for a transparent material ('z': with depth writing, Custom/fld_transz), ('pam', name, animation, event) for an animated palette)
    is a "tz_" texture and therefore not tinted. `ids_tz`: set of "tz_" texture identifiers (None = unknown: everything is tinted)."""
    if isinstance(lookup_key, tuple) and len(lookup_key) in (3, 4) and lookup_key[0] == 'tr': lookup_key = lookup_key[2]
    if isinstance(lookup_key, tuple) and len(lookup_key) >= 2 and lookup_key[0] == 'pam': return MARK in str(lookup_key[1])        # animated palette: textures "<name>.NNN" (FldObject.set_palette_data)
    return bool(ids_tz) and lookup_key in ids_tz


def read(cache):
    """Set of "tz_" identifiers recorded in the cache, None if it is not there (yet) or if it is unreadable."""
    try:
        with open(os.path.join(cache, FILE), encoding='utf-8') as fh: d = json.load(fh)
        return set(int(x) for x in d['ids'])
    except Exception:
        return None


def compute(data):
    """Reads the data pack (under `data`'s lock), collects the textures whose name contains "tz_", writes the cache file and returns the set. Raises an exception on failure."""
    with data._lock:
        loaded_here = data._env is None
        try:
            data.env()
            def name_str(o):
                try: return o.peek_name() or ''                  # reading the name only (recent UnityPy)
                except Exception: return o.read().m_Name         # otherwise full read of the object
            ids = sorted(o.path_id for o in data._objs.values() if o.type.name == 'Texture2D' and MARK in name_str(o))
        finally:
            if loaded_here: data.free_up()                  # the 800 MB are released if we were the ones who read the pack
    f = os.path.join(data.cache, FILE)
    with open(f + '.tmp', 'w', encoding='utf-8') as fh: json.dump({'ids': ids, 'marque': MARK}, fh)
    os.replace(f + '.tmp', f)
    return set(ids)


class TzKeys:
    """Set of "tz_" identifiers, read from the cache or computed as a background task; `ids()` returns None until it is ready (the scenery is then fully tinted: the lamps
    light up again as soon as the list arrives, a few seconds, once only)."""
    def __init__(self, data, log=print):
        self.data = data; self.log = log; self._ids = None; self._trial = False; self._thread = None

    def ids(self):
        if self._ids is not None: return self._ids
        if not self._trial:
            self._trial = True
            self._ids = read(self.data.cache)
            if self._ids is None:
                def worker():
                    try: self._ids = compute(self.data)
                    except Exception as ex:
                        self.log('Map tint: "tz_" textures unreadable (%s): the whole map will be tinted' % str(ex)[:80]); self._ids = set()
                self._thread = threading.Thread(target=worker, daemon=True, name='tint-tz'); self._thread.start()
        return self._ids


# ------------------------------------------------------------------------------------------------------------------------------------------------------
# Background color of the battle sceneries (FETC block of the scenery's .map file)
#
# Unity side (read in libil2cpp): `FldObject.init_fld` reads the FETC block (FLD_MAP_ETC); its first field `bg_color` is read by `ChunkFile.readColor` (RVA
# 0xCCEC20: 4 bytes r, g, b, a divided by 255); `NativeManager.cmd_fld_load` (RVA 0xD11D64), last, calls `BackColor.SetColor(bg_color, 0)` (RVA 0xCC4364: same
# color at top and bottom, immediately). The engine sends NO background color in battle (no packet 8): a battle's background is therefore the `bg_color` of the
# loaded scenery, variant by variant (`_d`, `_e`, `_n`, `_dk`): it is what gives the sunset orange around the ground. (Towns, for their part, then receive a
# packet 8: `cmd_back_color` RVA 0xD14F44, alpha 1.) The FETC alpha is 0 in the 140 sceneries: no effect, the data pack's `BackColor` shader has no blending
# (Blend One Zero, ZTest Always, ZWrite Off): it writes the vertex color as is.
# ------------------------------------------------------------------------------------------------------------------------------------------------------
BACKGROUNDS_FILE = 'backgrounds.json'
BACKGROUND_PREFIX = 'btl'                      # battle sceneries (btl_*, btlc*, btld*, btls*, btlt*, btlm*, btly*)


def fetc_background(raw):
    """Background color (r, g, b) as floats 0 to 1 of the FETC block of a scenery .map file (FLD_MAP_ETC.bg_color: bytes 8 to 10 of the block, after 'FETC' and its size), or None if there is no block."""
    from dq456_pc.world import fld
    return fld.background(raw)


def read_backgrounds(cache):
    """{scenery name: (r, g, b)} recorded in the cache, None if it is not there (yet) or if it is unreadable."""
    try:
        with open(os.path.join(cache, BACKGROUNDS_FILE), encoding='utf-8') as fh: d = json.load(fh)
        return {k: tuple(float(x) for x in v) for k, v in d['backgrounds'].items()}
    except Exception:
        return None


def compute_backgrounds(data):
    """Reads the data pack (under `data`'s lock), collects the FETC of each battle scenery, writes the cache file and returns the dictionary. Raises an exception on failure."""
    backgrounds = {}
    with data._lock:
        loaded_here = data._env is None
        try:
            data.env()
            for o in data._objs.values():
                if o.type.name != 'TextAsset': continue
                try: name_str = o.peek_name() or ''
                except Exception: name_str = o.read().m_Name
                if not (name_str.startswith(BACKGROUND_PREFIX) and name_str.endswith('.map')): continue
                t = o.read(); raw = t.m_Script.encode('utf-8', 'surrogateescape') if isinstance(t.m_Script, str) else bytes(t.m_Script)
                c = fetc_background(raw)
                if c is not None: backgrounds[name_str[:-4]] = c
        finally:
            if loaded_here: data.free_up()
    f = os.path.join(data.cache, BACKGROUNDS_FILE)
    with open(f + '.tmp', 'w', encoding='utf-8') as fh: json.dump({'backgrounds': backgrounds, 'prefix': BACKGROUND_PREFIX}, fh)
    os.replace(f + '.tmp', f)
    return backgrounds


class Backgrounds:
    """Background colors of the battle sceneries, read from the cache or computed as a background task (once, a few seconds); `color(name_str)` returns None until the list is ready or if the scenery is not
    in it: the caller then keeps its estimate (Game._battle_background)."""
    def __init__(self, data, log=print):
        self.data = data; self.log = log; self._backgrounds = None; self._trial = False; self._thread = None

    def color(self, name_str):
        if self._backgrounds is None and not self._trial:
            self._trial = True
            self._backgrounds = read_backgrounds(self.data.cache)
            if self._backgrounds is None:
                def worker():
                    try: self._backgrounds = compute_backgrounds(self.data)
                    except Exception as ex:
                        self.log('Battle scenery backgrounds unreadable (%s): background estimated' % str(ex)[:80]); self._backgrounds = {}
                self._thread = threading.Thread(target=worker, daemon=True, name='scenery-backgrounds'); self._thread.start()
        return (self._backgrounds or {}).get(name_str)
