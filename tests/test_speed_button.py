"""Battle speed button: it must never "appear" in the wrong place (for one frame on the left of the screen, or under the team banner), and it must not shift when an action message
replaces the command menu at the start of a turn (command frame at the width of the dialogues).

    python3 tests/test_speed_button.py                                    (parts without the engine: settings, migration, anchor)
    DQ_APK=<patched APK> DQ_SAVES=<saves> python3 -W ignore tests/test_speed_button.py
        (adds the real battle: a forced encounter on the world map, button position at EVERY frame drawn from the start of the battle, in a 1280 x 720 window without a screen (PYGLET_HEADLESS=1))
Saves are opened read-only. The "probe" (--sonde journal.jsonl) is the program the test launches: a full viewer session that records the button's rectangle at each draw."""
import contextlib, json, os, subprocess, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
import pyglet
pyglet.options['shadow_window'] = False
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True
from dq456_pc.persistence import settings as RG
from dq456_pc.core import engine as ENGINE
from dq456_pc.menus import hud_mobile as HM
try:
    from dq456_pc.window import game as F
    from dq456_pc import main
except Exception as ex:
    F = None; IMPORT_ERROR = ex

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
L, H = 1280, 720


def probe(logfile, frames=520):
    """Launches a session (slot 4, forced encounter, everything is confirmed) and records, at each draw of the button in battle, its rectangle, the message type and the active menu."""
    cache = _paths.ui_cache('/tmp/uicache47_vitesse')
    sys.argv = ['window.py', '--apk', APK, '--saves-read', SAVES, '--saves-write', tempfile.mkdtemp(prefix='sv_bouton_'), '--settings', os.path.join(tempfile.mkdtemp(prefix='rg_bouton_'), 'r.json'), '--slot', '4',
                '--cache', cache, '--msaa', '0', '--width', str(L), '--height', str(H), '--no-preparation', '--no-sound', '--shot', os.path.join(tempfile.gettempdir(), 'm_bouton.png'), '--images', '999999']
    J = {}; ini = F.Game.__init__
    def ini2(self, *a, **k): ini(self, *a, **k); J['j'] = self
    F.Game.__init__ = ini2
    out = open(logfile, 'w'); draw_all = HM.Buttons.draw_all
    def draw_all2(self, visible_ones, editing=False, grid=True):
        j = self.J; e = j.engine.state
        if e.part == ENGINE.PART_BATTLE or e.effect is not None or e.load_wait is not None:
            r = self.rect(HM.BATTLE) if HM.BATTLE in visible_ones else None
            out.write(json.dumps(dict(loop=j.n_loop, part=e.part, effect=e.effect is not None, wait=e.load_wait is not None, visible=r is not None, rect=None if r is None else [float(v) for v in r],
                                      msg=bool(j.engine.msg_visible), type_msg=getattr(j.ui_msg, 'type', None), menu=j.engine.active_menu())) + '\n'); out.flush()
        return draw_all(self, visible_ones, editing, grid)
    HM.Buttons.draw_all = draw_all2; state = {'force': False}
    def hook(dt):
        j = J.get('j')
        if j is None: return
        eng = j.engine
        if not state['force'] and eng.state.part == ENGINE.PART_FIELD and j.n > 150:
            c = eng.core; c.call(eng.E('_ZN7Encount12forceEncountEv'), c.call(eng.E('_ZN7Encount12getSingletonEv'), label='enc'), label='force'); state['force'] = True
            j.args.script = {n: [0x4, 0x8][(n // 20) % 2] for n in range(100000)}
        if eng.state.part == ENGINE.PART_BATTLE: j.args.script = None
        if j.args.battle_script is None and eng.state.part == ENGINE.PART_BATTLE: j.args.battle_script = {n: (ENGINE.A if (n > 60 and n % 10 == 0) else 0) for n in range(100000)}
        if j.n_loop > frames: out.close(); pyglet.app.exit()
    pyglet.clock.schedule(hook)
    main.main()


class Border(unittest.TestCase):
    def test_command_windows_at_dialog_width(self):
        r = RG.Settings(None)
        for n in RG.BATTLE_COMMAND_WINDOWS:
            self.assertEqual(r['interface_windows'][n], [RG.COMMANDS_WIDTH, 0.0, 0.0], n)
            self.assertEqual(RG.default_window(n), (RG.COMMANDS_WIDTH, 0.0, 0.0))
        self.assertAlmostEqual(459.0 * RG.COMMANDS_WIDTH, 510.0, delta=0.1)          # commands frame 459 units x 1.1111 = battle action messages (types 2 and 3: 510 units)
        self.assertEqual(RG.default_window('RootMenu'), RG.DEFAULT_WINDOW)

    def test_restore_resets_commands_to_default_size(self):
        r = RG.Settings(None); r['interface_windows'] = {'BattleRoot': [0.7, 0.1, 0.1], 'Status': [0.8, 0.0, 0.0]}
        r.reset_interface('BattleRoot'); self.assertEqual(r['interface_windows']['BattleRoot'], [RG.COMMANDS_WIDTH, 0.0, 0.0]); self.assertEqual(r['interface_windows']['Status'], [0.8, 0.0, 0.0])
        r.reset_interfaces(); self.assertEqual(r['interface_windows'], RG.DEFAULT['interface_windows'])

    def test_real_border_width(self):
        """On the real layout: command frame x default size = action message frame (to within half a unit)."""
        lay = os.path.join(_paths.ui_cache('/tmp/uicache47_vitesse'), 'ui_layout.json')
        if not os.path.exists(lay): self.skipTest('ui_layout.json absent')
        from dq456_pc.menus import ui_menu as UI
        ml = UI.PageLayout(lay, os.path.join(os.path.dirname(lay), 'ui_frameData.bin')); names = {}
        for num, t in ml.types.items():
            if t.get('err') in (None, 'None') and t.get('nodes'): names.setdefault(t.get('name', '').replace('Make_', '').replace('()', ''), []).append(int(num))
        fm = UI.MessageWindow(ml); fm.select_language(2, 0, False); lm = fm.extent_x(); msg_width = lm[1] - lm[0]
        for n in RG.BATTLE_COMMAND_WINDOWS:
            for num in names[n]:
                border_part = max(UI.Window(ml, num).rects(), key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
                self.assertAlmostEqual((border_part[2] - border_part[0]) * RG.COMMANDS_WIDTH, msg_width, delta=0.6, msg=n)
                self.assertAlmostEqual((border_part[0] + border_part[2]) / 2 * RG.COMMANDS_WIDTH, (lm[0] + lm[1]) / 2, delta=0.6, msg=n)           # and centered at the same place: same left edge


class Migration(unittest.TestCase):
    def load(self, d):
        with tempfile.TemporaryDirectory() as t:
            c = os.path.join(t, 'settings.json')
            with open(c, 'w', encoding='utf-8') as f: json.dump(d, f)
            return RG.Settings(c)

    def test_old_file_receives_new_size(self):
        for old in ({}, {'interface_windows': {}}, {'interface_windows': {'BattleRoot': [1.0, 0.0, 0.0]}}):
            r = self.load(old); self.assertEqual(r['interface_version'], RG.DEFAULT['interface_version'])
            for n in RG.BATTLE_COMMAND_WINDOWS: self.assertEqual(r['interface_windows'][n], [RG.COMMANDS_WIDTH, 0.0, 0.0], (old, n))

    def test_player_settings_kept(self):
        r = self.load({'interface_windows': {'BattleAction': [0.8, 0.1, -0.1], 'Status': [0.7, 0.0, 0.0], 'msg': [1.5, 0.0, 0.1]}})
        self.assertEqual(r['interface_windows']['BattleAction'], [0.8, 0.1, -0.1]); self.assertEqual(r['interface_windows']['Status'], [0.7, 0.0, 0.0]); self.assertEqual(r['interface_windows']['msg'], [1.5, 0.0, 0.1])
        self.assertEqual(r['interface_windows']['BattleRoot'], [RG.COMMANDS_WIDTH, 0.0, 0.0])

    def test_only_once(self):
        r = self.load({'interface_version': RG.DEFAULT['interface_version'], 'interface_windows': {'BattleRoot': [1.0, 0.0, 0.0]}})
        self.assertEqual(r['interface_windows'], {'BattleRoot': [1.0, 0.0, 0.0]})          # the player set 100% again after the migration: their choice prevails

    def test_unreadable_file_or_invalid_value(self):
        r = self.load({'interface_windows': 'n importe quoi'}); self.assertEqual(r['interface_windows'], {})
        self.assertEqual(RG.Settings(None)['interface_windows'], RG.DEFAULT['interface_windows'])


@unittest.skipIf(F is None, 'window.py non importable ici')
class Anchor(unittest.TestCase):
    """Dummy window: only the message box and the command windows matter; between two boxes the anchor does not move; at the very first draw of the battle it already exists."""
    @staticmethod
    def fake(part=ENGINE.PART_BATTLE):
        border = dict(pos=[0.0, 0.0, -338.0], vtx=[[-225.0, -100.0], [234.0, -100.0], [234.0, 30.0], [-225.0, 30.0]])
        msg = types.SimpleNamespace(N={'frame': border}, bottom=lambda: -338.0 - 100.0)
        def window(typ, rects): return types.SimpleNamespace(typ=typ, rects=lambda: rects)
        j = types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(part=part)), ui_msg=msg, battle_anchor=None, ui_followers=set(), reg={'interface_windows': {}}, ui_tf={},
                                  ui_g=types.SimpleNamespace(f={29: window(29, [(-219.0, 255.0, -107.0, 375.0)]), 32: window(32, [(-225.0, -402.0, 234.0, -144.0), (156.0, -397.0, 220.0, -335.0)])}))
        j._menu_hidden = lambda typ: False; j._type_name = lambda typ: {29: 'BattleUpStatus', 32: 'BattleAction'}.get(typ)
        j._ui_custom = lambda mode, s, v: (640.0, 400.0 * s * v[0], s * v[0])
        j.call = lambda entries, msg, dz: F.Game._anchor_battle_speed(j, entries, msg, dz, 1.0, 640.0, lambda lookup_key: (400.0, 1.0), None)
        return j

    def test_team_banner_does_not_attract_the_button(self):
        j = self.fake(); j.ui_tf = {29: (640.0, 400.0, 1.0)}
        j.call([(0, 29)], False, 0.0)
        self.assertIsNotNone(j.battle_anchor); self.assertLess(j.battle_anchor['y'], 100.0)           # fallback anchor (message box), not the bottom of the banner (y = 655)
        before = dict(j.battle_anchor); j.call([(0, 29)], False, 0.0); self.assertEqual(j.battle_anchor, before)

    def test_commands_then_between_two_boxes(self):
        j = self.fake(); j.ui_tf = {29: (640.0, 400.0, 1.0), 32: (640.0, 400.0, 1.1111)}
        j.call([(0, 29), (1, 32)], False, 0.0)
        self.assertAlmostEqual(j.battle_anchor['x'], 640.0 - 225.0 * 1.1111, places=3); self.assertAlmostEqual(j.battle_anchor['y'], 400.0 - 402.0 * 1.1111, places=3)
        commands = dict(j.battle_anchor); j.call([(0, 29)], False, 0.0); self.assertEqual(j.battle_anchor, commands)           # no more box: the anchor stays
        j.call([], False, 0.0); self.assertEqual(j.battle_anchor, commands)

    def test_outside_battle_no_anchor(self):
        j = self.fake(ENGINE.PART_FIELD); j.battle_anchor = {'x': 1.0, 'y': 2.0, 'w': None, 'h': None}; j.call([], False, 0.0); self.assertIsNone(j.battle_anchor)

    def test_button_hidden_while_no_room(self):
        """Mode attached to the bottom box (DQ_SPEED_ANCHOR=1, default): the button is shown only if it has room."""
        J = types.SimpleNamespace(reg={'speed_button_pos': [], 'speed_button': True}, ui_msg=object(), battle_anchor=None)
        b = HM.Buttons.__new__(HM.Buttons); b.J = J
        with env_anchor('1'):
            self.assertFalse(b._anchor_ready()); J.battle_anchor = {'x': 0.0, 'y': 0.0}; self.assertTrue(b._anchor_ready())
            J.battle_anchor = None; J.reg['speed_button_pos'] = [4.0, 6.0]; self.assertTrue(b._anchor_ready())           # place chosen by the player
            J.reg['speed_button_pos'] = []; J.ui_msg = None; self.assertTrue(b._anchor_ready())                       # simple menus: grid position


@contextlib.contextmanager
def env_anchor(value):
    """DQ_SPEED_ANCHOR set (or removed: None) for the duration of a block."""
    old = os.environ.get('DQ_SPEED_ANCHOR')
    if value is None: os.environ.pop('DQ_SPEED_ANCHOR', None)
    else: os.environ['DQ_SPEED_ANCHOR'] = value
    try: yield
    finally:
        if old is None: os.environ.pop('DQ_SPEED_ANCHOR', None)
        else: os.environ['DQ_SPEED_ANCHOR'] = old


def fake_buttons(width_px=1280, height_px=720, pos=None, anchor=None):
    """Buttons on a dummy window (only the window size, the speed button settings and the optional anchor matter)."""
    J = types.SimpleNamespace(width=width_px, height=height_px, ui_msg=object(), battle_anchor=anchor, engine=types.SimpleNamespace(state=types.SimpleNamespace(part=ENGINE.PART_BATTLE)),
                              reg={'speed_button_pos': pos or [], 'speed_button': True, 'speed_button_size': 1.0, 'buttons_pos': {}, 'buttons_size': 1.0})
    b = HM.Buttons.__new__(HM.Buttons); b.J = J; b.editing = False; return b, J


class LeftEdge(unittest.TestCase):
    """By default the battle speed button is at its grid cell, on the left edge of the screen, never attached to the
    bottom box (DQ_SPEED_ANCHOR=1 restores the attachment)."""
    ANCHOR = {'x': 430.0, 'y': 30.0, 'w': 85.0, 'h': 40.0}

    def test_default_no_anchor(self):
        self.assertFalse(HM.SPEED_ANCHOR_DEFAULT)
        with env_anchor(None): self.assertFalse(HM.speed_anchor())
        for v in ('', '  ', 'x?'):
            with env_anchor(v): self.assertFalse(HM.speed_anchor(), repr(v))                    # missing, empty or unreadable: the default
        for v in ('1', 'oui', 'True'):
            with env_anchor(v): self.assertTrue(HM.speed_anchor(), v)
        for v in ('0', 'non', 'False', 'FAUX'):
            with env_anchor(v): self.assertFalse(HM.speed_anchor(), v)

    def test_left_edge_even_with_known_anchor(self):
        b, J = fake_buttons(anchor=self.ANCHOR)
        with env_anchor(None):
            self.assertIsNone(b.anchor()); self.assertTrue(b._anchor_ready())
            x, y, w, h = b.rect(HM.BATTLE)
            self.assertAlmostEqual(x, 0.4 * 1280 / HM.COLS, places=6); self.assertAlmostEqual(y, 720 - 8 * 720 / HM.LINES - h, places=6)           # cell (0.4; 8) of the grid: left edge
            self.assertLess(x, 0.02 * 1280)                                                                                                       # (never under the bottom box: x ~ 380 to 460)
            self.assertEqual((w, h), (HM.DQ_PLATE[HM.BATTLE][0] * 720 / 800.0, HM.DQ_PLATE[HM.BATTLE][1] * 720 / 800.0))                       # the button's original plate, not that of "Flee"

    def test_visible_from_the_first_frame_without_anchor(self):
        b, J = fake_buttons(anchor=None)
        with env_anchor(None): self.assertTrue(b._anchor_ready())
        with env_anchor('1'): self.assertFalse(b._anchor_ready())

    def test_player_position_kept(self):
        b, J = fake_buttons(pos=[10.0, 4.0], anchor=self.ANCHOR)
        for v in (None, '1'):
            with env_anchor(v): x, y, w, h = b.rect(HM.BATTLE); self.assertAlmostEqual(x, 10.0 * 1280 / HM.COLS, places=6)

    def test_requested_anchor_restores_attachment(self):
        b, J = fake_buttons(anchor=self.ANCHOR)
        with env_anchor('1'):
            self.assertEqual(b.anchor(), self.ANCHOR); x, y, w, h = b.rect(HM.BATTLE); self.assertAlmostEqual(x, 430.0); self.assertGreater(w, 0)

    def test_no_change_outside_battle(self):
        b, J = fake_buttons(anchor=self.ANCHOR); J.engine.state.part = ENGINE.PART_FIELD
        for v in (None, '1'):
            with env_anchor(v): self.assertIsNone(b.anchor())


@unittest.skipUnless(APK and SAVES and F is not None, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealBattle(unittest.TestCase):
    ENV = {'DQ_SPEED_ANCHOR': '1'}                                    # mode attached to the bottom box (default); the default (left edge): RealBattleLeftEdge
    @classmethod
    def setUpClass(cls):
        cls.logfile = os.path.join(tempfile.mkdtemp(prefix='bouton_'), 'journal.jsonl')
        env = {k: v for k, v in os.environ.items() if k != 'DQ_SPEED_ANCHOR'}; env.update(PYGLET_HEADLESS='1', PYGLET_AUDIO='silent', **cls.ENV)
        r = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__), '--sonde', cls.logfile], capture_output=True, text=True, timeout=900, env=env)
        if not os.path.exists(cls.logfile): raise RuntimeError('probe without a log: ' + r.stdout[-600:] + r.stderr[-600:])
        cls.lines = [json.loads(l) for l in open(cls.logfile)]
        cls.views = [l for l in cls.lines if l['visible']]

    def test_battle_has_been_played(self):
        self.assertGreater(len(self.views), 150); self.assertTrue(any(l['effect'] for l in self.lines)); self.assertTrue(any(l['menu'] is not None for l in self.views)); self.assertTrue(any(l['type_msg'] in (2, 3) and l['msg'] for l in self.views))

    def test_each_frame_button_below_bottom_box_on_left(self):
        """All the drawn frames of the battle (from the black screen that follows the cascade to the last message): button at the bottom of the screen, at the left edge of the boxes (x from 380 to 460 pixels out of 1280)."""
        for l in self.views:
            x, y, w, h = l['rect']; self.assertLess(y, 0.1 * H, l); self.assertTrue(380.0 < x < 460.0, l)

    def test_first_frame_already_in_right_place(self):
        is_first = self.views[0]; x, y, w, h = is_first['rect']; self.assertTrue(380.0 < x < 460.0 and y < 0.1 * H, is_first)           # (before: x = 16, y = 346 for 4 frames)

    def test_no_offset_at_start_of_turn(self):
        """The command menu then the first action message (type 2 or 3): same left edge, to within a fraction of a pixel."""
        menus = [l['rect'][0] for l in self.views if l['menu'] is not None and not l['msg']]; actions = [l['rect'][0] for l in self.views if l['msg'] and l['type_msg'] in (2, 3)]
        self.assertTrue(menus and actions)
        for x in menus + actions: self.assertAlmostEqual(x, menus[0], delta=1.0)


@unittest.skipUnless(APK and SAVES and F is not None, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealBattleLeftEdge(RealBattle):
    """Default (no variable): at EVERY drawn frame of the battle the button is on the left edge of the screen, at its grid cell, and never moves."""
    ENV = {}

    def test_each_frame_button_below_bottom_box_on_left(self):
        for l in self.views: x, y, w, h = l['rect']; self.assertAlmostEqual(x, 0.4 * L / HM.COLS, delta=0.5, msg=l); self.assertAlmostEqual(y, H - 8 * H / HM.LINES - h, delta=0.5, msg=l)

    def test_first_frame_already_in_right_place(self):
        x, y, w, h = self.views[0]['rect']; self.assertAlmostEqual(x, 0.4 * L / HM.COLS, delta=0.5); self.assertAlmostEqual(y, H - 8 * H / HM.LINES - h, delta=0.5)

    def test_no_offset_at_start_of_turn(self):
        xs = {round(l['rect'][0], 2) for l in self.views}; ys = {round(l['rect'][1], 2) for l in self.views}; self.assertEqual((len(xs), len(ys)), (1, 1))


if __name__ == '__main__':
    if '--sonde' in sys.argv:
        i = sys.argv.index('--sonde'); probe(sys.argv[i + 1])
    else:
        unittest.main()
