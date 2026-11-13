"""Battle replay from the history (redone): the battle is played again by the engine itself, from the state saved when it began, like a real battle.

What the player sees is a real battle: the entry cascade, the music from its start, the "X appears!" message, then the turns. The player turns the messages and the animations by hand, exactly as in a battle
(Enter / Space / click; "Manual" waits for them), and the speed key and the on-screen speed button have the same role as in a battle ("Battle speed"). The command menus are never shown: each time the engine
opens one, the choice recorded in the real battle is sent to it. Esc, the history key, the B key, the right click or the back button stop the replay; it also stops by itself a moment after the end of the battle.
Then the game is put back EXACTLY as it was (savestate taken just before), so experience, gold, items and the history do not change: the history records nothing during the replay (History.replaying)
and the engine's save files are not written (GameCore.read_only).

Established with the real engine (tests/test_battle_replay.py): the engine's random draws do NOT depend on the pace of the inputs (24 replays of 6 different battles, with random delays of 1 to 60 steps before each
choice and random message turns: same messages, same damage, same outcome). So only the CHOICES are replayed, not the steps spent waiting for them.

A replay file holds the state of the game when the battle began and, for each engine step, what the engine received (keys, menu messages, message speed, the menu that had the input). `choice_script` keeps from it the
menu messages only."""
import struct, time, traceback
import pyglet
from pyglet import gl

from dq4_pc.core import engine as ENGINE
from dq4_pc.core.history import REPLAY_TAIL
from dq4_pc.menus import hud_mobile as HM
from dq4_pc.persistence import savestates as SS
from dq4_pc.window.constants import ENGINE_STEP

LEFT_STEPS = 120                     # engine steps outside the battle (after having been in it) before the replay stops even without the engine's "end"
ANY_MENU = -1                        # menu that had the input, for the files recorded (it was not kept): any menu that has the input will do
STARVED_STEPS = 45                   # engine steps a menu may wait for a choice that is not in the recording (or is not its own) before the replay is given up
REPLAY_SKIP = 30.0                   # clock factor between two turns: the command phase, answered by the recording, is played at once (a few frames), the last message of a turn goes straight on to the first one of the next;
                                     # the scenery's own animations (the sky of the plains turns once in 150 s) keep the real clock meanwhile, otherwise the sky jumped by a degree
KEEP_WINDOWS = (29,)                 # window types shown during a replay: the party's status; the command phase windows (Combattre / Fuir, commands, targets, monster names, lists...) are never shown
HIDDEN_CELLS = {29: (4, 5)}           # cells not drawn during a replay: under each status box, the action chosen for the turn ("Attack ▼", "Follow orders"): the replay goes from turn to turn without them
REPLAY_BUDGET = 0.012                # computing time (s) of the engine steps in one displayed frame between two turns (instead of FAST_STEP_BUDGET): the command phase spreads over a few frames
                                     # that keep the display's pace, instead of one or two slow ones (the "mini lag")
MONSTERS = '_ZN18BattleMonsterDraw211m_singletonE'          # BattleMonsterDraw2: 12 BattleMonster (DSSACharacter) of 0xa90 bytes; +0xa6c: the monster (-1: none); +0x24: the animation played, +0x28: -1 if
MONSTER_COUNT, MONSTER_SIZE = 12, 0xa90                      # it loops; its DSSAObject at +0x30 + 0xb8 x animation: +0x44 its frame count, +0xa8 its frame (DSSAObject::execute: +1 per engine step, back to 0 at the end)
FADE_OUT, FADE_IN = 0.5, 0.4         # seconds: fade to black when the replay stops (end of the battle or the player's stop), then the history appears from the black


def choice_script(inputs):
    """Recorded steps -> the menu choices to send again: [(messages, port of the menu that had the input (None: no menu had it; ANY_MENU: not recorded), follows the previous group at the very next step)].
    The steps spent waiting (no menu message) disappear; a group sent at the step right after the previous one (the release of a press) stays glued to it."""
    out = []; last = None
    for k, step in enumerate(inputs):
        menus = step[2]
        if not menus: continue
        out.append((list(menus), step[4] if len(step) > 4 else ANY_MENU, last is not None and k - last == 1)); last = k
    return out


def monster_frames(core):
    """The battle monsters' animations: {slot: (animation, frame, frame count, address of the frame, loops)}. `loops`: the animation starts again by itself, either looping (+0x28 = -1) or
    followed by itself (+0x28 = the same animation: the idle animation of some monsters, the matœil's)."""
    base = core.export(MONSTERS); out = {}
    if base is None: return out
    for i in range(MONSTER_COUNT):
        b = base + i * MONSTER_SIZE
        if struct.unpack('<i', core.mem(b + 0xa6c, 4))[0] == -1: continue
        anim, nxt = struct.unpack('<2i', core.mem(b + 0x24, 8))
        if not 0 <= anim < 14: continue
        o = b + 0x30 + anim * 0xb8; n = struct.unpack('<i', core.mem(o + 0x44, 4))[0]; frame = struct.unpack('<i', core.mem(o + 0xa8, 4))[0]
        if n > 0: out[i] = (anim, frame, n, o + 0xa8, nxt in (-1, anim))
    return out


def hold_monsters(core, held, tick):
    """before an engine step between two turns of a replay, where the engine runs ahead (REPLAY_SKIP): puts back each monster's animation at the frame the real clock has reached (minus the
    one the step adds), so that the monsters keep their pace from one turn to the next instead of racing through the whole command phase. `held` {slot: (animation, its frame, real tick then)}
    is kept up to date: an animation already playing when the skip began goes on from its frame; one that starts during the skip (a monster beginning its action before the turn's first message)
    plays from its first frame at real pace too. `tick`: engine steps of real time since the skip began. An animation that starts again by itself wraps around; another one is left to end on its
    own once the real clock has reached its last frame."""
    for i, (anim, frame, n, addr, loops) in monster_frames(core).items():
        h = held.get(i)
        if h is None or h[0] != anim: h = held[i] = (anim, frame if h is None else 0, tick)
        target = h[1] + tick - h[2]
        if loops: core.mem_w(addr, struct.pack('<i', (target - 1) % n))
        elif target < n - 1: core.mem_w(addr, struct.pack('<i', target - 1))          # (-1: DSSAObject::execute makes it frame 0)


class ReplayMixin:
    _replay = None                    # replay in progress: {'script', 'i' (next choice), 'back' (state of the game to put back), 'element', 'scroll', 'ended' (steps since the battle's end), 'starved', 'seen', 'left', 'talked' (a message was shown), 'fade' (time the stop began)}
    _replay_fade_in = None            # time the history appeared after a replay (fade from black)
    _replay_skip = None               # between two turns: (time the skip began, {slot: (animation, frame, tick)} held on the real clock, see hold_monsters)
    replay_zone = None                # area of the back button (click)

    def start_battle_replay(self, e):
        """History > Combats: replays battle `e`. -> True if the replay started (False: no replay file, unreadable, other engine version: a console line says why; no on-screen message outside saves)."""
        h = self.history; path = h.replay_path(e)
        if path is None: return False
        try:
            d = SS.read(path); inputs = d.pop('battle_inputs')
        except Exception as ex:
            print('Battle replay impossible: %r' % (ex,), flush=True); return False
        h.flush_recording(self.engine)
        try: back = self._complete_savestate()
        except Exception as ex:
            print('Battle replay impossible: %r' % (ex,), flush=True); return False
        menu = self.pause.view_state(); self.pause.shutdown(leaving=False)          # (every menu closes; they come back as they were at the end)
        here = self._grab_here()                                         # (the entry cascade shatters the screen where the player IS, not the place the battle was fought)
        scroll = self.engine.scroll_mode
        self._replay = {'script': choice_script(inputs), 'i': 0, 'back': back, 'element': e, 'scroll': scroll, 'ended': None, 'starved': 0, 'seen': False, 'left': 0, 'talked': False, 'fade': None, 'menu': menu}
        h.replaying = True; self.engine.core.read_only = True
        try: self._apply_savestate(d)
        except Exception as ex:                                         # (state of another engine version...): the game is put back at once
            traceback.print_exc(); self._replay = None
            try: self._apply_savestate(back)
            finally: h.replaying = False; self.engine.core.read_only = False; self.engine.scroll_mode = scroll; self.pause.restore_view(menu)
            print('Battle replay impossible: %r' % (ex,), flush=True); return False
        if here and self.engine.state.effect is not None: self.ref_effect = self.engine.state.effect; self.effect_tex_ready = True          # (the cascade starts at once on that picture)
        self.apply_scroll()                                              # the message speed is the player's ("Battle speed"), not the one of the recording
        return True

    def _grab_here(self):
        """The game as it is on screen now, menus closed, copied for the entry cascade: the replay's battle state starts at the cascade, and without this its first picture would be the place the battle was
        fought (the player saw himself teleported there). -> True if copied."""
        try: self._draw_scene(); self._clone_screen(); return True
        except Exception as ex: print('Battle replay: screen not copied: %r' % (ex,), flush=True); return False

    # ---- the recorded choices
    def replay_feed(self):
        """Once per unmuted engine step: sends the next recorded choice when the menu it was made in has the input (nothing from the player, the menus are not shown). A group that followed the previous one at the very next
        step (the release of a press) goes out at once; so does one made while no menu had the input. A menu that waits for a choice the recording does not have, or a different one, counts as starved (see replay_over)."""
        r = self._replay; s = r['script']; menu = self.engine.active_menu()
        if r['i'] >= len(s):
            if menu is not None: r['starved'] += 1
            return
        messages, active, glued = s[r['i']]
        if glued or active is None or menu == active or (active == ANY_MENU and menu is not None):
            for m in messages: self.engine.send_menu(*m)
            r['i'] += 1; r['starved'] = 0
        elif menu is not None: r['starved'] += 1

    def replay_between_turns(self):
        """Between two turns of the replayed battle: the battle has shown a message, there is none now and no fade or cascade is under way. That is the command phase, which the recording answers: it is played
        at REPLAY_SKIP and the message window stays drawn, so the last message of a turn is followed at once by the first one of the next."""
        r = self._replay
        if r is None or r.get('fade') is not None or r['ended'] is not None: return False
        eng = self.engine; e = eng.state
        if e.part != ENGINE.PART_BATTLE or e.effect is not None or e.load_wait is not None: return False
        if eng.msg_visible: r['talked'] = True; return False
        return bool(r.get('talked')) and e.fade['n'] <= 0 and e.background_fade['n'] <= 0 and float(e.fade['a']) < 0.01 and float(e.background_fade['a']) < 0.01

    def replay_skip_step(self, skipping):
        """Before each engine step of a replay: `skipping` True between two turns (REPLAY_SKIP). The monsters' animations keep the real clock meanwhile (hold_monsters)."""
        if not skipping: self._replay_skip = None; return
        core = self.engine.core
        if self._replay_skip is None: self._replay_skip = (time.perf_counter(), {})
        t0, held = self._replay_skip
        hold_monsters(core, held, int((time.perf_counter() - t0) / ENGINE_STEP))

    # ---- end
    def stop_battle_replay(self):
        """Stops the replay (end of the battle, or the player's stop: Esc, B, right click, back button) with a fade to black of FADE_OUT seconds, the engine stopped; the game is put back once the screen is black."""
        r = self._replay
        if r is not None and r.get('fade') is None: r['fade'] = time.perf_counter()

    def replay_fading(self):
        """Once per loop: the replay is stopping. -> True while the fade to black lasts (no engine step); at its end the game is put back and the history appears from the black (FADE_IN)."""
        r = self._replay
        if r is None or r.get('fade') is None: return False
        if time.perf_counter() - r['fade'] < FADE_OUT: return True
        self.end_battle_replay(); self._replay_fade_in = time.perf_counter()
        return False

    def replay_veil(self):
        """Opacity of the black veil of the replay's end (0: none)."""
        now = time.perf_counter(); r = self._replay
        if r is not None and r.get('fade') is not None: return min(1.0, (now - r['fade']) / FADE_OUT)
        t = getattr(self, '_replay_fade_in', None)
        if t is None: return 0.0
        a = 1.0 - (now - t) / FADE_IN
        if a <= 0.0: self._replay_fade_in = None; return 0.0
        return min(1.0, a)

    def draw_replay_veil(self):
        a = self.replay_veil()
        if a <= 0.0: return
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        r = pyglet.shapes.Rectangle(0, 0, self.width, self.height, color=(0, 0, 0)); r.opacity = int(round(255 * a)); r.draw()

    def replay_over(self):
        """The battle is over (a moment after the engine's "end"), or a menu waits for a choice the recording does not have, or the game left the battle without ending it."""
        r = self._replay
        if r is None: return False
        if r['starved'] > STARVED_STEPS: return True
        if r['ended'] is None:
            e = self.engine.state; cc = getattr(self.engine, 'battle_sensor', None)
            if cc is not None and any(ev[0] == 'end' for ev in cc.events): r['ended'] = 0
            elif e.part == ENGINE.PART_BATTLE: r['seen'] = True
            elif r['seen'] and e.effect is None and e.load_wait is None:
                r['left'] += 1                                                       # (safeguard: the game left the battle without the engine's "end": returned to the title...)
                if r['left'] > LEFT_STEPS: return True
            return False
        r['ended'] += 1
        return r['ended'] > REPLAY_TAIL

    def end_battle_replay(self):
        """Puts the game back as it was before the replay and reopens the history on the same battle."""
        r, self._replay = self._replay, None
        if r is None: return
        eng = self.engine
        try: self._apply_savestate(r['back'])
        finally:
            eng.scroll_mode = r['scroll']; eng.core.read_only = False; eng.battle_intro = False
            cc = getattr(eng, 'battle_sensor', None)
            if cc is not None: cc.events = []; cc.tracking = None; cc.outputs = []          # (the replayed battle's events must not become a new battle of the history)
            s = getattr(eng, 'sensor', None)
            if s is not None: s.drain(); s.events = []
            if hasattr(eng, 'record_inputs'): eng.record_inputs(False)
            self.history.replaying = False
        if r.get('menu') is not None: self.pause.restore_view(r['menu'])          # (every menu opens again as it was)
        else:
            self.pause.open_menu('history'); v = self.pause.hist
            v.change_tab(1)
            if r['element'] in v.elements: v.go_to(v.elements.index(r['element']))

    # ---- inputs during the replay: the battle's own (messages, speed), plus stopping
    def replay_key(self, symbol):
        K = pyglet.window.key; action = self.reg.action_of(symbol)
        if symbol in (K.ESCAPE, K.BACKSPACE) or action in ('B', 'history'): self.stop_battle_replay()
        elif action == 'battle_speed': self.change_battle_speed()

    def replay_press(self, x, y, button):
        if button == pyglet.window.mouse.RIGHT or (self.replay_zone and self.replay_zone[0] <= x <= self.replay_zone[2] and self.replay_zone[1] <= y <= self.replay_zone[3]):
            self.stop_battle_replay(); return
        vis = [n for n in self.hud.visible_ones() if n == HM.BATTLE]
        if vis and button == pyglet.window.mouse.LEFT and self.hud.press(x, y, vis): return          # (the battle speed button)
        if button == pyglet.window.mouse.LEFT and self.engine.msg_visible: self.click_a = True          # touching the message = next page, as in a battle

    def replay_release(self, x, y, button):
        if button == pyglet.window.mouse.LEFT and self.hud.press_state:
            if self.hud.let_go(x, y, [n for n in self.hud.visible_ones() if n == HM.BATTLE]) == HM.BATTLE: self.change_battle_speed()

    def draw_replay_overlay(self):
        """The back button at the top right (no "replay" label)."""
        k = max(0.75, self.height / 900.0); gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        bw, bh = 64 * 1.1 * k, 55.5 * 1.1 * k; bx, by = self.width - 16 * k - bw, self.height - 16 * k - bh
        self.replay_zone = (bx, by, bx + bw, by + bh)
        m = getattr(self, 'mouse', None); over = bool(m) and bx <= m[0] <= bx + bw and by <= m[1] <= by + bh
        self.pause._back_button(bx, by, bw, bh, over)
