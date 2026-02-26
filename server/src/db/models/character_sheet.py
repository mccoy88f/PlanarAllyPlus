from typing import cast

from peewee import BooleanField, ForeignKeyField, TextField

from ..base import BaseDbModel
from .character import Character
from .room import Room
from .user import User


class CharacterSheet(BaseDbModel):
    owner = cast(User, ForeignKeyField(User, backref="character_sheets", on_delete="CASCADE"))
    room = cast(Room, ForeignKeyField(Room, backref="character_sheets", on_delete="CASCADE"))
    character = cast(
        Character | None,
        ForeignKeyField(Character, backref="character_sheet", on_delete="SET NULL", default=None, null=True),
    )

    name = cast(str, TextField())
    data = cast(str, TextField())  # JSON blob
    visible_to_players = cast(bool, BooleanField(default=False))

    created_at = cast(str, TextField())  # ISO format timestamp
    updated_at = cast(str, TextField())  # ISO format timestamp
