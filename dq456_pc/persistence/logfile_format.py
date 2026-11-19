"""Minimal reading of a game adventure log file (data1.dat to data5.dat): enough to tell whether it is usable, without loading it into the engine.

Format (disassembly of Cryption::Filter 0x152de8 and Profile::isValidData; verified on a phone's saves and on those written by the engine): 15,360 bytes encrypted with an xorshift32 stream whose seed is the CRC32
(polynomial 0x7a7b58c6, key "vb76Eg43"); in plaintext: word 0 = "rate" (0x65747261) and word 1 = 0x0bf697de for a valid bank, "DWEN" (new bank) or "DLED" (deleted bank) for an empty bank; word 2 is the sum
of the first 0x3660 bytes (word 2 set to zero). data9.dat (512 bytes) is only a bank number: only its size is checked.
Dragon Quest V and VI (Profile::isValidData, Profile::calcCheckSum of their engines; checked on a save of each): the same file size, filter and key; another version word, a shorter checksummed
area, and in DQ VI an 8-byte header before "rate" (the checksum then at + 0x10): see FORMATS."""
import struct
from typing import NamedTuple, Optional

from dq456_pc import games as GM
from dq456_pc.language import tr

KEY, POLY = b'vb76Eg43', 0x7a7b58c6
MAGIC1, MAGIC2 = 0x65747261, 0x0bf697de
NEW, DELETED = 0x4e455744, 0x44454c44
LOGFILE_SIZE, SUM_SIZE = 0x3c00, 0x3660
UID_OFFSET = 0x538                    # in plaintext: the game's unique ID (status::g_Game + 8, the savestates' folder and the rules' file: savestates.game_folder, game_rules.path)


class Format(NamedTuple):
    header: int              # offset of "rate" (word 0 of the bank); "DWEN" / "DLED" there for an empty bank
    magic2: int              # the next word for a valid bank (the game's version signature)
    checksum: int            # offset of the checksum word (set to zero while summing)
    sum_size: int            # bytes summed, from the start of the file
    uid: Optional[int]       # offset of the game's unique ID (status::g_Game + 8); None: not known


FORMATS = {'dq4': Format(0, MAGIC2, 8, SUM_SIZE, UID_OFFSET),
           'dq5': Format(0, 0x0bf807ce, 8, 0x2b78, 0xc),
           'dq6': Format(8, 0x363fcf86, 0x10, 0x2ee8, 0x14)}          # (DQ VI draws no ID: 0 for an adventure made without the port's, see Engine._unique_id_hook_empty)


def _format(game=None):
    return FORMATS[game or GM.profile().key]


def _seed():
    s = 0xffffffff
    for ch in KEY:
        s ^= ch
        for _ in range(8): s = ((s >> 1) ^ (-(s & 1) & POLY)) & 0xffffffff
    return ~s & 0xffffffff


def decrypt(raw):
    """The game's filter (symmetric xor: also used to encrypt)."""
    s = _seed(); out = bytearray(len(raw))
    for i, b in enumerate(raw):
        s ^= (s << 13) & 0xffffffff; s ^= s >> 17; s ^= (s << 5) & 0xffffffff
        out[i] = b ^ (s & 0xff)
    return bytes(out)


def checksum(plain, game=None):
    f = _format(game)
    b = bytearray(plain[:f.sum_size]); b[f.checksum:f.checksum + 4] = b'\0\0\0\0'
    return sum(b) & 0xffffffff


def check(name_str, raw, game=None):
    """-> None if the file is usable, otherwise the reason (text for the player). The sizes are checked by the caller; data9.dat has no checksum. `game`: games.py key (default: the running game)."""
    if name_str.lower() == 'data9.dat' or len(raw) != LOGFILE_SIZE: return None
    f = _format(game); plain = decrypt(raw); m0, m1 = struct.unpack_from('<II', plain, f.header); ck, = struct.unpack_from('<I', plain, f.checksum)
    if m0 in (NEW, DELETED): return None                                      # empty bank: valid, no checksum
    if m0 != MAGIC1 or m1 != f.magic2: return tr('menus.not_game_adventure_log_unknown')
    if ck != checksum(plain, game): return tr('menus.damaged_file_checksum_mismatch')
    return None


class Unreadable(ValueError):
    """Not an adventure log of the game (wrong size or header): what it holds is unknown."""


def game_uid(raw, game=None):
    """The unique ID of the game an adventure log file holds; None for an empty or deleted bank ("DWEN" / "DLED"). Raises Unreadable if it is not an adventure log of the game
    (or if the place of the ID in this game's banks is not known)."""
    if len(raw) != LOGFILE_SIZE: raise Unreadable('size %d' % len(raw))
    f = _format(game); plain = decrypt(raw); m1, m2 = struct.unpack_from('<2I', plain, f.header)
    if m1 in (NEW, DELETED): return None                                      # (empty bank: "DWEN" / "DLED" in word 0, see check)
    if (m1, m2) == (MAGIC1, f.magic2) and f.uid is not None: return struct.unpack_from('<I', plain, f.uid)[0]
    raise Unreadable('header %08x %08x' % (m1, m2))
