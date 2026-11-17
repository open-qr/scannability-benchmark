"""Encoding mode -> QR version -> module density (reviewer #10: the benchmark only
used URL / byte-mode payloads).

QR-Code has three text encoding modes with very different packing density:
numeric packs ~3.3 chars per data codeword, alphanumeric ~1.6, byte exactly 1.
So the SAME visible character budget can force three different QR *versions* (and
therefore three different module counts n). At a fixed physical print size a higher
version = smaller modules = fewer px/module for a camera, which is precisely the
resolution axis the paper is about. This script shows that mechanism directly and
then confirms the decode cliff sits at the same ~px/module regardless of mode, so
mode acts on scannability *through version/layout*, not through a mode-specific cliff.

Reads segno's actual selected mode/version/error (segno.make(..., micro=False):
q.mode, q.version, q.error) and the standard data-bit capacity table
(segno.consts.SYMBOL_CAPACITY[version][error_code]). Renders + degrades with the
study's exact nuisance sampling (harness/run.py) and decodes with all four decoders.

Writes data/payload_modes.json. Does not touch existing data or the paper.
"""
from __future__ import annotations
import os, sys, json, hashlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import segno
from segno import consts
from qrgen import build_matrix, render          # noqa: E402
from degrade import degrade                      # noqa: E402
from decoders import Decoders                    # noqa: E402

DATA = os.path.join(HERE, "..", "data")
ECS = ["L", "M", "Q", "H"]
# segno / QR-spec error-level -> capacity-table key
ERR_CODE = {"L": consts.ERROR_LEVEL_L, "M": consts.ERROR_LEVEL_M,
            "Q": consts.ERROR_LEVEL_Q, "H": consts.ERROR_LEVEL_H}

# --- payload set ----------------------------------------------------------
# Matched 25-character set: identical character *count*, only the charset differs,
# so the ONLY thing that moves version is the encoding mode segno must pick.
MATCHED = [
    ("num25",   "1234567890123456789012345"),                 # digits only  -> numeric
    ("alnum25", "ABCDEFGHIJ0123456789KLMNO"),                 # A-Z + digits -> alphanumeric
    ("byte25",  "abcdefghij0123456789klmno"),                 # has lowercase -> byte
]
# Representative "natural" payloads per mode (each at a length that fits), plus the
# study's real 'med' URL as the anchor (26 chars, byte mode).
REPRESENTATIVE = [
    ("numeric_natural",     "314159265358979323846264338327950288"),      # 36 digits
    ("alphanumeric_natural", "HTTPS://OPENQR.UK/PROMO/SUMMER2026SALE"),    # uppercase URL -> alnum
    ("byte_natural",        "https://openqr.uk/promo/summer2026sale"),     # lowercase URL -> byte
    ("med_url_anchor",      "https://openqr.uk/r/aB3xK9"),                 # the study 'med' payload
]

SWEEP_PPMS = [2, 3, 4, 6]
SWEEP_N = 12
MODULE_PX = 16
QUIET = 4


def describe(name: str, payload: str) -> dict:
    """Per-EC segno-selected mode/version/n/effective-error + data capacity."""
    rows = {}
    for ec in ECS:
        q = segno.make(payload, error=ec.lower(), micro=False)
        eff = q.error                       # segno may boost EC when there is spare room
        bits = consts.SYMBOL_CAPACITY[q.version][ERR_CODE[eff]]
        rows[ec] = {
            "mode": q.mode if q.mode is not None else "mixed",
            "version": q.version,
            "n_modules": q.symbol_size(border=0)[0],
            "requested_ec": ec,
            "effective_ec": eff,             # differs from requested only when boosted
            "boosted": eff != ec,
            "data_bits": bits,
            "data_codewords": bits // 8,
        }
    return {"name": name, "payload": payload, "chars": len(payload), "by_ec": rows}


def decode_sweep(payloads) -> dict:
    """Render one representative per mode at EC H, degrade at each ppm with the
    study's stochastic nuisance model, decode with all four decoders, report rate."""
    dec = Decoders()
    out = {}
    for name, payload in payloads:
        sym = build_matrix(payload, "H")
        img = render(sym, module_px=MODULE_PX, quiet=QUIET)
        per_ppm = {}
        for ppm in SWEEP_PPMS:
            cid = hashlib.md5(f"payload_modes|{name}|{ppm}".encode()).hexdigest()[:12]
            succ = tot = 0
            per_dec = {d: [0, 0] for d in dec.names}
            for s in range(SWEEP_N):
                rng = np.random.default_rng(int(cid[:8], 16) + s)
                rot = rng.uniform(-8, 8)
                tilt = rng.uniform(0, 8)
                noise = float(rng.choice([0, 2, 5, 8]))
                jpeg = int(rng.choice([50, 75, 90, 100]))
                blur = float(rng.uniform(0.3, 0.9))
                bgr = degrade(img, sym.n, QUIET, ppm=ppm, blur_sigma=blur,
                              noise_sigma=noise, jpeg_q=jpeg, rot_deg=rot,
                              tilt_deg=tilt, rng=rng)
                for r in dec.all(bgr, payload):
                    tot += 1
                    succ += int(r.success)
                    per_dec[r.name][0] += int(r.success)
                    per_dec[r.name][1] += 1
            per_ppm[str(ppm)] = {
                "decode_rate": round(succ / tot, 3),
                "n_attempts": tot,
                "per_decoder": {d: round(v[0] / v[1], 3) for d, v in per_dec.items()},
            }
        out[name] = {"version": sym.version, "n_modules": sym.n,
                     "mode": segno.make(payload, error="h", micro=False).mode,
                     "by_ppm": per_ppm}
    return out


def _fmt_matched_table(entries) -> str:
    lines = []
    hdr = f"{'payload':<9} {'chars':>5} {'EC':>3} {'mode':>13} {'ver':>4} {'n':>4} {'eff_ec':>7} {'d.cw':>5}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for e in entries:
        for ec in ECS:
            r = e["by_ec"][ec]
            boost = "*" if r["boosted"] else " "
            lines.append(f"{e['name']:<9} {e['chars']:>5} {ec:>3} {r['mode']:>13} "
                         f"{r['version']:>4} {r['n_modules']:>4} {r['effective_ec']+boost:>7} "
                         f"{r['data_codewords']:>5}")
        lines.append("")
    lines.append("* = segno boosted the EC (spare capacity at that version); version/n unchanged.")
    return "\n".join(lines)


def main():
    matched = [describe(n, p) for n, p in MATCHED]
    representative = [describe(n, p) for n, p in REPRESENTATIVE]
    sweep = decode_sweep(MATCHED)   # num25 / alnum25 / byte25 at EC H

    result = {
        "note": ("Same character count, different encoding mode -> different QR version "
                 "and module count n. numeric ~3.3 chars/codeword, alphanumeric ~1.6, byte 1. "
                 "At fixed physical size a higher version = smaller modules = fewer px/module."),
        "matched_25char": matched,
        "representative": representative,
        "decode_sweep_ecH": {
            "ppms": SWEEP_PPMS, "captures_per_cell": SWEEP_N,
            "decoders": ["zbar", "opencv", "wechat", "zxing"],
            "results": sweep,
        },
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "payload_modes.json"), "w") as f:
        json.dump(result, f, indent=1)

    # ---- printed tables --------------------------------------------------
    print("\n=== MATCHED 25-CHARACTER SET (same count, mode -> version) ===\n")
    print(_fmt_matched_table(matched))

    print("\n=== REPRESENTATIVE PAYLOADS + med-URL anchor ===\n")
    print(_fmt_matched_table(representative))

    print("\n=== DECODE SWEEP @ EC H  (rate over "
          f"{SWEEP_N} captures x 4 decoders = {SWEEP_N*4} attempts/cell) ===\n")
    hdr = f"{'payload':<9} {'mode':>13} {'ver':>4} {'n':>4} " + " ".join(f"ppm{p:>2}" for p in SWEEP_PPMS)
    print(hdr); print("-" * len(hdr))
    for name, _ in MATCHED:
        r = sweep[name]
        rates = " ".join(f"{r['by_ppm'][str(p)]['decode_rate']:>6.3f}" for p in SWEEP_PPMS)
        print(f"{name:<9} {r['mode']:>13} {r['version']:>4} {r['n_modules']:>4}  {rates}")

    print("\nwrote", os.path.join(os.path.relpath(DATA, os.path.join(HERE, '..')), "payload_modes.json"))


if __name__ == "__main__":
    main()
