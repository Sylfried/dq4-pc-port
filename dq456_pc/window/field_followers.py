"""World map: the characters that walk with the camera (the hero behind his father in DQ V's first walk, the party behind the leader) drawn at a steady
distance from it.

The engine moves them by whole map pixels, each with its own pattern of 2 and 3 pixels per step (2.33 on average); the camera follows the leader exactly. A follower's
distance to the camera therefore goes back and forth by one pixel (27, 27, 27, 27, 27, 28, 28, 28...): four to six screen pixels on a large window, a tremble.
Its distance to the camera is drawn as the average of the last WINDOW steps, never further than MAX_LAG from the true one (a turn, a follower catching up), and back to
the true one when it stops. A character that does not move while the camera does (a ship left at the coast, a town's symbol) keeps its exact place: the error it had is
halved at each step."""
import collections

WINDOW = 8              # steps averaged: the longest pattern measured (5 x 27, 3 x 28)
MAX_LAG = 1.5           # map pixels: the drawn distance never differs more from the true one
JUMP = 24.0             # map pixels in one step: a jump (forced move, another place), never smoothed
SETTLED = 0.05          # map pixels: an error below this is dropped


class FieldFollowers:
    """Fed once per engine step (`step`); `offset(slot, a)` is what to add to the drawn (x, y) of a character, `a` being the fraction of the step."""

    def __init__(self): self.reset()

    def reset(self):
        self.cam = None; self.pos = {}; self.tracks = {}; self.err = {}; self.prev_err = {}

    def step(self, cam, sprites):
        """`cam`: (x, y) of the world map camera after the step, or None (not on the world map); `sprites`: {slot: (x, y, ...)}."""
        if cam is None: self.reset(); return
        cam = (float(cam[0]), float(cam[1]))
        cam_moved = self.cam is not None and cam != self.cam
        cam_jump = self.cam is not None and max(abs(cam[0] - self.cam[0]), abs(cam[1] - self.cam[1])) > JUMP
        self.prev_err = dict(self.err); err = {}; pos = {}
        for k, p in sprites.items():
            if p is None or len(p) < 2: continue
            xy = (float(p[0]), float(p[1])); pos[k] = xy; rel = (xy[0] - cam[0], xy[1] - cam[1])
            old = self.pos.get(k); tr = self.tracks.get(k)
            if old is None or tr is None or cam_jump or max(abs(xy[0] - old[0]), abs(xy[1] - old[1])) > JUMP:
                self.tracks[k] = collections.deque([rel], maxlen=WINDOW); self.prev_err.pop(k, None); continue          # (nothing drawn between the two places)
            moved = xy != old
            if moved == cam_moved:                                         # walking with the camera, or everything stopped: the average distance
                tr.append(rel)
                e = tuple(min(max(sum(r[i] for r in tr) / len(tr) - rel[i], -MAX_LAG), MAX_LAG) for i in (0, 1))
            else:                                                          # only one of them moves: back to the exact place
                self.tracks[k] = collections.deque([rel], maxlen=WINDOW)
                e = tuple(v * 0.5 for v in self.prev_err.get(k, (0.0, 0.0)))
            if max(abs(e[0]), abs(e[1])) >= SETTLED: err[k] = e
        self.cam = cam; self.pos = pos; self.err = err
        for k in list(self.tracks):
            if k not in pos: del self.tracks[k]

    def offset(self, slot, a=1.0):
        """(dx, dy) to add to the character's drawn position at fraction `a` of the step (between the previous step's error and this one's), or None."""
        e1 = self.err.get(slot); e0 = self.prev_err.get(slot)
        if e1 is None and e0 is None: return None
        e1 = e1 or (0.0, 0.0); e0 = e0 or (0.0, 0.0)
        return tuple(x + (y - x) * a for x, y in zip(e0, e1))
