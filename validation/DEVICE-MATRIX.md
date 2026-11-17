# Multi-device validation runbook (V1.0)

Goal: replace the single-Pixel-7 check with a real device matrix, the reviewers' top ask. Two harnesses: `phone_test.py` for native-camera devices, `webcam_test.py` for laptop cameras. Everything self-records; hand the CSVs back and `analysis/device_matrix.py` folds them into §4.

## Standardised capture protocol (v1) — read before scanning

The matrix is a fair test only if **everything except the device is held fixed**. A cross-device difference is evidence about the device only when distance, lighting, target, and operator behaviour are identical across passes. The protocol is enforced by the harness: every scan is stamped with the active **session** (lux, distance, operator, camera app), and scans made with no session set export as `pilot` and are excluded from the paper's matrix table.

### Fixed for the whole matrix (never change mid-run)
| Variable | Fixed value |
|---|---|
| Print target | **one physical sheet** (matte paper if available), printed at 100% scale (verify the 100 mm ruler), taped to the wall at a marked spot, **never moved between devices** |
| Screen target | the **same Mac** showing `/sheet`; display brightness set once and recorded; True Tone + Night Shift **off** |
| Distance | **25 cm** from the target plane to the device's **camera side**, set **once** with a ruler or tape (the print sheet carries a 100 mm ruler: use it twice + 50 mm, or a tape) and marked with tape. Device square-on (parallel to the sheet). Keep the Mac at the same plane as the hung sheet so screen codes and print codes share the one mark. Same 25 cm for on-screen codes, the print sheet, and webcams. Per device, verify the hold with the `/distance` check page (below) |
| Lighting | after dark or blinds closed (**no daylight**: it drifts); fixed room lighting; no lamp inside the camera frame; operator's shadow off the sheet. **Measured in lux at the sheet** with one instrument, every session. Acceptance band **200-600 lx**; outside it, re-light and re-measure before scanning |
| Camera app | the device's **default camera app, settings reset to defaults**; **1x, never pinch-zoom** (digital zoom is a resolution confound); **flash off, auto-flash disabled** (a flash firing on some devices and not others is a lighting confound); no filters or manual mode. Scene optimiser / night mode / auto-macro stay at device default: they are part of the device under test. Record the app + mode in the session |
| Focus | leave autofocus alone. One tap-to-focus is allowed **only** if AF never locks, and must be logged as a session deviation |
| Operator | the **same person** for every device (recorded per session; the paper discloses single-operator) |
| Order | the same fixed order for every device (the sheet order), one full pass per device |

**What varies: the device (and its camera pipeline). Nothing else.**

### Outcome definitions (timed)
- **scan**: reads within **10 s** held steady at 25 cm.
- **marginal**: reads only with extra effort: closer than 25 cm, longer than 10 s, many retries, or a focus tap. On the phone tap **"it struggled"** on the confirmation screen; on the dashboard use the marginal button.
- **no-scan**: nothing within **30 s** total, including one deliberate closer approach (~15 cm).

Do not chase a read by creeping closer: a closer read is a marginal by definition, and the 25 cm discipline is what makes the resolution and print cliffs comparable across devices.

**Classification is mechanical where the guided run measures it:** decode time is stamped server-side, and the analysis uses time-first rules (within 10 s = clean scan; over 10 s = slow/marginal; never opens within the step = no-scan). An operator "it struggled" tap is an override that matters for exactly one case timing cannot see: a read achieved by moving closer. Tap it then; otherwise the clock does the judging.

### Per-session record (stored by the harness)
Start a session on the dashboard **before each device pass**: lux reading, distance (cm), operator, camera app + mode, display note, any deviations. Re-measure lux if a pass spans more than ~30 min or the light changes. The session id, lux, distance, operator, and camera app are stamped onto every scan and exported with the CSV.

### Instruments
- **Lux**: a dedicated lux meter is the instrument (e.g. UNI-T UT383, ~£20, or any meter that reads lux), measured at the sheet surface facing the camera position. Fallback if no meter: **one** phone with a lux-meter app, the **same phone for every session**, disclosed in the paper as app-based. What matters for fairness is one instrument used consistently. **The scanning devices' own cameras cannot be the instrument**: each device meters exposure differently, so the same light would read differently per device, building the device into the measurement (and browsers no longer expose the ambient light sensor).
- **Distance**: ruler or tape measure + tape marks on the table; rest the device on the mark (a stand or a stack of books is steadier than hands; handheld is allowed since the operator is constant, but keep to the mark). For a zero-tech exact stop, tape a 25 cm spacer (dowel, cardboard strip) between the target plane and the device rest.
- **Distance check page (`/distance`, on the device, needs the https tunnel)**: two camera-based mechanisms, both saved into that device's details. (1) Where the hardware reports it (Android Chrome typically), the page reads the camera's **focus distance** live after autofocus locks: zero calibration, quantised to roughly ±1-3 cm, so treat it as a check that you are at the mark, not ground truth. (2) Elsewhere (incl. iOS) it uses one-time **calibrated geometry**: capture a frame, drag two handles onto the printed 100 mm ruler's ends, lock while at the taped mark; from then on the same capture measures your actual distance. The mark + jig remains the protocol's ground truth; the page verifies each device's hold and the reading lands in `devices.json` (`distance_check`).

### Pilot data
The original single-device Pixel 7 check (July) is archived as `results-pilot-pixel7.json` and cited by the paper; the live `results.json` started empty on 2026-09-27 for the protocol-v1 matrix. Anything scanned with no session set still exports as `pilot` and is excluded from the matrix.

## One-time setup
- **Default: bring the harness up via `./run-scanlab.sh`** (the named tunnel, below): it gives every device an https URL, which the camera-details probe and the `/distance` check need. Plain-LAN mode is the fallback when the tunnel is unavailable; those two checks then degrade (documented in-session as deviations).
- All phones/tablets on the **same Wi-Fi** as the Mac (LAN mode), **or** front the server with a tunnel so devices can be on any network (off-network mode, below).
- Print the resolution sheet at **100% scale**: `python print_sheet.py` (server must be running) then print `print_sheet.pdf`; verify the 100 mm ruler measures exactly 100 mm.
- Set up the jig: sheet taped to the wall, 25 cm tape mark measured and laid, lux instrument ready, Mac display set + True Tone/Night Shift off.

### Off-network mode (devices not on the Mac's Wi-Fi)
The QR codes bake the server URL into themselves, so the public URL must be set **before** the codes render (`PUBLIC_BASE_URL`).

**Preferred: the named Cloudflare tunnel (stable URL, reliable).** A dedicated tunnel `openqr-scanlab` is already provisioned on the account with a fixed hostname `https://scanlab.clinicalwebdesign.co.uk` (config `~/.cloudflared/openqr-scanlab.yml` -> `localhost:8009`). One command brings up the tunnel + harness in tmux:
```
./run-scanlab.sh
```
It starts `scanlab-tunnel` and `scanlab-harness` (tmux), bakes `https://scanlab.clinicalwebdesign.co.uk` into every code, and prints the dashboard/sheet URLs. Open those on the Mac; scan from any device on any network. Stop when done (this also closes the open `/reset` + `/device/*` endpoints):
```
tmux kill-session -t scanlab-harness; tmux kill-session -t scanlab-tunnel
```

**Fallback: a throwaway quick-tunnel** (random URL, no account setup, but `trycloudflare` edge routing proved unreliable on this network, so prefer the named tunnel):
```
python phone_test.py 8000                                  # start (renders LAN codes)
cloudflared tunnel --url http://localhost:8000             # new terminal; note the printed https URL
# Ctrl-C the server, then restart it so the codes re-render encoding the tunnel URL:
PUBLIC_BASE_URL="https://<printed>.trycloudflare.com" python phone_test.py 8000
```
The startup log prints `Codes encode: <url>` so you can confirm it baked the public URL, not the LAN IP.

## The matrix to run (your inventory)
| # | Device | Class | App | Harness |
|---|---|---|---|---|
| 1-3 | 3 modern Android phones | modern phone | native camera | phone_test |
| 4-5 | 2 older Android tablets | tablet | native camera | phone_test |
| 6 | mid-range iPhone (to get) | modern phone | native camera (iOS engine) | phone_test |
| 7 | one Android, **ZBar-based app** | modern phone | ZBar app | phone_test |
| 8 | same Android, **ZXing-based app** | modern phone | ZXing app | phone_test |
| 9 | modern laptop webcam | laptop webcam | opencv/zbar/zxing | webcam_test |
| 10 | older laptop / USB camera | laptop webcam | opencv/zbar/zxing | webcam_test |

7 and 8 are the highest-value adds: they test the ZBar/ZXing engines on real captures, which is the decoder-split claim (C2) directly. The iPhone is the only iOS pipeline in the set.

## A. Native-camera devices (1-8)
```
cd scannability/validation
python phone_test.py
```
On the Mac open the dashboard (`/`). **Devices are auto-detected, no add/select step.** Per device:

1. **Start a session** on the dashboard (lux at the sheet, 25 cm, operator, camera app + mode) so this device's scans stamp to it.
2. **Start the guided run** (`/run`, linked from the dashboard). The Mac presents each code in the fixed protocol order with a live clock. Hold the device at the 25 cm mark, square-on, and scan each presented code with its native camera. The **server times presentation to URL-open**, so the 10 s / 30 s windows are measured, not judged: a read inside 10 s is a clean scan; past 10 s the clock goes amber (marginal if you had to move closer or retry, tap **"it struggled"** on the phone); past 30 s mark **no-scan** on the run page and continue. The run auto-advances a couple of seconds after each recorded scan. Print codes (`p20..p66`) appear as steps too: hold the printed sheet at the mark and scan the named code.
3. **Device details are collected automatically**: the phone's confirmation page posts model (via client hints), screen, pixel ratio, cores, memory and BarcodeDetector availability with no prompts; tap **"Send this camera's details"** once per device for the camera's zoom / torch / focus capabilities, and **"Distance check"** once to verify the hold (both need the https tunnel; on plain LAN they report the failure, the passive details still arrive). View them via **Device details (JSON)** on the dashboard.
4. Pick up the next device, **start a new session**, **start a new run**, repeat. The **Device matrix** panel tracks everything.

`/sheet` remains for free-order manual passes; the guided run is the default because its timing is measured.

Notes: iPhones report only "iPhone" (iOS does not expose the model); each still gets its own bucket via the cookie. For **7/8** (ZBar/ZXing apps on one phone): if the app opens the URL in the **same** default browser it will group with that phone's native-camera bucket, so open those scans in the app's built-in browser or a different browser to keep the app pipeline as a distinct device. If the app decodes but does not open the URL, mark the outcome on the run page (marginal / no-scan buttons).
When all are done: **Export combined CSV (all devices)** + **Device details (JSON)**.

## B. Laptop webcams (9-10)
Run on the laptop that has the camera (needs `pip install opencv-contrib-python pyzbar zxing-cpp`), or on this Mac using its built-in camera (`camera_index 0`) and an external/older USB camera (`camera_index 1`):
```
python webcam_test.py "modern-laptop-webcam" 0 --lux 380 --operator Sam
python webcam_test.py "older-usb-camera" 1 --lux 380 --operator Sam
```
The same protocol applies: measured 25 cm to the target (printed sheet or `/sheet` on another screen), lux recorded, no zoom, flash off. Pass the conditions with `--lux/--distance/--operator/--camera-app` and they are written into the CSV. Point the camera at each validation code; the preview shows how many codes each decoder has read. Press **q** to finish. Each run writes `webcam_<label>.csv` with per-decoder (opencv/zbar/zxing) results, which is the OpenCV-class hardware test.

## Hand back
Give me `device_matrix.csv` + `devices.json` (from A) and the `webcam_*.csv` files (from B). `analysis/device_matrix.py` aggregates them into the §4 per-device pass/marginal/fail + agreement table (with measured decode times) and a figure, and flags any code where a real device diverges from the library proxy (itself a finding). Rows without a session stamp (`pilot`) are reported separately, not pooled with the protocol-v1 matrix.
