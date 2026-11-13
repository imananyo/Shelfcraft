"""Image → editable layers (OCR + cut-out + inpainted background), 360° spin from photos, offline voiceover."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import threading
import uuid
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.imaging import inpaint, ops

log = logging.getLogger("shelfcraft.media")
_ocr = None
_ocr_lock = threading.Lock()


# ---------------------------------------------------------------- OCR
def ocr(im: Image.Image) -> list[dict[str, Any]]:
    """Return [{text, box:(x,y,w,h), score}] using RapidOCR (local ONNX, Apache-2.0)."""
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            _ocr = RapidOCR()
        result, _ = _ocr(np.asarray(im.convert("RGB")))
    out = []
    for pts, text, score in result or []:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        if float(score) < 0.5 or not str(text).strip():
            continue
        out.append({"text": str(text).strip(), "box": (int(x0), int(y0), int(x1 - x0), int(y1 - y0)), "score": round(float(score), 3)})
    return out


def _text_color(rgb: np.ndarray, box: tuple[int, int, int, int]) -> str:
    x, y, w, h = box
    patch = rgb[max(0, y):y + h, max(0, x):x + w].reshape(-1, 3).astype(np.float32)
    if not len(patch):
        return "#111111"
    lum = patch @ np.array([0.299, 0.587, 0.114], np.float32)
    bg_lum = np.median(lum)
    # Text pixels are the ones furthest from the median (background) luminance.
    far = patch[np.abs(lum - bg_lum) > np.percentile(np.abs(lum - bg_lum), 80)]
    r, g, b = (np.median(far, axis=0) if len(far) else patch.mean(axis=0)).astype(int)
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def decompose_to_layers(im: Image.Image, *, max_side: int = 2000) -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any]]:
    """Split a flat image into background / subject / text layers. Returns (doc, images{name: png}, report)."""
    im = im.convert("RGB")
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    W, H = im.size
    rgb = np.asarray(im)
    texts = ocr(im)
    text_mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(text_mask)
    for t in texts:
        x, y, w, h = t["box"]
        pad = max(3, h // 6)
        d.rectangle((x - pad, y - pad, x + w + pad, y + h + pad), fill=255)
    # Subject: salient object cut-out, with text areas removed so text isn't duplicated in the subject layer.
    cut = ops.remove_background(im)
    alpha = np.asarray(cut.getchannel("A")).astype(np.uint8)
    alpha = np.where(np.asarray(text_mask) > 0, 0, alpha).astype(np.uint8)
    subject_area = float((alpha > 128).mean())
    has_subject = 0.01 < subject_area < 0.92
    remove = np.asarray(text_mask).copy()
    if has_subject:
        remove = np.maximum(remove, cv2.dilate((alpha > 64).astype(np.uint8) * 255, np.ones((11, 11), np.uint8)))
    mask = Image.fromarray(remove)
    if mask.getbbox():
        try:
            bg = inpaint.inpaint_lama(im, mask)
            bg_engine = "LaMa"
        except Exception:  # noqa: BLE001
            bg = inpaint.inpaint_opencv(im, mask)
            bg_engine = "OpenCV (non-AI)"
    else:
        bg, bg_engine = im, "none"
    images: dict[str, bytes] = {"background": ops.to_png(bg)}
    layers: list[dict[str, Any]] = [{"id": uuid.uuid4().hex[:12], "type": "image", "name": "Background", "x": 0, "y": 0, "width": W,
                                      "height": H, "rotation": 0, "opacity": 1, "locked": True, "visible": True, "assetId": "{{background}}",
                                      "fit": "fill"}]
    if has_subject:
        subj = cut.copy()
        subj.putalpha(Image.fromarray(alpha))
        bbox = subj.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        if bbox:
            images["subject"] = ops.to_png(subj.crop(bbox))
            layers.append({"id": uuid.uuid4().hex[:12], "type": "image", "name": "Subject", "x": bbox[0], "y": bbox[1],
                           "width": bbox[2] - bbox[0], "height": bbox[3] - bbox[1], "rotation": 0, "opacity": 1, "locked": False,
                           "visible": True, "assetId": "{{subject}}", "fit": "fill"})
    for t in texts:
        x, y, w, h = t["box"]
        layers.append({"id": uuid.uuid4().hex[:12], "type": "text", "name": t["text"][:40], "x": x, "y": y, "width": max(w + 8, 20),
                       "height": h, "rotation": 0, "opacity": 1, "locked": False, "visible": True, "text": t["text"],
                       "fontFamily": "Inter", "fontSize": max(8, int(h * 0.82)), "fontStyle": "bold" if h > H * 0.05 else "normal",
                       "fill": _text_color(rgb, t["box"]), "align": "left", "lineHeight": 1.0, "letterSpacing": 0})
    doc = {"width": W, "height": H, "background": "#ffffff", "layers": layers}
    report = {"text_layers": len(texts), "subject": has_subject, "background_engine": bg_engine,
              "note": "Fonts are approximated (Inter). Check text and font choices after splitting."}
    return doc, images, report


# ---------------------------------------------------------------- 360° spin from photos
def spin_frames(images: list[Image.Image], size: int = 1080, *, white: bool = True, tween: int = 3) -> list[Image.Image]:
    """Normalize angle photos to the same framing and add cross-fade tweens for a smooth turntable."""
    frames: list[Image.Image] = []
    norm = []
    for im in images:
        if white:
            cut = ops.remove_background(im)
            norm.append(ops.white_background(cut, size=size, fill_ratio=0.8).convert("RGB"))
        else:
            norm.append(ops.cover_resize(im.convert("RGB"), size, size))
    for i, a in enumerate(norm):
        b = norm[(i + 1) % len(norm)]
        frames.append(a)
        for k in range(1, tween + 1):
            frames.append(Image.blend(a, b, k / (tween + 1)))
    return frames


def encode_frames(frames: list[Image.Image], out_path: Path, *, fps: int = 24, loops: int = 3) -> float:
    from app.services.video import ffmpeg_bin

    with tempfile.TemporaryDirectory(prefix="shelfcraft-spin-") as tmp:
        n = 0
        for _ in range(loops):
            for f in frames:
                f.save(Path(tmp) / f"f{n:05d}.png")
                n += 1
        proc = subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(Path(tmp) / "f%05d.png"),
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(out_path)],  # noqa: S603
                              capture_output=True, text=True, timeout=600, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {proc.stderr[-400:]}")
    return round(n / fps, 2)


# ---------------------------------------------------------------- offline voiceover (Windows SAPI via pyttsx3)
_TTS_SCRIPT = r"""
import json, sys, pyttsx3
spec = json.loads(sys.stdin.read())
e = pyttsx3.init()
voices = e.getProperty('voices')
want = (spec.get('voice') or '').lower()
for v in voices:
    if want and want in v.name.lower():
        e.setProperty('voice', v.id)
e.setProperty('rate', int(spec.get('rate', 175)))
for i, line in enumerate(spec['lines']):
    e.save_to_file(line, spec['out'][i])
e.runAndWait()
print(json.dumps([v.name for v in voices]))
"""


def list_voices() -> list[str]:
    try:
        proc = subprocess.run([sys.executable, "-c", "import pyttsx3,json;e=pyttsx3.init();print(json.dumps([v.name for v in e.getProperty('voices')]))"],  # noqa: S603
                              capture_output=True, text=True, timeout=30, check=False)
        return json.loads(proc.stdout.strip() or "[]")
    except Exception:  # noqa: BLE001
        return []


def synthesize(lines: list[str], out_dir: Path, *, voice: str = "", rate: int = 175) -> list[tuple[Path, float]]:
    """Speak each line to a WAV file (offline). Returns [(path, seconds)]."""
    paths = [out_dir / f"line_{i:02d}.wav" for i in range(len(lines))]
    spec = {"lines": lines, "out": [str(p) for p in paths], "voice": voice, "rate": rate}
    proc = subprocess.run([sys.executable, "-c", _TTS_SCRIPT], input=json.dumps(spec), capture_output=True, text=True,  # noqa: S603
                          timeout=300, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"text-to-speech failed: {proc.stderr[-400:]}")
    out = []
    for p in paths:
        if not p.exists():
            raise RuntimeError("text-to-speech produced no audio")
        with wave.open(str(p)) as w:
            out.append((p, w.getnframes() / float(w.getframerate())))
    return out


def concat_wavs(parts: list[tuple[Path, float]], gap_s: float, out: Path) -> None:
    with wave.open(str(parts[0][0])) as first:
        params = first.getparams()
    silence = b"\x00" * int(params.framerate * gap_s) * params.sampwidth * params.nchannels
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        for p, _ in parts:
            with wave.open(str(p)) as r:
                w.writeframes(r.readframes(r.getnframes()))
            w.writeframes(silence)

