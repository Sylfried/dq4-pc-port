"""Test of the treasure chest dropped by an enemy at the end of a battle ("Le londuleux laisse tomber un coffre au tresor !", "Ragnar l'ouvre.", "Il contient ...", "Ragnar met ... dans le sac.").

Question: does the original game play a chest-opening sound effect during these messages? Answer established by reading the engine and running it:
  - what follows is the task BattleExecItem (4 subtasks BattleExecVictory30 to 32, messages 801876 and following): they only set a message (TextAPI::setMACRO0, BattleMessage::setMessage,
    BattleAutoFeed::setMessageSend) and give the item (PartyStatus::giveItem); none goes through SoundManager / Sound::sePlayDirect;
  - Unity only calls Sound.PlaySE directly in InputName.Update, MenuPortItem.Update and TouchPad.internalUpdate (buttons: sound effect 300);
  - in the real engine, with a forced loot, the only sound packets of the whole sequence are sound effect 300 ("beep") at the start of each of the 4 messages, played by ui_MsgLoop.
This test keeps this observation: if one day the engine asked for another sound during these messages, `State.sounds` would contain it and the viewer (Sound.events) would play it; the test would fail and show it.

The loot is forced in a throwaway engine: MonsterParty::getDropItem / getDropItemMonster (fields +0x3eac and +0x3eb0 of MonsterParty, written by checkDropItem at the end-of-battle draw) return an item
and a monster that are forced (the same method by which test_battle_history forces the composition of a group).

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_enemy_chest.py        (about a minute)
Without DQ_APK and DQ_SAVES, the real engine test is skipped.
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
FORCED_ITEM, FORCED_MONSTER = 1, 3          # bâton de cyprès; londuleux (the battle's monster)
SFX_BEEP = 300                                # sound effect played by ui_MsgLoop at the start of each message when the player has just regained control
STAGES = ('laisse tomber un coffre au trésor', "l'ouvre", 'Il contient', ('dans le sac', 'prend'))          # 4th message: "puts ... in the bag" when the character's inventory is full, "takes ..." otherwise — this depends on the player's save


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class ChestDroppedByEnemy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import unicorn; from dq456_pc.core import engine as ENGINE; from dq456_pc.persistence import savestates as SS
        cls.ENGINE, cls.SS = ENGINE, SS
        cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_coffre_')); c = cls.c = cls.eng.core
        SV.load_any(cls.eng)
        for _ in range(200): cls.eng.step(0, 0)
        enc = c.call(c.export('_ZN7Encount12getSingletonEv'), label='enc')
        def group(u, addr, sz, ud):                                                      # forced encounter: a londuleux
            for j in range(4):
                i, n = (FORCED_MONSTER, 1) if j == 0 else (0, 0)
                c.mem_w(enc + 0x34 + 4 * j, struct.pack('<I', i)); c.mem_w(enc + 0x44 + 4 * j, struct.pack('<I', n))
        a = c.export('_ZN10BattleRoot12setupMonsterEv'); c.uc.hook_add(unicorn.UC_HOOK_CODE, group, None, a, a)
        cls.loot = True
        def loot(u, addr, sz, ud):                                                       # end-of-battle draw: a chest containing FORCED_ITEM (or none)
            x0 = u.reg_read(c.XREG[0])
            c.mem_w(x0 + 0x3eac, struct.pack('<I', FORCED_ITEM if cls.loot else 0)); c.mem_w(x0 + 0x3eb0, struct.pack('<I', FORCED_MONSTER if cls.loot else 0))
        for n in ('_ZN6status12MonsterParty11getDropItemEv', '_ZN6status12MonsterParty18getDropItemMonsterEv'):
            a = c.export(n); c.uc.hook_add(unicorn.UC_HOOK_CODE, loot, None, a, a)
        c.uc.ctl_flush_tb()
        cls.initial = SS.snapshot(cls.eng)

    def play(self, loot):
        """Forced battle played to its end (A everywhere). -> (texts [(frame, text)], sounds [(frame, type, value)]); sounds = State.sounds, what the viewer passes to Sound.events."""
        ENGINE, eng, c = self.ENGINE, self.eng, self.c
        type(self).loot = loot
        self.SS.apply(eng, self.initial)
        texts, sounds = [], []
        def step(p=0, d=0):
            eng.state.sounds = []; eng.step(p, d); eng.ui.damage = []
            sounds.extend((eng.frames, t, v) for t, v in eng.state.sounds)
            for r in eng.sensor.drain(): texts.append((eng.frames, r['text'].replace('\xa0', ' ').replace('\n', ' / ').strip(' /')))
        for _ in range(3): step()
        texts.clear(); sounds.clear()
        c.call(c.export('_ZN6Global11startBattleEv'), eng._global(), label='startBattle')
        n = 0
        while eng.state.part != ENGINE.PART_BATTLE and n < 1500: step(); n += 1
        self.assertEqual(eng.state.part, ENGINE.PART_BATTLE)
        st = {'rel': None, 'pending': 0}
        for i in range(6000):
            p = d = 0
            if st['rel'] is not None: eng.send_menu(st['rel'], 1, -1, 0); st['rel'] = None
            port = eng.active_menu()
            if port is not None and not eng.msg_visible:
                st['pending'] += 1
                if st['pending'] % 4 == 0: eng.send_menu(port, 1, -1, 0x10); st['rel'] = port
            elif eng.msg_visible and (eng.ui.msg.get('feed') or eng.message_state()[1] in (3, 5)):
                st['pending'] += 1
                if st['pending'] % 4 == 0: p = d = ENGINE.A
            else: st['pending'] = 0
            prev = eng.state.part; step(p, d)
            if eng.state.part != ENGINE.PART_BATTLE and prev == ENGINE.PART_BATTLE: return texts, sounds
        self.fail('the battle does not end')

    @staticmethod
    def frame_of(texts, chunk):
        """Frame of the first message that contains `chunk` (or one of its variants when `chunk` is a tuple)."""
        parts = chunk if isinstance(chunk, tuple) else (chunk,)
        return next((im for im, t in texts if any(x in t for x in parts)), None)

    def test_message_sequence_and_only_sfx_300(self):
        texts, sounds = self.play(True)
        frames = [self.frame_of(texts, e) for e in STAGES]
        self.assertTrue(all(im is not None for im in frames), 'the 4 messages of the chest are shown: %r' % (frames,))
        self.assertEqual(frames, sorted(frames), 'in order: chest dropped, opening, content, item put in the bag')
        # window: from the start of the 1st message (the beep precedes the text by one frame) to that of the last (+ 3 frames)
        window = [(im, t, v) for im, t, v in sounds if frames[0] - 3 <= im <= frames[-1] + 3]
        self.assertEqual([v for _, t, v in window if t == 35], [SFX_BEEP] * 4, 'a single sound effect per message, beep 300: the engine requests no chest opening sound effect')
        self.assertEqual([t for _, t, v in window if t != 35], [], 'neither sound effect stop nor music during the chest sequence')

    def test_without_chest_no_message(self):
        texts, sounds = self.play(False)
        self.assertIsNone(self.frame_of(texts, STAGES[0]), 'without forced loot (item 0), no chest')
        self.assertTrue(any('pièces d\'or' in t for _, t in texts), 'the battle is won')


if __name__ == '__main__':
    unittest.main(verbosity=2)
