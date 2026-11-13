""""Sepia" effect of the flashbacks (packet 1, `cmd_map_effect_sepia`):

1. `State`: packet 1 (no argument) turns the scenery sepia; it stays that way (the game does not remove it) until the next map load (packet 0), which resets it to false; the other packets do not touch it;
2. a state recorded before this fix (without the attribute) behaves as a fresh one (no sepia);
3. the scenery shader takes the formula of the game's `Custom/fld_normal_sepia` (read from the data package, GLSL ES): gray (0.299; 0.587; 0.114) of texture x vertex color x tint, plus
   (0.109375; -0.0546875; 0), alpha unchanged; applied BEFORE the write clamped to 0-1; no effect as long as the `sepia` uniform is 0 (the default value of a uniform).

  python3 tests/test_sepia_scenery.py
"""
import os, re, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import engine as ENGINE
from dq4_pc.window import shaders as SH


def send(e, *packets):
    e.apply(list(packets), lambda: 'ceout')


class Packet1(unittest.TestCase):
    def test_default_and_packet(self):
        e = ENGINE.State(); self.assertFalse(e.sepia)
        send(e, (1, [], [])); self.assertTrue(e.sepia)
        send(e, (1, [], [])); self.assertTrue(e.sepia)                     # not a toggle: a second packet does not cancel it

    def test_other_packets_have_no_effect(self):
        e = ENGINE.State(); send(e, (1, [], []))
        send(e, (33, [], [1.25, 0.65, 0.75]), (8, [], [0.0] * 6), (2, [0], [0.5]), (30, [-1], [1.25]))
        self.assertTrue(e.sepia)

    def test_map_loading(self):
        e = ENGINE.State(); send(e, (1, [], []))
        send(e, (0, [], [])); self.assertFalse(e.sepia)                    # fresh FldObject: original materials
        send(e, (1, [], [])); self.assertTrue(e.sepia)                     # another flashback, after the loading

    def test_old_state(self):
        e = ENGINE.State.__new__(ENGINE.State); self.assertFalse(e.sepia)


class Shader(unittest.TestCase):
    def test_formula(self):
        src = SH.FRAG
        self.assertIn('uniform float sepia', src)
        m = re.search(r'if \(sepia > 0\.5\) m = vec3\(dot\(vec3\(([\d.]+), ([\d.]+), ([\d.]+)\), m\)\) \+ vec3\(([\d.]+), (-[\d.]+), ([\d.]+)\);', src)
        self.assertIsNotNone(m, 'sepia line of the shader')
        weight = [float(x) for x in m.groups()[:3]]; offset = [float(x) for x in m.groups()[3:]]
        self.assertEqual(weight, [0.299, 0.587, 0.114]); self.assertAlmostEqual(sum(weight), 1.0)
        self.assertEqual(offset, [0.109375, -0.0546875, 0.0])

    def test_before_clamp_and_alpha_intact(self):
        src = SH.FRAG
        self.assertLess(src.index('if (sepia > 0.5)'), src.index('c.rgb = clamp(m, 0.0, 1.0)'))          # the gray is computed on the unclamped color, like the game's shader
        self.assertLess(src.index('vec3 m = c.rgb * tint'), src.index('if (sepia > 0.5)'))             # after texture x vertex x tint
        line = [l for l in src.split('\n') if 'sepia > 0.5' in l][0]; self.assertNotIn('c.a', line)    # alpha is not touched


if __name__ == '__main__':
    unittest.main(verbosity=2)
