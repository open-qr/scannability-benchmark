"""Codeword-level damage audit (peer review round 1, amendment A2 of PROTOCOL.md v1.1).

The nominal 7/15/25/30% EC figures are capacities for errors at UNKNOWN positions
(t = floor(r/2) per Reed-Solomon block), not erasure capacities. This audit measures, for
the exact benchmark symbols (26-char 'med' payload, the payload the occlusion grid uses),
how a centre logo maps to corrupted codewords per interleaved RS block:

  area % -> modules covered -> dark modules changed -> codewords corrupted PER BLOCK vs t

Method (pure computation on the module matrices, no images, no decoders):
  1. Rebuild each symbol via segno exactly as the harness does (default boost_error, so
     requested L encodes at its effective EC; reported alongside).
  2. Walk the ISO/IEC 18004 zigzag placement over non-function modules to map every data
     module to (stream bit index -> codeword index, bit position).
  3. Invert the block interleaving to map stream codeword index -> (block, data/EC, index)
     using the v2-v4 block tables.
  4. A codeword is corrupted iff any of its 8 modules differs from the true matrix after
     the logo pad is painted. A block fails RS decoding iff corrupted codewords in that
     block (data + EC, both live in the symbol) exceed t = floor(ec_cw / 2).

Validations (all must pass, else the script refuses to write its artifact):
  - non-function module count == 8 * total_codewords + 7 remainder bits (v2-v6)
  - sum(data_cw) + sum(ec_cw) from the block table == total codewords for the version
  - the de-interleaved data codewords of the UNDAMAGED matrix (mask-XORed back to the
    stream) parse as byte mode with the exact payload string

Writes data/codeword_audit.json.
"""
from __future__ import annotations
import os, sys, json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
sys.path.insert(0, os.path.dirname(__file__))
import segno  # noqa: E402
from damage import function_mask, covered_mask  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
PAYLOAD = "https://openqr.uk/r/aB3xK9"  # harness/run.py 'med' payload, 26 chars (asserted below)

# RS block tables for versions 2-4: (version, EC) -> [(data_cw, ec_cw) per block].
# All v2-v4 blocks within a symbol are equal-sized. Validated against the matrices below.
BLOCKS = {
    (2, "L"): [(34, 10)], (2, "M"): [(28, 16)], (2, "Q"): [(22, 22)], (2, "H"): [(16, 28)],
    (3, "L"): [(55, 15)], (3, "M"): [(44, 26)], (3, "Q"): [(17, 18)] * 2, (3, "H"): [(13, 22)] * 2,
    (4, "L"): [(80, 20)], (4, "M"): [(32, 18)] * 2, (4, "Q"): [(24, 26)] * 2, (4, "H"): [(9, 16)] * 4,
}

OCC = sorted(set(list(range(0, 46, 2)) + list(range(4, 41, 4)) + [9, 16]))  # oracle grid + G1 grid + headline levels


def mask_bit(mask_id, r, c):
    m = {
        0: (r + c) % 2 == 0,
        1: r % 2 == 0,
        2: c % 3 == 0,
        3: (r + c) % 3 == 0,
        4: (r // 2 + c // 3) % 2 == 0,
        5: (r * c) % 2 + (r * c) % 3 == 0,
        6: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        7: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    }
    return m[mask_id]


def placement_order(n, fmask):
    """ISO/IEC 18004 zigzag: 2-column strips right-to-left, skipping the timing column 6,
    first strip upward, alternating; within each row right column then left. Returns the
    (row, col) of every non-function module in stream-bit order."""
    order = []
    col, up = n - 1, True
    while col > 0:
        if col == 6:
            col = 5
        rows = range(n - 1, -1, -1) if up else range(n)
        for r in rows:
            for c in (col, col - 1):
                if not fmask[r, c]:
                    order.append((r, c))
        up = not up
        col -= 2
    return order


def interleave_map(blocks):
    """Stream codeword index -> (block_idx, kind, index). Mirrors the spec's construction:
    data codewords round-robin over blocks, then EC codewords round-robin."""
    m = []
    for i in range(max(d for d, _ in blocks)):
        for b, (d, _) in enumerate(blocks):
            if i < d:
                m.append((b, "d", i))
    for i in range(max(e for _, e in blocks)):
        for b, (_, e) in enumerate(blocks):
            if i < e:
                m.append((b, "e", i))
    return m


def cw_of_module(order):
    """module stream-bit index k -> codeword index (k // 8); the trailing 7 remainder bits
    map to None."""
    return [k // 8 if k // 8 < (len(order) - 7) // 8 else None for k in range(len(order))]


def audit_symbol(ec_request):
    qr = segno.make(PAYLOAD, error=ec_request.lower(), micro=False)  # harness default: boost_error on
    m = np.array(qr.matrix, dtype=bool)
    n = m.shape[0]
    ec_eff = qr.error.upper()
    fmask = function_mask(n, qr.version)
    data_modules = int((~fmask).sum())
    total_cw = data_modules // 8
    assert data_modules % 8 == 7, f"v{qr.version}: expected 7 remainder bits, got {data_modules % 8}"
    blocks = BLOCKS[(qr.version, ec_eff)]
    assert sum(d + e for d, e in blocks) == total_cw, \
        f"v{qr.version}-{ec_eff}: block table {sum(d + e for d, e in blocks)} != matrix {total_cw} codewords"
    t = [e // 2 for _, e in blocks]

    order = placement_order(n, fmask)
    assert len(order) == data_modules, f"placement visited {len(order)} modules, function mask says {data_modules}"

    # stream bit k lives at order[k]; module value = stream bit XOR mask bit
    stream = np.array([m[r, c] ^ mask_bit(qr.mask, r, c) for r, c in order], dtype=bool)
    cw_vals = [int("".join("1" if b else "0" for b in stream[i * 8:(i + 1) * 8]), 2)
               for i in range(total_cw)]
    imap = interleave_map(blocks)
    assert len(imap) == total_cw

    # validation: de-interleaved data codewords parse back to the exact payload (byte mode)
    data_cw = []
    for b, (d, _e) in enumerate(blocks):
        data_cw += [cw_vals[i] for i, mm in enumerate(imap) if mm[0] == b and mm[1] == "d"]
    bits = "".join(f"{v:08b}" for v in data_cw)
    mode, count = int(bits[:4], 2), int(bits[4:12], 2)
    assert mode == 4, f"mode nibble {mode}, expected 4 (byte)"
    assert count == len(PAYLOAD), f"char count {count} != {len(PAYLOAD)}"
    decoded = bytes(int(bits[12 + 8 * i:20 + 8 * i], 2) for i in range(count)).decode("ascii")
    assert decoded == PAYLOAD, f"round-trip mismatch: {decoded!r}"

    # module stream-bit index k -> codeword index; codeword index -> block via the interleave map
    mod_cw = cw_of_module(order)

    rows = []
    for occ in OCC:
        cov = covered_mask(n, occ / 100.0)
        changed_hard = cov & m          # white pad: dark -> light
        changed_overlay = cov & ~m      # black overlay: light -> dark
        fn_hit = int((cov & fmask).sum())
        for label, changed in (("hard", changed_hard), ("overlay", changed_overlay)):
            # a codeword is corrupted if ANY of its 8 modules changed
            corrupted_cw = {mod_cw[k] for k, (r, c) in enumerate(order)
                            if mod_cw[k] is not None and changed[r, c]}
            per_block = [0] * len(blocks)
            for ci in corrupted_cw:
                per_block[imap[ci][0]] += 1
            rows.append({
                "occ_pct": occ, "mode": label,
                "modules_covered": int(cov.sum()),
                "modules_changed": int(changed.sum()),
                "codewords_corrupted": len(corrupted_cw),
                "per_block_corrupted": per_block,
                "per_block_t": t,
                "overflow": any(per_block[b] > t[b] for b in range(len(blocks))),
                "function_modules_hit": fn_hit,
            })
    summary = {
        "requested_ec": ec_request, "effective_ec": ec_eff, "boosted": ec_eff != ec_request,
        "version": qr.version, "mask": qr.mask, "n": n, "dark_fraction": round(float(m.mean()), 3),
        "blocks": blocks, "t_per_block": t, "total_codewords": total_cw,
        "budget_cw": sum(t), "budget_pct": round(100 * sum(t) / total_cw, 1),
    }
    return summary, rows


def main():
    assert len(PAYLOAD) == 26
    out = {"payload": PAYLOAD, "payload_chars": len(PAYLOAD), "per_ec": {}}
    print(f"{'EC':>6} {'ver':>3} {'mask':>4} {'blocks(d+e)':>16} {'t/blk':>10} {'budget':>12}")
    for ec in ["L", "M", "Q", "H"]:
        summary, rows = audit_symbol(ec)
        # predicted RS ceiling per mode: last contiguous occ with no block overflow
        ceil = {}
        for mode in ("hard", "overlay"):
            c = -1
            for r in rows:
                if r["mode"] == mode:
                    if r["overflow"]:
                        break
                    c = r["occ_pct"]
            ceil[mode] = c
        summary["predicted_rs_ceiling_occ"] = ceil
        out["per_ec"][ec] = {**summary, "rows": rows}
        bs = "+".join(f"{d}+{e}" for d, e in summary["blocks"])
        print(f"{ec:>4}({summary['effective_ec']}) {summary['version']:>3} {summary['mask']:>4} "
              f"{bs:>16} {str(summary['t_per_block']):>10} "
              f"{summary['budget_cw']}/{summary['total_codewords']} = {summary['budget_pct']}%")

    print("\nper-block corruption at key occlusions (hard mode, white pad):")
    for ec in ["L", "M", "Q", "H"]:
        s = out["per_ec"][ec]
        rws = {r["occ_pct"]: r for r in s["rows"] if r["mode"] == "hard"}
        print(f"\n{ec} (requested {ec}, effective {s['effective_ec']}, v{s['version']}, "
              f"mask {s['mask']}): t/block = {s['t_per_block']}")
        for occ in [8, 9, 10, 12, 16, 18, 20, 24]:
            r = rws[occ]
            flag = " OVERFLOW" if r["overflow"] else ""
            print(f"  occ {occ:>2}%: cov {r['modules_covered']:>3} mod, changed {r['modules_changed']:>3}, "
                  f"corrupt cw {r['codewords_corrupted']:>2}, per-block {r['per_block_corrupted']}, "
                  f"fn hit {r['function_modules_hit']}{flag}")
        print(f"  => predicted RS ceiling (hard): {s['predicted_rs_ceiling_occ']['hard']}%, "
              f"(overlay): {s['predicted_rs_ceiling_occ']['overlay']}%")

    json.dump(out, open(os.path.join(DATA, "codeword_audit.json"), "w"), indent=1)
    print("\nwrote data/codeword_audit.json")


if __name__ == "__main__":
    main()
