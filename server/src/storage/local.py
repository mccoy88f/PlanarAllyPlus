from __future__ import annotations

from pathlib import Path

from ..utils import THUMBNAILS_DIR, get_asset_hash_subpath
from .base import StorageBackend


def _is_thumbnail_suffix(suffix: str | None) -> bool:
    return suffix is not None and suffix.startswith(".thumb.")


class LocalStorageBackend(StorageBackend):
    def __init__(self, assets_dir: Path) -> None:
        self.assets_dir = assets_dir
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, file_hash: str, suffix: str | None = None) -> Path:
        sub = get_asset_hash_subpath(file_hash)
        base = THUMBNAILS_DIR if _is_thumbnail_suffix(suffix) else self.assets_dir
        if suffix:
            return base / f"{sub}{suffix}"
        return base / sub

    async def store(self, file_hash: str, data: bytes, *, suffix: str | None = None) -> None:
        self.store_sync(file_hash, data, suffix=suffix)

    async def exists(self, file_hash: str) -> bool:
        return self.exists_sync(file_hash)

    async def retrieve(self, file_hash: str) -> bytes:
        return self.retrieve_sync(file_hash)

    async def delete(self, file_hash: str, *, suffix: str | None = None) -> None:
        path = self._path(file_hash, suffix)
        if path.exists():
            path.unlink()

    def store_sync(self, file_hash: str, data: bytes, *, suffix: str | None = None) -> None:
        path = self._path(file_hash, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def exists_sync(self, file_hash: str) -> bool:
        return self._path(file_hash).exists()

    def retrieve_sync(self, file_hash: str) -> bytes:
        with open(self._path(file_hash), "rb") as f:
            return f.read()

    def get_url(self, file_hash: str, *, thumbnail_format: str | None = None) -> str:
        sub = get_asset_hash_subpath(file_hash)
        if thumbnail_format is not None:
            return f"/static/thumbnails/{sub}.thumb.{thumbnail_format}"
        return f"/static/assets/{sub}"

    def get_public_url_base(self) -> str | None:
        return None
