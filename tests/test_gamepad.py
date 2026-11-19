"""Test of the gamepad: third binding of each action (setting `manette`), controllers read as pseudo keys (window/gamepad.py), Start = Esc, gamepad inputs on the physical-key screens.
A fake controller and a fake controller manager stand in for the hardware (nothing could be tried with a real gamepad from Linux).

    python3 tests/test_gamepad.py
"""
import json, os, sys, tempfile, types, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import pyglet
pyglet.options['shadow_window'] = False
from pyglet.event import EventDispatcher
from dq456_pc.persistence import settings as RG
from dq456_pc.persistence import pad_inputs as PI
from dq456_pc.window import gamepad as GP
from dq456_pc.window.keyboard_mouse import KeyboardMouseMixin, physical_key
from dq456_pc.window.field import FieldMixin
from dq456_pc.menus import prompts as PR
import test_pause_pages as TP

K = pyglet.window.key


class FakePad:
    """Pollable attributes of a pyglet Controller."""
    def __init__(self, **v):
        self.name = 'Fake pad'; self.opened = False
        for a in ('a', 'b', 'x', 'y', 'back', 'start', 'leftshoulder', 'rightshoulder', 'leftstick', 'rightstick'): setattr(self, a, False)
        for a in ('lefttrigger', 'righttrigger', 'leftx', 'lefty', 'rightx', 'righty', 'dpadx', 'dpady'): setattr(self, a, 0.0)
        self.__dict__.update(v)
    def open(self): self.opened = True
    def close(self): self.opened = False


class FakeManager(EventDispatcher):
    def __init__(self, pads=()): self.pads = list(pads)
    def get_controllers(self): return list(self.pads)
FakeManager.register_event_type('on_connect'); FakeManager.register_event_type('on_disconnect')


class FakeWindow(EventDispatcher):
    """Records the key events, with a KeyStateHandler like the game's."""
    def __init__(self):
        self.events = []; self.key_list = K.KeyStateHandler(); self.push_handlers(self.key_list)
    def on_key_press(self, symbol, modifiers): self.events.append(('press', PI.NAME.get(symbol, symbol)))
    def on_key_release(self, symbol, modifiers): self.events.append(('release', PI.NAME.get(symbol, symbol)))
FakeWindow.register_event_type('on_key_press'); FakeWindow.register_event_type('on_key_release')
for _e in ('on_mouse_motion', 'on_mouse_press', 'on_mouse_release'): FakeWindow.register_event_type(_e)          # (the stick-driven pointer)


class LeftStick(unittest.TestCase):
    """The left stick and the d-pad are two inputs: "Button 1" of the directions shows the stick, "Button 2" the d-pad."""
    def test_default_directions(self):
        for fam in PI.FAMILIES:
            r = RG.Settings(None); r.set_pad_family(fam)
            for a, d in (('up', 'UP'), ('down', 'DOWN'), ('left', 'LEFT'), ('right', 'RIGHT')):
                self.assertEqual(r.pad_slots(a), ['PAD_LS_' + d, 'PAD_' + d], (fam, a))
                self.assertEqual(r.action_of(PI.SYMBOL['PAD_LS_' + d]), a); self.assertEqual(r.action_of(PI.SYMBOL['PAD_' + d]), a)

    def test_pictures(self):
        from dq456_pc.menus import prompts as PR
        for fam, prefix in (('XB', 'xbox'), ('PS', 'playstation'), ('NS', 'switch')):
            for d in ('up', 'down', 'left', 'right'):
                p = PR.pad_file(fam, 'PAD_LS_' + d.upper()); self.assertIsNotNone(p, (fam, d)); self.assertTrue(p.endswith('%s_stick_l_%s.png' % (prefix, d)))
                self.assertTrue(PR.pad_file(fam, 'PAD_' + d.upper()).endswith('%s_dpad_%s.png' % (prefix, d)))

    def test_codes_of_the_other_inputs_did_not_move(self):
        self.assertEqual(PI.SYMBOL['PAD_UP'], PI.PAD_BASE); self.assertEqual(PI.SYMBOL['PAD_TOUCH'], PI.PAD_BASE + 20); self.assertGreater(PI.SYMBOL['PAD_LS_UP'], PI.SYMBOL['PAD_TOUCH'])

    def test_old_file_keeps_the_stick_moving(self):
        """a settings file from before: PAD_UP... was the d-pad and the stick at once -> the stick input is added in front (the default of the time, or a player's own binding)"""
        old = {'up': 'PAD_UP', 'down': 'PAD_DOWN', 'left': 'PAD_LEFT', 'right': 'PAD_RIGHT', 'A': 'PAD_A'}
        d = RG.Settings.read_gamepads({'gamepads': {'XB': old, 'PS': dict(old, up='PAD_Y', menu='PAD_UP'), 'NS': dict(old, left=['PAD_LEFT', 'PAD_X'])}})
        self.assertEqual(d['XB']['up'], ['PAD_LS_UP', 'PAD_UP']); self.assertEqual(d['XB']['right'], ['PAD_LS_RIGHT', 'PAD_RIGHT'])
        self.assertEqual((d['PS']['up'], d['PS']['menu']), ('PAD_Y', ['PAD_LS_UP', 'PAD_UP']), 'the stick follows the d-pad direction wherever the player put it')
        self.assertEqual(d['NS']['left'], ['PAD_LEFT', 'PAD_X'], 'two inputs already: the player\'s choice is kept')
        new = {'up': 'PAD_UP', 'down': 'PAD_LS_DOWN'}
        self.assertEqual(RG.Settings.read_gamepads({'gamepads': {'XB': new}})['XB']['up'], 'PAD_UP', 'a file that already has the stick inputs is read as it is')


class Defaults(unittest.TestCase):
    def test_every_action_has_a_default_and_inputs_are_distinct(self):
        for fam in PI.FAMILIES:
            d = PI.DEFAULTS[fam]
            for a in d: self.assertIn(a, RG.DEFAULT_KEYS, a)
            for a in RG.DEFAULT_KEYS: self.assertIn(a, d, a)
            every = [n for v in d.values() for n in PI.inputs(v)]
            self.assertEqual(len(every), len(set(every)), 'a gamepad input serves only one action (%s)' % fam)
            for v in d.values(): self.assertTrue(PI.valid_binding(v), v)
            self.assertNotIn('PAD_START', every); self.assertEqual(PI.clean(None, d), d)

    def test_default_table(self):
        """the same actions on the same buttons as printed: Action A / × / A, Menu Y / △ / X, Cancel B / ○ / B, Map X / □ / Y; camera on the shoulders, accelerator on the right
        trigger, battle speed on the left one, party chat on both stick presses; History View / touch pad / −; the right stick is the mouse (no input of its own)."""
        xb, ps, ns = PI.DEFAULTS['XB'], PI.DEFAULTS['PS'], PI.DEFAULTS['NS']
        for d in (xb, ps, ns):
            self.assertEqual((d['cam_left'], d['cam_right'], d['accel'], d['battle_speed'], d['chat']), ('PAD_LB', 'PAD_RB', 'PAD_RT', 'PAD_LT', ['PAD_L3', 'PAD_R3']))
            self.assertFalse({'PAD_RS_UP', 'PAD_RS_DOWN', 'PAD_RS_LEFT', 'PAD_RS_RIGHT'} & {n for v in d.values() for n in PI.inputs(v)})
        self.assertEqual((xb['A'], xb['menu'], xb['B'], xb['map']), ('PAD_A', 'PAD_Y', 'PAD_B', 'PAD_X'))
        self.assertEqual((ps['A'], ps['menu'], ps['B'], ps['map']), ('PAD_A', 'PAD_Y', 'PAD_B', 'PAD_X'))
        self.assertEqual((ns['A'], ns['menu'], ns['B'], ns['map']), ('PAD_B', 'PAD_Y', 'PAD_A', 'PAD_X'))          # (positional: the Switch's "A" is the right button)
        for d in (xb, ps, ns): self.assertNotIn('history', d)                                    # (no more History key: the history is a line of the Esc menu)
        self.assertNotIn('pad_mouse', RG.DEFAULT); self.assertEqual(PI.MOUSE_STICK, 'right')          # (always the right stick, no option)

    def test_codes_and_action_of(self):
        r = RG.Settings(None)
        self.assertEqual(r['gamepad'], PI.DEFAULT_PAD)
        self.assertEqual(r.codes('A'), (K.SPACE, PI.SYMBOL['PAD_A'])); self.assertEqual(r.action_of(PI.SYMBOL['PAD_A']), 'A')
        self.assertEqual(r.action_of(PI.SYMBOL['PAD_Y']), 'menu'); self.assertIsNone(r.action_of(PI.SYMBOL['PAD_START']))
        self.assertEqual(r.codes('chat')[-2:], (PI.SYMBOL['PAD_L3'], PI.SYMBOL['PAD_R3'])); self.assertEqual(r.action_of(PI.SYMBOL['PAD_R3']), 'chat')
        r.set_pad_family('NS'); self.assertEqual(r.action_of(PI.SYMBOL['PAD_B']), 'A'); self.assertEqual(r['gamepad'], PI.DEFAULTS['NS'])
        r.set_pad_family('??'); self.assertEqual(r.family, 'XB')
        self.assertEqual(r.codes('modifier'), (K.LCTRL, K.RCTRL))          # no gamepad input by default
        self.assertEqual(RG.name_of(PI.SYMBOL['PAD_B']), 'PAD_B'); self.assertEqual(RG.key_symbol('PAD_B'), PI.SYMBOL['PAD_B']); self.assertEqual(RG.key_name('PAD_R3'), 'R3')

    def test_pad_codes_are_not_pyglet_keys(self):
        self.assertTrue(all(c > max(v for n, v in vars(K).items() if n.isupper() and isinstance(v, int)) for c in PI.NAME))


class Binding(unittest.TestCase):
    def test_bind_takes_the_input_from_the_other_action(self):
        r = RG.Settings(None)
        self.assertEqual(r.bind_pad('B', 'PAD_A'), 'A'); self.assertEqual((r['gamepad']['B'], r['gamepad']['A']), ('PAD_A', None))
        self.assertEqual(r.codes('B'), (K.BACKSPACE, PI.SYMBOL['PAD_A'])); self.assertEqual(r.codes('A'), (K.SPACE,))
        self.assertEqual(r.reset_pad('B'), None); self.assertEqual(r['gamepad']['B'], 'PAD_B')
        self.assertEqual(r.reset_pad('A'), None)          # PAD_A is free (B took it, then lost it with the reset)
        self.assertTrue(r.is_default_pad('A')); r.unbind_pad('A'); self.assertFalse(r.is_default_pad('A')); self.assertEqual(r.codes('A'), (K.SPACE,))

    def test_reset_gives_back_an_input_taken_by_another_action(self):
        r = RG.Settings(None); r.bind_pad('B', 'PAD_A')
        self.assertEqual(r.reset_pad('A'), 'B'); self.assertEqual((r['gamepad']['A'], r['gamepad']['B']), ('PAD_A', None))

    def test_default_keys_resets_the_gamepad_too(self):
        r = RG.Settings(None); r.bind_pad('B', 'PAD_A'); r.default_keys(); self.assertEqual(r['gamepad'], PI.DEFAULT_PAD)

    def test_saved_and_migrated_file(self):
        def load(content):
            f = os.path.join(tempfile.mkdtemp(prefix='rg_pad_'), 'settings.json')
            with open(f, 'w', encoding='utf-8') as fh: json.dump(content, fh)
            return RG.Settings(f)
        self.assertEqual(load({'sound': True})['gamepad'], PI.DEFAULT_PAD)          # a file from before the gamepad: the defaults
        self.assertEqual(load({'gamepad': PI.OLD_DEFAULT_PAD}).v['gamepads'], RG.DEFAULT['gamepads'])          # the old default becomes the new defaults of the three families
        r = load({'gamepad': {'A': 'PAD_Y', 'B': 'PAD_Y', 'menu': 'PAD_START', 'map': 'PAD_NOPE', 'L': None, 'ghost': 'PAD_B', 'chat': None}})
        self.assertEqual(r['gamepad']['A'], 'PAD_Y'); self.assertEqual(r['gamepad']['B'], 'PAD_B', 'the same input given to two actions: the first keeps it, the other falls back to its default')
        self.assertEqual(r['gamepad']['menu'], None, 'its default (Y) is taken by Action'); self.assertNotIn('ghost', r['gamepad'])
        self.assertIsNone(r['gamepad']['L'], 'an action the player cleared stays cleared'); self.assertIsNone(r['gamepad']['chat'])
        self.assertEqual(r['gamepad']['map'], PI.DEFAULT_PAD['map'], 'an unknown input is dropped')
        self.assertEqual(r.v['gamepads']['NS']['A'], 'PAD_Y', 'a binding changed by the player goes to the three families')
        self.assertEqual(load({'gamepad': 'garbage'})['gamepad'], PI.DEFAULT_PAD)
        r = load({'gamepads': {'PS': {'history': 'PAD_BACK'}}, 'pad_mouse': 'nope'})
        self.assertNotIn('history', r.v['gamepads']['PS']); self.assertEqual(r.v['gamepads']['XB'], PI.DEFAULTS['XB']);          # (the History key is gone)
        self.assertNotIn('pad_mouse', r.v)          # (an old file's value is dropped)

    def test_store_and_reload(self):
        f = os.path.join(tempfile.mkdtemp(prefix='rg_pad_'), 'settings.json'); r = RG.Settings(f); r.bind_pad('B', 'PAD_A'); r.store()
        self.assertEqual(RG.Settings(f)['gamepad'], r['gamepad'])


class Reading(unittest.TestCase):
    def test_strengths(self):
        s = GP.strengths(FakePad(a=True, lefty=-1.0, rightx=0.8, righttrigger=0.6, dpadx=-1.0))
        self.assertEqual((s['PAD_A'], s['PAD_B']), (1.0, 0.0))
        self.assertEqual(s['PAD_LS_UP'], 1.0, 'left stick up (y negative: SDL)'); self.assertEqual((s['PAD_UP'], s['PAD_DOWN'], s['PAD_LS_DOWN']), (0.0, 0.0, 0.0), 'the stick is not the d-pad any more')
        self.assertEqual(s['PAD_LEFT'], 1.0, 'd-pad left'); self.assertAlmostEqual(s['PAD_RS_RIGHT'], 0.8); self.assertAlmostEqual(s['PAD_RT'], 0.6)
        self.assertEqual(GP.strengths(FakePad(dpady=1.0))['PAD_UP'], 1.0)          # d-pad up: y positive (pyglet)

    def test_poll_presses_releases_and_updates_key_state(self):
        w = FakeWindow(); pad = FakePad(); g = GP.Gamepad(w, FakeManager([pad])); self.assertTrue(pad.opened)
        g.poll(); self.assertEqual(w.events, [])
        pad.a = True; pad.leftx = 0.9; g.poll()
        self.assertEqual(w.events, [('press', 'PAD_A'), ('press', 'PAD_LS_RIGHT')]); self.assertTrue(w.key_list[PI.SYMBOL['PAD_A']]); self.assertTrue(w.key_list[PI.SYMBOL['PAD_LS_RIGHT']])
        w.events.clear(); g.poll(); self.assertEqual(w.events, [], 'held: no new event')
        pad.a = False; pad.leftx = 0.4; g.poll()
        self.assertEqual(w.events, [('release', 'PAD_A')], 'between the thresholds the stick stays pressed (hysteresis)'); self.assertFalse(w.key_list[PI.SYMBOL['PAD_A']])
        w.events.clear(); pad.leftx = 0.2; g.poll(); self.assertEqual(w.events, [('release', 'PAD_LS_RIGHT')]); self.assertFalse(w.key_list[PI.SYMBOL['PAD_LS_RIGHT']])
        w.events.clear(); pad.leftx = 0.45; g.poll(); self.assertEqual(w.events, [], 'below the press threshold: nothing')

    def test_focus_loss_releases_everything(self):
        w = FakeWindow(); pad = FakePad(b=True, lefttrigger=1.0); g = GP.Gamepad(w, FakeManager([pad])); g.poll()
        self.assertTrue(w.key_list[PI.SYMBOL['PAD_B']]); w.events.clear()
        g.poll(False); self.assertEqual(sorted(w.events), [('release', 'PAD_B'), ('release', 'PAD_LT')]); self.assertFalse(w.key_list[PI.SYMBOL['PAD_B']])
        w.events.clear(); g.poll(True); self.assertEqual(sorted(w.events), [('press', 'PAD_B'), ('press', 'PAD_LT')], 'focus back, input still held')

    def test_hot_plug(self):
        w = FakeWindow(); m = FakeManager(); g = GP.Gamepad(w, m); pad = FakePad(start=True)
        m.dispatch_event('on_connect', pad); g.poll(); self.assertEqual(w.events, [('press', 'PAD_START')])
        m.dispatch_event('on_disconnect', pad); w.events.clear(); g.poll(); self.assertEqual(w.events, [('release', 'PAD_START')], 'unplugged while held: released')

    def test_two_controllers_and_failing_open(self):
        w = FakeWindow(); bad = FakePad(a=True); bad.open = lambda: 1 / 0; ok = FakePad(x=True)
        g = GP.Gamepad(w, FakeManager([bad, ok])); g.poll(); self.assertEqual(w.events, [('press', 'PAD_X')], 'a controller that cannot be opened is ignored')

    def test_no_manager_available(self):
        def broken(): raise RuntimeError('no controller support')
        real = sys.modules.get('pyglet.input'); sys.modules['pyglet.input'] = types.SimpleNamespace(ControllerManager=broken)
        try: g = GP.Gamepad(FakeWindow()); g.poll(); self.assertEqual(g.pads, [])          # the game runs without a gamepad
        finally:
            if real is None: del sys.modules['pyglet.input']
            else: sys.modules['pyglet.input'] = real


class XInput(unittest.TestCase):
    """Xbox controllers read straight from XInput (`XInputPad`, `Gamepad(xinput=...)`); the fake `get(slot)` stands for the Windows library."""

    @staticmethod
    def library(slots):
        """slots: {slot: [buttons, lt, rt, lx, ly, rx, ry]} (lists the test can change); an absent slot is an empty one."""
        return lambda slot: tuple(slots[slot]) if slot in slots else None

    def test_xinput_pad_attributes(self):
        pad = GP.XInputPad(self.library({0: [0x1000 | 0x8 | 0x100, 255, 0, 0, 32767, -32768, 0]}), 0)
        self.assertTrue(pad.connected); self.assertTrue(pad.a and pad.leftshoulder and not pad.b); self.assertEqual((pad.dpadx, pad.dpady), (1.0, 0.0))
        self.assertEqual((pad.lefttrigger, pad.righttrigger), (1.0, 0.0)); self.assertEqual((pad.lefty, pad.rightx), (1.0, -1.0))
        s = GP.strengths(pad); self.assertEqual((s['PAD_LS_UP'], s['PAD_LS_DOWN'], s['PAD_RS_LEFT'], s['PAD_RIGHT'], s['PAD_LB'], s['PAD_LT']), (1.0, 0.0, 1.0, 1.0, 1.0, 1.0), 'XInput: y positive = stick up')
        empty = GP.XInputPad(self.library({}), 1); self.assertFalse(empty.connected); self.assertEqual(max(GP.strengths(empty).values()), 0.0)

    def test_gamepad_reads_the_slots_and_ignores_pyglets_xinput_controllers(self):
        w = FakeWindow(); slots = {0: [0, 0, 0, 0, 0, 0, 0]}; pyglet_xi = FakePad(a=True); pyglet_xi.guid = 'XINPUTCONTROLLER'
        g = GP.Gamepad(w, FakeManager([pyglet_xi]), xinput=self.library(slots)); self.assertEqual(g.pads, [], "pyglet's own XInput controller is left aside")
        g.poll(); self.assertEqual(w.events, []); slots[0][0] = 0x2000; slots[0][4] = -32768; g.poll()
        self.assertEqual(sorted(w.events), [('press', 'PAD_B'), ('press', 'PAD_LS_DOWN')]); self.assertEqual(g.family(), 'XB')
        w.events.clear(); del slots[0]; g.poll(); self.assertEqual(sorted(w.events), [('release', 'PAD_B'), ('release', 'PAD_LS_DOWN')], 'unplugged while held: released')

    def test_empty_slots_are_looked_at_every_two_seconds(self):
        w = FakeWindow(); slots = {}; calls = []; lib = self.library(slots); get = lambda slot: (calls.append(slot), lib(slot))[1]
        clock = [100.0]; real = GP.time.monotonic; GP.time.monotonic = lambda: clock[0]
        try:
            g = GP.Gamepad(w, FakeManager(), xinput=get); calls.clear(); g.poll(); self.assertEqual(sorted(calls), [0, 1, 2, 3], 'first look at the four slots'); calls.clear()
            slots[2] = [0x10, 0, 0, 0, 0, 0, 0]; clock[0] += 1.0; g.poll(); self.assertEqual(calls, [], 'too early: empty slots are not asked again'); self.assertEqual(w.events, [])
            clock[0] += 1.5; g.poll(); self.assertEqual(w.events, [('press', 'PAD_START')], 'plugged in: found at the next look'); calls.clear(); g.poll(); self.assertEqual(calls, [2], 'then only that slot, at every frame')
        finally: GP.time.monotonic = real

    def test_pyglet_xinput_controller_is_kept_when_the_library_is_missing(self):
        w = FakeWindow(); pad = FakePad(lefty=1.0); pad.guid = 'XINPUTCONTROLLER'; g = GP.Gamepad(w, FakeManager([pad]), xinput=None)
        g.poll(); self.assertEqual(w.events, [('press', 'PAD_LS_UP')], "pyglet's XInput y axis is positive upwards")

    def test_loader_is_none_off_windows(self):
        if sys.platform != 'win32': self.assertIsNone(GP.load_xinput())


class Game(unittest.TestCase):
    def stub(self):
        r = RG.Settings(None); s = types.SimpleNamespace(reg=r, key_list=K.KeyStateHandler(), swallowed=set()); return s

    def test_held_reads_the_gamepad_like_a_key(self):
        s = self.stub(); self.assertFalse(FieldMixin._held(s, 'A'))
        s.key_list.on_key_press(PI.SYMBOL['PAD_A'], 0); self.assertTrue(FieldMixin._held(s, 'A')); self.assertFalse(FieldMixin._held(s, 'B'))
        s.key_list.on_key_release(PI.SYMBOL['PAD_A'], 0); self.assertFalse(FieldMixin._held(s, 'A'))
        s.key_list.on_key_press(PI.SYMBOL['PAD_LB'], 0); self.assertTrue(FieldMixin._held(s, 'cam_left'))

    def test_physical_keys_for_the_screens_that_read_them(self):
        s = self.stub(); f = lambda n: physical_key(s.reg, PI.SYMBOL[n])
        self.assertEqual((f('PAD_UP'), f('PAD_DOWN'), f('PAD_LEFT'), f('PAD_RIGHT')), (K.UP, K.DOWN, K.LEFT, K.RIGHT))
        self.assertEqual((f('PAD_A'), f('PAD_B'), f('PAD_LB')), (K.RETURN, K.BACKSPACE, PI.SYMBOL['PAD_LB']))
        self.assertEqual(f('PAD_X'), PI.SYMBOL['PAD_X'], 'an input with no equivalent stays as it is')
        s.reg.bind_pad('A', 'PAD_Y'); self.assertEqual(f('PAD_Y'), K.RETURN, 'follows the player\'s bindings')
        self.assertEqual(physical_key(s.reg, K.SPACE), K.SPACE)

    def test_start_is_escape(self):
        got = []; s = self.stub(); s.__dict__.update(_window_shortcut=lambda *a: False, _ready=True, mouse_guard=types.SimpleNamespace(keyboard=lambda m: None), mouse=(0, 0),
                                                       pause=types.SimpleNamespace(opened=True, key_press=lambda sym, mods: got.append(sym)))
        KeyboardMouseMixin.on_key_press(s, PI.SYMBOL['PAD_START'], 0); KeyboardMouseMixin.on_key_press(s, PI.SYMBOL['PAD_A'], 0)
        self.assertEqual(got, [K.ESCAPE, PI.SYMBOL['PAD_A']], 'Start reaches the Esc menu as Esc; the other inputs keep their code (the menu finds their action)')

    def test_key_cells_ignore_gamepad_inputs(self):
        from dq456_pc.menus import pause as PA
        r = RG.Settings(None); p = types.SimpleNamespace(J=types.SimpleNamespace(reg=r), capture=('A', 0, False))
        PA.Pause._capture(p, PI.SYMBOL['PAD_B']); self.assertEqual((p.capture, r['keys']['A']), (('A', 0, False), ['SPACE', None]))


class Families(unittest.TestCase):
    def test_family_of(self):
        f = lambda name, guid='': GP.family_of(types.SimpleNamespace(name=name, guid=guid))
        self.assertEqual(f('XInput Controller 0', 'XINPUTCONTROLLER'), 'XB'); self.assertEqual(f('Xbox Wireless Controller'), 'XB')
        self.assertEqual(f('Wireless Controller'), 'PS'); self.assertEqual(f('DualSense Wireless Controller'), 'PS'); self.assertEqual(f('Nintendo Switch Pro Controller'), 'NS')
        self.assertEqual(f('Gamepad', '030000004c050000cc09000000010000'), 'PS', 'Sony vendor in the guid'); self.assertEqual(f('Pad', '030000007e0500000920000000010000'), 'NS')
        self.assertEqual(f('Pad', '030000005e040000ea02000000010000'), 'XB'); self.assertIsNone(f('Generic USB Gamepad', '03000000046d0000c21d000000010000')); self.assertIsNone(f(None, None))

    def test_family_of_the_gamepad(self):
        ps, ns = FakePad(), FakePad(); ps.name = 'DualSense Wireless Controller'; ns.name = 'Nintendo Switch Pro Controller'
        g = GP.Gamepad(FakeWindow(), FakeManager()); self.assertEqual(g.family(), 'XB', 'none connected: Xbox')
        g._connect(ps); g._connect(ns); self.assertEqual(g.family(), 'PS', 'the first one')
        ns.a = True; g.poll(); self.assertEqual(g.family(), 'NS', 'the one used last'); g._disconnect(ns); self.assertEqual(g.family(), 'PS')

    def test_text_labels(self):
        self.assertEqual((PI.text_label('PAD_LT', 'XB'), PI.text_label('PAD_LT', 'PS'), PI.text_label('PAD_LT', 'NS')), ('LT', 'L2', 'ZL'))
        self.assertEqual((PI.text_label('PAD_START', 'PS'), PI.text_label('PAD_START', 'NS'), PI.text_label('PAD_UP', 'PS'), PI.text_label('PAD_L3', 'XB'), PI.text_label('PAD_L3', 'NS')), ('Options', '+', 'keys.dpad_up', 'L3', 'LS'))
        self.assertEqual(PI.text_label('PAD_LB', 'unknown'), 'LB', 'unknown family: Xbox')

    def test_every_input_has_a_text(self):
        for fam in ('XB', 'PS', 'NS'):
            for name in PI.SYMBOL: self.assertTrue(PI.text_label(name, fam), (fam, name))

    def test_pictures(self):
        """every input of every family has its Kenney picture (CC0, in the repository), the PlayStation touch pad included; keyboard keys too; both Shift keys the hollow arrow, Alt "ALT", Alt Gr "ALT GR"
        (drawn from Kenney's keys by tools/make_key_pictures.py); Ctrl and the keypad digits keep their text."""
        for fam in PI.FAMILIES:
            for name in PI.SYMBOL:
                if name == 'PAD_TOUCH' and fam != 'PS': continue
                p = PR.pad_file(fam, name); self.assertTrue(p and os.path.isfile(p), (fam, name))
        self.assertEqual(PR.pad_file('??', 'PAD_A'), PR.pad_file('XB', 'PAD_A')); self.assertIn('switch_button_b', PR.pad_file('NS', 'PAD_A'))          # (the Switch's bottom button is printed B)
        import pyglet.window.key as KK
        for name in ('A', 'Z', '_0', 'F1', 'F12', 'SPACE', 'RETURN', 'TAB', 'BACKSPACE', 'UP', 'LEFT', 'PAGEUP', 'DELETE'): self.assertTrue(PR.key_file(name), name)
        for name in ('NUM_1', None): self.assertIsNone(PR.key_file(name), name)
        self.assertEqual(PR.key_file('LCTRL'), PR.key_file('RCTRL')); self.assertIn('keyboard_ctrl', PR.key_file('LCTRL'))
        self.assertEqual(PR.key_file('LSHIFT'), PR.key_file('RSHIFT')); self.assertIn('keyboard_shift', PR.key_file('LSHIFT'))
        self.assertIn('keyboard_alt.png', PR.key_file('LALT')); self.assertIn('keyboard_altgr', PR.key_file('RALT')); self.assertEqual(RG.key_name('RALT'), 'Alt Gr')
        from PIL import Image
        for f in ('keyboard_shift', 'keyboard_alt', 'keyboard_altgr', 'keyboard_ctrl'):
            im = Image.open(PR.path(f)); a = np.array(im)[..., 3]; self.assertEqual(im.size, (128, 128), f)
            self.assertTrue(((a > 0) & (a < 255)).any() and (a == 255).sum() > 3000, f)          # (a white key with a sign cut out, smooth edges, like Kenney's)
        self.assertIn('keyboard_enter', PR.key_file('ENTER')); self.assertEqual(PR.key_file('ENTER'), PR.key_file('RETURN'))          # (pyglet names the main Enter key 'ENTER': not the keypad's)
        self.assertEqual(KK.symbol_string(KK.RETURN), 'ENTER'); self.assertIn('numpad_enter', PR.key_file('NUM_ENTER'))
        used = set(PR.KEY_FILES.values()) | {f for d in PR.PAD_FILES.values() for f in d.values()}
        self.assertEqual(sorted(f[:-4] for f in os.listdir(PR.FOLDER) if f.endswith('.png') and f[:-4] not in used), [], 'pictures in the repository that nothing shows')
        im = PR.image(PR.pad_file('PS', 'PAD_A')); self.assertEqual((im.size, im.mode), ((128, 128), 'RGBA'))
        lic = os.path.join(PR.FOLDER, 'LICENSE.txt'); self.assertIn('CC0', open(lic, encoding='utf-8').read())


class StickMouse(unittest.TestCase):
    """the right stick moves the mouse pointer (always); right after, the Action input clicks there; the PlayStation touch pad click is an input."""
    def window(self, family='XB'):
        w = FakeWindow(); w.width, w.height = 1000, 500; w.mouse = (500, 250); w.reg = RG.Settings(None); w.moves = []; w.clicks = []
        w.set_mouse_position = lambda x, y: w.moves.append((x, y))
        def motion(x, y, dx, dy): w.moves.append(('motion', x, y)); w.mouse = (x, y)          # (the game keeps the pointer in `mouse`, see KeyboardMouseMixin.on_mouse_motion)
        w.on_mouse_motion = motion
        w.on_mouse_press = lambda x, y, b, m: w.clicks.append(('press', x, y, b))
        w.on_mouse_release = lambda x, y, b, m: w.clicks.append(('release', x, y, b))
        return w

    def test_pointer_moves_and_action_clicks(self):
        w = self.window(); pad = FakePad(rightx=1.0); g = GP.Gamepad(w, FakeManager([pad]), xinput=None)
        g.mouse.t = 0.0; self.assertTrue(g.mouse.move(1.0, 0.0, now=0.1)); self.assertGreater(g.mouse.pos[0], 500)          # (fully right: 0.1 s = a tenth of the width)
        self.assertAlmostEqual(g.mouse.pos[0], 600, delta=1); self.assertEqual(w.moves[-1][0], 'motion')
        self.assertFalse(g.mouse.move(0.1, 0.1, now=0.2), 'dead zone')
        pad.rightx = 0.0; pad.a = True; g.mouse.moved_at = __import__('time').monotonic(); g.poll()
        self.assertEqual(w.clicks[-1][0], 'press'); self.assertNotIn(('press', 'PAD_A'), w.events, 'the click replaces the key')
        pad.a = False; g.poll(); self.assertEqual(w.clicks[-1][0], 'release'); self.assertNotIn(('release', 'PAD_A'), w.events)
        g.mouse.moved_at = -1e9; pad.a = True; g.poll(); self.assertIn(('press', 'PAD_A'), w.events, 'pointer asleep: Action again')

    def test_real_mouse_moved_in_between(self):
        """The stick starts from where the pointer is: after the real mouse moved, it does not jump back to where the stick had left it."""
        w = self.window(); g = GP.Gamepad(w, FakeManager([]), xinput=None)
        g.mouse.t = 0.0; g.mouse.move(1.0, 0.0, now=0.1); self.assertAlmostEqual(g.mouse.pos[0], 600, delta=1)
        g.mouse.move(1.0, 0.0, now=0.2); self.assertAlmostEqual(g.mouse.pos[0], 700, delta=1, msg='its own moves (a pixel apart at most) do not count as the real mouse')
        w.mouse = (100, 100); g.mouse.move(1.0, 0.0, now=0.3); self.assertAlmostEqual(g.mouse.pos[0], 200, delta=1); self.assertAlmostEqual(g.mouse.pos[1], 100, delta=1)

    def test_two_controllers_one_move(self):
        """Two controllers connected (a PlayStation one and its Xbox emulation...): the pointer moves at its full speed with the tilted stick, the other one does not eat the frame time."""
        w = self.window(); still, tilted = FakePad(), FakePad(rightx=1.0); g = GP.Gamepad(w, FakeManager([still, tilted]), xinput=None)
        g.mouse.t = __import__('time').monotonic() - 0.1; g.poll()
        self.assertGreater(g.mouse.pos[0], 590); self.assertIs(g.active, tilted)

    def test_release_frees_the_controllers(self):
        pad = FakePad(); m = FakeManager([pad]); g = GP.Gamepad(FakeWindow(), m, xinput=None); self.assertTrue(pad.opened)
        g.release(); self.assertFalse(pad.opened); self.assertEqual(g.pads, [])
        m.dispatch_event('on_connect', FakePad()); self.assertEqual(g.pads, [], 'the manager no longer calls a closed gamepad')

    def test_the_mouse_stick_gives_no_input(self):
        pad = FakePad(rightx=1.0, leftx=1.0)
        self.assertEqual(GP.strengths(pad, None, 'right')['PAD_RS_RIGHT'], 0.0); self.assertEqual(GP.strengths(pad, None, 'right')['PAD_LS_RIGHT'], 1.0)
        self.assertEqual(GP.strengths(pad, None, 'left')['PAD_LS_RIGHT'], 0.0); self.assertEqual(GP.strengths(pad, None, 'off')['PAD_RS_RIGHT'], 1.0)
        pad.dpadx = 1.0; self.assertEqual(GP.strengths(pad, None, 'left')['PAD_RIGHT'], 1.0, 'the d-pad still moves')

    def test_touch_pad_click(self):
        pad = FakePad(); pad._button_controls = [types.SimpleNamespace(value=False) for _ in range(14)]; pad._button_controls[13].value = True
        self.assertEqual(GP.strengths(pad, 'PS')['PAD_TOUCH'], 1.0); self.assertNotIn('PAD_TOUCH', GP.strengths(pad, 'XB'))
        pad._button_controls = pad._button_controls[:5]; self.assertEqual(GP.strengths(pad, 'PS')['PAD_TOUCH'], 0.0)

    def test_family_follows_the_controller(self):
        w = self.window(); pad = FakePad(name='Wireless Controller', a=True); g = GP.Gamepad(w, FakeManager([pad]), xinput=None); g.poll()
        self.assertEqual(w.reg.family, 'PS'); self.assertIn(('press', 'PAD_A'), w.events)


class CommandsColumn(unittest.TestCase):
    """two cells per line ("Key 1 / 2" or "Bouton 1 / 2"), the row above them chooses the keyboard or the gamepad: each action can have two keys and two gamepad inputs."""
    def test_line_values(self):
        J, p = TP.menu('controls'); e = TP.by_caption(p, 'controls.action')
        self.assertEqual(e['v'], ['keys.space', '—', 'PAD_A']); self.assertTrue(e['is_default']())
        J.reg.bind_pad('A', 'PAD_Y'); e = TP.by_caption(p, 'controls.action'); self.assertEqual(e['v'][2], 'PAD_Y'); self.assertFalse(e['is_default']())
        e['default'](); e = TP.by_caption(p, 'controls.action'); self.assertEqual(e['v'][2], 'PAD_A'); self.assertTrue(e['is_default']())

    def test_reset_reports_the_input_taken_from_another_action(self):
        J, p = TP.menu('controls'); J.reg.bind_pad('B', 'PAD_A'); TP.by_caption(p, 'controls.action')['default'](); self.assertEqual((J.reg['gamepad']['A'], J.reg['gamepad']['B']), ('PAD_A', None))
        self.assertTrue(any('controls.cancel_back' in str(a) for m in [p.message] if m for a in m))

    def test_cursor_stays_in_the_two_cells(self):
        J, p = TP.menu('controls'); p.selected['controls'] = [i for i, e in enumerate(p._entries()) if e['l'] == 'controls.action'][0]
        for _ in range(5): p._change_value(1)
        self.assertEqual(p.selected['col'], 1); p._change_value(-1); self.assertEqual(p.selected['col'], 0); p._change_value(-1); self.assertEqual(p.selected['col'], 0)

    def test_capture_binds_a_gamepad_input_in_a_button_cell(self):
        J, p = TP.menu('controls'); p.capture = ('up', 0, True)
        p._capture(K.SPACE); self.assertEqual(p.capture, ('up', 0, True), 'a keyboard key does not fit a gamepad cell')
        p._capture(PI.SYMBOL['PAD_B']); self.assertIsNone(p.capture); self.assertEqual((J.reg['gamepad']['up'], J.reg['gamepad']['B']), (['PAD_B', 'PAD_UP'], None), 'taken from "Annuler / Retour" (in "Button 1": the stick\'s cell; the d-pad stays in "Button 2")')
        self.assertEqual(J.reg['keys']['up'][0], 'W', 'the keys are untouched')
        self.assertEqual(p.message[4][1], 'controls.cancel_back')          # (the message names the action that lost the input)

    def test_two_gamepad_inputs_per_action(self):
        J, p = TP.menu('controls'); r = J.reg
        self.assertEqual(r.pad_slots('A'), ['PAD_A', None]); self.assertEqual(r.pad_slots('chat'), ['PAD_L3', 'PAD_R3'])
        p.capture = ('A', 1, True); p._capture(PI.SYMBOL['PAD_X']); self.assertEqual(r['gamepad']['A'], ['PAD_A', 'PAD_X']); self.assertIsNone(r['gamepad']['map'])          # (second cell: the first input stays)
        self.assertIn(PI.SYMBOL['PAD_X'], r.codes('A')); self.assertIn(PI.SYMBOL['PAD_A'], r.codes('A'))                   # both inputs act
        p.capture = ('A', 0, True); p._capture(PI.SYMBOL['PAD_Y']); self.assertEqual(r['gamepad']['A'], ['PAD_Y', 'PAD_X'])
        p.capture = ('A', 0, True); p._capture(PI.SYMBOL['PAD_X']); self.assertEqual(r['gamepad']['A'], 'PAD_X')          # (an input already in the other cell moves)
        r.unbind_pad('chat', 0); self.assertEqual(r['gamepad']['chat'], 'PAD_R3'); r.unbind_pad('chat', 0); self.assertIsNone(r['gamepad']['chat'])

    def test_capture_in_key_cells_ignores_the_gamepad(self):
        J, p = TP.menu('controls'); p.capture = ('up', 0, False); p._capture(PI.SYMBOL['PAD_B']); self.assertEqual(p.capture, ('up', 0, False)); self.assertEqual(J.reg['keys']['up'], ['W', None])

    def test_delete_and_escape(self):
        J, p = TP.menu('controls'); p.capture = ('A', 0, True); p._capture(K.DELETE); self.assertIsNone(p.capture); self.assertIsNone(J.reg['gamepad']['A'])
        J.reg.bind_pad('A', 'PAD_A'); p.capture = ('A', 0, True); p._capture(K.ESCAPE); self.assertIsNone(p.capture); self.assertEqual(J.reg['gamepad']['A'], 'PAD_A')
        p.selected['controls'] = [i for i, e in enumerate(p._entries()) if e['l'] == 'controls.action'][0]; p.selected['col'] = 0; p.controls_pad = True; p._delete_key(); self.assertIsNone(J.reg['gamepad']['A'])
        self.assertEqual(J.reg['keys']['A'][0], 'SPACE', 'the keyboard cell of the same place is untouched')

    def test_validate_starts_a_capture_on_the_chosen_cell(self):
        J, p = TP.menu('controls'); p.selected['controls'] = [i for i, e in enumerate(p._entries()) if e['l'] == 'controls.action'][0]; p.selected['col'] = 1; p._validate(); self.assertEqual(p.capture, ('A', 1, False))
        p.capture = None; p.switch_device(); p._validate(); self.assertEqual(p.capture, ('A', 1, True))

    def test_device_row_and_camera_keys(self):
        """The row above the headers switches the cells between keyboard and gamepad (click), the camera keys too ('s rule); the page opens on the device the menu was opened with."""
        J, p = TP.menu('controls'); self.assertFalse(p.controls_pad)
        p.zones_device = [(0, 0, 10, 10, False), (20, 0, 30, 10, True)]; p.click(25, 5, pyglet.window.mouse.LEFT); self.assertTrue(p.controls_pad)
        p.click(5, 5, pyglet.window.mouse.LEFT); self.assertFalse(p.controls_pad)
        cam = RG.key_symbol(J.reg['keys']['cam_right'][0]); p.key_press(cam); self.assertTrue(p.controls_pad); p.key_press(cam); self.assertFalse(p.controls_pad)
        J.last_device = 'gamepad'; p.stack = ['root']; p._go('controls')(); self.assertTrue(p.controls_pad)
        J.last_device = 'keyboard'; p.stack = ['root']; p._go('controls')(); self.assertFalse(p.controls_pad)

    def test_logos_follow_the_connected_controller(self):
        J, p = TP.menu('controls'); self.assertEqual(p._family(), 'XB'); J.gamepad = types.SimpleNamespace(family=lambda: 'PS'); self.assertEqual(p._family(), 'PS')


if __name__ == '__main__':
    unittest.main()
