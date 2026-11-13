"""Test (without window) of the Pause menu pages: root, Son (one line per sound: name, volume, mute, default), Commandes (speeds x1 to x4, "Text scrolling" section), Modifications (formerly "Game").

    python3 tests/test_pause_pages.py

The menu is driven with a fake "game" (real settings, simulated sound and window): the same functions as the menu's own, keyboard included (Pause.key_press).
"""
import os, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq4_pc)
import pyglet
pyglet.options['shadow_window'] = False                     # (no display needed: nothing is drawn)
from dq4_pc.persistence import settings as RG
from dq4_pc.menus import pause as PA
from dq4_pc import language as LG

K = pyglet.window.key
SOUND_LABELS = ['settings.general', 'settings.music', 'settings.jingles_fanfares', 'settings.sound_effects', 'settings.interface']
SOUND_KEYS = {'settings.music': ('music_enabled', 'music_volume'), 'settings.jingles_fanfares': ('jingles_enabled', 'jingle_volume'), 'settings.sound_effects': ('sfx_enabled', 'sfx_volume'),
            'settings.interface': ('interface_enabled', 'interface_volume'), 'settings.general': ('sound', 'master_volume')}


class FakeSound:
    active = True; listening = False


class FakeGame:
    """What the Pause menu asks of the window."""
    def window_names(self): return {'BattleRoot': [1], 'BattleAction': [2], 'RootMenu': [3], 'Status': [4]}
    def __init__(self):
        self.reg = RG.Settings(os.path.join(tempfile.mkdtemp(prefix='pause_test_'), 'settings.json'))
        self.sound = FakeSound(); self.args = types.SimpleNamespace(cache='/inexistant'); self.width, self.height = 1280, 720; self.mouse = None
        self.calls = []; self.fade = None
        self.is_fullscreen = False; self.mode = 4; self.post = types.SimpleNamespace(max_msaa=None)          # (page Affichage)
    def set_sound(self, yes): self.sound.active = bool(yes)
    def apply_mix(self): self.calls.append('mixage')
    def preview_sound(self, category): self.calls.append(('apercu', category))
    def set_fade(self, v): self.fade = v
    def apply_text(self): self.calls.append('texte')
    def apply_game(self): self.calls.append('jeu')
    def set_battle_speed(self, v): self.reg['battle_speed'] = RG.battle_notch(v); self.calls.append(('battle', RG.scroll_code(v)))
    def pause_game(self, yes): pass
    def resolutions(self): return [(1280, 720), (1920, 1080)]
    def current_resolution(self): return (1280, 720)
    def set_resolution(self, v): self.calls.append(('res', v))
    def set_full_screen(self, v): self.is_fullscreen = v
    def set_mode(self, v): self.mode = v
    game_language = 'fr'; title = False                     # (language of the game loaded; the title screen displayed)
    def language_pending(self): return self.game_language != LG.current_language()
    def on_title(self): return self.title


def menu(screen_page):
    J = FakeGame(); p = PA.Pause(J); p.opened = True; p.stack = [screen_page]
    return J, p


def by_caption(p, lib):
    return next(e for e in p._entries() if e['l'] == lib)


class Headings(unittest.TestCase):
    """"Interface to edit" drop-down list: the group subheadings ("Touch screen", "Dialogue"...) are discreet, never gold (gold is the current value's)."""
    def test_headings_neither_gold_nor_as_large_as_values(self):
        t, c = PA.heading_style(20.0)
        self.assertLess(t, 20.0 * 0.9); self.assertNotEqual(c, PA.GOLD); self.assertNotEqual(c[:3], PA.WHITE[:3])               # smaller, neither gold nor white
        lum = lambda x: 0.3 * x[0] + 0.59 * x[1] + 0.11 * x[2]
        self.assertLess(lum(c), lum(PA.WHITE) * 0.7); self.assertLess(c[2], c[0])                                              # dull (less bright than white) but still a golden gray (not a neutral gray)
        self.assertLess(c[0] - c[2], 60); self.assertLess(lum(c), lum(PA.GOLD) - 40)                                             # (and clearly less vivid than the gold of the current value)
        self.assertEqual(PA.GOLD, (255, 235, 4, 255))                                                                            # the gold remains that of the current value

    def test_list_code_uses_heading_style(self):
        src = _paths.source('pause.py')
        i = src.index('if self._header(vals[j]):'); block = src[i:i + 700]
        self.assertIn('heading_style(fs)', block); self.assertNotIn(', OR)', block)                                           # the subheading is no longer drawn in gold


class Root(unittest.TestCase):
    def test_entries(self):
        _, p = menu('root'); libs = [e['l'] for e in p._entries()]
        for old in ('Vitesse de défilement du texte', 'Texte et défilement'): self.assertNotIn(old, libs)             # no more text page: its two options are in Commandes
        self.assertEqual(libs, ['settings.resume', 'settings.history', 'settings.save_states', 'settings.display', 'settings.sound', 'settings.controls', 'settings.modifiers', 'settings.return_title_screen', 'settings.quit_game'])
        rows = {e['l']: e for e in p._entries()}; self.assertFalse(rows['settings.quit_game'].get('sub'))                                                      # no chevron on "Quit the game", even though the line opens the confirmation
        self.assertTrue(all(rows[l].get('sub') for l in ('settings.history', 'settings.save_states', 'settings.display', 'settings.sound', 'settings.controls', 'settings.modifiers')))             # (the real sub-pages keep theirs)
        self.assertNotIn('Jeu', libs); self.assertNotIn('Modifications', libs); self.assertEqual(libs.index('settings.modifiers'), libs.index('settings.controls') + 1)                # "Modifiers" (ex-"Changes", ex-"Game") : juste sous "Controls"
        self.assertFalse(hasattr(p, '_e_texte'))


class SoundPage(unittest.TestCase):
    def test_one_line_per_sound(self):
        _, p = menu('sound'); e = p._entries()
        self.assertEqual([x['l'] for x in e], SOUND_LABELS)
        self.assertNotIn('sep', [x['t'] for x in e], 'plus de sections')
        for x in e:                                                                    # each line: a volume bar (slider), a mute button, a "default" button
            self.assertEqual(x['t'], 'slider'); self.assertTrue(all(k in x for k in ('set_fraction', 'active', 'ok', 'default', 'is_default')), x['l'])

    def test_mute_cuts_and_restores_correct_switch(self):
        J, p = menu('sound')
        for lib in SOUND_LABELS:
            active_key, vol_key = SOUND_KEYS[lib]; x = by_caption(p, lib)
            read = (lambda: J.sound.active) if lib == 'settings.general' else (lambda c=active_key: J.reg[c])
            self.assertTrue(read() and x['active']())
            x['ok'](); self.assertFalse(read(), lib); self.assertFalse(by_caption(p, lib)['active']())
            if lib == 'settings.general': self.assertIs(J.reg['sound'], False)
            others = [l for l in SOUND_LABELS if l != lib]
            self.assertTrue(all(by_caption(p, o)['active']() for o in others), 'a line mutes only its own sound')
            self.assertEqual(J.reg[vol_key], 1.0, 'muting does not change the volume')
            x['ok'](); self.assertTrue(read(), lib)

    def test_default_resets_volume_and_sound(self):
        J, p = menu('sound')
        for lib in SOUND_LABELS:
            active_key, vol_key = SOUND_KEYS[lib]; x = by_caption(p, lib)
            self.assertTrue(x['is_default']())
            x['set_fraction'](0.3); x['ok']()
            self.assertFalse(x['is_default']()); self.assertAlmostEqual(J.reg[vol_key], 0.3, 2)
            x['default'](); self.assertAlmostEqual(J.reg[vol_key], RG.DEFAULT[vol_key], 3); self.assertTrue(x['active']()); self.assertTrue(x['is_default']())
            x['set_fraction'](0.3); self.assertFalse(x['is_default'](), 'un volume different suffit')
            x['default']()
        J2, p2 = menu('sound'); x = by_caption(p2, 'settings.music'); x['ok'](); self.assertFalse(x['is_default'](), 'muted: not by default'); x['default'](); self.assertTrue(J2.reg['music_enabled'])

    def test_keyboard(self):
        J, p = menu('sound')
        p.key_press(K.S); self.assertEqual(p.selected['sound'], 1)                            # Musique
        p.key_press(K.LEFT); self.assertAlmostEqual(J.reg['music_volume'], 0.95, 2)
        p.key_press(K.LEFT); p.key_press(K.RIGHT); self.assertAlmostEqual(J.reg['music_volume'], 0.95, 2)
        p.key_press(K.RETURN); self.assertFalse(J.reg['music_enabled'])                  # Enter: mute
        self.assertIsNone(p.entry, 'Enter does not start the volume entry on this page')
        p.key_press(K.RETURN); self.assertTrue(J.reg['music_enabled'])
        p.key_press(K.SPACE); self.assertFalse(J.reg['music_enabled']); p.key_press(K.SPACE)
        p.key_press(K.DELETE); self.assertAlmostEqual(J.reg['music_volume'], 1.0, 3)    # Delete: default
        p.key_press(K.LEFT); p.key_press(K.LEFT); p.key_press(K.RETURN); p.key_press(K.HOME)       # Home: also
        self.assertAlmostEqual(J.reg['music_volume'], 1.0, 3); self.assertTrue(J.reg['music_enabled'])
        p.key_press(K.W); p.key_press(K.W); self.assertEqual(p.selected['sound'], 4)              # wrap-around: at the top of the list you arrive at the bottom
        p.key_press(K.S); self.assertEqual(p.selected['sound'], 0)

    def test_clicking_value_allows_typing(self):
        J, p = menu('sound'); x = by_caption(p, 'settings.sound_effects')
        x['set_value'](40); self.assertAlmostEqual(J.reg['sfx_volume'], 0.4, 3)

    def test_volume_plays_a_preview_and_so_does_unmuting(self):
        J, p = menu('sound'); x = by_caption(p, 'settings.sound_effects')
        J.calls.clear(); x['minus'](); self.assertIn(('apercu', 'effects'), J.calls)
        x['ok'](); J.calls.clear(); x['ok'](); self.assertIn(('apercu', 'effects'), J.calls, 'the sound comes back: it is heard'); self.assertIn('mixage', J.calls)


class ScrollSection(unittest.TestCase):
    """Display > the two text scrolling settings, with no heading: "Text speed" and "Battle speed"."""

    @staticmethod
    def lines(p): return p._entries()

    def test_section_at_the_bottom_of_display(self):
        """"Text speed" is in Affichage, at the very bottom (above the Interface button); "Battle speed" is in Commandes, under its key."""
        _, p = menu('display'); ls = [(x['t'], x['l']) for x in self.lines(p)]
        i = ls.index(('choice', 'settings.text_speed'))
        self.assertEqual(ls[i - 1], ('choice', 'settings.supersampling')); self.assertEqual(ls[i:], [('choice', 'settings.text_speed'), ('act', 'settings.interface')])          # (the Interface button at the very end)          # two options, then the end of the page; no heading above them
        self.assertNotIn(('sep', 'Défilement du texte'), ls)
        _, c = menu('controls'); lc = [(x['t'], x['l']) for x in self.lines(c)]
        for x in (('sep', 'Défilement du texte'), ('choice', 'settings.text_speed')): self.assertNotIn(x, lc)
        self.assertEqual([l for t, l in lc if t == 'sep'], ['settings.movement', 'settings.camera', 'settings.hold_middle_click_move', 'settings.middle_click', 'settings.speeds', 'settings.game_actions', 'settings.other'])        # (the camera only rotates and recenters:; no more zoom or wheel)
        k = [l for _, l in lc].index('settings.change_battle_speed')
        self.assertEqual(lc[k + 1:k + 3], [('choice', 'settings.battle_speed'), ('sep', 'settings.game_actions')])                                     # (the speeds end with the battle speed key and its setting)

    def test_all_camera_options_in_a_single_group(self):                 # "Group all the camera options directly in a group named "Camera""
        _, p = menu('controls'); e = self.lines(p); ls = [(x['t'], x['l']) for x in e]
        i = ls.index(('sep', 'settings.camera')); j = ls.index(('sep', 'settings.speeds'))
        self.assertEqual(ls.count(('sep', 'settings.camera')), 1); self.assertNotIn('Caméra au clavier', [l for _, l in ls]); self.assertNotIn('Caméra à la souris', [l for _, l in ls])
        group = ls[i + 1:j]
        self.assertEqual(group, [('key', 'settings.camera_left'), ('key', 'settings.camera_right'), ('choice', 'settings.invert_left_right'),
                                  ('sep', 'settings.hold_middle_click_move'), ('sep', 'settings.middle_click')])
        self.assertNotIn('Vitesse de caméra', [l for _, l in ls])                                                                          # (no more camera speed setting)
        self.assertEqual(ls.index(('key', 'settings.camera_left')) > ls.index(('key', 'settings.right')), True)                                  # (the group comes after movement)
        info = {x['l']: x.get('v') for x in e if x['t'] == 'sep' and x.get('v')}
        self.assertEqual(info, {'settings.hold_middle_click_move': 'settings.rotates_camera', 'settings.middle_click': 'settings.recenters_camera'})

    def test_no_more_text_page(self):
        _, p = menu('root'); self.assertNotIn('texte', [e['l'] for e in p._entries()])
        with open(PA.__file__, encoding='utf-8') as f: src = f.read()
        self.assertNotIn("_go('texte')", src); self.assertNotIn("titles['texte']", src)

    def test_names(self):
        _, p = menu('display')
        vt = by_caption(p, 'settings.text_speed')
        self.assertEqual([p._value_name('settings.text_speed', v) for v in vt['vals']], ['settings.very_slow', 'settings.slow', 'settings.fairly_slow', 'settings.normal', 'settings.fast', 'settings.very_fast', 'settings.instant'])
        _, p = menu('controls'); cb = by_caption(p, 'settings.battle_speed')
        self.assertEqual([p._value_name('settings.battle_speed', v) for v in cb['vals']], ['settings.manual', 'settings.normal', 'settings.fast', 'settings.very_fast'])
        self.assertEqual(cb['vals'], [0.0, 1.0, 2.0, 3.0])

    def test_text_speed(self):
        J, p = menu('display'); vt = by_caption(p, 'settings.text_speed')
        self.assertEqual((vt['get'](), vt['v']()), (4.0, 'settings.normal')); self.assertTrue(vt['is_default']())
        vt['set'](16.0); self.assertEqual(J.reg['text_speed'], 16.0); self.assertEqual(J.calls[-1], 'texte'); self.assertFalse(vt['is_default']())        # the window is notified
        vt['default'](); self.assertEqual(J.reg['text_speed'], 4.0); self.assertEqual(J.calls[-1], 'texte'); self.assertTrue(vt['is_default']())
        self.assertTrue(vt.get('hint'))

    def test_choice_changes_speed_and_scroll(self):
        """"Battle speed": the menu notifies the window (which also imposes the scrolling: 4 in "Manual", 2 otherwise); the list loops; ↺ resets to Normal (on the keyboard: the line is chosen in the Controls page)."""
        J, p = menu('controls'); cb = by_caption(p, 'settings.battle_speed')
        self.assertEqual((cb['get'](), cb['v']()), (1.0, 'settings.normal')); self.assertTrue(cb['is_default']())
        p.selected['controls'] = [x['l'] for x in p._entries()].index('settings.battle_speed'); p.key_press(K.D); self.assertEqual(J.reg['battle_speed'], 2.0)          # (Commandes: the arrows are the camera keys there, D = right)
        p.key_press(K.D); self.assertEqual(J.reg['battle_speed'], 3.0)
        p.key_press(K.D); self.assertEqual(J.reg['battle_speed'], 0.0)                                       # (the list wraps around) Very fast -> Manual
        self.assertEqual(J.calls[-1], ('battle', 4)); self.assertFalse(cb['is_default']())
        cb['default'](); self.assertEqual(J.reg['battle_speed'], 1.0); self.assertEqual(J.calls[-1], ('battle', 0)); self.assertTrue(cb['is_default']())      # ↺ : Normal
        self.assertTrue(cb.get('hint')); self.assertNotIn('x2', cb['hint'])

    def test_no_old_setting(self):
        _, p = menu('controls'); ls = [x.get('l') for x in p._entries()]
        for old in ('Défilement automatique', 'Vitesse de défilement', 'Messages en combat', 'Rétablir le réglage du jeu'): self.assertNotIn(old, ls)


class ChangesPage(unittest.TestCase):
    LIB = 'settings.hp_mp_restored_level_up'

    def test_option_disabled_by_default_with_restoration(self):
        """"Modifiers" page (formerly "Changes", formerly "Game"), "Difficulty" category: a Yes / No switch, No by default (as in the game), which notifies the window; ↺ resets it to No."""
        J, p = menu('changes'); x = by_caption(p, self.LIB)
        self.assertEqual(x['vals'], [True, False]); self.assertFalse(J.reg['level_up_heal']); self.assertTrue(x['is_default']())
        x['set'](True); self.assertTrue(J.reg['level_up_heal']); self.assertEqual(J.calls[-1], 'jeu'); self.assertFalse(x['is_default']())
        x['default'](); self.assertFalse(J.reg['level_up_heal']); self.assertEqual(J.calls[-1], 'jeu'); self.assertTrue(x['is_default']())
        self.assertTrue(x.get('hint'))

    def test_three_categories_and_entry_of_the_root(self):
        """three categories (subheadings) in the order Difficulty, Modifier, Cheats; the existing option is in "Difficulty", the other two have no line yet."""
        J, p = menu('changes'); e = p._entries()
        self.assertEqual([(x['t'], x['l']) for x in e], [('sep', 'settings.difficulty'), ('choice', self.LIB), ('sep', 'settings.modifier'), ('sep', 'settings.cheats'), ('choice', 'settings.game_ending_talking_king_bastione'), ('choice', 'settings.ending_played_shortcut')])          # (the test shortcut, in "Cheats"; and the ending it plays)
        p.stack = ['root']; e = next(e for e in p._entries() if e['l'] == 'settings.modifiers'); e['ok'](); self.assertEqual(p.screen_page, 'changes')
        self.assertFalse(hasattr(p, '_e_jeu')); self.assertNotIn('Jeu', [e['l'] for e in p._entries()])
        with open(PA.__file__, encoding='utf-8') as f: src = f.read()
        self.assertIn("titles['changes'] = N_('settings.modifiers')", src); self.assertNotIn("_go('jeu')", src)                                          # page title: "Modifiers"

    def test_setting_stored(self):
        J = FakeGame(); J.reg['level_up_heal'] = True; J.reg.store()
        self.assertTrue(RG.Settings(J.reg.path)['level_up_heal'])
        J.reg.v['level_up_heal'] = 'window.yes'; J.reg.store(); self.assertFalse(RG.Settings(J.reg.path)['level_up_heal'])        # invalid value: back to the default (Non)


class CommandsPage(unittest.TestCase):
    def test_speeds_in_options(self):
        J, p = menu('controls')
        self.assertNotIn('Vitesse de caméra', [e.get('l') for e in p._entries()])                                                          # (removed: the camera turns at the game's speed)
        x = by_caption(p, 'settings.accelerator_multiplier'); self.assertEqual(x['t'], 'slider'); self.assertAlmostEqual(x['v'] and J.reg['accel_speed'], 1.5)    # the accelerator keeps its slider
        x['set_fraction'](1.0); self.assertEqual(J.reg['accel_speed'], 4.0); x['set_fraction'](0.0); self.assertEqual(J.reg['accel_speed'], 1.0); x['set_value'](3); self.assertEqual(J.reg['accel_speed'], 3.0)       # x1 to x4 (x8)
        self.assertNotIn('Vitesse de marche', [e.get('l') for e in p._entries()])                                                                                                   # retiree
        self.assertNotIn("Vitesse de l'accélérateur", [e.get('l') for e in p._entries()])                                                                                       # (old label: renamed)

    def test_battle_speed_key(self):
        """Commandes > Vitesses: the "Change battle speed" key just below the accelerator multiplier, then the "Battle speed" setting (from Affichage to here, under its key)."""
        J, p = menu('controls'); e = p._entries(); ls = [x['l'] for x in e]
        i = ls.index('settings.accelerator_multiplier'); self.assertEqual(ls[i - 1], 'settings.accelerator_key')
        self.assertEqual(ls[i + 1], 'settings.change_battle_speed'); self.assertEqual(ls[i + 2], 'settings.battle_speed'); self.assertEqual(e[i + 3]['t'], 'sep'); self.assertEqual(ls[i + 3], 'settings.game_actions')      # (then the next section)
        self.assertEqual(ls.count('settings.battle_speed'), 1)
        for old in ('Vitesse des combats', 'Touche de vitesse des combats'): self.assertNotIn(old, ls)
        t = by_caption(p, 'settings.change_battle_speed'); self.assertEqual((t['t'], t['act']), ('key', 'battle_speed')); self.assertEqual(t['v'], ['V', '—', 'PAD_LT'])
        self.assertIn('settings.goes_from_manual_normal_fast', t['hint']); self.assertNotIn('x2', t['hint'])

    def test_no_removed_speed_options(self):
        _, p = menu('controls'); ls = [e.get('l') for e in p._entries()]
        for old in ('Vitesse de transition', 'Vitesse de caméra'): self.assertNotIn(old, ls)                                           # (transitions at x1; the camera speed is removed)


class Hover(unittest.TestCase):
    """No more yellow frame: under the pointer (mouse mode), an area darkens; with the keyboard, nothing is hovered."""
    def test_pointer(self):
        _, p = menu('root'); z = (10, 10, 50, 30)
        p.mouse_mode = False; p.mouse_pos = (20, 20); self.assertFalse(p._pointer_in(z)); self.assertFalse(p._hovered(z))
        p.mouse_mode = True; self.assertTrue(p._pointer_in(z)); self.assertTrue(p._hovered(z))
        p.mouse_pos = (60, 20); self.assertFalse(p._hovered(z))                                # the pointer leaves: the area lights up again
        p.mouse_pos = (20, 20); p.popup = {'title': 'x', 'choice': 1}; self.assertFalse(p._hovered(z)); self.assertTrue(p._pointer_in(z))        # under a modal window: the hover belongs to it
        self.assertFalse(p._pointer_in(None))
        p.popup = None; p.mouse_pos = (20, 20); self.assertTrue(p._hovered(z)); p.output(); self.assertFalse(p._hovered(z), 'the pointer left the window: nothing is hovered any more')

    def test_no_more_yellow_border_in_page_code(self):
        with open(PA.__file__, encoding='utf-8') as f: src = f.read()
        self.assertNotIn('JAUNE if sel', src); self.assertNotIn(', YELLOW)', src.replace('color=YELLOW)', ''))


class InterfaceEntries(unittest.TestCase):
    """"Interface to edit" list: battle speed button in its own element of the "Battle" group, with its own settings."""
    def test_groups(self):
        J, p = menu('interface'); v = p.targets()
        screen_page = v[v.index('#settings.touch_screen') + 1:v.index('#settings.dialogue')]; self.assertEqual(screen_page, ['buttons'])                  # "On-screen buttons and D-pad" stays alone in its group
        i = v.index('#settings.battle'); self.assertEqual(v[i + 1], 'speed_button')                                                   # the speed button: first element of the "Battle" group
        self.assertEqual(v[i + 1:i + 4], ['speed_button', 'BattleRoot', 'BattleAction'])
        self.assertEqual(p.target_name('speed_button'), 'settings.battle_speed_button'); self.assertEqual(p.target_name('buttons'), 'settings.screen_buttons_d_pad')
        self.assertEqual(sum(1 for x in v if x == 'speed_button'), 1)

    def test_speed_button_page(self):
        J, p = menu('interface'); p.target = RG.SPEED_TARGET; libs = [e['l'] for e in p._entries()]
        self.assertIn('settings.button_size_one', libs); self.assertIn('settings.put_back_left_edge', libs); self.assertIn('settings.show_interface_screen', libs)
        for other in ('settings.button_size', 'settings.show_d_pad', 'settings.d_pad_size', 'settings.horizontal_position'): self.assertNotIn(other, libs)
        p.target = RG.SCREEN_TARGET; libs = [e['l'] for e in p._entries()]
        self.assertIn('settings.button_size', libs); self.assertIn('settings.show_d_pad', libs); self.assertNotIn('settings.button_size_one', libs)

    def test_settings_specific_to_the_button(self):
        J, p = menu('interface'); R = J.reg; p.target = RG.SPEED_TARGET
        p._set_visible(RG.SPEED_TARGET, False); self.assertEqual((R['speed_button'], R['buttons']), (False, True)); self.assertFalse(p._visible(RG.SPEED_TARGET)); self.assertTrue(p._visible(RG.SCREEN_TARGET))
        p._set_visible(RG.SCREEN_TARGET, False); p._set_visible(RG.SPEED_TARGET, True); self.assertEqual((R['speed_button'], R['buttons']), (True, False))
        e = by_caption(p, 'settings.button_size_one'); e['plus'](); e['plus'](); self.assertAlmostEqual(R['speed_button_size'], 1.2); self.assertEqual(R['buttons_size'], 1.0); e['default'](); self.assertEqual(R['speed_button_size'], 1.0)
        R['speed_button_pos'] = [3.0, 4.0]; by_caption(p, 'settings.put_back_left_edge')['ok'](); self.assertEqual(R['speed_button_pos'], [])
        R['speed_button_pos'] = [3.0, 4.0]; R['buttons_pos'] = {'map': [1, 1]}; by_caption(p, 'settings.restore_interface')['ok']()
        self.assertEqual((R['speed_button_pos'], R['speed_button_size'], R['speed_button'], R['buttons_pos']), ([], 1.0, True, {'map': [1, 1]}))      # the reset only touches the button

    def test_editor_shows_the_right_element(self):
        from dq4_pc.menus import hud_mobile as HM
        self.assertEqual(HM.editor_names(RG.SCREEN_TARGET), ('map', 'menu', 'chat', HM.DPAD, HM.BAR)); self.assertEqual(HM.editor_names(RG.SPEED_TARGET), (HM.BATTLE,)); self.assertEqual(HM.editor_names('msg'), ())
        self.assertNotIn(HM.BATTLE, HM.editor_names(RG.SCREEN_TARGET))                                                               # no longer in "On-screen buttons and D-pad"


if __name__ == '__main__':
    unittest.main(verbosity=2)
