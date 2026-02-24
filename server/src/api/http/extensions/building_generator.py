"""Building generator for PlanarAlly DungeonGen extension.

Generates floor-plan style buildings (house, shop, tavern, inn) as grid-based
room layouts. Rendering is delegated entirely to the dungeongen library's
Map.render() pipeline so the visual output is identical in style to dungeons.

== Room / wall model ==

Each room is passed to dungeongen as Room.from_grid(x, y, w, h).  Dungeongen
draws the room filling that rectangle and renders rock/crosshatching in any
canvas area NOT covered by a room.

Two adjacent rooms share a 1-cell wall gap between them:
  Room A ends at x2 = N  (slot x + slot_w)
  Gap cell: x = N  (1 cell wide, belongs to neither room)
  Room B starts at x = N+1

The door is placed at (N, mid_y) — inside the gap cell (the rock/wall cell).
DoorOrientation: VERTICAL for doors on a vertical wall (east/west sides),
                 HORIZONTAL for doors on a horizontal wall (north/south sides).

Minimum room size (interior + its own walls handled by dungeongen): MIN_ROOM = 3
  (dungeongen needs at least 3 cells to draw a room with visible interior)

Canvas layout for a simple 2-room horizontal split at cut=C (W total):
  Room A: x=0, w=C          (cells 0..C-1)
  gap:    x=C               (1 cell)
  Room B: x=C+1, w=W-C-1   (cells C+1..W-1)
  Door:   x=C, y=mid  (VERTICAL orientation — on the vertical wall)

For n rooms, each cut consumes 1 extra cell for the gap. So for n rooms:
  usable_width = W - (n-1) gaps

== Footprint ==
The footprint is one or more rectangular blocks covering the canvas.
Blocks share boundaries (no gaps between them) so the building outline is
solid. Inside each block, rooms are placed with the gap model above.
Between two blocks the shared boundary row/column is also a 1-cell gap where
a door can be placed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRID_SIZE = 50   # PlanarAlly pixels per cell
PADDING   = 50   # pixel padding around canvas

# Minimum cells for a dungeongen room (each axis)
MIN_ROOM = 3

# 1-cell gap between any two adjacent rooms (the shared wall)
GAP = 1


# ---------------------------------------------------------------------------
# Public enums
# ---------------------------------------------------------------------------

class BuildingArchetype(Enum):
    HOUSE  = "house"
    SHOP   = "shop"
    TAVERN = "tavern"
    INN    = "inn"


class FootprintShape(Enum):
    RECTANGLE = "rectangle"
    L_SHAPE   = "l_shape"
    CROSS     = "cross"
    OFFSET    = "offset"


class LayoutPlan(Enum):
    OPEN_PLAN = "open_plan"
    CORRIDOR  = "corridor"


# ---------------------------------------------------------------------------
# Internal grid kind (for wall extraction)
# ---------------------------------------------------------------------------

class CellKind(Enum):
    EMPTY = 0
    FLOOR = 1


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class BuildingSize(Enum):
    SMALL  = "small"
    MEDIUM = "medium"
    LARGE  = "large"
    XLARGE = "xlarge"


@dataclass
class BuildingParams:
    archetype: BuildingArchetype = BuildingArchetype.TAVERN
    footprint: FootprintShape    = FootprintShape.RECTANGLE
    layout:    LayoutPlan        = LayoutPlan.OPEN_PLAN
    size:      BuildingSize      = BuildingSize.MEDIUM
    seed:      int               = 0


@dataclass
class Room:
    """A room in dungeongen grid coordinates.

    These coordinates are passed directly to DGRoom.from_grid(x, y, w, h).
    Adjacent rooms are separated by a 1-cell gap (the shared wall).
    """
    id:   int
    x:    int
    y:    int
    w:    int
    h:    int
    kind: str   # "primary" | "secondary" | "bedroom" | "corridor"

    @property
    def x2(self) -> int: return self.x + self.w
    @property
    def y2(self) -> int: return self.y + self.h


@dataclass
class Door:
    x:         int
    y:         int
    direction: str    # "north"|"south"|"east"|"west"
    door_type: str = "normal"


@dataclass
class BuildingResult:
    grid:   list[list[CellKind]]
    width:  int
    height: int
    rooms:  list[Room]
    doors:  list[Door]
    seed:   int


# ---------------------------------------------------------------------------
# Archetype configuration
# ---------------------------------------------------------------------------

# Canvas base sizes per archetype (used as reference for medium size).
# The actual canvas is scaled by _SIZE_SCALE and adjusted to fit n_rooms.
ARCHETYPE_CFG: dict[BuildingArchetype, dict] = {
    BuildingArchetype.HOUSE:  {"canvas": (14, 11)},
    BuildingArchetype.SHOP:   {"canvas": (15, 11)},
    BuildingArchetype.TAVERN: {"canvas": (18, 13)},
    BuildingArchetype.INN:    {"canvas": (20, 15)},
}

# Room kind pools per archetype.
# _build_kinds() draws from this pool in order, repeating the last entry
# when n_rooms exceeds the pool length.  The first entry is always "primary".
ARCHETYPE_KINDS: dict[BuildingArchetype, list[str]] = {
    BuildingArchetype.HOUSE:  ["primary", "secondary", "secondary", "secondary"],
    BuildingArchetype.SHOP:   ["primary", "secondary", "secondary", "storage"],
    BuildingArchetype.TAVERN: ["primary", "secondary", "secondary", "secondary", "kitchen"],
    BuildingArchetype.INN:    ["primary", "secondary", "bedroom", "bedroom", "bedroom", "bedroom"],
}

# Number of rooms (min, max) per BuildingSize, chosen randomly with the seed.
# XLARGE capped at 15 to stay within dungeongen pixel limits (±3200px / 50px/cell ≈ 64 cells max).
_SIZE_ROOMS: dict[BuildingSize, tuple[int, int]] = {
    BuildingSize.SMALL:  (1, 3),
    BuildingSize.MEDIUM: (3, 5),
    BuildingSize.LARGE:  (5, 10),
    BuildingSize.XLARGE: (10, 15),
}

# Maximum canvas cells per axis to stay within dungeongen's ±3200px coordinate limit.
# With GRID_SIZE=50 and PADDING=50: max_cells = (3200 - 50) / 50 = 63
_MAX_CANVAS_CELLS = 62

# Canvas scale factor per BuildingSize (applied to base canvas dimensions).
_SIZE_SCALE: dict[BuildingSize, float] = {
    BuildingSize.SMALL:  0.70,
    BuildingSize.MEDIUM: 1.00,
    BuildingSize.LARGE:  1.35,
    BuildingSize.XLARGE: 1.70,
}


def _build_kinds(archetype: BuildingArchetype, n_rooms: int) -> list[str]:
    """Return a list of n_rooms kind strings for the given archetype.

    Always starts with "primary".  Subsequent kinds are drawn from the
    archetype's kind pool in order; the last pool entry is repeated when
    n_rooms exceeds the pool length.
    """
    pool = ARCHETYPE_KINDS[archetype]
    kinds: list[str] = []
    for i in range(n_rooms):
        idx = min(i, len(pool) - 1)
        kinds.append(pool[idx])
    return kinds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _min_block_size(n: int) -> int:
    """Minimum cells needed in one axis to fit n rooms with gaps between them."""
    return n * MIN_ROOM + (n - 1) * GAP


# ---------------------------------------------------------------------------
# Footprint blocks  (x, y, w, h) in canvas grid coordinates
#
# Blocks are non-overlapping and share exact boundary rows/columns so that
# rooms in adjacent blocks can be connected through a 1-cell gap.
# ---------------------------------------------------------------------------

def make_blocks(
    shape: FootprintShape,
    W: int, H: int,
    rng: random.Random,
) -> list[tuple[int, int, int, int]]:
    """Return list of non-overlapping (x,y,w,h) blocks covering the footprint."""

    if shape == FootprintShape.RECTANGLE:
        return [(0, 0, W, H)]

    if shape == FootprintShape.L_SHAPE:
        # top block: full width, upper portion
        # bottom-left block: left portion of lower part
        # They share the boundary row at y=split_h (so a room in the top block
        # that ends at y2=split_h is 1 gap away from a room in the bottom block
        # that starts at y=split_h+1).
        min_top = _min_block_size(1)
        # bot block is shrunk by GAP on its north side → needs MIN_ROOM + GAP
        min_bot = MIN_ROOM + GAP
        split_h = _clamp(
            rng.randint(int(H * 55 // 100), int(H * 70 // 100)),
            min_top, H - min_bot,
        )
        min_lw = _min_block_size(1)
        split_w = _clamp(
            rng.randint(int(W * 40 // 100), int(W * 60 // 100)),
            min_lw, W - min_lw,
        )
        return [
            (0, 0,        W,       split_h),
            (0, split_h,  split_w, H - split_h),
        ]

    if shape == FootprintShape.CROSS:
        # Three non-overlapping blocks:
        #   top_arm:  (cx, 0,         bar_w, cy)
        #   h_bar:    (0,  cy,        W,     bar_h)
        #   bot_arm:  (cx, cy+bar_h,  bar_w, H - cy - bar_h)
        #
        # _shrink_block will shrink h_bar by GAP on its north side (top_arm above it)
        # and shrink bot_arm by GAP on its north side (h_bar above it).
        # So min_bar_h and min_arm_h must each be MIN_ROOM + GAP to ensure
        # the partitioning area is still >= MIN_ROOM after shrinking.
        min_bar_h = MIN_ROOM + GAP
        min_arm_h = MIN_ROOM + GAP
        bar_h = _clamp(
            rng.randint(int(H * 30 // 100), int(H * 45 // 100)),
            min_bar_h, H - 2 * min_arm_h,
        )
        cy = _clamp((H - bar_h) // 2, min_arm_h, H - bar_h - min_arm_h)

        min_arm_w = _min_block_size(1)
        bar_w = _clamp(
            rng.randint(int(W * 30 // 100), int(W * 50 // 100)),
            min_arm_w, W - 2 * min_arm_w,
        )
        cx = (W - bar_w) // 2
        cx = _clamp(cx, 0, W - bar_w)

        blocks: list[tuple[int, int, int, int]] = [(0, cy, W, bar_h)]
        if cy >= min_arm_h:
            blocks.append((cx, 0, bar_w, cy))
        if H - cy - bar_h >= min_arm_h:
            blocks.append((cx, cy + bar_h, bar_w, H - cy - bar_h))
        return blocks

    if shape == FootprintShape.OFFSET:
        # Two blocks sharing a vertical boundary, vertically staggered.
        # The right block is shrunk by GAP on its west side → needs MIN_ROOM + GAP wide.
        min_w = MIN_ROOM + GAP
        half_w = _clamp(W // 2, min_w, W - min_w)
        right_w = W - half_w
        min_h = _min_block_size(1)
        stagger = _clamp(
            rng.randint(int(H // 6), int(H // 3)),
            1, H - min_h * 2,
        )
        left_h  = max(H - stagger, min_h)
        right_h = max(H - stagger, min_h)
        return [
            (0,      0,       half_w,  left_h),
            (half_w, stagger, right_w, right_h),
        ]

    return [(0, 0, W, H)]


def cell_in_blocks(cx: int, cy: int, blocks: list[tuple[int, int, int, int]]) -> bool:
    for bx, by, bw, bh in blocks:
        if bx <= cx < bx + bw and by <= cy < by + bh:
            return True
    return False


# ---------------------------------------------------------------------------
# Guillotine partitioning
#
# Split a block (bx, by, bw, bh) into n rooms with GAP-cell gaps between them.
# Each room gets at least MIN_ROOM cells on each axis.
#
# Cut at position C (relative to block start):
#   Room A: offset=0,       size=C
#   gap:    offset=C        (GAP cells)
#   Room B: offset=C+GAP,   size=remaining
#
# So: C >= MIN_ROOM, remaining = bw - C - GAP >= MIN_ROOM
#   => C in [MIN_ROOM, bw - GAP - MIN_ROOM]
# ---------------------------------------------------------------------------

def _guillotine(
    bx: int, by: int, bw: int, bh: int,
    n: int,
    rng: random.Random,
) -> list[tuple[int, int, int, int]]:
    """Partition block into n rooms. Returns list of (x,y,w,h) room rects."""
    if n <= 1:
        return [(bx, by, bw, bh)]

    # Can we split horizontally (along y)?
    can_h = bh >= _min_block_size(2)   # need room for 2 rooms + 1 gap
    # Can we split vertically (along x)?
    can_v = bw >= _min_block_size(2)

    if not can_h and not can_v:
        return [(bx, by, bw, bh)]

    # Prefer splitting along the longer axis
    use_h = (bh >= bw) if (can_h and can_v) else can_h

    n1 = max(1, n // 2)
    n2 = n - n1

    if use_h:
        # split horizontally: cut at y offset C
        # block A: (bx, by, bw, C), block B: (bx, by+C+GAP, bw, bh-C-GAP)
        min_c = _min_block_size(n1)
        max_c = bh - GAP - _min_block_size(n2)
        if min_c > max_c:
            return [(bx, by, bw, bh)]
        ideal = round(bh * n1 / n)
        ideal = _clamp(ideal, min_c, max_c)
        lo = _clamp(ideal - max(1, bh // 6), min_c, max_c)
        hi = _clamp(ideal + max(1, bh // 6), min_c, max_c)
        cut = rng.randint(lo, hi)
        part_a = _guillotine(bx, by,             bw, cut,             n1, rng)
        part_b = _guillotine(bx, by + cut + GAP, bw, bh - cut - GAP, n2, rng)
        return part_a + part_b
    else:
        # split vertically: cut at x offset C
        min_c = _min_block_size(n1)
        max_c = bw - GAP - _min_block_size(n2)
        if min_c > max_c:
            return [(bx, by, bw, bh)]
        ideal = round(bw * n1 / n)
        ideal = _clamp(ideal, min_c, max_c)
        lo = _clamp(ideal - max(1, bw // 6), min_c, max_c)
        hi = _clamp(ideal + max(1, bw // 6), min_c, max_c)
        cut = rng.randint(lo, hi)
        part_a = _guillotine(bx,             by, cut,             bh, n1, rng)
        part_b = _guillotine(bx + cut + GAP, by, bw - cut - GAP, bh, n2, rng)
        return part_a + part_b


# ---------------------------------------------------------------------------
# Room partitioning
# ---------------------------------------------------------------------------

def partition_rooms(
    blocks:    list[tuple[int, int, int, int]],
    W: int, H: int,
    kinds:     list[str],
    layout:    LayoutPlan,
    rng:       random.Random,
) -> list[Room]:
    n_rooms   = len(kinds)
    total_area = sum(bw * bh for _, _, bw, bh in blocks)

    # Distribute rooms across blocks proportionally to area.
    # For each block, shrink the partitioning area by GAP on any side that
    # shares a boundary with another block.  This reserves a 1-cell gap at
    # inter-block boundaries so rooms in different blocks are always separated
    # by exactly GAP cells (same as rooms within a single block).
    def _shrink_block(bx, by, bw, bh, all_blocks):
        """Return partitioning rect shrunk on sides shared with another block.

        Convention: only the block with the LARGER coordinate shrinks on the
        shared boundary side (the "incoming" side).  The block with the smaller
        coordinate keeps its natural extent up to the boundary.

        This ensures exactly GAP=1 cells between the last room of block A and
        the first room of block B:
          Block A rooms extend up to boundary coord C  (a.y2 == C)
          Block B rooms start at C+1                  (b.y  == C+1)
          Gap cell: y=C  →  a.y2 + GAP == b.y  ✓
        """
        ox, oy, ow, oh = bx, by, bw, bh
        for obx, oby, obw, obh in all_blocks:
            if (obx, oby, obw, obh) == (bx, by, bw, bh):
                continue
            # Other block is to the east: this block is left → keep east extent
            # Other block is to the west: this block is right → shrink west side
            if obx + obw == bx and max(by, oby) < min(by + bh, oby + obh):
                ox += GAP; ow -= GAP
            # Other block is to the south: this block is top → keep south extent
            # Other block is to the north: this block is bottom → shrink north side
            if oby + obh == by and max(bx, obx) < min(bx + bw, obx + obw):
                oy += GAP; oh -= GAP
        return ox, oy, ow, oh

    all_raw: list[tuple[int, int, int, int]] = []
    remaining = n_rooms
    for i, (bx, by, bw, bh) in enumerate(blocks):
        if i == len(blocks) - 1:
            n = remaining
        else:
            frac = (bw * bh) / total_area
            n = max(1, min(round(n_rooms * frac), remaining - (len(blocks) - i - 1)))
        remaining -= n
        px, py, pw, ph = _shrink_block(bx, by, bw, bh, blocks)
        all_raw.extend(_guillotine(px, py, pw, ph, n, rng))

    # Choose primary: largest room with at least one exterior (non-block) side
    def has_exterior_side(rx, ry, rw, rh) -> bool:
        mid_x = rx + rw // 2
        mid_y = ry + rh // 2
        return (
            not cell_in_blocks(mid_x, ry + rh, blocks) or   # south
            not cell_in_blocks(mid_x, ry - 1, blocks) or    # north
            not cell_in_blocks(rx - 1, mid_y, blocks) or    # west
            not cell_in_blocks(rx + rw, mid_y, blocks)      # east
        )

    exterior = [s for s in all_raw if has_exterior_side(*s)]
    pool = exterior if exterior else all_raw
    primary_raw = max(pool, key=lambda s: s[2] * s[3])

    # Insert corridor slot if requested
    if layout == LayoutPlan.CORRIDOR:
        all_raw = _insert_corridor(all_raw, W, H, primary_raw, rng)
        exterior2 = [s for s in all_raw if has_exterior_side(*s)]
        pool2 = exterior2 if exterior2 else all_raw
        primary_raw = max(pool2, key=lambda s: s[2] * s[3])

    # Find corridor slot (thinnest slot)
    corridor_raw: Optional[tuple[int, int, int, int]] = None
    if layout == LayoutPlan.CORRIDOR:
        for s in all_raw:
            if s is not primary_raw and (s[2] == MIN_ROOM or s[3] == MIN_ROOM):
                corridor_raw = s
                break

    # Assign kinds: primary first, corridor second, rest by area descending
    others = [s for s in all_raw if s is not primary_raw and s is not corridor_raw]
    others_sorted = sorted(others, key=lambda s: s[2] * s[3], reverse=True)

    ordered: list[tuple[tuple[int, int, int, int], str]] = [(primary_raw, "primary")]
    if corridor_raw is not None:
        ordered.append((corridor_raw, "corridor"))
    kind_idx = 1
    for s in others_sorted:
        k = kinds[kind_idx] if kind_idx < len(kinds) else "secondary"
        ordered.append((s, k))
        kind_idx += 1

    rooms: list[Room] = []
    for rid, (raw, kind) in enumerate(ordered):
        rx, ry, rw, rh = raw
        rooms.append(Room(rid, rx, ry, rw, rh, kind))

    return rooms


# ---------------------------------------------------------------------------
# Corridor insertion
# ---------------------------------------------------------------------------

def _trim_rooms_horizontal(
    rooms_raw: list[tuple[int, int, int, int]],
    primary_raw: tuple[int, int, int, int],
    corr_y: int,
) -> list[tuple[int, int, int, int]]:
    """Return rooms_raw with any room overlapping the horizontal corridor zone trimmed."""
    excl_top = corr_y - GAP
    excl_bot = corr_y + MIN_ROOM + GAP
    result: list[tuple[int, int, int, int]] = []
    for sx, sy, sw, sh in rooms_raw:
        if (sx, sy, sw, sh) == primary_raw:
            result.append((sx, sy, sw, sh))
            continue
        if sy + sh <= excl_top or sy >= excl_bot:
            result.append((sx, sy, sw, sh))
            continue
        if sy < excl_top and excl_top - sy >= MIN_ROOM:
            result.append((sx, sy, sw, excl_top - sy))
        if sy + sh > excl_bot and (sy + sh) - excl_bot >= MIN_ROOM:
            result.append((sx, excl_bot, sw, (sy + sh) - excl_bot))
    return result


def _trim_rooms_vertical(
    rooms_raw: list[tuple[int, int, int, int]],
    primary_raw: tuple[int, int, int, int],
    corr_x: int,
) -> list[tuple[int, int, int, int]]:
    """Return rooms_raw with any room overlapping the vertical corridor zone trimmed."""
    excl_left  = corr_x - GAP
    excl_right = corr_x + MIN_ROOM + GAP
    result: list[tuple[int, int, int, int]] = []
    for sx, sy, sw, sh in rooms_raw:
        if (sx, sy, sw, sh) == primary_raw:
            result.append((sx, sy, sw, sh))
            continue
        if sx + sw <= excl_left or sx >= excl_right:
            result.append((sx, sy, sw, sh))
            continue
        if sx < excl_left and excl_left - sx >= MIN_ROOM:
            result.append((sx, sy, excl_left - sx, sh))
        if sx + sw > excl_right and (sx + sw) - excl_right >= MIN_ROOM:
            result.append((excl_right, sy, (sx + sw) - excl_right, sh))
    return result


def _insert_corridor(
    rooms_raw: list[tuple[int, int, int, int]],
    W: int, H: int,
    primary_raw: tuple[int, int, int, int],
    rng: random.Random,
) -> list[tuple[int, int, int, int]]:
    """Insert a corridor (MIN_ROOM thick) adjacent to the primary room.

    Tries all 4 sides of the primary room in random order and places the
    corridor on the first side that fits on the canvas perimeter.
    Horizontal corridors (north/south) span the full canvas width.
    Vertical corridors (east/west) span the full canvas height.
    """
    px, py, pw, ph = primary_raw

    # Candidate placements: (side, corr_rect)
    candidates: list[tuple[str, tuple[int, int, int, int]]] = []

    corr_y_north = py - GAP - MIN_ROOM
    if corr_y_north >= 0:
        candidates.append(("north", (0, corr_y_north, W, MIN_ROOM)))

    corr_y_south = py + ph + GAP
    if corr_y_south + MIN_ROOM <= H:
        candidates.append(("south", (0, corr_y_south, W, MIN_ROOM)))

    corr_x_west = px - GAP - MIN_ROOM
    if corr_x_west >= 0:
        candidates.append(("west", (corr_x_west, 0, MIN_ROOM, H)))

    corr_x_east = px + pw + GAP
    if corr_x_east + MIN_ROOM <= W:
        candidates.append(("east", (corr_x_east, 0, MIN_ROOM, H)))

    if not candidates:
        return rooms_raw

    rng.shuffle(candidates)
    side, corr = candidates[0]

    if side in ("north", "south"):
        corr_y = corr[1]
        result = _trim_rooms_horizontal(rooms_raw, primary_raw, corr_y)
        result.append(corr)
        return result
    else:
        corr_x = corr[0]
        result = _trim_rooms_vertical(rooms_raw, primary_raw, corr_x)
        result.append(corr)
        return result


# ---------------------------------------------------------------------------
# Adjacency: two rooms are adjacent when separated by exactly GAP=1 cell
#
# Room A ends at x2=N, Room B starts at x=N+GAP → gap column at x=N
# Door is placed IN the gap cell: (N, mid_y) with VERTICAL orientation.
# For a horizontal gap: (mid_x, N) with HORIZONTAL orientation.
#
# DoorOrientation.VERTICAL   → door on a vertical wall (east/west sides)
# DoorOrientation.HORIZONTAL → door on a horizontal wall (north/south sides)
# ---------------------------------------------------------------------------

def _gap_between(a: Room, b: Room) -> Optional[tuple[int, int, str]]:
    """Return (door_x, door_y, direction) if rooms share a 1-cell wall gap.

    Door coordinates are placed IN the gap cell (rock/wall cell between rooms).
    This is what dungeongen expects: Door.from_grid(gap_x, gap_y, orientation).
    """

    # A left of B: gap column at a.x2 → door at (a.x2, mid_y) VERTICAL
    if a.x2 + GAP == b.x:
        oy1 = max(a.y, b.y)
        oy2 = min(a.y2, b.y2)
        if oy2 - oy1 >= MIN_ROOM:
            return (a.x2, (oy1 + oy2) // 2, "east")

    # B left of A: gap column at b.x2 → door at (b.x2, mid_y) VERTICAL
    if b.x2 + GAP == a.x:
        oy1 = max(a.y, b.y)
        oy2 = min(a.y2, b.y2)
        if oy2 - oy1 >= MIN_ROOM:
            return (b.x2, (oy1 + oy2) // 2, "west")

    # A above B: gap row at a.y2 → door at (mid_x, a.y2) HORIZONTAL
    if a.y2 + GAP == b.y:
        ox1 = max(a.x, b.x)
        ox2 = min(a.x2, b.x2)
        if ox2 - ox1 >= MIN_ROOM:
            return ((ox1 + ox2) // 2, a.y2, "south")

    # B above A: gap row at b.y2 → door at (mid_x, b.y2) HORIZONTAL
    if b.y2 + GAP == a.y:
        ox1 = max(a.x, b.x)
        ox2 = min(a.x2, b.x2)
        if ox2 - ox1 >= MIN_ROOM:
            return ((ox1 + ox2) // 2, b.y2, "north")

    return None


# ---------------------------------------------------------------------------
# Exterior entrance
# ---------------------------------------------------------------------------

def _find_entrance(
    primary:    Room,
    blocks:     list[tuple[int, int, int, int]],
    W: int, H: int,
    rng:        random.Random,
    avoid_room: Optional[Room] = None,
) -> Optional[Door]:
    """Find a free exterior side of the primary room for the entrance.

    A side is "free" if the gap cell is outside the footprint/canvas.
    If avoid_room is given (e.g. the corridor), prefer sides that do not
    face it; those sides are tried first (in random order controlled by rng).
    The position within the chosen side is centred on the room's midpoint.
    """
    r = primary

    def _side_faces_room(side: str, other: Room) -> bool:
        """True if 'side' of primary faces 'other' room across the gap."""
        if side == "south" and other.y == r.y2 + GAP:
            return max(r.x, other.x) < min(r.x2, other.x2)
        if side == "north" and other.y2 + GAP == r.y:
            return max(r.x, other.x) < min(r.x2, other.x2)
        if side == "west" and other.x2 + GAP == r.x:
            return max(r.y, other.y) < min(r.y2, other.y2)
        if side == "east" and other.x == r.x2 + GAP:
            return max(r.y, other.y) < min(r.y2, other.y2)
        return False

    def gap_is_free_exterior(cx: int, cy: int) -> bool:
        """True if (cx,cy) is a valid gap cell outside the building footprint.

        The cell must be within canvas bounds (so it renders correctly) or
        just one step off the canvas edge (still valid as exterior).
        We allow exactly one cell outside the canvas on each side.
        """
        # Must not be inside the footprint
        if 0 <= cx < W and 0 <= cy < H and cell_in_blocks(cx, cy, blocks):
            return False
        # Must be reachable: within canvas or exactly one cell off edge
        if cx < -1 or cy < -1 or cx > W or cy > H:
            return False
        return True

    # Keep the old name as alias for clarity below
    free_outside = gap_is_free_exterior

    mid_x = r.x + r.w // 2
    mid_y = r.y + r.h // 2

    def _sorted_by_center(lo: int, hi: int, center: int) -> list[int]:
        """Return range [lo, hi) sorted by distance from center (closest first)."""
        return sorted(range(lo, hi), key=lambda v: abs(v - center))

    sides = ["south", "north", "west", "east"]

    # Shuffle preferred sides randomly (seed-controlled), then append the
    # non-preferred sides (also shuffled) as fallback.
    preferred = [s for s in sides if avoid_room is None or not _side_faces_room(s, avoid_room)]
    fallback  = [s for s in sides if s not in preferred]
    rng.shuffle(preferred)
    rng.shuffle(fallback)
    order = preferred + fallback

    for side in order:
        if side == "south":
            for x in _sorted_by_center(r.x, r.x2, mid_x):
                if free_outside(x, r.y2):
                    return Door(x, r.y2, "south")
        elif side == "north":
            for x in _sorted_by_center(r.x, r.x2, mid_x):
                if free_outside(x, r.y - 1):
                    return Door(x, r.y - 1, "north")
        elif side == "west":
            for y in _sorted_by_center(r.y, r.y2, mid_y):
                if free_outside(r.x - 1, y):
                    return Door(r.x - 1, y, "west")
        elif side == "east":
            for y in _sorted_by_center(r.y, r.y2, mid_y):
                if free_outside(r.x2, y):
                    return Door(r.x2, y, "east")

    return None


# ---------------------------------------------------------------------------
# Door placement
# ---------------------------------------------------------------------------

def place_doors(
    rooms:  list[Room],
    blocks: list[tuple[int, int, int, int]],
    layout: LayoutPlan,
    W: int, H: int,
    rng:    random.Random,
) -> list[Door]:
    doors:   list[Door] = []
    primary: Room       = rooms[0]

    # In CORRIDOR mode, find the corridor first so entrance avoids its side
    corridor_room = next((r for r in rooms if r.kind == "corridor"), None) if layout == LayoutPlan.CORRIDOR else None
    entrance = _find_entrance(primary, blocks, W, H, rng, avoid_room=corridor_room)
    if entrance:
        doors.append(entrance)

    def add_door(a: Room, b: Room) -> bool:
        g = _gap_between(a, b)
        if g is None:
            return False
        d = Door(g[0], g[1], g[2])
        for ex in doors:
            if ex.x == d.x and ex.y == d.y:
                return True
        doors.append(d)
        return True

    def _bfs_connect(
        accessible: set[int],
        pending: list[Room],
    ) -> list[Room]:
        """BFS: try to connect all pending rooms to accessible set.

        Returns the list of rooms still not connected after all passes.
        """
        for _ in range(len(pending) + 1):
            still = []
            for room in pending:
                connected = False
                for aid in sorted(accessible):
                    if add_door(rooms[aid], room):
                        accessible.add(room.id)
                        connected = True
                        break
                if not connected:
                    still.append(room)
            pending = still
            if not pending:
                break
        return pending

    if layout == LayoutPlan.OPEN_PLAN:
        accessible = {primary.id}
        pending = [r for r in rooms[1:] if r.kind != "corridor"]
        _bfs_connect(accessible, pending)

    else:  # CORRIDOR — BFS through corridor first, then fallback to any accessible room
        corridor = next((r for r in rooms if r.kind == "corridor"), None)
        if corridor:
            # Connect primary ↔ corridor
            add_door(primary, corridor)
            accessible = {primary.id, corridor.id}
            pending = [r for r in rooms if r is not primary and r.kind != "corridor"]
            _bfs_connect(accessible, pending)
        else:
            accessible = {primary.id}
            pending = list(rooms[1:])
            _bfs_connect(accessible, pending)

    return doors


def _all_rooms_connected(rooms: list[Room], doors: list[Door]) -> bool:
    """Return True if all rooms are reachable from the primary room via valid doors.

    Uses the same gap model as _gap_between(): a door at (dx, dy) with direction
    east/west connects the room whose x2==dx to the room whose x==dx+GAP, and
    similarly for south/north.  Rooms connected through any chain of valid doors
    are considered reachable.  The exterior entrance (first door, if any) is
    excluded because it connects the primary room to the outside, not to another
    room.
    """
    if len(rooms) <= 1:
        return True

    # Build adjacency from internal doors only (skip the exterior entrance at index 0)
    interior_doors = doors[1:] if doors else []
    adj: dict[int, set[int]] = {r.id: set() for r in rooms}
    room_by_id = {r.id: r for r in rooms}

    for door in interior_doors:
        dx, dy = door.x, door.y
        a_id: Optional[int] = None
        b_id: Optional[int] = None
        for r in rooms:
            if door.direction in ("east", "west"):
                if r.x2 == dx and r.y <= dy < r.y2:
                    a_id = r.id
                elif r.x == dx + GAP and r.y <= dy < r.y2:
                    b_id = r.id
            else:  # south / north
                if r.y2 == dy and r.x <= dx < r.x2:
                    a_id = r.id
                elif r.y == dy + GAP and r.x <= dx < r.x2:
                    b_id = r.id
        if a_id is not None and b_id is not None:
            adj[a_id].add(b_id)
            adj[b_id].add(a_id)

    # BFS from primary (rooms[0])
    visited: set[int] = {rooms[0].id}
    queue = [rooms[0].id]
    while queue:
        cur = queue.pop()
        for nid in adj[cur]:
            if nid not in visited:
                visited.add(nid)
                queue.append(nid)

    return len(visited) == len(rooms)


# ---------------------------------------------------------------------------
# Occupancy grid & wall extraction
# ---------------------------------------------------------------------------

def make_grid(W: int, H: int) -> list[list[CellKind]]:
    return [[CellKind.EMPTY] * W for _ in range(H)]


def stamp_rooms(grid: list[list[CellKind]], rooms: list[Room]) -> None:
    H, W = len(grid), len(grid[0])
    for r in rooms:
        for row in range(r.y, r.y2):
            for col in range(r.x, r.x2):
                if 0 <= row < H and 0 <= col < W:
                    grid[row][col] = CellKind.FLOOR


def extract_walls(grid: list[list[CellKind]], W: int, H: int) -> list[list[list[int]]]:
    lines: list[list[list[int]]] = []
    for y in range(H):
        for x in range(W):
            if grid[y][x] != CellKind.FLOOR:
                continue
            if y == 0   or grid[y-1][x] == CellKind.EMPTY: lines.append([[x,y],[x+1,y]])
            if y == H-1 or grid[y+1][x] == CellKind.EMPTY: lines.append([[x,y+1],[x+1,y+1]])
            if x == 0   or grid[y][x-1] == CellKind.EMPTY: lines.append([[x,y],[x,y+1]])
            if x == W-1 or grid[y][x+1] == CellKind.EMPTY: lines.append([[x+1,y],[x+1,y+1]])
    return lines


# ---------------------------------------------------------------------------
# Rendering via dungeongen Map pipeline
# ---------------------------------------------------------------------------

def _dir_to_dg(direction: str):
    from dungeongen.map.enums import RoomDirection
    return {
        "north": RoomDirection.NORTH,
        "south": RoomDirection.SOUTH,
        "east":  RoomDirection.EAST,
        "west":  RoomDirection.WEST,
    }[direction]


def _rooms_for_door(door: Door, rooms: list[Room]) -> tuple[Optional[Room], Optional[Room]]:
    """Find the two rooms on either side of an internal door.

    Door coords are IN the gap cell between rooms:
      east/west door at (dx, dy):
        room A has r.x2 == dx  (A ends just before the gap)
        room B has r.x  == dx + GAP  (B starts just after the gap)
      south/north door at (dx, dy):
        room A has r.y2 == dy  (A ends just before the gap)
        room B has r.y  == dy + GAP  (B starts just after the gap)
    """
    dx, dy = door.x, door.y
    a: Optional[Room] = None
    b: Optional[Room] = None

    for r in rooms:
        if door.direction in ("east", "west"):
            # room A: its right edge is at dx (gap col)
            if r.x2 == dx and r.y <= dy < r.y2:
                a = r
            # room B: its left edge is at dx+GAP
            elif r.x == dx + GAP and r.y <= dy < r.y2:
                b = r
        else:  # south / north
            # room A: its bottom edge is at dy (gap row)
            if r.y2 == dy and r.x <= dx < r.x2:
                a = r
            # room B: its top edge is at dy+GAP
            elif r.y == dy + GAP and r.x <= dx < r.x2:
                b = r
    return a, b


def _is_exterior(door: Door, entrance: Optional[Door]) -> bool:
    """True if this door is the exterior entrance."""
    return entrance is not None and door.x == entrance.x and door.y == entrance.y


def render_building_with_dungeongen(
    rooms:    list[Room],
    doors:    list[Door],
    W: int, H: int,
) -> bytes:
    from dungeongen.map.map import Map
    from dungeongen.map.room import Room as DGRoom, RoomType
    from dungeongen.map.door import Door as DGDoor, DoorOrientation, DoorType
    from dungeongen.map.exit import Exit
    from dungeongen.options import Options
    import skia

    dungeon_map = Map(Options())
    dg_rooms: dict[int, DGRoom] = {}

    for room in rooms:
        dg_room = DGRoom.from_grid(room.x, room.y, room.w, room.h,
                                   RoomType.RECTANGULAR, room.id + 1)
        dungeon_map.add_element(dg_room)
        dg_rooms[room.id] = dg_room

    primary = rooms[0]
    # First door is always the exterior entrance (if any)
    entrance = doors[0] if doors else None

    for door in doors:
        if _is_exterior(door, entrance):
            try:
                exit_elem = Exit.from_grid(door.x, door.y, _dir_to_dg(door.direction))
                dungeon_map.add_element(exit_elem)
                dg_rooms[primary.id].connect_to(exit_elem)
            except (ValueError, KeyError):
                pass
        else:
            # HORIZONTAL = door on a vertical wall (east/west sides)
            # VERTICAL = door on a horizontal wall (north/south sides)
            orient = (DoorOrientation.HORIZONTAL if door.direction in ("east", "west")
                      else DoorOrientation.VERTICAL)
            try:
                dg_door = DGDoor.from_grid(door.x, door.y, orient, DoorType.CLOSED)
                dungeon_map.add_element(dg_door)
                ra, rb = _rooms_for_door(door, rooms)
                if ra is not None and rb is not None:
                    dg_rooms[ra.id].connect_to(dg_door)
                    dg_door.connect_to(dg_rooms[rb.id])
            except (ValueError, KeyError):
                pass

    scale = GRID_SIZE / 64   # dungeongen CELL_SIZE = 64
    px_w  = W * GRID_SIZE + PADDING * 2
    px_h  = H * GRID_SIZE + PADDING * 2

    surface = skia.Surface(int(px_w), int(px_h))
    cv      = surface.getCanvas()
    cv.clear(skia.Color(255, 255, 255))

    tf = skia.Matrix()
    tf.setScale(scale, scale)
    tf.postTranslate(PADDING, PADDING)
    dungeon_map.render(cv, tf)

    sync = skia.Paint(Style=skia.Paint.kStroke_Style,
                      Color=skia.Color(180, 180, 180), StrokeWidth=2)
    cv.drawRect(skia.Rect(1, 1, GRID_SIZE - 1, GRID_SIZE - 1), sync)

    data = surface.makeImageSnapshot().encodeToData()
    if data is None:
        raise RuntimeError("PNG encode failed")
    return bytes(data)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _try_generate(params: BuildingParams, attempt_seed: int) -> Optional[tuple[
    list[Room], list[Door], list[tuple[int, int, int, int]], int, int
]]:
    """Try to generate a fully-connected building layout for the given seed.

    Returns (rooms, doors, blocks, W, H) if all rooms are reachable from primary,
    or None if connectivity check fails (caller should retry with a different seed).
    """
    rng = random.Random(attempt_seed)
    cfg = ARCHETYPE_CFG[params.archetype]

    n_rooms = rng.randint(*_SIZE_ROOMS[params.size])
    kinds   = _build_kinds(params.archetype, n_rooms)

    scale    = _SIZE_SCALE[params.size]
    base_w, base_h = cfg["canvas"]
    scaled_w = max(8, round(base_w * scale))
    scaled_h = max(7, round(base_h * scale))

    n_blocks_est = {
        FootprintShape.RECTANGLE: 1,
        FootprintShape.L_SHAPE:   2,
        FootprintShape.OFFSET:    2,
        FootprintShape.CROSS:     3,
    }[params.footprint]
    rooms_per_block = max(1, (n_rooms + n_blocks_est - 1) // n_blocks_est)
    min_long  = _min_block_size(rooms_per_block) + 4
    min_short = MIN_ROOM + 4
    if base_w >= base_h:
        min_w, min_h = min_long, min_short
    else:
        min_w, min_h = min_short, min_long

    W = min(_MAX_CANVAS_CELLS, max(min_w, scaled_w + rng.randint(-1, 2)))
    H = min(_MAX_CANVAS_CELLS, max(min_h, scaled_h + rng.randint(-1, 2)))

    blocks = make_blocks(params.footprint, W, H, rng)
    rooms  = partition_rooms(blocks, W, H, kinds, params.layout, rng)
    doors  = place_doors(rooms, blocks, params.layout, W, H, rng)

    if not _all_rooms_connected(rooms, doors):
        return None

    return rooms, doors, blocks, W, H


def generate_building(params: BuildingParams) -> tuple[BuildingResult, bytes, list]:
    # Try up to MAX_ATTEMPTS seeds; each attempt uses seed + attempt index so the
    # original seed still produces a deterministic result (attempt 0 always runs
    # first and uses the exact seed the user requested).
    MAX_ATTEMPTS = 20
    result_data = None
    for attempt in range(MAX_ATTEMPTS):
        attempt_seed = params.seed + attempt
        result_data = _try_generate(params, attempt_seed)
        if result_data is not None:
            break

    if result_data is None:
        # Extremely unlikely; fall back to the original seed without connectivity guarantee
        rng = random.Random(params.seed)
        cfg = ARCHETYPE_CFG[params.archetype]
        n_rooms = rng.randint(*_SIZE_ROOMS[params.size])
        kinds   = _build_kinds(params.archetype, n_rooms)
        scale   = _SIZE_SCALE[params.size]
        base_w, base_h = cfg["canvas"]
        scaled_w = max(8, round(base_w * scale))
        scaled_h = max(7, round(base_h * scale))
        W = min(_MAX_CANVAS_CELLS, max(MIN_ROOM + 4, scaled_w))
        H = min(_MAX_CANVAS_CELLS, max(MIN_ROOM + 4, scaled_h))
        blocks = make_blocks(params.footprint, W, H, rng)
        rooms  = partition_rooms(blocks, W, H, kinds, params.layout, rng)
        doors  = place_doors(rooms, blocks, params.layout, W, H, rng)
    else:
        rooms, doors, blocks, W, H = result_data

    grid = make_grid(W, H)
    stamp_rooms(grid, rooms)
    walls = extract_walls(grid, W, H)

    png = render_building_with_dungeongen(rooms, doors, W, H)

    return BuildingResult(
        grid=grid, width=W, height=H,
        rooms=rooms, doors=doors, seed=params.seed,
    ), png, walls
