"""Leaving a monster arena battle: a back button at the top right of the screen replaces the original "Quit" window (type 71, `BattleMenu_StadiumAbort`).

How the original leaves a fight (read in `RoundTask::execute`, played with the real engine, tests/test_stadium_real.py): the "Quit" window is a single back button (gamepad key 0x400, which the Unity
interface turns into the game's key 0x20). When the engine receives that key during an arena battle (`Global+0x1c == 1`) it switches the window off (`MenuAPI::setBattleStadiumAbort(false)`), lets the action in
progress finish (every message of a spell that hits all the enemies still has to be turned), then asks "Attendez ! Si vous partez maintenant, vous perdrez tous les tickets que vous venez d'acheter. Vous
voulez vraiment partir ?" with Yes / No. Oui: "Dans ce cas, nous allons arrêter le combat.", the battle ends, the tickets are lost. Non: "Alors installez-vous et profitez de la fin du combat !", the window
is switched back on and the fight goes on.

The viewer gives that window no input (`Engine.ignored_types`) and does not draw it: this back button, the B key or the right click send the same key to the engine (`arena_abort_decl`), every step until the
engine has switched the window off. The button is shown exactly as long as the window is."""
import pyglet
from pyglet import gl

from dq4_pc.core import engine as ENGINE
from dq4_pc.window.constants import BTN_CHAT

ARENA_ABORT = 71                       # window type "FightStadiumAbort"
FADE_END = 0.6                         # fade to black of the end of the battle (same threshold as the windows, see MenusMixin._draw_menus): the button leaves with them


class ArenaAbortMixin:
    arena_pending = False                # the player asked to leave: BTN_CHAT is sent at every step until the engine has switched the "Quit" window off
    arena_pressed = False                # the left button was pressed on the back button
    arena_zone = None                    # (x0, y0, x1, y1) of the button, set when it is drawn

    def arena_back_shown(self):
        """Is the "Quit" window of the arena open (the engine has not switched it off) over a battle that is not ending, with no battle replay or settings menu on top?"""
        eng = self.engine
        if getattr(self, '_replay', None) is not None or self.pause.opened or eng.state.part != ENGINE.PART_BATTLE: return False
        if max(float(eng.state.fade['a']), float(eng.state.background_fade['a'])) >= FADE_END: return False
        return any(f.get('type') == ARENA_ABORT and f['visible'] for f in eng.ui.f.values())

    def arena_abort_decl(self, decl):
        """`decl` of this engine step: with the back key added as long as a request is waiting for the engine. The request ends when the button is no longer shown (window switched off, end of the battle)."""
        if not self.arena_pending: return decl
        if not self.arena_back_shown(): self.arena_pending = False; return decl
        return decl | BTN_CHAT

    def arena_back_press(self, x, y, button):
        """Left press on the button -> True (the click is used)."""
        z = self.arena_zone
        if button != pyglet.window.mouse.LEFT or z is None or not self.arena_back_shown() or not (z[0] <= x <= z[2] and z[1] <= y <= z[3]): return False
        self.arena_pressed = True; return True

    def arena_back_release(self, x, y, button):
        """Release of the left button: on the button where it was pressed = request to leave. -> True when the release belongs to the button."""
        if not self.arena_pressed or button != pyglet.window.mouse.LEFT: return False
        self.arena_pressed = False; z = self.arena_zone
        if z is not None and z[0] <= x <= z[2] and z[1] <= y <= z[3] and self.arena_back_shown(): self.arena_pending = True
        return True

    def draw_arena_back(self):
        """The back button at the top right, same size and place as in the battle replay."""
        k = max(0.75, self.height / 900.0); gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        bw, bh = 64 * 1.1 * k, 55.5 * 1.1 * k; bx, by = self.width - 16 * k - bw, self.height - 16 * k - bh
        self.arena_zone = (bx, by, bx + bw, by + bh)
        m = getattr(self, 'mouse', None); over = self.arena_pressed or self.arena_pending or (bool(m) and bx <= m[0] <= bx + bw and by <= m[1] <= by + bh)
        self.pause._back_button(bx, by, bw, bh, over)
