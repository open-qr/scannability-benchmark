"""Camera-proxy degradation: convert a clean render into a realistic 'capture'
at a target pixels-per-module (ppm), with blur, sensor noise, JPEG and geometric
jitter. This is the external-validity layer that maps print-size x distance x
camera onto one axis (ppm)."""
from __future__ import annotations
import cv2
import numpy as np
import io
from PIL import Image

def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def _bgr_to_pil(a: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))

def degrade(img: Image.Image, n_modules: int, quiet: int, ppm: float,
            blur_sigma: float = 0.0, noise_sigma: float = 0.0,
            jpeg_q: int = 100, rot_deg: float = 0.0, tilt_deg: float = 0.0,
            rng: np.random.Generator | None = None) -> np.ndarray:
    """Return a BGR uint8 array as a decoder would see it."""
    rng = rng or np.random.default_rng(0)
    a = _pil_to_bgr(img)
    # target total pixels so each module ~ ppm px (including quiet zone)
    target = int(round((n_modules + 2 * quiet) * ppm))
    target = max(target, 21)
    a = cv2.resize(a, (target, target), interpolation=cv2.INTER_AREA)
    # geometric jitter (rotation + mild perspective tilt) before blur
    if rot_deg or tilt_deg:
        a = _warp(a, rot_deg, tilt_deg, rng)
    # optical blur
    if blur_sigma > 0:
        k = max(3, int(blur_sigma * 4) | 1)
        a = cv2.GaussianBlur(a, (k, k), blur_sigma)
    # sensor noise
    if noise_sigma > 0:
        noise = rng.normal(0, noise_sigma, a.shape)
        a = np.clip(a.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    # JPEG round-trip
    if jpeg_q < 100:
        ok, buf = cv2.imencode(".jpg", a, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_q)])
        if ok:
            a = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return a

def _warp(a: np.ndarray, rot_deg: float, tilt_deg: float, rng) -> np.ndarray:
    h, w = a.shape[:2]
    # pad so rotation doesn't clip
    pad = int(max(h, w) * 0.25)
    a = cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    h, w = a.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rot_deg, 1.0)
    a = cv2.warpAffine(a, M, (w, h), borderValue=(255, 255, 255))
    if tilt_deg:
        t = np.tan(np.deg2rad(tilt_deg)) * w * 0.25
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32([[t, 0], [w - t, 0], [w, h], [0, h]])
        P = cv2.getPerspectiveTransform(src, dst)
        a = cv2.warpPerspective(a, P, (w, h), borderValue=(255, 255, 255))
    return a
