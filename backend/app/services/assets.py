"""Asset creation with upload validation (magic bytes, size), thumbnails and safe naming."""
from __future__ import annotations

import io
import mimetypes
import re
from pathlib import PurePath
from typing import Any, BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Asset
from app.storage.local import StorageError, get_storage

Image.MAX_IMAGE_PIXELS = 80_000_000  # decompression-bomb guard (~80 MP)


class UploadRejected(ValueError):
    pass


# (magic prefix, kind, ext, mime)
_SIGNATURES: list[tuple[bytes, str, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image", "png", "image/png"),
    (b"\xff\xd8\xff", "image", "jpg", "image/jpeg"),
    (b"GIF87a", "image", "gif", "image/gif"),
    (b"GIF89a", "image", "gif", "image/gif"),
    (b"%PDF-", "document", "pdf", "application/pdf"),
    (b"ID3", "audio", "mp3", "audio/mpeg"),
    (b"\xff\xfb", "audio", "mp3", "audio/mpeg"),
    (b"\xff\xf3", "audio", "mp3", "audio/mpeg"),
    (b"OggS", "audio", "ogg", "audio/ogg"),
    (b"PK\x03\x04", "archive", "zip", "application/zip"),
]


def sniff(head: bytes, filename: str) -> tuple[str, str, str]:
    """Identify file type from content, not from the client-supplied name/MIME."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "webp", "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "wav", "audio/wav"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio", "m4a", "audio/mp4"
        return "video", "mp4", "video/mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "webm", "video/webm"
    for sig, kind, ext, mime in _SIGNATURES:
        if head.startswith(sig):
            return kind, ext, mime
    suffix = PurePath(filename).suffix.lower().lstrip(".")
    if suffix in ("txt", "md", "csv", "json"):
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as e:
            raise UploadRejected("text file is not valid UTF-8") from e
        return "document", suffix, mimetypes.types_map.get(f".{suffix}", "text/plain")
    raise UploadRejected("unsupported or unrecognized file type")


def safe_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name or "file"
    base = re.sub(r"[^\w.\- ]+", "_", base).strip(" .")[:120]
    return base or "file"


def _image_meta_and_thumb(data: bytes) -> tuple[int, int, str | None]:
    storage = get_storage()
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            thumb = im.copy()
            thumb.thumbnail((480, 480))
            if thumb.mode not in ("RGB", "RGBA"):
                thumb = thumb.convert("RGBA")
            buf = io.BytesIO()
            thumb.save(buf, "WEBP", quality=82)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as e:
        raise UploadRejected(f"image could not be decoded: {e}") from e
    return w, h, storage.save_bytes(buf.getvalue(), area="thumbs", ext="webp")


ALLOWED_UPLOAD_KINDS = {"image", "document", "audio", "video"}


def create_asset_from_upload(db: Session, stream: BinaryIO, filename: str, *, allowed: set[str] | None = None,
                             **fields: Any) -> Asset:
    settings = get_settings()
    head = stream.read(64)
    kind, ext, mime = sniff(head, filename)
    if kind not in (allowed or ALLOWED_UPLOAD_KINDS):
        raise UploadRejected(f"{kind} files are not accepted here")
    rest = _Prefixed(head, stream)
    try:
        key, size = get_storage().save_stream(rest, area="uploads", ext=ext,
                                              max_bytes=settings.max_upload_mb * 1024 * 1024)
    except StorageError as e:
        raise UploadRejected(str(e)) from e
    asset = Asset(kind=kind, source="upload", storage_key=key, filename=safe_filename(filename),
                  mime_type=mime, size_bytes=size, **fields)
    if kind == "image":
        try:
            asset.width, asset.height, asset.thumb_key = _image_meta_and_thumb(get_storage().read_bytes(key))
        except UploadRejected:
            get_storage().delete(key)
            raise
    db.add(asset)
    db.flush()
    return asset


def create_asset_from_bytes(db: Session, data: bytes, *, ext: str, source: str, filename: str | None = None,
                            area: str = "generated", **fields: Any) -> Asset:
    kind, _, mime = sniff(data[:64], filename or f"file.{ext}")
    key = get_storage().save_bytes(data, area=area, ext=ext)
    asset = Asset(kind=kind, source=source, storage_key=key, filename=safe_filename(filename or f"{source}.{ext}"),
                  mime_type=mime, size_bytes=len(data), **fields)
    if kind == "image":
        asset.width, asset.height, asset.thumb_key = _image_meta_and_thumb(data)
    db.add(asset)
    db.flush()
    return asset


def register_file_asset(db: Session, key: str, *, kind: str, mime: str, filename: str, source: str,
                        **fields: Any) -> Asset:
    """For files written directly into storage (e.g. FFmpeg output)."""
    p = get_storage().path(key)
    asset = Asset(kind=kind, source=source, storage_key=key, filename=safe_filename(filename), mime_type=mime,
                  size_bytes=p.stat().st_size, **fields)
    db.add(asset)
    db.flush()
    return asset


def load_image(asset: Asset) -> Image.Image:
    data = get_storage().read_bytes(asset.storage_key)
    im = Image.open(io.BytesIO(data))
    return ImageOps.exif_transpose(im)


def asset_url(asset_id: str | None) -> str | None:
    return f"/api/assets/{asset_id}/file" if asset_id else None


def thumb_url(asset: Asset | None) -> str | None:
    if asset is None:
        return None
    return f"/api/assets/{asset.id}/thumb" if asset.thumb_key else asset_url(asset.id)


class _Prefixed:
    """Stream wrapper that replays already-read header bytes."""

    def __init__(self, head: bytes, stream: BinaryIO) -> None:
        self._head, self._stream = head, stream

    def read(self, n: int = -1) -> bytes:
        if self._head:
            out, self._head = self._head, b""
            if n == -1:
                return out + self._stream.read()
            return out + self._stream.read(max(0, n - len(out)))
        return self._stream.read(n)
