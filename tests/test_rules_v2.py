"""The rules of a game (Difficulty, Cheats) in Dragon Quest V and VI (engine.py: their own places of the engine's values):

1. DQ VI's adventure log keeps the game's ID at 0x14 (the port gives one: GameStatus::resetUniqueID draws none);
2. the battle's experience and gold are multiplied once, by the first reader (the victory message reads them before they are shared out);
3. (real data, DQ_APK_DQ5 / DQ_APK_DQ6) every instruction the hooks check is the one expected (rules, text speed, the Settings button, casino, battle history, play time, the copy's name, the randomizer).

    python3 tests/test_rules_v2.py
"""
import os, struct, sys, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.persistence import logfile_format as LF


class Dq6Log(unittest.TestCase):
    def test_uid(self):
        f = LF.FORMATS['dq6']
        plain = bytearray(b'\xd5' * LF.LOGFILE_SIZE)
        struct.pack_into('<II', plain, f.header, LF.MAGIC1, f.magic2); struct.pack_into('<I', plain, 0x14, 0x12345678)
        self.assertEqual(LF.game_uid(LF.decrypt(bytes(plain)), 'dq6'), 0x12345678)

    def test_empty_bank(self):
        f = LF.FORMATS['dq6']
        plain = bytearray(b'\xe5' * LF.LOGFILE_SIZE); plain[f.header:f.header + 4] = b'DWEN'
        self.assertIsNone(LF.game_uid(LF.decrypt(bytes(plain)), 'dq6'))


class FakeCore:
    """Memory, registers and hooks of the emulator, enough for _reward_hooks_v2."""
    XREG = list(range(32))

    def __init__(self, words):
        self.m = {}; self.words = words; self.hooks = []; self.regs = {}
        outer = self
        class UC:
            def hook_add(self, kind, fn, user, a, b): outer.hooks.append((a, fn))
            def reg_read(self, r): return outer.regs.get(r, 0)
        self.uc = UC()

    def export(self, name): return {n: 0x1000 + 0x10 * i for i, n in enumerate(sorted(self.words))}.get(name)
    def mem(self, a, n):
        for k, w in self.words.items():
            if a == self.export(k): return struct.pack('<I', w)[:n]
        return bytes(self.m.get(a + i, 0) for i in range(n))
    def mem_w(self, a, b):
        for i, x in enumerate(b): self.m[a + i] = x


class Rewards(unittest.TestCase):
    def test_once_per_battle(self):
        from dq456_pc.core import engine as ENGINE
        core = FakeCore(dict(zip(ENGINE.REWARD_READERS_V2, ENGINE.REWARD_WORDS_V2)))
        e = ENGINE.Engine.__new__(ENGINE.Engine); e.core = core; e.missing_hooks = []; e._flush_tb = lambda name: None
        e.exp_rate, e.gold_rate = 1.5, 0.5
        e._reward_hooks_v2()
        self.assertEqual(e.missing_hooks, []); self.assertEqual(len(core.hooks), 2)
        party = 0x8000; core.regs[0] = party
        core.mem_w(party + ENGINE.BATTLE_EXP_V2, struct.pack('<II', 100, 41))
        for a, fn in core.hooks: fn(core.uc, a, 4, None)                       # (both readers: multiplied once)
        self.assertEqual(struct.unpack('<II', core.mem(party + 8, 8)), (150, 21))
        core.mem_w(party + ENGINE.BATTLE_EXP_V2, struct.pack('<II', 10, 0))      # (the next battle)
        core.hooks[1][1](core.uc, 0, 4, None)
        self.assertEqual(struct.unpack('<II', core.mem(party + 8, 8)), (15, 0))

    def test_unexpected_code(self):
        from dq456_pc.core import engine as ENGINE
        core = FakeCore(dict(zip(ENGINE.REWARD_READERS_V2, (0, 0))))
        e = ENGINE.Engine.__new__(ENGINE.Engine); e.core = core; e.missing_hooks = []; e._flush_tb = lambda name: None
        e._reward_hooks_v2()
        self.assertEqual(len(core.hooks), 0); self.assertEqual(len(e.missing_hooks), 1)


def library(game):
    apk = os.path.join(os.environ.get('DQ_APK_' + game.upper(), ''), 'split_config.arm64_v8a.apk')
    if not os.path.isfile(apk): return None
    from dq456_pc.core.emu_core import Elf
    return Elf(zipfile.ZipFile(apk).read('lib/arm64-v8a/lib%score.so' % game))


class RealCode(unittest.TestCase):
    def check(self, game):
        from dq456_pc.core import engine as ENGINE
        elf = library(game)
        if elf is None: self.skipTest('DQ_APK_%s not set' % game.upper())
        word = lambda a: struct.unpack_from('<I', elf.img, a)[0]
        E = elf.exports
        for n, w in zip(ENGINE.REWARD_READERS_V2, ENGINE.REWARD_WORDS_V2): self.assertEqual(word(E[n]), w, n)
        fn, ret, kind = ENGINE.DAMAGE_V2[game]
        self.assertEqual((word(E[fn]), word(E[fn] + ret)), ENGINE.DAMAGE_WORDS)
        a = E[ENGINE.COUNTDOWN_FN_V2]; self.assertEqual((word(a), word(a + ENGINE.COUNTDOWN_RET)), ENGINE.COUNTDOWN_WORDS)
        off, w, reg = ENGINE.LEVELUP_V2[game]; self.assertEqual(word(E['_ZN6status10HaveStatus7levelupEb'] + off), w)
        pd, hsi, sh, sm = ENGINE.HEAL_V2[game]
        for n in (sh, sm, '_ZN6status15PartyStatusData8getCountEv', '_ZN6status15PartyStatusData8getOrderEi', '_ZN6status15PartyStatusData22getPlayerStatusForCtrlEi'): self.assertIn(n, E)
        self.assertEqual(word(E['_Z10ui_MsgLoopv'] + ENGINE.UI_MSGLOOP_V2[game]), ENGINE.SXTH_W20_W10)          # text speed
        off, w, reg, button = ENGINE.PARAMS_V2[game]; self.assertEqual(word(off), w)                           # the Miscellaneous menu's "Settings" button
        for name, off, w, reg in ENGINE.CASINO_WINS_V2[game]: self.assertEqual(word(E[name] + off), w, name)          # the casino's wins
        a = E['GameUpdate'] + ENGINE.PLAYTIME_V2[game]                                                        # play time
        self.assertEqual(word(a - 8), ENGINE.MOV_W1_2); self.assertEqual(word(a) & 0xfc000000, 0x94000000)
        self.assertEqual(bytes(elf.img[ENGINE.COPY_PREFIX_V2[game]:ENGINE.COPY_PREFIX_V2[game] + len(ENGINE.COPY_PREFIX_EN)]), ENGINE.COPY_PREFIX_EN)       # the copy's name
        self.assertEqual(word(E['_ZN4ardq6MsgVar11extract_varEPci'] + ENGINE.COPY_NAME_DONE), ENGINE.LDRB_W8_X20_12)
        self.assertEqual(word(E['_ZN3twn20TownFurnitureManager10initializeEv']), ENGINE.FURNITURE_INIT_V2)          # the randomizer's places
        off, w, reg = ENGINE.DROP_CHECK_V2[game]; self.assertEqual(word(E['_ZN6status12MonsterParty13checkDropItemEi'] + off), w)
        B = ENGINE.BREW_V2[game]; brew = E['_ZN3btl7Encount4brewEv']                                       # the randomizer's encounters
        self.assertEqual((word(brew), word(brew + B['groups'][0])), (B['entry'], B['groups'][1]))
        stubs = set()
        for name, off in B['random'] + B['forced']:                                                           # (a bl just before, all to the same place: brew's stub)
            i = word(E[name] + off - 4); self.assertEqual(i >> 26, 0x25, name); stubs.add(E[name] + off - 4 + (((i & 0x3ffffff) ^ 0x2000000) - 0x2000000) * 4)
        self.assertEqual(len(stubs), 1)
        r = E['_ZN2ar4randEi']; i1, i2 = word(r), word(r + 0xc)                                           # (ar::rand: adrp x9 / ldr w8, [x9, #n]: its state)
        page = (((i1 >> 5) & 0x7ffff) << 2 | (i1 >> 29) & 3) << 12
        self.assertEqual((r & ~0xfff) + page + ((i2 >> 10) & 0xfff) * 4, ENGINE.RNG_STATE_V2[game])
        g = E['_ZN12ScriptSystem12getSingletonEv' if game == 'dq5' else '_ZN6script12ScriptSystem12getSingletonEv'] + ENGINE.SCRIPT_SINGLETON_V2
        self.assertEqual((word(g) & 0x9f00001f, word(g + 4) & 0xffc003ff), (0x90000000, 0x91000000))       # (adrp x0 / add x0, x0)
        cf = E['_Z15CommandFunctionPv' if game == 'dq5' else '_ZN6script15CommandFunctionEPv']; self.assertEqual(word(cf), ENGINE.COMMAND_FN[1])
        from dq456_pc.battle import battle_history as BH                                                     # the battle history's places
        L = BH.LAYOUTS[game]
        for evt, name in L['hooks']: self.assertIn(name, E)
        self.assertIn(L['text'], E)
        for evt, name, off, w, reg in L['internal']: self.assertEqual(word(E[name] + off), w, evt)
        if game == 'dq6': self.assertEqual(word(E[ENGINE.UNIQUE_ID_EMPTY_V2[0]]), ENGINE.UNIQUE_ID_EMPTY_V2[1])
        else: name, off, w = ENGINE.UNIQUE_ID_STORE; self.assertEqual(word(E[name] + off), w)

    def test_dq5(self): self.check('dq5')

    def test_dq6(self): self.check('dq6')


if __name__ == '__main__':
    unittest.main()
