"""What belongs to a game follows its adventure logs: a game that no adventure log holds any more (its log deleted, written over by another game's save, or never
saved) loses its savestates (savestates/<ID>/), its rules (rules/<ID>.json) and its history (latest elements, favorites, battle replays). The game being played and the last one
played in the session keep theirs; a log that cannot be read: nothing is deleted.

  1. logfile_format.game_uid: the game's unique ID in an adventure log (plaintext + 0x538), None for an empty or deleted bank, Unreadable otherwise;
  2. savestates.journal_games / game_folders / drop_game; History.prune;
  3. SnapshotsMixin.follow_journals on a stand-in window;
  4. real files (DQ_SAVES): the ID read in each log is the one the engine gives the game.

    python3 tests/test_savestates_follow_journals.py
"""
import json, os, shutil, struct, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import paths as CH
from dq456_pc.core import history as HI
from dq456_pc.persistence import game_rules as GR
from dq456_pc.persistence import logfile_format as LF
from dq456_pc.persistence import savestates as SS

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def logfile(uid, deleted=False):
    """An adventure log holding the game `uid` (encrypted, checksum), or a deleted bank ("DLED" in word 0, as the game writes it)."""
    plain = bytearray(LF.LOGFILE_SIZE)
    if deleted: struct.pack_into('<II', plain, 0, LF.DELETED, 0xffffffff)
    else: struct.pack_into('<II', plain, 0, LF.MAGIC1, LF.MAGIC2); struct.pack_into('<I', plain, LF.UID_OFFSET, uid); struct.pack_into('<I', plain, 8, LF.checksum(bytes(plain)))
    return LF.decrypt(bytes(plain))


def put(path, raw=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as h: h.write(raw)


class Files(unittest.TestCase):
    def setUp(self): self.t = tempfile.mkdtemp(prefix='journals_')
    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def test_game_uid(self):
        self.assertEqual(LF.game_uid(logfile(0x7d3580f4)), 0x7d3580f4); self.assertIsNone(LF.game_uid(logfile(5, deleted=True)))
        for bad in (b'x' * 100, bytes(LF.LOGFILE_SIZE)): self.assertRaises(LF.Unreadable, LF.game_uid, bad)

    def test_journal_games_and_folders(self):
        p = lambda n: os.path.join(self.t, n)
        put(p('data1.dat'), logfile(0x11)); put(p('data2.dat'), logfile(0x22, deleted=True)); put(p('data4.dat'), logfile(0x11)); put(p('data9.dat'), b'\0' * 512)
        paths = {n: p(n) for n in ('data1.dat', 'data2.dat', 'data4.dat', 'data9.dat', 'data5.dat')}
        self.assertEqual(SS.journal_games(paths), {1: 0x11, 4: 0x11})                                     # (deleted, missing, data9: absent)
        put(p('data3.dat'), b'garbage'); paths['data3.dat'] = p('data3.dat'); self.assertIsNone(SS.journal_games(paths))          # (unknown content: nothing may be deleted)
        f = CH.FOLDERS.savestates_folder(self.t)
        put(os.path.join(SS.game_folder(f, 0x22), 'state_01.dqs')); put(os.path.join(f, 'state_02.dqs')); os.makedirs(os.path.join(f, 'other'))
        self.assertEqual(set(SS.game_folders(f)), {0x22})
        self.assertTrue(SS.drop_game(f, 0x22)); self.assertFalse(SS.drop_game(f, 0x22)); self.assertFalse(SS.drop_game(f, None)); self.assertTrue(os.path.isfile(os.path.join(f, 'state_02.dqs')))

    def test_history_prune(self):
        h = HI.History(os.path.join(self.t, 'settings', 'history_favorites.json')); folder = h.folder
        for ident in ('aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'cccccccccccc', 'dddddddddddd'):
            put(os.path.join(folder, ident + '.json'), b'{}'); put(os.path.join(folder, ident + '.favorites.json'), b'{}'); put(os.path.join(folder, ident, 'r.dqs'))
        h.index = {'1': {'id': 'aaaaaaaaaaaa', 'uid': 0x11}, '2': {'id': 'bbbbbbbbbbbb', 'uid': 0x22}, '5': {'id': 'cccccccccccc', 'uid': 0x33}}; h.adventure = 'dddddddddddd'
        gone = h.prune({1: 0x11, 2: 0x99})                                                                 # (log 2 written over by another game, log 5 deleted)
        self.assertEqual(gone, ['bbbbbbbbbbbb', 'cccccccccccc']); self.assertEqual(h.index, {'1': {'id': 'aaaaaaaaaaaa', 'uid': 0x11}})
        self.assertEqual(sorted(os.listdir(folder)), sorted(['aaaaaaaaaaaa', 'aaaaaaaaaaaa.json', 'aaaaaaaaaaaa.favorites.json', 'dddddddddddd', 'dddddddddddd.json', 'dddddddddddd.favorites.json', 'index.json']))
        with open(os.path.join(folder, 'index.json'), encoding='utf-8') as f: self.assertEqual(json.load(f)['banks'], {'1': {'id': 'aaaaaaaaaaaa', 'uid': 0x11}})


class Follow(unittest.TestCase):
    """follow_journals on a stand-in window: logs in its write folder; savestates, rules and history of five games."""
    def setUp(self):
        from dq456_pc.window import snapshots as SN
        self.SN = SN; self.last = SN.SnapshotsMixin._last_uid; SN.SnapshotsMixin._last_uid = None
        self.t = tempfile.mkdtemp(prefix='journals_follow_'); self.f = CH.FOLDERS.savestates_folder(self.t)
        for uid in (0x11, 0x22, 0x33, 0x44, 0x55):
            put(os.path.join(SS.game_folder(self.f, uid), 'state_01.dqs')); GR.save(self.t, uid, {'randomizer': {'seed': None}})
        self.log(1, 0x11); self.log(2, 0x22); self.log(3, 0x33)                                           # (0x44: a game never saved; 0x55: the last one played in the session)
        self.eng = types.SimpleNamespace(uid=None, playing=False); self.eng.game_uid = lambda: self.eng.uid; self.eng.in_game = lambda: self.eng.playing
        self.hist = types.SimpleNamespace(seen=[]); self.hist.prune = lambda games: self.hist.seen.append(dict(games)) or []
        self.w = types.SimpleNamespace(args=types.SimpleNamespace(saves_write=self.t, saves_read=None), engine=self.eng, history=self.hist)
        self.portage = (CH.FOLDERS.portage, CH.FOLDERS.savestates); CH.FOLDERS.portage = self.t; CH.FOLDERS.savestates = self.f          # (the usual saves folder: the history follows it)

    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True); self.SN.SnapshotsMixin._last_uid = self.last; CH.FOLDERS.portage, CH.FOLDERS.savestates = self.portage
    def log(self, n, uid, deleted=False): put(os.path.join(self.t, 'data%d.dat' % n), logfile(uid, deleted))
    def follow(self, prune=True): return self.SN.SnapshotsMixin.follow_journals(self.w, prune)
    def games(self): return sorted(SS.game_folders(self.f)), sorted(int(n[:8], 16) for n in GR.files(self.t))

    def test_startup_deletes_what_no_log_holds(self):
        self.SN.SnapshotsMixin._last_uid = 0x55
        out = self.follow()
        self.assertEqual(out['savestates'], [0x44]); self.assertEqual(out['rules'], [0x44]); self.assertEqual(self.games(), ([0x11, 0x22, 0x33, 0x55],) * 2)
        self.assertEqual(self.hist.seen, [{1: 0x11, 2: 0x22, 3: 0x33}])
        CH.FOLDERS.portage = os.path.join(self.t, 'elsewhere'); self.w.args.saves_write = self.t; self.follow(); self.assertEqual(len(self.hist.seen), 1)          # (another saves folder: the history is not touched)

    def test_deleted_log_and_game_saved_over_another(self):
        self.follow(); self.log(2, 0x22, deleted=True); self.follow()                                     # (log 2 deleted at the start menu)
        self.assertEqual(self.games()[0], [0x11, 0x33])
        self.eng.playing = True; self.eng.uid = 0x11; self.log(3, 0x11); self.follow()                     # (game 0x11 saved into slot 3: 0x33 gone, 0x11 keeps everything)
        self.assertEqual(self.games(), ([0x11],) * 2)

    def test_game_being_played_is_kept(self):
        self.eng.playing = True; self.eng.uid = 0x44; self.follow(); self.assertIn(0x44, self.games()[0])  # (a new game, not saved yet)
        self.eng.uid = 0x22; self.log(2, 0x11); self.follow(); self.assertIn(0x22, self.games()[0])         # (its log written over: still played)

    def test_unreadable_log_or_import_deletes_nothing(self):
        put(os.path.join(self.t, 'data5.dat'), b'garbage'); self.assertIsNone(self.follow()); self.assertEqual(self.games()[0], [0x11, 0x22, 0x33, 0x44, 0x55])
        os.remove(os.path.join(self.t, 'data5.dat')); self.assertIsNone(self.follow(prune=False)); self.assertEqual(len(self.games()[1]), 5)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK and DQ_SAVES')
class RealFiles(unittest.TestCase):
    def test_ids_of_the_real_logs(self):
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.persistence import saves as S
        games = SS.journal_games(S.effective_files(None, SAVES)); self.assertTrue(games)
        m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_journals_'))
        for n, uid in sorted(games.items())[:2]:
            if n > 3 or not m.load_save(n): continue
            for _ in range(20): m.step(0, 0)
            self.assertEqual(m.game_uid(), uid, n)


if __name__ == '__main__':
    unittest.main()
