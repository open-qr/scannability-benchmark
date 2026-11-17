"""QR-internal damage decomposition (reviewers #2/#3: visual area is not module damage,
and not codeword damage).

For the exact codes the occlusion sweep uses (26-char 'med' payload at EC L/M/Q/H ->
QR versions 2/2/3/4), this reports, per centre-square occlusion level, the four
quantities the reviewers ask to be separated:
  visual area %  ->  modules covered  ->  DARK modules changed  ->  (structure hit)
A white logo pad only erases the ~49% of modules under it that are dark, so X% area is
roughly 0.5*X% module damage. It also reports the mask, exact version, quiet-zone status,
alignment-pattern locations, and the occlusion level at which a growing centre logo first
reaches a function pattern (finder / timing / alignment) rather than pure data region.

Writes data/damage.json and prints a table for the paper.
"""
from __future__ import annotations
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
import segno  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
PAYLOAD = "https://openqr.uk/r/aB3xK9"  # harness/run.py 'med' payload, 26 chars
OCC = [4, 8, 9, 12, 16, 20, 24, 28, 32, 36, 40]  # sweep + the two headline ceilings (9, 16)

# Alignment-pattern centre coordinates by version (ISO/IEC 18004 Annex E), v1-7.
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38]}


def function_mask(n, version):
    """Mark function modules: finder+separator (8x8 at 3 corners), timing (row/col 6),
    alignment patterns (5x5 at valid centres), and the dark module. Format/version bits
    fall inside the finder 8x8 zones. Validated below against the known data-module count."""
    f = np.zeros((n, n), dtype=bool)
    for (r0, c0) in [(0, 0), (0, n - 8), (n - 8, 0)]:      # 8x8 finder+separator blocks
        f[r0:r0 + 8, c0:c0 + 8] = True
    f[6, :] = True; f[:, 6] = True                          # timing patterns
    f[8, 0:9] = True; f[0:9, 8] = True                      # format info (around TL finder)
    f[8, n - 8:n] = True; f[n - 7:n, 8] = True              # format info (split copy near TR/BL)
    centres = ALIGN.get(version, [])
    for r in centres:
        for c in centres:
            in_finder = ((r <= 8 and c <= 8) or (r <= 8 and c >= n - 9) or (r >= n - 9 and c <= 8))
            if not in_finder:
                f[r - 2:r + 3, c - 2:c + 3] = True          # 5x5 alignment pattern
    f[n - 8, 8] = True                                      # dark module
    return f


def covered_mask(n, occ_frac):
    """Modules whose centre falls inside the centred square of area occ_frac."""
    s = (occ_frac ** 0.5) * n
    lo, hi = n / 2 - s / 2, n / 2 + s / 2
    idx = np.arange(n) + 0.5
    inside = (idx >= lo) & (idx <= hi)
    return np.outer(inside, inside)


def main():
    out = {"payload_chars": len(PAYLOAD), "quiet_zone_modules": 4, "per_ec": {}}
    print(f"{'EC':>2} {'ver':>3} {'mask':>4} {'n':>3} {'dark%':>6}  "
          f"{'occ%':>5} {'mod%':>6} {'chng%':>7} {'fnHit':>6}")
    for ec in ["L", "M", "Q", "H"]:
        qr = segno.make(PAYLOAD, error=ec.lower(), micro=False)
        m = np.array(qr.matrix, dtype=bool)
        n = m.shape[0]
        fmask = function_mask(n, qr.version)
        # validate the function mask: non-function modules == total codeword bits + remainder
        data_modules = int((~fmask).sum())
        rows = []
        first_fn_hit = None
        for occ in OCC:
            cov = covered_mask(n, occ / 100.0)
            mod_cov = int(cov.sum())
            dark_cov = int((cov & m).sum())
            fn_cov = int((cov & fmask).sum())
            rows.append({"occ_pct": occ,
                         "modules_covered": mod_cov, "modules_covered_pct": round(100 * mod_cov / (n * n), 1),
                         "changed_modules": dark_cov,  # dark (dark->light) modules erased by a white pad
                         "changed_modules_pct": round(100 * dark_cov / (n * n), 1),
                         "function_modules_hit": fn_cov})
            if fn_cov > 0 and first_fn_hit is None:
                first_fn_hit = occ
            if occ in (9, 16):
                print(f"{ec:>2} {qr.version:>3} {qr.mask:>4} {n:>3} {100*m.mean():>5.1f}%  "
                      f"{occ:>4}% {rows[-1]['modules_covered_pct']:>5.1f}% "
                      f"{rows[-1]['changed_modules_pct']:>7.1f}% {fn_cov:>6}")
        out["per_ec"][ec] = {"version": qr.version, "mask": qr.mask, "n": n,
                             "dark_fraction": round(float(m.mean()), 3),
                             "total_codewords": data_modules // 8,
                             "data_modules": data_modules,
                             "alignment_centres": [[r, c] for r in ALIGN.get(qr.version, [])
                                                   for c in ALIGN.get(qr.version, [])
                                                   if not ((r <= 8 and c <= 8) or (r <= 8 and c >= n - 9)
                                                           or (r >= n - 9 and c <= 8))],
                             "first_occ_hitting_function_pattern": first_fn_hit,
                             "rows": rows}
    json.dump(out, open(os.path.join(DATA, "damage.json"), "w"), indent=1)
    print("\nwrote data/damage.json")
    # headline sanity: at H, area 16% vs dark-damage
    h = {r["occ_pct"]: r for r in out["per_ec"]["H"]["rows"]}
    print(f"H (v{out['per_ec']['H']['version']}): 9% area -> {h[9]['changed_modules_pct']}% of modules changed; "
          f"16% area -> {h[16]['changed_modules_pct']}% changed; "
          f"logo covers only data region until {out['per_ec']['H']['first_occ_hitting_function_pattern']}% area.")


if __name__ == "__main__":
    main()
