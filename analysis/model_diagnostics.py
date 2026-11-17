"""Model diagnostics (v1.1 amendment A5 + A6): the validation the reviewers asked for.

  1. Leave-one-payload-out CV: three held-out numbers instead of one (the v1.0 holdout was
     the long payload only).
  2. Boundary-band discrimination: AUC inside the decision-relevant band (px/module 2-4 or
     occlusion 4-20%), where a designer actually chooses. Pooled AUC on a grid full of easy
     cliffs (1 ppm never decodes, 8 ppm always decodes) overstates usefulness.
  3. Permutation feature importance on the held-out set (impurity importance is biased
     against low-cardinality features like EC and inversion), plus on the training boundary
     band. The held-out long payload has zero occlusion/inversion/contrast variation, so
     permutation importance there only exercises resolution/EC/version.
  4. Thresholds at 90/95/99% worst-case success (occlusion per EC, worst-case and
     excluding-OpenCV at H; resolution cliff for the medium payload), same interpolation
     as headline.py.

Writes data/model_diagnostics.json.
"""
from __future__ import annotations
import os, sys, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.inspection import permutation_importance
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from headline import lin_threshold  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
DECODERS = ["opencv", "wechat", "zbar", "zxing"]


def features(d: pd.DataFrame):
    style_d = pd.get_dummies(d["style"], prefix="st")
    dec_d = pd.get_dummies(d["decoder"], prefix="dec")
    return pd.concat([d[["ec_ord", "ppm", "contrast_ratio", "occ", "version", "inverted_i"]],
                      style_d, dec_d], axis=1).astype(float)


def boundary(d: pd.DataFrame) -> pd.Series:
    return (d["ppm"].between(2, 4)) | (d["occ"].between(4, 20))


def lopo(d: pd.DataFrame):
    out = {}
    for held in ["short", "med", "long"]:
        tr, te = d["payload"] != held, d["payload"] == held
        feat = features(d)
        y = d["success"].values
        sc = StandardScaler()
        Xtr, Xte = sc.fit_transform(feat[tr]), sc.transform(feat[te])
        lr = LogisticRegression(max_iter=2000).fit(Xtr, y[tr])
        gb = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0).fit(feat[tr], y[tr])
        te_band = te & boundary(d).values
        out[held] = {
            "n_test_rows": int(te.sum()),
            "logistic_auc": round(float(roc_auc_score(y[te], lr.predict_proba(Xte)[:, 1])), 3),
            "gbm_auc": round(float(roc_auc_score(y[te], gb.predict_proba(feat[te])[:, 1])), 3),
            "boundary_band_rows": int(te_band.sum()),
            "gbm_auc_boundary_band": round(float(roc_auc_score(y[te_band],
                                   gb.predict_proba(feat[te_band])[:, 1])), 3)
            if 0 < y[te_band].mean() < 1 else None,
            "test_band_factor_variation": {
                "occ_levels": sorted(d.loc[te_band, "occ"].unique().tolist()),
                "inverted_levels": sorted(d.loc[te_band, "inverted"].unique().tolist()),
                "contrast_levels": sorted(d.loc[te_band, "contrast_ratio"].unique().tolist()),
            },
        }
    return out


def perm_importance(d: pd.DataFrame):
    """Permutation importance of the six design-time features, pooled across decoder rows.
    Fitted on keep-only features so permutation operates on the same columns as fit."""
    tr, te = (d["payload"] != "long").values, (d["payload"] == "long").values
    keep = ["ec_ord", "ppm", "contrast_ratio", "occ", "version", "inverted_i"]
    X = d[keep].astype(float)
    y = d["success"].values
    gb = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0).fit(X[tr], y[tr])
    out = {}
    pi = permutation_importance(gb, X[te], y[te], scoring="roc_auc",
                                n_repeats=10, random_state=0)
    out["heldout_long_payload"] = {k: {"mean_auc_drop": round(float(m), 4), "std": round(float(s), 4)}
                                   for k, m, s in zip(keep, pi.importances_mean, pi.importances_std)}
    band = boundary(d).values
    tr_band = tr & band
    gb_band = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0)\
        .fit(X[tr_band], y[tr_band])
    pi2 = permutation_importance(gb_band, X[tr_band], y[tr_band], scoring="roc_auc",
                                 n_repeats=10, random_state=0)
    out["training_boundary_band"] = {k: {"mean_auc_drop": round(float(m), 4), "std": round(float(s), 4)}
                                     for k, m, s in zip(keep, pi2.importances_mean, pi2.importances_std)}
    return out


def thresholds(df: pd.DataFrame, cliff: pd.DataFrame):
    """90/95/99 worst-case occlusion ceilings per EC (+ H excluding OpenCV) and the ppm cliff,
    same curve construction as headline.py."""
    out = {"occlusion_worstcase": {}, "occlusion_H_excl_opencv": {}}
    for ec in ["L", "M", "Q", "H"]:
        sub = df[(df.exp == "G1") & (df.ppm >= 4) & (df.ec == ec)]
        levels = np.array(sorted(sub.occ.unique()), dtype=float)
        curve = np.array([sub[sub.occ == lv].groupby("decoder")["success"].mean().min() for lv in levels])
        out["occlusion_worstcase"][ec] = {str(q): round(float(lin_threshold(levels, curve, q / 100,
                                        increasing=False)), 1) for q in (90, 95, 99)}
        if ec == "H":
            curve_x = np.array([sub[sub.occ == lv].groupby("decoder")["success"].mean()
                                .drop("opencv").min() for lv in levels])
            out["occlusion_H_excl_opencv"] = {str(q): round(float(lin_threshold(levels, curve_x,
                                              q / 100, increasing=False)), 1) for q in (90, 95, 99)}
    sub = cliff[cliff.payload == "med"]
    levels = np.array(sorted(sub.ppm.unique()), dtype=float)
    curve = np.array([sub[sub.ppm == lv].groupby("decoder")["success"].mean().min() for lv in levels])
    out["min_ppm_worstcase_med"] = {str(q): round(float(lin_threshold(levels, curve, q / 100,
                                    increasing=True)), 2) for q in (90, 95, 99)}
    return out


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    df["ec_ord"] = df["ec"].map({"L": 0, "M": 1, "Q": 2, "H": 3})
    df["inverted_i"] = df["inverted"].astype(int)
    cliff = pd.read_parquet(os.path.join(DATA, "results_cliff.parquet"))

    out = {"lopo_cv": lopo(df), "permutation_importance": perm_importance(df),
           "thresholds_90_95_99": thresholds(df, cliff)}
    json.dump(out, open(os.path.join(DATA, "model_diagnostics.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    print("\nwrote data/model_diagnostics.json")


if __name__ == "__main__":
    main()
