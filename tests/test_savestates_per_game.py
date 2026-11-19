"""Savestates of each game: savestates/<game ID in 8 hexadecimal digits>/state_NN.dqs (the game's unique ID, status::g_Game + 8, kept in its adventure log).

  1. listing, export and import keep the game folder (`<ID>/state_NN.dqs`); a state not sorted yet (`state_NN.dqs`) and an old name (`etats/etat_NN.dqs`) are still recognized;
  2. real engine (DQ_APK, DQ_SAVES): the ID read in a state is the one of its game; the states saved before (flat folder) go into the folder of their game, their number kept
     (or the first free one); a state of another library stays where it is.

    python3 tests/test_savestates_per_game.py
"""
import os, shutil, sys, tempfile, unittest, zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.persistence import saves as S
from dq456_pc.persistence import savestates as SS
from dq456_pc import paths as CH

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
STATE = b'DQ4ETAT1' + b'\0' * 2000          # (enough to be taken for a state by the import)


class Files(unittest.TestCase):
    def setUp(self): self.t = tempfile.mkdtemp(prefix='states_game_')
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def put(self, *parts):
        p = os.path.join(CH.FOLDERS.savestates_folder(self.t), *parts); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f: f.write(STATE)
        return p

    def test_game_folder(self):
        f = CH.FOLDERS.savestates_folder(self.t)
        self.assertEqual(SS.game_folder(f, 0xabc), os.path.join(f, '00000abc')); self.assertEqual(SS.game_folder(f, None), f)

    def test_listing_export_import(self):
        self.put('0000abcd', 'state_01.dqs'); self.put('12345678', 'state_09.dqs'); self.put('state_02.dqs'); self.put('other', 'state_03.dqs')
        self.assertEqual(sorted(S.savestates(self.t)), ['0000abcd/state_01.dqs', '12345678/state_09.dqs', 'state_02.dqs'])          # (a folder that is not a game ID: ignored)
        z = os.path.join(self.t, 'out.zip')
        with open(os.path.join(self.t, 'data1.dat'), 'wb') as f: f.write(valid_logfile())
        S.export_saves(self.t, None, z)
        with zipfile.ZipFile(z) as zz: self.assertIn('savestates/0000abcd/state_01.dqs', zz.namelist())
        dst = os.path.join(self.t, 'b'); S.import_saves([z], dst, None)
        self.assertEqual(sorted(S.savestates(dst)), ['0000abcd/state_01.dqs', '12345678/state_09.dqs', 'state_02.dqs'])

    def test_old_names(self):
        self.assertEqual(S.savestate_name('0000ABCD\\etat_04.dqs'), '0000abcd/state_04.dqs'); self.assertEqual(S.savestate_name('etat_04.dqs'), 'state_04.dqs')
        self.assertEqual(S.RE_SAVESTATE.search('etats/etat_05.dqs').group(1), 'etat_05.dqs')


def valid_logfile():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_paths
    return test_paths.valid_logfile(1)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def test_states_go_into_their_game_folder(self):
        from dq456_pc.core import engine as ENGINE
        t = tempfile.mkdtemp(prefix='states_game_real_'); f = os.path.join(t, 'savestates'); os.makedirs(f)
        try:
            m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_states_'))
            for _ in range(3): m.step(0, 0)
            m.load_save(4)
            for _ in range(30): m.step(0, 0)
            uid = m.game_uid(); d = SS.snapshot(m)
            self.assertEqual(SS.uid_of(d, m.core), uid)
            SS.write(os.path.join(f, 'state_03.dqs'), d, {}); SS.write(os.path.join(f, 'state_05.dqs'), dict(d, lib_sha='x'), {})          # (the second: another library)
            os.makedirs(SS.game_folder(f, uid)); SS.write(os.path.join(SS.game_folder(f, uid), 'state_03.dqs'), d, {})                     # (number already taken in the game's folder)
            self.assertEqual(SS.sort_by_game(f, m.core), 1)
            self.assertEqual(sorted(os.listdir(SS.game_folder(f, uid))), ['state_01.dqs', 'state_03.dqs']); self.assertEqual(sorted(n for n in os.listdir(f) if n.endswith('.dqs')), ['state_05.dqs'])
            self.assertEqual(SS.sort_by_game(f, m.core), 0)
        finally: shutil.rmtree(t, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=1)
