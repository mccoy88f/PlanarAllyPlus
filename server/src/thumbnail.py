import io
import warnings
from pathlib import Path

import fitz
from PIL import Image

from .storage import get_storage
from .utils import ASSETS_DIR, THUMBNAILS_DIR, get_asset_hash_subpath

warnings.simplefilter("ignore", Image.DecompressionBombWarning)


def _pdf_first_page_to_image(pdf_path: Path, max_width: int = 400) -> bytes | None:
    """Extract first page of PDF as PNG bytes for thumbnail generation."""
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            doc.close()
            return None
        page = doc.load_page(0)
        mat = fitz.Matrix(max_width / page.rect.width, max_width / page.rect.width)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes
    except Exception:
        return None


def create_thumbnail_from_bytes(input_bytes, max_size=(200, 200)):
    image = Image.open(io.BytesIO(input_bytes))

    # Handle palette mode with potential transparency
    if image.mode == "P":
        image = image.convert("RGBA")

    # Calculate aspect ratio preserving dimensions
    original_width, original_height = image.size
    ratio = min(max_size[0] / original_width, max_size[1] / original_height)
    new_size = (int(original_width * ratio), int(original_height * ratio))

    # Resize using LANCZOS
    image = image.resize(new_size, Image.Resampling.LANCZOS)

    # Generate both formats
    jpeg_output = io.BytesIO()
    webp_output = io.BytesIO()

    # For JPEG (fallback format), we need RGB
    if image.mode in ("RGBA", "LA"):
        jpeg_image = Image.new("RGB", image.size, (255, 255, 255))
        jpeg_image.paste(image, mask=image.split()[-1])
        jpeg_image.save(jpeg_output, format="JPEG", quality=85, optimize=True)
    else:
        image.save(jpeg_output, format="JPEG", quality=85, optimize=True)

    # For WebP, we can keep transparency
    image.save(
        webp_output,
        format="WebP",
        quality=80,
        method=4,
        lossless=False,
    )

    return {"webp": webp_output.getvalue(), "jpeg": jpeg_output.getvalue()}


async def generate_thumbnail_for_asset(file_hash: str) -> None:
    from .db.models.asset import Asset
    storage = get_storage()

    if not await storage.exists(file_hash):
        return

    try:
        data = await storage.retrieve(file_hash)
        asset = Asset.get_or_none(file_hash=file_hash)
        if asset and asset.extension and asset.extension.lower() == "pdf":
            # For PDF we need a temporary file for fitz
            import tempfile
            from pathlib import Path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            try:
                first_page_bytes = _pdf_first_page_to_image(tmp_path)
                if first_page_bytes:
                    thumbnails = create_thumbnail_from_bytes(first_page_bytes, max_size=(300, 420))
                else:
                    thumbnails = create_thumbnail_from_bytes(data)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        else:
            thumbnails = create_thumbnail_from_bytes(data)

        if thumbnails is None:
            return
        for fmt, thumb_data in thumbnails.items():
            await storage.store(file_hash, thumb_data, suffix=f".thumb.{fmt}")
    except Image.DecompressionBombError:
        print(f"Thumbnail generation failed for {file_hash}: The asset is too large")
    except Exception as e:
        print(f"Thumbnail generation failed for {file_hash}: {e}")


def generate_thumbnail_for_asset_sync(file_hash: str) -> None:
    """Sync version for use in thread-executor contexts (save migrations)."""
    from .db.models.asset import Asset
    storage = get_storage()

    if not storage.exists_sync(file_hash):
        return

    try:
        data = storage.retrieve_sync(file_hash)
        asset = Asset.get_or_none(file_hash=file_hash)
        if asset and asset.extension and asset.extension.lower() == "pdf":
            import tempfile
            from pathlib import Path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            try:
                first_page_bytes = _pdf_first_page_to_image(tmp_path)
                if first_page_bytes:
                    thumbnails = create_thumbnail_from_bytes(first_page_bytes, max_size=(300, 420))
                else:
                    thumbnails = create_thumbnail_from_bytes(data)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        else:
            thumbnails = create_thumbnail_from_bytes(data)

        if thumbnails is None:
            return
        for fmt, thumb_data in thumbnails.items():
            storage.store_sync(file_hash, thumb_data, suffix=f".thumb.{fmt}")
    except Image.DecompressionBombError:
        print()
        print(f"Thumbnail generation failed for {file_hash}: The asset is too large")
    except Exception as e:
        print()
        print(f"Thumbnail generation failed for {file_hash}: {e}")
