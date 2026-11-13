"""Minimal reading of a game adventure log file (data1.dat to data5.dat): enough to tell whether it is usable, without loading it into the engine.

Format (disassembly of Cryption::Filter 0x152de8 and Profile::isValidData; verified on a phone's saves and on those written by the engine): 15,360 bytes encrypted with an xorshift32 stream whose seed is the CRC32
(polynomial 0x7a7b58c6, key "vb76Eg43"); in plaintext: word 0 = "rate" (0x65747261) and word 1 = 0x0bf697de for a valid bank, "DWEN" (new bank) or "DLED" (deleted bank) for an empty bank; word 2 is the sum
of the first 0x3660 bytes (word 2 set to zero). data9.dat (512 bytes) is only a bank number: only its size is checked."""
import struct

from dq4_pc.language import tr

KEY, POLY = b'vb76Eg43', 0x7a7b58c6
MAGIC1, MAGIC2 = 0x65747261, 0x0bf697de
NEW, DELETED = 0x4e455744, 0x44454c44
LOGFILE_SIZE, SUM_SIZE = 0x3c00, 0x3660


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


def checksum(plain):
    b = bytearray(plain[:SUM_SIZE]); b[8:12] = b'\0\0\0\0'
    return sum(b) & 0xffffffff


def check(name_str, raw):
    """-> None if the file is usable, otherwise the reason (text for the player). The sizes are checked by the caller; data9.dat has no checksum."""
    if name_str.lower() == 'data9.dat' or len(raw) != LOGFILE_SIZE: return None
    plain = decrypt(raw); m0, m1, ck = struct.unpack_from('<III', plain, 0)
    if m0 in (NEW, DELETED): return None                                      # empty bank: valid, no checksum
    if m0 != MAGIC1 or m1 != MAGIC2: return tr('menus.not_game_adventure_log_unknown')
    if ck != checksum(plain): return tr('menus.damaged_file_checksum_mismatch')
    return None
