"""Object removal.

- AI path: LaMa (big-lama, Apache-2.0 weights) exported to ONNX (Carve/LaMa-ONNX, 512×512 fixed input),
  run with onnxruntime on CPU. Downloaded on first use into data/models.
- Non-AI path: OpenCV Telea inpainting. Always available; labeled as non-AI in results.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import httpx
import numpy as np
from PIL import Image

from app.config import get_settings

log = logging.getLogger("shelfcraft.imaging.inpaint")

LAMA_URL = "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
LAMA_FILE = "lama_fp32.onnx"
_session = None
_lock = threading.Lock()


def lama_path() -> Path:
    return get_settings().models_dir / LAMA_FILE


def lama_available() -> bool:
    return lama_path().is_file() and lama_path().stat().st_size > 50_000_000


def download_lama() -> Path:
    """Download the LaMa ONNX model (~200 MB) once. Atomic: writes .part then renames."""
    p = lama_path()
    if lama_available():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    log.info("downloading LaMa ONNX model from %s", LAMA_URL)
    with httpx.stream("GET", LAMA_URL, follow_redirects=True, timeout=httpx.Timeout(30.0, read=300.0)) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.replace(p)
    return p


def _get_session():  # noqa: ANN202
    global _session
    if _session is None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        _session = ort.InferenceSession(str(download_lama()), opts, providers=["CPUExecutionProvider"])
    return _session


def _crop_box(mask: np.ndarray, pad_ratio: float = 0.6, min_side: int = 256) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    if len(xs) == 0:
        return 0, 0, w, h
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    side = max(x1 - x0, y1 - y0, min_side / (1 + pad_ratio))
    side = int(side * (1 + pad_ratio))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    side = min(side, max(w, h))
    left = int(max(0, min(w - side, cx - side // 2))) if side <= w else 0
    top = int(max(0, min(h - side, cy - side // 2))) if side <= h else 0
    return left, top, min(w, left + side), min(h, top + side)


def inpaint_lama(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Remove masked region with LaMa. Works on a padded crop around the mask for detail."""
    rgb = np.array(image.convert("RGB"))
    m = (np.array(mask.convert("L").resize(image.size)) > 127).astype(np.uint8)
    m = cv2.dilate(m, np.ones((9, 9), np.uint8), iterations=1)  # cover object edges/shadows
    left, top, right, bottom = _crop_box(m)
    crop, mcrop = rgb[top:bottom, left:right], m[top:bottom, left:right]
    ch, cw = crop.shape[:2]
    img_in = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    mask_in = (cv2.resize(mcrop, (512, 512), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
    feeds = {"image": img_in.transpose(2, 0, 1)[None], "mask": mask_in[None, None]}
    with _lock:
        sess = _get_session()
        names = [i.name for i in sess.get_inputs()]
        out = sess.run(None, dict(zip(names, (feeds["image"], feeds["mask"]))))[0][0]
    out = out.transpose(1, 2, 0)
    if out.max() <= 1.5:
        out = out * 255.0
    out = np.clip(out, 0, 255).astype(np.uint8)
    out = cv2.resize(out, (cw, ch), interpolation=cv2.INTER_CUBIC)
    # Blend only inside the (feathered) mask so untouched pixels stay identical.
    feather = cv2.GaussianBlur(mcrop.astype(np.float32), (15, 15), 0)[..., None]
    merged = (out * feather + crop * (1 - feather)).astype(np.uint8)
    result = rgb.copy()
    result[top:bottom, left:right] = merged
    res = Image.fromarray(result)
    if image.mode == "RGBA":
        res.putalpha(image.getchannel("A"))
    return res


def inpaint_opencv(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Classical (non-AI) Telea inpainting — fine for small blemishes, weak on large objects."""
    rgb = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    m = (np.array(mask.convert("L").resize(image.size)) > 127).astype(np.uint8) * 255
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    out = cv2.inpaint(rgb, m, 7, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
