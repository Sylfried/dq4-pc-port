"""Real battle replay from the history (redone): the state at the start of a battle (its entry cascade) + every input the engine got, replayed by the engine itself like a real battle: the player
turns the messages, the recorded menu choices are sent to the menus that open (nothing is waited for, nothing is shown).

Checks:
  1. without engine: the replay file is kept with the battle (file round trip, favorite copy), deleted when the battle drops out of the latest 100 and is no favorite; the window opens the replay rather than the
     messages when there is one; the choice script keeps the menu messages only (glued release, menu that had the input); ReplayMixin sends each choice to the menu it was made in, stops a moment after the
     battle's end (or when nothing can answer a menu), puts the game back and reopens the history on the same battle;
  2. with the real engine (DQ_APK, DQ_SAVES): a battle recorded by History from its entry cascade (snapshot + inputs, file written) replays with the SAME messages, damage and outcome whatever the pace of the player
     (random message turns, menus answered at once): the engine's random draws do not depend on the pace; the game put back afterwards has the experience and gold it had; no save file is written
     during the replay; the history does not change.

    python3 tests/test_battle_replay.py
"""
import os, random, shutil, struct, sys, tempfile, threading, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc import language as LG
LG.select_language('fr')
from dq456_pc.core import history as HI
from dq456_pc.menus import ui_history as UH
from dq456_pc.window import battle_replay as BRP

ADV = '0123456789ab'


def battle(t=900):
    return {'t': t, 'outcome': 'victory', 'gold': 3, 'xp': 4, 'enemies': [{'name': 'Gluant', 'total': 1, 'defeated': 1}]}


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='rp_'); self.addCleanup(shutil.rmtree, self.d, True)
        self.h = HI.History(os.path.join(self.d, 'fav.json'), lambda: 1.0); self.h.set_adventure(ADV)

    def touch(self, rel):
        p = os.path.join(self.d, HI.HISTORY_FOLDER, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'wb').close(); return p

    def test_round_trip_and_favorite(self):
        e = self.h.add_battle(battle()); e.replay = ADV + '/aaaaaaaaaaaa.dqs'; self.touch(e.replay); self.h.toggle_favorite(e); self.h.store(True)
        h2 = HI.History(os.path.join(self.d, 'fav.json'), lambda: 1.0); h2.set_adventure(ADV)
        self.assertEqual((h2.battles[0].replay, h2.favorites[0].replay), (e.replay, e.replay)); self.assertIsNotNone(h2.replay_path(h2.battles[0]))
        bad = HI.Element.from_dict({'k': 'c', 'id': None, 't': 1, 'enemies': [], 'outcome': 'victory', 'replay': '../../x.dqs'}, 1, recent=True)
        self.assertIsNone(bad.replay)                                                                    # (never a path out of the history folder)

    def test_files_deleted_with_their_battle(self):
        first = self.h.add_battle(battle(1)); first.replay = ADV + '/bbbbbbbbbbbb.dqs'; p1 = self.touch(first.replay)
        kept = self.h.add_battle(battle(2)); kept.replay = ADV + '/cccccccccccc.dqs'; p2 = self.touch(kept.replay); self.h.toggle_favorite(kept)
        for i in range(HI.MAX_BATTLES): self.h.add_battle(battle(10 + i))
        self.assertFalse(os.path.exists(p1)); self.assertTrue(os.path.exists(p2))                         # out of the latest 100: deleted, unless it is a favorite
        self.h.toggle_favorite(self.h.favorites[0]); self.assertFalse(os.path.exists(p2))     # the favorite removed: its replay too

    def test_window_prefers_the_replay(self):
        h = HI.History(None, lambda: 1.0); e = h.add_battle(battle(), [{'text': 'A !', 'kind': 'g', 'val': None, 'cat': 'c', 't': 1}]); e.replay = ADV + '/dddddddddddd.dqs'
        asked = []
        P = types.SimpleNamespace(mouse_mode=False, mouse_pos=None, back=lambda: None, shutdown=lambda: None, _repeat=lambda *a: None)
        P.J = types.SimpleNamespace(history=h, reg=types.SimpleNamespace(action_of=lambda s: 'A', __getitem__=None), height=720, start_battle_replay=lambda el: asked.append(el) or True)
        v = UH.HistoryView(P); v.enter(UH.O_BATTLES); self.assertTrue(v.open_rewind()); self.assertEqual((asked, v.rewind), ([e], None))
        P.J.start_battle_replay = lambda el: False; self.assertTrue(v.open_rewind()); self.assertIsNotNone(v.rewind)       # (replay impossible: the messages)


class FakeWindow(BRP.ReplayMixin):
    def __init__(self, menu=None, ended=False):
        self.sent = []; self.applied = []; self.toasts = []; self.scroll_applied = 0; self.menu = menu
        self.engine = types.SimpleNamespace(scroll_mode=0, impose_scroll_mode=lambda c: setattr(self.engine, 'scroll_mode', c), send_menu=lambda *m: self.sent.append(m), core=types.SimpleNamespace(read_only=False), active_menu=lambda: self.menu,
                                            state=types.SimpleNamespace(part=0xd, effect=None, load_wait=None), battle_intro=True,
                                            battle_sensor=types.SimpleNamespace(events=[('start',)], tracking=object(), outputs=[1]), sensor=types.SimpleNamespace(drain=lambda: [], events=[], output=[]),
                                            record_inputs=lambda on: None)
        self.history = types.SimpleNamespace(replaying=False, flush_recording=lambda eng: None, replay_path=lambda e: 'x.dqs')
        hv = types.SimpleNamespace(elements=[], change_tab=lambda i: None, go_to=lambda i: None)
        self.pause = types.SimpleNamespace(shutdown=lambda leaving=True: self.applied.append(('closed', leaving)), open_menu=lambda page=None: self.applied.append(('menu', page)), open_history=lambda: self.applied.append(('menu', 'history')), hist=hv,
                                           view_state=lambda: 'VIEW', restore_view=lambda v: self.applied.append(('menu', v)))
        self.ref_effect = None; self.effect_tex_ready = False
    def _complete_savestate(self): return 'BACK'
    def _apply_savestate(self, d): self.applied.append(d)
    def _draw_scene(self): self.applied.append('scene drawn')
    def _clone_screen(self, battle=True): self.applied.append('screen copied')
    def apply_scroll(self): self.scroll_applied += 1
    def toast(self, t, **k): self.toasts.append(t)


STEPS = [(0, 0, [], 0, None), (0, 16, [], 0, None),                                                      # waiting, a message page turned by the player
         (0, 0, [(5, 1, 2, 16)], 0, 5), (0, 0, [(5, 1, -1, 0)], 0, 5),                                    # a choice in menu 5 and its release at the very next step
         (0, 0, [], 0, None), (0, 0, [], 0, None), (0, 16, [], 0, None),
         (0, 0, [(7, 1, 0, 16), (7, 1, -1, 0)], 0, 7)]                                                    # a choice in menu 7 (with its release in the same step)


class TestScript(unittest.TestCase):
    def test_choice_script_keeps_the_choices_only(self):
        self.assertEqual(BRP.choice_script(STEPS), [([(5, 1, 2, 16)], 5, False), ([(5, 1, -1, 0)], 5, True), ([(7, 1, 0, 16), (7, 1, -1, 0)], 7, False)])
        self.assertEqual(BRP.choice_script([(0, 0, [(5, 1, 2, 16)], 0)]), [([(5, 1, 2, 16)], BRP.ANY_MENU, False)])      # (a file: no menu recorded)

    def test_files_from_before_have_four_values(self):
        self.assertEqual(BRP.choice_script([(0, 0, [], 0), (0, 0, [(3, 1, -1, 16)], 0), (0, 0, [(3, 1, -1, 0)], 0)]), [([(3, 1, -1, 16)], BRP.ANY_MENU, False), ([(3, 1, -1, 0)], BRP.ANY_MENU, True)])


class TestMixin(unittest.TestCase):
    def start(self, w):
        real_read = BRP.SS.read; BRP.SS.read = lambda p: {'state': 1, 'battle_inputs': STEPS}
        try: return w.start_battle_replay('battle')
        finally: BRP.SS.read = real_read

    def test_choices_go_to_their_menu_then_the_end(self):
        w = FakeWindow(menu=None); self.assertTrue(self.start(w))
        self.assertEqual((w.applied, w.history.replaying, w.engine.core.read_only, w.scroll_applied), ([('closed', False), 'scene drawn', 'screen copied', {'state': 1}], True, True, 1))
        w.applied = [{'state': 1}]
        w.replay_feed(); self.assertEqual(w.sent, [])                                                       # (no menu has the input: nothing is sent, the player is not waited for)
        w.menu = 7; w.replay_feed(); self.assertEqual((w.sent, w._replay['starved']), ([], 1))              # (another menu: it waits for its own choice)
        w.menu = 5; w.replay_feed(); self.assertEqual(w.sent, [(5, 1, 2, 16)])
        w.menu = None; w.replay_feed(); self.assertEqual(w.sent[-1], (5, 1, -1, 0))                         # (the release: the very next step, whatever the menu)
        w.menu = 7; w.replay_feed(); self.assertEqual(w.sent[-2:], [(7, 1, 0, 16), (7, 1, -1, 0)]); self.assertEqual(w._replay['starved'], 0)
        self.assertFalse(w.replay_over())
        w.engine.battle_sensor.events.append(('end', False, False)); self.assertFalse(w.replay_over())      # (the engine's "end": a few steps still play)
        for _ in range(BRP.REPLAY_TAIL): self.assertFalse(w.replay_over())
        self.assertTrue(w.replay_over())
        w.end_battle_replay()
        self.assertEqual(w.applied[1:], ['BACK', ('menu', 'VIEW')]); self.assertFalse(w.history.replaying); self.assertFalse(w.engine.core.read_only); self.assertFalse(w.engine.battle_intro)          # (the menus as they were)
        self.assertEqual((w.engine.battle_sensor.events, w.engine.battle_sensor.tracking, w.engine.battle_sensor.outputs), ([], None, []))

    def test_a_victory_ends_on_its_last_page(self):
        """A won battle ends on "X est vaincu.", the first page after the victory (BattleExecDefeatMonster::initialize): the engine holds on it (manual messages imposed), then, messages turned by themselves,
        the fade comes LAST_PAGE_STEPS steps later; "Manual": the player's key (replay_on_last_page). The rewards (experience, gold, items, levels) are never shown: the summary box has them."""
        for manual in (False, True):
            w = FakeWindow(); self.assertTrue(self.start(w)); w.engine.scroll_mode = 4 if manual else 0; out = w.engine.sensor.output; out += ['page'] * 3
            self.assertFalse(w.replay_over()); w.engine.battle_sensor.events.append(('victory',))
            self.assertFalse(w.replay_over()); self.assertEqual(w.engine.scroll_mode, 4); self.assertFalse(w.replay_on_last_page())          # (manual imposed: the engine will hold on the page)
            for _ in range(10): self.assertFalse(w.replay_over())
            out.append('Le rat volant est vaincu.'); self.assertTrue(w.replay_on_last_page())
            for _ in range(BRP.LAST_PAGE_STEPS): self.assertFalse(w.replay_over())
            self.assertEqual(w.replay_over(), not manual, manual)
            for _ in range(200): self.assertEqual(w.replay_over(), not manual)
            out.append("Ragnar reçoit 3 points d'expérience !"); self.assertTrue(w.replay_over())          # (a page after it: never expected, the replay ends anyway)
            w.end_battle_replay(); self.assertEqual(w.engine.scroll_mode, 0, 'the scroll mode of before the replay')
        w = FakeWindow(); self.start(w); w.engine.battle_sensor.events.append(('victory',))
        for _ in range(BRP.LAST_PAGE_MAX): self.assertFalse(w.replay_over())
        self.assertTrue(w.replay_over())                                                                    # (no page after the victory: the replay ends anyway)

    def test_cascade_starts_where_the_player_is(self):
        """the menus close, the screen as it is NOW is copied, then the battle's state is loaded; its entry cascade shatters that copy (not the place the battle was fought: no teleport)."""
        w = FakeWindow(); effect = {'duree': 57}
        w._apply_savestate = lambda d: (w.applied.append(d), setattr(w.engine.state, 'effect', effect))
        self.assertTrue(self.start(w))
        self.assertEqual(w.applied[:4], [('closed', False), 'scene drawn', 'screen copied', {'state': 1}])
        self.assertIs(w.ref_effect, effect); self.assertTrue(w.effect_tex_ready)

    def test_sky_keeps_the_real_clock_between_turns(self):
        """between two turns the engine runs at REPLAY_SKIP, but the scenery's own animations (the plains' sky turns once in 150 s) only take the steps of the real clock: the sky no longer jumps."""
        import inspect
        from dq456_pc.window import game as GM, field as FD
        self.assertIn('scenery_ticks', inspect.getsource(GM.Game._loop))
        ticks = []
        o = types.SimpleNamespace(scenery_ticks=2, objects=types.SimpleNamespace(tick=lambda: ticks.append(1) or set(), dirty_uv=set(), dirty_col=set()), palettes=None, ext_map=[], map_vl=[],
                                  engine=types.SimpleNamespace(state=types.SimpleNamespace(object_cmds=[])), map_name='btl_pl_d', n=0)
        for _ in range(5): FD.FieldMixin._map_objects(o)
        self.assertEqual(len(ticks), 2)

    def test_monsters_keep_the_real_clock_between_turns(self):
        """between two turns the engine runs ahead, but each monster's animation is put back, before each step, at the frame the real clock has reached (minus the one the step adds):
        no jump of the whole command phase. An animation that starts again by itself (looping, or followed by itself: the matœil's idle animation) wraps around; one that starts during the skip
        (a monster beginning its action) plays from its first frame at real pace; one that does not start again is left to end once the real clock reaches its last frame."""
        import struct
        mem = bytearray(BRP.MONSTER_COUNT * BRP.MONSTER_SIZE); base = 0x1000
        for i in range(BRP.MONSTER_COUNT): struct.pack_into('<i', mem, i * BRP.MONSTER_SIZE + 0xa6c, -1)
        def monster(i, anim, nxt, frame, n):
            b = i * BRP.MONSTER_SIZE; struct.pack_into('<2i', mem, b + 0x24, anim, nxt); struct.pack_into('<i', mem, b + 0xa6c, 7)
            o = b + 0x30 + anim * 0xb8; struct.pack_into('<i', mem, o + 0x44, n); struct.pack_into('<i', mem, o + 0xa8, frame)
        frame = lambda i, anim: struct.unpack_from('<i', mem, i * BRP.MONSTER_SIZE + 0x30 + anim * 0xb8 + 0xa8)[0]
        core = types.SimpleNamespace(export=lambda name: base if name == BRP.MONSTERS else None, mem=lambda a, n: bytes(mem[a - base:a - base + n]))
        def write(a, b): mem[a - base:a - base + len(b)] = b
        core.mem_w = write
        monster(0, 0, -1, 15, 17); monster(1, 2, 2, 3, 25); monster(2, 1, 0, 4, 30)                       # (0 loops; 1 is followed by itself; 2 goes on to animation 0 when it ends)
        fr = BRP.monster_frames(core); self.assertEqual({i: v[4] for i, v in fr.items()}, {0: True, 1: True, 2: False})
        held = {}
        BRP.hold_monsters(core, held, 0); self.assertEqual((frame(0, 0), frame(1, 2), frame(2, 1)), (14, 2, 3))          # (the step adds one: the frame the skip began with)
        BRP.hold_monsters(core, held, 3); self.assertEqual((frame(0, 0), frame(1, 2), frame(2, 1)), (0, 5, 6))           # (3 steps of real time: 15 + 3 = 18 -> 1 after the step, looping at 17)
        monster(1, 3, 0, 9, 25); BRP.hold_monsters(core, held, 4); self.assertEqual(frame(1, 3), 0)                     # (an action that began during the skip: from its start, now; never frame -1, the engine draws it before advancing it)
        BRP.hold_monsters(core, held, 7); self.assertEqual(frame(1, 3), 2)                                             # (then at the real clock's pace)
        monster(2, 1, 0, 28, 30); BRP.hold_monsters(core, held, 40); self.assertEqual(frame(2, 1), 28)                  # (past its last frame: left to end on its own)
        w = FakeWindow(); self.assertTrue(self.start(w)); w.engine.core = core
        w.replay_skip_step(True); self.assertIsNotNone(w._replay_skip); w.replay_skip_step(False); self.assertIsNone(w._replay_skip)

    def test_a_turn_at_the_game_clock_ends_the_skip(self):
        """"Manual" and "Normal": the turns are played at the game's clock (no battle step, so no replay_skip_step(False)); the loop itself ends the skip, otherwise the next one kept the frames
        and the start time of the first (measured in a replay at "Normal": from the second turn on, each monster jumped to the frame of a clock started at the first skip)."""
        from dq456_pc.window import game as WND
        w = FakeWindow(); self.assertTrue(self.start(w)); w._replay_skip = (0.0, {0: (0, 5, 0)})
        j = types.SimpleNamespace(n_loop=0, _replay=w._replay, replay_fading=lambda: False, args=types.SimpleNamespace(keys_test=False, shots_loop=False, options_test=False), _reload_step=lambda: False,
                                  gamepad=types.SimpleNamespace(poll=lambda a: None), _focus_lost=False, sound=types.SimpleNamespace(out_of_focus=False), hd_jobs={}, pause=types.SimpleNamespace(opened=False),
                                  t_loop=None, fixed_test=False, _battle_clock=lambda: True, _replay_skip=w._replay_skip, scenery_ticks=None, _scenery_acc=0.0)
        j.replay_skip_step = lambda skipping: BRP.ReplayMixin.replay_skip_step(j, skipping)
        j._speed_factor = lambda: 1.0; j.engine = types.SimpleNamespace(clock_speed=1.0)
        try: WND.Game._loop(j, 0.03)
        except Exception: pass                                                                                  # (the rest of the loop needs the real window)
        self.assertIsNone(j._replay_skip)
        j._replay_skip = (0.0, {}); j._speed_factor = lambda: BRP.REPLAY_SKIP
        try: WND.Game._loop(j, 0.03)
        except Exception: pass
        self.assertIsNotNone(j._replay_skip)                                                                    # (between two turns: the skip goes on)

    def test_no_action_labels_during_a_replay(self):
        """the cells under each status box that show the action chosen for the turn ("Attack", "Follow orders") are not drawn during a replay; the steps between two turns get a smaller
        computing budget per frame, and a frame stops catching up as soon as the next turn begins."""
        import inspect
        from dq456_pc.menus import ui_menu as UM
        from dq456_pc.window import game as GM, menu_display as MD, battle_scene as BS
        self.assertEqual(BRP.HIDDEN_CELLS, {29: (4, 5)}); self.assertLess(BRP.REPLAY_BUDGET, 0.02)
        self.assertIn('RP.HIDDEN_CELLS', inspect.getsource(MD.MenusMixin._draw_menus)); self.assertIn('RP.REPLAY_BUDGET', inspect.getsource(GM.Game._loop))
        self.assertIn('replay_skip_step', inspect.getsource(BS.BattleMixin._do_battle_step))
        r = types.SimpleNamespace(hidden_cells={29: (4, 5)}); win = types.SimpleNamespace(typ=29)
        self.assertIsNone(UM.Render._text(r, win, {'cell': (1, 4), 'text': None}, 0, 0, 'Attaquer'))        # (returns before reading anything: not drawn)
        r.hidden_cells = None
        with self.assertRaises(AttributeError): UM.Render._text(r, win, {'cell': (1, 4), 'text': None}, 0, 0, 'Attaquer')          # (outside a replay: drawn, so it reads the node's text)
        self.assertIn("node['cell'] = (i, no)", inspect.getsource(UM.Window.param_str))

    def test_no_arrow_of_the_command_phase(self):
        """while the recording answers the command menus, the status plates' arrow (code 5) went from member to member, as if someone chose by hand: during a replay it is never drawn
        (it shows only in the command phase: measured with the real engine, code 5 is -1 everywhere else)."""
        import inspect
        from dq456_pc.menus import ui_menu as UM
        from dq456_pc.window import menu_display as MD
        w = types.SimpleNamespace(parts=[{'node': 7, 'ib': [{'k': 'icon', 'partsNo': 10}]}], N={7: {'act': False}}, _icon=lambda pt, ib, no: None)
        UM.Window._cursor_icon(w, 2, True); self.assertTrue(w.N[7]['up_cursor']); self.assertTrue(w.N[7]['act'])          # (the arrow's node is known as such)
        self.assertFalse(UM.Render.hide_up_cursor)                                                                           # (a real battle: shown)
        self.assertIn("if self.hide_up_cursor and node.get('up_cursor'): continue", inspect.getsource(UM.Render.draw_all))
        self.assertIn('self.ui_render.hide_up_cursor = replay', inspect.getsource(MD.MenusMixin._draw_menus))

    def test_between_turns(self):
        """after the battle's first message, a moment with no message, no fade and no cascade is the command phase: played at once (REPLAY_SKIP), the message window stays drawn."""
        w = FakeWindow(); self.assertTrue(self.start(w)); st = w.engine.state
        st.fade = {'a': 0.0, 'n': 0}; st.background_fade = {'a': 0.0, 'n': 0}; w.engine.msg_visible = False
        self.assertFalse(w.replay_between_turns(), 'before the first message (the battle\'s opening): played as it is')
        w.engine.msg_visible = True; self.assertFalse(w.replay_between_turns()); self.assertTrue(w._replay['talked'])
        w.engine.msg_visible = False; self.assertTrue(w.replay_between_turns())
        st.fade = {'a': 0.5, 'n': 10}; self.assertFalse(w.replay_between_turns(), 'a fade: the game\'s own pace')
        st.fade = {'a': 0.0, 'n': 0}; st.part = 0xe; self.assertFalse(w.replay_between_turns())
        st.part = 0xd; w._replay['ended'] = 0; self.assertFalse(w.replay_between_turns(), 'after the end: the closing plays at its pace')
        import inspect
        from dq456_pc.window import game as GM, menu_display as MD
        self.assertIn('RP.REPLAY_SKIP', inspect.getsource(GM.Game._speed_factor)); self.assertIn('RP.KEEP_WINDOWS', inspect.getsource(MD.MenusMixin._draw_menus))
        self.assertEqual(BRP.KEEP_WINDOWS, (29,))                                                         # (only the party's status: never the monster names or the command windows)

    def test_stop_fades_then_puts_the_game_back(self):
        """a stop (end of the battle, Esc, back button) is a fade to black, then the game is put back and the history appears from the black."""
        import pyglet
        w = FakeWindow(); self.assertTrue(self.start(w)); w.applied = [{'state': 1}]; w.reg = types.SimpleNamespace(action_of=lambda s: None)
        w.replay_key(pyglet.window.key.ESCAPE); self.assertIsNotNone(w._replay); self.assertIsNotNone(w._replay['fade'])
        self.assertTrue(w.replay_fading()); self.assertEqual(w.applied, [{'state': 1}]); self.assertGreaterEqual(w.replay_veil(), 0.0)
        w.stop_battle_replay(); t0 = w._replay['fade']; w.stop_battle_replay(); self.assertEqual(w._replay['fade'], t0, 'a second stop does not restart the fade')
        w._replay['fade'] -= BRP.FADE_OUT + 0.01; self.assertAlmostEqual(w.replay_veil(), 1.0)
        self.assertFalse(w.replay_fading()); self.assertIsNone(w._replay); self.assertEqual(w.applied[1:], ['BACK', ('menu', 'VIEW')])
        self.assertGreater(w.replay_veil(), 0.5, 'the history appears from the black')
        w._replay_fade_in -= BRP.FADE_IN + 0.01; self.assertEqual(w.replay_veil(), 0.0); self.assertIsNone(w._replay_fade_in)

    def test_menu_without_a_choice_ends_the_replay(self):
        w = FakeWindow(menu=5); self.assertTrue(self.start(w))
        w.replay_feed(); w.replay_feed(); w.menu = 7; w.replay_feed()
        self.assertEqual(len(w.sent), 4); w.menu = 9                                                        # (every recorded choice was sent; a menu opens that has no answer)
        for _ in range(BRP.STARVED_STEPS): w.replay_feed(); self.assertFalse(w.replay_over())
        w.replay_feed(); self.assertTrue(w.replay_over())

    def test_game_left_without_the_end(self):
        w = FakeWindow(); self.start(w); self.assertFalse(w.replay_over())
        w.engine.battle_sensor.events = []; w.engine.state.part = 0xe
        for _ in range(BRP.LEFT_STEPS): self.assertFalse(w.replay_over())
        self.assertTrue(w.replay_over())

    def test_file_from_before_waits_for_any_menu(self):
        w = FakeWindow(menu=None); real_read = BRP.SS.read; BRP.SS.read = lambda p: {'state': 1, 'battle_inputs': [(0, 0, [], 0), (0, 0, [(3, 1, -1, 16)], 0), (0, 0, [(3, 1, -1, 0)], 0), (0, 0, [(4, 1, -1, 16)], 0)]}
        try: self.assertTrue(w.start_battle_replay('battle'))
        finally: BRP.SS.read = real_read
        for _ in range(5): w.replay_feed()
        self.assertEqual(w.sent, [])                                                                        # (no menu has the input: the choices wait, they are not all sent at once)
        w.menu = 8; w.replay_feed(); w.replay_feed(); self.assertEqual(w.sent, [(3, 1, -1, 16), (3, 1, -1, 0)]); w.replay_feed(); self.assertEqual(len(w.sent), 3)

    def test_unreadable_file(self):
        w = FakeWindow(); real_read = BRP.SS.read
        def boom(p): raise ValueError('autre version')
        BRP.SS.read = boom
        try: self.assertFalse(w.start_battle_replay('battle'))
        finally: BRP.SS.read = real_read
        self.assertIsNone(w._replay); self.assertEqual(w.toasts, [])                                       # (no on-screen message outside saves: a console line)


class Rig(BRP.ReplayMixin):
    """What the replay uses of the window, around the real engine (the real window needs a screen)."""
    def __init__(self, eng, h, SS):
        self.engine, self.history = eng, h
        self.pause = types.SimpleNamespace(shutdown=lambda leaving=True: None, open_menu=lambda page=None: None, open_history=lambda: None, hist=types.SimpleNamespace(elements=[], change_tab=lambda i: None, go_to=lambda i: None),
                                           view_state=lambda: None, restore_view=lambda v: None)
        self.ref_effect = None; self.effect_tex_ready = False
        self._complete_savestate = lambda: SS.snapshot(eng); self._apply_savestate = lambda d: SS.apply(eng, d)
    def apply_scroll(self): pass
    def _draw_scene(self): pass
    def _clone_screen(self, battle=True): pass


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'real engine: DQ_APK and DQ_SAVES')
class RealEngine(unittest.TestCase):
    MONSTER = 20                                          # (monster of the random encounter; 20 = a single weak one)
    WANDER = None                                         # seed of a player who moves the cursor, cancels and chooses at random in the menus (None: always the first choice)

    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.persistence import savestates as SS
        cls.ENGINE, cls.SS = ENGINE, SS
        cls.d = tempfile.mkdtemp(prefix='rp_mo_'); cls.sv = os.path.join(cls.d, 'sv'); os.makedirs(cls.sv)
        eng = cls.eng = ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], cls.sv)
        h = cls.h = HI.History(os.path.join(cls.d, 'fav.json'), lambda: 1.0); h.snapshotter = lambda: SS.snapshot(eng)
        for _ in range(3): eng.step(0, 0); h.do_update(eng)
        for slot in (4, 3, 2, 1):                                                                        # a log that starts where a monster can be met by walking
            if not eng.load_save(slot): continue
            eng.force_monster = cls.MONSTER; dirs = [ENGINE.UP, ENGINE.RIGHT, ENGINE.DOWN, ENGINE.LEFT]; n = 0
            while h._rec is None and n < 3000:
                d = dirs[(n // 40) % 4]; eng.step(d, d | (ENGINE.A if n % 15 == 0 else 0)); h.do_update(eng); n += 1
            if h._rec is not None: break
        cls.ok = h._rec is not None
        if not cls.ok: return
        cls.cascade_at_start = eng.state.effect is not None and eng.state.part != ENGINE.PART_BATTLE          # (the recording began with the entry cascade)
        cls.messages = cls.fight(eng, h, random.Random(cls.WANDER) if cls.WANDER is not None else None)
        h.flush_recording(eng)
        for t in threading.enumerate():
            if t is not threading.current_thread() and t.daemon: t.join(30)
        cls.e = h.battles[-1]; cls.after = cls.party(eng)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.d, ignore_errors=True)

    @classmethod
    def party(cls, eng):
        c = eng.core; return struct.unpack('<2I', c.mem(c.export('_ZN6status7g_PartyE') + 0x2f8, 8)), c.mem(c.export('_ZN6status7g_PartyE'), 0x400)

    @classmethod
    def fight(cls, eng, h, wander=None):
        """Plays the battle from its entry cascade (the first menu choice each time, or, with `wander`, cursor moves, cancels and choices at random; A on the messages); -> its battle messages."""
        ENGINE = cls.ENGINE; out = []; k = 0; release = None; after = 0; seen = False
        while True:
            decl = 0
            if release is not None: eng.send_menu(release, 1, -1, 0); release = None
            elif k % 10 == 0:
                port = eng.active_menu()
                if eng.msg_visible: decl = ENGINE.A
                elif port is not None: eng.send_menu(port, 1, -1, 0x10 if wander is None else wander.choice((0x10, 0x10, 0x10, 0x1, 0x1, 0x2, 0x20))); release = port
            eng.step(0, decl)
            out += [r['text'] for r in eng.sensor.output if r['cat'] == 'c']; h.do_update(eng)       # (History drains the sensor)
            k += 1
            seen = seen or eng.state.part == ENGINE.PART_BATTLE
            if seen and eng.state.part != ENGINE.PART_BATTLE: after += 1
            if after > 40 or k > 15000: break
        return out

    def replay(self, seed, period, speed=1.0):
        """Replays the recorded battle like the window does: the choices from the recording, the messages turned at random moments (`period`: one turn per `period` steps on average). -> (messages, steps)."""
        eng, h, ENGINE = self.eng, self.h, self.ENGINE; rnd = random.Random(seed); rig = Rig(eng, h, self.SS)
        self.assertTrue(rig.start_battle_replay(self.e)); eng.clock_speed = speed
        self.assertTrue(eng.state.effect is not None and eng.state.part != ENGINE.PART_BATTLE)           # (the entry cascade comes first, then the battle)
        out = []; k = 0; last = 0; seen = len(eng.sensor.output)
        while not rig.replay_over() and k < 30000:
            rig.replay_feed()
            decl = ENGINE.A if eng.msg_visible and eng.active_menu() is None and not last and rnd.random() < 1.0 / period else 0          # (a key press is never seen at two consecutive steps)
            if decl and rig.replay_on_last_page(): break                                                  # (as in the window: the key on "X est vaincu." ends the replay)
            eng.step(0, decl); last = decl; out += [r['text'] for r in eng.sensor.output[seen:] if r['cat'] == 'c']; seen = len(eng.sensor.output); k += 1          # (the Sensor's pages are not taken: the replay counts them, as in the window)
        self.assertLess(k, 30000); eng.clock_speed = 1.0
        return out, k, rig

    def setUp(self):
        if not self.ok: self.skipTest('no battle met from these saves')

    def won_part(self, messages):
        """What a replay shows of the battle's messages: a victory ends on its "X est vaincu." (the rewards that follow are not replayed); any other outcome, all of them."""
        if self.e.outcome != 'victory': return messages
        i = max(i for i, m in enumerate(messages) if 'vaincu' in m); self.assertLess(i, len(messages) - 1)          # (the experience and the gold come after it)
        return messages[:i + 1]

    def test_recorded_from_the_cascade(self):
        self.assertTrue(self.cascade_at_start)                                                           # (the state was taken when the cascade began, not when the battle did)
        self.assertTrue(self.e.replay); path = self.h.replay_path(self.e); self.assertIsNotNone(path)
        d = self.SS.read(path); steps = d['battle_inputs']; self.assertGreater(len(steps), 100)
        self.assertTrue(any(m for _, _, m, *_ in steps)); self.assertTrue(all(len(x) == 5 for x in steps))     # (the menu choices are in it, each with the menu that had the input)
        self.assertTrue(all(x[4] is not None for x in steps if x[2]))
        self.assertGreaterEqual(len(self.messages), 4)

    def test_monsters_held_between_turns_same_battle(self):
        """with the real engine: the monsters' animations put back on the real clock between two turns (hold_monsters before each step, as the window does) change nothing in the
        battle (same messages, same outcome), and over the command phase a monster's frame is the one the real clock has reached."""
        eng, ENGINE = self.eng, self.ENGINE; rig = Rig(eng, self.h, self.SS); self.assertTrue(rig.start_battle_replay(self.e))
        out = []; k = 0; last = 0; seen = len(eng.sensor.output); rnd = random.Random(5); sim = 0.0; skip = None; moves = []
        while not rig.replay_over() and k < 30000:
            rig.replay_feed(); between = rig.replay_between_turns()
            if between:
                if skip is None: skip = (sim, {})
                tick = int((sim - skip[0]) / (1 / 30.0)); BRP.hold_monsters(eng.core, skip[1], tick)
            else: skip = None
            sim += 0.003 if between else 1 / 30.0                                                         # (between two turns: 3 ms of real time per engine step)
            decl = ENGINE.A if eng.msg_visible and eng.active_menu() is None and not last and rnd.random() < 0.1 else 0
            if decl and rig.replay_on_last_page(): break
            eng.step(0, decl); last = decl; out += [r['text'] for r in eng.sensor.output[seen:] if r['cat'] == 'c']; seen = len(eng.sensor.output); k += 1
            if between:
                now = BRP.monster_frames(eng.core)
                moves += [(now[i][1], (f0 + tick - t0) % now[i][2]) for i, (a, f0, t0) in skip[1].items() if i in now and now[i][0] == a and now[i][4]]
        rig.end_battle_replay(); eng.sensor.output = []
        self.assertEqual(out, self.won_part(self.messages))
        self.assertTrue(moves); self.assertEqual([m for m in moves if m[0] != m[1]], [])                 # (each step shows the frame the real clock has reached: it raced through the command phase before)

    def test_replay_same_battle_whatever_the_pace(self):
        eng, h = self.eng, self.h
        for seed, period, speed in ((1, 10, 1.0), (2, 3, 3.0), (3, 25, 1.0), (4, 1, 2.0)):
            back = self.SS.snapshot(eng); before = self.party(eng); n_battles = len(h.battles); files = sorted(os.listdir(self.sv))
            replayed, k, rig = self.replay(seed, period, speed)
            rig.end_battle_replay()
            eng.sensor.output = []
            self.assertEqual(replayed, self.won_part(self.messages), (seed, period))                     # same battle: same messages, same damage, same outcome, whatever the pace
            self.assertEqual(self.party(eng), before); self.assertEqual(len(h.battles), n_battles); self.assertEqual(sorted(os.listdir(self.sv)), files)
            self.assertFalse(h.replaying); self.assertFalse(eng.core.read_only)


class LongBattle(RealEngine):
    """A tougher monster: many turns, status effects, a command menu and a target menu at each turn."""
    MONSTER = 65


class WanderingPlayer(RealEngine):
    """A player who moves the cursor, cancels and chooses at random in the menus: cursor moves, cancels and every command go through the recording."""
    MONSTER = 10
    WANDER = 5


if __name__ == '__main__':
    unittest.main()
