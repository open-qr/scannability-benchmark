"""Deterministic, style-controlled QR rendering for the scannability study.

We build the module matrix with segno (full control of version + EC), then render
each module ourselves so that module *style*, *colour/contrast* and *centre-logo
occlusion* are all reproducible and independent. Finder patterns are kept solid
square (as real styling tools do) so the deformation penalty we measure is the
data-region penalty a real designer actually incurs.
"""
from __future__ import annotations
import segno
import numpy as np
from PIL import Image, ImageDraw
from dataclasses import dataclass

# ---- WCAG relative luminance / contrast ----------------------------------
def _srgb_lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def rel_luminance(rgb) -> float:
    r, g, b = (_srgb_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast_ratio(fg, bg) -> float:
    l1, l2 = rel_luminance(fg), rel_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)

def grey_for_ratio(target: float, bg=(255, 255, 255)):
    """Return a grey foreground giving ~target contrast ratio against bg (white)."""
    best, bestd = 0, 1e9
    for v in range(256):
        d = abs(contrast_ratio((v, v, v), bg) - target)
        if d < bestd:
            best, bestd = v, d
    return (best, best, best)

# ---- symbol construction --------------------------------------------------
@dataclass
class Symbol:
    matrix: np.ndarray   # bool, dark=True, no quiet zone
    version: int
    ec: str
    n: int               # modules per side

def build_matrix(payload: str, ec: str) -> Symbol:
    q = segno.make(payload, error=ec.lower(), micro=False)
    m = np.array(q.matrix, dtype=bool)
    return Symbol(matrix=m, version=q.version, ec=ec.upper(), n=m.shape[0])

def _finder_mask(n: int) -> np.ndarray:
    """True where a module belongs to a finder pattern block (keep square)."""
    mask = np.zeros((n, n), bool)
    for (r0, c0) in [(0, 0), (0, n - 7), (n - 7, 0)]:
        mask[r0:r0 + 7, c0:c0 + 7] = True
    return mask

def render(sym: Symbol, module_px: int = 24, quiet: int = 4,
           fg=(0, 0, 0), bg=(255, 255, 255), style: str = "square",
           fill: float = 1.0) -> Image.Image:
    """Render a clean symbol image at module_px per module with a quiet zone."""
    n = sym.n
    size = (n + 2 * quiet) * module_px
    img = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(img)
    fmask = _finder_mask(n)
    for r in range(n):
        for c in range(n):
            if not sym.matrix[r, c]:
                continue
            x0 = (c + quiet) * module_px
            y0 = (r + quiet) * module_px
            is_finder = fmask[r, c]
            if is_finder or style == "square":
                d.rectangle([x0, y0, x0 + module_px - 1, y0 + module_px - 1], fill=fg)
            elif style == "gapped":
                pad = module_px * (1 - 0.72) / 2
                d.rectangle([x0 + pad, y0 + pad, x0 + module_px - 1 - pad, y0 + module_px - 1 - pad], fill=fg)
            elif style == "dots":
                rad = module_px * 0.42
                cx, cy = x0 + module_px / 2, y0 + module_px / 2
                d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=fg)
            elif style == "rounded":
                rad = module_px * 0.35
                d.rounded_rectangle([x0, y0, x0 + module_px - 1, y0 + module_px - 1], radius=rad, fill=fg)
    return img

def apply_center_logo(img: Image.Image, sym: Symbol, area_frac: float,
                      quiet: int = 4, mode: str = "hard", bg=(255, 255, 255)) -> Image.Image:
    """Knock out a centred square covering `area_frac` of the *symbol* area.
    mode='hard' -> clear to background (excavated logo); 'overlay' -> opaque black block."""
    if area_frac <= 0:
        return img
    n = sym.n
    module_px = img.width // (n + 2 * quiet)
    sym_px = n * module_px
    side = int(round((area_frac ** 0.5) * sym_px))
    cx = cy = img.width // 2
    x0, y0 = cx - side // 2, cy - side // 2
    d = ImageDraw.Draw(img)
    color = bg if mode == "hard" else (0, 0, 0)
    d.rectangle([x0, y0, x0 + side, y0 + side], fill=color)
    if mode == "hard":  # thin white pad already is bg; add a subtle border to mimic real clearance
        pass
    return img

if __name__ == "__main__":
    for ec in ["L", "M", "Q", "H"]:
        s = build_matrix("https://oqr.to/aB3xK", ec)
        print(ec, "version", s.version, "modules", s.n)
