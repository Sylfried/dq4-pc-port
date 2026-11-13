"""Random encounters, day / night clock and walking speed.

What the original game does (read from the disassembly of libdq4core.so):
  - Each engine frame where the hero's position has changed (world map: FieldPlayerDoku::checkDokuDamage; towns and dungeons: TownDamageFloor::checkDamageFloor, both through
    CommonWalkDamage::checkWalk) calls `Encount::execWalk`. It counts 16 calls, then runs `Encount::exec` (once, or five times when [+0x2c] is non-zero).
  - `Encount::exec` calls `CountDown::exec` (0x1f454c): the counter [Encount+0x134] loses `2 x [Encount+0x144]`; the encounter is triggered when it becomes negative (state [+0x1c]: 0 -> 1 -> 2, then `brew`
    and `Global::startBattle`). The counter is drawn by `CountDown::setup` (0x1e00 + table[rand(31)]) at each map initialization (`Encount::setup`, hence also on return from a battle);
    its loss per call (`[+0x144]`) comes from `TileSubtractValue[tile] x terrain table >> 8` (setTileIdRate / setLandType, recomputed at each `exec`).
  - None of this depends on real time: the game counts ENGINE FRAMES where the hero advances (hence steps).

Random encounters: the viewer does NOT touch them. Accelerated walking (accelerator) runs the engine `a` times faster, so the hero takes `a` times more steps
per real second and the game triggers `a` times more encounters per second, exactly the mobile game's logic (x4: battles come 4 times faster than at x1, for the same number of steps). the counter
was reduced so that it was (1 + a) / 2: that hook has been removed.

Day / night clock: likewise, the viewer no longer touches it. World time advances only through the tail jump of `FieldPlayerDoku::checkDokuDamage`, at each hero step: at x4, four times
more steps per second, so night comes 4 times faster, as on mobile. (limited it to (1 + a) / 2 through a hook on that jump, since removed.)
"""


class Passer:
    """Lets through the fraction `factor` (0 to 1) of calls, evenly, carrying fractions over: out of n calls, floor(n x factor) (to within one) are let through; at 1 or more, all of them."""

    def __init__(self, factor=1.0):
        self.factor = factor; self.remainder = 0.0

    def allows(self):
        """True if this call must take place."""
        if self.factor >= 1.0: return True
        self.remainder += self.factor
        if self.remainder >= 1.0: self.remainder -= 1.0; return True
        return False
