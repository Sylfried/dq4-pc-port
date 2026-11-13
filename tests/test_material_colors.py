"""Animated material colors: FSRA block + FldObject.update_sra / sra_func, silently ignored until now (steam from hot springs, glows, fades in event scenes).

  python3 tests/test_material_colors.py                             (DQ_APK=<folder of the patched APKs> for the part on real data)

1. reading (`fld.sra`): material name (32 bytes), movement header, event number, 68-byte keys (frame + 4 RGBA colors; only the diffuse is used);
2. `MapObjects`: the diffuse color (key by key, fraction clamped to [0, 1]) is MULTIPLIED with the original vertex color; the _Color alpha of the material, baked into the vertices, is replaced by that of
   the key (diffuse / original alpha factor); entry's own clock (start delay, loops, duration, last key held); entry linked to an event: original color while the event is not
   running, restarts from the beginning at its launch (SetEventAnimation), original color restored when it stops; last winning entry on a shared range; sequence of meshes with variable colors:
   the factor is multiplied there too; state saved / restored; map reload;
3. (real data) 26 maps, 274 entries: same constants as the disassembly (sorted keys, first frame 0, last = end, diffuse RGB = 1); the targeted materials switch to transparent groups.
"""
import os, struct, sys, tempfile, shutil, unittest
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper)
from dq4_pc.world import fld
from dq4_pc.world import map_objects as OC

APK = os.environ.get('DQ_APK', '')
PACK = os.path.join(APK, 'split_UnityDataAssetPack.apk')


def chunk(tag, body, declared=None):
    n = 8 + len(body); b = struct.pack('<4sI', tag, n if declared is None else declared) + body
    return b + b'\0' * (-len(b) % 16)


def fsra(entries):
    """A single FSRA chunk at the start of a file: count, absolute offsets, then each entry (32-byte name, 6 words, 5 integers, 68-byte keys).
    `entries` = [dict(nom, flag, repeat, delai, rdelai, fin, event, keys=[(image, diffuse RGBA)])]."""
    n = len(entries); head = 4 + 4 * n; pos = 8 + head; pos += -pos % 16; offs = []; blobs = []
    for e in entries:
        keys = e['keys']; b = e['name'].encode().ljust(32, b'\0')
        b += struct.pack('<6h5i', e.get('flag', 0), len(keys), e['repeat'], e['delay'], e['loop_delay'], 68, 0, e['end'], e['event'], e['delay'], e['repeat'])
        for fr, rgba in keys: b += struct.pack('<i16f', fr, 0.5, 0.5, 0.5, 1.0, *rgba, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        offs.append(pos); blobs.append(b); pos += len(b)
    body = struct.pack('<i', n) + struct.pack('<%di' % n, *offs); body += b'\0' * (-(8 + len(body)) % 16) + b''.join(blobs)
    return chunk(b'FSRA', body)


def tri(z):
    return np.array([[0, 0, z], [1, 0, z], [0, 1, z]], np.float32)


def entry(name='x', event=0, keys=((0, 0.0), (60, 1.0)), repeat=-1, delay=0, loop_delay=0, end=None):
    return dict(name=name, event=event, repeat=repeat, delay=delay, loop_delay=loop_delay, end=keys[-1][0] if end is None else end, flag=0, nkey=len(keys), keys=[(f, (1.0, 1.0, 1.0, a)) for f, a in keys])


def carte(sra, spans, ean=(), alpha0=1.0, n=3):
    """Carte factice : `n` objets d'un triangle (groupe 'k', objet i = sommets 3i..3i+2, couleur de sommet (0.8, 0.6, 0.4, alpha0)) ; `spans[m]` = objets que vise l'entree m."""
    objs = []; plages = {}; pos = np.zeros((3 * n, 3), np.float32); col = np.tile(np.array([0.8, 0.6, 0.4, alpha0], np.float32), (3 * n, 1))
    for i in range(n):
        objs.append(dict(i=i, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0), model=i, canim=-1, flag=0, sequence_object=-1, pmv=-1, id=i, com=0, uid=0, prio=0, rest=''))
        pos[3 * i:3 * i + 3] = tri(i + 1.0); plages[i] = [('k', 3 * i, 3)]
    return {'objects': objs, 'nobj': n, 'ean': list(ean), 'groups': {'k': (pos, np.zeros((3 * n, 2), np.float32), col)}, 'spans': plages, 'var': {}, 'tabs': [], 'motions': [], 'sequences': [], 'sequence_entries': [],
            'imgobj': {}, 'sra': sra, 'sra_plages': [[('k', 3 * i, 3, alpha0) for i in objs_] for objs_ in spans]}


def alpha(mo, i): return float(mo.col('k')[3 * i:3 * i + 3, 3].mean())


def rgb(mo, i): return np.round(mo.col('k')[3 * i, :3], 4)


class Reading(unittest.TestCase):
    def test_entries(self):
        raw = fsra([entry('km0c_000', event=0, keys=((0, 0.9), (14, 0.0), (14, 0.0), (42, 0.9)), repeat=-1), entry('ymhd1a_001', event=3, keys=((0, 0.0), (500, 1.0)), repeat=1, delay=10, loop_delay=4)])
        a, b = fld.sra(raw)
        self.assertEqual((a['name'], a['event'], a['nkey'], a['repeat'], a['end']), ('km0c_000', 0, 4, -1, 42))
        self.assertEqual([k[0] for k in a['keys']], [0, 14, 14, 42]); self.assertEqual([round(k[1][3], 2) for k in a['keys']], [0.9, 0.0, 0.0, 0.9])
        self.assertEqual((b['name'], b['event'], b['repeat'], b['delay'], b['loop_delay'], b['end']), ('ymhd1a_001', 3, 1, 10, 4, 500))
        self.assertEqual(tuple(round(x, 2) for x in b['keys'][1][1]), (1.0, 1.0, 1.0, 1.0))              # the diffuse, not the ambient (0.5) nor the specular

    def test_no_fsra(self): self.assertEqual(fld.sra(chunk(b'FETC', b'\0' * 8)), [])


class Colors(unittest.TestCase):
    def test_fade_from_first_key_and_repeat(self):
        mo = OC.MapObjects(carte([entry()], [[1]]))
        self.assertEqual(alpha(mo, 1), 0.0); self.assertEqual(alpha(mo, 0), 1.0); self.assertEqual(alpha(mo, 2), 1.0)                  # the targeted range alone, from frame 0
        np.testing.assert_allclose(rgb(mo, 1), (0.8, 0.6, 0.4))                                                                        # the vertex color stays (the diffuse is 1)
        for _ in range(15): mo.tick()
        self.assertAlmostEqual(alpha(mo, 1), 0.5, 5)                                                                                  # temps 30 de 60
        for _ in range(15): mo.tick()
        self.assertAlmostEqual(alpha(mo, 1), 1.0, 5)
        self.assertIn('k', mo.dirty_col)

    def test_wraps_to_remainder(self):
        mo = OC.MapObjects(carte([entry(keys=((0, 0.0), (60, 1.0)))], [[0]]))
        for _ in range(31): mo.tick()                                                                                                  # temps 62 > 60 : retour au debut (reste 2)
        self.assertAlmostEqual(alpha(mo, 0), 2 / 60.0, 5)

    def test_material_alpha_replaced_not_multiplied(self):
        mo = OC.MapObjects(carte([entry(keys=((0, 0.25), (60, 1.0)))], [[0]], alpha0=0.5))                                              # _Color alpha 0.5 baked into the vertices
        self.assertAlmostEqual(alpha(mo, 0), 0.25, 5)
        for _ in range(30): mo.tick()
        self.assertAlmostEqual(alpha(mo, 0), 1.0, 5)                                                                                   # key 2: 1 (not 0.5 x 1)

    def test_diffuse_rgb_multiplies_vertex_colour(self):
        e = entry(); e['keys'] = [(0, (0.5, 1.0, 0.0, 1.0)), (60, (0.5, 1.0, 0.0, 1.0))]
        mo = OC.MapObjects(carte([e], [[0]]))
        np.testing.assert_allclose(rgb(mo, 0), (0.4, 0.6, 0.0)); self.assertAlmostEqual(alpha(mo, 0), 1.0, 5)

    def test_single_run_holds_last_key(self):
        mo = OC.MapObjects(carte([entry(keys=((0, 1.0), (20, 0.0)), repeat=1)], [[2]]))
        for _ in range(40): mo.tick()
        self.assertEqual(alpha(mo, 2), 0.0)
        for _ in range(5): mo.tick()
        self.assertEqual(alpha(mo, 2), 0.0)

    def test_start_delay_holds_first_key(self):
        mo = OC.MapObjects(carte([entry(keys=((0, 0.2), (60, 1.0)), delay=10)], [[0]]))
        for _ in range(5): mo.tick()                                                                                                   # 5 x 2 = 10: still in the delay
        self.assertAlmostEqual(alpha(mo, 0), 0.2, 5)
        for _ in range(15): mo.tick()                                                                                                  # 30 after the delay
        self.assertAlmostEqual(alpha(mo, 0), 0.2 + 0.8 * 0.5, 5)

    def test_no_keys_no_repeat_or_no_span_do_nothing(self):
        mo = OC.MapObjects(carte([entry(repeat=0), entry(), entry(end=0)], [[0], [], [1]]))
        self.assertEqual(sorted(mo.sra_h), [])
        for _ in range(5): mo.tick()
        self.assertEqual([alpha(mo, i) for i in range(3)], [1.0, 1.0, 1.0])

    def test_without_fsra(self):
        c = carte([], []); del c['sra']; del c['sra_plages']
        mo = OC.MapObjects(c); mo.tick(); self.assertEqual(mo.sra_h, {}); self.assertEqual(mo.sra_state(), {})

    def test_two_entries_one_span_last_wins(self):
        mo = OC.MapObjects(carte([entry(keys=((0, 0.3), (60, 0.3))), entry(event=1, keys=((0, 0.8), (60, 0.8)))], [[0], [0]], ean=[(0, 0)]))
        self.assertAlmostEqual(alpha(mo, 0), 0.3, 5)                                                                                   # the second one does nothing (event 1 not started)
        mo.event_anim(1); self.assertAlmostEqual(alpha(mo, 0), 0.8, 5)                                                                 # puis elle l'emporte
        mo.event_anim(0); self.assertAlmostEqual(alpha(mo, 0), 0.3, 5)


class Events(unittest.TestCase):
    def setUp(self): self.mo = OC.MapObjects(carte([entry(event=2, keys=((0, 0.0), (60, 0.8)), repeat=1)], [[1]], ean=[(0, 0), (0, 0)]))

    def test_original_colour_until_the_event(self):
        mo = self.mo
        self.assertEqual(alpha(mo, 1), 1.0)
        for _ in range(10): mo.tick()
        self.assertEqual(alpha(mo, 1), 1.0); self.assertEqual(mo.sra_h[0]['time'], 0)                                                  # (the clock does not run)

    def test_other_event_does_nothing(self):
        mo = self.mo; mo.event_anim(1)
        for _ in range(10): mo.tick()
        self.assertEqual(alpha(mo, 1), 1.0)

    def test_event_starts_from_the_beginning_and_ends_with_original_colour(self):
        mo = self.mo
        for _ in range(7): mo.tick()
        mo.event_anim(2); self.assertEqual(alpha(mo, 1), 0.0)
        for _ in range(15): mo.tick()
        self.assertAlmostEqual(alpha(mo, 1), 0.4, 5)
        mo.event_anim(0); self.assertEqual(alpha(mo, 1), 1.0)                                                                           # l'evenement s'arrete : couleur d'origine
        for _ in range(5): mo.tick()
        self.assertEqual(alpha(mo, 1), 1.0)
        mo.event_anim(2); self.assertEqual(alpha(mo, 1), 0.0)                                                                           # restart: from the beginning

    def test_out_of_table_event_changes_nothing(self):
        mo = self.mo; mo.event_anim(5); self.assertEqual(mo.event, 0); self.assertEqual(alpha(mo, 1), 1.0)

    def test_no_fean_no_event(self):
        mo = OC.MapObjects(carte([entry(event=1)], [[1]]))
        mo.event_anim(1)
        for _ in range(5): mo.tick()
        self.assertEqual(alpha(mo, 1), 1.0)


class Sequence(unittest.TestCase):
    def test_sequence_colours_are_multiplied(self):
        c = carte([entry(keys=((0, 0.5), (60, 0.5)))], [[0]])
        c['objects'][0]['sequence_object'] = 0; c['sequence_entries'] = [(0, 0, 0, 0, 0, -1, 0, 1)]; c['sequences'] = [{'flag': 0, 'keys': [(0, 0), (60, 1), (60, 2)], 'end': 60}]        # (last key = terminator, as in the data)
        c0 = np.tile(np.array([1.0, 1.0, 1.0, 1.0], np.float32), (3, 1)); c1 = np.tile(np.array([0.5, 0.4, 0.2, 1.0], np.float32), (3, 1))
        c['imgobj'] = {0: [{'pos': np.stack([tri(1.0), tri(1.0)]), 'uv': None, 'col': np.stack([c0, c1])}]}
        mo = OC.MapObjects(c); self.assertEqual(mo.sra_var, {('k', 0): 0})
        np.testing.assert_allclose(mo.col('k')[0], (1.0, 1.0, 1.0, 0.5), atol=1e-5)
        for _ in range(15): mo.tick()                                                                                                   # middle of the sequence: colour (0.75, 0.7, 0.6)
        np.testing.assert_allclose(mo.col('k')[0], (0.75, 0.7, 0.6, 0.5), atol=1e-5)


class SavedState(unittest.TestCase):
    def test_clocks_restored(self):
        c = carte([entry(), entry(event=1, keys=((0, 0.0), (40, 1.0)), repeat=1)], [[0], [2]], ean=[(0, 0)])
        a = OC.MapObjects(c); a.event_anim(1)
        for _ in range(13): a.tick()
        st, ev = a.sra_state(), a.event_state(); va = [alpha(a, 0), alpha(a, 2)]
        b = OC.MapObjects(c); b.reinit(); b.restore({}, None, ev, st)
        self.assertEqual([alpha(b, 0), alpha(b, 2)], va)
        for _ in range(4): a.tick(); b.tick()
        self.assertEqual([alpha(b, 0), alpha(b, 2)], [alpha(a, 0), alpha(a, 2)])

    def test_reinit_starts_over(self):
        mo = OC.MapObjects(carte([entry(), entry(event=1)], [[0], [1]], ean=[(0, 0)])); mo.event_anim(1)
        for _ in range(9): mo.tick()
        mo.reinit()
        self.assertEqual((alpha(mo, 0), alpha(mo, 1)), (0.0, 1.0)); self.assertEqual(mo.sra_h[0]['time'], 0)


@unittest.skipUnless(os.path.exists(PACK), 'no game data pack (DQ_APK=<folder of the patched APKs>)')
class RealMaps(unittest.TestCase):
    MAPS = ('btlde1 ckf3f5 cmf3b ddb2 deb1 deb2a dlb1a dlb3 dlb4 dlb5 dpb7b dpout ev02 ev05 ev06 ev08 mjf1f1 mnout mpout1 mpout2 mqout tcf5 za2f5 za2f7 za2f8 za3f2').split()

    @classmethod
    def setUpClass(cls):
        from dq4_pc.world import data as DO
        cls.cache = tempfile.mkdtemp(prefix='cache_test_material_colors_')
        cls.d = DO.Data(PACK, cls.cache, log=lambda *a: None)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.cache, ignore_errors=True)

    def test_274_entries_in_26_maps(self):
        total = 0
        for nm in self.MAPS:
            for s in fld.sra(self.d._map_text(nm)):
                total += 1; fr = [k[0] for k in s['keys']]
                self.assertEqual(fr, sorted(fr), nm); self.assertEqual((fr[0], fr[-1]), (0, s['end']), nm)
                self.assertTrue(all(tuple(k[1][:3]) == (1.0, 1.0, 1.0) for k in s['keys']), nm)                                         # seul l'alpha change
                self.assertTrue(s['event'] >= 0 and s['repeat'] != 0 and s['end'] > 0 and s['delay'] == 0, nm)
        self.assertEqual(total, 274)

    def test_steam_fades_in_and_loops(self):
        c = self.d.game_map('za2f7'); mo = OC.MapObjects(c)
        self.assertEqual(c['sra'][0]['name'], 'yuge1b_001'); self.assertEqual(len(c['sra_plages'][0]), 1)
        key, d, n, a = c['sra_plages'][0][0]; self.assertEqual(key[0], 'tr'); self.assertTrue(0.0 < a <= 1.0)                                  # materiau vise : groupe transparent
        al = lambda: float(mo.col(key)[d:d + n, 3].mean())
        self.assertEqual(al(), 0.0)
        for _ in range(30): mo.tick()                                                                                                   # temps 60 : pleine vapeur
        self.assertAlmostEqual(al(), 1.0, 5)
        for _ in range(30): mo.tick()                                                                                                   # time 120: end of the round
        self.assertAlmostEqual(al(), 1.0, 5)
        mo.tick(); self.assertAlmostEqual(al(), 2 / 60.0, 5)                                                                            # tour suivant (repeat -1)

    def test_event_materials_in_transparent_groups(self):
        for nm in ('ckf3f5', 'ev05', 'cmf3b'):
            c = self.d.game_map(nm); mo = OC.MapObjects(c)
            hit = [sp for lst in c['sra_plages'] for sp in lst]; self.assertTrue(hit, nm)
            self.assertTrue(all(isinstance(sp[0], tuple) and sp[0][0] == 'tr' for sp in hit), nm)
            self.assertTrue(all(0.0 < sp[3] <= 1.0 for sp in hit), nm)
            before = {sp[:2]: mo.col(sp[0])[sp[1]:sp[1] + sp[2]].copy() for sp in hit}
            mo.event_anim(1)                                                                                                            # (1 = first animation of these maps)
            for _ in range(3): mo.tick()
            self.assertTrue(any(not np.allclose(before[sp[:2]], mo.col(sp[0])[sp[1]:sp[1] + sp[2]]) for sp in hit), nm)

    def test_ev02_zwrite_groups_and_queue(self):
        """init_fld (map whose name contains "ev02"): bit 0x8000000 on objects 1, 4, 37 -> FSRA materials in Custom/fld_transz (ZWrite); set_priority2(object 4, 2999) -> queue 2999."""
        c = self.d.game_map('ev02'); fsra = {(k, d, n) for lst in c['sra_plages'] for k, d, n, _ in lst}
        self.assertTrue(fsra)
        for i, spans in c['spans'].items():                                                                                            # get_material_list: the material comes from the object (s6_001 is also in objects 23 to 33, without the bit: fld_trans)
            for k, d, n in spans:
                if (k, d, n) in fsra: self.assertEqual((len(k), k[3:]), (4, ('z',)) if i in (1, 4, 37) else (3, ()), (i, k))
        by_obj = {i: {sp[0] for sp in spans} for i, spans in c['spans'].items()}
        self.assertEqual({k[1] for k in by_obj[4] if isinstance(k, tuple)}, {-1})                                                       # object 4: queue 3000 - 1 = 2999 (not 3000 + 9)
        self.assertEqual({k[1] for k in by_obj[37] if isinstance(k, tuple) and len(k) == 4}, {12})                                      # objet 37 : priorite 12 conservee
        for nm in self.MAPS:
            if nm == 'ev02': continue
            c = self.d.game_map(nm)
            self.assertTrue(all(len(k) == 3 for spans in c['spans'].values() for k, _, _ in spans if isinstance(k, tuple) and k[0] == 'tr'), nm)      # elsewhere: fld_trans, no depth write

    def test_zwrite_group_drawn_with_depth_mask(self):
        import inspect
        from dq4_pc.window import field
        src = inspect.getsource(field.FieldMixin._paint_scenery)
        self.assertIn("glDepthMask(gl.GL_TRUE if len(key) == 4 else gl.GL_FALSE)", src)
        from dq4_pc.world import map_tint as TC
        self.assertTrue(TC.group_tz(('tr', 12, 202, 'z'), {202})); self.assertFalse(TC.group_tz(('tr', -1, 303, 'z'), {202}))


if __name__ == '__main__': unittest.main(verbosity=1)
