"""Test of the default movement keys by keyboard layout: AZERTY -> Z Q S D (and A for "Page precedente"), QWERTY / QWERTZ -> W A S D (and Q), fallback to W A S D / Q when the layout
is unusual; Windows detection with a fake library (nothing could be tried on a real Windows from Linux).

    python3 tests/test_keyboard_layout.py
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.persistence import settings as RG

SC = {a: sc for a, (sc, _) in RG.PHYSICAL_KEYS.items()}              # up W 0x11, left A 0x1E, down S 0x1F, right D 0x20, L Q 0x10


def layout(**letters):
    """A layout: action -> letter placed at the physical position of that action (None = not a letter)."""
    by_scancode = {SC[a]: l for a, l in letters.items()}
    return lambda sc: by_scancode[sc]


class Layouts(unittest.TestCase):
    def test_azerty(self):
        self.assertEqual(RG.layout_keys(layout(up='Z', left='Q', down='S', right='D', L='A')), {'up': 'Z', 'left': 'Q', 'down': 'S', 'right': 'D', 'L': 'A'})

    def test_qwerty_and_qwertz(self):
        wasd = {'up': 'W', 'left': 'A', 'down': 'S', 'right': 'D', 'L': 'Q'}
        self.assertEqual(RG.layout_keys(layout(**wasd)), wasd)                                                                           # (QWERTZ: same letters in the same places as QWERTY)

    def test_unusual_layout_falls_back_to_wasd(self):
        wasd = {'up': 'W', 'left': 'A', 'down': 'S', 'right': 'D', 'L': 'Q'}
        self.assertEqual(RG.layout_keys(layout(up=None, left='A', down='O', right='E', L=None)), wasd)                              # Dvorak: the W position is a comma
        self.assertEqual(RG.layout_keys(layout(up='Z', left='Z', down='S', right='D', L='A')), wasd)                                # two places, the same letter
        self.assertEqual(RG.layout_keys(layout(up='R', left='Q', down='S', right='D', L='A')), wasd)                                # R is already "Next page"
        self.assertEqual(RG.layout_keys(lambda sc: None), wasd)                                                                           # hors Windows : rien de lisible

    def test_no_duplicate_whatever_the_layout(self):
        for lay in (dict(up='Z', left='Q', down='S', right='D', L='A'), dict(up='W', left='A', down='S', right='D', L='Q'), dict(up=None, left='A', down='S', right='D', L='Q')):
            keys = {a: [n, None] for a, n in RG.layout_keys(layout(**lay)).items()}
            every = [n for a, ts in {**RG.DEFAULT_KEYS, **keys}.items() for n in ts if n]
            self.assertEqual(len(every), len(set(every)), lay)                                                                           # a key serves only one action

    def test_this_machine_defaults_are_valid(self):
        for a in RG.PHYSICAL_KEYS: self.assertEqual(RG.DEFAULT_KEYS[a][1], None); self.assertIsNotNone(RG.key_symbol(RG.DEFAULT_KEYS[a][0]), a)
        r = RG.Settings(None)
        for a in RG.PHYSICAL_KEYS: self.assertTrue(r.is_default_binding(a)); self.assertEqual(r.action_of(r.codes(a)[0]), a)           # each default key finds its action again

    def test_saved_keys_are_kept(self):
        """Only the defaults change: a reglages.json that keeps Z Q S D (a player's AZERTY keyboard) keeps them, and the A key remains "Page precedente"."""
        import json, tempfile
        f = os.path.join(tempfile.mkdtemp(prefix='rg_layout_'), 'settings.json')
        with open(f, 'w', encoding='utf-8') as fh: json.dump({'keys_version': RG.DEFAULT['keys_version'], 'keys': {'up': ['Z', None], 'left': ['Q', None], 'down': ['S', None], 'right': ['D', None], 'L': ['A', None]}}, fh)
        r = RG.Settings(f)
        self.assertEqual([r['keys'][a][0] for a in ('up', 'left', 'down', 'right', 'L')], ['Z', 'Q', 'S', 'D', 'A'])


class WindowsDetection(unittest.TestCase):
    def fake_windows(self, table):
        """Un faux `ctypes.windll.user32` : MapVirtualKeyExW(code de balayage, 1, disposition) -> code de touche virtuelle de `table`."""
        import ctypes
        calls = []
        user32 = types.SimpleNamespace(GetKeyboardLayout=lambda tid: 0x04090409, MapVirtualKeyExW=lambda sc, kind, hkl: (calls.append((sc, kind, hkl)), table.get(sc, 0))[1])
        old_platform, old_windll = sys.platform, getattr(ctypes, 'windll', None)
        sys.platform = 'win32'; ctypes.windll = types.SimpleNamespace(user32=user32)
        def restore():
            sys.platform = old_platform
            if old_windll is None: del ctypes.windll
            else: ctypes.windll = old_windll
        self.addCleanup(restore); return calls

    def test_not_windows_nothing_read(self):
        if sys.platform != 'win32': self.assertIsNone(RG.windows_letter(0x11))

    def test_letter_of_the_active_layout(self):
        calls = self.fake_windows({0x11: ord('Z'), 0x1E: ord('Q'), 0x1F: ord('S'), 0x20: ord('D'), 0x10: ord('A')})
        self.assertEqual(RG.layout_keys(), {'up': 'Z', 'left': 'Q', 'down': 'S', 'right': 'D', 'L': 'A'})                           # clavier AZERTY
        self.assertTrue(all(kind == 1 and hkl == 0x04090409 for _, kind, hkl in calls)); self.assertEqual(sorted(sc for sc, _, _ in calls), sorted(SC.values()))

    def test_not_a_letter_or_error(self):
        self.fake_windows({0x11: 0xBC})                                                                                                   # VK_OEM_COMMA (Dvorak)
        self.assertIsNone(RG.windows_letter(0x11)); self.assertIsNone(RG.windows_letter(0x1E))                                           # 0 = no key
        import ctypes; ctypes.windll.user32.MapVirtualKeyExW = lambda *a: (_ for _ in ()).throw(OSError('boom'))
        self.assertIsNone(RG.windows_letter(0x11)); self.assertEqual(RG.layout_keys()['up'], 'W')                                      # an error crashes nothing: W A S D


if __name__ == '__main__':
    unittest.main()
