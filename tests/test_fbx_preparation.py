"""Background cache preparation (world/data.py, Data.prepare): every 3D model of the data pack (GameObjects c0003 to c2000) is extracted in advance, not only those of the battle attacks,
the title dragon and the dream filter (and the veil of the unexplored lands of the map window). A model read on demand (c1000 to c1017: the models of the maps' scenes) loaded the whole data pack in the middle of a game: seconds of stalls when the scene
loaded. A preparation list written before this (without the "fbx" key) is rebuilt once, so the missing models are extracted at the next launch.

  python3 tests/test_fbx_preparation.py
"""
import json, os, sys, tempfile, threading, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.world import data as DO

GOS = {'abc1.fld': 1, 'c0003': 2, 'c1000': 3, 'c1017': 4, 'c1018': 5, 'c2000': 6, 'c12': 7, 'cx000': 8}


class FakeData(DO.Data):
    """The data pack replaced by a list of names; each extraction writes its cache file and is recorded."""
    def __init__(self, cache):
        super().__init__(None, cache, log=lambda *a: None); self.calls = []
    def _gos(self): self.calls.append('pack'); return GOS
    def _textures(self): return {'h1': 1, 'm001': 2}
    def _write(self, f): open(os.path.join(self.cache, f), 'wb').close()
    def game_map(self, n, *a): self.calls.append(('map', n)); self._write(DO.MAP_PREFIX + '%s.pkl' % n)
    def sheet(self, n): self.calls.append(('sheet', n)); self._write('sprite_h%d.npy' % n)
    def texture(self, n): self.calls.append(('texture', n)); self._write('tex_%s.npy' % n)
    def world_plan(self): self.calls.append('plan'); self._write('world_plan.npz')
    def world_veil(self): self.calls.append('veil'); self._write('world_veil.npy')
    def fbx_model(self, no): self.calls.append(('fbx', no)); self._write(DO.FBX_PREFIX + 'c%04d.pkl' % no)
    def free_up(self): pass


class Elements(unittest.TestCase):
    def test_every_model(self):
        d = FakeData(tempfile.mkdtemp())
        fbx = [int(n) for kind, n, _ in d._elements({'maps': [], 'sheets': [], 'monsters': [], 'fbx': ['1000', '1017', '3']}) if kind == 'fbx']
        self.assertEqual(fbx, sorted(set(fbx)), 'once each, in order')
        for no in (1000, 1017, 1018) + DO.FBX_COMBAT + DO.FBX_SCREEN: self.assertIn(no, fbx)


class Prepare(unittest.TestCase):
    def test_new_list_has_every_model(self):
        d = FakeData(tempfile.mkdtemp()); d.prepare(threading.Event())
        entries = json.load(open(os.path.join(d.cache, 'preparation.json'), encoding='utf-8'))
        self.assertEqual(entries['fbx'], ['3', '1000', '1017', '1018', '2000'], 'the GameObjects named c + 4 digits')
        self.assertIn(('fbx', 1000), d.calls); self.assertIn(('fbx', 1017), d.calls)
        self.assertIn('veil', d.calls, 'the veil of the map window too: nothing is left to read from the pack in a game')

    def test_old_list_rebuilt_once(self):
        d = FakeData(tempfile.mkdtemp()); d.prepare(threading.Event())
        os.remove(os.path.join(d.cache, DO.FBX_PREFIX + 'c1000.pkl'))
        p = os.path.join(d.cache, 'preparation.json'); entries = json.load(open(p, encoding='utf-8')); del entries['fbx']
        json.dump(entries, open(p, 'w', encoding='utf-8'))
        d.calls = []; d.prepare(threading.Event())
        self.assertIn('pack', d.calls, 'a list without the models is rebuilt'); self.assertEqual([c for c in d.calls if c != 'pack'], [('fbx', 1000)], 'only the missing model is extracted')
        d.calls = []; d.prepare(threading.Event())
        self.assertEqual(d.calls, [], 'everything ready: the data pack is not read any more')

    def test_veil_missing_noted_once(self):
        d = FakeData(tempfile.mkdtemp()); d.world_veil = lambda: (d.calls.append('veil'), None)[1]
        d.prepare(threading.Event())
        self.assertIn('world_veil', json.load(open(os.path.join(d.cache, 'preparation.json'), encoding='utf-8'))['failures'])
        d.calls = []; d.prepare(threading.Event()); self.assertEqual(d.calls, [], 'a veil that does not exist is not searched again')


if __name__ == '__main__':
    unittest.main()
