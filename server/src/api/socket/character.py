from typing import Any

from ... import auth
from ...api.socket.constants import GAME_NS
from ...app import app, sio
from ...db.models.character import Character
from ...db.models.shape import Shape
from ...logs import logger
from ...models.access import has_ownership
from ...models.role import Role
from ...state.game import game_state
from ..helpers import _send_game
from ..models.character import CharacterCreate, CharacterLink


def _asset_from_assetrect_shape(shape: Shape):
    """L'immagine del token è su AssetRect → Asset; Shape non ha attributo .asset."""
    if shape.type_ != "assetrect":
        return None
    try:
        ar = shape.assetrect_set.get()
    except Exception:
        return None
    return ar.asset if ar else None


@sio.on("Character.Create", namespace=GAME_NS)
@auth.login_required(app, sio, "game")
async def create_character(sid: str, raw_data: Any):
    data = CharacterCreate(**raw_data)

    pr = game_state.get(sid)

    shape = Shape.get_by_id(data.shape)
    asset = _asset_from_assetrect_shape(shape) if shape is not None else None

    if shape is None or asset is None:
        logger.error("Attempt to create character for incorrect shape")
        return
    elif not has_ownership(shape, pr, edit=True):
        logger.warning("Attempt to create character without access")
        return
    elif shape.character_id is not None:
        logger.warning("Shape is already associated with a character")
        return

    try:
        char = Character.create(name=data.name, owner=pr.player, campaign=pr.room, asset=asset)
    except:
        logger.exception("Failed to create character")
        return
    else:
        shape.character = char
        shape.save()

    for psid, ppr in game_state.get_t(room=pr.room):
        if has_ownership(shape, ppr, edit=True):
            await _send_game(
                "Character.Created",
                char.as_pydantic(),
                room=psid,
            )


@sio.on("Character.Remove", namespace=GAME_NS)
@auth.login_required(app, sio, "game")
async def remove_character(sid: str, char_id: int):
    pr = game_state.get(sid)

    character = Character.get_by_id(char_id)

    if character is None:
        logger.error("Attempt to remove unknown character")
        return
    elif character.campaign != pr.room:
        logger.error("Attempt to remove character from other campaign")
        return
    # Only the owner and the DM can remove a character
    elif character.owner != pr.player and pr.role != Role.DM:
        logger.error("Attempt to remove character by player without access")
        return

    shape = character.shape

    for psid, ppr in game_state.get_t(room=pr.room):
        if has_ownership(shape, ppr, edit=True):
            await _send_game(
                "Character.Removed",
                char_id,
                room=psid,
            )

    # If the associated shape is not placed anywhere, remove it as well
    if character.shape.layer is None:
        character.shape.delete_instance(True)

    character.delete_instance(True)


@sio.on("Character.Link", namespace=GAME_NS)
@auth.login_required(app, sio, "game")
async def link_character(sid: str, raw_data: Any):
    data = CharacterLink(**raw_data)

    pr = game_state.get(sid)

    character = Character.get_by_id(data.characterId)
    shape = Shape.get_by_id(data.shape)

    if character is None or shape is None:
        logger.error("Attempt to link unknown character or shape")
        return
    elif character.campaign != pr.room or shape.layer.floor.location.room != pr.room:
        logger.error("Attempt to link character/shape from other campaign")
        return
    
    # Check permissions: DM or owner of character AND owner of shape
    is_dm = pr.role == Role.DM
    can_link_char = is_dm or character.owner == pr.player
    can_link_shape = is_dm or has_ownership(shape, pr, edit=True)

    if not (can_link_char and can_link_shape):
        logger.warning("Attempt to link character without access")
        return

    # Link
    shape.character = character
    shape.save()

    for psid, ppr in game_state.get_t(room=pr.room):
        if has_ownership(shape, ppr, edit=True):
            await _send_game(
                "Character.Linked",
                {"charId": character.id, "shape": shape.uuid},
                room=psid,
            )
