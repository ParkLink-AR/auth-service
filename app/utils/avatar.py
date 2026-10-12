from __future__ import annotations

import io
import uuid
from uuid import UUID

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.exceptions.handler import ServiceException
from app.utils import storage

MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
AVATAR_MAX_DIMENSION = 512  # re-encoded, longest side capped at this many px


async def save_avatar(user_id: UUID, file: UploadFile) -> str:
    """Validates, re-encodes and stores a profile picture, returning its
    (relative, /static-mounted) URL. Raises ServiceException on anything
    that doesn't check out."""

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="Unsupported image format. Use JPEG, PNG or WEBP.",
        )

    # Read in bounded chunks instead of `await file.read()` -- the
    # Content-Length header is caller-supplied and can't be trusted, so this
    # is the actual enforcement of the size limit, not just a fast-fail.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AVATAR_SIZE_BYTES:
            raise ServiceException(
                status_code=400,
                title="Bad Request",
                detail="Image is too large (max 5 MB).",
            )
        chunks.append(chunk)
    raw = b"".join(chunks)

    # The real format check: Pillow has to actually be able to decode this
    # as an image, regardless of what the client claimed in content_type/the
    # filename. Re-encoding (instead of storing the uploaded bytes verbatim)
    # also strips EXIF/any other embedded payload before it's ever written
    # to disk or served back to other users.
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
    except (UnidentifiedImageError, OSError):
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="The uploaded file is not a valid image.",
        )
    # Upright first: a phone photo's rotation lives in its EXIF orientation tag, which the
    # re-encode below drops -- without this a portrait selfie could come out sideways.
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    image.thumbnail((AVATAR_MAX_DIMENSION, AVATAR_MAX_DIMENSION))

    filename = f"{user_id}-{uuid.uuid4().hex[:8]}.jpg"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)

    return storage.upload_bytes(f"avatars/{filename}", buffer.getvalue(), "image/jpeg")


def delete_avatar_file(avatar_url: str | None) -> None:
    """Best-effort cleanup of the previous avatar file when it's replaced."""
    storage.delete_object(avatar_url)
