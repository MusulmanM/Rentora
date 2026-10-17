"""Small WebP copies of listing photos for cards (home page, similar listings, dashboards).

Cards are ~400px wide, so sending the full photo wastes bandwidth. A 640px WebP is made next to
the original (media/thumbs/...) when a photo is uploaded; `manage.py make_thumbnails` fills in
photos that existed before. Without a thumbnail the original photo is used.
"""
import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

THUMB_WIDTH = 640
THUMB_QUALITY = 72


def thumb_name(name):
    base, _ = os.path.splitext(name)
    return f"thumbs/{base}.webp"


def make_thumbnail(field_file):
    """Create the thumbnail if it is missing. Returns its storage name, or "" on failure."""
    if not field_file:
        return ""
    storage, target = field_file.storage, thumb_name(field_file.name)
    if storage.exists(target):
        return target
    try:
        with field_file.open("rb") as handle, Image.open(handle) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            if image.width > THUMB_WIDTH:
                image = image.resize((THUMB_WIDTH, round(image.height * THUMB_WIDTH / image.width)), Image.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, "WEBP", quality=THUMB_QUALITY, method=6)
    except (OSError, ValueError) as exc:
        logger.warning("Thumbnail for %s could not be made: %s", field_file.name, type(exc).__name__)
        return ""
    return storage.save(target, ContentFile(buffer.getvalue()))


def thumbnail_url(field_file):
    if not field_file:
        return ""
    target = thumb_name(field_file.name)
    return field_file.storage.url(target) if field_file.storage.exists(target) else field_file.url
