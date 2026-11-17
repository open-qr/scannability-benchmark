"""Publication figures from results.parquet (+ results_cliff.parquet)."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
FIG = os.path.join(HERE, "..", "paper", "figures")
os.makedirs(FIG, exist_ok=True)

mpl.rcParams.update({
    "figure.dpi": 140, "savefig.dpi": 200, "font.size": 13,
    "axes.titlesize": 13, "axes.labelsize": 12.5, "legend.fontsize": 11.5,
    "xtick.labelsize": 11.5, "ytick.labelsize": 11.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "font.family": "DejaVu Sans",
})
INK = "#14161a"
DEC_C = {"wechat": "#2a9d8f", "zxing": "#4361ee", "zbar": "#e76f51", "opencv": "#e63946"}
EC_C = {"L": "#adb5bd", "M": "#748ffc", "Q": "#5c7cfa", "H": "#1b1f24"}

def load():
    return pd.read_parquet(os.path.join(DATA, "results.parquet"))

def worst_by(df, keys):
    pc = df.groupby(keys + ["decoder"])["success"].mean().reset_index()
    return pc.groupby(keys)["success"].min().reset_index()

# ---- Fig 1: decoder robustness gap ----
def fig_decoders(df):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.8, 3.2))
    m = df.groupby("decoder")["success"].mean().reindex(["opencv", "zbar", "zxing", "wechat"])
    a1.bar(m.index, m.values, color=[DEC_C[d] for d in m.index])
    for i, v in enumerate(m.values):
        a1.text(i, v + 0.01, f"{v:.0%}", ha="center", fontweight="bold")
    a1.set_ylim(0, 0.7); a1.set_ylabel("overall decode rate"); a1.set_title("a) Decoders are not interchangeable")
    for d in ["opencv", "zbar", "zxing", "wechat"]:
        s = df[df.decoder == d].groupby("ppm")["success"].mean()
        a2.plot(s.index, s.values, "-o", ms=4, color=DEC_C[d], label=d)
    a2.set_xlabel("pixels per module (resolution)"); a2.set_ylabel("decode rate")
    a2.set_title("b) Low resolution widens the gap"); a2.legend(frameon=False)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig1_decoders.png")); plt.close(fig)

# ---- Fig 2: occlusion ceiling vs RS budget ----
def fig_occlusion(df):
    RS = {"L": 7, "M": 15, "Q": 25, "H": 30}
    g = df[(df.exp == "G1") & (df.ppm >= 4)]
    w = worst_by(g, ["ec", "occ"])
    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    for ec in ["L", "M", "Q", "H"]:
        s = w[w.ec == ec].sort_values("occ")
        ax.plot(s.occ, s.success, "-o", ms=4, color=EC_C[ec], label=f"EC {ec}")
        ax.axvline(RS[ec], color=EC_C[ec], ls=":", alpha=0.6)
    ax.axhline(0.95, color="k", ls="--", lw=0.8, alpha=0.5)
    ax.text(24, 0.965, "95% reliable", fontsize=11, alpha=0.7)
    ax.set_xlabel("centre-logo occlusion (% of symbol area)")
    ax.set_ylabel("worst-case decode rate")
    ax.set_title("The 30% myth: measured decode vs nominal RS budget")
    ax.legend(frameon=False, title="EC level (dotted = its RS budget)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig2_occlusion.png")); plt.close(fig)

# ---- Fig 3: resolution cliff + EC illusion (cliff data) ----
def fig_cliff():
    df = pd.read_parquet(os.path.join(DATA, "results_cliff.parquet"))
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 3.1), sharey=True)
    for ax, pl, ttl in zip(axes, ["short", "med", "long"],
                           ["short URL (20 ch)", "medium URL (26 ch)", "long URL (89 ch)"]):
        w = worst_by(df[df.payload == pl], ["ec", "ppm"])
        for ec in ["L", "M", "Q", "H"]:
            s = w[w.ec == ec].sort_values("ppm")
            ax.plot(s.ppm, s.success, "-o", ms=3, color=EC_C[ec], label=f"EC {ec}")
        ax.set_title(ttl); ax.set_xlabel("pixels per module")
        ax.axvspan(2.5, 3.0, color="#ffd6d6", alpha=0.4)
    axes[0].set_ylabel("worst-case decode rate"); axes[0].legend(frameon=False)
    fig.suptitle("The resolution cliff (~3 px/module); EC level barely moves it")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig4_cliff.png")); plt.close(fig)

# ---- Fig 4: contrast + inversion ----
def fig_contrast(df):
    g = df[(df.exp == "G2") & (df.ppm >= 4)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.8, 3.3))
    for d in ["opencv", "zbar", "zxing", "wechat"]:
        s = g[(g.decoder == d) & (~g.inverted)].groupby("contrast_ratio")["success"].mean()
        a1.plot(s.index, s.values, "-o", ms=4, color=DEC_C[d], label=d)
    a1.axvline(4.5, color="k", ls="--", lw=0.8); a1.text(5.0, 0.87, "WCAG-AA\n(text) 4.5:1", fontsize=10)
    a1.axvline(3.0, color="gray", ls=":", lw=0.8)
    a1.set_xlabel("foreground/background contrast ratio (WCAG)"); a1.set_ylabel("decode rate")
    a1.set_title("a) Contrast floor is low"); a1.legend(frameon=False)
    dd = df[df.exp == "G2"]
    xs = ["opencv", "zbar", "zxing", "wechat"]
    norm = [dd[(dd.decoder == d) & (~dd.inverted)]["success"].mean() for d in xs]
    inv = [dd[(dd.decoder == d) & (dd.inverted)]["success"].mean() for d in xs]
    x = np.arange(len(xs)); wdt = 0.38
    a2.bar(x - wdt / 2, norm, wdt, label="normal (dark on light)", color="#495057")
    a2.bar(x + wdt / 2, inv, wdt, label="inverted (light on dark)", color="#e63946")
    a2.set_xticks(x); a2.set_xticklabels(xs); a2.set_ylabel("decode rate"); a2.set_ylim(0, 1.0)
    a2.set_title("b) Inversion breaks half the decoders"); a2.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig3_contrast.png")); plt.close(fig)

# ---- Fig 5: what actually predicts scannability (GBM importance) ----
def fig_importance():
    import json
    d = json.load(open(os.path.join(DATA, "summary.json")))
    imp = d["C5_model"]["feature_importance_gbm"]
    label = {"occ": "logo occlusion", "ppm": "resolution (px/module)", "inverted_i": "inversion",
             "dec_zxing": "decoder", "dec_opencv": "decoder", "dec_zbar": "decoder",
             "dec_wechat": "decoder", "ec_ord": "error-correction level", "contrast_ratio": "contrast",
             "version": "version"}
    agg = {}
    for k, v in imp.items():
        agg[label.get(k, k)] = agg.get(label.get(k, k), 0) + v
    agg = dict(sorted(agg.items(), key=lambda t: t[1]))
    fig, ax = plt.subplots(figsize=(7.0, 3.7))
    cols = ["#1b1f24" if k in ("logo occlusion", "resolution (px/module)", "inversion") else "#adb5bd" for k in agg]
    ax.barh(list(agg.keys()), list(agg.values()), color=cols)
    ax.set_xlabel("relative importance (gradient-boosted model)")
    ax.set_title("What decides if a QR scans, error correction ranks last")
    fig.subplots_adjust(left=0.28, right=0.97, top=0.9, bottom=0.13)
    fig.savefig(os.path.join(FIG, "fig5_importance.png")); plt.close(fig)

if __name__ == "__main__":
    df = load()
    fig_decoders(df); fig_occlusion(df); fig_cliff(); fig_contrast(df); fig_importance()
    print("figures ->", FIG)
    print(os.listdir(FIG))
