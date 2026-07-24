"""Avatar image upload and validation.

Provides utilities for detecting image types from raw bytes, validating
avatar image constraints (size, format), and uploading to an external
image host (e.g. Catbox).
"""

from __future__ import annotations

import httpx

from core import config

MAX_AVATAR_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"jpeg", "png", "gif", "webp"}


class AvatarUploadError(ValueError):
    """Raised when avatar validation or upload fails."""


def detect_image_type(content: bytes) -> str | None:
    """Detect image format from magic bytes.

    Args:
        content: Raw image bytes.

    Returns:
        One of 'jpeg', 'png', 'gif', 'webp', or None if unrecognised.
    """
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def validate_image_bytes(content: bytes) -> str:
    """Validate avatar image size and type.

    Args:
        content: Raw image bytes.

    Returns:
        The detected image type string.

    Raises:
        AvatarUploadError: If the image is empty, too large, or an
            unsupported format.
    """
    if not content:
        raise AvatarUploadError("Image file is empty")
    if len(content) > MAX_AVATAR_BYTES:
        raise AvatarUploadError("Image must be at most 2 MB")
    image_type = detect_image_type(content)
    if image_type not in ALLOWED_IMAGE_TYPES:
        raise AvatarUploadError("Image must be JPEG, PNG, GIF, or WebP")
    return image_type


def extension_for_type(image_type: str) -> str:
    """Map an image type string to a file extension.

    Args:
        image_type: One of 'jpeg', 'png', 'gif', 'webp'.

    Returns:
        The corresponding file extension (e.g. 'jpg' for 'jpeg').
    """
    return {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}.get(image_type, "img")


def upload_image_to_external_host(content: bytes, filename: str, content_type: str) -> str:
    """Send image bytes to an external host and return the public URL."""
    if not config.AVATAR_UPLOAD_ENABLED:
        raise AvatarUploadError("Image upload is disabled. Paste an image URL instead.")

    upload_url = config.AVATAR_UPLOAD_URL.strip()
    if not upload_url:
        raise AvatarUploadError("Image upload is not configured. Paste an image URL instead.")

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            upload_url,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (filename, content, content_type)},
        )
        response.raise_for_status()
        url = response.text.strip()
        if not url.startswith(("http://", "https://")):
            raise AvatarUploadError("Upload host did not return a valid URL")
        return url
