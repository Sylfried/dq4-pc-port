"""Dungeon exit effect (Capture.Riremito, packet 34 value & 0xf = 6): the screen capture is displayed as FOUR superimposed translucent copies that move apart diagonally while rotating very slightly,
while the game camera is turned off; behind them, a full-screen plane shows the previous rendering (blurred half-resolution afterimage); from frame 30 the copies darken, everything fades out, then clean black
(Fade.SetFadeOutBlack(0)). 63 MoveNext calls: 2 of preparation (the game stays displayed), 59 mesh updates (counter 1 to 59), 1 of clean black, 1 of cleanup (MoveNext returns false: bit 1 drops).
Rules of Capture.<Riremito>d__48.MoveNext (libil2cpp, RVA 0xCC97FC), in float32 like the game (addresses in comments):
  * at the update with counter c: the rotation (degrees) grows by 0.11 per frame; copy i (0 to 3) is the square [-1, 1]^2 rotated by that angle around Z, then shifted by (+-3 u, +-u) with u = 10 (i + 1) c x 0.00005
    (diagonals: i = 0 right-bottom, 1 right-top, 2 left-top, 3 left-bottom);
  * updates 1 to 9: the background goes to (b, b, b, 1) with b = 0.1 c, the opacity of the copies to 0.9 - 0.08 c (0.18 at frame 9, then constant);
  * from c = 30: the color of the copies (r = g = b) decreases by 1/30 per frame down to 0 (reached at c = 59).
The mesh always has 20 vertices (it does not depend on the screen) and the positions are in normalized screen coordinates: the copies cover the whole screen whatever its aspect ratio (in 16/9 the displacement,
in fractions of the screen, is more horizontal than in portrait: reproduced as is)."""
import numpy as np
from dq4_pc.render import capture_effects as EC
from dq4_pc.render.capture_effects import F32, f32

CLONE_COUNT = 4
ROT_STEP = f32(0x3DE147AE)       # 0.11 degree per frame (pool 0x4C1304)
DEG_RAD = f32(0x3C8EFA35)       # pi / 180 (pool 0x4C13A0)
STEP_B = f32(0x3DCCCCCD)         # 0.1: step of the background AND z spacing between copies (pool 0x4C136C; z has no effect: ZTest Always)
STEP_C = f32(0xBDA3D70A)         # -0.08: step of the copies' opacity (pool 0x4C1508)
K_DEP = f32(0xB851B717)         # -0.00005: displacement factor (pool 0x4C1490)
FADE_STEP = f32(0xBD088889)      # -1/30 (pool 0x4C13E0)
INIT_C_ALPHA, INIT_B_ALPHA, INIT_ROT, INIT_FADE = f32(0x3F666666), F32(0.0), F32(0.0), F32(1.0)      # 0.9; 0; 0; 1 (pool 0x4DBB00)
LIMIT_B, FADE_START, END = 9, 30, 60                         # 0xCCA248, 0xCCA404, 0xCC9E28
CORNERS = np.array([[-1, 1], [-1, -1], [1, 1], [1, -1]], F32)    # vertices of a copy: top left, bottom left, top right, bottom right
TRIANGLES = np.array([0, 2, 1, 2, 3, 1])                            # triangles of a copy (loop 0xCC9B48)


class RiremitoEffect(EC.CaptureEffect):
    def __init__(self):
        super().__init__()
        self.duration = EC.FRAMES['riremito']
        self.state = 0                                         # <>1__state
        self.counter = 0; self.c_alpha = INIT_C_ALPHA; self.b_alpha = INIT_B_ALPHA; self.rot = INIT_ROT; self.fade = INIT_FADE
        self.vt = np.zeros((4 * CLONE_COUNT, 3), F32)           # vertices of the four copies (x, y, z)
        self.background_mat = np.ones(4, F32); self.mat_capture = np.ones(4, F32)     # _Color of the Custom/CaptureBlur and Custom/Capture materials
        idx = (np.arange(CLONE_COUNT)[:, None] * 4 + TRIANGLES[None, :]).ravel()
        self._idx = idx; self._uv = np.tile(EC.BACKGROUND_UV[TRIANGLES], (CLONE_COUNT, 1))
        self._background_uv = EC.BACKGROUND_UV[EC.BACKGROUND_TRIANGLES]; self._background_pos = EC.BACKGROUND_CORNERS[EC.BACKGROUND_TRIANGLES]

    # ------------------------------------------------------------------ one MoveNext call
    def _move_next(self):
        e = self.state
        if e == 0:                                            # 0xCC98F4: SetBlur(true), Snap()
            self._blur = True; self._capture = True; self.state = 1
            return True
        if e == 1:                                            # 0xCC99B0: mesh
            self.state = 2
            return True
        if e == 2:                                            # 0xCC9DC4: once the capture is taken: start of display and update 1
            if self._capture: return True
            self.render_active = True
            self.c_alpha, self.b_alpha, self.rot, self.fade = INIT_C_ALPHA, INIT_B_ALPHA, INIT_ROT, INIT_FADE
            self.counter = 1; self._update(); self.state = 3
            return True
        if e == 3:                                            # 0xCC9E18
            self.counter += 1
            if self.counter < END:
                self._update()
                return True
            self._blur = False; self.state = 4                 # 0xCC9E38: SetBlur(false); the host turns the screen black (Fade.SetFadeOutBlack(0))
            return True
        self.render_active = False; self.state = 5               # 0xCC9EDC: cleanup, MoveNext returns false
        return False

    def _update(self):
        """Update of the mesh and materials for the current counter (0xCCA204-0xCCA4C0)."""
        c = self.counter
        self.rot = F32(self.rot + ROT_STEP)
        half = F32(F32(self.rot * DEG_RAD) * F32(0.5))
        sz, cw = F32(np.sin(half)), F32(np.cos(half))        # Quaternion.Internal_FromEulerRad(0, 0, angle) = (0, 0, sin(angle / 2), cos(angle / 2))
        n3 = F32(sz * F32(2.0)); a = F32(F32(1.0) - F32(sz * n3)); n12 = F32(cw * n3)         # Quaternion * Vector3 (Unity formula)
        if c <= LIMIT_B:
            self.b_alpha = F32(self.b_alpha + STEP_B); self.background_mat[:] = (self.b_alpha, self.b_alpha, self.b_alpha, 1)
            self.c_alpha = F32(self.c_alpha + STEP_C); self.mat_capture[:] = (1, 1, 1, self.c_alpha)
        for i in range(CLONE_COUNT):
            t = F32(F32(10 * (i + 1)) * F32(c))
            dx = F32(F32(t * F32(3.0)) * K_DEP); dy = F32(t * K_DEP)
            if i == 0: dx = -dx
            elif i == 1: dx = -dx; dy = -dy
            elif i == 2: dy = -dy
            dz = F32(F32(i) * STEP_B)
            for j in range(4):
                px, py = CORNERS[j]
                self.vt[4 * i + j] = (F32(dx + F32(F32(a * px) + F32(-n12 * py))), F32(dy + F32(F32(n12 * px) + F32(a * py))), dz)
        if c >= FADE_START and self.fade > 0:
            self.fade = F32(max(F32(self.fade + FADE_STEP), F32(0.0)))
            self.mat_capture[:] = (self.fade, self.fade, self.fade, self.c_alpha)

    # ------------------------------------------------------------------ drawing
    def drawings(self):
        if not self.render_active: return []
        n = len(self._idx)
        return [('blur', self._background_pos, self._background_uv, np.tile(self.background_mat, (6, 1))),
                ('capture', self.vt[self._idx, :2], self._uv, np.tile(self.mat_capture, (n, 1)))]
