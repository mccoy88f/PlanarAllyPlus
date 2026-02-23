"""Building generator for PlanarAlly DungeonGen extension.

Generates floor-plan style buildings (house, shop, tavern, inn) as grid-based
occupancy maps, wall segments and doors, rendered to PNG via Skia.

The output format is deliberately identical to the dungeon generator so that
the existing client-side addDungeonToMap() pipeline works unchanged.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Constants (must match dungeongen.py)
# ---------------------------------------------------------------------------

GRID_SIZE = 50   # pixels per cell
PADDING = 50     # pixel padding around the building


# ---------------------------------------------------------------------------
# Enums
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


class CellKind(Enum):
    EMPTY = 0
    FLOOR = 1


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BuildingParams:
    archetype: BuildingArchetype = BuildingArchetype.TAVERN
    footprint: FootprintShape    = FootprintShape.RECTANGLE
    layout:    LayoutPlan        = LayoutPlan.OPEN_PLAN
    seed:      int               = 0


@dataclass
class FootprintBlock:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def contains(self, cx: int, cy: int) -> bool:
        return self.x <= cx < self.x2 and self.y <= cy < self.y2


@dataclass
class Room:
    id:   int
    x:    int
    y:    int
    w:    int
    h:    int
    kind: str  # "primary" | "secondary" | "bedroom" | "corridor"

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h


@dataclass
class Door:
    x:         int
    y:         int
    direction: str   # "north" | "south" | "east" | "west"
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

# primary_frac: target fraction of total footprint area for primary room
# base_size: (width, height) in grid cells, before random ±1 variation
ARCHETYPE_CFG: dict[BuildingArchetype, dict] = {
    BuildingArchetype.HOUSE: {
        "primary_frac": 0.35,
        "base_size":    (8, 7),
        "min_room":     2,
    },
    BuildingArchetype.SHOP: {
        "primary_frac": 0.45,
        "base_size":    (9, 7),
        "min_room":     2,
    },
    BuildingArchetype.TAVERN: {
        "primary_frac": 0.55,
        "base_size":    (12, 9),
        "min_room":     2,
    },
    BuildingArchetype.INN: {
        "primary_frac": 0.40,
        "base_size":    (14, 10),
        "min_room":     2,
    },
}

# Room kind labels per archetype (primary first, then additional rooms)
ARCHETYPE_ROOM_KINDS: dict[BuildingArchetype, list[str]] = {
    BuildingArchetype.HOUSE:  ["primary", "secondary", "secondary", "secondary"],
    BuildingArchetype.SHOP:   ["primary", "secondary", "secondary"],
    BuildingArchetype.TAVERN: ["primary", "secondary", "secondary", "secondary"],
    BuildingArchetype.INN:    ["primary", "secondary", "bedroom", "bedroom", "bedroom", "bedroom"],
}

# Colour fills per room kind  (R, G, B)
ROOM_COLORS: dict[str, tuple[int, int, int]] = {
    "primary":   (252, 248, 240),
    "secondary": (242, 236, 224),
    "bedroom":   (235, 228, 215),
    "corridor":  (210, 200, 185),
}


# ---------------------------------------------------------------------------
# Footprint generation
# ---------------------------------------------------------------------------

def build_footprint(
    shape:   FootprintShape,
    total_w: int,
    total_h: int,
    rng:     random.Random,
) -> tuple[list[FootprintBlock], int, int]:
    """Return (blocks, canvas_w, canvas_h)."""

    if shape == FootprintShape.RECTANGLE:
        return [FootprintBlock(0, 0, total_w, total_h)], total_w, total_h

    if shape == FootprintShape.L_SHAPE:
        # Arm 1: full width, upper portion
        split_h = rng.randint(max(2, int(total_h * 0.55)), max(3, int(total_h * 0.70)))
        split_h = min(split_h, total_h - 2)
        # Arm 2: partial width, lower portion
        split_w = rng.randint(max(2, int(total_w * 0.40)), max(3, int(total_w * 0.60)))
        split_w = min(split_w, total_w - 2)
        arm1 = FootprintBlock(0, 0, total_w, split_h)
        arm2 = FootprintBlock(0, split_h, split_w, total_h - split_h)
        return [arm1, arm2], total_w, total_h

    if shape == FootprintShape.CROSS:
        bar_h = max(2, rng.randint(int(total_h * 0.30), int(total_h * 0.45)))
        bar_w = max(2, rng.randint(int(total_w * 0.30), int(total_w * 0.45)))
        cy = (total_h - bar_h) // 2
        cx = (total_w - bar_w) // 2
        h_bar = FootprintBlock(0, cy, total_w, bar_h)
        v_bar = FootprintBlock(cx, 0, bar_w, total_h)
        return [h_bar, v_bar], total_w, total_h

    if shape == FootprintShape.OFFSET:
        half_w = total_w // 2
        right_w = total_w - half_w
        stagger = max(1, rng.randint(1, max(1, total_h // 4)))
        left  = FootprintBlock(0, 0, half_w, total_h - stagger)
        right = FootprintBlock(half_w, stagger, right_w, total_h - stagger)
        return [left, right], total_w, total_h

    # Fallback
    return [FootprintBlock(0, 0, total_w, total_h)], total_w, total_h


# ---------------------------------------------------------------------------
# Occupancy grid helpers
# ---------------------------------------------------------------------------

def make_grid(w: int, h: int) -> list[list[CellKind]]:
    return [[CellKind.EMPTY] * w for _ in range(h)]


def stamp_footprint(
    grid:   list[list[CellKind]],
    blocks: list[FootprintBlock],
) -> None:
    for b in blocks:
        for row in range(b.y, b.y + b.h):
            for col in range(b.x, b.x + b.w):
                grid[row][col] = CellKind.FLOOR


def cell_in_footprint(blocks: list[FootprintBlock], cx: int, cy: int) -> bool:
    return any(b.contains(cx, cy) for b in blocks)


# ---------------------------------------------------------------------------
# Room partitioning
# ---------------------------------------------------------------------------

def _slice_block(
    block:       FootprintBlock,
    min_size:    int,
    target_frac: float,
    axis:        str,   # "h" = horizontal cut, "v" = vertical cut
    rng:         random.Random,
) -> tuple[FootprintBlock, FootprintBlock] | None:
    """
    Split block along axis.  Returns (piece_a, piece_b) or None if impossible.
    target_frac is the desired fraction for piece_a.
    """
    if axis == "h":
        ideal = int(block.h * target_frac)
        lo = max(min_size, int(ideal * 0.80))
        hi = min(block.h - min_size, int(ideal * 1.20))
        if lo > hi:
            return None
        cut = rng.randint(lo, hi)
        a = FootprintBlock(block.x, block.y,         block.w, cut)
        b = FootprintBlock(block.x, block.y + cut,   block.w, block.h - cut)
    else:
        ideal = int(block.w * target_frac)
        lo = max(min_size, int(ideal * 0.80))
        hi = min(block.w - min_size, int(ideal * 1.20))
        if lo > hi:
            return None
        cut = rng.randint(lo, hi)
        a = FootprintBlock(block.x,       block.y, cut,            block.h)
        b = FootprintBlock(block.x + cut, block.y, block.w - cut,  block.h)
    return a, b


def _guillotine(
    block:      FootprintBlock,
    room_kinds: list[str],
    min_size:   int,
    rng:        random.Random,
    room_id_counter: list[int],
    axis:       str = "v",
) -> list[Room]:
    """
    Recursively partition block into len(room_kinds) rooms.
    Returns list of Room objects that cover block completely.
    """
    if len(room_kinds) == 1:
        rid = room_id_counter[0]
        room_id_counter[0] += 1
        return [Room(rid, block.x, block.y, block.w, block.h, room_kinds[0])]

    # Fraction for first piece = proportional to 1/n_rooms (rough approximation)
    n = len(room_kinds)
    frac = 1.0 / n

    result = _slice_block(block, min_size, frac, axis, rng)
    if result is None:
        # Cannot split; give everything to one room
        rid = room_id_counter[0]
        room_id_counter[0] += 1
        return [Room(rid, block.x, block.y, block.w, block.h, room_kinds[0])]

    a, b = result
    next_axis = "h" if axis == "v" else "v"
    rooms_a = _guillotine(a, room_kinds[:1],   min_size, rng, room_id_counter, next_axis)
    rooms_b = _guillotine(b, room_kinds[1:],   min_size, rng, room_id_counter, next_axis)
    return rooms_a + rooms_b


def partition_rooms(
    blocks:      list[FootprintBlock],
    archetype:   BuildingArchetype,
    layout:      LayoutPlan,
    cfg:         dict,
    rng:         random.Random,
) -> list[Room]:
    """Partition blocks into rooms; primary room is always rooms[0]."""

    min_size = cfg["min_room"]
    room_kinds = list(ARCHETYPE_ROOM_KINDS[archetype])

    # Find the largest block to host the primary room
    largest = max(blocks, key=lambda b: b.w * b.h)

    all_rooms: list[Room] = []
    counter = [0]

    # --- Primary room from largest block ---
    primary_frac = cfg["primary_frac"]

    # How many room_kinds to assign to the largest block?
    # Estimate: largest_area / total_area * n_kinds
    total_area = sum(b.w * b.h for b in blocks)
    largest_area = largest.w * largest.h
    n_largest = max(1, round(len(room_kinds) * largest_area / total_area))
    n_largest = min(n_largest, len(room_kinds))

    largest_kinds = room_kinds[:n_largest]
    remaining_kinds = room_kinds[n_largest:]

    # Ensure primary is first in largest_kinds
    if "primary" in largest_kinds:
        # Move it to index 0
        largest_kinds.remove("primary")
        largest_kinds = ["primary"] + largest_kinds

    # Place primary room in a sub-block of largest, preserving fill constraint
    # We give the primary a horizontal strip at the bottom of the largest block
    # (bottom = closer to exterior edge for entrance door)
    primary_h = max(min_size, int(largest.h * primary_frac))
    primary_h = min(primary_h, largest.h - (min_size * (n_largest - 1)))

    if n_largest == 1 or primary_h >= largest.h:
        # Give whole largest block to primary
        rooms_largest = _guillotine(largest, largest_kinds, min_size, rng, counter)
    else:
        # Bottom strip = primary, rest = other rooms
        primary_strip = FootprintBlock(largest.x, largest.y + largest.h - primary_h, largest.w, primary_h)
        rest_strip    = FootprintBlock(largest.x, largest.y, largest.w, largest.h - primary_h)

        primary_room_obj = Room(counter[0], primary_strip.x, primary_strip.y, primary_strip.w, primary_strip.h, "primary")
        counter[0] += 1

        if n_largest > 1 and rest_strip.h >= min_size:
            other_rooms = _guillotine(rest_strip, largest_kinds[1:], min_size, rng, counter)
        else:
            other_rooms = []

        rooms_largest = [primary_room_obj] + other_rooms

    # --- Remaining blocks ---
    other_block_rooms: list[Room] = []
    for b in blocks:
        if b is largest:
            continue
        b_area = b.w * b.h
        n_b = max(1, round(len(remaining_kinds) * b_area / sum(
            ob.w * ob.h for ob in blocks if ob is not largest
        ) if sum(ob.w * ob.h for ob in blocks if ob is not largest) > 0 else 1))
        n_b = min(n_b, len(remaining_kinds))
        b_kinds = remaining_kinds[:n_b]
        remaining_kinds = remaining_kinds[n_b:]
        if b_kinds:
            other_block_rooms += _guillotine(b, b_kinds, min_size, rng, counter)

    all_rooms = rooms_largest + other_block_rooms

    # --- Corridor variant ---
    if layout == LayoutPlan.CORRIDOR and len(all_rooms) > 1:
        all_rooms = _insert_corridor(all_rooms, blocks, min_size, rng, counter)

    return all_rooms


def _insert_corridor(
    rooms:    list[Room],
    blocks:   list[FootprintBlock],
    min_size: int,
    rng:      random.Random,
    counter:  list[int],
) -> list[Room]:
    """
    Carve a 1-cell corridor from the primary room's interior wall.
    The corridor runs along the longer axis of the building footprint.
    Secondary rooms are trimmed by 1 cell on the corridor side.
    """
    primary = rooms[0]

    # Bounding box of all floor cells
    all_x = [b.x for b in blocks] + [b.x2 for b in blocks]
    all_y = [b.y for b in blocks] + [b.y2 for b in blocks]
    bb_w = max(all_x) - min(all_x)
    bb_h = max(all_y) - min(all_y)

    # Corridor axis: longer footprint dimension
    corridor_horizontal = bb_w >= bb_h

    if corridor_horizontal:
        # Corridor is a 1-cell-tall horizontal strip
        # Place it just above the primary room (primary is at bottom)
        cy = primary.y - 1
        if cy < 0:
            cy = primary.y2  # place below instead
        corridor_x  = min(b.x for b in blocks)
        corridor_w  = max(b.x2 for b in blocks) - corridor_x
        if corridor_w < 2:
            return rooms  # not enough space, skip corridor
        corridor = Room(
            counter[0],
            corridor_x, cy,
            corridor_w, 1,
            "corridor",
        )
        counter[0] += 1

        # Shrink any room that overlaps the corridor row
        trimmed: list[Room] = []
        for r in rooms:
            if r is primary:
                trimmed.append(r)
                continue
            if r.y <= cy < r.y2 and r.h > min_size:
                if cy == r.y:
                    trimmed.append(Room(r.id, r.x, r.y + 1, r.w, r.h - 1, r.kind))
                elif cy == r.y2 - 1:
                    trimmed.append(Room(r.id, r.x, r.y, r.w, r.h - 1, r.kind))
                else:
                    trimmed.append(r)
            else:
                trimmed.append(r)
        return trimmed + [corridor]

    else:
        # Corridor is a 1-cell-wide vertical strip
        cx = primary.x2  # to the right of primary
        if cx >= max(b.x2 for b in blocks):
            cx = primary.x - 1  # to the left instead
        if cx < 0:
            return rooms
        corridor_y = min(b.y for b in blocks)
        corridor_h = max(b.y2 for b in blocks) - corridor_y
        if corridor_h < 2:
            return rooms
        corridor = Room(
            counter[0],
            cx, corridor_y,
            1, corridor_h,
            "corridor",
        )
        counter[0] += 1

        trimmed: list[Room] = []
        for r in rooms:
            if r is primary:
                trimmed.append(r)
                continue
            if r.x <= cx < r.x2 and r.w > min_size:
                if cx == r.x:
                    trimmed.append(Room(r.id, r.x + 1, r.y, r.w - 1, r.h, r.kind))
                elif cx == r.x2 - 1:
                    trimmed.append(Room(r.id, r.x, r.y, r.w - 1, r.h, r.kind))
                else:
                    trimmed.append(r)
            else:
                trimmed.append(r)
        return trimmed + [corridor]


# ---------------------------------------------------------------------------
# Door placement
# ---------------------------------------------------------------------------

def _rooms_share_wall(a: Room, b: Room) -> tuple[int, int, str] | None:
    """
    If rooms a and b share a wall, return (door_x, door_y, direction).
    door_x/y is the cell on the b side. direction is from a into b.
    Returns None if they don't share a wall.
    """
    # a is to the left of b
    if a.x2 == b.x and max(a.y, b.y) < min(a.y2, b.y2):
        mid_y = (max(a.y, b.y) + min(a.y2, b.y2)) // 2
        return (b.x, mid_y, "east")

    # a is to the right of b
    if b.x2 == a.x and max(a.y, b.y) < min(a.y2, b.y2):
        mid_y = (max(a.y, b.y) + min(a.y2, b.y2)) // 2
        return (a.x, mid_y, "west")

    # a is above b
    if a.y2 == b.y and max(a.x, b.x) < min(a.x2, b.x2):
        mid_x = (max(a.x, b.x) + min(a.x2, b.x2)) // 2
        return (mid_x, b.y, "south")

    # a is below b
    if b.y2 == a.y and max(a.x, b.x) < min(a.x2, b.x2):
        mid_x = (max(a.x, b.x) + min(a.x2, b.x2)) // 2
        return (mid_x, a.y, "north")

    return None


def place_doors(
    rooms:   list[Room],
    blocks:  list[FootprintBlock],
    layout:  LayoutPlan,
    rng:     random.Random,
) -> list[Door]:
    doors: list[Door] = []
    primary = rooms[0]

    # 1. Exterior entrance on the primary room
    entrance = _find_exterior_entrance(primary, blocks)
    if entrance:
        doors.append(entrance)

    # 2. Interior connections
    if layout == LayoutPlan.OPEN_PLAN:
        # Connect each non-primary room directly to the primary
        for room in rooms[1:]:
            if room.kind == "corridor":
                continue
            wall = _rooms_share_wall(primary, room)
            if wall:
                doors.append(Door(wall[0], wall[1], wall[2]))

    elif layout == LayoutPlan.CORRIDOR:
        # Find corridor
        corridor = next((r for r in rooms if r.kind == "corridor"), None)
        if corridor:
            # Connect primary ↔ corridor
            wall = _rooms_share_wall(primary, corridor)
            if wall:
                doors.append(Door(wall[0], wall[1], wall[2]))
            # Connect corridor ↔ each other room
            for room in rooms:
                if room is primary or room.kind == "corridor":
                    continue
                wall = _rooms_share_wall(corridor, room)
                if wall:
                    doors.append(Door(wall[0], wall[1], wall[2]))
        else:
            # Fallback to open_plan
            for room in rooms[1:]:
                wall = _rooms_share_wall(primary, room)
                if wall:
                    doors.append(Door(wall[0], wall[1], wall[2]))

    return doors


def _find_exterior_entrance(primary: Room, blocks: list[FootprintBlock]) -> Optional[Door]:
    """Find the best wall of the primary room that faces outside the footprint."""
    # Check south edge (bottom): cells at (x, primary.y2) should be EMPTY
    mid_x = (primary.x + primary.x2) // 2
    south_y = primary.y2

    if not any(b.contains(mid_x, south_y) for b in blocks):
        return Door(mid_x, south_y - 1, "south")

    # Check north edge
    north_y = primary.y - 1
    if not any(b.contains(mid_x, north_y) for b in blocks):
        return Door(mid_x, primary.y, "north")

    # Check west edge
    mid_y = (primary.y + primary.y2) // 2
    west_x = primary.x - 1
    if not any(b.contains(west_x, mid_y) for b in blocks):
        return Door(primary.x, mid_y, "west")

    # Check east edge
    east_x = primary.x2
    if not any(b.contains(east_x, mid_y) for b in blocks):
        return Door(primary.x2 - 1, mid_y, "east")

    return None


# ---------------------------------------------------------------------------
# Wall extraction
# ---------------------------------------------------------------------------

def extract_walls(
    grid:     list[list[CellKind]],
    canvas_w: int,
    canvas_h: int,
) -> list[list[list[int]]]:
    """
    Extract exterior wall segments (FLOOR→EMPTY boundaries).
    Returns list of [[x1,y1],[x2,y2]] line segments in grid coordinates.
    """
    wall_lines: list[list[list[int]]] = []

    for y in range(canvas_h):
        for x in range(canvas_w):
            if grid[y][x] != CellKind.FLOOR:
                continue

            # North
            if y == 0 or grid[y - 1][x] == CellKind.EMPTY:
                wall_lines.append([[x, y], [x + 1, y]])
            # South
            if y == canvas_h - 1 or grid[y + 1][x] == CellKind.EMPTY:
                wall_lines.append([[x, y + 1], [x + 1, y + 1]])
            # West
            if x == 0 or grid[y][x - 1] == CellKind.EMPTY:
                wall_lines.append([[x, y], [x, y + 1]])
            # East
            if x == canvas_w - 1 or grid[y][x + 1] == CellKind.EMPTY:
                wall_lines.append([[x + 1, y], [x + 1, y + 1]])

    return wall_lines


# ---------------------------------------------------------------------------
# Skia rendering
# ---------------------------------------------------------------------------

def render_building(
    grid:     list[list[CellKind]],
    rooms:    list[Room],
    doors:    list[Door],
    canvas_w: int,
    canvas_h: int,
    grid_size: int = GRID_SIZE,
    padding:   int = PADDING,
) -> bytes:
    """Render the building to PNG bytes using Skia."""
    import skia

    img_w = canvas_w * grid_size + padding * 2
    img_h = canvas_h * grid_size + padding * 2

    surface = skia.Surface(img_w, img_h)
    canvas  = surface.getCanvas()

    # Parchment background
    canvas.clear(skia.Color(200, 190, 175))

    def px(cell_coord: int) -> float:
        return cell_coord * grid_size + padding

    # --- Room fills ---
    for room in rooms:
        r, g, b = ROOM_COLORS.get(room.kind, (245, 240, 230))
        fill_paint = skia.Paint(
            Style=skia.Paint.kFill_Style,
            Color=skia.Color(r, g, b),
        )
        canvas.drawRect(
            skia.Rect(px(room.x), px(room.y), px(room.x2), px(room.y2)),
            fill_paint,
        )

    # --- Interior room dividers (thin lines between adjacent rooms) ---
    divider_paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        Color=skia.Color(160, 140, 110),
        StrokeWidth=1.5,
        AntiAlias=True,
    )
    checked: set[tuple[int, int]] = set()
    for i, ra in enumerate(rooms):
        for j, rb in enumerate(rooms):
            if j <= i:
                continue
            key = (min(i, j), max(i, j))
            if key in checked:
                continue
            checked.add(key)

            # Shared vertical edge (ra right side == rb left side)
            if ra.x2 == rb.x and max(ra.y, rb.y) < min(ra.y2, rb.y2):
                shared_y1 = max(ra.y, rb.y)
                shared_y2 = min(ra.y2, rb.y2)
                x_px = px(ra.x2)
                canvas.drawLine(x_px, px(shared_y1), x_px, px(shared_y2), divider_paint)

            # Shared vertical edge (rb right side == ra left side)
            elif rb.x2 == ra.x and max(ra.y, rb.y) < min(ra.y2, rb.y2):
                shared_y1 = max(ra.y, rb.y)
                shared_y2 = min(ra.y2, rb.y2)
                x_px = px(rb.x2)
                canvas.drawLine(x_px, px(shared_y1), x_px, px(shared_y2), divider_paint)

            # Shared horizontal edge (ra bottom == rb top)
            elif ra.y2 == rb.y and max(ra.x, rb.x) < min(ra.x2, rb.x2):
                shared_x1 = max(ra.x, rb.x)
                shared_x2 = min(ra.x2, rb.x2)
                y_px = px(ra.y2)
                canvas.drawLine(px(shared_x1), y_px, px(shared_x2), y_px, divider_paint)

            # Shared horizontal edge (rb bottom == ra top)
            elif rb.y2 == ra.y and max(ra.x, rb.x) < min(ra.x2, rb.x2):
                shared_x1 = max(ra.x, rb.x)
                shared_x2 = min(ra.x2, rb.x2)
                y_px = px(rb.y2)
                canvas.drawLine(px(shared_x1), y_px, px(shared_x2), y_px, divider_paint)

    # --- Exterior walls (thick) ---
    wall_paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        Color=skia.Color(70, 50, 30),
        StrokeWidth=3.5,
        StrokeCap=skia.Paint.kSquare_Cap,
        AntiAlias=True,
    )
    for y in range(canvas_h):
        for x in range(canvas_w):
            if grid[y][x] != CellKind.FLOOR:
                continue
            if y == 0 or grid[y - 1][x] == CellKind.EMPTY:
                canvas.drawLine(px(x), px(y), px(x + 1), px(y), wall_paint)
            if y == canvas_h - 1 or grid[y + 1][x] == CellKind.EMPTY:
                canvas.drawLine(px(x), px(y + 1), px(x + 1), px(y + 1), wall_paint)
            if x == 0 or grid[y][x - 1] == CellKind.EMPTY:
                canvas.drawLine(px(x), px(y), px(x), px(y + 1), wall_paint)
            if x == canvas_w - 1 or grid[y][x + 1] == CellKind.EMPTY:
                canvas.drawLine(px(x + 1), px(y), px(x + 1), px(y + 1), wall_paint)

    # --- Door gaps (erase wall segment, draw door marker) ---
    gap_paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        Color=skia.Color(240, 235, 225),  # match floor colour approx
        StrokeWidth=5.0,
        StrokeCap=skia.Paint.kSquare_Cap,
    )
    door_paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        Color=skia.Color(110, 70, 30),
        StrokeWidth=2.5,
        StrokeCap=skia.Paint.kRound_Cap,
        AntiAlias=True,
    )
    half = grid_size * 0.4

    for door in doors:
        cx = px(door.x) + grid_size * 0.5
        cy = px(door.y) + grid_size * 0.5

        if door.direction in ("north", "south"):
            # Horizontal gap
            y_line = px(door.y) if door.direction == "north" else px(door.y + 1)
            canvas.drawLine(cx - half, y_line, cx + half, y_line, gap_paint)
            canvas.drawLine(cx - half, y_line, cx + half, y_line, door_paint)
        else:
            # Vertical gap
            x_line = px(door.x) if door.direction == "west" else px(door.x + 1)
            canvas.drawLine(x_line, cy - half, x_line, cy + half, gap_paint)
            canvas.drawLine(x_line, cy - half, x_line, cy + half, door_paint)

    # --- Sync square (1 cell = GRID_SIZE px) for PlanarAlly auto-resize ---
    sync_paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        Color=skia.Color(180, 180, 180),
        StrokeWidth=2,
    )
    canvas.drawRect(skia.Rect(1, 1, grid_size - 1, grid_size - 1), sync_paint)

    image    = surface.makeImageSnapshot()
    png_data = image.encodeToData()
    if png_data is None:
        raise RuntimeError("Failed to encode building PNG")
    return bytes(png_data)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_building(params: BuildingParams) -> tuple[BuildingResult, bytes]:
    """
    Generate a building and return (BuildingResult, png_bytes).
    """
    rng = random.Random(params.seed)
    cfg = ARCHETYPE_CFG[params.archetype]

    base_w, base_h = cfg["base_size"]
    total_w = base_w + rng.randint(-1, 1)
    total_h = base_h + rng.randint(-1, 1)
    total_w = max(4, total_w)
    total_h = max(4, total_h)

    # Build footprint
    blocks, canvas_w, canvas_h = build_footprint(params.footprint, total_w, total_h, rng)

    # Occupancy grid
    grid = make_grid(canvas_w, canvas_h)
    stamp_footprint(grid, blocks)

    # Room partition
    rooms = partition_rooms(blocks, params.archetype, params.layout, cfg, rng)

    # Door placement
    doors = place_doors(rooms, blocks, params.layout, rng)

    # Wall extraction
    wall_lines = extract_walls(grid, canvas_w, canvas_h)

    # Render
    png_bytes = render_building(grid, rooms, doors, canvas_w, canvas_h, GRID_SIZE, PADDING)

    result = BuildingResult(
        grid=grid,
        width=canvas_w,
        height=canvas_h,
        rooms=rooms,
        doors=doors,
        seed=params.seed,
    )

    return result, png_bytes, wall_lines
