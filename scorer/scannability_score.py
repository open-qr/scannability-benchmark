"""Scannability Margin scorer, OpenQR Research. Per-decoder held-out AUC {"opencv": 0.9651, "zbar": 0.9744, "zxing": 0.9636, "wechat": 0.9388}.
The scalar margin ranks; the grade is calibrated to held-out worst-case decode rate. Not a
calibrated probability (use the gradient-boosted model for that)."""
import math
_M = {"opencv": {"intercept": -6.936831, "coef": {"ec_ord": -0.229233, "ppm": 1.874114, "contrast_ratio": 0.036393, "occ": -0.595234, "version": 0.758883, "inverted_i": -13.805743}}, "zbar": {"intercept": -4.927565, "coef": {"ec_ord": -0.053928, "ppm": 1.306306, "contrast_ratio": 0.03722, "occ": -0.397301, "version": 0.621991, "inverted_i": -11.475897}}, "zxing": {"intercept": -4.454886, "coef": {"ec_ord": -0.103343, "ppm": 1.58174, "contrast_ratio": 0.032596, "occ": -0.46881, "version": 0.483104, "inverted_i": -0.098011}}, "wechat": {"intercept": -4.332219, "coef": {"ec_ord": -0.019996, "ppm": 1.36952, "contrast_ratio": 0.069208, "occ": -0.431907, "version": 0.548228, "inverted_i": -0.976405}}}
_PROFILE = {"worst_case": ["opencv", "zbar", "zxing", "wechat"], "modern_phone": ["zxing", "wechat"], "kiosk_embedded": ["opencv", "zbar"]}
_EC = {"L": 0, "M": 1, "Q": 2, "H": 3}
_CUT = {"risky": 0.5775, "safe": 0.9917}

def _feat(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted=False):
    return {"ec_ord": _EC[ec_level], "ppm": px_per_module, "contrast_ratio": contrast_ratio,
            "occ": occlusion_pct, "version": version, "inverted_i": 1 if inverted else 0}

def score_by_decoder(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted=False):
    x = _feat(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted)
    out = {}
    for d, m in _M.items():
        z = m["intercept"] + sum(m["coef"][k] * x[k] for k in m["coef"])
        out[d] = 1 / (1 + math.exp(-z))
    return out

def scannability_margin(ec_level, px_per_module, contrast_ratio, occlusion_pct, version,
                        inverted=False, profile="worst_case"):
    s = score_by_decoder(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted)
    return min(s[d] for d in _PROFILE[profile])

def scannability_grade(*a, profile="worst_case", **k):
    m = scannability_margin(*a, profile=profile, **k)
    return "safe" if m >= _CUT["safe"] else "risky" if m >= _CUT["risky"] else "fragile"
