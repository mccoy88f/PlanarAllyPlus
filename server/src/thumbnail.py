import io
import warnings
from pathlib import Path

import fitz
from PIL import Image

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


def generate_thumbnail_for_asset(name: str, file_hash: str) -> None:
    full_hash_name = get_asset_hash_subpath(file_hash)
    asset_path = ASSETS_DIR / full_hash_name

    if not asset_path.exists():
        return

    try:
        if name.lower().endswith(".pdf"):
            first_page_bytes = _pdf_first_page_to_image(asset_path)
            if first_page_bytes is None:
                return
            thumbnail = create_thumbnail_from_bytes(first_page_bytes, max_size=(300, 420))
        else:
            with open(asset_path, "rb") as f:
                thumbnail = create_thumbnail_from_bytes(f.read())
        if thumbnail is None:
            return
        for format, data in thumbnail.items():
            path = THUMBNAILS_DIR / Path(f"{full_hash_name}.thumb.{format}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
    except Image.DecompressionBombError:
        print()
        print(f"Thumbnail generation failed for {name}: The asset is too large")
    except Exception as e:
        print()
        print(f"Thumbnail generation failed for {name}: {e}")
