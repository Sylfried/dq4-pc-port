"""DQ VI Pegasus effect (Capture.Pegasus, packet 34 value & 0xff = 9; bit 15 = bOut: the arrival): the scene, captured again at every frame (the game goes on underneath: the engine does not wait
for this effect, Global.Flag is not raised), seen through a lens: a grid of 32 columns (rows: Capture.m_divY = 32 / aspect ratio) whose vertices bulge (z = (cos x + cos y) / 2 - 0.3), and
Custom/Pegasus reads the capture at s - |p|^2 p.xy x Bias (s = screen position, p = vertex); over it, the effect's previous frame (Custom/CaptureBlur2) as an afterimage.
Rules of Capture.<Pegasus>d__50.MoveNext (libil2cpp of DQ VI, RVA 0xCCBAD4): call 1 builds the mesh and takes the first capture, call 2 starts the display with ca = 0, cb = cmax, then one frame
per call while ca <= cmax:
  * departure (cmax = 70): grid color and alpha k = min(cb / (3 cmax / 5), 1) (it darkens at the end), Bias = ca / cmax x 0.18, afterimage alpha min(ca / (cmax / 4), 0.9);
  * arrival (cmax = 40): grid k = min(ca / (cmax / 4), 1), Bias = cb / cmax x 0.3, afterimage color k and alpha min(cb / cmax, 0.9);
then the afterimage's alpha drops by 0.1 per call down to 0, and the last call ends with Fade.SetFadeOutBlack(0) (departure) or Fade.SetFadeIn(0) (arrival), played by the engine."""
import math
import numpy as np
from dq456_pc.render import capture_effects as EC
from dq456_pc.render.capture_effects import F32
from dq456_pc.render.ido_effect import DIV_X, div_y

CMAX = {False: 70, True: 40}
STEP_X = F32(0.0625)             # 2 / 32
Z_BIAS = F32(-0.3)
TRAIL_MAX = F32(0.9)
TRAIL_DROP = F32(-0.1)


def grid(div_x, div_y_):
    """Vertices (x, y, z) four per cell, rows from the top (0xCCC06C): top left, bottom left, top right, bottom right; z = (cos y + cos x) x 0.5 - 0.3. Triangles (b, b + 2, b + 1), (b + 2, b + 3, b + 1)."""
    sy = F32(2.0) / F32(div_y_)
    out = np.zeros((div_x * div_y_ * 4, 3), F32); k = 0
    top = F32(1.0)
    for r in range(div_y_):
        bottom = F32(top - sy); ct = F32(math.cos(top)); cb = F32(math.cos(bottom)); left = F32(-1.0)
        for c in range(div_x):
            right = F32(left + STEP_X); cl = F32(math.cos(left)); cr = F32(math.cos(right))
            z = lambda a, b: F32(F32(F32(a + b) * F32(0.5)) + Z_BIAS)
            out[k:k + 4] = ((left, top, z(ct, cl)), (left, bottom, z(cb, cl)), (right, top, z(ct, cr)), (right, bottom, z(cb, cr)))
            k += 4; left = right
        top = bottom
    idx = (np.arange(div_x * div_y_)[:, None] * 4 + np.array([0, 2, 1, 2, 3, 1])[None, :]).ravel()
    return out, idx


def texture_coords(vt, bias):
    """Custom/Pegasus's vertex shader: uv = p.xy x 0.5 + 0.5 - dot(p, p) p.xy x Bias."""
    p = vt.astype(F32); d = np.sum(p * p, axis=1, dtype=F32)[:, None]
    return (p[:, :2] * F32(0.5) + F32(0.5) - (d * p[:, :2]) * F32(bias)).astype(F32)


def call_count(arrival):
    """MoveNext calls up to the one that returns false: 2 + (cmax + 1) frames + the afterimage's fade (each call while its alpha > 0) + the last one."""
    sim = PegasusEffect(arrival, 16 / 9); n = 1
    while sim.stage(): n += 1
    return n


class PegasusEffect(EC.CaptureEffect):
    moving_uv = True                 # (the window updates the texture coordinates at each frame)
    live_capture = True              # (the window captures the scene again at each frame)

    def __init__(self, arrival, aspect):
        super().__init__()
        self.arrival = bool(arrival); self.cmax = CMAX[self.arrival]
        self.state = 0; self.ca = 0; self.cb = self.cmax
        vt, idx = grid(DIV_X, div_y(aspect))
        self._vt = vt; self._idx = idx; self._pos = vt[idx][:, :2]
        self._uv = texture_coords(vt, 0.0)[idx]
        self.grid_color = F32(1.0); self.trail_color = F32(1.0); self.trail_alpha = F32(0.0)
        self.final_fade = None           # 'black' (departure) or 'clear' (arrival) at the last call
        self._trail_pos = EC.BACKGROUND_CORNERS[EC.BACKGROUND_TRIANGLES]; self._trail_uv = EC.BACKGROUND_UV[EC.BACKGROUND_TRIANGLES]

    def _move_next(self):
        e = self.state
        if e == 0:                                    # 0xCCBBF0: mesh, first capture, shaders
            self._capture = True; self.state = 1
            return True
        if e == 1:                                    # 0xCCBC6C: rendering enabled, ca = 0
            self.render_active = True; self._blur = True
            self.ca, self.cb = 0, self.cmax; self._frame(); self.state = 2
            return True
        if e == 2:                                    # 0xCCBD1C
            self.ca += 1; self.cb -= 1
            if self.ca <= self.cmax:
                self._frame()
                return True
            self.state = e = 3
        if e == 3:                                    # 0xCCBDC8: the afterimage fades out, then the end
            if self.trail_alpha > 0:
                self.trail_alpha = F32(max(F32(self.trail_alpha + TRAIL_DROP), F32(0.0)))
                return True
            self.render_active = False; self._blur = False; self.state = -1
            self.final_fade = 'clear' if self.arrival else 'black'
            return False
        return False

    def _frame(self):
        ca, cb, cmax = F32(self.ca), F32(self.cb), F32(self.cmax)
        if self.arrival:                              # 0xCCBD48
            r = F32(cb / cmax)
            self.trail_alpha = F32(min(r, TRAIL_MAX)) if r >= 0 else F32(0.0)
            k = F32(min(F32(ca / F32(self.cmax >> 2)), F32(1.0)))
            bias = F32(r * F32(0.3)); self.trail_color = k
        else:                                         # 0xCCC594
            r = F32(cb / F32((self.cmax * 3) // 5))
            k = F32(min(r, F32(1.0))) if r >= 0 else F32(0.0)
            bias = F32(F32(ca / cmax) * F32(0.18)); self.trail_color = F32(1.0)
            self.trail_alpha = F32(min(F32(ca / F32(self.cmax >> 2)), TRAIL_MAX))
        self.grid_color = k
        self._uv = texture_coords(self._vt, bias)[self._idx]

    def drawings(self):
        if not self.render_active: return []
        n = len(self._pos); g = float(self.grid_color); t = float(self.trail_color)
        return [('capture', self._pos, self._uv, np.tile(np.array((g, g, g, g), F32), (n, 1))),
                ('trail', self._trail_pos, self._trail_uv, np.tile(np.array((t, t, t, float(self.trail_alpha)), F32), (6, 1)))]
