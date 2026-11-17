"""Supplementary high-resolution sweep around the detection cliff to firm up the
EC-paradox (C4): fixed physical size, vary ppm finely, all EC levels & payloads,
high replication. Writes data/results_cliff.parquet."""
from __future__ import annotations
import os, sys, time, itertools, hashlib
import numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
from run import work, _init, COLS, BASE, PAYLOADS, DATA

PPMS = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0]
ECS = ["L", "M", "Q", "H"]

def cells():
    out = []
    for pl, ec, ppm in itertools.product(["short", "med", "long"], ECS, PPMS):
        c = dict(BASE); c.update(exp="G6", payload=pl, ec=ec, occ=0, ppm=ppm)
        c["cid"] = hashlib.md5(f"cliff{pl}{ec}{ppm}".encode()).hexdigest()[:12]
        out.append(c)
    return out

def main():
    cs = cells(); N = 40
    print(f"cliff cells={len(cs)} N={N} -> {len(cs)*N*4:,} attempts", flush=True)
    t0 = time.time(); rows = []
    with Pool(8, initializer=_init) as p:
        for r in p.imap_unordered(work, [(c, N) for c in cs], chunksize=2):
            rows.extend(r)
    df = pd.DataFrame(rows, columns=COLS)
    df.to_parquet(os.path.join(DATA, "results_cliff.parquet"), index=False)
    print(f"done {len(df):,} rows {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
