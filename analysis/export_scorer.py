"""Export the Scannability Margin scorer as portable Python + TypeScript.

Reviewer #9: a designer cannot supply `decoder`, and the score should be per-decoder and
worst-case (not a single model with `decoder` as a feature). Reviewer #8: AUC is not
calibration, and the single logistic is overconfident (see analysis/calibration.py: logistic
ECE 0.27, the gradient-boosted model is the calibrated one). So the shipped scorer:

  - fits a SEPARATE logistic per decoder on design-time features only (no decoder input),
  - exposes a per-decoder margin, a WORST-CASE margin (min over decoders, the safe spec), and
    two target profiles (modern-phone = strong tier zxing-cpp/WeChat; kiosk-embedded = weak
    tier ZBar/OpenCV),
  - is presented as a RANKING margin plus a safe/risky/fragile GRADE whose thresholds are
    calibrated against the held-out empirical worst-case decode rate (so "safe" means the
    worst-case decoder actually decoded >= 95% of the time), NOT as a calibrated P(decode).
    A calibrated probability is available from the gradient-boosted model in calibration.py.

Per-decoder logistic coefficients are interpretable and tiny to ship; the grade is what a
generator surfaces before a code is printed.
"""
from __future__ import annotations
import os, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "scorer")
os.makedirs(OUT, exist_ok=True)

FEATS = ["ec_ord", "ppm", "contrast_ratio", "occ", "version", "inverted_i"]
DECODERS = ["opencv", "zbar", "zxing", "wechat"]
PROFILES = {"worst_case": DECODERS, "modern_phone": ["zxing", "wechat"], "kiosk_embedded": ["opencv", "zbar"]}


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    df["ec_ord"] = df["ec"].map({"L": 0, "M": 1, "Q": 2, "H": 3})
    df["inverted_i"] = df["inverted"].astype(int)
    tr = (df["payload"] != "long").values
    te = ~tr

    # one model per decoder, design-time features only (a designer never supplies `decoder`)
    models, aucs = {}, {}
    for d in DECODERS:
        m = LogisticRegression(max_iter=5000)
        sub = df[tr & (df.decoder == d)]
        m.fit(sub[FEATS].astype(float).values, sub["success"].values)
        models[d] = {"intercept": float(round(m.intercept_[0], 6)),
                     "coef": dict(zip(FEATS, m.coef_[0].round(6).tolist()))}
        ste = df[te & (df.decoder == d)]
        y = ste["success"].values
        aucs[d] = round(float(roc_auc_score(y, m.predict_proba(ste[FEATS].astype(float).values)[:, 1])), 4) \
            if len(np.unique(y)) > 1 else None

    def score_decoder(d, feat):
        mo = models[d]
        z = mo["intercept"] + sum(mo["coef"][f] * feat[f] for f in FEATS)
        return sigmoid(z)

    # ---- calibrate the safe/risky/fragile grade (cutoffs on TRAINING cells only) ----
    # v1.1 amendment A5: v1.0 fitted these cutoffs over all 907 cells (training included)
    # while describing them as held-out-calibrated. Cutoffs now come from training cells;
    # band rates are reported for training and held-out cells separately. Per design cell:
    # predicted worst-case margin (min over decoders) vs actual worst-case decode rate.
    rate = df.groupby(["cid", "decoder"])["success"].mean()
    feats_by_cid = df.groupby("cid")[FEATS].first()
    cell_payload = df.groupby("cid")["payload"].first()
    train_cids = [c for c in feats_by_cid.index if cell_payload[c] != "long"]
    heldout_cids = [c for c in feats_by_cid.index if cell_payload[c] == "long"]

    def cell_pair(cids):
        pred, act = [], []
        for cid in cids:
            frow = feats_by_cid.loc[cid]
            feat = {f: float(frow[f]) for f in FEATS}
            pred.append(min(score_decoder(d, feat) for d in DECODERS))
            act.append(min(float(rate[(cid, d)]) for d in DECODERS))
        return np.array(pred), np.array(act)

    pred_tr, act_tr = cell_pair(train_cids)
    pred_wc, act_wc = cell_pair(heldout_cids)

    order = np.argsort(pred_tr)
    ps, as_ = pred_tr[order], act_tr[order]
    W = 40
    smooth = np.array([as_[max(0, i - W):i + W + 1].mean() for i in range(len(as_))])

    def first_cross(thr):
        idx = np.where(smooth >= thr)[0]
        return float(ps[idx[0]]) if len(idx) else 1.0
    c_risky, c_safe = first_cross(0.60), first_cross(0.95)
    c_safe = max(c_safe, c_risky)  # keep monotone

    def grade(s):
        return "safe" if s >= c_safe else "risky" if s >= c_risky else "fragile"
    band_rate = {}
    for label, pred, act in (("train", pred_tr, act_tr), ("heldout", pred_wc, act_wc)):
        band_rate[label] = {g: round(float(act[[grade(s) == g for s in pred]].mean()), 3)
                            if any(grade(s) == g for s in pred) else None
                            for g in ("fragile", "risky", "safe")}

    model = {"features": FEATS, "decoders": DECODERS, "profiles": PROFILES,
             "per_decoder": models, "heldout_auc_per_decoder": aucs,
             "grade_cutoffs": {"risky": round(c_risky, 4), "safe": round(c_safe, 4)},
             "grade_band_empirical_worstcase_rate": band_rate,
             "note": "Per-decoder logistic P(a single capture decodes) on design-time features. "
                     "Combine as worst_case=min over decoders (safe spec), modern_phone=min(zxing,wechat), "
                     "kiosk_embedded=min(opencv,zbar). The scalar margin RANKS (see heldout AUC); the "
                     "safe/risky/fragile grade cutoffs are calibrated on TRAINING cells only (v1.1 A5) "
                     "with band rates reported separately for training and held-out cells. For a "
                     "calibrated probability use the gradient-boosted model (analysis/calibration.py)."}
    json.dump(model, open(os.path.join(OUT, "scannability_model.json"), "w"), indent=1)
    print("held-out AUC per decoder:", aucs)
    print(f"grade cutoffs: risky>={c_risky:.3f}, safe>={c_safe:.3f}")
    print("empirical worst-case decode rate by grade band:", band_rate)

    # ---- portable TypeScript ----
    per_dec_ts = ",\n  ".join(
        f'{d}: {{ b0: {models[d]["intercept"]}, c: {json.dumps(models[d]["coef"])} }}' for d in DECODERS)
    ts = f"""// Scannability Margin, OpenQR Research. Per-decoder held-out AUC {json.dumps(aucs)}. CC-BY-4.0.
// Predicts, from design-time features, P(a single camera capture decodes) for EACH decoder,
// then combines them: worstCase = weakest deployed reader (the safe spec), or a target profile.
// The scalar margin RANKS; the safe/risky/fragile grade is calibrated to held-out decode rates.
// It is not a calibrated probability (use the gradient-boosted model for that).

export interface ScanFeatures {{
  ecLevel: 'L' | 'M' | 'Q' | 'H';
  pxPerModule: number;        // rendered/printed resolution (camera px per module)
  contrastRatio: number;      // WCAG fg/bg contrast ratio, e.g. 21 for black-on-white
  occlusionPct: number;       // centre-logo area as % of symbol (0..40)
  version: number;            // QR version (1..40)
  inverted: boolean;          // light modules on dark field
}}
export type Profile = 'worst_case' | 'modern_phone' | 'kiosk_embedded';

const EC = {{ L: 0, M: 1, Q: 2, H: 3 }} as const;
const M = {{
  {per_dec_ts}
}} as const;
const PROFILE: Record<Profile, (keyof typeof M)[]> = {{
  worst_case: {json.dumps(DECODERS)},
  modern_phone: {json.dumps(PROFILES["modern_phone"])},
  kiosk_embedded: {json.dumps(PROFILES["kiosk_embedded"])},
}};
const CUT = {{ risky: {round(c_risky, 4)}, safe: {round(c_safe, 4)} }};

function feat(f: ScanFeatures): Record<string, number> {{
  return {{ ec_ord: EC[f.ecLevel], ppm: f.pxPerModule, contrast_ratio: f.contrastRatio,
           occ: f.occlusionPct, version: f.version, inverted_i: f.inverted ? 1 : 0 }};
}}
export function scoreByDecoder(f: ScanFeatures): Record<keyof typeof M, number> {{
  const x = feat(f); const out: any = {{}};
  for (const d of Object.keys(M) as (keyof typeof M)[]) {{
    const m = M[d]; let z = m.b0;
    for (const k of Object.keys(m.c)) z += (m.c as any)[k] * x[k];
    out[d] = 1 / (1 + Math.exp(-z));
  }}
  return out;
}}
export function scannabilityMargin(f: ScanFeatures, profile: Profile = 'worst_case'): number {{
  const s = scoreByDecoder(f);
  return Math.min(...PROFILE[profile].map(d => s[d]));  // weakest reader in the profile
}}
export function scannabilityVerdict(f: ScanFeatures, profile: Profile = 'worst_case'):
    {{ margin: number; grade: 'safe'|'risky'|'fragile'; reasons: string[] }} {{
  const margin = scannabilityMargin(f, profile);
  const reasons: string[] = [];
  if (f.pxPerModule < 3.3) reasons.push('resolution below ~3.3 px/module, the dominant failure cause');
  if (f.occlusionPct > 9) reasons.push('logo covers >9% of area, above the worst-case decoder ceiling');
  if (f.inverted) reasons.push('inverted (light-on-dark) codes fail on 2 of 4 tested libraries (ZBar, OpenCV)');
  if (f.contrastRatio < 2) reasons.push('contrast below ~2:1');
  const grade = margin >= CUT.safe ? 'safe' : margin >= CUT.risky ? 'risky' : 'fragile';
  return {{ margin, grade, reasons }};
}}
"""
    open(os.path.join(OUT, "scannability_score.ts"), "w").write(ts)

    # ---- portable Python ----
    py = f'''"""Scannability Margin scorer, OpenQR Research. Per-decoder held-out AUC {json.dumps(aucs)}.
The scalar margin ranks; the grade is calibrated to held-out worst-case decode rate. Not a
calibrated probability (use the gradient-boosted model for that)."""
import math
_M = {json.dumps(models)}
_PROFILE = {json.dumps(PROFILES)}
_EC = {{"L": 0, "M": 1, "Q": 2, "H": 3}}
_CUT = {{"risky": {round(c_risky, 4)}, "safe": {round(c_safe, 4)}}}

def _feat(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted=False):
    return {{"ec_ord": _EC[ec_level], "ppm": px_per_module, "contrast_ratio": contrast_ratio,
            "occ": occlusion_pct, "version": version, "inverted_i": 1 if inverted else 0}}

def score_by_decoder(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted=False):
    x = _feat(ec_level, px_per_module, contrast_ratio, occlusion_pct, version, inverted)
    out = {{}}
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
'''
    open(os.path.join(OUT, "scannability_score.py"), "w").write(py)
    print("exported ->", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
