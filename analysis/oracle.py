"""Oracle decode: separate front-end (capture/detection) failure from symbol-channel
(codeword / Reed-Solomon) capacity, answering reviewer R2-1 ("front-end-limited" was
asserted, not shown).

Method. The main benchmark decodes each occluded symbol through the full capture proxy
(area-resample to a target ppm, optical blur, sensor noise, JPEG, geometric jitter). Its
worst-case 95%-success occlusion ceiling is ~9% area at level H. Here we decode the *same*
occluded symbols under a PRISTINE capture: rendered large and fed to the libraries with no
blur, noise, JPEG or geometric jitter. That bypasses the capture-degradation front-end and
leaves only the real decoders' own detection + Reed-Solomon error correction. So:

  - occlusion the pristine decode still reads, but the degraded pipeline does not
      => failure in that band is FRONT-END / capture limited (the codewords survived).
  - occlusion at which even the pristine decode fails
      => the true symbol-channel / RS-capacity ceiling (as realized by the library RS stage,
         which corrects errors at unknown positions, i.e. t = floor((n-k)/2) per block, half
         the erasure budget, the honest bound when the reader does not know the logo location).

We report both ceilings per EC and the gap between them. A large gap is the evidence that the
9% figure is front-end limited. Deterministic, no stochastic sampling (the pristine capture
has no nuisance to average). Writes data/oracle.json.
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import cv2
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
sys.path.insert(0, os.path.dirname(__file__))
from qrgen import build_matrix, render, apply_center_logo  # noqa: E402
from decoders import Decoders  # noqa: E402
from headline import lin_threshold  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
PAYLOAD = "https://openqr.uk/r/aB3xK9"      # the 'med' payload class (byte, 26 chars)
DECODERS = ["opencv", "wechat", "zbar", "zxing"]
OCC = list(range(0, 46, 2))                  # fine occlusion sweep, 0..44% area
MODULE_PX = 12                               # large, so a module is many pixels: no resolution limit


def pristine_bgr(payload, ec, occ):
    """Render the occluded symbol large and clean, no degradation at all."""
    sym = build_matrix(payload, ec)
    img = render(sym, module_px=MODULE_PX, quiet=4, fg=(0, 0, 0), bg=(255, 255, 255), style="square")
    img = apply_center_logo(img, sym, occ / 100.0, quiet=4, mode="hard", bg=(255, 255, 255))
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def pristine_ceiling(dec, ec):
    """Per-decoder highest occ (contiguous from 0) that still decodes under a pristine capture,
    and the full pass/fail vector. 'ceiling' = last occ level before the first miss."""
    ok = {d: [] for d in DECODERS}
    for occ in OCC:
        bgr = pristine_bgr(PAYLOAD, ec, occ)
        res = {r.name: int(r.success) for r in dec.all(bgr, PAYLOAD)}
        for d in DECODERS:
            ok[d].append(res[d])
    ceil = {}
    for d in DECODERS:
        v = ok[d]
        c = -1
        for i, o in enumerate(OCC):
            if v[i]:
                c = o
            else:
                break            # first miss = ceiling (contiguous survival from 0)
        ceil[d] = c
    return ceil, ok


def degraded_ceiling(df, ec):
    """Reproduce the paper's degraded worst-case 95%-success occlusion ceiling for this EC
    (exp G1, ppm>=4, worst-case = min over decoders), same interpolation as headline.py."""
    sub = df[(df.exp == "G1") & (df.ppm >= 4) & (df.ec == ec)]
    levels = np.array(sorted(sub.occ.unique()), dtype=float)
    curve = []
    for lv in levels:
        cell = sub[sub.occ == lv]
        per_dec = cell.groupby("decoder")["success"].mean()
        curve.append(per_dec.min())            # worst-case decoder at this occ
    return float(lin_threshold(levels, np.array(curve), 0.95, increasing=False))


def main():
    df = pd.read_parquet(os.path.join(DATA, "results.parquet"))
    dam = json.load(open(os.path.join(DATA, "damage.json")))
    dec = Decoders(want_wechat=True)
    out = {"payload": PAYLOAD, "payload_chars": len(PAYLOAD), "occ_sweep": OCC,
           "module_px_pristine": MODULE_PX,
           "method": "pristine (no blur/noise/JPEG/jitter) decode of the occluded symbol vs the "
                     "degraded-pipeline ceiling; gap = front-end/capture-limited band. Library RS "
                     "corrects errors at unknown positions (t=floor((n-k)/2) per block).",
           "per_ec": {}}
    print(f"{'EC':>2} {'ver':>3}  {'degraded95':>10}  {'pristine worst-case':>19}  {'gap':>6}")
    for ec in ["L", "M", "Q", "H"]:
        ceil, ok = pristine_ceiling(dec, ec)
        deg = round(degraded_ceiling(df, ec), 1)
        worst_pristine = min(ceil.values())    # the occ even the weakest decoder survives pristine
        ver = dam["per_ec"][ec]["version"]
        # module damage context at the two ceilings (from damage.py's committed decomposition)
        rows = {r["occ_pct"]: r for r in dam["per_ec"][ec]["rows"]}
        def changed(o):
            o = min(rows, key=lambda k: abs(k - o))
            return rows[o]["changed_modules_pct"]
        out["per_ec"][ec] = {
            "version": ver,
            "degraded_worstcase_p95_occ": deg,
            "pristine_ceiling_by_decoder": ceil,
            "pristine_worstcase_occ": worst_pristine,
            "pristine_best_occ": max(ceil.values()),
            "gap_occ_points": round(worst_pristine - deg, 1),
            "modules_changed_pct_at_degraded_ceiling": changed(deg),
            "modules_changed_pct_at_pristine_ceiling": changed(worst_pristine),
            "pass_vectors": {d: ok[d] for d in DECODERS},
        }
        print(f"{ec:>2} {ver:>3}  {deg:>9.1f}%  {worst_pristine:>17}%  {worst_pristine-deg:>+5.0f}")
    json.dump(out, open(os.path.join(DATA, "oracle.json"), "w"), indent=1)
    print("\nwrote data/oracle.json")
    h = out["per_ec"]["H"]
    print(f"\nH (v{h['version']}): degraded worst-case ceiling {h['degraded_worstcase_p95_occ']}% area; "
          f"pristine worst-case ceiling {h['pristine_worstcase_occ']}% area "
          f"(best decoder {h['pristine_best_occ']}%). The {h['gap_occ_points']}-point gap decodes "
          f"cleanly with no capture degradation, so failure across it is front-end/capture limited, "
          f"not codeword loss ({h['modules_changed_pct_at_pristine_ceiling']}% of modules changed at "
          f"the pristine ceiling vs {h['modules_changed_pct_at_degraded_ceiling']}% at the degraded ceiling).")


if __name__ == "__main__":
    main()
