"""(paused everything, poll): when the window loses focus (Alt + Tab, click elsewhere, minimizing), the game KEEPS running and only the sound is cut (volume at zero, the players are not paused: the music stays in place); on return the sound comes back.
- Sound: `Sound.lose_focus` (fake players, no window or sound card), including while listening on the "Sound" page of the menu and with the menu suspended.
- Game: `Game.on_deactivate` / `on_activate` / `_loop` on a fake Game (skipped if pyglet cannot be imported: the Game tests do not run in CI).
    python3 tests/test_focus_loss.py"""
import os, sys, time, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


class FakePlayer:
    def __init__(self): self.playing = True; self.volume = 1.0
    def play(self): self.playing = True
    def pause(self): self.playing = False
    def delete(self): self.playing = False


def new_sound():
    """A Sound without pyglet (`pyglet` module masked) with fake players: a music track and a sound effect playing."""
    saved = sys.modules.get('pyglet', 0); sys.modules['pyglet'] = None
    try:
        from dq4_pc import sound as SOUND
        s = SOUND.Sound('inexistant.apk', '/tmp', log=lambda *a: None, logfile=lambda *a: None, alert=lambda *a: None)
    finally:
        if saved == 0: sys.modules.pop('pyglet', None)
        else: sys.modules['pyglet'] = saved
    s.ok = True
    s.bgm = FakePlayer(); s.bgm_end = time.time() + 30.0; s.bgm_t0 = time.time()
    s.sfx = [types.SimpleNamespace(p=FakePlayer(), end=time.time() + 5.0, category='effects', own=1.0)]
    return s


class SoundWithoutFocus(unittest.TestCase):
    def test_focus_loss_mutes_without_pausing(self):
        s = new_sound(); end = s.bgm_end
        s.lose_focus(True)
        self.assertEqual((s.bgm.volume, s.sfx[0].p.volume), (0.0, 0.0))
        self.assertTrue(s.bgm.playing); self.assertTrue(s.sfx[0].p.playing); self.assertIsNone(s.t_pause)         # (the players are running: the music stays in sync with the game)
        s.lose_focus(False)
        self.assertEqual((s.bgm.volume, s.sfx[0].p.volume), (1.0, 1.0)); self.assertEqual(s.bgm_end, end)          # (no deadline shifted: there was no pause)

    def test_idempotent(self):
        s = new_sound(); s.lose_focus(True); s.lose_focus(True); self.assertEqual(s.bgm.volume, 0.0)
        s.lose_focus(False); s.lose_focus(False); self.assertEqual(s.bgm.volume, 1.0); self.assertTrue(s.bgm.playing)

    def test_new_sounds_stay_silent_without_focus(self):
        s = new_sound(); s.lose_focus(True)
        self.assertEqual(s.mix.gain('effects', 1.0, 'effects'), 0.0); self.assertEqual(s.mix.gain('music', 1.0), 0.0)       # (music and sound effects started after the focus loss: at zero)
        s.lose_focus(False); self.assertEqual(s.mix.gain('music', 1.0), 1.0)

    def test_volume_changes_without_focus_stay_muted(self):
        s = new_sound(); s.lose_focus(True); s.set_mix(general=0.5)
        self.assertEqual(s.bgm.volume, 0.0)                                       # (the menu cannot reopen the sound without focus)
        s.lose_focus(False); self.assertEqual(s.bgm.volume, 0.5)

    def test_during_sound_page_listening(self):
        """The "Sound" page of the menu plays sounds with the menu suspended (`listening`); without focus, nothing is heard anyway, and the return of focus hands control back to the page."""
        s = new_sound(); s.set_paused(True); s.listen(True)
        self.assertTrue(s.bgm.playing)                                            # (listening: the settings are heard)
        s.lose_focus(True); self.assertEqual(s.bgm.volume, 0.0); self.assertTrue(s.bgm.playing)
        s.listen(True); self.assertEqual(s.bgm.volume, 0.0)                      # (the page asks for listening again: still silent)
        s.lose_focus(False); self.assertEqual(s.bgm.volume, 1.0); self.assertTrue(s.bgm.playing)

    def test_suspended_menu_remains_paused_on_return(self):
        s = new_sound(); s.set_paused(True); self.assertFalse(s.bgm.playing)
        s.lose_focus(True); s.lose_focus(False)
        self.assertFalse(s.bgm.playing)                                           # (the menu still suspends the game: no resume)
        s.set_paused(False); self.assertTrue(s.bgm.playing)


class GameWithoutFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try: from dq4_pc.window import game as window; cls.WND = window
        except Exception as ex: raise unittest.SkipTest('fenetre non importable ici (%r)' % (ex,))

    def fake_game(self):
        calls = []
        sound = types.SimpleNamespace(out_of_focus=False)
        def lose(yes): sound.out_of_focus = bool(yes); calls.append(bool(yes))
        sound.lose_focus = lose
        hud = types.SimpleNamespace(dpad_on=True, press_state='map', dpad_drop=lambda: setattr(hud, 'dpad_on', False))
        wheel = types.SimpleNamespace(in_progress=True, cancel=lambda: setattr(wheel, 'in_progress', False))
        bar_gesture = types.SimpleNamespace(in_progress=True, cancel=lambda: setattr(bar_gesture, 'in_progress', False))          # (camera rotation bar)
        j = types.SimpleNamespace(_ready=True, _focus_lost=False, sound=sound, hud=hud, wheel=wheel, bar_gesture=bar_gesture, press_state=('p', 1, 2), hovered=[1], acc=0.7, t_loop=1.0, alpha=0.4, n_loop=0,
                                  args=types.SimpleNamespace(keys_test=False, shots_loop=False, options_test=False), hd_jobs={}, pad_prev=9, prev_action={'x': 1}, rep={'a': 1}, mouse=(3, 4),
                                  mouse_guard=types.SimpleNamespace(keyboard=lambda pos: calls.append(('garde', pos))), pad=lambda: 0, _held=lambda a: False, camera_forgotten=0, polls=[], _reload_step=lambda: False)          # (_reload_step: language change)
        j.gamepad = types.SimpleNamespace(poll=lambda active: j.polls.append(active))
        j._camera_forget = lambda: setattr(j, 'camera_forgotten', j.camera_forgotten + 1)
        j.calls = calls
        return j

    def test_loss_of_focus(self):
        j = self.fake_game(); self.WND.Game.on_deactivate(j)
        self.assertTrue(j._focus_lost); self.assertEqual(j.calls, [True])
        self.assertFalse(j.wheel.in_progress); self.assertFalse(j.bar_gesture.in_progress); self.assertFalse(j.hud.dpad_on); self.assertIsNone(j.hud.press_state); self.assertIsNone(j.press_state); self.assertIsNone(j.hovered)      # (held mouse buttons: released)
        self.assertEqual(j.camera_forgotten, 1)                                      # (camera rotation requested with the mouse: abandoned)

    def test_loop_is_not_frozen_without_focus(self):
        """The game keeps running: `_loop` does not return control before the engine step (a fake Game has no engine: the error comes from the step, proof that it is reached) and the clock is not reset to zero."""
        j = self.fake_game(); self.WND.Game.on_deactivate(j)
        j.acc = 0.7; j.alpha = 0.4; j.t_loop = 1.0; j.n_loop = 0
        with self.assertRaises(Exception): self.WND.Game._loop(j, 0.016)
        self.assertEqual(j.n_loop, 1); self.assertNotEqual((j.acc, j.alpha), (0.0, 1.0))

    def test_gamepad_is_read_only_with_focus(self):
        """The gamepad is polled at every loop frame; without focus it is told to release everything and read nothing."""
        j = self.fake_game()
        with self.assertRaises(Exception): self.WND.Game._loop(j, 0.016)
        self.WND.Game.on_deactivate(j)
        with self.assertRaises(Exception): self.WND.Game._loop(j, 0.016)
        self.assertEqual(j.polls, [True, False])

    def test_loop_mutes_sound_if_event_came_before_loading(self):
        j = self.fake_game(); j._ready = False; self.WND.Game.on_deactivate(j)
        self.assertTrue(j._focus_lost); self.assertEqual(j.calls, [])           # (nothing exists yet: no call)
        j._ready = True
        with self.assertRaises(Exception): self.WND.Game._loop(j, 0.016)
        self.assertEqual(j.calls, [True])

    def test_focus_regained(self):
        j = self.fake_game(); self.WND.Game.on_deactivate(j); j.acc = 0.3; j.t_loop = 5.0; j.rep = {'a': 1}
        self.WND.Game.on_activate(j)
        self.assertFalse(j._focus_lost); self.assertEqual(j.calls[-2:], [False, ('garde', (3, 4))]); self.assertEqual((j.acc, j.t_loop), (0.3, 5.0)); self.assertEqual(j.rep, {})      # (the game was not stopped: clock intact)
        self.assertEqual(j.pad_prev, 0)                                            # (keys held on return are not a new press)

    def test_return_before_loading(self):
        j = self.fake_game(); j._ready = False; j._focus_lost = True; self.WND.Game.on_activate(j)
        self.assertFalse(j._focus_lost); self.assertEqual(j.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
