"""Exact binomial (Clopper-Pearson) 95% intervals for the headline thresholds
(data/binomial_ci.json). Answers reviewer point #6: "N=16 per cell is thin for
95% claims." The paper's other interval file (headline_ci.json) reports bootstrap
CIs on the interpolated P95 crossing; this file is complementary and reports EXACT
binomial coverage on the underlying decode proportions, so a reader can see how a
single stochastic miss at N=16 moves a headline threshold.

Two views per threshold factor (occlusion / ppm / contrast):
  1. PER-LEVEL POOLED: at each discrete factor level, the worst-case decoder
     (lowest pooled decode rate there) and its Clopper-Pearson interval on the
     pooled k of n captures (n = cells_at_level x captures_per_cell).
  2. SINGLE-CELL BOUNDARY: the individual design cell (one cid) at the factor
     level nearest the reported threshold, and its worst-case decoder's k of N.
     This is the honest N=16 view: with N=16 even a clean 16/16 cell has a CP
     lower bound of ~0.79, and a single miss (15/16) drops it to ~0.70, both well
     below 0.95, which is exactly the reviewer's point.

Clopper-Pearson (alpha=0.05), scipy.stats.beta:
  lower = beta.ppf(alpha/2, k, n-k+1)   (0 if k==0)
  upper = beta.ppf(1-alpha/2, k+1, n-k) (1 if k==n)

Reads results.parquet (occlusion G1, contrast G2) + results_cliff.parquet (ppm
sweep, payload=med). Writes a separate file; never touches headline*.json.
Factor subsets and reported thresholds match headline.py exactly."""
from __future__ import annotations
import os, json
import numpy as np, pandas as pd
from scipy.stats import beta

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
ALPHA = 0.05
DECODERS = ["opencv", "wechat", "zbar", "zxing"]

# Reported worst-case P95 thresholds from headline.py / data/headline.json.
OCC_THRESH = {"L": 8.2, "M": 8.0, "Q": 6.4, "H": 8.9}
PPM_THRESH = {"L": 3.33, "M": 3.17, "Q": 3.25, "H": 3.25}
CONTRAST_THRESH = 2.05


def clopper_pearson(k, n, alpha=ALPHA):
    k, n = int(k), int(n)
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return round(lo, 4), round(hi, 4)


def pooled_worst_level(sub, level):
    """At one factor level, find the decoder with the lowest pooled decode rate,
    return its pooled k, n, rate and Clopper-Pearson interval."""
    g = sub.groupby("decoder")["success"]
    rates = g.mean()
    wd = rates.idxmin()
    k = int(sub[sub.decoder == wd]["success"].sum())
    n = int((sub.decoder == wd).sum())
    lo, hi = clopper_pearson(k, n)
    return {"level": round(float(level), 2), "worst_decoder": wd,
            "k": k, "n": n, "rate": round(k / n, 4), "cp": [lo, hi]}


def boundary_cell(sub, levels, worst_rate, threshold, level_col):
    """Pick the single design cell (cid) nearest the reported threshold and report
    its own worst-case decoder's k of N. Level nearest on the factor axis; ties
    broken toward the level whose pooled worst-rate sits closest to 0.95, then the
    lower level. Within that level, the cid whose worst-case-decoder rate is
    closest to 0.95 (the on-the-fence cell that decides the crossing)."""
    lv = min(levels, key=lambda x: (abs(x - threshold), abs(worst_rate[x] - 0.95), x))
    at = sub[sub[level_col] == lv]
    best = None
    for cid, g in at.groupby("cid"):
        rates = g.groupby("decoder")["success"].mean()
        wd = rates.idxmin()
        gg = g[g.decoder == wd]
        k, N = int(gg["success"].sum()), int(len(gg))
        rate = k / N
        key = (abs(rate - 0.95), rate, cid)
        cand = {"level": round(float(lv), 2), "cid": cid, "worst_decoder": wd,
                "k": k, "N": N, "rate": round(rate, 4), "cp": list(clopper_pearson(k, N)),
                "_key": key}
        if best is None or key < best["_key"]:
            best = cand
    best.pop("_key")
    return best


def build_factor(sub, level_col, levels, threshold):
    levels = sorted(float(x) for x in levels)
    per_level = []
    worst_rate = {}
    for lv in levels:
        at = sub[sub[level_col] == lv]
        pl = pooled_worst_level(at, lv)
        per_level.append(pl)
        worst_rate[lv] = pl["rate"]
    bc = boundary_cell(sub, levels, worst_rate, threshold, level_col)
    return {"reported_threshold": threshold, "per_level_pooled": per_level,
            "boundary_cell": bc}


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    cf = pd.read_parquet(os.path.join(DATA, "results_cliff.parquet"))

    out = {
        "method": (
            "Exact Clopper-Pearson 95% intervals (alpha=0.05) via scipy.stats.beta: "
            "lower=beta.ppf(a/2,k,n-k+1) (0 if k=0), upper=beta.ppf(1-a/2,k+1,n-k) "
            "(1 if k=n). Two views per threshold factor. (1) per_level_pooled: at "
            "each discrete factor level the worst-case decoder = lowest pooled decode "
            "rate; CP on pooled k of n (n = cells_at_level x captures_per_cell). "
            "(2) boundary_cell: the single design cell (one cid) at the factor level "
            "nearest the reported P95 threshold, its own worst-case decoder's k of N, "
            "CP on that. Occlusion = results.parquet exp=G1 & ppm>=4 per EC (N=16 per "
            "cell, 3 cells/level -> pooled n=48). Contrast = results.parquet exp=G2 & "
            "~inverted & ppm>=4 (N=16 per cell, 12 cells/level -> pooled n=192). PPM "
            "cliff = results_cliff.parquet payload=med per EC (N=40 per cell, 1 cell/"
            "level -> pooled n=40; here the boundary cell N=40, not 16). Reported "
            "thresholds and subsets match headline.py."
        )
    }

    # (a) occlusion ceilings per EC
    occ = {}
    g1 = df[(df.exp == "G1") & (df.ppm >= 4)]
    for ec in ["L", "M", "Q", "H"]:
        sub = g1[g1.ec == ec]
        occ[ec] = build_factor(sub, "occ", sub.occ.unique(), OCC_THRESH[ec])
    out["occ_ceilings"] = occ

    # (b) ppm cliff per EC
    ppm = {}
    med = cf[cf.payload == "med"]
    for ec in ["L", "M", "Q", "H"]:
        sub = med[med.ec == ec]
        ppm[ec] = build_factor(sub, "ppm", sub.ppm.unique(), PPM_THRESH[ec])
    out["ppm_cliff"] = ppm

    # (c) contrast floor (single, pooled across EC as in headline.py)
    g2 = df[(df.exp == "G2") & (~df.inverted) & (df.ppm >= 4)]
    out["contrast_floor"] = build_factor(
        g2, "contrast_ratio", g2.contrast_ratio.unique(), CONTRAST_THRESH)

    with open(os.path.join(DATA, "binomial_ci.json"), "w") as f:
        json.dump(out, f, indent=1)

    print_tables(out)
    sanity_checks()


def _fmt_levels(rows, unit):
    print(f"  {'level':>7} {'worst':>7} {'k':>4}/{'n':<4} {'rate':>7}  "
          f"{'CP 95% interval':>20}")
    for r in rows:
        lo, hi = r["cp"]
        print(f"  {r['level']:>7}{unit:<1} {r['worst_decoder']:>7} "
              f"{r['k']:>4}/{r['n']:<4} {r['rate']:>7.4f}  [{lo:.4f}, {hi:.4f}]")


def _fmt_boundary(bc, unit):
    lo, hi = bc["cp"]
    print(f"  boundary cell @ {bc['level']}{unit} cid={bc['cid']} "
          f"worst={bc['worst_decoder']} {bc['k']}/{bc['N']} "
          f"rate={bc['rate']:.4f}  CP=[{lo:.4f}, {hi:.4f}]  (N={bc['N']})")


def print_tables(out):
    print("=" * 78)
    print("BINOMIAL (CLOPPER-PEARSON) 95% INTERVALS  -  data/binomial_ci.json")
    print("=" * 78)

    print("\n(a) OCCLUSION CEILINGS  (exp=G1, ppm>=4)  worst-case decoder per occ %")
    for ec in ["L", "M", "Q", "H"]:
        f = out["occ_ceilings"][ec]
        print(f"\n EC {ec}  reported P95 ceiling = {f['reported_threshold']}% occlusion")
        _fmt_levels(f["per_level_pooled"], "%")
        _fmt_boundary(f["boundary_cell"], "%")

    print("\n(b) PPM CLIFF  (results_cliff, payload=med)  worst-case decoder per ppm")
    for ec in ["L", "M", "Q", "H"]:
        f = out["ppm_cliff"][ec]
        print(f"\n EC {ec}  reported min px/module = {f['reported_threshold']}")
        _fmt_levels(f["per_level_pooled"], "")
        _fmt_boundary(f["boundary_cell"], "")

    print("\n(c) CONTRAST FLOOR  (exp=G2, ~inverted, ppm>=4)  worst-case decoder per ratio")
    f = out["contrast_floor"]
    print(f"\n reported P95 floor = {f['reported_threshold']}:1")
    _fmt_levels(f["per_level_pooled"], "")
    _fmt_boundary(f["boundary_cell"], "")


def sanity_checks():
    print("\n" + "=" * 78)
    print("SANITY CHECKS")
    print("=" * 78)
    lo16, hi16 = clopper_pearson(16, 16)
    print(f" k=16,n=16 -> CP=[{lo16},{hi16}]  lower<1: {lo16 < 1}  upper==1: {hi16 == 1.0}")
    lo0, hi0 = clopper_pearson(0, 16)
    print(f" k=0, n=16 -> CP=[{lo0},{hi0}]   lower==0: {lo0 == 0.0}")
    lo15, hi15 = clopper_pearson(15, 16)
    print(f" k=15,n=16 -> CP=[{lo15},{hi15}]  single miss: lower {lo15} << 0.95: {lo15 < 0.95}")
    print(f" => At N=16 a single-cell 95% claim is unsupportable: even a perfect 16/16"
          f" cell has CP lower bound {lo16} (< 0.95).")


if __name__ == "__main__":
    main()
