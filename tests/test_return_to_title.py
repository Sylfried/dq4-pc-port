"""Test of the return to the title screen: Pause menu > "Return to title screen" = the game's original box (its text, Yes / No), then the game's fade to black, then the title.

    python3 tests/test_return_to_title.py [--apk <folder of the patched APKs> --saves <saves folder>]
(or DQ_APK and DQ_SAVES; without them only parts 1 and 2 run). Part 3 loads the real engine (about 1 minute).

Part 1 (no engine): the Pause menu line. It closes the menu and asks the game to return to the title (no more confirmation page in the Pause menu: the question is the game's); it is grayed out
when the game is neither in a town nor on the world map.
Part 2 (simulated engine): `Engine.request_return_to_title` and the two moments played around GameUpdate (`_return_to_title_before` / `_return_to_title_after`): the engine calls in the order of the original Settings menu (TownMenu_OPERATION_SETTING::menuUpdate, state 5),
"No" changes nothing, "Yes" erases bank 4 then launches Global::startTitle; a box closed without an answer releases the player.
Part 3 (real engine, in a town): the box opens and stays open; "No" (arrow toward Non then A) closes it without launching the title; "Yes" (A, original cursor on Oui) launches killbank then startTitle in the very
same step of GameUpdate and the fade to black is gradual (30 frames, never a jump), then the title map loads.
"""
import argparse, inspect, os, struct, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
pyglet.options['shadow_window'] = False                     # (no display needed: nothing is drawn)
from dq456_pc.persistence import settings as RG
from dq456_pc.menus import pause as PA
from dq456_pc.core import engine as ENGINE

K = pyglet.window.key
APK = os.environ.get('DQ_APK'); SAVES = os.environ.get('DQ_SAVES'); REST = sys.argv[1:]
if __name__ == '__main__':
    _ap = argparse.ArgumentParser(); _ap.add_argument('--apk'); _ap.add_argument('--saves'); _a, REST = _ap.parse_known_args()
    APK = _a.apk or APK; SAVES = _a.saves or SAVES
CAPTION = 'settings.return_title_screen'
PAD_DOWN = 1; PAD_A = 0x10                                    # game gamepad sent to the menus: down 1, up 2, right 4, left 8, A 16, B 32 (Game._menu_input); the engine arranges Yes / No in one column (1 x 2 grid): the viewer's "right" goes out as "down"


class FakeSound:
    active = True; listening = False


class FakeGame:
    """What the Pause menu asks of the window."""
    def __init__(self, possible=True):
        self.reg = RG.Settings(os.path.join(tempfile.mkdtemp(prefix='retour_titre_'), 'settings.json'))
        self.sound = FakeSound(); self.args = types.SimpleNamespace(cache='/inexistant'); self.width, self.height = 1280, 720; self.mouse = None
        self.calls = []; self.possible = possible
    def window_names(self): return {}
    def pause_game(self, yes): self.calls.append(('pause_jeu', yes))
    def back_to_title(self): self.calls.append('titre')
    def ask_quit(self): self.calls.append('quitter')
    def quit_game(self): self.calls.append('quit')
    def back_to_title_possible(self): return self.possible


def menu(possible=True):
    J = FakeGame(possible); p = PA.Pause(J); p.opened = True; p.stack = ['root']
    return J, p


def line(p): return next(e for e in p._entries() if e.get('l') == CAPTION)


def choose(p):
    """Places the root cursor on the return-to-title line."""
    p.selected['root'] = [e.get('l') for e in p._entries()].index(CAPTION)


# ---------------------------------------------------------------------------------------------------------------------------------- 1. the Pause menu
class MenuLine(unittest.TestCase):
    def test_line_is_just_above_quit(self):
        """Last line of the root menu before "Quit the game", which is just below it."""
        J, p = menu(); libs = [e['l'] for e in p._entries() if e['t'] != 'sep']
        self.assertEqual(libs[-2:], [CAPTION, 'settings.quit_game'])

    def test_no_more_pause_menu_confirmation_page(self):
        self.assertFalse(hasattr(PA.Pause, '_e_titre'))                                                  # the question is the game's (original box), not a menu page
        src = inspect.getsource(PA.Pause); self.assertNotIn("_go('titre')", src); self.assertNotIn("titles['titre']", src)

    def test_validate_closes_the_menu_and_requests_return_to_game(self):
        J, p = menu(); choose(p); p.key_press(K.RETURN)
        self.assertFalse(p.opened); self.assertEqual([a for a in J.calls if a == 'titre'], ['titre'])
        self.assertIn(('pause_jeu', False), J.calls)                                                    # the game resumes: it is the one that asks the question

    def test_line_action_is_the_click_action(self):
        J, p = menu(); line(p)['ok'](); self.assertFalse(p.opened); self.assertEqual(J.calls.count('titre'), 1)

    def test_grayed_out_outside_town_and_world_map(self):
        J, p = menu(possible=False); e = line(p)
        self.assertTrue(p._inactive(e)); self.assertFalse(p._active(e)); self.assertTrue(e.get('hint'))   # grayed out, with its explanation
        choose(p); p.key_press(K.RETURN)
        self.assertTrue(p.opened); self.assertNotIn('titre', J.calls)                                  # nothing is sent

    def test_active_when_possible(self):
        J, p = menu(possible=True); self.assertFalse(p._inactive(line(p)))

    def test_quit_through_the_game_box(self):
        """"Quit the game": where the game's box answers, the menu closes and the window asks the game's question (ask_quit: b0834000.mpt#96); elsewhere, the menu's Yes / No page."""
        J, p = menu(possible=True); e = next(x for x in p._entries() if x['l'] == 'settings.quit_game'); e['ok']()
        self.assertFalse(p.opened); self.assertEqual([a for a in J.calls if a in ('quitter', 'quit')], ['quitter'])
        J, p = menu(possible=False); e = next(x for x in p._entries() if x['l'] == 'settings.quit_game'); e['ok']()
        self.assertTrue(p.opened); self.assertEqual(p.screen_page, 'quit'); self.assertNotIn('quitter', J.calls)
        from dq456_pc.window import game as F
        self.assertIn('quit_app=True', inspect.getsource(F.Game.ask_quit)); self.assertIn('quit_requested', inspect.getsource(F.Game._step))

    def test_game_knows_when_possible(self):
        from dq456_pc.window import game as F
        src = inspect.getsource(F.Game.back_to_title_possible)
        self.assertIn('PART_TOWN', src); self.assertIn('PART_FIELD', src); self.assertIn('TITLE_MAP', src); self.assertNotIn('PART_BATTLE', src)
        self.assertIn('request_return_to_title', inspect.getsource(F.Game.back_to_title))


# ---------------------------------------------------------------------------------------------------------------------------------- 2. the engine (simulated)
class FakeCountdownCore:
    """Replaces emu_core: records the engine calls (symbol names), keeps a word memory."""
    def __init__(self): self.calls = []; self.memory = {}; self.is_open = True
    def export(self, name_str): return 0x5000 if name_str == 'gTownMenu_MESSAGE' else 0x9000
    def call(self, address, *args, label=None):
        self.calls.append((address, args))
        return (1 if self.is_open else 0) if address == '_ZN8MenuBase6isOpenEv' else 0
    def mem(self, addr, n): return self.memory.get(addr, bytes(n))
    def mem_w(self, addr, raw): self.memory[addr] = bytes(raw); self.calls.append(('mem_w', (addr, bytes(raw))))
    def names(self): return [a[0] for a in self.calls if isinstance(a[0], str) and a[0] != 'mem_w']


def simulated_engine(part=ENGINE.PART_TOWN):
    m = ENGINE.Engine.__new__(ENGINE.Engine); m.core = FakeCountdownCore(); m.E = lambda s: s; m._global = lambda: 0x7000
    m.state = types.SimpleNamespace(part=part, game_map='mak1f1'); m.back_to_title_state = None
    return m


def answer(m, v): m.core.memory[0x5000 + ENGINE.MESSAGE_RESULT] = struct.pack('<I', v)


class ReturnMachine(unittest.TestCase):
    def test_original_menu_constants(self):
        self.assertEqual(ENGINE.RETURN_TITLE_MESSAGES['dq4'], (0xcba2f, 0xcba33)); self.assertEqual(ENGINE.MESSAGE_RESULT, 0x10)
        self.assertEqual((ENGINE.MSG_RETURN_TITLE, ENGINE.MSG_QUIT_APP), ENGINE.RETURN_TITLE_MESSAGES[ENGINE.GM.profile().key])

    def test_each_game_asks_with_its_own_message(self):
        """DQ V showed "ERROR 834095@" in the box: the question's number is DQ IV's; each game's b0834000.mpt has its own (the file's last message is the "quit the application" question)."""
        self.assertEqual({k: tuple(n - 834003 for n in v) for k, v in ENGINE.RETURN_TITLE_MESSAGES.items()}, {'dq4': (92, 96), 'dq5': (75, 77), 'dq6': (48, 50)})

    def test_box_of_dq6(self):
        """DQ VI names its town message box gCommonMenuMessage (no gTownMenu_MESSAGE): the request crashed the step."""
        m = simulated_engine(); m.core.export = lambda n: {'_ZN4menu18gCommonMenuMessageE': 0x6000}.get(n)
        self.assertEqual(m._title_box(), 0x6000)

    def test_camera_of_the_start_menu_after_a_return(self):
        """DQ V's title only gives the camera a target: after a return to the title its start menu showed the scene from the last town's camera; the engine's starting position is put back."""
        m = simulated_engine(); m.back_to_title_state = 'fading'; m._title_steps = 0; m.boot_cam_pos = (0.0, -100.0, 0.0)
        m.state.cam_pos = (2.25, 28.9, -17.7); m._return_to_title_after(); self.assertEqual(m.state.cam_pos, (2.25, 28.9, -17.7))          # (still on the town's map)
        m.state.game_map = ENGINE.TITLE_MAP; m._return_to_title_after()
        self.assertIsNone(m.back_to_title_state); self.assertEqual(m.state.cam_pos, (0.0, -100.0, 0.0))

    def test_only_in_town_and_on_the_map(self):
        for part, expected in ((ENGINE.PART_TOWN, True), (ENGINE.PART_FIELD, True), (ENGINE.PART_BATTLE, False), (ENGINE.PART_CASINO, False), (ENGINE.PART_BESTIARY, False), (ENGINE.PART_INITIAL, False)):
            m = simulated_engine(part); self.assertEqual(m.request_return_to_title(), expected, part); self.assertEqual(m.back_to_title_state, 'requested' if expected else None)

    def test_a_single_request_at_a_time(self):
        m = simulated_engine(); self.assertTrue(m.request_return_to_title()); self.assertFalse(m.request_return_to_title())

    def test_opening_like_original_menu(self):
        m = simulated_engine(); m.request_return_to_title(); answer(m, 2); m._return_to_title_before()               # (an old answer does not count: reset to 0)
        self.assertEqual(m.back_to_title_state, 'dialog')
        self.assertEqual(m.core.names(), ['_ZN3cmn11GameManager12getSingletonEv', '_ZN3cmn13PlayerManager7setLockEb', '_ZN16TownMenu_MESSAGE18openMessageForMENUEv', '_ZN16TownMenu_MESSAGE10addMessageEi',
                                         '_ZN16TownMenu_MESSAGE8setYesNoEv', '_ZN16TownMenu_MESSAGE19setYesNoSuperCancelEb'])
        a = {x[0]: x[1] for x in m.core.calls if isinstance(x[0], str)}
        self.assertEqual(a['_ZN3cmn13PlayerManager7setLockEb'], (1,)); self.assertEqual(a['_ZN16TownMenu_MESSAGE10addMessageEi'], (0x5000, ENGINE.MSG_RETURN_TITLE)); self.assertEqual(a['_ZN16TownMenu_MESSAGE19setYesNoSuperCancelEb'], (0x5000, 0))
        self.assertEqual(m.core.memory[0x5000 + ENGINE.MESSAGE_RESULT], bytes(4))

    def test_nothing_before_the_request(self):
        m = simulated_engine(); m._return_to_title_before(); m._return_to_title_after(); self.assertEqual(m.core.calls, []); self.assertIsNone(m.back_to_title_state)

    def test_waiting_for_answer(self):
        m = simulated_engine(); m.request_return_to_title(); m._return_to_title_before(); m.core.calls.clear(); answer(m, 0); m._return_to_title_after()
        self.assertEqual(m.back_to_title_state, 'dialog'); self.assertEqual(m.core.names(), ['_ZN8MenuBase6isOpenEv'])                                # only reading the box state

    def test_no_changes_nothing(self):
        m = simulated_engine(); m.request_return_to_title(); m._return_to_title_before(); m.core.calls.clear(); answer(m, 2); m._return_to_title_after()
        self.assertIsNone(m.back_to_title_state); n = m.core.names()
        self.assertIn('_ZN8MenuBase5closeEv', n); self.assertNotIn('_ZN6Global10startTitleEv', n); self.assertNotIn('_ZN7profile8SaveLoad8killbankEib', n)
        self.assertEqual([x[1] for x in m.core.calls if x[0] == '_ZN3cmn13PlayerManager7setLockEb'], [(0,)])               # the player is released

    def test_yes_erases_bank_4_then_launches_title(self):
        m = simulated_engine(); m.request_return_to_title(); m._return_to_title_before(); m.core.calls.clear(); answer(m, 1); m._return_to_title_after()
        self.assertEqual(m.back_to_title_state, 'fading'); n = m.core.names()
        self.assertLess(n.index('_ZN7profile8SaveLoad8killbankEib'), n.index('_ZN6Global10startTitleEv')); self.assertEqual(n[-1], '_ZN6Global10startTitleEv')
        self.assertEqual([x[1] for x in m.core.calls if x[0] == '_ZN7profile8SaveLoad8killbankEib'], [(4, 0)])
        self.assertEqual([x[1] for x in m.core.calls if x[0] == '_ZN3cmn13PlayerManager7setLockEb'], [(1,)])

    def test_the_return_lasts_until_the_title(self):
        """"Yes": the return stays under way ('fading': no screen buttons, no second request, not yet "on the title") through the fade and the black screen, until the title's map; a safeguard ends it
        TITLE_RETURN_STEPS steps later if the title never comes."""
        m = simulated_engine(); m.request_return_to_title(); m._return_to_title_before(); answer(m, 1); m._return_to_title_after(); m.core.calls.clear()
        for _ in range(40): m._return_to_title_after(); self.assertEqual(m.back_to_title_state, 'fading')
        self.assertEqual(m.core.calls, []); self.assertFalse(m.request_return_to_title())
        m.state.game_map = ENGINE.TITLE_MAP; m._return_to_title_after(); self.assertIsNone(m.back_to_title_state)
        m = simulated_engine(); m.request_return_to_title(); m._return_to_title_before(); answer(m, 1); m._return_to_title_after()
        for _ in range(ENGINE.TITLE_RETURN_STEPS): m._return_to_title_after()
        self.assertEqual(m.back_to_title_state, 'fading'); m._return_to_title_after(); self.assertIsNone(m.back_to_title_state)

    def test_no_screen_buttons_during_the_return(self):
        """The screen buttons stay hidden from the game's box to the title: at the end of the fade the player was free again on the black screen for a step or two, and they flashed."""
        from dq456_pc.menus import hud_mobile as HM
        eng = types.SimpleNamespace(state=types.SimpleNamespace(effect=None, part=ENGINE.PART_TOWN), flags=lambda: 0x38, back_to_title_state=None)
        b = HM.Buttons.__new__(HM.Buttons); b.J = types.SimpleNamespace(pause=types.SimpleNamespace(opened=False), engine=eng, reg={'buttons': True, 'dpad': True, 'rotation_bar': False, 'speed_button': True}, map_open=False)
        self.assertIn(HM.DPAD, b.visible_ones()); self.assertTrue(b.allowed('menu'))
        for st in ('requested', 'dialog', 'fading'): eng.back_to_title_state = st; self.assertEqual(b.visible_ones(), (), st); self.assertFalse(b.allowed('menu'), st)

    def test_no_screen_buttons_on_the_title_and_the_start_menu(self):
        """After a return to the title the engine's flags are still those of the place the player left (0x38: free, pad present, map allowed): DQ VI showed the buttons and the D-pad over its
        title, DQ V over its start menu. The title's map in the town part and the start menu's part never show them."""
        from dq456_pc.menus import hud_mobile as HM
        st = types.SimpleNamespace(effect=None, part=ENGINE.PART_TOWN, game_map='mak1f1'); eng = types.SimpleNamespace(state=st, flags=lambda: 0x38, back_to_title_state=None)
        b = HM.Buttons.__new__(HM.Buttons); b.J = types.SimpleNamespace(pause=types.SimpleNamespace(opened=False), engine=eng, reg={'buttons': True, 'dpad': True, 'rotation_bar': False, 'speed_button': True}, map_open=False)
        self.assertIn(HM.DPAD, b.visible_ones())
        st.game_map = ENGINE.TITLE_MAP; self.assertEqual(b.visible_ones(), ()); self.assertFalse(b.allowed('menu'))
        st.part = ENGINE.PART_INITIAL; st.game_map = 'mak1f1'; self.assertEqual(b.visible_ones(), ()); self.assertFalse(b.allowed('map'))
        st.part = ENGINE.PART_FIELD; st.game_map = ENGINE.TITLE_MAP; self.assertIn(HM.DPAD, b.visible_ones())          # (a game loaded straight onto the world map keeps the title's town map loaded)

    def test_system_busy_flag_hides_the_buttons(self):
        """DQ V / VI raise bit 0x80 of the global flag while a message, a menu, a shop or a map link has the hand (CommandObjectDefine*System::set*): Unity's TouchPad.IsEnable masks it
        (0xC4 against DQ IV's 0x47); without it the buttons flashed during the fades around those moments. DQ IV has no such bit."""
        from dq456_pc.menus import hud_mobile as HM
        self.assertEqual(ENGINE.SYSTEM_BUSY_FLAG, 0x80 if ENGINE.ENGINE_V2 else 0); self.assertEqual(ENGINE.HUD_HIDDEN_FLAGS, 0x30047 | ENGINE.SYSTEM_BUSY_FLAG)
        self.assertEqual(ENGINE.NOT_FREE_FLAGS, ENGINE.PLAYER_LOCKED_FLAG | ENGINE.SYSTEM_BUSY_FLAG)
        st = types.SimpleNamespace(effect=None, part=ENGINE.PART_TOWN, game_map='mak1f1'); flags = [0x38]; eng = types.SimpleNamespace(state=st, flags=lambda: flags[0], back_to_title_state=None)
        b = HM.Buttons.__new__(HM.Buttons); b.J = types.SimpleNamespace(pause=types.SimpleNamespace(opened=False), engine=eng, reg={'buttons': True, 'dpad': True, 'rotation_bar': False, 'speed_button': True}, map_open=False)
        self.assertIn('menu', b.visible_ones())
        flags[0] = 0x38 | ENGINE.HUD_HIDDEN_FLAGS & 0x80
        self.assertEqual(bool(b.visible_ones()), not ENGINE.ENGINE_V2); self.assertEqual(b.allowed('menu'), not ENGINE.ENGINE_V2)

    def test_no_screen_buttons_under_a_fade(self):
        """DQ VI, map change: the exit fade ends (flags 0x78), the engine frees the player for one step on the black screen (0x38, no fade in progress), then the next map fades in (0x39).
        The buttons appeared for that step. They stay hidden while a fade plane is on screen, held at black included, and during the black screen that waits for a scene."""
        from dq456_pc.menus import hud_mobile as HM
        gone = dict(a=0.0, step=0.0, n=0)
        st = types.SimpleNamespace(effect=None, part=ENGINE.PART_TOWN, game_map='m01uk1f1', fade=dict(gone), background_fade=dict(gone), load_wait=None)
        eng = types.SimpleNamespace(state=st, flags=lambda: 0x38, back_to_title_state=None)
        b = HM.Buttons.__new__(HM.Buttons); b.J = types.SimpleNamespace(pause=types.SimpleNamespace(opened=False), engine=eng, reg={'buttons': True, 'dpad': True, 'rotation_bar': False, 'speed_button': True}, map_open=False)
        self.assertIn(HM.DPAD, b.visible_ones()); self.assertTrue(b.allowed('menu'))
        for plane in (dict(a=1.0, step=0.0, n=0), dict(a=0.5, step=-0.033, n=15), dict(a=0.0, step=0.033, n=30)):          # held at black, going back down, starting to rise
            st.fade = plane; self.assertEqual(b.visible_ones(), (), plane); self.assertFalse(b.allowed('menu'), plane)
        st.fade = dict(gone); st.background_fade = dict(a=0.3, step=0.0, n=0); self.assertEqual(b.visible_ones(), ())
        st.background_fade = dict(gone); st.load_wait = {'n': 3}; self.assertEqual(b.visible_ones(), ())
        st.load_wait = None; self.assertIn(HM.DPAD, b.visible_ones())

    def test_quit_box(self):
        """The same box asks to quit the application (MSG_QUIT_APP = b0834000.mpt#96: "Voulez-vous vraiment quitter l'application ?"): "Yes" closes it and asks the window to quit (nothing of the
        return to the title: no killbank, no startTitle); "No" releases the player as for the title."""
        self.assertEqual(ENGINE.RETURN_TITLE_MESSAGES['dq4'][1], 834003 + 96)
        m = simulated_engine(); self.assertTrue(m.request_return_to_title(quit_app=True)); m._return_to_title_before()
        self.assertEqual({x[0]: x[1] for x in m.core.calls if isinstance(x[0], str)}['_ZN16TownMenu_MESSAGE10addMessageEi'], (0x5000, ENGINE.MSG_QUIT_APP))
        m.core.calls.clear(); answer(m, 1); m._return_to_title_after(); n = m.core.names()
        self.assertTrue(m.quit_requested); self.assertIsNone(m.back_to_title_state); self.assertIn('_ZN8MenuBase5closeEv', n)
        self.assertNotIn('_ZN6Global10startTitleEv', n); self.assertNotIn('_ZN7profile8SaveLoad8killbankEib', n)
        m = simulated_engine(); m.request_return_to_title(quit_app=True); m._return_to_title_before(); m.core.calls.clear(); answer(m, 2); m._return_to_title_after()
        self.assertFalse(m.quit_requested); self.assertEqual([x[1] for x in m.core.calls if x[0] == '_ZN3cmn13PlayerManager7setLockEb'], [(0,)])
        m.request_return_to_title(); m._return_to_title_before()                                                     # (the next request is the return to the title again)
        self.assertIn((0x5000, ENGINE.MSG_RETURN_TITLE), [x[1] for x in m.core.calls if x[0] == '_ZN16TownMenu_MESSAGE10addMessageEi'])

    def test_closed_box_without_answer_releases_player(self):
        m = simulated_engine(); m.request_return_to_title(); m._return_to_title_before(); m.core.calls.clear(); m.core.is_open = False; answer(m, 0); m._return_to_title_after()
        self.assertIsNone(m.back_to_title_state); self.assertEqual([x[1] for x in m.core.calls if x[0] == '_ZN3cmn13PlayerManager7setLockEb'], [(0,)]); self.assertNotIn('_ZN6Global10startTitleEv', m.core.names())
        self.assertTrue(m.request_return_to_title())                                                                        # and the question can be asked again

    def test_two_moments_are_in_the_engine_step(self):
        """The title fade is a packet read with those of the step: startTitle must be launched between `pk.begin()` and `pk.packets()`, around GameUpdate (otherwise the fade is lost and the screen jumps to black)."""
        src = inspect.getsource(ENGINE.Engine.step)
        i0 = src.index('self.pk.begin()'); i1 = src.index('_return_to_title_before()'); i2 = src.index("'GameUpdate'"); i3 = src.index('_return_to_title_after()'); i4 = src.index('self.pk.packets()')
        self.assertTrue(i0 < i1 < i2 < i3 < i4)


# ---------------------------------------------------------------------------------------------------------------------------------- 3. the real engine
@unittest.skipUnless(APK and SAVES, 'real engine: --apk and --saves (or DQ_APK and DQ_SAVES)')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import unicorn; from dq456_pc.persistence import savestates as SS
        cls.SS = SS; eng = cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_retour_titre_')); c = cls.c = eng.core
        eng.load_save(1)
        for _ in range(200): eng.step(0, 0)
        cls.part0 = eng.state.part; cls.map0 = eng.state.game_map
        def counter(name_str):
            addr = c.export(name_str); n = []; c.uc.hook_add(unicorn.UC_HOOK_CODE, lambda u, a, sz, ud: n.append(eng.frames), None, addr, addr); return n
        cls.title_screen = counter('_ZN6Global10startTitleEv'); cls.kill = counter('_ZN7profile8SaveLoad8killbankEib'); c.uc.ctl_flush_tb()
        cls.initial = SS.snapshot(eng)

    def setUp(self):
        self.SS.apply(self.eng, self.initial); self.eng.back_to_title_state = None; self.title_screen.clear(); self.kill.clear()

    def box(self): return self.c.export('gTownMenu_MESSAGE')
    def is_open(self): return bool(self.c.call(self.c.export('_ZN8MenuBase6isOpenEv'), self.box()) & 1)
    def answer(self): return struct.unpack('<I', self.c.mem(self.box() + ENGINE.MESSAGE_RESULT, 4))[0]

    def step(self, n=1, p=0, d=0):
        for _ in range(n): self.eng.step(p, d); self.eng.ui.damage = []; p = d = 0

    def key_press(self, pad):
        """A gamepad button sent to the engine menu that has the input focus (like Game._menu_input: [1, -1, gamepad]), released on the next frame, then 8 rest frames."""
        port = self.eng.active_menu(); self.assertIsNotNone(port, 'no engine menu waits for a key')
        self.eng.send_menu(port, 1, -1, pad); self.step(1); self.eng.send_menu(port, 1, -1, 0); self.step(1); self.step(8)

    def open_box(self):
        self.assertTrue(self.eng.request_return_to_title()); self.step(150)                                    # the text is written, then Yes / No
        self.assertEqual(self.eng.back_to_title_state, 'dialog'); self.assertTrue(self.is_open()); self.assertEqual(self.answer(), 0); self.assertIsNotNone(self.eng.active_menu())           # Yes / No waits

    def test_1_box_opens_and_waits(self):
        self.open_box(); self.step(120)
        self.assertEqual(self.eng.back_to_title_state, 'dialog'); self.assertTrue(self.is_open()); self.assertEqual(self.title_screen, [])          # it waits: nothing happens without an answer

    def test_2_no_changes_nothing(self):
        self.open_box(); self.key_press(PAD_DOWN); self.key_press(PAD_A); self.step(30)
        self.assertIsNone(self.eng.back_to_title_state); self.assertFalse(self.is_open())
        self.assertEqual(self.title_screen, []); self.assertEqual(self.kill, [])                                      # neither bank erased, nor title
        self.assertEqual(self.eng.state.part, self.part0); self.assertEqual(self.eng.state.game_map, self.map0)
        self.assertLess(self.eng.state.fade['a'], 0.01)                                                        # no fade

    def test_3_yes_starts_fade_then_title(self):
        self.open_box(); self.key_press(PAD_A)                                                          # the original cursor is on "Yes"
        alphas = []
        for _ in range(140): self.step(1); alphas.append(self.eng.state.fade['a'])
        self.assertEqual(len(self.title_screen), 1); self.assertEqual(len(self.kill), 1); self.assertLessEqual(self.kill[0], self.title_screen[0])        # bank 4 erased then title, once each
        jumps = [b - a for a, b in zip(alphas, alphas[1:])]
        self.assertLess(max(jumps), 0.1, 'the fade jumps to black: %.3f' % max(jumps))                      # gradual (one thirty-third per frame), never all at once
        self.assertGreaterEqual(sum(1 for a in alphas if 0.05 < a < 0.95), 20)                               # about thirty fade frames
        self.assertGreater(max(alphas), 0.99)
        self.assertFalse(self.is_open())

    def test_4_request_after_no_is_possible(self):
        self.open_box(); self.key_press(PAD_DOWN); self.key_press(PAD_A); self.step(30)
        self.open_box()                                                                                   # and the same question is asked again


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + REST)
