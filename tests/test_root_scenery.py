"""Scenery whose mesh is carried by the map ROOT (MeshFilter + MeshRenderer on the GameObject `<name_str>.fld`, no `NNN_...` child): the map's object 0 is the root itself.
Before, `Data._extract_map` only looked at the numbered children: these 32 maps (18 battle backdrops: btl_mt_*, btl_po_*, btl_sd_*, btldc1, btldh1, btldp8_*, btlta2, btltd1_*;
14 places: ddb1b, dnb1b2, dnb2b3, dnb3b4, ev04, za1f6, za1f8, za1f9, za2f4..7, za2f9, za3f1) came out empty (zero vertices). Checks (if the data package exists: DQ_APK) that they have geometry, and that an ordinary scenery (numbered children) is unchanged.

    python3 tests/test_root_scenery.py
"""
import os, shutil, sys, tempfile, unittest


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
APK = os.environ.get('DQ_APK', '')
PACK = os.path.join(APK, 'split_UnityDataAssetPack.apk')

ROOT = ['btl_mt_d', 'btl_po_n', 'btl_sd_e', 'btldc1', 'btldh1', 'btldp8_d', 'btlta2', 'btltd1_d', 'ddb1b', 'dnb1b2', 'dnb2b3', 'dnb3b4', 'ev04', 'za1f6', 'za1f8', 'za1f9', 'za2f4', 'za2f5', 'za2f6', 'za2f7', 'za2f9', 'za3f1']
ORDINARY = ['btl_pl_d', 'btlcb1_d']


@unittest.skipUnless(os.path.exists(PACK), 'no game data pack')
class TestRootSceneries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.world import data as DO
        cls.cache = tempfile.mkdtemp(prefix='cache_test_racine_')
        cls.d = DO.Data(PACK, cls.cache, log=lambda *a: None)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.cache, ignore_errors=True)

    def vertices(self, name_str):
        c = self.d.game_map(name_str, True)
        return sum(len(g[0]) for g in c['groups'].values()), c

    def test_root_bears_geometry(self):
        for name_str in ROOT:
            n, c = self.vertices(name_str)
            self.assertGreater(n, 0, name_str)
            self.assertIn(0, c['spans'], name_str)               # map object 0 has geometry

    def test_ordinary_scenery_unchanged(self):
        for name_str in ORDINARY:
            n, c = self.vertices(name_str)
            self.assertGreater(n, 1000, name_str)
            self.assertEqual(sorted(c['spans']), [0, 1], name_str)     # two numbered objects (000_..., 001_...), as before


if __name__ == '__main__':
    unittest.main(verbosity=1)
