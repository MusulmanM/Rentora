"""Safe handling of user uploads: random file names and content-based type checks."""
import posixpath
import uuid

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "AVIF": "avif"}
MAX_IMAGE_PIXELS = 40_000_000


SAFE_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif", "avif")
SAFE_CHAT_EXTENSIONS = SAFE_IMAGE_EXTENSIONS + (
    "mp4", "m4v", "mov", "webm", "mkv", "3gp", "ogg", "oga", "opus", "mp3", "wav", "m4a", "aac",
)


@deconstructible
class randomized_upload_path:
    """upload_to callable: <prefix>/<YYYY>/<MM>/<uuid>.<ext>, never trusting the uploaded name.

    A random name stops users from choosing paths, and the extension allowlist stops names like
    ``evil.html`` that the web server would serve with a dangerous content type.
    """

    def __init__(self, prefix, allowed=SAFE_IMAGE_EXTENSIONS, fallback="jpg"):
        self.prefix = prefix
        self.allowed = tuple(allowed)
        self.fallback = fallback

    def __call__(self, instance, filename):
        extension = posixpath.splitext(filename)[1].lower().lstrip(".")
        if extension not in self.allowed:
            extension = self.fallback
        now = timezone.now()
        return f"{self.prefix}/{now:%Y/%m}/{uuid.uuid4().hex}.{extension}"

    def __eq__(self, other):
        return isinstance(other, randomized_upload_path) and (other.prefix, other.allowed, other.fallback) == (
            self.prefix, self.allowed, self.fallback,
        )


def validate_image_upload(uploaded, max_bytes=10 * 1024 * 1024, label="Rasm"):
    """Verify a real raster image and rename it with the extension of its actual format."""
    if uploaded.size > max_bytes:
        raise ValidationError(f"{label} hajmi {max_bytes // (1024 * 1024)} MB dan oshmasligi kerak.")
    try:
        with Image.open(uploaded) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValidationError("Rasm o'lchami juda katta.")
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError("Faqat haqiqiy rasm fayllarini yuklang.")
    finally:
        uploaded.seek(0)
    extension = IMAGE_EXTENSIONS.get(image_format)
    if not extension:
        raise ValidationError("Faqat JPG, PNG, WEBP, GIF yoki AVIF rasm yuklang.")
    uploaded.name = f"upload.{extension}"
    return uploaded


# Video/audio containers recognised by their leading bytes.
def _sniff_media(head):
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return {"mp4", "m4v", "mov", "m4a", "3gp"}
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return {"webm", "mkv"}
    if head.startswith(b"OggS"):
        return {"ogg", "oga", "opus"}
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return {"mp3"}
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return {"wav"}
    if head[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return {"aac"}
    return set()


AUDIO_EXTENSIONS = {"ogg", "oga", "opus", "mp3", "wav", "m4a", "aac", "webm"}
VIDEO_EXTENSIONS = {"mp4", "m4v", "mov", "webm", "mkv", "3gp"}


def validate_media_upload(uploaded, kind_hint=""):
    """Return "audio" or "video" for a real audio/video file, otherwise raise ValidationError."""
    extension = posixpath.splitext(uploaded.name or "")[1].lower().lstrip(".")
    head = uploaded.read(16)
    uploaded.seek(0)
    if extension not in _sniff_media(head):
        raise ValidationError("Faqat rasm, video yoki audio fayl yuborish mumkin.")
    if extension == "webm":
        kind = "audio" if kind_hint == "audio" else "video"
    elif extension in VIDEO_EXTENSIONS and not (kind_hint == "audio" and extension in AUDIO_EXTENSIONS):
        kind = "video"
    elif extension in AUDIO_EXTENSIONS:
        kind = "audio"
    else:
        raise ValidationError("Faqat rasm, video yoki audio fayl yuborish mumkin.")
    uploaded.name = f"upload.{extension}"
    return kind
