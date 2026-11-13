"""Test of the added settings (sound per category, text speed, battle scrolling, speeds x1 to x4): an old reglages.json remains valid (migration of the old sliders and of the old battle scrolling), absurd values are reset.

python3 tests/test_sound_text_settings.py
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.persistence import settings as RG


def load(content):
    f = os.path.join(tempfile.mkdtemp(prefix='rg_test_'), 'settings.json')
    with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
    return RG.Settings(f), f


class Settings(unittest.TestCase):
    def test_old_file(self):
        r, _ = load({'sound': False, 'music_volume': 0.4, 'sfx_volume': 0.7, 'keys_version': 4, 'sprite_mode': 2})
        self.assertEqual((r['sound'], r['music_volume'], r['sfx_volume']), (False, 0.4, 0.7))      # the old settings are kept
        self.assertEqual((r['master_volume'], r['jingle_volume'], r['interface_volume']), (1.0, 1.0, 1.0))
        self.assertTrue(all(r[k] for k in ('music_enabled', 'jingles_enabled', 'sfx_enabled', 'interface_enabled')))
        self.assertEqual((r['text_speed'], r['battle_speed']), (4.0, 1.0))      # = the behavior from before: Normal (original speed and messages)
        self.assertNotIn('defilement_force', r.v); self.assertNotIn('defilement_combat', r.v)
        self.assertNotIn('vitesse_camera', r.v); self.assertNotIn('vitesse_marche', r.v)

    def test_absurd_values(self):
        r, _ = load({'master_volume': 5, 'jingle_volume': -2, 'interface_volume': 'fort', 'music_enabled': 'oui', 'interface_enabled': None, 'battle_speed': 'vite',
                        'text_speed': 3.1, 'accel_speed': 'vite', 'vitesse_camera': True})
        self.assertEqual((r['master_volume'], r['jingle_volume'], r['interface_volume']), (1.0, 0.0, 1.0))
        self.assertIs(r['music_enabled'], True); self.assertIs(r['interface_enabled'], True); self.assertEqual(r['battle_speed'], 1.0)
        self.assertEqual(r['text_speed'], 4.0)
        self.assertEqual(r['accel_speed'], 1.5); self.assertNotIn('vitesse_camera', r.v)      # absurd values: the defaults (and the old camera speed is ignored)

    def test_text_speed_clamped_to_one_notch(self):
        for raw_value, notch in ((0.1, 0.5), (0.8, 1.0), (1.5, 2.0), (5.0, 4.0), (7.0, 8.0), (100.0, 16.0), (100000, 4000.0)):
            r, _ = load({'text_speed': raw_value}); self.assertEqual(r['text_speed'], notch, raw_value)

    def test_round_trip(self):
        r, f = load({})
        r['interface_volume'] = 0.35; r['jingles_enabled'] = False; r['text_speed'] = 16.0; r['battle_speed'] = 0.0
        r['accel_speed'] = 3.5
        r.store()
        r2 = RG.Settings(f)
        self.assertEqual((r2['interface_volume'], r2['jingles_enabled'], r2['text_speed'], r2['battle_speed']), (0.35, False, 16.0, 0.0))
        self.assertEqual(r2['accel_speed'], 3.5)

    def test_battle_scroll_migration(self):
        """Old settings "Automatic scrolling" (yes / no) + "Scrolling speed" (0 to 3), then "Battle messages" (0 Fast, 2 Medium, 3 Slow, 4 Manual) -> "Battle speed": only "by hand" (imposed) has an equivalent: Manual."""
        for old, expected in (({'defilement_auto': True, 'defilement_vitesse': 0}, 1.0), ({'defilement_auto': True, 'defilement_vitesse': 3}, 1.0), ({'defilement_auto': False, 'defilement_vitesse': 0}, 0.0),
                                ({'defilement_auto': False}, 0.0), ({'defilement_auto': True}, 1.0), ({'defilement_combat': 4}, 0.0), ({'defilement_combat': 0}, 1.0), ({'defilement_combat': 3}, 1.0),
                                ({'defilement_combat': 4, 'battle_speed': 3.0}, 0.0), ({'defilement_combat': 2, 'battle_speed': 3.0}, 3.0)):
            r, _ = load(dict(old, defilement_force=True))
            self.assertEqual(r['battle_speed'], expected, old)
            for k in ('defilement_auto', 'defilement_vitesse', 'defilement_force', 'defilement_combat'): self.assertNotIn(k, r.v)
        r, _ = load({'defilement_auto': False, 'defilement_vitesse': 1}); self.assertEqual(r['battle_speed'], 1.0)      # nothing was imposed: nothing is after the migration
        r, _ = load({'defilement_force': False, 'defilement_combat': 4}); self.assertEqual(r['battle_speed'], 1.0)

    def test_notch_like_game_is_engine_standard(self):
        """The "Normal" notch (4 letters per frame) is the game's standard speed: it is the value that the game's priority rule (game_priority.letters_per_frame) replaces with the player's setting, and the one that changes nothing."""
        from dq4_pc.core import game_priority as PJ
        self.assertEqual(RG.DEFAULT['text_speed'], PJ.STANDARD_LETTERS)
        self.assertIn(float(PJ.STANDARD_LETTERS), RG.TEXT_SPEEDS)
        for v in RG.TEXT_SPEEDS: self.assertEqual(PJ.letters_per_frame(v, 400), 400, 'fenetres de combat : jamais touchees')

    def test_no_more_transition_speed_setting(self):
        """the transitions stay at the game's duration (x1), it is no longer a setting. An old file that had x2, x3 or x4 loads without error, the key is ignored and no longer rewritten."""
        for lookup_key in ('vitesse_fondu', 'vitesse_fondu_v'): self.assertNotIn(lookup_key, RG.DEFAULT); self.assertNotIn(lookup_key, RG.Settings(None).v); self.assertNotIn(lookup_key, RG.BOUNDS)
        for old in (1.0, 2.0, 3.0, 4.0):
            r, f = load({'vitesse_fondu': old, 'vitesse_fondu_v': 2, 'accel_speed': 3.0}); self.assertNotIn('vitesse_fondu', r.v); self.assertEqual(r['accel_speed'], 3.0)
            r.store()
            with open(f, encoding='utf-8') as fh: self.assertNotIn('vitesse_fondu', json.load(fh))
        from dq4_pc.core import engine as ENGINE
        self.assertEqual(ENGINE.State.fade_speed, 1.0)                                                            # (the engine keeps the original duration)

    def test_camera_speed_setting_removed(self):
        """No more camera speed: an old file that had one loads without error, the key is ignored and no longer rewritten; the accelerator keeps its slider."""
        self.assertNotIn('vitesse_camera', RG.DEFAULT); self.assertNotIn('vitesse_camera', RG.BOUNDS); self.assertIn('vitesse_camera', RG.OBSOLETE_KEYS)
        for old in (0.5, 1.5, 3, 4, 9, -3, True):
            r, f = load({'vitesse_camera': old}); self.assertNotIn('vitesse_camera', r.v, old); r.store()
            with open(f, encoding='utf-8') as fh: self.assertNotIn('vitesse_camera', json.load(fh))
        self.assertEqual(RG.DEFAULT['accel_speed'], 1.5)                                                      # the accelerator keeps its slider (1 to 4)
        r, _ = load({'accel_speed': 1.37}); self.assertEqual(r['accel_speed'], 1.37)
        for old, expected in ((0.2, 1.0), (3.5, 3.5), (5.5, 4.0), (8, 4.0), (12, 4.0)): self.assertEqual(load({'accel_speed': old})[0]['accel_speed'], expected, old)      # x1 to x4 (x8)
        r, _ = load({'vitesse_marche': 3.0}); self.assertNotIn('vitesse_marche', r.v); r.store()                        # the old walking setting is ignored, never written again
        with open(r.path, encoding='utf-8') as fh: self.assertNotIn('vitesse_marche', json.load(fh))


if __name__ == '__main__':
    unittest.main(verbosity=2)
