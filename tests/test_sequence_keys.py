"""Mesh sequences: the data's last key is a terminator (read as an ordinary key, the floating raft trembled a little).

  python3 tests/test_sequence_keys.py                    (DQ_APK=<folder of the APKs> for the part on real data)

Established in the disassembly of FldObject.update_seq_one (0xCDA55C) and fld_motion_update (0xCD69DC): the last FSQD key has frame = end and value = number of frames of the model.
  - sequence flag bit 0 = 0 (344 sequences): update_seq_one hands nkey - 1 keys to fld_motion_update (put back after), so at frame == end the key before (frame end too) is drawn;
  - bit 0 = 1 (503 sequences): the last key keeps its frame and takes the value of the key before it, or of the first key if the object has FLD_OBJ_FLAG_LOOP (2).
Read as is, the terminator's value (clamped to the last frame) was drawn once per round: the raft of Estuaria (map chout, object 75, frames 0 -> 1 -> 2 -> 0 over 116 sixtieths, terminator 3)
dipped to its frame 2 every two seconds.
"""
import os, sys, shutil, tempfile, unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper)
from dq456_pc.world import map_objects as OC

APK = os.environ.get('DQ_APK', '')
PACK = os.path.join(APK, 'split_UnityDataAssetPack.apk')
RAFT = {'flag': 0, 'nkey': 5, 'repeat': 0, 'delay': 0, 'loop_delay': 0, 'end': 116, 'keys': [(0, 0), (32, 1), (74, 2), (116, 0), (116, 3)]}


class Keys(unittest.TestCase):
    def test_terminator_left_out(self):
        self.assertEqual(OC.sequence_keys(RAFT, 0), [(0, 0), (32, 1), (74, 2), (116, 0)])
        self.assertEqual(OC.sequence_keys(RAFT, OC.FLD_OBJ_FLAG_LOOP), [(0, 0), (32, 1), (74, 2), (116, 0)])          # (bit 0 = 0: the object's flag plays no part)

    def test_flag_one_takes_the_key_before_or_the_first(self):
        s = {'flag': 1, 'end': 16, 'keys': [(0, 0), (4, 1), (8, 2), (12, 3), (14, 4), (16, 5)]}
        self.assertEqual(OC.sequence_keys(s, 0)[-1], (16, 4))
        self.assertEqual(OC.sequence_keys(s, OC.FLD_OBJ_FLAG_LOOP)[-1], (16, 0))
        self.assertEqual(len(OC.sequence_keys(s, 0)), 6)
        self.assertEqual(s['keys'][-1], (16, 5))                                                                   # (the data is not changed)

    def test_raft_round_without_jump(self):
        """The raft's round, step by step (2 sixtieths per engine step): the frame drawn at time 116 is frame 0, as at 114 and 2 (no jump to frame 2)."""
        img = {'pos': np.stack([np.zeros((3, 3)), np.full((3, 3), -0.1), np.full((3, 3), -0.13)]).astype(np.float32), 'uv': None, 'col': None}
        mo = OC.MapObjects.__new__(OC.MapObjects); mo._seq_keys = {}; mo.orig = {'g': np.zeros((3, 3), np.float32)}
        y = {}
        for t in (112, 114, 116, 2):
            st = {'sequence': RAFT, 'sequence_time': t, 'time': t}
            y[t] = float(mo._src_seq('g', 0, 3, img, st, 0)[0][0, 1])
        self.assertAlmostEqual(y[116], 0.0, places=6)
        self.assertLess(max(abs(y[a] - y[b]) for a, b in ((112, 114), (114, 116), (116, 2))), 0.01)


@unittest.skipUnless(os.path.exists(PACK), 'DQ_APK: folder of the APKs (split_UnityDataAssetPack.apk)')
class RealRaft(unittest.TestCase):
    def test_chout_raft(self):
        from dq456_pc.world import data as DO
        cache = tempfile.mkdtemp(prefix='cache_test_sequence_keys_')
        try:
            c = DO.Data(PACK, cache, log=lambda *a: None).game_map('chout')
            o = c['objects'][75]; e = c['sequence_entries'][o['sequence_object']]; sq = c['sequences'][e[1]]
            self.assertEqual((sq['flag'], sq['end'], sq['keys'][-1]), (0, 116, (116, 3)))
            mo = OC.MapObjects(c); key, d, n = mo.spans[75][0]
            seen = []
            for _ in range(70):                                                                                    # (one round and a bit: 58 steps)
                mo.tick(); seen.append(mo.cur[key][d:d + n].copy())
            jumps = [float(np.abs(b - a).max()) for a, b in zip(seen, seen[1:])]
            self.assertLess(max(jumps), 0.02, jumps)                                                                # (before: 0.13 at the end of each round)
        finally: shutil.rmtree(cache, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=1)
