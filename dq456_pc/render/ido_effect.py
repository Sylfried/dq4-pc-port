"""DQ VI well effect (Capture.IDO, packet 34 value & 0xff = 10; bit 15 = bOut: the arrival): the screen capture, cut into a grid of 32 columns (rows: 32 / aspect ratio of the screen, Capture.<Start>),
wobbles: each cell's corners read the capture at the screen position scaled from the bottom left corner by 1 + BiasA (top left and bottom right corners: z = 0.5) or 1 + BiasB (the other two),
the grid's diagonals alternating from one cell to the next; over it, the previous frame of the effect (a full-screen plane, Custom/CaptureBlur2) with an opacity up to 0.6: an afterimage.
Rules of Capture.<IDO>d__51.MoveNext (libil2cpp of DQ VI, RVA 0xCCACC4):
  * departure: call 1 builds the mesh, call 2 takes the capture, call 3 starts the display (afterimage opacity 0), then one frame per call with ca = 0 to 60: strength s = min(ca / 15, 1),
    afterimage opacity min(s, 0.6); at ca = 40 Fade.SetFadeOutBlack(20); call 64 ends (bit 1 of Global.Flag drops), the screen stays black;
  * arrival (bOut): call 1 Fade.SetFadeOutBlack(0), then the same with Fade.SetFadeIn(20) when the display starts (call 4, afterimage opacity 0.6), s = min(cb / 30, 1) with cb = 60 - ca, ending at call 65;
  * BiasA = sin(0.1 ca) / pi x 0.05 s, BiasB = cos(0.1 cb) / pi x 0.05 s (Material.SetFloat on Custom/Ido; its vertex shader computes the texture coordinates).
The fades are played by the engine (core/engine.py, Engine._screen_effect: IDO_FADES)."""
import math
import numpy as np
from dq456_pc.render import capture_effects as EC
from dq456_pc.render.capture_effects import F32

DIV_X = 32                       # Capture.m_divX
CMAX = 60                        # <cmax>: last value of ca
PI = F32(math.pi)
K_WAVE = F32(0.1)                # sinf(ca x 0.1), cosf(cb x 0.1)
K_BIAS = F32(0.05)
TRAIL_MAX = F32(0.6)
TRAIL_Z = F32(0.1)               # the afterimage plane (z has no effect: ZTest Always)


def div_y(aspect):
    """Capture.m_divY = (int)(32 / camera aspect ratio)."""
    return max(1, int(32.0 / max(float(aspect), 1e-6)))


def grid(div_x, div_y_):
    """Vertices (x, y, z) of the grid, four per cell, row by row from the top (0xCCB1D4): even cells (row + column) top left z 0.5, bottom left, top right, bottom right z 0.5; odd cells
    bottom left, top left z 0.5, bottom right z 0.5, top right. Triangles (b, b + 2, b + 1), (b + 2, b + 3, b + 1)."""
    sx, sy = F32(2.0) / F32(div_x), F32(2.0) / F32(div_y_)
    out = np.zeros((div_x * div_y_ * 4, 3), F32); k = 0
    top = F32(1.0)
    for r in range(div_y_):
        bottom = F32(top - sy); left = F32(-1.0)
        for c in range(div_x):
            right = F32(left + sx)
            if (r + c) & 1 == 0: out[k:k + 4] = ((left, top, 0.5), (left, bottom, 0.0), (right, top, 0.0), (right, bottom, 0.5))
            else: out[k:k + 4] = ((left, bottom, 0.0), (left, top, 0.5), (right, bottom, 0.5), (right, top, 0.0))
            k += 4; left = right
        top = bottom
    idx = (np.arange(div_x * div_y_)[:, None] * 4 + np.array([0, 2, 1, 2, 3, 1])[None, :]).ravel()
    return out, idx


def texture_coords(vt, bias_a, bias_b):
    """Custom/Ido's vertex shader: s = position x 0.5 + 0.5; uv = s + 2z s BiasA + (1 - 2z) s BiasB."""
    s = vt[:, :2] * F32(0.5) + F32(0.5); z2 = (vt[:, 2:3] * F32(2.0)).astype(F32)
    return (s + z2 * s * F32(bias_a) + (F32(1.0) - z2) * s * F32(bias_b)).astype(F32)


class IdoEffect(EC.CaptureEffect):
    moving_uv = True                 # (the window updates the texture coordinates at each frame)

    def __init__(self, arrival, aspect):
        super().__init__()
        self.arrival = bool(arrival)
        self.state = 0; self.ca = 0; self.cb = CMAX
        vt, idx = grid(DIV_X, div_y(aspect))
        self._vt = vt; self._idx = idx; self._pos = vt[idx][:, :2]
        self._uv = texture_coords(vt, 0.0, 0.0)[idx]
        self.trail_alpha = F32(0.0)
        self._trail_pos = EC.BACKGROUND_CORNERS[EC.BACKGROUND_TRIANGLES]; self._trail_uv = EC.BACKGROUND_UV[EC.BACKGROUND_TRIANGLES]

    def _move_next(self):
        e = self.state
        if e == 0:                                    # 0xCCADD8 (arrival: Fade.SetFadeOutBlack(0), played by the engine, then the mesh at the next call)
            self.state = 1 if self.arrival else 2
            return True
        if e == 1:                                    # 0xCCAE8C: mesh
            self.state = 2
            return True
        if e == 2:                                    # 0xCCAE98: the game camera renders the capture
            self._capture = True; self.state = 3
            return True
        if e == 3:                                    # 0xCCAF68: shaders, afterimage opacity, rendering enabled; first frame (ca = 0)
            self.render_active = True; self._blur = True
            self.trail_alpha = TRAIL_MAX if self.arrival else F32(0.0)
            self.ca, self.cb = 0, CMAX; self._frame(); self.state = 4
            return True
        if e == 4:                                    # 0xCCB0C0
            self.ca += 1; self.cb -= 1
            if self.ca > CMAX:                        # 0xCCB6A4: mesh cleared, rendering off
                self.render_active = False; self._blur = False; self.state = -1
                return False
            self._frame()
            return True
        return False

    def strength(self):
        """s of the current frame (0xCCB7F4)."""
        if self.arrival: return min(F32(self.cb) / F32(CMAX >> 1), F32(1.0))
        return min(F32(self.ca) / F32(CMAX >> 2), F32(1.0))

    def _frame(self):
        s = F32(self.strength())
        wa = F32(math.sin(F32(F32(self.ca) * K_WAVE))); wb = F32(math.cos(F32(F32(self.cb) * K_WAVE)))
        bias_a = F32(F32(F32(wa / PI) * K_BIAS) * s); bias_b = F32(F32(F32(wb / PI) * K_BIAS) * s)
        self._uv = texture_coords(self._vt, bias_a, bias_b)[self._idx]
        self.trail_alpha = F32(min(s, TRAIL_MAX))

    def drawings(self):
        """The grid (capture texture), then the afterimage (the effect's previous frame; before the first pass: the capture) at its opacity."""
        if not self.render_active: return []
        n = len(self._pos)
        return [('capture', self._pos, self._uv, np.ones((n, 4), F32)),
                ('trail', self._trail_pos, self._trail_uv, np.tile(np.array((1.0, 1.0, 1.0, float(self.trail_alpha)), F32), (6, 1)))]
