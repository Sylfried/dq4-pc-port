"""the 3D models of the data pack (`Resources/fbx/c<number>`) and who asks for them.

Established (libdq4core): packet 31 comes from `ModelObject::setup(index, model)`, called by `TownModelDraw::setup` with model = 1000 + the town character's graphic
(`TOWN_CHARACTER + 0x14`: c1000 to c1018, c1018 being the title dragon; town characters of kind 3 in `TownCharacterStorage::getContainer`, 5 at most) and by `CommonEffectCubic::setup`
(battle and bestiary effects: c3 to c609). Every model of the data pack extracts: 36, c1003 included (an empty slot in its Animation component's list).
    DQ_APK=<patched APKs folder> python3 tests/test_fbx_models.py        (a few minutes: the data pack is read once)
"""
import os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
APK = os.environ.get('DQ_APK')


class Source(unittest.TestCase):
    def test_empty_animation_slot_skipped(self):
        src = open(os.path.join(HERE, '..', 'dq4_pc', 'world', 'data.py'), encoding='utf-8').read()
        i = src.index("for cref in comps['Animation'].read().m_Animations:")
        self.assertIn("if not getattr(cref, 'm_PathID', 0): continue", src[i:i + 300])


@unittest.skipUnless(APK, 'APK: DQ_APK=<folder of the patched APKs>')
class AllModels(unittest.TestCase):
    def test_every_model_extracts(self):
        from dq4_pc.world import data as DO
        d = DO.Data(os.path.join(APK, 'split_UnityDataAssetPack.apk'), tempfile.mkdtemp(prefix='fbx_tous_'), log=lambda *a: None)
        ids = sorted(int(k[1:]) for k in d._gos() if re.fullmatch(r'c\d{4}', k))
        self.assertGreaterEqual(len(ids), 36); self.assertIn(1003, ids); self.assertIn(1018, ids)
        failed = {}
        for n in ids:
            try:
                m = d.fbx_model(n)
                if n != 2000: self.assertTrue(len(m['groups']) >= 1, n)                       # (c2000: the dream filter, a built-in plane: no group of its own)
            except Exception as ex: failed[n] = repr(ex)[:120]
        self.assertEqual(failed, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
