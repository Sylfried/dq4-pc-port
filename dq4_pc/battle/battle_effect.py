"""Battle start effect (Capture.BattleEffect of the Unity layer): a screen capture, cut into 32 columns of chunks, shatters and falls
row after row, from top to bottom, then darkens to black.

Reproduces the game's rules, one update per frame (30 Hz):
  * two counters: A (0, 1, 2...) and B (0 until frame 21, then it follows A with a 20-frame lag); on every frame and for each chunk, the game randomly picks
    (1 chance in 3 for B) the counter that drives that chunk;
  * a chunk in row r moves if either counter exceeds r; the fall speed is -0.001953125 - (32 - r - column + counter) * 0.0015625
    (in normalized screen coordinates, -1..1), half of that when it is the "lagging" counter that made it move; the left and right edges move closer
    by about 0.001 per frame (the chunk narrows) and the chunk drifts 0.002 to the left;
  * a chunk's opacity decreases by 8/255 per frame of movement;
  * when A exceeds half the height, the capture's brightness drops by 2/56 per frame; the effect stops when A exceeds 56.
The original game cuts the portrait screen into 32 x 56 square chunks (56 = 32 / 0.5625). On a 16/9 screen we keep square chunks (32 x 18) and each row
takes the place of 56 / 18 original rows, so the timing (57 frames) is the same."""
import numpy as np

COLS = 32
DIV_Y = 56                 # int(32 / ASPECT_DEF) from the original: sets the duration of the effect
FRAMES = DIV_Y + 1         # number of updates before the end (A from 0 to 56)
DRIFT = -0.001953125
G_SPEED = -0.0015625
SHEAR = 0.001
# vertices of a chunk: 0 top left, 1 bottom left, 2 top right, 3 bottom right -> two triangles
TRIANGLES = np.array([0, 1, 2, 2, 1, 3])


class TilesEffect:
    def __init__(self, aspect, seed=1234):
        self.rows = max(4, int(COLS / max(aspect, 0.1)))
        R, C = self.rows, COLS
        self.rng = np.random.default_rng(seed)
        self.k = DIV_Y / float(R)                                   # original rows per displayed row
        self.line = (np.arange(R) * self.k)[:, None]               # original row number (float)
        self.col = np.arange(C)[None, :]
        x0 = -1.0 + np.arange(C) * (2.0 / C); x1 = x0 + 2.0 / C
        yh = 1.0 - np.arange(R) * (2.0 / R); yb = yh - 2.0 / R
        P = np.empty((R, C, 4, 2), np.float32)
        P[..., 0, 0] = x0[None, :]; P[..., 1, 0] = x0[None, :]; P[..., 2, 0] = x1[None, :]; P[..., 3, 0] = x1[None, :]
        P[..., 0, 1] = yh[:, None]; P[..., 2, 1] = yh[:, None]; P[..., 1, 1] = yb[:, None]; P[..., 3, 1] = yb[:, None]
        self.P = P; self.dec = np.zeros_like(P)
        u0 = np.arange(C) / float(C); u1 = u0 + 1.0 / C
        vh = 1.0 - np.arange(R) / float(R); vb = vh - 1.0 / R
        UV = np.empty((R, C, 4, 2), np.float32)
        UV[..., 0, 0] = u0[None, :]; UV[..., 1, 0] = u0[None, :]; UV[..., 2, 0] = u1[None, :]; UV[..., 3, 0] = u1[None, :]
        UV[..., 0, 1] = vh[:, None]; UV[..., 2, 1] = vh[:, None]; UV[..., 1, 1] = vb[:, None]; UV[..., 3, 1] = vb[:, None]
        self.UV = UV[:, :, TRIANGLES, :].reshape(-1, 2)
        self.alpha = np.full((R, C), 255, np.int32)
        self.A = 0; self.B = 0; self.lum = 1.0

    @property
    def frames(self):
        return self.A

    def stage(self):
        """One update (one game frame)."""
        R, C = self.rows, COLS; A, B = self.A, self.B
        on_b = self.rng.integers(0, 3, size=(R, C)) == 0
        chosen = np.where(on_b, B, A).astype(np.float64); other = np.where(on_b, A, B).astype(np.float64)
        full = chosen > self.line
        active = full | (other > self.line)
        dy = DRIFT + ((32.0 - self.line - self.col) + chosen) * G_SPEED
        sh = np.sin((chosen * 120.0 + 49152.0) / 65535.0) * SHEAR
        dy = np.where(full, dy, dy * 0.5); sh = np.where(full, sh, sh * 0.5)
        dx_g = np.where(active, sh + DRIFT, 0.0); dx_d = np.where(active, DRIFT - sh, 0.0); dy = np.where(active, dy, 0.0)
        self.dec[:, :, 0, 0] += dx_g; self.dec[:, :, 1, 0] += dx_g; self.dec[:, :, 2, 0] += dx_d; self.dec[:, :, 3, 0] += dx_d
        self.dec[:, :, :, 1] += dy[:, :, None]
        a = self.alpha
        bottom = active & (a > 0) & (a <= 7); topmost = active & (a > 7)
        a[topmost] -= 8; a[bottom] = 0
        self.A += 1
        if self.A >= 21: self.B += 1
        if self.A > DIV_Y // 2: self.lum = max(self.lum - 2.0 / DIV_Y, 0.0)

    @property
    def finished(self):
        return self.A > DIV_Y

    def positions(self):
        return (self.P + self.dec)[:, :, TRIANGLES, :].reshape(-1, 2)

    def colors(self):
        """One RGBA per vertex: white, chunk opacity."""
        a = np.clip(self.alpha, 0, 255).astype(np.float32) / 255.0
        c = np.ones((self.rows, COLS, 6, 4), np.float32); c[..., 3] = a[:, :, None]
        return c.reshape(-1, 4)
