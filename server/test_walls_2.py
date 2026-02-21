import random
from dungeongen.layout import DungeonGenerator, GenerationParams, DungeonSize
from dungeongen.layout.occupancy import CellType

params = GenerationParams()
params.size = DungeonSize.TINY
generator = DungeonGenerator(params)
dungeon = generator.generate(seed=42)

grid = generator.occupancy

# Find bounds
bounds = dungeon.bounds
print(f"Bounds: {bounds}")

# Extract walls
wall_segments = []

for y in range(bounds[1] - 1, bounds[3] + 2):
    for x in range(bounds[0] - 1, bounds[2] + 2):
        cell = grid.get(x, y)
        is_walkable = cell.cell_type in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR)
        
        if is_walkable:
            # Check 4 neighbors
            # North
            if grid.get(x, y - 1).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                wall_segments.append(((x, y), (x + 1, y)))
            # South
            if grid.get(x, y + 1).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                wall_segments.append(((x, y + 1), (x + 1, y + 1)))
            # West
            if grid.get(x - 1, y).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                wall_segments.append(((x, y), (x, y + 1)))
            # East
            if grid.get(x + 1, y).cell_type not in (CellType.ROOM, CellType.PASSAGE, CellType.DOOR):
                wall_segments.append(((x + 1, y), (x + 1, y + 1)))

print(f"Extracted {len(wall_segments)} wall segments")
for seg in wall_segments[:10]:
    print(seg)
