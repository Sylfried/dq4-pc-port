"""Names of the savestates recorded before the code was in English (the French names stay HERE, nowhere else).

A savestate (`persistence/savestates.py`) is a pickle: the `State` and `Interface` objects keep their attribute names, and the dictionaries they hold keep their keys. Each
rename of the switch to English (05/11/2026: attributes; 10/11/2026: keys) is carried over on read by the functions below, which `State.__setstate__`,
`Interface.__setstate__` and `savestates.apply` call. Reading is idempotent: a state recorded since (English names) passes through as is, and when an old and a new name are
both present the new one wins. This module is the only one whose French keys must not be renamed (tests/test_legacy_names.py checks that the new names are the ones the code uses)."""

# Attributes of State / Interface (05/11/2026).
OLD_ATTRIBUTES = {
    'attente': 'waiting', 'attente_charge': 'load_wait', 'cam_down': 'cam_down', 'cam_cible': 'cam_target', 'cam_libre': 'cam_free',
    'carte': 'game_map', 'cartes_chargees': 'loaded_maps', 'champ': 'field', 'champ_echelle': 'field_scale', 'chargement': 'loading',
    'degats': 'damage', 'dort_haut': 'sleeping_height', 'ecran_noir': 'black_screen', 'effet': 'effect', 'effet_ecran': 'screen_effect',
    'fen_entree': 'entry_window', 'fen_retour': 'return_window', 'flottants': 'floats', 'fond': 'background', 'fond_bas': 'bottom_background',
    'fond_haut': 'top_background', 'fondu': 'fade', 'fondu_fond': 'background_fade', 'garde_trans': 'transition_guard', 'icones': 'icons',
    'maillages': 'meshes', 'maillages_vus': 'meshes_seen', 'mesh_etat': 'mesh_state', 'modeles': 'models', 'monde': 'world', 'musique': 'music',
    'objets_cmd': 'object_cmds', 'ordre': 'order', 'pad_clignote': 'pad_blink', 'partie': 'part', 'rapport_fondu': 'fade_ratio', 'sons': 'sounds',
    'symboles': 'symbols', 'systeme': 'system', 'teinte': 'tint', 'vitesse_fondu': 'fade_speed',
}


def renamed_attributes(state):
    """Attribute dictionary read from a pickle -> the same one with the current names."""
    return {OLD_ATTRIBUTES.get(k, k): v for k, v in state.items()}


def rename_keys(d, mapping):
    """Renames in place the keys of dictionary `d` (the new name wins if both exist); anything that is not a dictionary is left alone. -> d"""
    if isinstance(d, dict):
        for old, new in mapping.items():
            if old in d: v = d.pop(old); d.setdefault(new, v)
    return d


def rename_values(d, mapping):
    """The same for every value of the dictionary `d` that is itself a dictionary (slot -> {...})."""
    if isinstance(d, dict):
        for v in d.values(): rename_keys(v, mapping)
    return d


# Keys of the dictionaries held by State (10/11/2026). attribute -> {old key: new key}; VALUE_KEYS: the attribute is a dictionary of dictionaries (slot -> {...}).
FADE_KEYS = {'fin': 'end', 'pas': 'step', 'noir': 'black', 'combat': 'battle'}
STATE_KEYS = {
    'fade': FADE_KEYS, 'background_fade': FADE_KEYS, 'effect': {'duree': 'duration'}, 'field': {'tuiles': 'tiles'},
    'screen_effect': {'duree': 'duration', 'images': 'frames', 'genre': 'kind', 'matin': 'morning', 'noir': 'black', 'fondu': 'fade_in'},
}
STATE_VALUE_KEYS = {
    'sprites': {'vis': 'visible', 'cree': 'created', 'dort': 'sleeping', 'dort_rot': 'sleeping_rot', 'ech': 'scale', 'ombre': 'shadow', 'ombre_sep': 'shadow_separate',
                'ombre_pos': 'shadow_pos', 'ombre_a': 'shadow_alpha', 'ombre_champ': 'shadow_field'},
    'symbols': {'vis': 'visible', 'genre': 'kind'}, 'fbx': {'vis': 'visible'}, 'mesh_state': {'vis': 'visible'},
}
KIND_VALUES = {'lampe': 'lamp'}                         # screen_effect['kind']


def renamed_dict_keys(attrs):
    """Attributes of a State (already renamed by renamed_attributes) -> the same ones, the keys of the dictionaries they hold brought to their current names."""
    for name, mapping in STATE_KEYS.items(): rename_keys(attrs.get(name), mapping)
    for name, mapping in STATE_VALUE_KEYS.items(): rename_values(attrs.get(name), mapping)
    ef = attrs.get('screen_effect')
    if isinstance(ef, dict) and 'kind' in ef: ef['kind'] = KIND_VALUES.get(ef['kind'], ef['kind'])
    if 'object_cmds' in attrs: attrs['object_cmds'] = [('map',) if c == ('carte',) else c for c in attrs['object_cmds']]
    return attrs


# Keys of the dictionaries held by Interface (10/11/2026): `msg` (message window) and `f` (port -> menu window).
MSG_KEYS = {'qui': 'speaker', 'qui_att': 'speaker_pending'}
WINDOW_KEYS = {'vis': 'visible', 'cases': 'cells', 'indic': 'indicators', 'dispo': 'layout', 'att': 'pending', 'ordre': 'order', 'entree': 'input', 'ferme': 'closed',
               'listes': 'lists', 'plaq': 'plates', 'suite': 'next_list', 'grille': 'grid', 'dgt': 'damage_pending'}
PLATE_KEYS = {'nom': 'name', 'prm': 'params'}
PLATE_STAGES = {'nom': 'name', 'prm': 'params'}           # window['pending'] = (plate, stage that is waited for)


def renamed_interface_keys(attrs):
    """Attributes of an Interface (already renamed by renamed_attributes) -> the same ones, the keys of the dictionaries they hold brought to their current names."""
    rename_keys(attrs.get('msg'), MSG_KEYS)
    rename_values(attrs.get('f'), WINDOW_KEYS)
    for w in (attrs.get('f') or {}).values():
        if not isinstance(w, dict): continue
        rename_values(w.get('plates'), PLATE_KEYS)
        if isinstance(w.get('pending'), tuple) and len(w['pending']) == 2: w['pending'] = (w['pending'][0], PLATE_STAGES.get(w['pending'][1], w['pending'][1]))
    return attrs


# The state file itself (persistence/savestates.py, 10/11/2026): header, outer dictionary, `python` dictionary and `viewer` dictionary.
INFO_KEYS = {'lieu': 'location', 'carte': 'map', 'partie': 'part', 'images': 'frames'}                  # header (JSON) of the file
FILE_KEYS = {'fichiers': 'files'}
PYTHON_KEYS = {'etat': 'state', 'images': 'frames', 'grille': 'grid', 'grille_img': 'grid_frame'}
VIEWER_KEYS = {'objets_etat': 'object_states', 'objets_auto': 'auto_objects', 'objets_evt': 'event_objects', 'objets_sra': 'sra_clocks', 'carte_nom': 'map_name',
               'motif_n': 'pattern_n', 'motif_acc': 'acc_pattern', 'musique': 'music'}
# animated objects of the map (world/map_objects.py): state of an object, continuous animation, clock, motion / sequence read from the map
OBJECT_KEYS = {'mdl': 'model', 'mot': 'motion', 'seq': 'sequence', 'temps': 'time', 'tmot': 'motion_time', 'tseq': 'sequence_time', 'fini': 'finished'}
AUTO_KEYS = {'mot': 'motion', 'seq': 'sequence', 'hm': 'motion_clock', 'hs': 'sequence_clock'}
CLOCK_KEYS = {'delai': 'delay', 'rdelai': 'loop_delay', 'rep': 'loops', 'fin': 'end', 'temps': 'time', 'fini': 'finished'}
MOTION_KEYS = {'delai': 'delay', 'rdelai': 'loop_delay', 'fin': 'end', 'nom': 'name'}


def renamed_info(ent):
    """Header of a state file -> the same one with the current keys."""
    return rename_keys(ent, INFO_KEYS)


def renamed_file(d):
    """Outer dictionary of a state file (`read`) -> the same one with the current keys."""
    return rename_keys(d, FILE_KEYS)


def renamed_python(p):
    """`python` dictionary of a state file (the State, the Interface, the frames...) -> the same one with the current keys."""
    return rename_keys(p, PYTHON_KEYS)


def renamed_viewer(v):
    """`viewer` dictionary of a state file (animated objects of the map, music...) -> the same one with the current keys. None if there is none."""
    if not isinstance(v, dict): return v
    rename_keys(v, VIEWER_KEYS)
    states = v.get('object_states')
    for st in (states or {}).values():
        rename_keys(st, OBJECT_KEYS)
        if isinstance(st, dict):
            for k in ('motion', 'sequence'): rename_keys(st.get(k), MOTION_KEYS)
    for a in (v.get('auto_objects') or {}).values():
        rename_keys(a, AUTO_KEYS)
        if isinstance(a, dict):
            rename_keys(a, CLOCK_KEYS)                                    # (a very old format: a single clock for both animations, in the dictionary itself)
            for k in ('motion_clock', 'sequence_clock'): rename_keys(a.get(k), CLOCK_KEYS)
            for k in ('motion', 'sequence'): rename_keys(a.get(k), MOTION_KEYS)
    rename_values(v.get('sra_clocks'), CLOCK_KEYS)
    return v


def carry_over_file(folder, old, new):
    """Cache file whose name was in French (10/11/2026): `folder/old` is renamed `folder/new` if only the old one exists (nothing is rebuilt). -> path of `new`."""
    import os
    f_old, f_new = os.path.join(folder, old), os.path.join(folder, new)
    try:
        if os.path.exists(f_old) and not os.path.exists(f_new): os.replace(f_old, f_new)
    except OSError:
        pass                                               # (the old file stays where it is; the new one will be rebuilt)
    return f_new


# Favorites file of the message history (core/history.py), version 2 -> 3 (10/11/2026): keys and outcome words in English.
HISTORY_FILE_KEYS = {'suivant': 'next', 'favoris': 'favorites'}
HISTORY_ELEMENT_KEYS = {'nom': 'name', 'texte': 'text', 'ennemis': 'enemies', 'or': 'gold', 'issue': 'outcome', 'objets': 'objects'}
HISTORY_ENEMY_KEYS = {'nom': 'name', 'vaincus': 'defeated', 'fuis': 'fled', 'disparus': 'vanished'}
HISTORY_OUTCOMES = {'victoire': 'victory', 'fuite': 'escape', 'defaite': 'defeat'}


def renamed_history(d):
    """Content of a favorites file of version 2 (French keys) -> the same with the version 3 keys; the 'version' field is left to the caller. Anything unexpected is passed on
    untouched (the validation of History.load decides what is kept)."""
    if not isinstance(d, dict): return d
    rename_keys(d, HISTORY_FILE_KEYS)
    for e in d.get('favorites') if isinstance(d.get('favorites'), list) else ():
        if not isinstance(e, dict): continue
        rename_keys(e, HISTORY_ELEMENT_KEYS)
        if e.get('outcome') in HISTORY_OUTCOMES: e['outcome'] = HISTORY_OUTCOMES[e['outcome']]
        for k, keys in (('enemies', HISTORY_ENEMY_KEYS), ('objects', {'nom': 'name'})):
            for x in e.get(k) if isinstance(e.get(k), list) else (): rename_keys(x, keys)
    return d
