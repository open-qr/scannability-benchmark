"""Regenerates data/headline.json: the small set of headline numbers cited in the
preprint. These use *linear interpolation* of the empirical worst-case decode
curves (piecewise between measured factor levels), as opposed to the parametric
logistic fit in analyze.py (summary.json). Linear interpolation makes no shape
assumption and is the number the paper reports; analyze.py's logistic fit is kept
as a smoothed cross-check (the two agree except where a long zero tail pulls the
sigmoid's P95 crossing to the right, e.g. the H occlusion ceiling). Reads
results.parquet (main grid) + results_cliff.parquet (fine ppm sweep)."""
from __future__ import annotations
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")


def per_cell(df):
    keys = ["cid", "exp", "payload", "version", "n_modules", "ec", "occ", "occ_mode",
            "contrast_ratio", "inverted", "hue", "style", "ppm"]
    pc = df.groupby(keys + ["decoder"])["success"].mean().reset_index()
    worst = pc.groupby(keys)["success"].min().reset_index().rename(columns={"success": "worst"})
    return worst


def lin_threshold(xs, ys, target, increasing):
    """Piecewise-linear crossing of `target`. xs need not be pre-sorted.
    increasing=False: curve falls with x (occlusion); return largest safe x.
    increasing=True: curve rises with x (contrast/ppm); return smallest safe x."""
    order = np.argsort(xs)
    xs = np.asarray(xs, float)[order]
    ys = np.asarray(ys, float)[order]
    if increasing:
        if ys[0] >= target:
            return float(xs[0])
        for i in range(1, len(xs)):
            if ys[i - 1] < target <= ys[i]:
                t = (target - ys[i - 1]) / (ys[i] - ys[i - 1])
                return float(xs[i - 1] + t * (xs[i] - xs[i - 1]))
        return float("nan")
    else:
        if ys[-1] >= target:
            return float(xs[-1])
        for i in range(1, len(xs)):
            if ys[i - 1] >= target > ys[i]:
                t = (ys[i - 1] - target) / (ys[i - 1] - ys[i])
                return float(xs[i - 1] + t * (xs[i] - xs[i - 1]))
        return float("nan")


def occ_ceiling(df):
    w = per_cell(df[(df.exp == "G1") & (df.ppm >= 4)])
    out = {}
    for ec in ["L", "M", "Q", "H"]:
        c = w[w.ec == ec].groupby("occ")["worst"].mean()
        out[ec] = round(lin_threshold(c.index.values, c.values, 0.95, increasing=False), 1)
    return out


def occ_ceiling_by_decoder(df):
    """Per-decoder interpolated P95 occlusion ceilings, plus the worst case over
    the three decoders other than OpenCV QRCodeDetector. At Q/H the pooled
    worst-case ceiling is set by OpenCV alone; every other decoder (including
    classical ZBar and ZXing) reads materially further, so the paper reports
    both the 4-decoder floor and this excluding-OpenCV figure."""
    keys = ["cid", "exp", "payload", "version", "n_modules", "ec", "occ", "occ_mode",
            "contrast_ratio", "inverted", "hue", "style", "ppm"]
    sub = df[(df.exp == "G1") & (df.ppm >= 4)]
    pc = sub.groupby(keys + ["decoder"])["success"].mean().reset_index()
    out = {}
    for ec in ["L", "M", "Q", "H"]:
        row = {}
        for dec in ["zbar", "opencv", "wechat", "zxing"]:
            c = pc[(pc.ec == ec) & (pc.decoder == dec)].groupby("occ")["success"].mean()
            row[dec] = round(lin_threshold(c.index.values, c.values, 0.95, increasing=False), 1)
        w3 = (pc[pc.decoder != "opencv"].groupby(keys)["success"].min()
              .reset_index().rename(columns={"success": "worst"}))
        c3 = w3[w3.ec == ec].groupby("occ")["worst"].mean()
        row["worst_excl_opencv"] = round(lin_threshold(c3.index.values, c3.values, 0.95, increasing=False), 1)
        out[ec] = row
    return out


def min_ppm(cf, payload):
    w = per_cell(cf[cf.payload == payload])
    out = {}
    for ec in ["L", "M", "Q", "H"]:
        c = w[w.ec == ec].groupby("ppm")["worst"].mean()
        out[ec] = round(lin_threshold(c.index.values, c.values, 0.95, increasing=True), 2)
    return out


def contrast_floor(df):
    w = per_cell(df[(df.exp == "G2") & (~df.inverted) & (df.ppm >= 4)])
    c = w.groupby("contrast_ratio")["worst"].mean()
    return round(lin_threshold(c.index.values, c.values, 0.95, increasing=True), 2)


def inversion(df):
    g2 = df[df.exp == "G2"]
    out = {}
    for dec in ["opencv", "wechat", "zbar", "zxing"]:
        norm = g2[(g2.decoder == dec) & (~g2.inverted)]["success"].mean()
        inv = g2[(g2.decoder == dec) & (g2.inverted)]["success"].mean()
        out[dec] = {"normal": round(float(norm), 3), "inverted": round(float(inv), 3)}
    return out


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    cf = pd.read_parquet(os.path.join(DATA, "results_cliff.parquet"))
    out = {
        "occ_p95_worstcase": occ_ceiling(df),
        "occ_p95_by_decoder": occ_ceiling_by_decoder(df),
        "min_ppm_95_med": min_ppm(cf, "med"),
        "min_ppm_95_short": min_ppm(cf, "short"),
        "contrast_floor_worstcase_p95": contrast_floor(df),
        "inversion": inversion(df),
        "decoder_overall": {d: round(float(v), 3) for d, v in
                            df.groupby("decoder")["success"].mean().items()},
        "decoder_lowres_ppm2": {d: round(float(v), 3) for d, v in
                                df[df.ppm <= 2].groupby("decoder")["success"].mean().items()},
    }
    with open(os.path.join(DATA, "headline.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
