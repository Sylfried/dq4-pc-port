"""Vertex data copied into pyglet's buffers in one block (render/fast_vertices.py): the same buffer contents as pyglet's own path, much faster.

  python3 tests/test_fast_vertices.py          (needs an OpenGL context: PYGLET_HEADLESS=1 on a machine without a screen; not in the CI)

1. a vertex list created from numpy arrays, then rewritten with `vl.position[:] = a` and `vl.position = a`, holds what a list created and written through pyglet alone holds
   (float64 arrays rounded to float32 like ctypes does);
2. reading (`vl.position[:]`, one value, `len`, numpy.asarray) gives the values; lists and tuples still go through pyglet; a wrong size still raises ValueError;
3. 47 700 vertices (the DQ VI world map): one write in a few milliseconds.
"""
import os, sys, time, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
os.environ.setdefault('PYGLET_HEADLESS', '1')
import pyglet
from pyglet import gl
from pyglet.graphics.shader import Shader, ShaderProgram
from dq456_pc.render import fast_vertices as FV

VERTEX = """#version 330 core
in vec3 position; in vec2 tex_coords; in vec4 colors; out vec2 t; void main() { t = tex_coords; gl_Position = vec4(position, 1.0) * colors; }"""
FRAG = """#version 330 core
in vec2 t; out vec4 o; void main() { o = vec4(t, 0.0, 1.0); }"""


class FastVertices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = pyglet.window.Window(64, 64, visible=False)
        cls.prog = ShaderProgram(Shader(VERTEX, 'vertex'), Shader(FRAG, 'fragment'))
        FV.install()

    @classmethod
    def tearDownClass(cls): cls.window.close()

    @staticmethod
    def stored(vl, name):
        b = vl.domain.attrib_name_buffers[name]
        return np.frombuffer(bytes(memoryview(b.data).cast('B')), np.float32)[vl.start * b.count:(vl.start + vl.count) * b.count]

    def test_same_contents(self):
        rnd = np.random.RandomState(1); n = 300
        pos = rnd.rand(n * 3) * 100.0; uv = rnd.rand(n * 2).astype(np.float32); col = rnd.rand(n * 4).astype(np.float32)
        a = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', pos), tex_coords=('f', uv), colors=('f', col))
        b = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', pos.tolist()), tex_coords=('f', uv.tolist()), colors=('f', col.tolist()))
        for name in ('position', 'tex_coords', 'colors'): self.assertTrue(np.array_equal(self.stored(a, name), self.stored(b, name)), name)
        self.assertTrue(np.array_equal(self.stored(a, 'position'), pos.astype(np.float32)))
        pos2 = rnd.rand(n * 3).astype(np.float32); a.position[:] = pos2; b.position[:] = pos2.tolist()
        self.assertTrue(np.array_equal(self.stored(a, 'position'), self.stored(b, 'position')))
        pos3 = rnd.rand(n * 3); a.position = pos3; self.assertTrue(np.array_equal(self.stored(a, 'position'), pos3.astype(np.float32)))
        a.draw(gl.GL_TRIANGLES); b.draw(gl.GL_TRIANGLES)

    def test_reading_and_errors(self):
        a = self.prog.vertex_list(3, gl.GL_TRIANGLES, position=('f', [0, 0, 0, 1, 0, 0, 0, 1, 0]), tex_coords=('f', [0] * 6), colors=('f', [1] * 12))
        self.assertEqual(list(a.position[:]), [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]); self.assertEqual(len(a.position), 9); self.assertEqual(a.colors[5], 1.0)
        a.position[0:3] = (5, 6, 7); self.assertEqual(list(np.asarray(a.position)[:3]), [5.0, 6.0, 7.0])
        with self.assertRaises(ValueError): a.position[:] = np.zeros(6, np.float32)
        with self.assertRaises(ValueError): a.position = np.zeros(12, np.float32)

    def test_speed(self):
        n = 47700; pos = np.random.rand(n * 3).astype(np.float32)
        a = self.prog.vertex_list(n, gl.GL_TRIANGLES, position=('f', pos), tex_coords=('f', np.zeros(n * 2, np.float32)), colors=('f', np.ones(n * 4, np.float32)))
        t = time.perf_counter(); a.position[:] = pos; dt = time.perf_counter() - t
        self.assertLess(dt, 0.005, dt)


if __name__ == '__main__':
    unittest.main(verbosity=1)
