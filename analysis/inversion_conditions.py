"""Reviewer point #3 rerun: disentangle QR module polarity from quiet-zone polarity.

The committed "inverted" condition inverts the symbol field TOGETHER with its quiet
zone (a dark quiet zone), so it confounds module polarity with a nonstandard
quiet-zone polarity. This script separates the two by rendering four conditions and
decoding N stochastic captures with all four library decoders, reusing the study's
own harness (qrgen.render, degrade.degrade, decoders.Decoders) and the EXACT
per-sample nuisance sampling used in run.py.

Conditions (med payload, all EC levels, ppm in {2,4,6,8}):
  1. normal            dark modules on light field, light quiet zone (fg=black, bg=white)
  2. full_inverse      light modules on dark field, DARK quiet zone (fg=white, bg=black)
                       -- the committed aesthetic inverse
  3. inverse_light_qz  inverted SYMBOL (light modules on dark field) but a COMPLIANT
                       LIGHT quiet zone (render full_inverse, then paint the outer
                       quiet-zone frame white)
  4. preinverted       render full_inverse, degrade as usual, then invert the pixels
                       (255 - array) before decoding -- a one-line preprocessing step

Writes data/inversion_conditions.json. Does not touch any committed artefact.
"""
from __future__ import annotations
import os, sys, json, hashlib
import numpy as np

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, "..", "harness"))
from qrgen import build_matrix, render          # noqa: E402
from degrade import degrade                      # noqa: E402
from decoders import Decoders                     # noqa: E402

DATA = os.path.join(_HERE, "..", "data")

PAYLOAD = "https://openqr.uk/r/aB3xK9"   # 'med'
ECS = ["L", "M", "Q", "H"]
PPMS = [2, 4, 6, 8]
CONDITIONS = ["normal", "full_inverse", "inverse_light_qz", "preinverted"]
MODULE_PX = 16
QUIET = 4
N = 16
DECODERS = ["zbar", "opencv", "wechat", "zxing"]


def cell_id(ec: str, ppm: int, cond: str) -> str:
    key = f"ec={ec}|ppm={ppm}|cond={cond}|payload=med|module_px={MODULE_PX}|quiet={QUIET}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def render_base(sym, cond: str):
    """Return the clean PIL render for a condition (before degradation).

    preinverted shares full_inverse's render; the pixel inversion is applied
    post-degradation, so it renders identically here.
    """
    if cond == "normal":
        return render(sym, module_px=MODULE_PX, quiet=QUIET, fg=(0, 0, 0), bg=(255, 255, 255))
    # full_inverse / inverse_light_qz / preinverted all start from the aesthetic inverse
    img = render(sym, module_px=MODULE_PX, quiet=QUIET, fg=(255, 255, 255), bg=(0, 0, 0))
    if cond == "inverse_light_qz":
        arr = np.array(img)
        b = QUIET * MODULE_PX  # outer quiet-zone frame width in pixels
        arr[:b, :, :] = 255
        arr[-b:, :, :] = 255
        arr[:, :b, :] = 255
        arr[:, -b:, :] = 255
        from PIL import Image
        img = Image.fromarray(arr)
    return img


def run():
    dec = Decoders()  # 4 decoders; raises if WeChat models are unavailable
    records = []       # per (ec, ppm, condition, decoder) mean decode rate
    for ec in ECS:
        sym = build_matrix(PAYLOAD, ec)
        for ppm in PPMS:
            for cond in CONDITIONS:
                cid = cell_id(ec, ppm, cond)
                img = render_base(sym, cond)
                succ = {d: 0 for d in DECODERS}
                for s in range(N):
                    # EXACT copy of run.py per-sample stochastic nuisance sampling
                    rng = np.random.default_rng(int(cid[:8], 16) + s)
                    rot = rng.uniform(-8, 8)
                    tilt = rng.uniform(0, 8)
                    noise = float(rng.choice([0, 2, 5, 8]))
                    jpeg = int(rng.choice([50, 75, 90, 100]))
                    blur = float(rng.uniform(0.3, 0.9))
                    bgr = degrade(img, sym.n, QUIET, ppm=ppm, blur_sigma=blur,
                                  noise_sigma=noise, jpeg_q=jpeg, rot_deg=rot,
                                  tilt_deg=tilt, rng=rng)
                    if cond == "preinverted":
                        bgr = 255 - bgr
                    for r in dec.all(bgr, PAYLOAD):
                        succ[r.name] += int(r.success)
                for d in DECODERS:
                    records.append(dict(ec=ec, ppm=ppm, condition=cond, decoder=d,
                                        version=int(sym.version), n_modules=int(sym.n),
                                        n=N, rate=succ[d] / N))
            print(f"  done ec={ec} ppm={ppm}", flush=True)
    return records


def aggregate(records, ppm_min=None):
    """Mean rate per (condition, decoder), optionally restricted to ppm>=ppm_min."""
    acc = {}
    for r in records:
        if ppm_min is not None and r["ppm"] < ppm_min:
            continue
        acc.setdefault((r["condition"], r["decoder"]), []).append(r["rate"])
    return {k: float(np.mean(v)) for k, v in acc.items()}


def fmt_table(agg, title):
    lines = [title, "-" * len(title)]
    header = f"{'decoder':<8} " + " ".join(f"{c:>16}" for c in CONDITIONS)
    lines.append(header)
    for d in DECODERS:
        row = f"{d:<8} " + " ".join(f"{agg.get((c, d), float('nan')):>16.3f}" for c in CONDITIONS)
        lines.append(row)
    return "\n".join(lines)


def main():
    records = run()

    agg_ge4 = aggregate(records, ppm_min=4)
    print()
    print(fmt_table(agg_ge4, "Decode rate per decoder x condition (pooled over all EC, ppm>=4)"))

    print()
    print("Per-ppm breakdown (pooled over all EC)")
    print("=" * 40)
    ppm_break = {}
    for ppm in PPMS:
        agg_p = aggregate([r for r in records if r["ppm"] == ppm])
        ppm_break[ppm] = {c: {d: agg_p.get((c, d)) for d in DECODERS} for c in CONDITIONS}
        print()
        print(fmt_table(agg_p, f"ppm={ppm}"))

    out = dict(
        meta=dict(payload=PAYLOAD, ecs=ECS, ppms=PPMS, conditions=CONDITIONS,
                  module_px=MODULE_PX, quiet=QUIET, n_captures=N, decoders=DECODERS,
                  note="reviewer point #3: separate module polarity from quiet-zone polarity"),
        records=records,
        agg_ppm_ge4={c: {d: agg_ge4.get((c, d)) for d in DECODERS} for c in CONDITIONS},
        ppm_breakdown={str(k): v for k, v in ppm_break.items()},
    )
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "inversion_conditions.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("wrote", os.path.abspath(path))


if __name__ == "__main__":
    main()
