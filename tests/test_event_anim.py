"""Map event animations: packet 6 (`cmd_fld_event_anim`) -> FldObject.SetEventAnimation + FEAN block, silently ignored until now.

  python3 tests/test_event_anim.py                                  (DQ_APK=<folder of the patched APKs> for the part on real data)

1. reading: FMAP carries `mobj` objects (the event objects follow the `nobj` map objects), FEAN = count, an unused float, (start, end) pairs - even when the size recorded in the chunk
   is too small (ddb5b);
2. packet 6: number < 0x1000 = event animation; >= 0x1000 = SetCameraNo (DQ IV: ignored; DQ V / VI: camera movement, see test_dq5_title); negative ignored;
3. `MapObjects.event_anim` (logic from the disassembly of SetEventAnimation, 0xCD637C): event objects hidden at the start; animation `no` shows start .. end - 1 and hides the map objects with the same
   non-zero `uid`; a following animation does not hide the objects of the previous one; 0 resets everything; number outside the table or map without FEAN: nothing; the display of packet 7 (mask) is added to the table;
   the animation of the shown objects restarts from the beginning; state saved / restored (savestates);
4. palettes linked to an event: the clock restarts from 0 when the event starts, the frame is the key's only from then on;
5. (real data) dhb2c (21 entries: one bingo cell per entry), ev05 (slot machine), ddb5b: event objects baked into the groups, hidden at the start, shown then hidden again.
"""
import os, struct, sys, tempfile, shutil, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper)
from dq456_pc.world import fld
from dq456_pc.world import map_objects as OC
from dq456_pc.core import engine as ENGINE

APK = os.environ.get('DQ_APK', '')
PACK = os.path.join(APK, 'split_UnityDataAssetPack.apk')


def chunk(tag, body, declared=None):
    n = 8 + len(body); b = struct.pack('<4sI', tag, n if declared is None else declared) + body
    return b + b'\0' * (-len(b) % 16)


def fmap(objects, nobj):
    """Chunk FMAP minimal : en-tete de 0x20 octets (tag, taille, nobj, mobj) puis 0x50 octets par objet ; `objects` = [(uid, mdl)] (mobj = leur nombre)."""
    body = bytearray()
    for uid, model in objects:
        o = bytearray(0x50); struct.pack_into('<hH', o, 28, model, 65535); struct.pack_into('<i', o, 44, uid); struct.pack_into('<3f', o, 32, 1.0, 1.0, 1.0); body += o
    hdr = bytearray(0x20); hdr[:4] = b'FMAP'; struct.pack_into('<I', hdr, 4, 0x20 + len(body)); struct.pack_into('<II', hdr, 8, nobj, len(objects))
    return bytes(hdr + body)


def tri(z):
    return np.array([[0, 0, z], [1, 0, z], [0, 1, z]], np.float32)


def carte(uids, nobj, ean, pmv_of=None, pam=None):
    """Dummy map: one triangle per object (in group 'k', at height z = index + 1), `uids[i]` = uid of object i, the first `nobj` are the map objects; `pmv_of` {object: movement}."""
    n = len(uids); objs = []; plages = {}; pos = np.zeros((3 * n, 3), np.float32)
    for i, uid in enumerate(uids):
        objs.append(dict(i=i, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0), model=i, canim=-1, flag=0, sequence_object=-1, pmv=(pmv_of or {}).get(i, -1), id=i, com=0, uid=uid, prio=0, rest=''))
        pos[3 * i:3 * i + 3] = tri(i + 1.0); plages[i] = [('k', 3 * i, 3)]
    motions = [dict(flag=0, nkey=2, repeat=-1, delay=0, loop_delay=0, end=60, keys=[(0, (0, 0, 0), (0, 0, 0), (1, 1, 1)), (60, (6.0, 0, 0), (0, 0, 0), (1, 1, 1))])]
    c = {'objects': objs, 'nobj': nobj, 'ean': ean, 'groups': {'k': (pos, np.zeros((3 * n, 2), np.float32), np.ones((3 * n, 4), np.float32))}, 'spans': plages, 'var': {}, 'tabs': [], 'motions': motions, 'sequences': [], 'sequence_entries': [], 'imgobj': {}}
    if pam: c.update(pam)
    return c


def shown(mo, i):
    """Does object i have its (non-zero) vertices in the group?"""
    return all(float(np.abs(mo.cur[k][d:d + n]).sum()) > 0 for k, d, n in mo.spans[i])


# 0 .. 3: map objects (uid 0, 7, 0, 9); 4, 5, 6: event objects (uid 7, 7, 9)
UIDS = [0, 7, 0, 9, 7, 7, 9]
EAN = [(4, 5), (5, 7)]


class Reading(unittest.TestCase):
    def test_fmap_reads_the_event_objects(self):
        n, objs = fld.map_objs(fmap([(0, 1), (7, 2), (9, 3)], nobj=2))                              # nobj = 2, mobj = 3
        self.assertEqual(n, 2); self.assertEqual([o['uid'] for o in objs], [0, 7, 9])               # before: only the first 2

    def test_fean_pairs(self):
        body = struct.pack('<i', 3) + struct.pack('<f', 63.0) + struct.pack('<6h', 15, 16, 16, 17, 17, 20)
        self.assertEqual(fld.fean(chunk(b'FEAN', body)), [(15, 16), (16, 17), (17, 20)])

    def test_fean_size_too_small_like_ddb5b(self):
        body = struct.pack('<i', 4) + struct.pack('<i', 8) + struct.pack('<8h', 19, 22, 22, 25, 25, 28, 28, 31)
        raw = chunk(b'FEAN', body, declared=0x18) + chunk(b'FETC', b'\0' * 8)                          # declared size 0x18 for 32 useful bytes
        self.assertEqual(fld.fean(raw), [(19, 22), (22, 25), (25, 28), (28, 31)])

    def test_no_fean(self): self.assertEqual(fld.fean(chunk(b'FETC', b'\0' * 8)), [])


class Packet6(unittest.TestCase):
    def apply(self, v):
        e = ENGINE.State(); e.apply([(6, [v], [])], lambda *a: '')
        return e.object_cmds

    def test_event_number(self):
        self.assertEqual(self.apply(3), [('event', 3)]); self.assertEqual(self.apply(0), [('event', 0)]); self.assertEqual(self.apply(0xfff), [('event', 0xfff)])

    def test_camera_and_negative_ignored(self):
        self.assertEqual(self.apply(0x1000), []); self.assertEqual(self.apply(0x1005), []); self.assertEqual(self.apply(-1), [])


class EventAnim(unittest.TestCase):
    def setUp(self): self.mo = OC.MapObjects(carte(UIDS, 4, EAN))

    def test_hidden_at_start(self):
        mo = self.mo
        self.assertEqual([shown(mo, i) for i in range(7)], [True] * 4 + [False] * 3)

    def test_animation_shows_range_and_hides_same_uid(self):
        mo = self.mo; mo.event_anim(1)                       # objet 4 (uid 7) : cache l'objet 1 (uid 7)
        self.assertEqual([shown(mo, i) for i in range(7)], [True, False, True, True, True, False, False])
        self.assertEqual(mo.event, 1)

    def test_range_with_two_objects(self):
        mo = self.mo; mo.event_anim(2)                       # objects 5 (uid 7) and 6 (uid 9): hide 1 and 3
        self.assertEqual([shown(mo, i) for i in range(7)], [True, False, True, False, False, True, True])

    def test_previous_animation_objects_stay_shown(self):
        mo = self.mo; mo.event_anim(1); mo.event_anim(2)
        self.assertTrue(shown(mo, 4) and shown(mo, 5) and shown(mo, 6)); self.assertFalse(shown(mo, 1)); self.assertFalse(shown(mo, 3))      # (the engine sends 0 to reset everything)

    def test_zero_restores_everything(self):
        mo = self.mo; mo.event_anim(1); mo.event_anim(2); mo.event_anim(0)
        self.assertEqual([shown(mo, i) for i in range(7)], [True] * 4 + [False] * 3); self.assertEqual(mo.event, 0)

    def test_unknown_number_and_negative_do_nothing(self):
        mo = self.mo; mo.event_anim(1); before = {k: v.copy() for k, v in mo.cur.items()}
        mo.event_anim(3); mo.event_anim(-1)
        for k in before: np.testing.assert_array_equal(mo.cur[k], before[k])
        self.assertEqual(mo.event, 1)

    def test_map_without_fean_does_nothing(self):
        mo = OC.MapObjects(carte([0, 7], 2, [])); mo.event_anim(0); mo.event_anim(1)
        self.assertTrue(shown(mo, 0) and shown(mo, 1)); self.assertEqual(mo.event, 0)

    def test_on_off_adds_to_the_table(self):
        mo = self.mo; mo.event_anim(1)
        mo.on_off(4, 1); self.assertFalse(shown(mo, 4))                       # paquet 7 : masque
        mo.on_off(4, 0); self.assertTrue(shown(mo, 4))
        mo.on_off(1, 0); self.assertFalse(shown(mo, 1))                       # the table (uid 7 replaces object 1) wins over "visible"
        mo.event_anim(0); self.assertTrue(shown(mo, 1))

    def test_animation_restarts_from_the_beginning(self):
        mo = OC.MapObjects(carte(UIDS, 4, EAN, pmv_of={4: 0}))               # event object 4 has a looping move (0 -> +6 in X over 60 / 60 s)
        self.assertNotIn(4, mo.auto)                                          # no clock while it is hidden
        mo.event_anim(1)
        self.assertIn(4, mo.auto)
        for _ in range(10): mo.tick()
        x_before = float(mo.cur['k'][12:15, 0].mean())
        self.assertGreater(x_before, 0.5 + 0.0)                               # 10 frames = 20 / 60 s: the triangle has moved
        mo.event_anim(0); mo.event_anim(1)                                    # restart: from the beginning
        self.assertEqual(mo.state[4]['motion_time'], 0)
        self.assertLess(float(mo.cur['k'][12:15, 0].mean()), x_before)

    def test_common_animation_zero_keeps_the_movement_of_an_object_without_sequence_slot(self):
        """FldObject.SetCommonAnimation does nothing to an object whose seq_obj_id is -1 (the three games), number 0 included: DQ V's ev06 sends 0 to the docked harbour of its
        second event animation, whose movement places it (the pier and its people stayed 21 units away when that order dropped the movement)."""
        mo = OC.MapObjects(carte(UIDS, 4, EAN, pmv_of={4: 0})); mo.event_anim(1)
        for _ in range(10): mo.tick()
        moved = mo.display_position(4)
        mo.common_anim(4, 0)
        self.assertIn(4, mo.auto); self.assertEqual(mo.display_position(4), moved)
        mo.objs[4]['sequence_object'] = 0; mo.common_anim(4, 0)                # (an object with a sequence slot: back to its original model, motionless)
        self.assertNotIn(4, mo.auto); self.assertEqual(mo.display_position(4), (0.0, 0.0, 0.0))

    def test_state_round_trip(self):
        mo = self.mo; mo.event_anim(2)
        copy = OC.MapObjects(carte(UIDS, 4, EAN)); copy.reinit(); copy.restore(mo.state, mo.auto, mo.event_state())
        self.assertEqual([shown(copy, i) for i in range(7)], [shown(mo, i) for i in range(7)]); self.assertEqual(copy.event, 2)

    def test_old_state_without_event_keeps_extras_hidden(self):
        mo = self.mo; mo.event_anim(1)
        copy = OC.MapObjects(carte(UIDS, 4, EAN)); copy.reinit(); copy.restore(dict(mo.state), None)
        self.assertEqual([shown(copy, i) for i in range(4, 7)], [False] * 3)

    def test_reinit_resets_the_table(self):
        mo = self.mo; mo.event_anim(1); mo.reinit()
        self.assertEqual([shown(mo, i) for i in range(7)], [True] * 4 + [False] * 3); self.assertEqual(mo.event, 0)


class Palettes(unittest.TestCase):
    def test_event_palette_clock_restarts(self):
        defs = {('pam', 'x', 0, 1): {'name': 'x', 'pam': 0, 'event': 1, 'images': [None, None]}, ('pam', 'y', 1, 0): {'name': 'y', 'pam': 1, 'event': 0, 'images': [None, None]}}
        p = OC.MapPalettes({'pamdef': defs, 'pam': [{'frame': 50, 'key': 1, 'durations': [100, 100]}, {'frame': 40, 'key': 1, 'durations': [100, 100]}]})
        p.start_event(2); self.assertEqual([q['frame'] for q in p.pams], [50, 40])           # another event: nothing
        p.start_event(1); self.assertEqual([q['frame'] for q in p.pams], [0, 40])
        self.assertEqual(p.image(('pam', 'x', 0, 1), 0), 0); self.assertEqual(p.image(('pam', 'x', 0, 1), 1), 1)         # frame 0 while the event is not running


class Dispatch(unittest.TestCase):
    """The window passes the order to the map objects and its palettes (`FieldMixin._map_objects`)."""
    def test_event_reaches_objects_and_palettes(self):
        import types, pyglet
        pyglet.options['shadow_window'] = False
        from dq456_pc.window import field as FI
        log = []
        objects = types.SimpleNamespace(event=0, dirty_uv=set(), dirty_col=set(), event_anim=lambda no: log.append(('objects', no)), tick=lambda: set())
        palettes = types.SimpleNamespace(start_event=lambda no: log.append(('palettes', no)), tick=lambda: None)
        e = types.SimpleNamespace(object_cmds=[('event', 4), ('event', 0)], game_map='ev05', part=0)
        fake = types.SimpleNamespace(engine=types.SimpleNamespace(state=e), objects=objects, palettes=palettes, map_name='ev05', ext_map=[], map_vl=[], n=0)
        FI.FieldMixin._map_objects(fake)
        self.assertEqual(log, [('objects', 4), ('palettes', 4), ('objects', 0), ('palettes', 0)]); self.assertEqual(e.object_cmds, [])


@unittest.skipUnless(os.path.exists(PACK), 'no game data pack (DQ_APK=<folder of the patched APKs>)')
class RealMaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.world import data as DO
        cls.cache = tempfile.mkdtemp(prefix='cache_test_event_anim_')
        cls.d = DO.Data(PACK, cls.cache, log=lambda *a: None)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.cache, ignore_errors=True)

    def test_dhb2c_one_cell_per_entry(self):
        c = self.d.game_map('dhb2c'); self.assertEqual((c['nobj'], len(c['objects']), len(c['ean'])), (15, 36, 21))
        self.assertEqual(c['ean'][0], (15, 16)); self.assertEqual(c['ean'][-1], (35, 36))
        mo = OC.MapObjects(c)
        self.assertTrue(all(shown(mo, i) for i in range(15))); self.assertFalse(any(shown(mo, i) for i in range(15, 36)))
        mo.event_anim(1)
        self.assertTrue(shown(mo, 15)); self.assertFalse(shown(mo, 3))                          # l'objet 15 (uid 501) remplace l'objet 3 (uid 501)
        self.assertEqual(sorted(mo.tbl_hidden - mo.extra), [3])
        mo.event_anim(0)
        self.assertTrue(shown(mo, 3)); self.assertFalse(shown(mo, 15))

    def test_every_fean_map_covers_exactly_its_event_objects(self):
        for nm in ('ev05', 'ddb5b', 'ddb2', 'dhf1'):
            c = self.d.game_map(nm); covered = sorted(k for s, e in c['ean'] for k in range(s, e))
            self.assertEqual(covered, list(range(c['nobj'], len(c['objects']))), nm)
            mo = OC.MapObjects(c)
            self.assertFalse(any(shown(mo, i) for i in mo.extra if i in mo.spans), nm)           # all hidden at first
            for no in range(1, len(c['ean']) + 1): mo.event_anim(no)
            self.assertTrue(all(shown(mo, i) for i in mo.extra if i in mo.spans), nm)           # all the animations played: all shown
            mo.event_anim(0); self.assertFalse(any(shown(mo, i) for i in mo.extra if i in mo.spans), nm)

    def test_ordinary_map_has_no_event_objects(self):
        c = self.d.game_map('mak1f1'); self.assertEqual(c['ean'], []); self.assertEqual(c['nobj'], len(c['objects']))


if __name__ == '__main__': unittest.main(verbosity=1)
