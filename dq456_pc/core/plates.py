"""Monster name plates of the battle screen (MenuPortItemTable.MonsterNamePlate, window type 31): their layout, without a window (testable without a screen)."""

PLATE_HALF_WIDTH, PLATE_X_LIMIT, PLATE_X_PUSHED = 83.0, 142.0, 24.0         # MonsterNamePlate: box half-extents (83, 0.5, 30) set by its constructor; x limit of a plate; x of the other plate when one is held at the limit


def separate_plates(order, xs, zs):
    """Make_MonsterName b__1 (the three games), after the rows: every ordered pair of plates (array order: sorted by x when there are more than two) on the same row whose boxes overlap
    (166 units wide: |xa - xb| <= 166) is set 166 apart around their middle, the left one staying left; when that would pass the limit (+-142), the outer one stays at the limit and the other goes
    to +-24 (166 from it). The names then sit side by side instead of over each other, even away from their group. `xs`, `zs`: plate -> x, z, changed in place."""
    w, lim, other = PLATE_HALF_WIDTH, PLATE_X_LIMIT, PLATE_X_PUSHED
    for a in order:
        for b in order:
            if a == b or zs[a] != zs[b] or xs[a] - w > xs[b] + w or xs[a] + w < xs[b] - w: continue
            mid = (xs[a] + xs[b]) * 0.5
            if xs[a] < xs[b]:
                if mid - w < -lim: xs[a], xs[b] = -lim, other
                elif mid + w > lim: xs[a], xs[b] = -other, lim
                else: xs[a], xs[b] = mid - w, mid + w
            else:
                if mid - w < -lim: xs[a], xs[b] = other, -lim
                elif mid + w > lim: xs[a], xs[b] = lim, -other
                else: xs[a], xs[b] = mid + w, mid - w
