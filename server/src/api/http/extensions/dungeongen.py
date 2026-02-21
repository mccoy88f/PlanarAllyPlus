"""Dungeongen extension - procedural dungeon generation API."""

import random
import uuid

from aiohttp import web

from ....auth import get_authorized_user
from ....utils import STATIC_DIR

# PlanarAlly grid: 1 cell = 50 pixels
GRID_SIZE = 50
PADDING = 40


async def generate(request: web.Request) -> web.Response:
    """Generate dungeon and return PNG URL + dimensions."""
    await get_authorized_user(request)

    try:
        from dungeongen.layout import (
            DungeonArchetype,
            DungeonGenerator,
            DungeonSize,
            GenerationParams,
            SymmetryType,
        )
        from dungeongen.webview.adapter import convert_dungeon
    except ImportError as e:
        return web.HTTPInternalServerError(
            text=f"Dungeongen extension not available: {e}. Ensure extensions/dungeongen-main is installed."
        )

    data = await request.json() or {}

    params = GenerationParams()

    size_map = {
        "tiny": DungeonSize.TINY,
        "small": DungeonSize.SMALL,
        "medium": DungeonSize.MEDIUM,
        "large": DungeonSize.LARGE,
        "xlarge": DungeonSize.XLARGE,
    }
    params.size = size_map.get(data.get("size", "medium"), DungeonSize.MEDIUM)

    archetype_map = {
        "classic": DungeonArchetype.CLASSIC,
        "warren": DungeonArchetype.WARREN,
        "temple": DungeonArchetype.TEMPLE,
        "crypt": DungeonArchetype.CRYPT,
        "cavern": DungeonArchetype.CAVERN,
        "fortress": DungeonArchetype.FORTRESS,
        "lair": DungeonArchetype.LAIR,
    }
    params.archetype = archetype_map.get(data.get("archetype", "classic"), DungeonArchetype.CLASSIC)

    symmetry_map = {
        "none": SymmetryType.NONE,
        "bilateral": SymmetryType.BILATERAL,
        "radial2": SymmetryType.RADIAL_2,
        "radial4": SymmetryType.RADIAL_4,
        "partial": SymmetryType.PARTIAL,
    }
    params.symmetry = symmetry_map.get(data.get("symmetry", "none"), SymmetryType.NONE)

    pack_level = data.get("pack", "normal")
    if pack_level == "sparse":
        params.density = 0.2
    elif pack_level == "tight":
        params.density = 0.8
    else:
        params.density = 0.5

    roomsize_level = data.get("roomsize", "mixed")
    if roomsize_level == "cozy":
        params.room_size_bias = -1.0
    elif roomsize_level == "grand":
        params.room_size_bias = 0.8
    else:
        params.room_size_bias = 0.0

    params.round_room_chance = 0.3 if data.get("round_rooms", False) else 0.05
    params.hall_chance = 0.15 if data.get("halls", True) else 0.0

    cross_level = data.get("cross", "med")
    if cross_level == "none":
        params.loop_factor = 0.0
        params.extra_room_connections = 0.0
        params.extra_passage_junctions = 0.0
    elif cross_level == "low":
        params.loop_factor = 0.15
        params.extra_room_connections = 0.1
        params.extra_passage_junctions = 0.05
    elif cross_level == "med":
        params.loop_factor = 0.3
        params.extra_room_connections = 0.2
        params.extra_passage_junctions = 0.15
    else:
        params.loop_factor = 0.5
        params.extra_room_connections = 0.4
        params.extra_passage_junctions = 0.3

    params.passage_width = 1
    params.symmetry_break = float(data.get("symmetry_break", 0.2))

    water_level = data.get("water", "dry")
    water_depth_map = {
        "dry": 0.0,
        "puddles": 0.75,
        "pools": 0.60,
        "lakes": 0.45,
        "flooded": 0.30,
    }
    water_depth = water_depth_map.get(water_level, 0.0)
    params.water_enabled = water_depth > 0
    params.water_threshold = water_depth

    water_scale = data.get("water_scale", 0.018)
    water_res = data.get("water_res", 0.2)
    water_stroke = data.get("water_stroke", 3.5)
    water_ripple = data.get("water_ripple", 8.0)
    show_numbers = data.get("show_numbers", True)

    seed = data.get("seed")
    if seed is not None and seed != "":
        try:
            seed = int(seed)
        except ValueError:
            seed = hash(seed) % (2**31)
    else:
        seed = random.randint(0, 2**31)

    generator = DungeonGenerator(params)
    dungeon = generator.generate(seed=seed)

    bounds = dungeon.bounds
    cells_x = bounds[2] - bounds[0]
    cells_y = bounds[3] - bounds[1]

    if cells_x > 60 or cells_y > 60:
        return web.HTTPBadRequest(
            text=f"Dungeon too large ({cells_x}x{cells_y} cells). Try a smaller size."
        )

    try:
        import skia

        dungeon_map = convert_dungeon(
            dungeon,
            water_depth=water_depth,
            water_scale=water_scale,
            water_res=water_res,
            water_stroke=water_stroke,
            water_ripple=water_ripple,
            show_numbers=show_numbers,
        )

        map_units_per_grid = 64
        scale = GRID_SIZE / map_units_per_grid
        canvas_width = cells_x * GRID_SIZE + PADDING * 2
        canvas_height = cells_y * GRID_SIZE + PADDING * 2

        surface = skia.Surface(int(canvas_width), int(canvas_height))
        canvas = surface.getCanvas()
        canvas.clear(skia.Color(255, 255, 255))

        transform = skia.Matrix()
        transform.setScale(scale, scale)
        transform.postTranslate(PADDING, PADDING)

        dungeon_map.render(canvas, transform)

        # Draw sync square (1 cell = GRID_SIZE px) in top-left for PlanarAlly auto-resize
        sync_paint = skia.Paint(
            Style=skia.Paint.kStroke_Style,
            Color=skia.Color(180, 180, 180),
            StrokeWidth=2,
        )
        canvas.drawRect(skia.Rect(0, 0, GRID_SIZE, GRID_SIZE), sync_paint)

        image = surface.makeImageSnapshot()
        png_data = image.encodeToData()
        if png_data is None:
            return web.HTTPInternalServerError(text="Failed to encode PNG")

        png_bytes = bytes(png_data)

    except Exception as e:
        return web.HTTPInternalServerError(text=f"Render failed: {e}")

    # Save to static temp
    temp_dir = STATIC_DIR / "temp" / "dungeons"
    temp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    filepath = temp_dir / filename
    filepath.write_bytes(png_bytes)

    # Extract walls from occupancy grid
    wall_lines = []
    try:
        from dungeongen.layout.occupancy import CellType
        grid = generator.occupancy
        for y in range(bounds[1] - 1, bounds[3] + 2):
            for x in range(bounds[0] - 1, bounds[2] + 2):
                cell = grid.get(x, y)
                if cell.cell_type in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                    bx, by = x - bounds[0], y - bounds[1]
                    # North
                    if grid.get(x, y - 1).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                        wall_lines.append([[bx, by], [bx + 1, by]])
                    # South
                    if grid.get(x, y + 1).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                        wall_lines.append([[bx, by + 1], [bx + 1, by + 1]])
                    # West
                    if grid.get(x - 1, y).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                        wall_lines.append([[bx, by], [bx, by + 1]])
                    # East
                    if grid.get(x + 1, y).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                        wall_lines.append([[bx + 1, by], [bx + 1, by + 1]])
    except ImportError:
        pass

    url = f"/static/temp/dungeons/{filename}"
    return web.json_response(
        {
            "url": url,
            "gridCells": {"width": cells_x, "height": cells_y},
            "imageWidth": canvas_width,
            "imageHeight": canvas_height,
            "syncSquareSize": GRID_SIZE,
            "seed": seed,
            "walls": {
                "lines": wall_lines,
            },
        }
    )
