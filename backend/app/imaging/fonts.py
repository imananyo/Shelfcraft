"""Font resolution for server-side rendering.

Order: data/fonts cache → download from the google/fonts GitHub repo (OFL/Apache fonts) →
system fonts (Windows/macOS/Linux) → Pillow's built-in scalable default. Downloads are best-effort and
cached; rendering never fails because of a missing font.
"""
from __future__ import annotations

import logging
import re
import threading
from functools import lru_cache
from pathlib import Path

import httpx
from PIL import ImageFont

from app.config import get_settings

log = logging.getLogger("shelfcraft.fonts")
_lock = threading.Lock()
_failed: set[str] = set()

# System font folders for Windows, macOS and Linux (searched recursively, first match wins).
SYSTEM_FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts",
    Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".local" / "share" / "fonts",
    Path.home() / ".fonts",
]
SYSTEM_FALLBACKS = {
    "regular": ["segoeui.ttf", "arial.ttf", "Arial.ttf", "calibri.ttf", "DejaVuSans.ttf",
                "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "FreeSans.ttf"],
    "bold": ["segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf",
             "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "FreeSansBold.ttf"],
    "italic": ["segoeuii.ttf", "ariali.ttf", "Arial Italic.ttf", "DejaVuSans-Oblique.ttf",
               "LiberationSans-Italic.ttf", "NotoSans-Italic.ttf", "FreeSansOblique.ttf"],
    "bold italic": ["segoeuiz.ttf", "arialbi.ttf", "Arial Bold Italic.ttf", "DejaVuSans-BoldOblique.ttf",
                    "LiberationSans-BoldItalic.ttf", "NotoSans-BoldItalic.ttf", "FreeSansBoldOblique.ttf"],
}


@lru_cache(maxsize=8)
def _system_font(key: str) -> Path | None:
    """Find the first available system fallback font for a style on any OS."""
    dirs = [d for d in SYSTEM_FONT_DIRS if d.is_dir()]
    for name in SYSTEM_FALLBACKS[key]:
        for d in dirs:
            if (d / name).is_file():
                return d / name
        for d in dirs:  # Linux distros nest fonts in sub-folders (e.g. truetype/dejavu)
            hit = next(d.rglob(name), None)
            if hit:
                return hit
    return None


def fonts_dir() -> Path:
    d = get_settings().data_dir / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]", "", family.lower())


def _download_family(family: str) -> list[Path]:
    """Fetch TTFs for a Google Fonts family from github.com/google/fonts (licenses: OFL/Apache)."""
    slug = _slug(family)
    if not slug or slug in _failed:
        return []
    out: list[Path] = []
    for lic in ("ofl", "apache", "ufl"):
        try:
            r = httpx.get(f"https://api.github.com/repos/google/fonts/contents/{lic}/{slug}", timeout=10.0,
                          headers={"Accept": "application/vnd.github+json"})
        except httpx.HTTPError:
            break
        if r.status_code != 200:
            continue
        for item in r.json():
            name = item.get("name", "")
            if name.endswith(".ttf") and item.get("download_url"):
                dest = fonts_dir() / f"{slug}__{name}"
                if not dest.exists():
                    try:
                        data = httpx.get(item["download_url"], timeout=30.0, follow_redirects=True).content
                        dest.write_bytes(data)
                    except httpx.HTTPError:
                        continue
                out.append(dest)
        if out:
            return out
    _failed.add(slug)
    return out


def _family_files(family: str) -> list[Path]:
    slug = _slug(family)
    files = sorted(fonts_dir().glob(f"{slug}__*.ttf"))
    if files:
        return files
    with _lock:
        files = sorted(fonts_dir().glob(f"{slug}__*.ttf"))
        return files or _download_family(family)


def _pick(files: list[Path], style: str) -> tuple[Path, str | None] | None:
    """Return (file, variation-name) for a style from static or variable font files."""
    want_bold, want_italic = "bold" in style, "italic" in style
    statics = [f for f in files if "[" not in f.name]
    variables = [f for f in files if "[" in f.name]
    for f in statics:
        n = f.name.lower()
        is_bold = "bold" in n and "semibold" not in n and "extrabold" not in n
        is_italic = "italic" in n
        if is_bold == want_bold and is_italic == want_italic and ("regular" in n or is_bold or is_italic):
            return f, None
    for f in variables:
        if ("italic" in f.name.lower()) == want_italic:
            return f, ("Bold" if want_bold else "Regular")
    if variables:
        return variables[0], ("Bold" if want_bold else "Regular")
    return (statics[0], None) if statics else None


@lru_cache(maxsize=256)
def get_font(family: str | None, size: int, style: str = "normal") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(4, int(size))
    style = (style or "normal").lower()
    key = "bold italic" if ("bold" in style and "italic" in style) else ("bold" if "bold" in style else
                                                                          ("italic" if "italic" in style else "regular"))
    if family:
        files = _family_files(family)
        picked = _pick(files, style) if files else None
        if picked:
            path, variation = picked
            try:
                font = ImageFont.truetype(str(path), size)
                if variation:
                    try:
                        font.set_variation_by_name(variation)
                    except (OSError, ValueError):
                        pass
                return font
            except OSError:
                log.warning("could not load font file %s", path)
    p = _system_font(key)
    if p:
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            log.warning("could not load system font %s", p)
    return ImageFont.load_default(size)
