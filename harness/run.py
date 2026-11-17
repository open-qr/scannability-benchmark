"""Orchestrator: enumerate the pre-registered design, render each cell once,
apply N stochastic 'captures', decode with all four decoders, write per-attempt
rows to data/results.parquet. Reproducible via fixed seeds.

Usage:
  python run.py --smoke        # tiny sanity run
  python run.py --full [-n 16] [-j 8]
"""
from __future__ import annotations
import argparse, os, sys, time, itertools, hashlib
import numpy as np
import pandas as pd
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(__file__))
from qrgen import build_matrix, render, apply_center_logo, grey_for_ratio, contrast_ratio
from degrade import degrade
from decoders import Decoders

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

PAYLOADS = {
    "short": "https://oqr.to/aB3xK",
    "med":   "https://openqr.uk/r/aB3xK9",
    "long":  "https://openqr.uk/r/aB3xK9?utm_source=print&utm_medium=poster&utm_campaign=launch2026&v=2",
}
ECS = ["L", "M", "Q", "H"]
PPMS = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
OCCS = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40]
CRS = [1.5, 2, 3, 4.5, 7, 10, 15, 21]
HUES = {
    "navy_cream":  ((20, 30, 70), (250, 245, 220)),
    "red_white":   ((200, 20, 20), (255, 255, 255)),
    "green_white": ((10, 110, 40), (255, 255, 255)),
}

BASE = dict(payload="med", ec="Q", occ=0, occ_mode="hard", cr=21.0,
            inverted=False, hue="mono", style="square", ppm=6.0)

def cell_id(c: dict) -> str:
    key = "|".join(f"{k}={c[k]}" for k in sorted(c))
    return hashlib.md5(key.encode()).hexdigest()[:12]

def gen_cells():
    seen = set()
    def add(**over):
        c = dict(BASE); c.update(over); c["cid"] = cell_id({k: c[k] for k in BASE})
        if c["cid"] not in seen:
            seen.add(c["cid"]); cells.append(c)
    cells = []
    # G1  EC x occlusion x ppm   (C1, C4)
    for ec, occ, ppm in itertools.product(ECS, OCCS, PPMS):
        add(exp="G1", ec=ec, occ=occ, ppm=ppm)
    # G2  EC x contrast(normal+inverted) x ppm   (C3)
    for ec, cr, inv, ppm in itertools.product(ECS, CRS, [False, True], PPMS):
        add(exp="G2", ec=ec, cr=float(cr), inverted=inv, ppm=ppm)
    # G3  EC x module-style x ppm
    for ec, style, ppm in itertools.product(ECS, ["square", "rounded", "dots", "gapped"], PPMS):
        add(exp="G3", ec=ec, style=style, ppm=ppm)
    # G4  payload/version x EC x ppm   (C4 version inflation, occ=0)
    for pl, ec, ppm in itertools.product(["short", "med", "long"], ECS, PPMS):
        add(exp="G4", payload=pl, ec=ec, ppm=ppm)
    # G5  occlusion mode(hard/overlay) + hue
    for ec, occ, mode, ppm in itertools.product(["M", "H"], [0, 8, 16, 24, 32], ["hard", "overlay"], [2.0, 4.0, 6.0]):
        add(exp="G5", ec=ec, occ=occ, occ_mode=mode, ppm=ppm)
    for hue, ppm in itertools.product(HUES, [2.0, 4.0, 6.0]):
        add(exp="G5h", ec="Q", hue=hue, ppm=ppm)
    return cells

def render_cell(c):
    sym = build_matrix(PAYLOADS[c["payload"]], c["ec"])
    if c["hue"] != "mono":
        fg, bg = HUES[c["hue"]]
    else:
        grey = grey_for_ratio(c["cr"])
        fg, bg = ((0, 0, 0), (255, 255, 255)) if c["cr"] >= 21 else (grey, (255, 255, 255))
        if c["inverted"]:
            fg, bg = bg, fg  # light modules on dark field
            if c["cr"] >= 21:
                fg, bg = (255, 255, 255), (0, 0, 0)
    img = render(sym, module_px=16, quiet=4, fg=fg, bg=bg, style=c["style"])
    img = apply_center_logo(img, sym, c["occ"] / 100.0, quiet=4, mode=c["occ_mode"], bg=bg)
    real_cr = contrast_ratio(fg, bg)
    return sym, img, real_cr, PAYLOADS[c["payload"]]

_DEC = None
def _init():
    global _DEC
    _DEC = Decoders()

def work(args):
    c, n = args
    sym, img, real_cr, expect = render_cell(c)
    rows = []
    for s in range(n):
        rng = np.random.default_rng(int(c["cid"][:8], 16) + s)
        rot = rng.uniform(-8, 8)
        tilt = rng.uniform(0, 8)
        noise = float(rng.choice([0, 2, 5, 8]))
        jpeg = int(rng.choice([50, 75, 90, 100]))
        blur = float(rng.uniform(0.3, 0.9))
        bgr = degrade(img, sym.n, 4, ppm=c["ppm"], blur_sigma=blur,
                      noise_sigma=noise, jpeg_q=jpeg, rot_deg=rot, tilt_deg=tilt, rng=rng)
        for r in _DEC.all(bgr, expect):
            rows.append((c["cid"], c["exp"], c["payload"], sym.version, sym.n, c["ec"],
                         c["occ"], c["occ_mode"], round(real_cr, 2), c["inverted"], c["hue"],
                         c["style"], c["ppm"], s, r.name, int(r.success), int(r.detected), round(r.ms, 2)))
    return rows

COLS = ["cid", "exp", "payload", "version", "n_modules", "ec", "occ", "occ_mode",
        "contrast_ratio", "inverted", "hue", "style", "ppm", "sample", "decoder",
        "success", "detected", "ms"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("-n", type=int, default=16)  # the committed dataset was collected with N=16
    ap.add_argument("-j", type=int, default=8)
    a = ap.parse_args()
    cells = gen_cells()
    if a.smoke:
        cells = cells[::37][:20]; a.n = 4
    os.makedirs(DATA, exist_ok=True)
    print(f"cells={len(cells)}  N={a.n}  decoders=4  -> ~{len(cells)*a.n*4:,} attempts", flush=True)
    t0 = time.time()
    all_rows = []
    with Pool(a.j, initializer=_init) as pool:
        for i, rows in enumerate(pool.imap_unordered(work, [(c, a.n) for c in cells], chunksize=4)):
            all_rows.extend(rows)
            if (i + 1) % 50 == 0:
                el = time.time() - t0
                print(f"  {i+1}/{len(cells)} cells  {el:.0f}s  {len(all_rows):,} rows", flush=True)
    df = pd.DataFrame(all_rows, columns=COLS)
    out = os.path.join(DATA, "results_smoke.parquet" if a.smoke else "results.parquet")
    df.to_parquet(out, index=False)
    print(f"done {len(df):,} rows in {time.time()-t0:.0f}s -> {out}", flush=True)
    print(df.groupby("decoder")["success"].mean().round(3).to_string())

if __name__ == "__main__":
    main()
