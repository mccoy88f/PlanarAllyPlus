"""Building generator for PlanarAlly DungeonGen extension.

Generates floor-plan style buildings (house, shop, tavern, inn) as grid-based
room layouts. Rendering is delegated entirely to the dungeongen library's
Map.render() pipeline so the visual output is identical in style to dungeons.

Wall extraction and door data for PlanarAlly use the same grid-based approach
as the dungeon generator.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Constants (must match dungeongen.py)
# ---------------------------------------------------------------------------

GRID_SIZE = 50   # PlanarAlly pixels per cell
PADDING   = 50   # pixel padding (matches dungeongen.py)


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
# Internal grid kind (for wall extraction only)
# ---------------------------------------------------------------------------

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
    """Internal room representation (grid coordinates)."""
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
    """Door in grid coordinates for PlanarAlly wall/door pipeline."""
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

ARCHETYPE_ROOM_KINDS: dict[BuildingArchetype, list[str]] = {
    BuildingArchetype.HOUSE:  ["primary", "secondary", "secondary", "secondary"],
    BuildingArchetype.SHOP:   ["primary", "secondary", "secondary"],
    BuildingArchetype.TAVERN: ["primary", "secondary", "secondary", "secondary"],
    BuildingArchetype.INN:    ["primary", "secondary", "bedroom", "bedroom", "bedroom", "bedroom"],
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
        split_h = rng.randint(max(2, int(total_h * 0.55)), max(3, int(total_h * 0.70)))
        split_h = min(split_h, total_h - 2)
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

    return [FootprintBlock(0, 0, total_w, total_h)], total_w, total_h


# ---------------------------------------------------------------------------
# Occupancy grid helpers (used for wall extraction only)
# ---------------------------------------------------------------------------

def make_grid(w: int, h: int) -> list[list[CellKind]]:
    return [[CellKind.EMPTY] * w for _ in range(h)]


def stamp_footprint(grid: list[list[CellKind]], blocks: list[FootprintBlock]) -> None:
    for b in blocks:
        for row in range(b.y, b.y + b.h):
            for col in range(b.x, b.x + b.w):
                grid[row][col] = CellKind.FLOOR


# ---------------------------------------------------------------------------
# Room partitioning (guillotine, axis-alternating)
# ---------------------------------------------------------------------------

def _slice_block(
    block:       FootprintBlock,
    min_size:    int,
    target_frac: float,
    axis:        str,
    rng:         random.Random,
) -> Optional[tuple[FootprintBlock, FootprintBlock]]:
    if axis == "h":
        ideal = int(block.h * target_frac)
        lo = max(min_size, int(ideal * 0.80))
        hi = min(block.h - min_size, int(ideal * 1.20))
        if lo > hi:
            return None
        cut = rng.randint(lo, hi)
        return (
            FootprintBlock(block.x, block.y,       block.w, cut),
            FootprintBlock(block.x, block.y + cut, block.w, block.h - cut),
        )
    else:
        ideal = int(block.w * target_frac)
        lo = max(min_size, int(ideal * 0.80))
        hi = min(block.w - min_size, int(ideal * 1.20))
        if lo > hi:
            return None
        cut = rng.randint(lo, hi)
        return (
            FootprintBlock(block.x,       block.y, cut,           block.h),
            FootprintBlock(block.x + cut, block.y, block.w - cut, block.h),
        )


def _guillotine(
    block:           FootprintBlock,
    room_kinds:      list[str],
    min_size:        int,
    rng:             random.Random,
    room_id_counter: list[int],
    axis:            str = "v",
) -> list[Room]:
    if len(room_kinds) == 1:
        rid = room_id_counter[0]
        room_id_counter[0] += 1
        return [Room(rid, block.x, block.y, block.w, block.h, room_kinds[0])]

    frac = 1.0 / len(room_kinds)
    result = _slice_block(block, min_size, frac, axis, rng)
    if result is None:
        rid = room_id_counter[0]
        room_id_counter[0] += 1
        return [Room(rid, block.x, block.y, block.w, block.h, room_kinds[0])]

    a, b = result
    next_axis = "h" if axis == "v" else "v"
    return (
        _guillotine(a, room_kinds[:1],  min_size, rng, room_id_counter, next_axis)
        + _guillotine(b, room_kinds[1:], min_size, rng, room_id_counter, next_axis)
    )


def _insert_corridor(
    rooms:    list[Room],
    blocks:   list[FootprintBlock],
    min_size: int,
    rng:      random.Random,
    counter:  list[int],
) -> list[Room]:
    primary = rooms[0]
    all_x = [b.x for b in blocks] + [b.x2 for b in blocks]
    all_y = [b.y for b in blocks] + [b.y2 for b in blocks]
    bb_w = max(all_x) - min(all_x)
    bb_h = max(all_y) - min(all_y)
    corridor_horizontal = bb_w >= bb_h

    if corridor_horizontal:
        cy = primary.y - 1
        if cy < 0:
            cy = primary.y2
        corridor_x = min(b.x for b in blocks)
        corridor_w = max(b.x2 for b in blocks) - corridor_x
        if corridor_w < 2:
            return rooms
        corridor = Room(counter[0], corridor_x, cy, corridor_w, 1, "corridor")
        counter[0] += 1
        trimmed = []
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
        cx = primary.x2
        if cx >= max(b.x2 for b in blocks):
            cx = primary.x - 1
        if cx < 0:
            return rooms
        corridor_y = min(b.y for b in blocks)
        corridor_h = max(b.y2 for b in blocks) - corridor_y
        if corridor_h < 2:
            return rooms
        corridor = Room(counter[0], cx, corridor_y, 1, corridor_h, "corridor")
        counter[0] += 1
        trimmed = []
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


def partition_rooms(
    blocks:    list[FootprintBlock],
    archetype: BuildingArchetype,
    layout:    LayoutPlan,
    cfg:       dict,
    rng:       random.Random,
) -> list[Room]:
    min_size   = cfg["min_room"]
    room_kinds = list(ARCHETYPE_ROOM_KINDS[archetype])
    largest    = max(blocks, key=lambda b: b.w * b.h)
    counter    = [0]

    total_area   = sum(b.w * b.h for b in blocks)
    largest_area = largest.w * largest.h
    n_largest    = max(1, min(round(len(room_kinds) * largest_area / total_area), len(room_kinds)))

    largest_kinds   = room_kinds[:n_largest]
    remaining_kinds = room_kinds[n_largest:]

    if "primary" in largest_kinds:
        largest_kinds.remove("primary")
        largest_kinds = ["primary"] + largest_kinds

    primary_frac = cfg["primary_frac"]
    primary_h    = max(min_size, int(largest.h * primary_frac))
    primary_h    = min(primary_h, largest.h - min_size * (n_largest - 1))

    if n_largest == 1 or primary_h >= largest.h:
        rooms_largest = _guillotine(largest, largest_kinds, min_size, rng, counter)
    else:
        primary_strip = FootprintBlock(largest.x, largest.y + largest.h - primary_h, largest.w, primary_h)
        rest_strip    = FootprintBlock(largest.x, largest.y, largest.w, largest.h - primary_h)
        primary_obj   = Room(counter[0], primary_strip.x, primary_strip.y, primary_strip.w, primary_strip.h, "primary")
        counter[0]   += 1
        other_rooms   = (
            _guillotine(rest_strip, largest_kinds[1:], min_size, rng, counter)
            if n_largest > 1 and rest_strip.h >= min_size else []
        )
        rooms_largest = [primary_obj] + other_rooms

    other_block_rooms: list[Room] = []
    for b in blocks:
        if b is largest:
            continue
        b_area    = b.w * b.h
        other_sum = sum(ob.w * ob.h for ob in blocks if ob is not largest)
        n_b       = max(1, min(round(len(remaining_kinds) * b_area / other_sum) if other_sum else 1, len(remaining_kinds)))
        b_kinds          = remaining_kinds[:n_b]
        remaining_kinds  = remaining_kinds[n_b:]
        if b_kinds:
            other_block_rooms += _guillotine(b, b_kinds, min_size, rng, counter)

    all_rooms = rooms_largest + other_block_rooms

    if layout == LayoutPlan.CORRIDOR and len(all_rooms) > 1:
        all_rooms = _insert_corridor(all_rooms, blocks, min_size, rng, counter)

    return all_rooms


# ---------------------------------------------------------------------------
# Door placement helpers
# ---------------------------------------------------------------------------

def _rooms_share_wall(a: Room, b: Room) -> Optional[tuple[int, int, str]]:
    """Return (door_x, door_y, direction_from_a_to_b) or None."""
    if a.x2 == b.x and max(a.y, b.y) < min(a.y2, b.y2):
        return (b.x, (max(a.y, b.y) + min(a.y2, b.y2)) // 2, "east")
    if b.x2 == a.x and max(a.y, b.y) < min(a.y2, b.y2):
        return (a.x, (max(a.y, b.y) + min(a.y2, b.y2)) // 2, "west")
    if a.y2 == b.y and max(a.x, b.x) < min(a.x2, b.x2):
        return ((max(a.x, b.x) + min(a.x2, b.x2)) // 2, b.y, "south")
    if b.y2 == a.y and max(a.x, b.x) < min(a.x2, b.x2):
        return ((max(a.x, b.x) + min(a.x2, b.x2)) // 2, a.y, "north")
    return None


def _find_exterior_entrance(primary: Room, blocks: list[FootprintBlock]) -> Optional[Door]:
    mid_x = (primary.x + primary.x2) // 2
    mid_y = (primary.y + primary.y2) // 2

    if not any(b.contains(mid_x, primary.y2) for b in blocks):
        return Door(mid_x, primary.y2 - 1, "south")
    if not any(b.contains(mid_x, primary.y - 1) for b in blocks):
        return Door(mid_x, primary.y, "north")
    if not any(b.contains(primary.x - 1, mid_y) for b in blocks):
        return Door(primary.x, mid_y, "west")
    if not any(b.contains(primary.x2, mid_y) for b in blocks):
        return Door(primary.x2 - 1, mid_y, "east")
    return None


def place_doors(
    rooms:  list[Room],
    blocks: list[FootprintBlock],
    layout: LayoutPlan,
    rng:    random.Random,
) -> list[Door]:
    doors:   list[Door] = []
    primary: Room       = rooms[0]

    entrance = _find_exterior_entrance(primary, blocks)
    if entrance:
        doors.append(entrance)

    if layout == LayoutPlan.OPEN_PLAN:
        for room in rooms[1:]:
            if room.kind == "corridor":
                continue
            wall = _rooms_share_wall(primary, room)
            if wall:
                doors.append(Door(wall[0], wall[1], wall[2]))
    else:
        corridor = next((r for r in rooms if r.kind == "corridor"), None)
        if corridor:
            wall = _rooms_share_wall(primary, corridor)
            if wall:
                doors.append(Door(wall[0], wall[1], wall[2]))
            for room in rooms:
                if room is primary or room.kind == "corridor":
                    continue
                wall = _rooms_share_wall(corridor, room)
                if wall:
                    doors.append(Door(wall[0], wall[1], wall[2]))
        else:
            for room in rooms[1:]:
                wall = _rooms_share_wall(primary, room)
                if wall:
                    doors.append(Door(wall[0], wall[1], wall[2]))

    return doors


# ---------------------------------------------------------------------------
# Wall extraction (identical to dungeongen.py approach)
# ---------------------------------------------------------------------------

def extract_walls(
    grid:     list[list[CellKind]],
    canvas_w: int,
    canvas_h: int,
) -> list[list[list[int]]]:
    """Extract exterior wall segments as [[x1,y1],[x2,y2]] in grid coordinates."""
    wall_lines: list[list[list[int]]] = []
    for y in range(canvas_h):
        for x in range(canvas_w):
            if grid[y][x] != CellKind.FLOOR:
                continue
            if y == 0 or grid[y - 1][x] == CellKind.EMPTY:
                wall_lines.append([[x, y], [x + 1, y]])
            if y == canvas_h - 1 or grid[y + 1][x] == CellKind.EMPTY:
                wall_lines.append([[x, y + 1], [x + 1, y + 1]])
            if x == 0 or grid[y][x - 1] == CellKind.EMPTY:
                wall_lines.append([[x, y], [x, y + 1]])
            if x == canvas_w - 1 or grid[y][x + 1] == CellKind.EMPTY:
                wall_lines.append([[x + 1, y], [x + 1, y + 1]])
    return wall_lines


# ---------------------------------------------------------------------------
# Rendering via the dungeongen library Map pipeline
# ---------------------------------------------------------------------------

def render_building_with_dungeongen(
    rooms:     list[Room],
    doors:     list[Door],
    canvas_w:  int,
    canvas_h:  int,
) -> bytes:
    """
    Build a dungeongen Map from our room/door data and render it using the
    same Map.render() pipeline that dungeon generation uses.
    This ensures visual consistency (crosshatching, shadows, borders, etc.)
    """
    from dungeongen.map.map import Map
    from dungeongen.map.room import Room as DGRoom, RoomType
    from dungeongen.map.passage import Passage
    from dungeongen.map.door import Door as DGDoor, DoorOrientation, DoorType
    from dungeongen.map.exit import Exit
    from dungeongen.map.enums import RoomDirection
    from dungeongen.options import Options
    import skia

    options = Options()
    dungeon_map = Map(options)

    # Map our internal Room -> dungeongen Room
    dg_rooms: dict[int, DGRoom] = {}
    for room in rooms:
        dg_room = DGRoom.from_grid(room.x, room.y, room.w, room.h, RoomType.RECTANGULAR, room.id + 1)
        dungeon_map.add_element(dg_room)
        dg_rooms[room.id] = dg_room

    # Build lookup: grid position -> (our_door, DGDoor)
    # For interior doors: connect adjacent rooms via a 1-cell passage
    # For the exterior entrance: add an Exit element
    entrance_door = next(
        (d for d in doors if _is_exterior_door(d, rooms[0])),
        None,
    )

    for door in doors:
        if door is entrance_door:
            # Exterior entrance → Exit element
            direction = _direction_to_dg(door.direction)
            exit_elem = Exit.from_grid(door.x, door.y, direction)
            dungeon_map.add_element(exit_elem)
            # Connect to the primary room
            dg_rooms[rooms[0].id].connect_to(exit_elem)
        else:
            # Interior door → short Passage with a Door in it
            orientation = (
                DoorOrientation.HORIZONTAL
                if door.direction in ("north", "south")
                else DoorOrientation.VERTICAL
            )
            dg_door = DGDoor.from_grid(door.x, door.y, orientation, DoorType.OPEN)
            dungeon_map.add_element(dg_door)

            # Find the two rooms this door connects and wire them
            room_a, room_b = _find_rooms_for_door(door, rooms)
            if room_a is not None and room_b is not None:
                dg_rooms[room_a.id].connect_to(dg_door)
                dg_door.connect_to(dg_rooms[room_b.id])

    # Render with the same transform as dungeongen.py
    map_units_per_grid = 64          # dungeongen internal units per grid cell
    scale       = GRID_SIZE / map_units_per_grid   # = 50/64
    canvas_width  = canvas_w * GRID_SIZE + PADDING * 2
    canvas_height = canvas_h * GRID_SIZE + PADDING * 2

    surface = skia.Surface(int(canvas_width), int(canvas_height))
    canvas  = surface.getCanvas()
    canvas.clear(skia.Color(255, 255, 255))

    transform = skia.Matrix()
    transform.setScale(scale, scale)
    transform.postTranslate(PADDING, PADDING)

    dungeon_map.render(canvas, transform)

    # Sync square — identical to dungeongen.py
    sync_paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        Color=skia.Color(180, 180, 180),
        StrokeWidth=2,
    )
    canvas.drawRect(skia.Rect(1, 1, GRID_SIZE - 1, GRID_SIZE - 1), sync_paint)

    image    = surface.makeImageSnapshot()
    png_data = image.encodeToData()
    if png_data is None:
        raise RuntimeError("Failed to encode building PNG")
    return bytes(png_data)


def _direction_to_dg(direction: str):
    """Convert our direction string to dungeongen RoomDirection."""
    from dungeongen.map.enums import RoomDirection
    return {
        "north": RoomDirection.NORTH,
        "south": RoomDirection.SOUTH,
        "east":  RoomDirection.EAST,
        "west":  RoomDirection.WEST,
    }[direction]


def _is_exterior_door(door: Door, primary: Room) -> bool:
    """True if this door is on the exterior wall of the primary room."""
    mid_x = (primary.x + primary.x2) // 2
    mid_y = (primary.y + primary.y2) // 2
    if door.direction == "south" and door.y == primary.y2 - 1 and door.x == mid_x:
        return True
    if door.direction == "north" and door.y == primary.y and door.x == mid_x:
        return True
    if door.direction == "west" and door.x == primary.x and door.y == mid_y:
        return True
    if door.direction == "east" and door.x == primary.x2 - 1 and door.y == mid_y:
        return True
    return False


def _find_rooms_for_door(door: Door, rooms: list[Room]) -> tuple[Optional[Room], Optional[Room]]:
    """Return the two rooms that share the wall where this door sits."""
    dx, dy = door.x, door.y
    direction = door.direction
    room_a: Optional[Room] = None
    room_b: Optional[Room] = None

    for room in rooms:
        if room.x <= dx < room.x2 and room.y <= dy < room.y2:
            # dx,dy is inside this room
            if direction in ("south", "east"):
                room_a = room
            else:
                room_b = room
        # Neighbour cell
        elif direction == "east" and room.x == dx + 1 and room.y <= dy < room.y2:
            room_b = room
        elif direction == "west" and room.x2 == dx and room.y <= dy < room.y2:
            room_a = room
        elif direction == "south" and room.y == dy + 1 and room.x <= dx < room.x2:
            room_b = room
        elif direction == "north" and room.y2 == dy and room.x <= dx < room.x2:
            room_a = room

    return room_a, room_b


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_building(params: BuildingParams) -> tuple[BuildingResult, bytes, list]:
    """
    Generate a building.
    Returns (BuildingResult, png_bytes, wall_lines).
    """
    rng = random.Random(params.seed)
    cfg = ARCHETYPE_CFG[params.archetype]

    base_w, base_h = cfg["base_size"]
    total_w = max(4, base_w + rng.randint(-1, 1))
    total_h = max(4, base_h + rng.randint(-1, 1))

    blocks, canvas_w, canvas_h = build_footprint(params.footprint, total_w, total_h, rng)

    grid = make_grid(canvas_w, canvas_h)
    stamp_footprint(grid, blocks)

    rooms = partition_rooms(blocks, params.archetype, params.layout, cfg, rng)
    doors = place_doors(rooms, blocks, params.layout, rng)
    wall_lines = extract_walls(grid, canvas_w, canvas_h)

    # Render using the dungeongen library pipeline (same visual style as dungeons)
    png_bytes = render_building_with_dungeongen(rooms, doors, canvas_w, canvas_h)

    result = BuildingResult(
        grid=grid,
        width=canvas_w,
        height=canvas_h,
        rooms=rooms,
        doors=doors,
        seed=params.seed,
    )

    return result, png_bytes, wall_lines
