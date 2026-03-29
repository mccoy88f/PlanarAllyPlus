"""SVG companion for wall segments (grid coordinates), usable with Extra → Carica muri (svg)."""

from __future__ import annotations

import hashlib
import uuid

from ....db.models.asset import Asset
from ....db.models.asset_entry import AssetEntry
from ....utils import ASSETS_DIR, get_asset_hash_subpath


def svg_path_num(n: float) -> str:
    s = f"{float(n):.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def wall_lines_to_svg_bytes(walls: dict | None, grid_cells: dict) -> bytes | None:
    """SVG con <path> per segmento; stesso spazio di addDungeonToMap con wallPadding 0."""
    if not walls or not isinstance(walls, dict):
        return None
    lines = walls.get("lines")
    if not isinstance(lines, list) or len(lines) == 0:
        return None
    try:
        gw = float(grid_cells.get("width") or 20)
        gh = float(grid_cells.get("height") or 15)
    except (TypeError, ValueError):
        return None
    if gw <= 0 or gh <= 0:
        return None
    path_chunks: list[str] = []
    max_x, max_y = gw, gh
    for line in lines:
        if not isinstance(line, (list, tuple)) or len(line) != 2:
            continue
        a, b = line[0], line[1]
        if not isinstance(a, (list, tuple)) or len(a) != 2:
            continue
        if not isinstance(b, (list, tuple)) or len(b) != 2:
            continue
        try:
            x1, y1 = float(a[0]), float(a[1])
            x2, y2 = float(b[0]), float(b[1])
        except (TypeError, ValueError):
            continue
        max_x = max(max_x, x1, x2)
        max_y = max(max_y, y1, y2)
        path_chunks.append(
            f'<path d="M {svg_path_num(x1)} {svg_path_num(y1)} L {svg_path_num(x2)} {svg_path_num(y2)}" fill="none"/>'
        )
    if not path_chunks:
        return None
    svg_w = max(1.0, max_x)
    svg_h = max(1.0, max_y)
    inner = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_path_num(svg_w)}" height="{svg_path_num(svg_h)}" '
        f'viewBox="0 0 {svg_path_num(svg_w)} {svg_path_num(svg_h)}">\n'
        + "\n".join(path_chunks)
        + "\n</svg>\n"
    )
    return inner.encode("utf-8")


def save_walls_svg_asset(
    user,
    folder: AssetEntry,
    name_stem: str,
    walls: dict,
    grid_cells: dict,
) -> dict[str, int | str] | None:
    """Salva SVG muri in libreria; chiavi JSON wallsSvg* per il client Maps Gen."""
    svg_bytes = wall_lines_to_svg_bytes(walls, grid_cells)
    if not svg_bytes:
        return None
    h_svg = hashlib.sha1(svg_bytes).hexdigest()
    svg_disk = ASSETS_DIR / get_asset_hash_subpath(h_svg)
    if not svg_disk.exists():
        svg_disk.parent.mkdir(parents=True, exist_ok=True)
        svg_disk.write_bytes(svg_bytes)
    svg_asset, _ = Asset.get_or_create(
        file_hash=h_svg,
        defaults={"kind": "regular", "extension": "svg", "file_size": len(svg_bytes)},
    )
    walls_svg_name = f"{name_stem}_walls_{uuid.uuid4().hex[:6]}.svg"
    svg_entry = AssetEntry.create(name=walls_svg_name, asset=svg_asset, owner=user, parent=folder)
    walls_svg_url = f"/static/assets/{get_asset_hash_subpath(h_svg).as_posix()}"
    return {
        "wallsSvgEntryId": svg_entry.id,
        "wallsSvgAssetId": svg_asset.id,
        "wallsSvgUrl": walls_svg_url,
        "wallsSvgName": walls_svg_name,
    }
