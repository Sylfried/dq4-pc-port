"""Travel effect (Capture.Tabi: Chimaera Wings, packet 34 value & 0xf = 3): the screen capture, laid on a grid of 16 columns of cells, is sucked into a swirl (zoom out + rotation
+ pinch toward the center) while two layers are superimposed: the capture (alpha "cAlpha") and a blurred copy of the previous frame (alpha "bAlpha", afterimage).
  * departure (bit 7 of the value at 0): the swirl tightens for 61 frames (time 0 -> 1, step of 1/60), then both layers go to alpha 0: black screen, the game camera stays turned off; 64 MoveNext calls;
  * arrival (bit 7 at 1, after the map change): the same swirl run backwards (time 2/3 -> 0, 41 frames) with a 30-frame fade-in, then the game is restored; 45 calls.
Rules of Capture.<Tabi>d__49.MoveNext (libil2cpp, RVA 0xCCAC3C), to the instruction (addresses in comments): vertices identical to the bit to the machine code run under Unicorn.
The original's mesh depends on the screen (`Capture.m_divY` = int(32 / aspect) read from the game camera: 56 in 9/16 portrait, hence 28 rows of cells; 18 in 16/9, hence 9): the 28 rows of the mobile game are kept here, because
the formulas are in normalized screen coordinates (the swirl has the same shape on screen, better sampled; 9 rows would make visible facets). These coordinates make the swirl elliptical on a 16/9 screen (as it is, the other way round, on the mobile game):
reproduced as is."""
import numpy as np
from dq456_pc.render import capture_effects as EC
from dq456_pc.render.capture_effects import F32, f32

COLS = 16                       # h_divX (0xCCAD38): cells per row
NX = COLS + 1                   # divX: vertices per row
ROWS = 28                    # h_divY = m_divY >> 1 (0xCCAD74) with m_divY = 56 (original portrait screen)
EPS = f32(0x38D1B717)           # 1e-4: fallback value of a vertex that crosses the center (pool 0x4C1258)
CORNER_R = f32(0x3FB50481)        # 1.4142 (not the true square root of 2): pool 0x4C1438
K_PINCH = F32(1.75)             # fmov 0xCCB2BC
K_ZOOM = F32(-0.5)              # fmov 0xCCB25C
K_DECAY_BLUR = f32(0xBC23D70A)    # -0.01: decrease of bAlpha per unit of time (pool 0x4C13C0)
K_DECAY_CAPTURE = f32(0xBD99999A)    # -0.075: decrease of cAlpha (pool 0x4C1278)
ROT_ACC = f32(0xBF866666)       # -1.05: rotAcc (pool 0x4DC044)
TIME_STEP = f32(0x3C888889)     # +1/60: timeAcc of the departure (pool 0x4DC04C)
BACK_T0 = f32(0x3F2AAAAA)     # 2/3: initial time of the arrival (pool 0x4C0CC8)
BACK_TIME_STEP = f32(0xBC888889)    # -1/60
ACC_BLUR = {False: f32(0x3E6CCCCD), True: f32(0x3E79999A)}      # 0.23125 (departure) / 0.24375 (arrival): rise of bAlpha per frame (pool 0x4C0B68)
ACC_CAPTURE_OUTBOUND = f32(0xBD800000)      # -0.0625: cAlpha step at departure (pool 0x4DC040)
ACC_CAPTURE_RETURN = f32(0x3D800000)     # +0.0625: cAlpha step at arrival (pool 0x4C0FF8)
END_COUNTER = 61               # 0xCCB0D4: end when the counter reaches 61
DECAY_START = 30         # 0xCCB170: departure only
F_ALPHA = {False: 4, True: 24}  # fAlpha: the alphas rise while counter < fAlpha (4 frames)
COUNTER_RETURN = 20            # 0xCCBA7C: initial counter of the arrival
Z_GRID = f32(0x3E828F5C)      # 0.255 (no effect: ZTest Always)


class TabiEffect(EC.CaptureEffect):
    def __init__(self, inverse=False, rows=ROWS):
        """inverse = bReverse (arrival); rows = h_divY (28: the mesh of the mobile game)."""
        super().__init__()
        self.inverse = bool(inverse)
        self.lines = max(1, int(rows)); self.ny = self.lines + 1
        self.num = NX * self.ny                                    # vertices of the grid
        self.duration = EC.frames_of('tabi', self.inverse)
        ax = F32(F32(2.0) / F32(COLS)); ay = F32(F32(2.0) / F32(self.lines))            # grid steps (0xCCAD94), accumulated in float32 like the game (0xCCAF4C)
        self._gx = np.add.accumulate(np.concatenate(([F32(-1.0)], np.full(NX - 1, ax, F32))), dtype=F32)
        self._gy = np.add.accumulate(np.concatenate(([F32(1.0)], np.full(self.ny - 1, -ay, F32))), dtype=F32)
        u = np.add.accumulate(np.concatenate(([F32(0.0)], np.full(NX - 1, F32(F32(1.0) / F32(COLS)), F32))), dtype=F32)
        v = np.add.accumulate(np.concatenate(([F32(1.0)], np.full(self.ny - 1, -F32(F32(1.0) / F32(self.lines)), F32))), dtype=F32)
        self._triangles = EC.triangle_grid(COLS, self.lines)
        self._uv = np.stack([np.tile(u, self.ny), np.repeat(v, NX)], 1).astype(F32)[self._triangles]       # (3 * 2 * cells, 2): constant
        self._vt = np.zeros((self.num, 2), F32)                    # x, y of the grid vertices (z has no effect)
        self._background_uv = EC.BACKGROUND_UV[EC.BACKGROUND_TRIANGLES]; self._background_pos = EC.BACKGROUND_CORNERS[EC.BACKGROUND_TRIANGLES]
        self.state = 0                                             # <>1__state
        self.counter = 0; self.clock = F32(0.0); self.time_step = TIME_STEP; self.rot_acc = ROT_ACC; self.f_alpha = 4
        self.alpha_blur = F32(0.0); self.acc_blur = F32(0.0); self.alpha_capture = F32(0.0); self.acc_capture = F32(0.0)
        self.black_final = False                                   # end of departure: _Color of both materials = (0, 0, 0, 0)

    # ------------------------------------------------------------------ one MoveNext call
    def _move_next(self):
        e = self.state
        if e == 0:                                    # 0xCCAD34: SetBlur(true), Snap()
            self._blur = True; self._capture = True; self.state = 1
            return True
        if e == 1:                                    # 0xCCADCC: mesh (the grid is written as is by state 2)
            self.state = 2
            return True
        if e == 2:                                    # 0xCCAF80: once the capture is taken: setup, then first frame of the swirl
            if self._capture: return True
            self._begin(); self._body(); self.state = 3
            return True
        if e == 3:                                    # 0xCCB0C0
            self.counter += 1
            if self.counter >= END_COUNTER:         # 0xCCB510
                if not self.inverse:                  # 0xCCB9A8: both materials at (0, 0, 0, 0): black screen; nothing is restored (the game camera stays turned off until the arrival)
                    self.black_final = True; self.state = -1
                    return False
                self._blur = False; self.state = 4     # 0xCCB530: SetBlur(false), then one more frame
                return True
            self._body()
            return True
        if e == 4:                                    # 0xCCB430: Mesh.Clear, rendering turned off, game camera re-enabled: end of the arrival
            self.render_active = False; self.state = -1
            return False
        return False

    def _begin(self):
        """State 2 (0xCCAFE8-0xCCBAF4): rendering enabled, black background, game camera turned off; variables of the departure or the arrival."""
        self.render_active = True
        inv = self.inverse
        self.acc_blur = ACC_BLUR[inv]; self.alpha_blur = F32(0.0)
        self.alpha_capture = F32(F32(1.0) - self.acc_blur); self.acc_capture = ACC_CAPTURE_OUTBOUND
        self.rot_acc = ROT_ACC; self.clock = F32(0.0); self.time_step = TIME_STEP; self.f_alpha = F_ALPHA[False]; self.counter = 0
        if inv:                                       # 0xCCBA60
            self.clock = BACK_T0; self.time_step = BACK_TIME_STEP; self.counter = COUNTER_RETURN; self.f_alpha = F_ALPHA[True]
            self.alpha_capture = F32(0.0); self.acc_capture = ACC_CAPTURE_RETURN

    def _body(self):
        """One frame of the swirl (0xCCB0DC-0xCCB3D8): alphas of the two layers, then vertices of the grid."""
        t = self.clock
        if self.counter < self.f_alpha:              # rise of the alphas (4 frames)
            self.alpha_blur = F32(self.alpha_blur + self.acc_blur)
            self.alpha_capture = F32(self.alpha_capture + self.acc_capture)
        if (not self.inverse) and self.counter >= DECAY_START:      # decrease (departure only): cAlpha = 0 from frame 41, bAlpha 0.69 at frame 60
            if self.alpha_blur > 0:
                self.alpha_blur = F32(self.alpha_blur + F32(t * K_DECAY_BLUR))
                if self.alpha_blur < 0: self.alpha_blur = F32(0.0)
            if self.alpha_capture > 0:
                self.alpha_capture = F32(self.alpha_capture + F32(t * K_DECAY_CAPTURE))
                if self.alpha_capture < 0: self.alpha_capture = F32(0.0)
        X = self._gx[None, :]; Y = self._gy[:, None]
        r = np.sqrt(Y * Y + X * X)                    # distance to the center
        d = CORNER_R - r                                # 0 at the corners, 1.4142 at the center
        s12 = ((d * d) * t) * K_PINCH                 # pinch toward the center
        angle = (t * self.rot_acc) + t * (d * self.rot_acc)
        zoom = F32(F32(t * K_ZOOM) + F32(1.0))        # 1 - t / 2
        xp = zoom * (X - X * s12); yp = zoom * (Y - Y * s12)
        xp = np.where(((X > 0) & (xp < 0)) | ((X < 0) & (xp > 0)), X * EPS, xp).astype(F32)      # a vertex that would change side of the center is brought back there (position x 1e-4)
        yp = np.where(((Y > 0) & (yp < 0)) | ((Y < 0) & (yp > 0)), Y * EPS, yp).astype(F32)
        a = np.asarray(angle, F32).astype(np.float64); s = np.sin(a).astype(F32); c = np.cos(a).astype(F32)      # bionic sincosf, to within 1 ulp
        self._vt[:, 0] = (c * xp - s * yp).reshape(-1)
        self._vt[:, 1] = (s * xp + c * yp).reshape(-1)
        self.clock = F32(t + self.time_step)

    # ------------------------------------------------------------------ drawing
    def drawings(self):
        if not self.render_active: return []
        if self.black_final: cf = cc = (0.0, 0.0, 0.0, 0.0)
        else: cf = (1.0, 1.0, 1.0, float(self.alpha_blur)); cc = (1.0, 1.0, 1.0, float(self.alpha_capture))
        return [('blur', self._background_pos, self._background_uv, np.tile(np.array(cf, F32), (6, 1))),
                ('capture', self._vt[self._triangles], self._uv, np.tile(np.array(cc, F32), (len(self._triangles), 1)))]
