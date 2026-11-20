"""Test of the reading of a settings.json written BEFORE its keys were in English: every setting, action id and button id is carried over under its new name,
nothing is lost, the new form wins when both are present, and the file is rewritten in English at the next save.

python3 tests/test_settings_migration.py
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import language as LG
from dq456_pc.persistence import settings as RG

# A file as the version saved it: all the keys, each with a value that is not the default.
OLD_FILE = {
    'langue': 'systeme', 'mode_sprites': 1, 'mode_fenetre': 1, 'msaa': 2, 'echelle_rendu': 1.5, 'nettete': 0.4, 'luminosite': 1.2, 'infos': True,
    'son': False, 'volume_musique': 0.3, 'volume_bruitages': 0.4, 'volume_general': 0.5, 'volume_jingles': 0.6, 'volume_interface': 0.7,
    'musique_active': False, 'jingles_actifs': False, 'bruitages_actifs': False, 'interface_active': False, 'vitesse_texte': 8.0, 'resolution': [1600, 900],
    'camera_inverser_gd': True, 'vignette': 0.5, 'vitesse_accel': 3.0, 'vitesse_combat': 2.0, 'historique_favoris_seuls': True, 'soin_niveau': True,
    'grille_edition': False, 'boutons': False, 'croix': False, 'croix_taille': 1.5, 'barre_rotation': False, 'boutons_taille': 1.4, 'boutons_aimant': False,
    'interface_fenetres': {'msg': [1.2, 0.0, 0.1]}, 'boutons_pos': {'carte': [2, 2], 'discussion': [3, 3], 'croix': [20, 9]},
    'bouton_vitesse': False, 'bouton_vitesse_taille': 1.3, 'bouton_vitesse_pos': [4.0, 5.0], 'interface_v': 2, 'interface_masquees': ['boutons', 'bouton_vitesse', 'msg'],
    'touches_v': 5, 'touches': {'haut': ['I', None], 'bas': ['K', None], 'gauche': ['J', None], 'droite': ['L', None], 'cam_haut': ['T', None], 'cam_bas': ['G', None],
                                'cam_gauche': ['F', None], 'cam_droite': ['H', None], 'carte': ['N', None], 'discussion': ['C', None], 'historique': ['Y', None],
                                'infos': ['F2', None], 'modif': ['X', None], 'vit_combat': ['B', None], 'menu': ['RETURN', None], 'accel': ['LSHIFT', None]},
    'manette': {'haut': 'PAD_UP', 'carte': 'PAD_BACK', 'discussion': 'PAD_Y', 'historique': 'PAD_R3', 'infos': 'PAD_L3', 'modif': 'PAD_RB', 'vit_combat': 'PAD_LT'},
}
# old key -> (new key, expected value); the nested dictionaries are checked apart
FLAT = {
    'langue': ('language', 'system'), 'mode_sprites': ('sprite_mode', 1), 'mode_fenetre': ('window_mode', 1), 'echelle_rendu': ('render_scale', 1.5), 'nettete': ('sharpness', 0.4),
    'luminosite': ('brightness', 1.2), 'infos': ('info', True), 'son': ('sound', False), 'volume_musique': ('music_volume', 0.3), 'volume_bruitages': ('sfx_volume', 0.4),
    'volume_general': ('master_volume', 0.5), 'volume_jingles': ('jingle_volume', 0.6), 'volume_interface': ('interface_volume', 0.7), 'musique_active': ('music_enabled', False),
    'jingles_actifs': ('jingles_enabled', False), 'bruitages_actifs': ('sfx_enabled', False), 'interface_active': ('interface_enabled', False), 'vitesse_texte': ('text_speed', 8.0),
    'camera_inverser_gd': ('camera_invert_lr', True), 'vitesse_accel': ('accel_speed', 3.0), 'vitesse_combat': ('battle_speed', 2.0), 'historique_favoris_seuls': ('history_favorites_only', True),
    'soin_niveau': ('level_up_heal', True), 'grille_edition': ('editor_grid', False), 'boutons': ('buttons', False), 'croix': ('dpad', False), 'croix_taille': ('dpad_size', 1.5),
    'barre_rotation': ('rotation_bar', False), 'boutons_taille': ('buttons_size', 1.4), 'boutons_aimant': ('buttons_snap', False), 'bouton_vitesse': ('speed_button', False),
    'bouton_vitesse_taille': ('speed_button_size', 1.3), 'bouton_vitesse_pos': ('speed_button_pos', [4.0, 5.0]),
}


def load(content):
    f = os.path.join(tempfile.mkdtemp(prefix='rg_test_'), 'settings.json')
    with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
    return RG.Settings(f), f


class Migration(unittest.TestCase):
    def test_the_table_covers_every_old_setting(self):
        for old, (new, _) in FLAT.items(): self.assertEqual(RG.LEGACY_KEYS[old], new, old)
        self.assertTrue(set(RG.LEGACY_KEYS.values()) - {'gamepad'} <= set(RG.DEFAULT), 'a new name that is not a setting')          # ('gamepad': the single binding, read into `gamepads`)
        self.assertFalse(set(RG.LEGACY_KEYS) & set(RG.DEFAULT), 'an old name is still a setting')

    def test_every_setting_is_carried_over(self):
        r, _ = load(OLD_FILE)
        for old, (new, value) in FLAT.items():
            self.assertEqual(r[new], value, '%s -> %s' % (old, new))
        self.assertEqual(r['interface_windows']['msg'], [1.2, 0.0, 0.1])
        self.assertEqual(r['buttons_pos'], {'map': [2, 2], 'chat': [3, 3], 'dpad': [20, 9]})
        self.assertEqual(r['interface_hidden'], ['buttons', 'speed_button', 'msg'])
        self.assertEqual(r['msaa'], 2); self.assertEqual(r['resolution'], [1600, 900])

    def test_keys_and_gamepad_action_ids(self):
        r, _ = load(OLD_FILE)
        k = r['keys']
        self.assertEqual((k['up'][0], k['down'][0], k['left'][0], k['right'][0]), ('I', 'K', 'J', 'L'))
        self.assertEqual((k['cam_left'][0], k['cam_right'][0]), ('F', 'H')); self.assertNotIn('cam_up', k); self.assertNotIn('cam_down', k)          # (the up / down arrow actions are gone, their old keys with them)
        self.assertEqual((k['map'][0], k['chat'][0], k['info'][0], k['modifier'][0], k['battle_speed'][0]), ('N', 'C', 'F2', 'X', 'B')); self.assertNotIn('history', k)          # (the History key is gone)
        pad = r['gamepad']
        self.assertEqual((pad['up'], pad['map'], pad['chat'], pad['info'], pad['modifier'], pad['battle_speed']), (['PAD_LS_UP', 'PAD_UP'], 'PAD_BACK', 'PAD_Y', 'PAD_L3', 'PAD_RB', 'PAD_LT')); self.assertNotIn('history', pad)          # (the left stick joins the d-pad: it was the same input)
        self.assertTrue(set(k) <= set(RG.DEFAULT_KEYS) and set(RG.DEFAULT_KEYS) <= set(k))

    def test_no_french_key_is_left_and_the_file_is_rewritten_in_english(self):
        r, path = load(OLD_FILE); r.store()
        with open(path, encoding='utf-8') as f: saved = json.load(f)
        self.assertFalse(set(saved) & set(RG.LEGACY_KEYS), set(saved) & set(RG.LEGACY_KEYS))
        self.assertFalse(set(saved['keys']) & set(RG.LEGACY_ACTIONS) - set(RG.DEFAULT_KEYS), 'French action id')
        for fam in saved['gamepads'].values(): self.assertFalse(set(fam) & set(RG.LEGACY_ACTIONS) - set(RG.DEFAULT_KEYS))
        self.assertEqual(RG.Settings(path).v, r.v, 'what is saved is read back identically')

    def test_the_new_form_wins(self):
        r, _ = load({'son': True, 'sound': False, 'keys_version': 5, 'touches': {'haut': ['I', None]}, 'keys': {'up': ['O', None]}})
        self.assertFalse(r['sound']); self.assertEqual(r['keys']['up'][0], 'O')

    def test_language_read_before_the_settings(self):
        for content, wanted in (({'langue': 'systeme'}, 'system'), ({'langue': 'en'}, 'en-us'), ({'language': 'fr'}, 'fr-fr'), ({'langue': 'systeme', 'language': 'en'}, 'en-us'), ({'language': 'zh-tw'}, 'zh-tw'), ({'langue': 'xx'}, 'system')):
            _, path = load(content); self.assertEqual(LG.read_setting(path), wanted, content)

    def test_old_legacy_migrations_still_work_after_the_renaming(self):
        r, _ = load({'boutons': True, 'boutons_pos': {'combat': [7, 3.5]}, 'boutons_taille': 1.2})          # before the speed button had its own settings
        self.assertEqual((r['speed_button'], r['speed_button_pos'], r['speed_button_size']), (True, [7, 3.5], 1.2)); self.assertNotIn('combat', r['buttons_pos'])
        r, _ = load({'plein_ecran': True}); self.assertEqual(r['window_mode'], 1)
        r, _ = load({'vitesse_course': 3.0}); self.assertEqual(r['accel_speed'], 3.0)


class CameraKeys(unittest.TestCase):
    """v8 -> v9: the camera on Q / E (A / E on an AZERTY keyboard) with the arrows as second keys; previous / next page R / T and the vehicle command F free those places.
    Only the keys still at their old default change."""
    def azerty(self):
        letters = {0x11: 'Z', 0x1E: 'Q', 0x1F: 'S', 0x20: 'D', 0x10: 'A', 0x12: 'E'}
        old = (RG.windows_letter, {a: list(v) for a, v in RG.DEFAULT_KEYS.items()})
        RG.windows_letter = letters.get; RG.DEFAULT_KEYS.update({a: [n, RG.DEFAULT_KEYS[a][1]] for a, n in RG.layout_keys(letters.get).items()})
        def restore(): RG.windows_letter = old[0]; RG.DEFAULT_KEYS.clear(); RG.DEFAULT_KEYS.update(old[1])
        self.addCleanup(restore)

    V8_AZERTY = {'up': ['Z', None], 'left': ['Q', None], 'down': ['S', None], 'right': ['D', None], 'cam_left': ['LEFT', None], 'cam_right': ['RIGHT', None], 'L': ['A', None], 'R': ['R', None], 'extra': ['E', None]}

    def test_old_defaults_move(self):
        self.azerty()
        self.assertEqual((RG.DEFAULT_KEYS['cam_left'], RG.DEFAULT_KEYS['cam_right']), (['A', 'LEFT'], ['E', 'RIGHT']))
        r, _ = load({'keys_version': 8, 'keys': dict(self.V8_AZERTY)})
        self.assertEqual({a: r['keys'][a] for a in ('cam_left', 'cam_right', 'L', 'R', 'extra', 'left', 'up')},
                         {'cam_left': ['A', 'LEFT'], 'cam_right': ['E', 'RIGHT'], 'L': ['R', None], 'R': ['T', None], 'extra': ['F', None], 'left': ['Q', None], 'up': ['Z', None]})
        self.assertEqual(r['keys_version'], RG.DEFAULT['keys_version'])
        every = [n for ts in r['keys'].values() for n in ts if n]; self.assertEqual(len(every), len(set(every)))          # (a key serves one action)

    def test_keys_the_player_chose_stay(self):
        self.azerty()
        keys = dict(self.V8_AZERTY, cam_left=['J', None], extra=['G', None], L=['A', 'P'])
        r, _ = load({'keys_version': 8, 'keys': keys})
        self.assertEqual({a: r['keys'][a] for a in ('cam_left', 'cam_right', 'L', 'R', 'extra')},
                         {'cam_left': ['J', None], 'cam_right': ['E', 'RIGHT'], 'L': ['A', 'P'], 'R': ['T', None], 'extra': ['G', None]})
        r, _ = load({'keys_version': 9, 'keys': dict(self.V8_AZERTY)})                                       # (already v9: nothing moves)
        self.assertEqual(r['keys']['cam_left'], ['LEFT', None])


if __name__ == '__main__':
    unittest.main()
