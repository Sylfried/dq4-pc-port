"""Choose or impose the engine state for the real-engine tests.

The saves read by the tests are the player's (`DQ_SAVES`): their content changes as soon as the player plays. A test that hard-codes
"save 1 is at chapter 1, map `mak1f1`, party Ragnar + Doc" breaks without any port defect being at fault
(20 failures and 6 errors in 7 files, all due to this one drift: save 1 had moved on to chapter 2).

Two ways to avoid it, in this order of preference:

1. **impose the wanted state** (`force_chapter`): the test no longer depends on any save. Measured: from save 1
   (chapter 2), `force_chapter(m, 1)` then `start_town('taf1')` gives back exactly packets 17 [1040, 1863] and 16 0x0c000508 of the
   lying-down soldier, which chapter 2 does not have;
2. **choose the save that fits** (`pick_save`) when the state cannot be imposed (the party's position, the world time), and
   **skip with a message saying what was missing** rather than failing opaquely.

What must never again be hard-coded in a test: a save number, a map name, a chapter, the party size,
a character's row in a list, their HP.
"""
import struct
import unittest

SLOTS = (1, 2, 3, 4, 5)

G_STORY = '_ZN6status7g_StoryE'                  # status::g_Story: +4 = the chapter
G_STAGE = '_ZN6status7g_StageE'                  # status::g_Stage: +0xcc = the world time
SET_CHAPTER = '_ZN6status11StoryStatus10setChapterEi'
CLOCK = 0xcc
EVENING = range(1984, 2240)                      # the world time at which the game switches the scenery and tints to evening (measured: 1000 = day, 1984 and 2239 = evening, 2240 and 64 = night)


def chapter(eng):
    """The current chapter (1 to 9)."""
    c = eng.core; return struct.unpack('<I', c.mem(c.export(G_STORY) + 4, 4))[0]


def force_chapter(eng, n):
    """Sets chapter `n` (`StoryStatus::setChapter`), as the game does between two chapters. Does not change the party, which comes from the save."""
    c = eng.core; c.call(c.export(SET_CHAPTER), c.export(G_STORY), n)


def world_clock(eng):
    """The world time, 0 to 0xd3f."""
    c = eng.core; return struct.unpack('<i', c.mem(c.export(G_STAGE) + CLOCK, 4))[0]


def party(eng):
    """The party slots shown on screen (0 = the hero), in order."""
    return sorted(k for k in eng.state.sprites if k < 8)


def settle(eng, frames=250, limit=1500):
    """Lets the map load, closes the save's welcome message and gives control back to the player."""
    from dq4_pc.core import engine as ENGINE
    for _ in range(frames): eng.step(0, 0)
    n = 0
    while (eng.msg_visible or eng.active_menu() is not None) and n < limit:
        n += 1
        if n % 6 == 0: eng.step(ENGINE.A, ENGINE.A)
        else: eng.step(0, 0)
    for _ in range(40): eng.step(0, 0)
    return eng


def load_any(eng, slots=SLOTS):
    """Loads the first non-empty save: for a test that then imposes everything it cares about (chapter, map). -> its number."""
    for slot in slots:
        if eng.load_save(slot): return slot
    raise unittest.SkipTest('no readable save in DQ_SAVES')


def pick_save(make_engine, want, hint, slots=SLOTS):
    """Returns (engine, number) for the first save that `want(engine)` accepts, otherwise skips the test, saying what was missing.

    `make_engine()` returns a **new** engine on each attempt: reloading a save into an engine that has already been used leaves the state of the
    previous one (measured: after an empty save, the previous save's map is still in place). `want` receives the engine right
    after loading and brings it into the state it wants itself (`settle` is there for the common case).
    """
    tried = []
    for slot in slots:
        eng = make_engine()
        if not eng.load_save(slot):
            tried.append('%d : vide' % slot); continue
        ok = False
        try: ok = bool(want(eng))
        except Exception as e: tried.append('%d : %s' % (slot, type(e).__name__)); continue
        tried.append('%d : %s (%s, chapitre %d)' % (slot, 'convient' if ok else 'non', eng.state.game_map, chapter(eng)))
        if ok: return eng, slot
    raise unittest.SkipTest('no save of DQ_SAVES fits — it would need %s. Tried: %s' % (hint, ' ; '.join(tried)))


G_PARTY = '_ZN6status7g_PartyE'
PARTY_CLEAR, PARTY_ADD, PARTY_COUNT = '_ZN6status11PartyStatus5clearEv', '_ZN6status11PartyStatus3addEi', '_ZNK6status11PartyStatus8getCountEv'


def force_party(eng, *who):
    """Imposes the party composition (`status::PartyStatus`), by slots of `originalPlayer_`: 3 = Ragnar, 12 = Doc...

    The `originalPlayer_` registry holds all the characters of the game and does not depend on the save; only the party does. Imposing
    the party makes everything that follows from it deterministic: the list of characters in the menus and each one's row (measured:
    from save 1, clear + add(3) + add(12) gives back "Ragnar" row 2 and "Doc" row 3). -> the number of members.
    """
    c = eng.core; p = c.export(G_PARTY)
    c.call(c.export(PARTY_CLEAR), p)
    for k in who: c.call(c.export(PARTY_ADD), p, k)
    for _ in range(30): eng.step(0, 0)
    return c.call(c.export(PARTY_COUNT), p)
