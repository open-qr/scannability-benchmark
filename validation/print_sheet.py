"""Generates print_sheet.pdf: the same QR rendered at exact physical module sizes (mm)
for a real resolution-cliff test. Print at 100% scale (verify the 100 mm ruler measures
100 mm), then scan the printout from one fixed distance and note the smallest code that
reads reliably: that is your real minimum module size. Each code encodes a URL on the
running phone_test.py server, so scanning the printout self-records to the dashboard/CSV.

Run:  python print_sheet.py [port]   (default port 8000, must match the running server)
"""
from __future__ import annotations
import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import phone_test as pt
from qrgen import build_matrix

A4_W, A4_H = 210.0, 297.0
QUIET = 4


def matrix_with_quiet(payload):
    sym = build_matrix(payload, "H")
    n = sym.n
    pad = np.zeros((n + 2 * QUIET, n + 2 * QUIET), bool)
    pad[QUIET:QUIET + n, QUIET:QUIET + n] = sym.matrix
    return pad


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    # Match phone_test: bake the public tunnel URL when set, else the LAN address.
    public = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    base = public if public else f"http://{pt.lan_ip()}:{port}"
    cells = [c for c in pt.CELLS if c["group"] == "print"]

    fig = plt.figure(figsize=(A4_W / 25.4, A4_H / 25.4))
    fig.text(0.5, 1 - 12 / A4_H, "Scannability resolution test: print at 100% scale",
             ha="center", va="center", fontsize=12, weight="bold")
    fig.text(0.5, 1 - 20 / A4_H,
             f"Scan each code from one fixed distance. Results self-record to {base}/",
             ha="center", va="center", fontsize=8)
    fig.text(0.5, 1 - 26 / A4_H,
             "Protocol v1: measured 25 cm, square-on, 1x (no zoom), flash off, default camera app. "
             "Reads within 10 s steady = scan; only closer/longer/many retries = marginal; "
             "nothing in 30 s = no-scan. Record lux + camera app in the session before each device.",
             ha="center", va="center", fontsize=6.5, color="0.25")

    left, y = 20.0, 32.0
    for c in cells:
        cid = c["cid"]; mm = c["render"]["mm"]
        M = matrix_with_quiet(f"{base}/s/{cid}")
        side = M.shape[0] * mm
        ax = fig.add_axes([left / A4_W, 1 - (y + side) / A4_H, side / A4_W, side / A4_H])
        ax.imshow(M, cmap="gray_r", interpolation="nearest", aspect="auto")
        ax.axis("off")
        fig.text((left + side + 5) / A4_W, 1 - (y + side / 2) / A4_H,
                 f"{cid}:  {mm:.2f} mm per module   ({M.shape[0]} modules, {side:.1f} mm wide)",
                 va="center", fontsize=9)
        y += side + 9

    ry = A4_H - 22
    rax = fig.add_axes([left / A4_W, 1 - ry / A4_H, 100 / A4_W, 7 / A4_H])
    rax.set_xlim(0, 100); rax.set_ylim(0, 1); rax.axis("off")
    rax.plot([0, 100], [0.5, 0.5], color="k", lw=1)
    for t in range(0, 101, 10):
        rax.plot([t, t], [0.15, 0.85], color="k", lw=1)
    fig.text(left / A4_W, 1 - (ry - 5) / A4_H,
             "100 mm calibration ruler: measure this line, it must be exactly 100 mm",
             fontsize=8)

    out = os.path.join(HERE, "print_sheet.pdf")
    fig.savefig(out, dpi=600)
    plt.close(fig)
    print(f"wrote {out} ({len(cells)} codes, encoding {base}). Print at 100% scale, then scan the printout.")


if __name__ == "__main__":
    main()
