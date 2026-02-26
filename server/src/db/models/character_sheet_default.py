from typing import cast

from peewee import ForeignKeyField

from ..base import BaseDbModel
from .character_sheet import CharacterSheet
from .room import Room
from .user import User


class CharacterSheetDefault(BaseDbModel):
    user = cast(User, ForeignKeyField(User, backref="default_character_sheets", on_delete="CASCADE"))
    room = cast(Room, ForeignKeyField(Room, backref="default_character_sheets", on_delete="CASCADE"))
    sheet = cast(
        CharacterSheet,
        ForeignKeyField(CharacterSheet, backref="default_for_users", on_delete="CASCADE"),
    )
