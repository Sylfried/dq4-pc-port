"""What differs between the engines of the three games (core/engine_layout.py) and the export lookup without namespace (emu_core.strip_namespace).

1. Packets: the DQ V / VI numbers translate into DQ IV's one to one (NativeManager's command table of each game), the three new commands get their own numbers.
2. Names: `_ZN3fld9FieldData9drawBlockEv` is found as `_ZN9FieldData9drawBlockEv`, `_ZN4ardq10ui_MsgLoopEv` as `_Z10ui_MsgLoopv`.
3. Real engine (DQ_APK, DQ IV): the addresses found in the code are the ones known before (engine_layout.DQ4).
4. Real engine (DQ_APK_DQ5 / DQ_APK_DQ6: folders of the French APKs of these games): the engine starts and runs, the title screen's part and map are read.

    python3 tests/test_engine_layout.py"""
import os, sys, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine_layout as LY
from dq456_pc.core import emu_core as T


def library(apk_folder, key):
    return zipfile.ZipFile(os.path.join(apk_folder, 'split_config.arm64_v8a.apk')).read('lib/arm64-v8a/lib%score.so' % key)


class Packets(unittest.TestCase):
    def test_one_to_one(self):
        m = LY.packets_v2()
        self.assertEqual(sorted(m), list(range(41)))                                      # 41 commands in DQ V / VI
        dq4 = sorted(v for v in m.values() if v < LY.FLD_ETC)
        self.assertEqual(dq4, list(range(38)))                                             # each of DQ IV's 38 commands once
        self.assertEqual((m[8], m[28], m[40]), (LY.FLD_ETC, LY.MESH_ORTHO, LY.PARTICLE))
        self.assertEqual((m[9], m[10], m[22], m[23], m[29], m[39]), (8, 9, 21, 22, 27, 37))  # back_color, fade, mesh_load, mesh, field_load, bgm

    def test_parts(self):
        self.assertEqual([LY.PARTS_V2[k] for k in (4, 5, 6, 0xb)], [0xc, 0xd, 0xe, 0xc])           # town, battle, world map; title (a scene drawn like a town)
        self.assertEqual([LY.PARTS['dq6'][k] for k in (4, 5, 6, 7, 0xa)], [0x3, 0xc, 0xd, 0xe, 0xc])     # DQ VI: start menu, town, battle, world map, title


class Names(unittest.TestCase):
    def test_strip_namespace(self):
        for name, alias in (('_ZN3fld9FieldData9drawBlockEv', '_ZN9FieldData9drawBlockEv'), ('_ZN4ardq10ui_MsgLoopEv', '_Z10ui_MsgLoopv'),
                            ('_ZN4menu17MaterielMenu_LOAD10menuUpdateEv', '_ZN17MaterielMenu_LOAD10menuUpdateEv'), ('_ZNK3fld5Field3getEv', '_ZNK5Field3getEv'),
                            ('_ZN4menu18gMaterielMenu_SAVEE', 'gMaterielMenu_SAVE'),
                            ('GameInit', None), ('_Z14UnityGetPacketi', None)):
            self.assertEqual(T.strip_namespace(name), alias, name)


@unittest.skipUnless(os.environ.get('DQ_APK'), 'DQ_APK (French APK folder of DQ IV) not set')
class Dq4Addresses(unittest.TestCase):
    def test_found_in_the_code_as_known_before(self):
        core = T.Core(library(os.environ['DQ_APK'], 'dq4'), None, lambda *a: None)
        lay = LY.Layout(core, False)
        for k, v in LY.DQ4.items():
            if k in ('resource_name', 'input_buffer'): continue                         # (read through strings[0] and core.inp instead)
            self.assertEqual(getattr(lay, k), core.LIB_BASE + v, k)
        self.assertEqual(lay.part_address, core.LIB_BASE + LY.DQ4['global_object'] + LY.PART_GLOBAL_V1)
        fixed = LY.Layout.fixed(core.LIB_BASE)
        for k in LY.DQ4: self.assertEqual(getattr(fixed, k), core.LIB_BASE + LY.DQ4[k], k)


class OtherEngines(unittest.TestCase):
    def run_game(self, key, variable):
        folder = os.environ.get(variable)
        if not folder: self.skipTest('%s (French APK folder of %s) not set' % (variable, key))
        os.environ['DQ_GAME'] = key
        try:
            import importlib
            from dq456_pc.core import engine as E
            importlib.reload(E)
            import tempfile
            saves = tempfile.mkdtemp(prefix='layout_')
            e = E.Engine(folder, saves, saves)
            for _ in range(300): e.step(0, 0)
            return e
        finally:
            os.environ.pop('DQ_GAME', None)
            importlib.reload(E)

    def test_dq5_starts(self):
        e = self.run_game('dq5', 'DQ_APK_DQ5')
        self.assertEqual(e.state.part, 0xc)                                               # the title part (Global::startTitle: ChangeGamePart(0xb)), drawn as a town: its map ev17
        self.assertEqual(e.state.game_map, 'ev17')
        self.assertIsNotNone(e.layout.obj_message); self.assertIsNotNone(e.layout.menu_ports)

    def test_dq6_starts(self):
        e = self.run_game('dq6', 'DQ_APK_DQ6')
        self.assertGreaterEqual(e.state.part, LY.PART_EXTRA)
        self.assertIsNotNone(e.layout.obj_message); self.assertIsNotNone(e.layout.menu_ports)


if __name__ == '__main__':
    unittest.main(verbosity=1)
