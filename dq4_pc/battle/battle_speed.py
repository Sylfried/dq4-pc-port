"""Battle speed: the engine clock during a battle (pure logic, no window or engine: tested by tests/test_battle_speed.py).

Principle: the original engine advances in steps of 1 / 30 s (Time.fixedDeltaTime). The viewer makes it perform 1, 2 or 3 times more steps per real second during a battle (setting "Battle speed":
Manuel and Normal: 1; Rapide: 2; Tres rapide: 3), instead of changing anything in the engine. Each step is exactly the game's own: the result of a battle (damage, action order, random draws, delays counted in
frames) therefore does not depend on speed; only the real duration changes. Everything the viewer animates during a battle is counted in engine steps (`engine.frames` + fraction `alpha`): damage numbers,
plate shakes, fades, battle start effect, message scrolling (written by the engine), 3D model animation; they therefore follow the accelerated clock.

What is NOT accelerated, on purpose:
  - music and sound effects: they are played by pyglet at their normal speed (real time, file duration); only the trigger TIME of a sound effect follows the engine. If acceleration makes the same
    sound effect arrive several times in the same displayed frame, it is played only once (`sounds_to_play`);
  - key READING while the player is being waited for (command menu, target choice, "Manual" message waiting for a key): the engine runs there at the setting's speed (monsters keep their idle animation
    at that speed) but only steps at normal cadence (one every 1 / 30 real seconds) read keys; the others are "muted" (window.tick(mute=True)): cursor and key repeat unchanged;
  - the accelerator key: it only multiplies walking and the camera outside battle. `factor` deliberately has no parameter for it."""
import math

ENGINE_STEP = 1.0 / 30.0                  # the original engine runs at 30 Hz
STEP_BUDGET = 0.030                       # maximum duration (s) of engine steps within a single displayed frame when the clock is accelerated: beyond it, the game falls behind instead of freezing the display
TOLERANCE = 0.85                         # a step is taken as soon as 85% of its duration has elapsed (60 Hz screen: exactly one step every 2 frames, with no 2 / 3 frame jitter)
ALPHA_LEAD = 1.0 - TOLERANCE             # the step taken early leaves the clock up to 15% of a step below zero: the displayed fraction is acc / step + ALPHA_LEAD (display_fraction), always in [0, 1),
                                         # continuous across steps; before, it was clamped at 0 and the picture jumped forward then stalled (ev09's clouds shook)


def display_fraction(acc, step=ENGINE_STEP):
    """Fraction of the way between the previous engine step and the current one to draw (characters, camera, map objects: Game.alpha), from the clock left by advance_time. A step is taken as soon as
    TOLERANCE of it has elapsed, so the clock can be up to (1 - TOLERANCE) step below zero: the fraction is shifted by that much (the picture shows 5 ms "later", the same amount at every frame) instead of
    being clamped at 0, which made smooth movements jump then stall on every screen with a little timing jitter, and on every screen faster than 60 Hz."""
    return max(0.0, min(1.0, acc / step + ALPHA_LEAD))
CATCHUP = 3                           # at most 3 catch-up steps per displayed frame at normal speed (a longer stall is forgotten)
MAX_SPEED = 3.0


def factor(speed, in_battle):
    """Engine clock factor during a battle; None outside battle (the caller then applies the walking speed). `speed`: setting "Battle speed" (0 Manuel, 1 Normal, 2 Rapide, 3 Tres rapide):
    Manuel and Normal keep the game's clock (factor 1; Manuel also advances messages by hand, see settings.scroll_code). Even when the engine is waiting for the player (command menu, target, message waiting
    for a key) the factor stays the setting's: monsters keep their idle animation at the chosen speed, and it is the key READING that stays at normal cadence (unmuted steps, see window._do_battle_step)."""
    if not in_battle: return None
    try: v = float(speed)
    except (TypeError, ValueError): return 1.0
    if v != v: return 1.0
    return max(1.0, min(MAX_SPEED, v))


def advance_time(acc, dt, f, do_step, clock, step=ENGINE_STEP, budget=STEP_BUDGET):
    """One displayed frame: the engine clock advances by `dt * f` seconds; `do_step()` performs one engine step as many times as the clock requires (at most 3 x ceil(f)), limiting the computation time to `budget`
    seconds when f > 1 (accelerated walking, battle). `do_step()` returns False when the engine has just started waiting for the player: we stop there, without catching up on the rest.
    -> (remaining acc in engine seconds, number of steps done, budget exceeded). The remaining clock is forgotten if the catch-up is at its maximum, if the budget is exceeded or if the engine is waiting for the player."""
    acc += min(dt * f, CATCHUP * step * max(1.0, f))
    n = 0; nmax = CATCHUP * max(1, math.ceil(f)); cut = False; waiting = False; t0 = clock()
    while acc >= step * TOLERANCE and n < nmax:
        suite = do_step(); acc -= step; n += 1
        if f > 1.0 and clock() - t0 > budget: cut = True; break
        if suite is False: waiting = True; break
    if n == nmax or cut or waiting: acc = 0.0
    return acc, n, cut


def sounds_to_play(events, already):
    """Sound orders of an engine step [(packet type, value)] -> those to play, without launching the same sound effect (packet 35) twice in the same displayed frame: `already` is the set of sound effects
    already launched since the start of this frame (updated here). A stop (packet 36) frees its sound effect: a new start after it is played. Music (packet 37) is never filtered. `already` None: everything passes."""
    if already is None: return list(events)
    out = []
    for t, v in events:
        if t == 35:
            if v in already: continue
            already.add(v)
        elif t == 36: already.discard(v)
        out.append((t, v))
    return out
