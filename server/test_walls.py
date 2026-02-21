import random
from dungeongen.layout import DungeonGenerator, GenerationParams, DungeonSize
from dungeongen.layout.models import Dungeon, RoomShape

params = GenerationParams()
params.size = DungeonSize.TINY
generator = DungeonGenerator(params)
dungeon = generator.generate(seed=42)

for room in dungeon.rooms.values():
    if room.shape != RoomShape.RECT: continue
    print(f"Room {room.id}: (x={room.x}, y={room.y}, w={room.width}, h={room.height})")
    
for door in dungeon.doors.values():
    print(f"Door {door.id} for Room {door.room_id}: (x={door.x}, y={door.y}, dir={door.direction})")

for passage in dungeon.passages.values():
    print(f"Passage {passage.id}: {passage.waypoints} w={passage.width}")
