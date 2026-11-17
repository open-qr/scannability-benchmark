"""Numeric results for factors collected in v1.0 but unreported in the preprint (v1.1 A6):
module style (G3), hue pairs at matched contrast (G5h), overlay-vs-excavated occlusion (G5),
plus the unstyled-control anchor. All from the committed results.parquet. No new data.

Writes data/factor_report.json.
"""
from __future__ import annotations
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
DECODERS = ["opencv", "wechat", "zbar", "zxing"]


def rates(sub: pd.DataFrame):
    per = {d: round(float(sub[sub.decoder == d]["success"].mean()), 3) for d in DECODERS}
    cell = sub.groupby(["cid", "decoder"])["success"].mean().unstack()
    return {"per_decoder": per, "worst_case_cells": round(float(cell.min(axis=1).mean()), 3),
            "n_cells": int(cell.shape[0])}


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))

    out = {}

    # unstyled-control anchor: pristine square, no logo, max contrast, normal polarity, ppm>=4
    anchor = df[(df.occ == 0) & (~df.inverted) & (df.contrast_ratio == 21) & (df.style == "square")
                & (df.ppm >= 4)]
    out["unstyled_control"] = rates(anchor)

    # module style, matched conditions (no logo, max contrast, normal polarity); ppm>=4 and pooled
    base = df[(df.occ == 0) & (~df.inverted) & (df.contrast_ratio == 21)]
    out["module_style"] = {}
    for label, sub in [("ppm_ge4", base[base.ppm >= 4]), ("all_ppm", base)]:
        out["module_style"][label] = {st: rates(sub[sub.style == st])
                                      for st in sorted(sub.style.unique())}

    # hue at matched contrast (G5h: EC Q, no logo, pairs at ~matched WCAG ratio)
    hue = df[df.hue.notna() & (df.hue != "none")] if "hue" in df else df.iloc[:0]
    out["hue_pairs"] = {h: rates(hue[hue.hue == h]) for h in sorted(hue.hue.unique())}

    # overlay vs hard (excavated) at matched EC x occ x ppm (G5 overlay vs G1 hard)
    ov = df[(df.exp == "G5") & (df.occ > 0)]
    hd = df[(df.exp == "G1") & (df.occ > 0) & df.occ.isin(ov.occ.unique())
            & df.ppm.isin(ov.ppm.unique()) & df.ec.isin(ov.ec.unique())]
    out["overlay_vs_hard"] = {"overlay": rates(ov), "hard_matched": rates(hd),
                              "matched_on": {"ec": sorted(ov.ec.unique().tolist()),
                                             "occ": sorted(ov.occ.unique().tolist()),
                                             "ppm": sorted(ov.ppm.unique().tolist())}}

    json.dump(out, open(os.path.join(DATA, "factor_report.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    print("\nwrote data/factor_report.json")


if __name__ == "__main__":
    main()
