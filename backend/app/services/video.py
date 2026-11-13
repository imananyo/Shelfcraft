"""Slideshow-style product video composition with FFmpeg (non-generative).

Each scene: an image (cover-fit to the output frame) with optional Ken Burns zoom and a text
overlay rendered by Pillow (so no fragile drawtext escaping). Scenes are joined with xfade
transitions; optional user music is trimmed and faded. FFmpeg is invoked with an argument list
(never a shell string), so user text cannot inject commands.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.db.models import Asset
from app.imaging.fonts import get_font
from app.imaging.ops import cover_resize
from app.services.assets import load_image
from app.storage.local import get_storage

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
TRANSITIONS = {"fade", "slideleft", "slideright", "slideup", "wipeleft", "circleopen", "dissolve", "smoothleft", "none"}
FPS = 30


class VideoError(RuntimeError):
    pass


def find_tool(name: str) -> str | None:
    """Locate ffmpeg/ffprobe: explicit setting → PATH → winget's links folder (PATH may be stale)."""
    import os

    from app.config import get_settings

    explicit = get_settings().ffmpeg_dir
    candidates = [Path(explicit) / f"{name}.exe"] if explicit else []
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    candidates.append(Path(local) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe")
    candidates += list((Path(local) / "Microsoft" / "WinGet" / "Packages").glob(f"Gyan.FFmpeg*/**/bin/{name}.exe"))
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def ffmpeg_bin() -> str:
    exe = find_tool("ffmpeg")
    if not exe:
        raise VideoError("FFmpeg is not installed or not on PATH")
    return exe


def _overlay(frame: Image.Image, text: str, position: str, style: dict[str, Any]) -> Image.Image:
    if not text.strip():
        return frame
    W, H = frame.size
    out = frame.convert("RGBA")
    size = int(style.get("font_size") or (H * 0.055))
    font = get_font(style.get("font_family"), size, "bold")
    d = ImageDraw.Draw(out)
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=font) > W * 0.82 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    lh = size * 1.25
    block_h = lh * len(lines) + size * 0.8
    y0 = {"top": H * 0.07, "center": (H - block_h) / 2}.get(position, H - block_h - H * 0.08)
    band = Image.new("RGBA", (W, int(block_h)), (0, 0, 0, int(255 * float(style.get("band_opacity", 0.45)))))
    out.alpha_composite(band, (0, int(y0)))
    color = style.get("color", "#ffffff")
    for i, line in enumerate(lines):
        lw = d.textlength(line, font=font)
        d.text(((W - lw) / 2, y0 + size * 0.4 + i * lh), line, font=font, fill=color)
    return out.convert("RGB")


def render_video(scenes: list[dict[str, Any]], *, aspect: str, transition: str, transition_s: float,
                 music: Asset | None, assets: dict[str, Asset], text_style: dict[str, Any],
                 progress: Any = None, voice_path: Path | None = None) -> tuple[str, float]:
    """Render scenes to an MP4 in storage. Returns (storage key, duration seconds)."""
    if not scenes:
        raise VideoError("add at least one scene")
    if len(scenes) > 30:
        raise VideoError("at most 30 scenes")
    W, H = ASPECTS.get(aspect, ASPECTS["16:9"])
    transition = transition if transition in TRANSITIONS else "fade"
    tdur = 0.0 if transition == "none" else max(0.2, min(1.5, float(transition_s)))
    exe = ffmpeg_bin()
    tick = progress or (lambda *_a, **_k: None)
    key, out_path = get_storage().new_path("videos", "mp4")
    with tempfile.TemporaryDirectory(prefix="shelfcraft-video-") as tmp:
        tmpd = Path(tmp)
        clips: list[tuple[Path, float]] = []
        for i, sc in enumerate(scenes):
            dur = max(1.0, min(15.0, float(sc.get("duration", 3))))
            a = assets.get(sc.get("asset_id", ""))
            if a is None:
                raise VideoError(f"scene {i + 1}: image not found")
            # Over-size frame for Ken Burns headroom.
            frame = cover_resize(load_image(a).convert("RGB"), int(W * 1.12), int(H * 1.12))
            frame = _overlay(frame, sc.get("text", ""), sc.get("text_position", "bottom"), text_style)
            img_path = tmpd / f"scene_{i}.png"
            frame.save(img_path)
            clip = tmpd / f"clip_{i}.mp4"
            frames = int(dur * FPS)
            motion = sc.get("motion", "zoom_in")
            if motion == "zoom_out":
                z = f"zoom='if(eq(on,0),1.10,max(1.0,zoom-0.10/{frames}))'"
            elif motion == "none":
                z = "zoom='1.0'"
            else:
                z = f"zoom='min(1.10,1.0+0.10*on/{frames})'"
            vf = (f"{'zoompan=' + z + ':x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)'}:d={frames}:s={W}x{H}:fps={FPS},"
                  "format=yuv420p")
            _run([exe, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img_path), "-t", f"{dur:.3f}",
                  "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-pix_fmt", "yuv420p", str(clip)])
            clips.append((clip, dur))
            tick(0.1 + 0.6 * (i + 1) / len(scenes), f"Rendered scene {i + 1}/{len(scenes)}")
        # Join with transitions.
        joined = tmpd / "joined.mp4"
        if len(clips) == 1 or tdur == 0:
            lst = tmpd / "list.txt"
            lst.write_text("".join(f"file '{c.as_posix()}'\n" for c, _ in clips), encoding="utf-8")
            _run([exe, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
            total = sum(d for _, d in clips)
        else:
            args = [exe, "-y", "-loglevel", "error"]
            for c, _ in clips:
                args += ["-i", str(c)]
            parts, prev, offset = [], "[0:v]", 0.0
            for i in range(1, len(clips)):
                offset += clips[i - 1][1] - tdur
                label = f"[v{i}]"
                parts.append(f"{prev}[{i}:v]xfade=transition={transition}:duration={tdur:.2f}:offset={offset:.3f}{label}")
                prev = label
            args += ["-filter_complex", ";".join(parts), "-map", prev, "-c:v", "libx264", "-preset", "veryfast",
                     "-crf", "20", "-pix_fmt", "yuv420p", str(joined)]
            _run(args)
            total = sum(d for _, d in clips) - tdur * (len(clips) - 1)
        tick(0.85, "Mixing audio" if (music or voice_path) else "Finalizing")
        if voice_path is not None:
            # Voiceover at full level; optional music ducked underneath.
            args = [exe, "-y", "-loglevel", "error", "-i", str(joined), "-i", str(voice_path)]
            if music:
                args += ["-i", str(get_storage().path(music.storage_key))]
                fc = (f"[1:a]apad,atrim=0:{total:.3f}[v];[2:a]atrim=0:{total:.3f},volume=0.18,"
                      f"afade=t=out:st={max(0.0, total - 1.5):.3f}:d=1.5[m];[v][m]amix=inputs=2:duration=first[a]")
            else:
                fc = f"[1:a]apad,atrim=0:{total:.3f}[a]"
            _run(args + ["-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                         "-movflags", "+faststart", str(out_path)])
        elif music:
            mpath = get_storage().path(music.storage_key)
            fade_start = max(0.0, total - 1.5)
            _run([exe, "-y", "-loglevel", "error", "-i", str(joined), "-i", str(mpath), "-filter_complex",
                  f"[1:a]atrim=0:{total:.3f},afade=t=in:st=0:d=0.8,afade=t=out:st={fade_start:.3f}:d=1.5[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                  "-movflags", "+faststart", str(out_path)])
        else:
            _run([exe, "-y", "-loglevel", "error", "-i", str(joined), "-c", "copy", "-movflags", "+faststart",
                  str(out_path)])
    return key, round(total, 2)


def _run(args: list[str]) -> None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=900, check=False)  # noqa: S603
    except subprocess.TimeoutExpired as e:
        raise VideoError("FFmpeg timed out") from e
    if proc.returncode != 0:
        raise VideoError(f"FFmpeg failed: {proc.stderr.strip()[-600:]}")


def probe_duration(path: Path) -> float | None:
    exe = find_tool("ffprobe")
    if not exe:
        return None
    proc = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],  # noqa: S603
                          capture_output=True, text=True, timeout=30, check=False)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None
