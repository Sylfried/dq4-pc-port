"""What the game's own shaders say about two effects of the town, and how the port draws them.

1. The icon bubbles (packets 19/20, Riseup: the item that rises out of a chest, a jar or a wardrobe, a mini medal; the "!" above a character): the shader Custom/Riseup is in the
   queue Overlay-150 with ZTest and ZWrite off, so the bubble goes after the scenery, the characters, the mesh effects and the particles (Transparent+400) and over all of them, a
   wall in front included; only the orthographic layer (logos, title texts) and the windows go over it. The port drew it with the depth test on, before the mesh effects: scenery
   in front of it could hide it.
2. DQ VI's well (Capture.IDO, render/ido_effect.py): the shader Custom/Ido computes each corner's texture coordinates from its depth z, uv = s + 2z s BiasA + (1 - 2z) s BiasB
   (s: the screen position from the bottom left corner), and the game's mesh gives the corners of a cell their own z (0.5 top left and bottom right): two neighbouring cells read
   the capture at different places along their shared edge, so the picture breaks into squares that wobble. That is the game's effect, kept as it is.

Part 1 of the drawing code is checked without data; the shaders are read from the APK files of data\\apk\\<game>\\<language> (skipped without them).

    python3 tests/test_game_shaders.py
"""
import glob, os, sys, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
DATAPACK = 'assets/bin/Data/datapack.unity3d'


class DrawingCode(unittest.TestCase):
    def test_bubbles_after_the_particles_without_depth(self):
        with open(os.path.join(ROOT, 'dq456_pc', 'window', 'game.py'), encoding='utf-8') as f: s = f.read()
        particles = s.index('self._paint_particles(e, field)'); bubbles = s.index('for tex, vl in icons: self._paint(tex, vl)')
        self.assertGreater(bubbles, particles)
        block = s[particles:bubbles]
        self.assertIn('gl.glDisable(gl.GL_DEPTH_TEST)', block); self.assertIn('gl.glDepthMask(gl.GL_FALSE)', block)
        self.assertEqual(s.count('for tex, vl in icons: self._paint(tex, vl)'), 1)                 # (drawn once, not also before the mesh effects)

    def test_well_texture_coordinates(self):
        import numpy as np
        from dq456_pc.render import ido_effect as IE
        vt, _ = IE.grid(2, 1)
        uv = IE.texture_coords(vt, 0.04, -0.02)
        s = vt[:, :2] * 0.5 + 0.5; z2 = vt[:, 2:3] * 2.0
        self.assertTrue(np.allclose(uv, s + z2 * s * 0.04 + (1 - z2) * s * -0.02, atol=1e-6))
        self.assertFalse(np.allclose(uv[2], uv[5]))                      # (the top right corner of the first cell and the top left one of the second: same place, not the same texture point)


def data_pack():
    for game in ('dq6', 'dq5', 'dq4'):
        for apk in sorted(glob.glob(os.path.join(ROOT, 'data', 'apk', game, '*', 'split_UnityDataAssetPack.apk'))): return game, apk
    return None


@unittest.skipUnless(data_pack(), 'no APK files in data\\apk\\<game>\\<language>')
class GameShaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try: import UnityPy
        except ImportError: raise unittest.SkipTest('UnityPy missing')
        cls.game, apk = data_pack(); cls.shaders = {}
        for o in UnityPy.load(zipfile.ZipFile(apk).read(DATAPACK)).objects:
            if o.type.name == 'Shader':
                d = o.read(); cls.shaders[d.m_ParsedForm.m_Name] = d

    def passes(self, name):
        pf = self.shaders[name].m_ParsedForm
        for ss in pf.m_SubShaders:
            tags = dict(ss.m_Tags.tags if hasattr(ss.m_Tags, 'tags') else ss.m_Tags)
            for p in ss.m_Passes: yield tags, p.m_State

    def test_riseup_is_overlay_without_depth(self):
        found = list(self.passes('Custom/Riseup')); self.assertTrue(found)
        for tags, st in found:
            self.assertEqual(tags.get('QUEUE'), 'Overlay-150'); self.assertEqual((st.zTest.val, st.zWrite.val), (0.0, 0.0))          # (ZTest 0: disabled, the bubble is never hidden)

    def test_well_shader_formula(self):
        if 'Custom/Ido' not in self.shaders: self.skipTest('Custom/Ido is DQ VI\'s (pack read: %s)' % self.game)
        import lz4.block
        d = self.shaders['Custom/Ido']; blob = bytes(d.compressedBlob)
        flat = lambda x: [w for v in x for w in (flat(v) if isinstance(v, (list, tuple)) else [v])]
        text = ''.join(lz4.block.decompress(blob[o:o + c], uncompressed_size=n).decode('latin-1') for o, c, n in zip(flat(d.offsets), flat(d.compressedLengths), flat(d.decompressedLengths)))
        for line in ('u_xlat16_0.x = in_POSITION0.z + in_POSITION0.z;', 'u_xlat16_2.xy = in_POSITION0.xy * vec2(0.5, 0.5) + vec2(0.5, 0.5);',
                     'u_xlat1.xy = u_xlat16_0.xw * vec2(_BiasA) + u_xlat16_2.xy;', 'u_xlat16_0.x = (-in_POSITION0.z) * 2.0 + 1.0;'):
            self.assertIn(line, text)


if __name__ == '__main__':
    unittest.main(verbosity=1)
