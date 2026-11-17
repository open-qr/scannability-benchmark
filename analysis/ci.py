"""Bootstrap 95% confidence intervals for the headline numbers (data/headline_ci.json).

The design cells (EC x occlusion x ppm etc.) are fixed by the protocol, not sampled,
so the resampling unit is the stochastic capture: within every cell we resample the
N capture indices with replacement, keeping the four decoders paired per capture
(each decoder saw the same degraded image). Each replicate recomputes the full
aggregation (per-cell decode rate -> worst-case min across decoders -> curve ->
piecewise-linear P95 crossing, exactly as headline.py) so the interval reflects
the whole pipeline, not just a single proportion. Seeded and deterministic.

Writes a separate file; never touches headline.json / summary.json."""
from __future__ import annotations
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from headline import lin_threshold

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
B = 1000  # bootstrap replicates
DECODERS = ["opencv", "wechat", "zbar", "zxing"]
NON_OPENCV = ["wechat", "zbar", "zxing"]


def success_cube(df, keys):
    """(cells x decoders x samples) success array + the cell key frame.
    Requires a rectangular design (same N per cell), which run.py guarantees."""
    pv = df.pivot_table(index=keys, columns=["decoder", "sample"], values="success")
    n_samples = df["sample"].nunique()
    cube = pv.values.reshape(len(pv), len(DECODERS), n_samples)
    # pivot_table sorts columns: decoder alphabetical, sample numeric
    return cube, pv.index.to_frame(index=False)


def boot_thresholds(df, group_col, target, increasing, decoders, rng, keys):
    """Bootstrap the interpolated P95 threshold of the worst-case (min over
    `decoders`) curve aggregated over `group_col`. Returns B threshold draws."""
    cube, cells = success_cube(df, keys)
    di = [DECODERS.index(d) for d in decoders]
    groups = cells[group_col].values
    levels = np.unique(groups)
    n_cells, _, n_s = cube.shape
    out = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n_s, size=(n_cells, n_s))
        # paired resample: same capture indices for every decoder within a cell
        res = np.take_along_axis(cube[:, di, :], idx[:, None, :], axis=2)
        worst = res.mean(axis=2).min(axis=1)  # per-cell worst-case rate
        curve = np.array([worst[groups == lv].mean() for lv in levels])
        out[b] = lin_threshold(levels.astype(float), curve, target, increasing)
    return out


def ci(draws):
    d = draws[~np.isnan(draws)]
    if len(d) == 0:
        return None
    return [round(float(np.percentile(d, 2.5)), 2), round(float(np.percentile(d, 97.5)), 2)]


def rate_ci(df, rng=None):
    """Bootstrap CI for a pooled decode rate: resample captures within cells.
    All cells have equal N, so the mean of cell means equals the pooled rate."""
    g = df.groupby(["cid", "decoder"])["success"]
    means, ns = g.mean().values, g.size().values
    out = np.empty(B)
    for b in range(B):
        draws = rng.binomial(ns, np.clip(means, 0, 1)) / ns
        out[b] = draws.mean()
    return ci(out)


KEYS = ["cid", "exp", "payload", "version", "n_modules", "ec", "occ", "occ_mode",
        "contrast_ratio", "inverted", "hue", "style", "ppm"]


def main():
    rng = np.random.default_rng(0)
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    cf = pd.read_parquet(os.path.join(DATA, "results_cliff.parquet"))
    out = {"method": "bootstrap over capture indices within fixed design cells, "
                     "decoders paired per capture, B=%d, seed=0; interval = 2.5th-97.5th pct "
                     "of the recomputed interpolated P95 threshold" % B}

    occ = {}
    occ_x = {}
    for ec in ["L", "M", "Q", "H"]:
        sub = df[(df.exp == "G1") & (df.ppm >= 4) & (df.ec == ec)]
        occ[ec] = ci(boot_thresholds(sub, "occ", 0.95, False, DECODERS, rng, KEYS))
        occ_x[ec] = ci(boot_thresholds(sub, "occ", 0.95, False, NON_OPENCV, rng, KEYS))
    out["occ_p95_worstcase_ci"] = occ
    out["occ_p95_excl_opencv_ci"] = occ_x

    ppm_ci = {}
    for ec in ["L", "M", "Q", "H"]:
        sub = cf[(cf.payload == "med") & (cf.ec == ec)]
        ppm_ci[ec] = ci(boot_thresholds(sub, "ppm", 0.95, True, DECODERS, rng, KEYS))
    out["min_ppm_95_med_ci"] = ppm_ci

    sub = df[(df.exp == "G2") & (~df.inverted) & (df.ppm >= 4)]
    out["contrast_floor_worstcase_p95_ci"] = ci(
        boot_thresholds(sub, "contrast_ratio", 0.95, True, DECODERS, rng, KEYS))

    out["decoder_overall_ci"] = {d: rate_ci(df[df.decoder == d], rng=rng) for d in DECODERS}
    out["decoder_lowres_ppm2_ci"] = {d: rate_ci(df[(df.decoder == d) & (df.ppm <= 2)], rng=rng)
                                     for d in DECODERS}

    with open(os.path.join(DATA, "headline_ci.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
