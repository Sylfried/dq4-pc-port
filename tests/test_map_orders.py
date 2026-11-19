"""Map loading safeguards: the engine's orders on the map objects always reach the objects of THEIR map, and the world grid read from memory is checked against the engine's own tiles."""
import os, sys, types, unittest
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.core import engine as ENGINE
from dq456_pc.window import field as FI


class Objects:
    """Stand-in for `MapObjects`: records the orders it receives."""
    def __init__(self, name): self.name = name; self.log = []; self.event = 0; self.dirty_uv = set(); self.dirty_col = set()
    def reinit(self): self.log.append(('reinit',))
    def common_anim(self, a, b): self.log.append(('anim', a, b))
    def on_off(self, a, b): self.log.append(('onoff', a, b))
    def alpha(self, a, b): self.log.append(('alpha', a, b))
    def position(self, a, b): self.log.append(('pos', a, b))
    def rotation(self, a, b): self.log.append(('rot', a, b))
    def event_anim(self, a): self.log.append(('event', a))
    def tick(self): return set()


def window(loaded, part=ENGINE.PART_TOWN):
    """A window with `loaded` already loaded; `_load_map` loads another one the way the real one ends (orders delivered)."""
    e = types.SimpleNamespace(object_cmds=[], game_map=loaded, part=part)
    w = types.SimpleNamespace(engine=types.SimpleNamespace(state=e), objects=Objects(loaded), palettes=None, map_name=loaded, ext_map=[], map_vl=[], n=0, loads=[])
    def load(name):
        w.loads.append(name); w.objects = Objects(name); w.map_name = name; FI.FieldMixin._deliver_orders(w, True)
    w._load_map = load
    return w, e


def step(w, e, *cmds, game_map=None, part=None):
    """One engine step as the window sees it: the engine's state, then `_map_objects`."""
    if game_map is not None: e.game_map = game_map
    if part is not None: e.part = part
    e.object_cmds = list(cmds)
    FI.FieldMixin._map_objects(w)


class Orders(unittest.TestCase):
    def test_orders_of_the_loaded_map_apply_at_once(self):
        w, e = window('dpa1')
        step(w, e, ('onoff', 3, 0), ('anim', 1, 2))
        self.assertEqual(w.objects.log, [('onoff', 3, 0), ('anim', 1, 2)]); self.assertEqual(w.loads, [])

    def test_same_map_again_reinitializes(self):
        w, e = window('dpa1')
        step(w, e, ('map',), ('onoff', 3, 1))
        self.assertEqual(w.objects.log, [('reinit',), ('onoff', 3, 1)])

    def test_new_map_gets_its_orders_after_its_load(self):
        w, e = window('dpa1'); old = w.objects
        step(w, e, ('map',), ('onoff', 3, 0), game_map='fk01')
        self.assertEqual(w.loads, ['fk01']); self.assertEqual(old.log, []); self.assertEqual(w.objects.log, [('onoff', 3, 0)])      # fresh objects: no reinit

    def test_orders_wait_on_the_world_map_and_never_reach_the_old_objects(self):
        """The teleportation case: the engine names the town while the part is still the world map; the window keeps the last town's objects."""
        w, e = window('dpa1', part=ENGINE.PART_FIELD); old = w.objects
        step(w, e, ('map',), ('onoff', 3, 0), game_map='fk01')
        self.assertEqual(old.log, []); self.assertEqual(w.loads, [])
        step(w, e, ('anim', 5, 6))                                   # still the world map: waiting
        self.assertEqual(old.log, []); self.assertEqual(w.loads, [])
        step(w, e, part=ENGINE.PART_TOWN)                            # the town: loaded, then every order given since the load, in order
        self.assertEqual(w.loads, ['fk01']); self.assertEqual(old.log, []); self.assertEqual(w.objects.log, [('onoff', 3, 0), ('anim', 5, 6)])

    def test_orders_wait_for_the_drawing_to_load_the_map(self):
        """The map is loaded by the drawing (not by an order step): the orders given before are delivered by the load itself."""
        w, e = window('dpa1', part=ENGINE.PART_FIELD)
        step(w, e, ('map',), ('onoff', 7, 1), game_map='dpb8b')
        e.part = ENGINE.PART_TOWN; w._load_map('dpb8b')
        self.assertEqual(w.objects.log, [('onoff', 7, 1)])

    def test_a_new_map_drops_what_the_unloaded_one_was_given(self):
        w, e = window('dpa1', part=ENGINE.PART_FIELD)
        step(w, e, ('map',), ('onoff', 1, 1), game_map='fk01')
        step(w, e, ('map',), ('onoff', 2, 2), game_map='dpb8b', part=ENGINE.PART_TOWN)
        self.assertEqual(w.loads, ['dpb8b']); self.assertEqual(w.objects.log, [('onoff', 2, 2)])

    def test_stale_list_is_void(self):
        w, e = window('dpa1', part=ENGINE.PART_FIELD)
        step(w, e, ('map',), ('onoff', 1, 1), game_map='fk01')
        step(w, e, game_map='dpb8b', part=ENGINE.PART_TOWN)           # another map, no mark seen (state loaded...)
        self.assertEqual(w.loads, []); self.assertEqual(w.objects.log, [])

    def test_map_that_cannot_be_loaded_drops_its_orders(self):
        w, e = window('dpa1')
        def load(name): w.map_name = name; w.objects = None; FI.FieldMixin._deliver_orders(w, True)
        w._load_map = load
        step(w, e, ('map',), ('onoff', 1, 1), game_map='zzz'); step(w, e)
        self.assertEqual(w._orders[1], [])


class WorldGrid(unittest.TestCase):
    """`Engine._world_matches`: the grid read from memory must give the tiles of packet 28 around the hero."""
    def engine(self, field):
        eng = object.__new__(ENGINE.Engine); eng.state = types.SimpleNamespace(field=field); return eng

    def test_matching_grid(self):
        ids = np.arange(64 * 64, dtype=np.int32).reshape(64, 64) % 700
        f = {'x0': 60, 'y0': 62, 'cols': 5, 'tiles': [int(v) for v in ids[(np.arange(62, 66) % 64)[:, None], (np.arange(60, 65) % 64)[None, :]].ravel()]}
        self.assertTrue(self.engine(f)._world_matches(ids))               # (the window wraps around the edges)

    def test_grid_of_water_is_refused(self):
        ids = np.full((64, 64), 3, np.int32)
        f = {'x0': 10, 'y0': 10, 'cols': 5, 'tiles': list(range(100, 120))}
        self.assertFalse(self.engine(f)._world_matches(ids))

    def test_nothing_to_compare_with_yet(self):
        ids = np.full((8, 8), 3, np.int32)
        self.assertTrue(self.engine(None)._world_matches(ids)); self.assertTrue(self.engine({'x0': 0, 'y0': 0, 'cols': 5, 'tiles': []})._world_matches(ids))


if __name__ == '__main__':
    unittest.main()
