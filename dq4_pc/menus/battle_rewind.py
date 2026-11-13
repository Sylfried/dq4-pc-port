"""Battle rewind: a battle of the history is replayed with its messages only, at the pace they had in the game.

Pure logic (no pyglet, tested by tests/test_battle_rewind.py): `Replay` takes the battle's log ([time since the first message in 1/60 s of game time, name, text], see history.battle_log) and a clock;
`tick(speed)` advances the replay by the real time elapsed times the battle speed ("Battle speed": Normal 1, Fast 2, Very fast 3; Manuel: each message waits for `advance`, like the
game's battle messages in Manuel). `shown` gives the messages already started, the last one being typed letter by letter. Nothing goes through the engine: the game is not touched.

The recorded times include the waits of the battle itself (the player choosing a command, the monsters' animations): a gap is cut at MAX_GAP so that a long hesitation is not replayed."""

MAX_GAP = 180                     # game frames (1/60 s): longest wait replayed between two messages (3 s at Normal)
FIRST_DELAY = 15                  # frames before the first message
CHARS_PER_FRAME = 1.0             # shortcut: typing speed chosen by the port (the engine's battle text speed is not measured); measure it on the engine if the replay looks off
HOLD = 60                         # frames after the last message is fully typed before the replay counts as finished


def schedule(log):
    """Start time (frames, from the opening of the rewind) of each message: the first after FIRST_DELAY, then the recorded gaps, each cut at MAX_GAP."""
    starts = []; prev = None; t = float(FIRST_DELAY)
    for m in log:
        if prev is not None: t += min(MAX_GAP, max(0, m[0] - prev))
        starts.append(t); prev = m[0]
    return starts


def factor(speed):
    """Replay speed for a "Battle speed" notch: Manual (0) and Normal (1) = 1, Fast = 2, Very fast = 3."""
    try: v = float(speed)
    except (TypeError, ValueError): return 1.0
    return max(1.0, min(3.0, v)) if v == v else 1.0


def manual(speed):
    """"Manual" notch: each message waits for a key."""
    return not isinstance(speed, bool) and isinstance(speed, (int, float)) and speed == 0


class Replay:
    def __init__(self, element, clock):
        self.e = element; self.log = [list(m) for m in element.log]; self.starts = schedule(self.log)
        self.clock = clock; self._last = clock(); self.t = 0.0
        self.allowed = 1                              # Manuel: messages allowed to start (advance() gives the next one)

    def _typed_until(self, i):
        """Time at which message i is fully typed."""
        return self.starts[i] + len(self.log[i][2]) / CHARS_PER_FRAME

    def tick(self, speed):
        """Advances by the real time elapsed since the last call. Manuel: time stops at the start of a message that advance() has not released yet."""
        now = self.clock(); dt = max(0.0, min(0.25, now - self._last)); self._last = now
        t = self.t + dt * 60.0 * factor(speed)
        if manual(speed) and self.allowed < len(self.starts): t = max(self.t, min(t, self.starts[self.allowed] - 1e-6))
        self.t = t

    def advance(self, speed):
        """Enter / click: the current message is typed in full; if it already is, the next message starts now (in Manuel it is also released)."""
        n = len(self.starts)
        cur = max([i for i in range(n) if self.starts[i] <= self.t] or [-1])
        if cur >= 0 and self.t < self._typed_until(cur): self.t = self._typed_until(cur); return
        if cur + 1 < n:
            self.allowed = max(self.allowed, cur + 2); self.t = max(self.t, self.starts[cur + 1])

    def shown(self):
        """[(name or None, whole text, number of characters typed so far)] of the messages already started, oldest first."""
        out = []
        for s, m in zip(self.starts, self.log):
            if s > self.t: break
            out.append((m[1], m[2], min(len(m[2]), max(0, int((self.t - s) * CHARS_PER_FRAME + 1e-6)))))
        return out

    def finished(self):
        return not self.starts or self.t >= self._typed_until(len(self.starts) - 1) + HOLD
