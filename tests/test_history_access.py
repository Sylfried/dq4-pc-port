"""Test (no engine or display) of access to the history ("the history should be accessible only when I have control of my character, so not during a battle nor during a moment when the game
takes control"): `Game.player_control`, `Game.history_possible`, `Game._history_key`, the "History" line of the "Settings" menu and the closing of the page when the game takes control back.

    python3 tests/test_history_access.py

  1. player_control: true only on the field (town, world map) with no player lock (Global.Flag 4), message, game menu, screen effect, loading or battle; a fade alone (flag 1) changes nothing here;
  2. history_possible: in addition, never on the title screen;
  3. H key: opens the page when possible, otherwise a brief message and no page; the key is wired to `_history_key` in on_key_press (and no longer to the direct opening);
  4. "Settings" menu: the "History" line is active / inactive (grayed out, tooltip) depending on `history_possible`; without this method (minimal fake game) it stays active;
  5. Pause.do_update: history page opened, then the game takes control back (battle, dialogue, scene): the page closes (back to the root, or the menu closed if it had been opened by the key) with a message; while the player has control, the list follows the game.
"""
import inspect, os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F
from dq456_pc.menus import pause as PA
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG


def fake_game(part=ENGINE.PART_TOWN, flag=0, msg=False, menu=None, effect=None, waiting=None, guard=0, title_screen=None):
    """What `player_control` reads from the engine and the window."""
    e = types.SimpleNamespace(part=part, effect=effect, load_wait=waiting, transition_guard=guard)
    eng = types.SimpleNamespace(state=e, msg_visible=msg, active_menu=lambda: menu, flags=lambda: flag)
    j = types.SimpleNamespace(engine=eng, title_screen=title_screen, calls=[])
    j._battle_clock = lambda: F.Game._battle_clock(j)
    j.player_control = lambda: F.Game.player_control(j)
    j.history_possible = lambda: F.Game.history_possible(j)
    j.pause = types.SimpleNamespace(open_menu=lambda page=None: j.calls.append(page))
    return j


class TestPlayerControl(unittest.TestCase):
    def test_player_free_on_terrain(self):
        for part in (ENGINE.PART_TOWN, ENGINE.PART_FIELD): self.assertTrue(F.Game.player_control(fake_game(part=part)), part)

    def test_not_in_battle(self):
        self.assertFalse(F.Game.player_control(fake_game(part=ENGINE.PART_BATTLE)))
        self.assertFalse(F.Game.player_control(fake_game(effect={'n': 3, 'duration': 57})), 'cascade d\'entree en combat')
        self.assertFalse(F.Game.player_control(fake_game(waiting=object())), 'black screen waiting for the battle scene')
        self.assertFalse(F.Game.player_control(fake_game(guard=2)), 'entre deux fondus d\'un combat')

    def test_not_when_game_takes_control(self):
        self.assertFalse(F.Game.player_control(fake_game(flag=ENGINE.PLAYER_LOCKED_FLAG)), 'evenement, scene, dialogue, fondu de sortie : joueur verrouille')
        self.assertFalse(F.Game.player_control(fake_game(flag=ENGINE.PLAYER_LOCKED_FLAG | ENGINE.FADE_FLAG)))
        self.assertFalse(F.Game.player_control(fake_game(msg=True)), 'message visible')
        self.assertFalse(F.Game.player_control(fake_game(menu=3)), 'game menu (commands, shop, Misc...)')

    def test_a_fade_alone_does_not_count(self):
        self.assertTrue(F.Game.player_control(fake_game(flag=ENGINE.FADE_FLAG)), 'arrival fade or fade back from a battle, player free')
        self.assertTrue(F.Game.player_control(fake_game(flag=0x8 | 0x20)), 'autres bits de Global.Flag (manette, carte autorisee)')

    def test_other_parts(self):
        others = [p for p in (getattr(ENGINE, n) for n in dir(ENGINE) if n.startswith('PART_')) if p not in (ENGINE.PART_TOWN, ENGINE.PART_FIELD)]
        self.assertTrue(others)
        for p in others: self.assertFalse(F.Game.player_control(fake_game(part=p)), 'part %r: neither town nor world map' % (p,))


class TestHistoryPossible(unittest.TestCase):
    def test_possible_when_free(self): self.assertTrue(F.Game.history_possible(fake_game()))
    def test_not_on_title_screen(self): self.assertFalse(F.Game.history_possible(fake_game(title_screen=object())))
    def test_not_in_battle_nor_dialogue(self):
        for kw in (dict(part=ENGINE.PART_BATTLE), dict(msg=True), dict(flag=ENGINE.PLAYER_LOCKED_FLAG), dict(menu=1)): self.assertFalse(F.Game.history_possible(fake_game(**kw)), kw)


class TestKey(unittest.TestCase):
    def test_no_history_key(self):
        """No more History key (nor its line in "Controls"): the history is a line of the Esc menu, drawn on the right of its root."""
        self.assertFalse(hasattr(F.Game, '_history_key')); self.assertNotIn('history', RG.DEFAULT_KEYS); self.assertNotIn('history', dict(RG.ACTIONS))
        self.assertNotIn("== 'history'", inspect.getsource(F.Game.on_key_press))


def menu(j, stack=None):
    p = PA.Pause.__new__(PA.Pause); p.J = j; p.opened = True; p.stack = stack or ['root']; p.selected = {}; return p


def history_line(p):
    return next(entry for entry in p._entries_root() if entry.get('l') == 'settings.history')


class TestMenu(unittest.TestCase):
    def test_line_active_when_player_has_control(self):
        p = menu(fake_game()); entry = history_line(p); self.assertFalse(PA.Pause._inactive(entry)); self.assertTrue(p._active(entry))

    def test_line_grayed_otherwise_with_tooltip(self):
        for kw in (dict(part=ENGINE.PART_BATTLE), dict(msg=True), dict(flag=ENGINE.PLAYER_LOCKED_FLAG), dict(menu=2)):
            p = menu(fake_game(**kw)); entry = history_line(p); self.assertTrue(PA.Pause._inactive(entry), kw); self.assertFalse(p._active(entry), kw)
            self.assertIn('settings.only_available_when_control_character', entry.get('hint', ''))

    def test_line_follows_game_state_each_frame(self):
        j = fake_game(); p = menu(j); self.assertFalse(PA.Pause._inactive(history_line(p)))
        j.engine.msg_visible = True; self.assertTrue(PA.Pause._inactive(history_line(p)))
        j.engine.msg_visible = False; self.assertFalse(PA.Pause._inactive(history_line(p)))

    def test_minimal_fake_game_keeps_active_line(self):
        p = menu(types.SimpleNamespace()); self.assertFalse(PA.Pause._inactive(history_line(p)))


class TestClosing(unittest.TestCase):
    """Pause.do_update on the "historique" page (the other pages and `shutdown` are replaced by spies)."""
    def pause(self, j, stack):
        p = menu(j, stack); p.calls = []; p.hist = types.SimpleNamespace(follow_game=lambda: p.calls.append('suit'), leave=lambda: None)
        p.J.sound = types.SimpleNamespace(listening=False, listen=lambda e: None, tick=lambda: None)
        p.pan_fold_at = None; p.pan_pressed = None; p.rep = None
        p.shutdown = lambda: p.calls.append('closed'); return p

    def test_follows_the_game_while_the_player_has_control(self):
        j = fake_game(); p = self.pause(j, ['root', 'history']); p.do_update(); self.assertEqual(p.calls, ['suit']); self.assertEqual(p.stack, ['root', 'history'])

    def test_game_regains_control_back_to_root(self):          # no message
        for kw in (dict(part=ENGINE.PART_BATTLE), dict(msg=True), dict(flag=ENGINE.PLAYER_LOCKED_FLAG)):
            j = fake_game(); p = self.pause(j, ['root', 'history']); p.do_update(); self.assertEqual(p.stack, ['root', 'history'])
            for k, v in kw.items():
                if k == 'part': j.engine.state.part = v
                elif k == 'msg': j.engine.msg_visible = v
                elif k == 'flag': j.engine.flags = lambda v=v: v
            p.do_update(); self.assertEqual(p.stack, ['root'], kw); self.assertNotIn('closed', p.calls)

    def test_opened_by_key_menu_closes(self):
        j = fake_game(msg=True); p = self.pause(j, ['history']); p.do_update(); self.assertEqual(p.calls, ['closed'])

    def test_other_pages_are_not_touched(self):
        for page in ('root', 'display', 'sound', 'controls'):
            j = fake_game(part=ENGINE.PART_BATTLE, msg=True); p = self.pause(j, ['root'] + ([page] if page != 'root' else [])); stack = list(p.stack); p.do_update()
            self.assertEqual(p.stack, stack, page)


if __name__ == '__main__':
    unittest.main(verbosity=2)
