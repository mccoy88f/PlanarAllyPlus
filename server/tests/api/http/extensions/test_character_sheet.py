import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from src.api.http.extensions.character_sheet import (
    create_sheet,
    update_sheet,
    delete_sheet,
    duplicate_sheet,
    associate_sheet,
    set_default,
    toggle_sheet_visibility
)

# We'll use pytest's async features since these are aiohttp handlers
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_request():
    request = MagicMock(spec=web.Request)
    request.match_info = {}
    request.query = {}
    # Make json() returning a coroutine
    request.json = AsyncMock(return_value={})
    return request

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    user.name = "Test User"
    return user

@pytest.fixture
def mock_room():
    room = MagicMock()
    room.id = 1
    room.name = "Test Room"
    return room

@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
async def test_create_sheet_creates_db_record(MockCharacterSheet, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    
    mock_pr = MagicMock()
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.json.return_value = {
        "roomCreator": "Creator",
        "roomName": "Test Room",
        "name": "New Hero"
    }

    mock_sheet = MagicMock()
    mock_sheet.id = 42
    MockCharacterSheet.create.return_value = mock_sheet

    response = await create_sheet(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    assert body["sheetId"] == "42"
    MockCharacterSheet.create.assert_called_once()


@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
async def test_update_sheet_updates_db_record(MockCharacterSheet, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    mock_pr = MagicMock()
    mock_pr.role = 2 # DM
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.match_info = {"sheet_id": "42"}
    mock_request.json.return_value = {
        "roomCreator": "Creator",
        "roomName": "Test Room",
        "sheet": {"name": "Updated Hero"}
    }
    
    mock_sheet = MagicMock()
    mock_sheet.room.id = mock_room.id
    mock_sheet.owner.id = mock_user.id
    MockCharacterSheet.get_or_none.return_value = mock_sheet
    
    response = await update_sheet(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    mock_sheet.save.assert_called_once()


@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
async def test_duplicate_sheet_duplicates_db_record(MockCharacterSheet, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    mock_pr = MagicMock()
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.match_info = {"sheet_id": "42"}
    mock_request.json.return_value = {
        "roomCreator": "Creator",
        "roomName": "Test Room",
        "newName": "Cloned Hero"
    }

    mock_src_sheet = MagicMock()
    mock_src_sheet.room.id = mock_room.id
    mock_src_sheet.owner.id = mock_user.id
    mock_src_sheet.data = "{}"
    MockCharacterSheet.get_or_none.return_value = mock_src_sheet
    
    mock_new_sheet = MagicMock()
    mock_new_sheet.id = 43
    MockCharacterSheet.create.return_value = mock_new_sheet

    response = await duplicate_sheet(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    assert body["sheetId"] == "43"
    MockCharacterSheet.create.assert_called_once()


@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
@patch("src.api.http.extensions.character_sheet.Character")
async def test_associate_sheet_sets_character(MockCharacter, MockCharacterSheet, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    mock_pr = MagicMock()
    mock_pr.role = 2 # DM
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.match_info = {"sheet_id": "42"}
    mock_request.json.return_value = {
        "roomCreator": "Creator",
        "roomName": "Test Room",
        "characterId": 100
    }

    mock_char = MagicMock()
    mock_char.campaign_id = mock_room.id
    mock_char.owner_id = mock_user.id
    MockCharacter.get_by_id.return_value = mock_char

    mock_sheet = MagicMock()
    mock_sheet.room.id = mock_room.id
    mock_sheet.owner.id = mock_user.id
    mock_sheet.data = "{}"
    # To check existing link 
    MockCharacterSheet.get_or_none.side_effect = [mock_sheet, None] 

    response = await associate_sheet(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    assert mock_sheet.character == mock_char
    mock_sheet.save.assert_called_once()


@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheetDefault")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
async def test_set_default_creates_or_updates_default_record(MockCharacterSheet, MockCharacterSheetDefault, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    mock_pr = MagicMock()
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.json.return_value = {
        "roomCreator": "Creator",
        "roomName": "Test Room",
        "sheetId": 42
    }

    mock_sheet = MagicMock()
    mock_sheet.room.id = mock_room.id
    mock_sheet.owner.id = mock_user.id
    MockCharacterSheet.get_or_none.return_value = mock_sheet

    MockCharacterSheetDefault.get_or_none.return_value = None

    response = await set_default(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    MockCharacterSheetDefault.create.assert_called_once_with(user=mock_user, room=mock_room, sheet=mock_sheet)


@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
async def test_toggle_visibility_changes_boolean(MockCharacterSheet, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    mock_pr = MagicMock()
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.match_info = {"sheet_id": "42"}
    mock_request.json.return_value = {}
    mock_request.query = {
        "room_creator": "Creator",
        "room_name": "Test Room",
    }

    mock_sheet = MagicMock()
    mock_sheet.room.id = mock_room.id
    mock_sheet.owner.id = mock_user.id
    mock_sheet.visible_to_players = False
    MockCharacterSheet.get_or_none.return_value = mock_sheet

    response = await toggle_sheet_visibility(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    assert body["visibleToPlayers"] is True
    assert mock_sheet.visible_to_players is True
    mock_sheet.save.assert_called_once()


@patch("src.api.http.extensions.character_sheet.get_authorized_user")
@patch("src.api.http.extensions.character_sheet._get_room")
@patch("src.api.http.extensions.character_sheet.PlayerRoom")
@patch("src.api.http.extensions.character_sheet.CharacterSheet")
async def test_delete_sheet_deletes_db_record(MockCharacterSheet, MockPlayerRoom, mock_get_room, mock_get_authorized_user, mock_request, mock_user, mock_room):
    mock_get_authorized_user.return_value = mock_user
    mock_get_room.return_value = mock_room
    mock_pr = MagicMock()
    mock_pr.role = 2 # DM
    MockPlayerRoom.get_or_none.return_value = mock_pr
    
    mock_request.match_info = {"sheet_id": "42"}
    mock_request.query = {
        "room_creator": "Creator",
        "room_name": "Test Room",
    }
    
    mock_sheet = MagicMock()
    mock_sheet.room.id = mock_room.id
    mock_sheet.owner.id = mock_user.id
    MockCharacterSheet.get_or_none.return_value = mock_sheet
    
    response = await delete_sheet(mock_request)
    assert response.status == 200
    
    body = json.loads(response.text)
    assert body["ok"] is True
    mock_sheet.delete_instance.assert_called_once()
