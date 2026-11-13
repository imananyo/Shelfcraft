"""Storage abstraction with a local-filesystem backend.

Keys are relative POSIX paths like ``generated/2026/11/<uuid>.png``. Every key is resolved
and verified to stay inside the media root, so user-influenced values can never escape it
(path traversal protection). A cloud backend can implement the same Protocol later.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Protocol

from app.config import get_settings


class StorageError(ValueError):
    pass


class StorageBackend(Protocol):
    def save_bytes(self, data: bytes, *, area: str, ext: str) -> str: ...
    def save_stream(self, stream: BinaryIO, *, area: str, ext: str, max_bytes: int) -> tuple[str, int]: ...
    def path(self, key: str) -> Path: ...
    def read_bytes(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


ALLOWED_AREAS = {"uploads", "generated", "edited", "exports", "videos", "thumbs", "tmp", "system"}
SAFE_EXT = {
    "png", "jpg", "jpeg", "webp", "gif", "mp4", "webm", "mp3", "wav", "m4a", "ogg",
    "pdf", "txt", "md", "json", "csv", "zip",
}


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_settings().media_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _new_key(self, area: str, ext: str) -> str:
        if area not in ALLOWED_AREAS:
            raise StorageError(f"unknown storage area: {area}")
        ext = ext.lower().lstrip(".")
        if ext not in SAFE_EXT:
            raise StorageError(f"file extension not allowed: {ext}")
        now = datetime.now(timezone.utc)
        return f"{area}/{now:%Y/%m}/{uuid.uuid4().hex}.{ext}"

    def path(self, key: str) -> Path:
        if not key or "\x00" in key or key.startswith(("/", "\\")) or ":" in key:
            raise StorageError("invalid storage key")
        p = (self.root / key).resolve()
        if p != self.root and self.root not in p.parents:
            raise StorageError("storage key escapes media root")
        return p

    def save_bytes(self, data: bytes, *, area: str, ext: str) -> str:
        key = self._new_key(area, ext)
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomic on same volume
        return key

    def save_stream(self, stream: BinaryIO, *, area: str, ext: str, max_bytes: int) -> tuple[str, int]:
        key = self._new_key(area, ext)
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        total = 0
        try:
            with tmp.open("wb") as out:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise StorageError(f"file exceeds {max_bytes // (1024 * 1024)} MB limit")
                    out.write(chunk)
            tmp.replace(p)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return key, total

    def new_path(self, area: str, ext: str) -> tuple[str, Path]:
        """Reserve a key and return its path (for tools like FFmpeg that write files)."""
        key = self._new_key(area, ext)
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        return key, p

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self.path(key).is_file()
        except StorageError:
            return False

    def delete(self, key: str) -> None:
        p = self.path(key)
        if p.is_file():
            p.unlink()

    def usage_bytes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for area in ALLOWED_AREAS:
            d = self.root / area
            out[area] = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.exists() else 0
        return out

    def clear_tmp(self) -> None:
        shutil.rmtree(self.root / "tmp", ignore_errors=True)


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage


def reset_storage(root: Path | None = None) -> LocalStorage:
    global _storage
    _storage = LocalStorage(root)
    return _storage
