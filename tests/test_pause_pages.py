"""Test (without window) of the Pause menu pages: root, Son (one line per sound: name, volume, mute, default), Commandes (speeds x1 to x4, "Text scrolling" section), Modifications (formerly "Game").

    python3 tests/test_pause_pages.py

The menu is driven with a fake "game" (real settings, simulated sound and window): the same functions as the menu's own, keyboard included (Pause.key_press).
"""
import os, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
pyglet.options['shadow_window'] = False                     # (no display needed: nothing is drawn)
from dq456_pc.persistence import settings as RG
from dq456_pc.menus import pause as PA
from dq456_pc import language as LG

K = pyglet.window.key
SOUND_LABELS = ['sound.general', 'sound.music', 'sound.jingles_fanfares', 'sound.sound_effects', 'menu.interface']
SOUND_KEYS = {'sound.music': ('music_enabled', 'music_volume'), 'sound.jingles_fanfares': ('jingles_enabled', 'jingle_volume'), 'sound.sound_effects': ('sfx_enabled', 'sfx_volume'),
            'menu.interface': ('interface_enabled', 'interface_volume'), 'sound.general': ('sound', 'master_volume')}


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
        self.assertEqual(libs, ['menu.resume', 'menu.display', 'menu.sound', 'menu.controls', 'menu.save_states', 'menu.history', 'menu.achievements', 'menu.difficulty', 'menu.cheats', 'menu.randomizer', 'menu.return_title_screen', 'menu.quit_game'])
        rows = {e['l']: e for e in p._entries()}; self.assertFalse(rows['menu.quit_game'].get('sub'))                                                      # no chevron on "Quit the game", even though the line opens the confirmation
        self.assertTrue(all(rows[l].get('sub') for l in ('menu.history', 'menu.save_states', 'menu.display', 'menu.sound', 'menu.controls', 'menu.difficulty', 'menu.randomizer', 'menu.cheats', 'menu.achievements')))             # (the real sub-pages keep theirs)
        self.assertNotIn('Jeu', libs); self.assertNotIn('Modifications', libs); self.assertEqual(libs.index('menu.difficulty'), libs.index('menu.achievements') + 1)
        self.assertEqual(libs.index('menu.randomizer'), libs.index('menu.cheats') + 1); self.assertNotIn('settings.extras', libs)
        _, p = menu('achievements'); self.assertEqual([(e['t'], e['l']) for e in p._entries()], [('sep', 'menu.no_achievement_yet')]); self.assertTrue(p._entries()[0]['gray'])          # ("Achievements": none yet)
        self.assertFalse(hasattr(p, '_e_texte'))

    def test_dq5_dq6_randomizer(self):
        """DQ V / VI: Achievements, Difficulty, Cheats and the Randomizer (all its settings); the new game's panel has no gender
        line (the hero is a boy) and "Start the adventure" only needs a name; the Difficulty page has all its lines."""
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.randomizer import seed as SD
        old = ENGINE.ENGINE_V2; ENGINE.ENGINE_V2 = True
        try:
            _, p = menu('root'); libs = [e['l'] for e in p._entries()]
            _, d = menu('difficulty'); rows = [e['l'] for e in d._entries()]
            J, n = menu('root'); n.new_game = True; panel = [e['l'] for e in n._entries()]
            J, r = menu('randomizer'); r.new_game = True; r.randomizer_on = True; r.draft_seed = SD.new_code(number=5); rnd = [e['l'] for e in r._entries()]
        finally: ENGINE.ENGINE_V2 = old
        self.assertEqual(libs, ['menu.resume', 'menu.display', 'menu.sound', 'menu.controls', 'menu.save_states', 'menu.history', 'menu.achievements', 'menu.difficulty', 'menu.cheats', 'menu.randomizer', 'menu.return_title_screen', 'menu.quit_game'])
        self.assertIn('difficulty.casino_tokens_won', rows); self.assertIn('difficulty.experience_gained', rows); self.assertIn('difficulty.encounter_rate', rows)
        self.assertNotIn('new_game.hero_gender', panel); self.assertIn('new_game.hero_name', panel); self.assertIn('menu.randomizer', panel)
        self.assertEqual(rnd[2:], [k for _k, k, _h in PA.Pause.RANDOMIZER_SETTINGS])

    def test_opens_on_the_last_page(self):
        """Esc (or the game's "Settings" button) opens the menu on the page open on the right when it was last closed (kept in settings.json, the same for every game); Display the
        first time, or when that page cannot be opened now; the panel of a new game does not change it."""
        J, p = menu('root'); p.opened = False
        self.assertEqual(p.last_page(), 'display')
        p.open_menu(side=p.last_page()); p._switch_side(next(i for i, x in enumerate(p._entries_root()) if x.get('page') == 'sound')); self.assertEqual(p.stack, ['root', 'sound'])
        p.shutdown(); self.assertEqual(J.reg['settings_page'], 'sound'); self.assertEqual(RG.Settings(J.reg.path)['settings_page'], 'sound')
        p.open_menu(side=p.last_page()); self.assertEqual(p.stack, ['root', 'sound']); p.shutdown()
        p.open_menu(page='quit'); p.shutdown(); self.assertEqual(J.reg['settings_page'], 'sound')                  # (the "Quit" question: not a page to open on)
        J.history_possible = lambda: False; J.reg['settings_page'] = 'history'; self.assertEqual(p.last_page(), 'display')
        J.reg.v['settings_page'] = 'nothing'; J.reg.store(); self.assertEqual(RG.Settings(J.reg.path)['settings_page'], 'display')

    def test_esc_opens_on_display_and_closes_everything(self):
        J, p = menu('root'); p.opened = False; p.open_menu(side='display')                          # (Esc in the game: the Display page, the root's line chosen)
        self.assertEqual(p.stack, ['root', 'display']); self.assertEqual(p._entries_root()[p.selected['root']]['l'], 'menu.display')
        p.key_press(pyglet.window.key.ESCAPE); self.assertFalse(p.opened)


class DisplayPage(unittest.TestCase):
    def test_fullscreen_has_no_default_button(self):
        """No round "default value" button on "Fullscreen": No (windowed) stays only the setting's default (settings.DEFAULT); the other choices keep theirs."""
        J, p = menu('display'); e = by_caption(p, 'display.fullscreen')
        self.assertNotIn('default', e); self.assertNotIn('is_default', e); self.assertEqual(RG.DEFAULT['window_mode'], 0)
        self.assertIn('default', by_caption(p, 'language.title'))


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
            read = (lambda: J.sound.active) if lib == 'sound.general' else (lambda c=active_key: J.reg[c])
            self.assertTrue(read() and x['active']())
            x['ok'](); self.assertFalse(read(), lib); self.assertFalse(by_caption(p, lib)['active']())
            if lib == 'sound.general': self.assertIs(J.reg['sound'], False)
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
        J2, p2 = menu('sound'); x = by_caption(p2, 'sound.music'); x['ok'](); self.assertFalse(x['is_default'](), 'muted: not by default'); x['default'](); self.assertTrue(J2.reg['music_enabled'])

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
        J, p = menu('sound'); x = by_caption(p, 'sound.sound_effects')
        x['set_value'](40); self.assertAlmostEqual(J.reg['sfx_volume'], 0.4, 3)

    def test_volume_plays_a_preview_and_so_does_unmuting(self):
        J, p = menu('sound'); x = by_caption(p, 'sound.sound_effects')
        J.calls.clear(); x['minus'](); self.assertIn(('apercu', 'effects'), J.calls)
        x['ok'](); J.calls.clear(); x['ok'](); self.assertIn(('apercu', 'effects'), J.calls, 'the sound comes back: it is heard'); self.assertIn('mixage', J.calls)


class ScrollSection(unittest.TestCase):
    """Display > the two text scrolling settings, with no heading: "Text speed" and "Battle speed"."""

    @staticmethod
    def lines(p): return p._entries()

    def test_section_at_the_bottom_of_display(self):
        """"Text speed" is in Affichage, at the very bottom (above the Interface button); "Battle speed" is in Commandes, under its key."""
        _, p = menu('display'); ls = [(x['t'], x['l']) for x in self.lines(p)]
        i = ls.index(('choice', 'display.text_speed'))
        self.assertEqual(ls[i - 1], ('choice', 'display.supersampling')); self.assertEqual(ls[i:], [('choice', 'display.text_speed'), ('act', 'menu.interface')])          # (the Interface button at the very end)          # two options, then the end of the page; no heading above them
        self.assertNotIn(('sep', 'Défilement du texte'), ls)
        _, c = menu('controls'); lc = [(x['t'], x['l']) for x in self.lines(c)]
        for x in (('sep', 'Défilement du texte'), ('choice', 'display.text_speed')): self.assertNotIn(x, lc)
        self.assertEqual([l for t, l in lc if t == 'sep'], ['controls.movement', 'controls.camera', 'controls.hold_middle_click_move', 'controls.middle_click', 'controls.speeds', 'controls.game_actions', 'controls.other'])        # (the camera only rotates and recenters:; no more zoom or wheel)
        k = [l for _, l in lc].index('controls.change_battle_speed')
        self.assertEqual(lc[k + 1:k + 3], [('choice', 'controls.battle_speed'), ('sep', 'controls.game_actions')])                                     # (the speeds end with the battle speed key and its setting)

    def test_all_camera_options_in_a_single_group(self):                 # "Group all the camera options directly in a group named "Camera""
        _, p = menu('controls'); e = self.lines(p); ls = [(x['t'], x['l']) for x in e]
        i = ls.index(('sep', 'controls.camera')); j = ls.index(('sep', 'controls.speeds'))
        self.assertEqual(ls.count(('sep', 'controls.camera')), 1); self.assertNotIn('Caméra au clavier', [l for _, l in ls]); self.assertNotIn('Caméra à la souris', [l for _, l in ls])
        group = ls[i + 1:j]
        self.assertEqual(group, [('key', 'controls.camera_left'), ('key', 'controls.camera_right'),
                                  ('sep', 'controls.hold_middle_click_move'), ('sep', 'controls.middle_click'), ('choice', 'controls.invert_left_right')])          # (the inversion under "Middle click": it reverses the mouse drag)
        self.assertNotIn('Vitesse de caméra', [l for _, l in ls])                                                                          # (no more camera speed setting)
        self.assertEqual(ls.index(('key', 'controls.camera_left')) > ls.index(('key', 'controls.right')), True)                                  # (the group comes after movement)
        info = {x['l']: x.get('v') for x in e if x['t'] == 'sep' and x.get('v')}
        self.assertEqual(info, {'controls.hold_middle_click_move': 'controls.rotates_camera', 'controls.middle_click': 'controls.recenters_camera'})

    def test_no_more_text_page(self):
        _, p = menu('root'); self.assertNotIn('texte', [e['l'] for e in p._entries()])
        with open(PA.__file__, encoding='utf-8') as f: src = f.read()
        self.assertNotIn("_go('texte')", src); self.assertNotIn("titles['texte']", src)

    def test_names(self):
        _, p = menu('display')
        vt = by_caption(p, 'display.text_speed')
        self.assertEqual([p._value_name('display.text_speed', v) for v in vt['vals']], ['display.very_slow', 'display.slow', 'display.fairly_slow', 'common.normal', 'common.fast', 'common.very_fast', 'display.instant'])
        _, p = menu('controls'); cb = by_caption(p, 'controls.battle_speed')
        self.assertEqual([p._value_name('controls.battle_speed', v) for v in cb['vals']], ['common.manual', 'common.normal', 'common.fast', 'common.very_fast'])
        self.assertEqual(cb['vals'], [0.0, 1.0, 2.0, 3.0])

    def test_text_speed(self):
        J, p = menu('display'); vt = by_caption(p, 'display.text_speed')
        self.assertEqual((vt['get'](), vt['v']()), (4.0, 'common.normal')); self.assertTrue(vt['is_default']())
        vt['set'](16.0); self.assertEqual(J.reg['text_speed'], 16.0); self.assertEqual(J.calls[-1], 'texte'); self.assertFalse(vt['is_default']())        # the window is notified
        vt['default'](); self.assertEqual(J.reg['text_speed'], 4.0); self.assertEqual(J.calls[-1], 'texte'); self.assertTrue(vt['is_default']())
        self.assertTrue(vt.get('hint'))

    def test_drop_down_list_is_drawn_on_the_controls_page(self):
        """the list of "Battle speed" opened but was never drawn on the Controls page: the key cells reused the name `n` (number of pictures) of the number of lines, and the list
        is only drawn for a line below that number"""
        src = _paths.source('pause.py'); i = src.index("fam = self._family(); pad_mode = self.controls_pad"); j = src.index('self._draw_tooltip(e, n, lines', i)
        self.assertNotIn(' n = ', src[i:j]); self.assertNotIn('; n = ', src[i:j])

    def test_choice_changes_speed_and_scroll(self):
        """"Battle speed": the menu notifies the window (which also imposes the scrolling: 4 in "Manual", 2 otherwise); the list loops; ↺ resets to Manual, the default (on the keyboard: the line is chosen in the Controls page)."""
        J, p = menu('controls'); cb = by_caption(p, 'controls.battle_speed')
        self.assertEqual((cb['get'](), cb['v']()), (0.0, 'common.manual')); self.assertTrue(cb['is_default']())
        p.selected['controls'] = [x['l'] for x in p._entries()].index('controls.battle_speed'); p.key_press(K.D); self.assertEqual(J.reg['battle_speed'], 1.0)          # (Commandes: the arrows are the camera keys there, D = right)
        self.assertEqual(J.calls[-1], ('battle', 0)); self.assertFalse(cb['is_default']())
        p.key_press(K.D); p.key_press(K.D); self.assertEqual(J.reg['battle_speed'], 3.0)
        p.key_press(K.D); self.assertEqual(J.reg['battle_speed'], 0.0); self.assertEqual(J.calls[-1], ('battle', 4))          # (the list wraps around) Very fast -> Manual
        p.key_press(K.D); cb['default'](); self.assertEqual(J.reg['battle_speed'], 0.0); self.assertEqual(J.calls[-1], ('battle', 4)); self.assertTrue(cb['is_default']())      # ↺ : Manual
        self.assertTrue(cb.get('hint')); self.assertNotIn('x2', cb['hint'])

    def test_no_old_setting(self):
        _, p = menu('controls'); ls = [x.get('l') for x in p._entries()]
        for old in ('Défilement automatique', 'Vitesse de défilement', 'Messages en combat', 'Rétablir le réglage du jeu'): self.assertNotIn(old, ls)


class SaveStatesPage(unittest.TestCase):
    def test_choice_on_the_slot(self):
        """No more "Action" list at the top: one line per slot; an empty slot receives a new state at once; a slot holding one opens, beside it, the list of what to do with it
        (load, create in its place, delete: through the confirmation window), Esc closes it without doing anything."""
        J, p = menu('states'); done = []
        J.state_info = lambda n: [{'date': '2026-11-15 01:00:00', 'map': 'f'}] if n == 2 else None
        J.save_state = lambda n, png: done.append(('save', n)); J._png_thumbnail = lambda tex: b''; J.load_state = lambda n: done.append(('load', n))
        e = p._entries(); self.assertEqual([x['t'] for x in e], ['slot'] * PA.SAVESTATE_COUNT); self.assertFalse(hasattr(p, 'state_action'))
        p.selected['states'] = 0; p.key_press(pyglet.window.key.RETURN); self.assertEqual(done, [('save', 1)]); self.assertIsNone(p.open_dropdown)
        p.selected['states'] = 1; p.key_press(pyglet.window.key.RETURN); self.assertEqual(p.open_dropdown, [1, 0]); self.assertEqual(p._entries()[1]['vals'], ['load', 'create', 'delete'])
        self.assertEqual([p._value_name(p._entries()[1]['list_label'], v) for v in p._entries()[1]['vals']], ['save_states.load_save_state', 'save_states.create_save_state', 'save_states.delete_a_save_state'])
        p.key_press(pyglet.window.key.BACKSPACE); self.assertIsNone(p.open_dropdown); self.assertEqual(done, [('save', 1)]); self.assertTrue(p.opened)          # (Backspace: the list only)
        p.key_press(pyglet.window.key.ENTER); self.assertIsNotNone(p.open_dropdown); p.key_press(pyglet.window.key.ESCAPE); self.assertFalse(p.opened)          # (Esc: the whole menu, list included)
        p.key_press(pyglet.window.key.RETURN); p.key_press(pyglet.window.key.RETURN); self.assertIn(('load', 2), done)                                      # (Charger)
        p.opened = True; p.stack = ['states']; p.selected['states'] = 1; p.key_press(pyglet.window.key.RETURN); p.open_dropdown[1] = 2; p.key_press(pyglet.window.key.RETURN)
        self.assertIsNotNone(p.popup)                                                                                                                       # (Supprimer: the confirmation)


class ChangesPage(unittest.TestCase):
    LIB = 'difficulty.hp_mp_restored_level_up'
    LIB_BATTLE = 'difficulty.hp_mp_restored_battle_end'

    def test_option_disabled_by_default_with_restoration(self):
        """"Modifiers" page (formerly "Changes", formerly "Game"), "Difficulty" category: a Yes / No switch, No by default (as in the game), which notifies the window; ↺ resets it to No."""
        J, p = menu('difficulty'); x = by_caption(p, self.LIB)
        self.assertEqual(x['vals'], [True, False]); self.assertFalse(J.reg['level_up_heal']); self.assertTrue(x['is_default']())
        x['set'](True); self.assertTrue(J.reg['level_up_heal']); self.assertEqual(J.calls[-1], 'jeu'); self.assertFalse(x['is_default']())
        x['default'](); self.assertFalse(J.reg['level_up_heal']); self.assertEqual(J.calls[-1], 'jeu'); self.assertTrue(x['is_default']())
        self.assertTrue(x.get('hint'))

    def test_battle_end_option(self):
        """"HP and MP restored after a battle", right below the level-up one: a Yes / No switch, No by default (as in the game), which notifies the window; ↺ resets it to No; stored like the others."""
        J, p = menu('difficulty'); x = by_caption(p, self.LIB_BATTLE)
        self.assertEqual(x['vals'], [True, False]); self.assertFalse(J.reg['battle_end_heal']); self.assertTrue(x['is_default']())
        x['set'](True); self.assertTrue(J.reg['battle_end_heal']); self.assertEqual(J.calls[-1], 'jeu'); self.assertFalse(x['is_default']())
        self.assertFalse(J.reg['level_up_heal'])                                                                       # (the two options are independent)
        x['default'](); self.assertFalse(J.reg['battle_end_heal']); self.assertTrue(x['is_default']())
        self.assertTrue(x.get('hint'))
        J = FakeGame(); J.reg['battle_end_heal'] = True; J.reg.store(); self.assertTrue(RG.Settings(J.reg.path)['battle_end_heal'])
        J.reg.v['battle_end_heal'] = 1; J.reg.store(); self.assertFalse(RG.Settings(J.reg.path)['battle_end_heal'])      # not a boolean: back to the default (No)

    def test_three_pages_and_entry_of_the_root(self):
        """"Difficulty", "Modifier", "Cheats": three pages of the root (no tabs): "Difficulty" has the existing options, "Modifier" no line yet, "Cheats" "Random encounters"."""
        J, p = menu('difficulty'); e = p._entries()
        self.assertEqual([(x['t'], x['l']) for x in e], [('choice', self.LIB), ('choice', self.LIB_BATTLE), ('slider', 'difficulty.difficulty_level'), ('slider', 'difficulty.experience_gained'), ('slider', 'difficulty.gold_gained'),
                                                         ('slider', 'difficulty.casino_tokens_won'), ('slider', 'difficulty.damage_taken_party'), ('slider', 'difficulty.damage_taken_enemies'), ('slider', 'difficulty.encounter_rate')])
        self.assertFalse(hasattr(PA.Pause, 'CHANGES_TABS')); self.assertFalse(hasattr(PA.Pause, 'switch_tab'))
        _, p = menu('randomizer'); self.assertEqual([(x['t'], x['l'], x.get('gray')) for x in p._entries()], [('sep', 'randomizer.game_without_randomizer', True)])          # (no game rules: no seed; see test_game_rules)
        _, p = menu('cheats'); self.assertEqual([x['l'] for x in p._entries()], ['difficulty.random_encounters'])
        for label, page in (('menu.difficulty', 'difficulty'), ('menu.randomizer', 'randomizer'), ('menu.cheats', 'cheats')):
            _, p = menu('root'); e = next(e for e in p._entries() if e['l'] == label); e['ok'](); self.assertEqual(p.screen_page, page)
        with open(PA.__file__, encoding='utf-8') as f: src = f.read()
        self.assertIn("titles.update(difficulty=N_('menu.difficulty'), randomizer=N_('menu.randomizer'), cheats=N_('menu.cheats')", src); self.assertNotIn("_go('jeu')", src)                                          # page title: "Modifiers"

    def test_five_notches(self):
        """"Experience gained", "Gold gained", "Casino tokens won", "Damage taken by the party", "Damage taken by enemies": sliders of 5 notches, Much less (x0.5), Less (x0.75), Normal (x1, the default: the game),
        More (x1.25), Much more (x1.5); only the names are shown (never the factor); each one notifies the window, ↺ goes back to Normal; stored."""
        names = ['difficulty.rate_much_less', 'difficulty.rate_less', 'common.normal', 'difficulty.rate_more', 'difficulty.rate_much_more']
        for label, key in (('difficulty.experience_gained', 'exp_rate'), ('difficulty.gold_gained', 'gold_rate'), ('difficulty.casino_tokens_won', 'casino_rate'), ('difficulty.damage_taken_party', 'party_damage_rate'), ('difficulty.damage_taken_enemies', 'enemy_damage_rate'),
                           ('difficulty.encounter_rate', 'encounter_rate')):
            J, p = menu('difficulty'); J.reg['difficulty'] = RG.DIFFICULTY_CUSTOM; x = by_caption(p, label)          # (Custom: the lines are set by hand)
            self.assertEqual((J.reg[key], x['v']()), (1.0, 'common.normal')); self.assertTrue(x['is_default']()); self.assertAlmostEqual(x['fraction'](), 0.5)
            x['minus'](); self.assertEqual((J.reg[key], x['v']()), (0.75, 'difficulty.rate_less')); self.assertEqual(J.calls[-1], 'jeu'); self.assertFalse(x['is_default']())
            x['minus'](); self.assertEqual((J.reg[key], x['v']()), (0.5, 'difficulty.rate_much_less')); x['minus'](); self.assertEqual(J.reg[key], 0.5)             # (no notch below)
            for v, n in ((0.75, 1), (1.0, 2), (1.25, 3), (1.5, 4)): x['plus'](); self.assertEqual((J.reg[key], x['v']()), (v, names[n]))
            x['plus'](); self.assertEqual(J.reg[key], 1.5)
            x['set_fraction'](0.1); self.assertEqual(J.reg[key], 0.5); x['set_fraction'](0.3); self.assertEqual(J.reg[key], 0.75); x['set_fraction'](0.7); self.assertEqual(J.reg[key], 1.25)         # (a click on the bar: the nearest notch)
            self.assertEqual((x['notches'], x['notch_names']), ([0.0, 0.25, 0.5, 0.75, 1.0], names))
            x['default'](); self.assertEqual(J.reg[key], 1.0); self.assertTrue(x['is_default']()); self.assertIn('difficulty.normal_as_original_game_rewards', x['hint'])
            self.assertNotIn('(x', LG.tr(x['v']()))
            J.reg[key] = 1.25; J.reg.store(); self.assertEqual(RG.Settings(J.reg.path)[key], 1.25)
            for bad in (2.0, 0.6, True, 'x', None): J.reg.v[key] = bad; J.reg.store(); self.assertEqual(RG.Settings(J.reg.path)[key], 1.0, bad)          # (anything but a notch: Normal)

    def test_notched_values_are_never_typed(self):
        """The difficulty level and its notched lines show only the notch's name: neither Enter nor a click on the value starts typing it, and their help does not offer it (a volume still can)."""
        J, p = menu('difficulty'); J.reg['difficulty'] = RG.DIFFICULTY_CUSTOM
        for i, x in enumerate(p._entries()):
            if x['t'] != 'slider': continue
            self.assertTrue(x.get('notches'), x['l'])
            p.selected['difficulty'] = i; p.key_press(K.RETURN); self.assertIsNone(p.entry, x['l'])
            self.assertNotIn('common.click_value_type', p._line_helptext(x), x['l'])
        J2, p2 = menu('display'); x = by_caption(p2, 'display.brightness'); self.assertIn('common.click_value_type', p2._line_helptext(x))

    def test_random_encounters_switch_in_cheats(self):
        """"Random encounters" (tab "Cheats"): a Yes / No switch, Yes by default (as in the game); No does not gray "Encounter rate" (tab "Difficulty"): it stays settable; each change notifies the window."""
        J, p = menu('cheats'); J.reg['difficulty'] = RG.DIFFICULTY_CUSTOM; x = by_caption(p, 'difficulty.random_encounters'); p.stack = ['difficulty']; f = by_caption(p, 'difficulty.encounter_rate')
        self.assertEqual(x['vals'], [True, False]); self.assertTrue(J.reg['random_encounters']); self.assertTrue(x['is_default']()); self.assertFalse(p._inactive(f))
        f['plus'](); self.assertEqual(J.reg['encounter_rate'], 1.25)
        x['set'](False); self.assertFalse(J.reg['random_encounters']); self.assertEqual(J.calls[-1], 'jeu'); self.assertFalse(p._inactive(f)); self.assertEqual(J.reg['encounter_rate'], 1.25)
        f['plus'](); self.assertEqual(J.reg['encounter_rate'], 1.5)
        x['default'](); self.assertTrue(J.reg['random_encounters']); self.assertFalse(p._inactive(f)); self.assertTrue(x.get('hint'))
        J.reg['random_encounters'] = False; J.reg.store(); self.assertFalse(RG.Settings(J.reg.path)['random_encounters'])
        J.reg.v['random_encounters'] = 0; J.reg.store(); self.assertTrue(RG.Settings(J.reg.path)['random_encounters'])          # (not a boolean: back to the default)

    RATE_LABELS = ('difficulty.experience_gained', 'difficulty.gold_gained', 'difficulty.casino_tokens_won', 'difficulty.damage_taken_party', 'difficulty.damage_taken_enemies', 'difficulty.encounter_rate')

    def test_difficulty_levels(self):
        """"Difficulty", right above the notched lines: 6 notches, Dragon egg, Dragonling, Dragon (the default: the game), Dragon chief, Dragon god, Custom. A level sets the 5 notched lines
        (the easier, the more experience, gold and damage on the monsters, the less damage on the party and the fewer encounters) and grays them; Custom puts them back to their default and lets them be set by hand."""
        names = ['difficulty.dragon_egg', 'difficulty.dragonling', 'difficulty.dragon', 'difficulty.dragon_chief', 'difficulty.dragon_god', 'difficulty.custom']
        J, p = menu('difficulty'); e = p._entries(); d = by_caption(p, 'difficulty.difficulty_level')
        self.assertEqual([x['l'] for x in e].index('difficulty.difficulty_level') + 1, [x['l'] for x in e].index('difficulty.experience_gained'))
        self.assertEqual((J.reg['difficulty'], d['v']()), (2, 'difficulty.dragon')); self.assertTrue(d['is_default']()); self.assertEqual(d['notch_names'], names)
        self.assertEqual(d['notches'], [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]); self.assertIn('difficulty.dragon_as_original_game', d['hint'])
        rates = lambda: {k: J.reg[k] for k in RG.RATE_KEYS}; lines = lambda: [by_caption(p, l) for l in self.RATE_LABELS]
        self.assertTrue(all(p._inactive(x) for x in lines())); self.assertTrue(all('difficulty.set_by_difficulty_choose_custom' in x['hint'] for x in lines()))
        self.assertEqual(rates(), dict.fromkeys(RG.RATE_KEYS, 1.0))
        d['minus'](); self.assertEqual((J.reg['difficulty'], d['v']()), (1, 'difficulty.dragonling')); self.assertEqual(J.calls[-1], 'jeu')
        self.assertEqual(rates(), {'exp_rate': 1.25, 'gold_rate': 1.25, 'casino_rate': 1.25, 'party_damage_rate': 0.75, 'enemy_damage_rate': 1.25, 'encounter_rate': 0.75})
        d['minus'](); self.assertEqual(rates(), {'exp_rate': 1.5, 'gold_rate': 1.5, 'casino_rate': 1.5, 'party_damage_rate': 0.5, 'enemy_damage_rate': 1.5, 'encounter_rate': 0.5})          # (Dragon egg: the easiest)
        d['set_fraction'](0.8); self.assertEqual((J.reg['difficulty'], d['v']()), (4, 'difficulty.dragon_god'))
        self.assertEqual(rates(), {'exp_rate': 0.5, 'gold_rate': 0.5, 'casino_rate': 0.5, 'party_damage_rate': 1.5, 'enemy_damage_rate': 0.5, 'encounter_rate': 1.5})
        self.assertEqual([x['v']() for x in lines()], ['difficulty.rate_much_less', 'difficulty.rate_much_less', 'difficulty.rate_much_less', 'difficulty.rate_much_more', 'difficulty.rate_much_less', 'difficulty.rate_much_more'])          # (the lines show the level's notches)
        d['plus'](); self.assertEqual((J.reg['difficulty'], d['v']()), (5, 'difficulty.custom')); self.assertEqual(rates(), dict.fromkeys(RG.RATE_KEYS, 1.0))          # (Custom: every notch back to its default)
        self.assertFalse(any(p._inactive(x) for x in lines())); self.assertFalse(any('difficulty.set_by_difficulty_choose_custom' in x['hint'] for x in lines()))
        by_caption(p, 'difficulty.experience_gained')['plus'](); self.assertEqual(J.reg['exp_rate'], 1.25)
        d['plus'](); self.assertEqual(J.reg['exp_rate'], 1.25)                                                       # (already on Custom: its settings stay)
        J.reg['random_encounters'] = False; self.assertFalse(p._inactive(by_caption(p, 'difficulty.encounter_rate'))); J.reg['random_encounters'] = True          # (no random encounter: the rate can still be set)
        d['default'](); self.assertEqual(J.reg['difficulty'], 2); self.assertEqual(rates(), dict.fromkeys(RG.RATE_KEYS, 1.0))

    def test_difficulty_stored(self):
        """Stored; a level decides the notches when read again (whatever the file says); a file from before the setting gets the level of its notches, otherwise Custom."""
        J = FakeGame(); J.reg['difficulty'] = 3; J.reg['exp_rate'] = 1.5; J.reg.store(); r = RG.Settings(J.reg.path)
        self.assertEqual((r['difficulty'], r['exp_rate'], r['party_damage_rate']), (3, 0.75, 1.25))
        J.reg['difficulty'] = 5; J.reg.store(); r = RG.Settings(J.reg.path); self.assertEqual((r['difficulty'], r['exp_rate']), (5, 1.5))
        for bad in (6, -1, 2.5, True, 'x', None): J.reg.v['difficulty'] = bad; J.reg.store(); self.assertEqual(RG.Settings(J.reg.path)['difficulty'], 2, bad)          # (anything but a notch: Dragon)
        import json
        for rates, level in ((dict.fromkeys(RG.RATE_KEYS, 1.0), 2), (RG.difficulty_rates(1), 1), (dict(RG.difficulty_rates(2), exp_rate=1.25), 5)):
            with open(J.reg.path, encoding='utf-8') as f: v = json.load(f)
            v.pop('difficulty', None); v.update(rates)
            with open(J.reg.path, 'w', encoding='utf-8') as f: json.dump(v, f)
            r = RG.Settings(J.reg.path); self.assertEqual(r['difficulty'], level, rates); self.assertEqual({k: r[k] for k in RG.RATE_KEYS}, rates)

    def test_setting_stored(self):
        J = FakeGame(); J.reg['level_up_heal'] = True; J.reg.store()
        self.assertTrue(RG.Settings(J.reg.path)['level_up_heal'])
        J.reg.v['level_up_heal'] = 'window.yes'; J.reg.store(); self.assertFalse(RG.Settings(J.reg.path)['level_up_heal'])        # invalid value: back to the default (Non)


class CommandsPage(unittest.TestCase):
    def test_speeds_in_options(self):
        J, p = menu('controls')
        self.assertNotIn('Vitesse de caméra', [e.get('l') for e in p._entries()])                                                          # (removed: the camera turns at the game's speed)
        x = by_caption(p, 'controls.accelerator_multiplier'); self.assertEqual(x['t'], 'slider'); self.assertAlmostEqual(x['v'] and J.reg['accel_speed'], 1.5)    # the accelerator keeps its slider
        x['set_fraction'](1.0); self.assertEqual(J.reg['accel_speed'], 4.0); x['set_fraction'](0.0); self.assertEqual(J.reg['accel_speed'], 1.0); x['set_value'](3); self.assertEqual(J.reg['accel_speed'], 3.0)       # x1 to x4 (x8)
        self.assertNotIn('Vitesse de marche', [e.get('l') for e in p._entries()])                                                                                                   # retiree
        self.assertNotIn("Vitesse de l'accélérateur", [e.get('l') for e in p._entries()])                                                                                       # (old label: renamed)

    def test_battle_speed_key(self):
        """Commandes > Vitesses: the "Change battle speed" key just below the accelerator multiplier, then the "Battle speed" setting (from Affichage to here, under its key)."""
        J, p = menu('controls'); e = p._entries(); ls = [x['l'] for x in e]
        i = ls.index('controls.accelerator_multiplier'); self.assertEqual(ls[i - 1], 'controls.accelerator_key')
        self.assertEqual(ls[i + 1], 'controls.change_battle_speed'); self.assertEqual(ls[i + 2], 'controls.battle_speed'); self.assertEqual(e[i + 3]['t'], 'sep'); self.assertEqual(ls[i + 3], 'controls.game_actions')      # (then the next section)
        self.assertEqual(ls.count('controls.battle_speed'), 1)
        for old in ('Vitesse des combats', 'Touche de vitesse des combats'): self.assertNotIn(old, ls)
        t = by_caption(p, 'controls.change_battle_speed'); self.assertEqual((t['t'], t['act']), ('key', 'battle_speed')); self.assertEqual(t['v'], ['V', '—', 'PAD_LT'])
        self.assertIn('controls.goes_from_manual_normal_fast', t['hint']); self.assertNotIn('x2', t['hint'])

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
        screen_page = v[v.index('#interface.touch_screen') + 1:v.index('#interface.dialogue')]; self.assertEqual(screen_page, ['buttons'])                  # "On-screen buttons and D-pad" stays alone in its group
        i = v.index('#save_states.battle'); self.assertEqual(v[i + 1], 'speed_button')                                                   # the speed button: first element of the "Battle" group
        self.assertEqual(v[i + 1:i + 4], ['speed_button', 'BattleRoot', 'BattleAction'])
        self.assertEqual(p.target_name('speed_button'), 'interface.battle_speed_button'); self.assertEqual(p.target_name('buttons'), 'interface.screen_buttons_d_pad')
        self.assertEqual(sum(1 for x in v if x == 'speed_button'), 1)

    def test_speed_button_page(self):
        J, p = menu('interface'); p.target = RG.SPEED_TARGET; libs = [e['l'] for e in p._entries()]
        self.assertIn('interface.button_size_one', libs); self.assertIn('interface.put_back_left_edge', libs); self.assertIn('interface.show_interface_screen', libs)
        for other in ('interface.button_size', 'interface.show_d_pad', 'interface.d_pad_size', 'interface.horizontal_position'): self.assertNotIn(other, libs)
        p.target = RG.SCREEN_TARGET; libs = [e['l'] for e in p._entries()]
        self.assertIn('interface.button_size', libs); self.assertIn('interface.show_d_pad', libs); self.assertNotIn('interface.button_size_one', libs)

    def test_settings_specific_to_the_button(self):
        J, p = menu('interface'); R = J.reg; p.target = RG.SPEED_TARGET
        p._set_visible(RG.SPEED_TARGET, False); self.assertEqual((R['speed_button'], R['buttons']), (False, True)); self.assertFalse(p._visible(RG.SPEED_TARGET)); self.assertTrue(p._visible(RG.SCREEN_TARGET))
        p._set_visible(RG.SCREEN_TARGET, False); p._set_visible(RG.SPEED_TARGET, True); self.assertEqual((R['speed_button'], R['buttons']), (True, False))
        e = by_caption(p, 'interface.button_size_one'); e['plus'](); e['plus'](); self.assertAlmostEqual(R['speed_button_size'], 1.2); self.assertEqual(R['buttons_size'], 1.0); e['default'](); self.assertEqual(R['speed_button_size'], 1.0)
        R['speed_button_pos'] = [3.0, 4.0]; by_caption(p, 'interface.put_back_left_edge')['ok'](); self.assertEqual(R['speed_button_pos'], [])
        R['speed_button_pos'] = [3.0, 4.0]; R['buttons_pos'] = {'map': [1, 1]}; by_caption(p, 'interface.restore_interface')['ok']()
        self.assertEqual((R['speed_button_pos'], R['speed_button_size'], R['speed_button'], R['buttons_pos']), ([], 1.0, True, {'map': [1, 1]}))      # the reset only touches the button

    def test_editor_shows_the_right_element(self):
        from dq456_pc.menus import hud_mobile as HM
        self.assertEqual(HM.editor_names(RG.SCREEN_TARGET), ('map', 'menu', 'chat', HM.DPAD, HM.BAR)); self.assertEqual(HM.editor_names(RG.SPEED_TARGET), (HM.BATTLE,)); self.assertEqual(HM.editor_names('msg'), ())
        self.assertNotIn(HM.BATTLE, HM.editor_names(RG.SCREEN_TARGET))                                                               # no longer in "On-screen buttons and D-pad"


if __name__ == '__main__':
    unittest.main(verbosity=2)
