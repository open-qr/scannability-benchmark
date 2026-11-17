"""Calibration of the Scannability Margin model (reviewer #9: AUC is not calibration).

Reproduces the C5 model from analyze.py exactly (same features, same payload=="long"
holdout), then reports on the held-out set: reliability curve, Brier score, expected
calibration error (ECE), and per-decoder calibration, for the logistic and the
gradient-boosted model, plus an isotonic-recalibrated GBM. Writes data/calibration.json
and paper/figures/fig6_calibration.png. This tells us whether the score can be surfaced
as a probability or should stay a ranking score.
"""
from __future__ import annotations
import os, json
import numpy as np, pandas as pd
import matplotlib as mpl, matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import roc_auc_score, brier_score_loss

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
FIG = os.path.join(HERE, "..", "paper", "figures")
mpl.rcParams.update({"figure.dpi": 140, "savefig.dpi": 200, "font.size": 13,
    "axes.titlesize": 13, "axes.labelsize": 12.5, "legend.fontsize": 11.5,
    "xtick.labelsize": 11.5, "ytick.labelsize": 11.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "font.family": "DejaVu Sans"})


def _r(x, n=4):
    return None if x != x else round(float(x), n)


def ece(y, p, bins=10):
    """Expected calibration error over equal-width probability bins."""
    edges = np.linspace(0, 1, bins + 1)
    e, n = 0.0, len(y)
    for i in range(bins):
        m = (p >= edges[i]) & (p <= edges[i + 1]) if i == bins - 1 else (p >= edges[i]) & (p < edges[i + 1])
        if m.sum() == 0:
            continue
        e += (m.sum() / n) * abs(y[m].mean() - p[m].mean())
    return e


def build(df):
    d = df.copy()
    d["ec_ord"] = d["ec"].map({"L": 0, "M": 1, "Q": 2, "H": 3})
    d["inverted_i"] = d["inverted"].astype(int)
    style_d = pd.get_dummies(d["style"], prefix="st")
    dec_d = pd.get_dummies(d["decoder"], prefix="dec")
    feat = pd.concat([d[["ec_ord", "ppm", "contrast_ratio", "occ", "version", "inverted_i"]],
                      style_d, dec_d], axis=1).astype(float)
    y = d["success"].values.astype(int)
    tr = (d["payload"] != "long").values
    te = ~tr
    return feat, y, tr, te, d["decoder"].values


def metrics(y, p):
    return {"brier": _r(brier_score_loss(y, p)), "ece": _r(ece(y, p)),
            "auc": _r(roc_auc_score(y, p)), "mean_pred": _r(p.mean()), "base_rate": _r(y.mean())}


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    feat, y, tr, te, decoder = build(df)
    sc = StandardScaler()
    Xtr, Xte = sc.fit_transform(feat[tr]), sc.transform(feat[te])
    yte = y[te]

    lr = LogisticRegression(max_iter=2000).fit(Xtr, y[tr])
    p_lr = lr.predict_proba(Xte)[:, 1]
    gb = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0).fit(feat[tr], y[tr])
    p_gb = gb.predict_proba(feat[te])[:, 1]
    # isotonic recalibration of the GBM, fit on a held-in split (prefit on train, calibrate on train via CV)
    gb_iso = CalibratedClassifierCV(GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0),
                                    method="isotonic", cv=3).fit(feat[tr], y[tr])
    p_iso = gb_iso.predict_proba(feat[te])[:, 1]

    out = {"heldout": "payload==long", "n_test": int(te.sum()),
           "logistic": metrics(yte, p_lr), "gbm": metrics(yte, p_gb),
           "gbm_isotonic": metrics(yte, p_iso), "per_decoder_gbm": {}}
    dte = decoder[te]
    for dec in ["opencv", "zbar", "zxing", "wechat"]:
        m = dte == dec
        if m.sum() > 20:
            out["per_decoder_gbm"][dec] = metrics(yte[m], p_gb[m])

    json.dump(out, open(os.path.join(DATA, "calibration.json"), "w"), indent=1)

    # reliability diagram
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    ax.plot([0, 1], [0, 1], "--", color="#888", lw=1, label="perfect")
    for p, lab, col in [(p_lr, f"logistic (ECE {out['logistic']['ece']:.3f})", "#748ffc"),
                        (p_gb, f"gradient-boosted (ECE {out['gbm']['ece']:.3f})", "#e63946"),
                        (p_iso, f"GBM + isotonic (ECE {out['gbm_isotonic']['ece']:.3f})", "#2a9d8f")]:
        frac, mean = calibration_curve(yte, p, n_bins=10, strategy="uniform")
        ax.plot(mean, frac, "-o", ms=4, color=col, label=lab)
    ax.set_xlabel("predicted P(decode)"); ax.set_ylabel("observed decode rate")
    ax.set_title("Scannability Margin calibration (held-out long payload)")
    ax.legend(frameon=False, loc="upper left"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig6_calibration.png")); plt.close(fig)

    print("calibration.json:", json.dumps(out, indent=1))
    print("wrote paper/figures/fig6_calibration.png")


if __name__ == "__main__":
    main()
