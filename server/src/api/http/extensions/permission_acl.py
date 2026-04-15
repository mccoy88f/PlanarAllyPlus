"""Modello ACL condiviso per risorse delle estensioni (documenti, schede, voci compendio, …).

Il creatore ha sempre view+edit. ``public_view`` consente a qualunque utente autenticato
di visualizzare (non modificare). I ``grants`` elencano diritti per nome utente.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExtensionResourceGrant(BaseModel):
    user_name: str = Field(alias="userName")
    can_view: bool = Field(alias="canView")
    can_edit: bool = Field(alias="canEdit")

    model_config = {"populate_by_name": True}

    @field_validator("user_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class ExtensionResourceAclPayload(BaseModel):
    """Payload serializzabile (client / JSON file)."""

    creator_name: str = Field(alias="creatorName")
    public_view: bool = Field(alias="publicView", default=False)
    grants: list[ExtensionResourceGrant] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("creator_name")
    @classmethod
    def strip_creator(cls, v: str) -> str:
        return v.strip()


def effective_extension_access(
    viewer_name: str,
    acl: ExtensionResourceAclPayload,
) -> tuple[bool, bool]:
    """Restituisce (can_view, can_edit) per ``viewer_name``."""
    if viewer_name == acl.creator_name:
        return True, True
    for g in acl.grants:
        if g.user_name == viewer_name:
            can_view = g.can_view or g.can_edit
            return can_view, g.can_edit
    if acl.public_view:
        return True, False
    return False, False


def user_can_view_acl(viewer_name: str, acl: ExtensionResourceAclPayload) -> bool:
    return effective_extension_access(viewer_name, acl)[0]


def user_can_edit_acl(viewer_name: str, acl: ExtensionResourceAclPayload) -> bool:
    return effective_extension_access(viewer_name, acl)[1]


def acl_payload_from_dict(data: dict[str, Any]) -> ExtensionResourceAclPayload:
    return ExtensionResourceAclPayload.model_validate(data)


def legacy_visible_to_players_to_payload(creator_name: str, visible: bool) -> ExtensionResourceAclPayload:
    """Migrazione da un singolo booleano ``visible_to_players``."""
    return ExtensionResourceAclPayload(creatorName=creator_name, publicView=visible, grants=[])
