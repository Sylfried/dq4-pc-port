"""Lying poses of town characters (engine packets 16 / 17 / 18).

What the original game does (read from the disassembly, Unity IL2CPP + engine):
  - Packet 16 `cmd_chara_sleep_pose` D132FC, one integer v: character = v & 0xff; if v & 0x300: Chara.SetSleepPose(bit 8) (CCC234); if v & 0x400: Chara.SetSleepDir(v >> 12) (CCC5A0).
    Sent by `DisplayCharacter::setSleepFlag` (engine 0x17c918: 0x500 | angle << 12 to lie down, 0x200 to get up) and, when the direction changes during sleep,
    by `DisplayCharacter::draw` (0x400 | angle << 12). SetSleepDir(d): angle = (d & 0xffff) / -182.0444 + 180 degrees, Y rotation; quadrant = bits 14-15 of d.
  - Packet 17 `cmd_chara_sleep_near` D133E4, two integers (defNear, offset): Chara.SetSleepNear (CCD494): height of the lying body = 0.3104 if offset = 0, otherwise offset x 1.6 / 8192;
    it is written into the Y component of the 4 `s_lieOffset` offsets (static: it persists from one map to the next). Sent by `cmd_set_sleep_near` (engine 0x219e1c).
  - Packet 18 `cmd_chara_pose` D13474: v = slot | number << 8: Chara.SetTexture(number): the character changes sprite sheet (`TownCharacterDraw::changePose`).
  - Lying mesh `Chara.s_meshLie4 / 8`: the same rectangle as the panel (0.48 x 0.64) but FLAT (XZ plane, y = 0), turned around by half a turn (top of the sheet toward -Z), hence the + 180 degrees of SetSleepDir.
  - Shader `Custom/CharaSleep`: the screen position (x, y) comes from the character's transform, whose rotation is that of the inverted camera x the sleep rotation (s_lieBillboardRot,
    Chara.CalcLieBillboard): the lying plane is seen exactly FROM ABOVE, without foreshortening: the sprite appears on screen as its sheet turned by an angle, at full size. The z and w (depth,
    perspective division) come from the `_sleepMatrix` matrix = TRS(position + (0, 0.1, 0), sleep rotation, scale): the body is flat in the world for the z-buffer and the overlaps.
  - Position: P + s_lieOffset[quadrant]; s_lieOffset (Chara..cctor CCE364) = (0, h, 0.2), (-0.1, h, 0), (0, h, -0.2), (0.1, h, 0); h = height from SetSleepNear (0 as long as there is no packet 17).
  - The shadow is not drawn (Chara.lieBillboard pushes it 64 below the ground when it is not separate).

This module contains only geometry (numpy): testable without a window.
"""
import math
import numpy as np

HALF_L, HALF_H = 0.24, 0.32                                  # half of the lying mesh (0.48 x 0.64), before the character's scale
OFFSETS = ((0.0, 0.2), (-0.1, 0.0), (0.0, -0.2), (0.1, 0.0))   # s_lieOffset[quadrant]: (x, z); the y component is the height from SetSleepNear
HEIGHT_DEFAULT = 0.3104                                         # SetSleepNear: offset 0
MATRIX_HEIGHT = 0.1                                           # lieBillboard: the _sleepMatrix matrix is raised by 0.1
DEG_PER_UNIT = -182.04444885253906                          # SetSleepDir: 16-bit angle / -182.0444 + 180 (65536 / 360, sign reversed)


def packet_height(offset):
    """Height of the lying body (packet 17, second integer): Chara.SetSleepNear."""
    return HEIGHT_DEFAULT if offset == 0 else offset * (1.0 / 8192.0) * 1.6


def packet_direction(value):
    """(angle of the Y rotation in degrees, quadrant 0 to 3) of a packet 16 carrying bit 0x400: Chara.SetSleepDir(value >> 12)."""
    d = int(value) >> 12
    return (d & 0xffff) / DEG_PER_UNIT + 180.0, (d >> 14) & 3


def head_on_screen(angle_deg):
    """Direction of the lying character's head on screen (top view, zero-yaw camera) in degrees clockwise: 0 = up, 90 = right: used by the tests."""
    return (angle_deg + 180.0) % 360.0


def vertices(p, angle_deg, quadrant, topmost, scale_factor, border, cam):
    """The 4 WORLD vertices (bottom left, bottom right, top right, top left OF THE SHEET) of the panel of a lying character whose feet are at p.
    scale_factor: mesh size (width of the panel on screen / 0.48, with the character's SetScale scale); border = (right, up, forward) of the camera, cam = its position.
    The points are on the view rays: on screen the panel is the sheet turned by an angle, at full size (no foreshortening, no tilt), but its depth is that of the flat body
    (see the header); None if the body is behind the camera."""
    r_, u_, f_ = border; p = np.asarray(p, float); cam = np.asarray(cam, float)
    ox, oz = OFFSETS[quadrant & 3]
    c0 = p + np.array([ox, topmost, oz])                                   # center of the mesh (Transform.position)
    w0 = c0 + np.array([0.0, MATRIX_HEIGHT, 0.0])                       # center for depth (_sleepMatrix)
    z0 = float((w0 - cam) @ f_)
    if z0 <= 1e-3: return None
    th = math.radians(angle_deg); ct, st = math.cos(th), math.sin(th)
    rh = np.array([r_[0], 0.0, r_[2]]); rh /= (np.linalg.norm(rh) or 1.0)       # camera yaw only: top view oriented by the camera
    fh = np.array([f_[0], 0.0, f_[2]]); fh /= (np.linalg.norm(fh) or 1.0)
    cv = c0 - cam; xc, yc = float(cv @ r_), float(cv @ u_)
    out = []
    for cx, cy in ((-HALF_L, -HALF_H), (HALF_L, -HALF_H), (HALF_L, HALF_H), (-HALF_L, HALF_H)):       # corners of the sheet, centered: bottom left, bottom right, top right, top left
        mx, mz = -cx * scale_factor, -cy * scale_factor                           # vertex of the lying mesh: right of the sheet = -X, top = -Z
        dx, dz = mx * ct + mz * st, -mx * st + mz * ct                   # Y rotation (Quaternion.Euler(0, angle, 0))
        d = np.array([dx, 0.0, dz])
        zi = float((w0 + d - cam) @ f_)                                  # depth of the flat body
        xs, ys = xc + float(d @ rh), yc + float(d @ fh)                  # screen position (focal length 1 at depth z0): XZ plane seen from above, without foreshortening
        k = zi / z0
        out.append(cam + r_ * (xs * k) + u_ * (ys * k) + f_ * zi)
    return tuple(out)
