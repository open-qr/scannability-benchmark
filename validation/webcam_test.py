"""Webcam validation: run the three library decoders on a real laptop-webcam feed.

Covers the webcam / kiosk / OpenCV-class hardware the reviewers ask for, and yields
PER-DECODER results on real captures (opencv / zbar / zxing) -- a direct hardware test
of the weak/strong-tier decoder split (finding C2). Point the webcam at each validation
code (the printed sheet, or another screen showing /sheet); each decoder that reads a
code is recorded. Press q in the preview window to finish.

Run:  python webcam_test.py "<device label>" [camera_index] [--lux N] [--distance-cm N]
      [--operator Name] [--camera-app "desc"] [--display "desc"]
The standardised capture protocol (DEVICE-MATRIX.md) applies: measured 25 cm to the
target, lux recorded at the sheet (200-600 lx, no daylight), no zoom, flash off. The
conditions are written into the CSV; without --lux the run exports as `pilot`.
Writes: webcam_<label>.csv (one row per code: which of opencv/zbar/zxing read it).
"""
from __future__ import annotations
import sys, os, re, csv, argparse
import cv2
from pyzbar.pyzbar import decode as zbar_decode
import zxingcpp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from phone_test import CELLS  # same cell set + modern-decoder predictions

CID_RE = re.compile(r"/s/([a-z0-9]+)")
_qd = cv2.QRCodeDetector()


def texts_opencv(frame):
    ok, info, _pts, _ = _qd.detectAndDecodeMulti(frame)
    return [t for t in (info or []) if t] if ok else []

def texts_zbar(frame):
    try:
        return [r.data.decode("utf-8", "ignore") for r in zbar_decode(frame)]
    except Exception:
        return []

def texts_zxing(frame):
    try:
        return [r.text for r in zxingcpp.read_barcodes(frame)]
    except Exception:
        return []

def mark(seen, decoder, texts):
    """Record, per code id, that `decoder` read it (sticky across frames)."""
    for t in texts:
        m = CID_RE.search(t or "")
        if m and m.group(1) in seen:
            seen[m.group(1)][decoder] = True

def scan_frame(seen, frame):
    mark(seen, "opencv", texts_opencv(frame))
    mark(seen, "zbar", texts_zbar(frame))
    mark(seen, "zxing", texts_zxing(frame))

def new_seen():
    return {c["cid"]: {"opencv": False, "zbar": False, "zxing": False} for c in CELLS}

def write_csv(label, seen, sess):
    out = os.path.join(HERE, f"webcam_{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["device", "cid", "group", "prediction_modern", "opencv", "zbar", "zxing", "any_decoder",
                    "protocol", "lux", "distance_cm", "operator", "camera_app", "display"])
        for c in CELLS:
            s = seen[c["cid"]]
            w.writerow([label, c["cid"], c["group"], c["pred"],
                        int(s["opencv"]), int(s["zbar"]), int(s["zxing"]), int(any(s.values())),
                        sess["protocol"], sess["lux"], sess["distance_cm"],
                        sess["operator"], sess["camera_app"], sess["display"]])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("label")
    ap.add_argument("camera_index", nargs="?", type=int, default=0)
    ap.add_argument("--lux", default="", help="lux measured at the sheet this session (required for protocol v1)")
    ap.add_argument("--distance-cm", dest="distance_cm", default="25")
    ap.add_argument("--operator", default="Sam")
    ap.add_argument("--camera-app", dest="camera_app", default="opencv/zbar/zxing on webcam feed")
    ap.add_argument("--display", default="printed sheet (or /sheet on a screen)")
    args = ap.parse_args()
    sess = {"protocol": "v1" if str(args.lux).strip() else "pilot",
            "lux": str(args.lux).strip(), "distance_cm": args.distance_cm,
            "operator": args.operator, "camera_app": args.camera_app, "display": args.display}
    seen = new_seen()
    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        print(f"Could not open camera index {args.camera_index}. Try 0, 1 or 2.")
        sys.exit(1)
    print(f"Webcam validation for '{args.label}'. Point the camera at each code; press q to finish.")
    if sess["protocol"] == "pilot":
        print("  NOTE: no --lux given; this run exports as PILOT (excluded from the paper's matrix).")
    print(f"  Session: {sess['lux'] or '?'} lx @ {sess['distance_cm']} cm, operator {sess['operator']}, "
          f"camera '{sess['camera_app']}', target '{sess['display']}'")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        scan_frame(seen, frame)
        done = sum(1 for v in seen.values() if any(v.values()))
        o = sum(v["opencv"] for v in seen.values())
        z = sum(v["zbar"] for v in seen.values())
        x = sum(v["zxing"] for v in seen.values())
        cv2.putText(frame, f"{args.label}: {done}/{len(seen)} seen  opencv={o} zbar={z} zxing={x}  (q=quit)",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 120), 2)
        cv2.imshow("webcam validation", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    out = write_csv(args.label, seen, sess)
    print(f"\nWrote {out}")
    print("Per-decoder codes read:",
          "opencv", sum(v['opencv'] for v in seen.values()),
          "zbar", sum(v['zbar'] for v in seen.values()),
          "zxing", sum(v['zxing'] for v in seen.values()), f"of {len(seen)}")


if __name__ == "__main__":
    main()
