"""Unified interface over four independent library decoders:
zbar, OpenCV QRCodeDetector, OpenCV WeChat (CNN), zxing-cpp.
Each returns DecodeResult(name, success, text, detected, ms)."""
from __future__ import annotations
import time, os, urllib.request
import numpy as np
import cv2
from dataclasses import dataclass

_HERE = os.path.dirname(__file__)
_MODELS = os.path.join(_HERE, "models")

@dataclass
class DecodeResult:
    name: str
    success: bool
    text: str
    detected: bool
    ms: float

def _download_wechat_models() -> bool:
    os.makedirs(_MODELS, exist_ok=True)
    base = "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/"
    files = ["detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel"]
    for f in files:
        p = os.path.join(_MODELS, f)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            continue
        try:
            urllib.request.urlretrieve(base + f, p)
        except Exception as e:
            print("wechat model download failed:", f, e)
            return False
    return all(os.path.exists(os.path.join(_MODELS, f)) for f in files)

class Decoders:
    def __init__(self, want_wechat=True):
        self.cv = cv2.QRCodeDetector()
        self.wechat = None
        if want_wechat:
            # Fail loud: a missing WeChat model must abort the run, not silently
            # record every wechat attempt as a failure and corrupt the dataset.
            if not _download_wechat_models():
                raise RuntimeError(
                    "WeChat CNN models unavailable (download failed). Re-run with "
                    "network access, place the four model files in harness/models/, "
                    "or pass want_wechat=False to run a 3-decoder study explicitly.")
            self.wechat = cv2.wechat_qrcode.WeChatQRCode(
                os.path.join(_MODELS, "detect.prototxt"),
                os.path.join(_MODELS, "detect.caffemodel"),
                os.path.join(_MODELS, "sr.prototxt"),
                os.path.join(_MODELS, "sr.caffemodel"))
        import pyzbar.pyzbar as pyz
        import zxingcpp
        self._pyz = pyz
        self._zxing = zxingcpp

    def _zbar(self, bgr, expect):
        t = time.perf_counter()
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        res = self._pyz.decode(gray)
        ms = (time.perf_counter() - t) * 1000
        qrs = [r for r in res if r.type == "QRCODE"]
        text = qrs[0].data.decode("utf-8", "replace") if qrs else ""
        return DecodeResult("zbar", text == expect, text, bool(qrs), ms)

    def _opencv(self, bgr, expect):
        t = time.perf_counter()
        try:
            text, pts, _ = self.cv.detectAndDecode(bgr)
        except cv2.error:
            text, pts = "", None
        ms = (time.perf_counter() - t) * 1000
        detected = pts is not None and len(np.array(pts).reshape(-1)) > 0
        return DecodeResult("opencv", text == expect, text, detected, ms)

    def _wechat(self, bgr, expect):
        if self.wechat is None:
            return DecodeResult("wechat", False, "", False, 0.0)
        t = time.perf_counter()
        try:
            texts, pts = self.wechat.detectAndDecode(bgr)
        except cv2.error:
            texts, pts = [], []
        ms = (time.perf_counter() - t) * 1000
        text = texts[0] if texts else ""
        return DecodeResult("wechat", text == expect, text, len(pts) > 0, ms)

    def _zxingcpp(self, bgr, expect):
        t = time.perf_counter()
        res = self._zxing.read_barcodes(bgr)
        ms = (time.perf_counter() - t) * 1000
        qrs = [r for r in res if r.format == self._zxing.BarcodeFormat.QRCode]
        text = qrs[0].text if qrs else ""
        return DecodeResult("zxing", text == expect, text, bool(res), ms)

    def all(self, bgr, expect):
        return [self._zbar(bgr, expect), self._opencv(bgr, expect),
                self._wechat(bgr, expect), self._zxingcpp(bgr, expect)]

    @property
    def names(self):
        return ["zbar", "opencv", "wechat", "zxing"]

if __name__ == "__main__":
    import segno
    from qrgen import build_matrix, render
    from degrade import degrade
    d = Decoders()
    print("wechat available:", d.wechat is not None)
    s = build_matrix("https://oqr.to/aB3xK", "H")
    img = render(s)
    bgr = degrade(img, s.n, 4, ppm=6)
    for r in d.all(bgr, "https://oqr.to/aB3xK"):
        print(f"{r.name:8} success={r.success} detected={r.detected} {r.ms:.1f}ms  '{r.text[:30]}'")
