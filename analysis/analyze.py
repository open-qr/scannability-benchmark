"""Analysis for the scannability study. Reads data/results.parquet, aggregates to
per-cell/per-decoder decode rates, computes the pre-registered contributions
C1-C5, and writes data/summary.json + data/frontiers.csv."""
from __future__ import annotations
import os, json, sys
import numpy as np, pandas as pd
from scipy.optimize import curve_fit
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
EC_ORD = {"L": 0, "M": 1, "Q": 2, "H": 3}
# nominal RS codeword recovery budgets (fraction)
RS_BUDGET = {"L": 0.07, "M": 0.15, "Q": 0.25, "H": 0.30}

def load():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    df["ec_ord"] = df["ec"].map(EC_ORD)
    return df

def logistic(x, x0, k):
    return 1.0 / (1.0 + np.exp(-k * (x - x0)))

def threshold(x, y, target, increasing):
    """Fit logistic p(x); return x where p==target. increasing: p rises with x."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(np.unique(x)) < 3 or y.min() == y.max():
        # degenerate: return boundary
        if y.mean() >= target:
            return x.min() if increasing else x.max()
        return np.nan
    try:
        sign = 1 if increasing else -1
        p0 = [np.median(x), sign * 1.0]
        popt, _ = curve_fit(logistic, x, y, p0=p0, maxfev=20000)
        x0, k = popt
        # invert logistic: target = 1/(1+exp(-k(x-x0)))
        if abs(k) < 1e-6:
            return np.nan
        xt = x0 - np.log(1 / target - 1) / k
        return float(xt)
    except Exception:
        return np.nan

def per_cell(df):
    g = (df.groupby(["cid", "exp", "payload", "version", "n_modules", "ec", "ec_ord",
                     "occ", "occ_mode", "contrast_ratio", "inverted", "hue", "style",
                     "ppm", "decoder"])["success"].mean().reset_index())
    return g

def worst_any(df):
    """Per-cell worst-case (min across decoders) and any-decoder (max)."""
    pc = per_cell(df)
    keys = ["cid", "exp", "payload", "version", "n_modules", "ec", "ec_ord", "occ",
            "occ_mode", "contrast_ratio", "inverted", "hue", "style", "ppm"]
    w = pc.groupby(keys)["success"].min().reset_index().rename(columns={"success": "worst"})
    a = pc.groupby(keys)["success"].max().reset_index()["success"]
    w["any"] = a.values
    return w

def main():
    df = load()
    out = {"n_attempts": int(len(df)), "n_cells": int(df["cid"].nunique())}
    pc = per_cell(df)

    # ---- overall per-decoder ----
    out["overall_decoder_success"] = df.groupby("decoder")["success"].mean().round(4).to_dict()
    out["detected_not_decoded"] = round(
        float(((df["detected"] == 1) & (df["success"] == 0)).mean()), 4)

    # ---- C1: occlusion ceiling per EC (G1, use a good-resolution slice ppm>=4) ----
    g1 = pc[(pc.exp == "G1")]
    c1 = {}
    for dec in ["zbar", "opencv", "wechat", "zxing", "WORST"]:
        c1[dec] = {}
        for ec in ["L", "M", "Q", "H"]:
            if dec == "WORST":
                sub = worst_any(df[(df.exp == "G1") & (df.ec == ec) & (df.ppm >= 4)])
                x, y = sub["occ"], sub["worst"]
            else:
                sub = g1[(g1.ec == ec) & (g1.decoder == dec) & (g1.ppm >= 4)]
                x, y = sub["occ"], sub["success"]
            p95 = threshold(x, y, 0.95, increasing=False)
            p50 = threshold(x, y, 0.50, increasing=False)
            c1[dec][ec] = {"p95_occ": _r(p95), "p50_occ": _r(p50),
                           "rs_budget_pct": RS_BUDGET[ec] * 100,
                           "gap_vs_rs": _r(RS_BUDGET[ec] * 100 - p95) if p95 == p95 else None}
    out["C1_occlusion_ceiling"] = c1

    # ---- C3: contrast floor (G2 normal), inverted penalty ----
    g2 = pc[pc.exp == "G2"]
    c3 = {"contrast_floor_p95": {}, "inverted_penalty": {}}
    for dec in ["zbar", "opencv", "wechat", "zxing", "WORST"]:
        if dec == "WORST":
            base = worst_any(df[(df.exp == "G2") & (~df.inverted) & (df.ppm >= 4)])
            xcol = "worst"
        else:
            base = g2[(g2.decoder == dec) & (~g2.inverted) & (g2.ppm >= 4)]; xcol = "success"
        c3["contrast_floor_p95"][dec] = _r(threshold(base["contrast_ratio"], base[xcol], 0.95, increasing=True))
    # inverted vs normal matched
    for dec in ["zbar", "opencv", "wechat", "zxing"]:
        norm = g2[(g2.decoder == dec) & (~g2.inverted)]["success"].mean()
        inv = g2[(g2.decoder == dec) & (g2.inverted)]["success"].mean()
        c3["inverted_penalty"][dec] = {"normal": _r(norm), "inverted": _r(inv),
                                       "abs_drop": _r(norm - inv)}
    out["C3_contrast"] = c3

    # ---- C4: EC paradox, success vs EC at fixed physical size (low ppm), occ0 ----
    c4 = {}
    for ppm in sorted(df.ppm.unique()):
        sub = worst_any(df[(df.exp.isin(["G1", "G4"])) & (df.occ == 0) & (df.payload == "med") & (df.ppm == ppm)])
        by_ec = sub.groupby("ec")["worst"].mean()
        c4[str(ppm)] = {ec: _r(by_ec.get(ec, np.nan)) for ec in ["L", "M", "Q", "H"]}
    out["C4_ec_paradox_worstcase_by_ppm"] = c4
    # explicit paradox flag: any ppm where H < L (worst-case)
    out["C4_paradox_regimes"] = [ppm for ppm, d in c4.items()
                                 if d["H"] is not None and d["L"] is not None and d["H"] < d["L"] - 0.02]
    # version inflation reference
    out["C4_version_by_ec_med"] = (df[df.payload == "med"].groupby("ec")["version"].first().to_dict())

    # ---- module style penalty (G3) ----
    g3 = worst_any(df[df.exp == "G3"])
    out["style_penalty_worstcase"] = {st: _r(g3[g3.style == st]["worst"].mean())
                                      for st in ["square", "rounded", "dots", "gapped"]}

    # ---- C5: predictive Scannability Margin model ----
    out["C5_model"] = fit_model(df)

    with open(os.path.join(DATA, "summary.json"), "w") as f:
        json.dump(out, f, indent=2)
    worst_any(df).to_csv(os.path.join(DATA, "cell_worst_any.csv"), index=False)
    pc.to_csv(os.path.join(DATA, "cell_decoder.csv"), index=False)
    print(json.dumps(out, indent=2)[:4000])
    print("... [full summary.json written]")

def fit_model(df):
    """Predict per-attempt decode from design-time features; hold out payload=long."""
    d = df.copy()
    d["inverted_i"] = d["inverted"].astype(int)
    style_d = pd.get_dummies(d["style"], prefix="st")
    dec_d = pd.get_dummies(d["decoder"], prefix="dec")
    feat = pd.concat([d[["ec_ord", "ppm", "contrast_ratio", "occ", "version", "inverted_i"]],
                      style_d, dec_d], axis=1).astype(float)
    y = d["success"].values
    tr = d["payload"] != "long"; te = d["payload"] == "long"
    res = {}
    sc = StandardScaler()
    Xtr = sc.fit_transform(feat[tr]); Xte = sc.transform(feat[te])
    lr = LogisticRegression(max_iter=2000).fit(Xtr, y[tr])
    res["logistic_auc_heldout"] = _r(roc_auc_score(y[te], lr.predict_proba(Xte)[:, 1]))
    gb = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0).fit(feat[tr], y[tr])
    res["gbm_auc_heldout"] = _r(roc_auc_score(y[te], gb.predict_proba(feat[te])[:, 1]))
    # interpretable coefficients (standardized)
    raw = feat.columns.tolist()
    res["logistic_coefficients_standardized"] = {c: _r(v) for c, v in zip(raw, lr.coef_[0])}
    res["feature_importance_gbm"] = {c: _r(v) for c, v in
                                     sorted(zip(raw, gb.feature_importances_), key=lambda t: -t[1])[:8]}
    res["prereg_bar_auc_0.85_met"] = bool(res["gbm_auc_heldout"] >= 0.85 or res["logistic_auc_heldout"] >= 0.85)
    return res

def _r(x):
    try:
        if x != x:  # nan
            return None
        return round(float(x), 3)
    except Exception:
        return None

if __name__ == "__main__":
    main()
