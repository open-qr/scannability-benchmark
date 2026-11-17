# Real-device (phone) validation

The preprint's main external-validity caveat is that the four library decoders, especially the strong-tier pair (WeChat, ZXing), stand in for a real phone camera. This harness tests that claim directly and fills the paper's "real-device validation" placeholder. It renders a small, targeted sample of the *same* styled codes the benchmark uses (identical `qrgen` renderer, no simulated degradation, because your phone camera is the real capture channel), each encoding a unique URL served by this machine. You scan each with your phone's normal camera; a successful scan opens the URL and self-records a PASS. Codes that will not scan you mark FAIL on the dashboard.

## Run

```
cd scannability/validation
python phone_test.py            # optional: python phone_test.py <port>
```

Your phone must be on the same Wi-Fi as this Mac. The script prints two URLs:

- **Dashboard** (`/`): live results, per-code status, and running agreement with the study. Open on the Mac.
- **Sheet** (`/sheet`): the codes to scan. Open on the Mac screen (or print it).

Scan each code with the phone's built-in camera and tap the notification to open the link. **Each device is detected automatically** on its first scan (a first-party cookie groups its scans; the User-Agent, upgraded by Chromium's `Sec-CH-UA-Model` client hint, names it) and appears in the Device matrix, no add/select step. The dashboard row turns green automatically. For a code that will not scan at all, click **no-scan** on that device's view; for one that read **only** after you moved closer, held it, or retried a lot, tap **"it struggled &rarr; mark marginal"** on the phone's own confirmation screen (records `marginal` without reaching the Mac). When done, **Export CSV**.

**Standard scanning distance:** hold every device ~**25 cm (a hand-span)** from the code, square-on, and keep the same distance for every code and device, so the resolution and print cliffs are comparable across the matrix. "The phone eventually got it" is a `marginal`, not a clean pass.

### Off-network devices (not on this Mac's Wi-Fi)
The codes bake the server URL into themselves, so the public URL is set **before** they render (`PUBLIC_BASE_URL`). A named Cloudflare tunnel is provisioned (stable `https://scanlab.clinicalwebdesign.co.uk`); one command starts the tunnel + harness in tmux:
```
./run-scanlab.sh
```
Open the printed dashboard/sheet URLs on the Mac and scan from any device. Stop when done (closes the open `/reset` + `/device/*` endpoints): `tmux kill-session -t scanlab-harness; tmux kill-session -t scanlab-tunnel`. Details + the throwaway quick-tunnel fallback are in `DEVICE-MATRIX.md`.

## Printed resolution test

The on-screen sheet oversamples the resolution cliff (a sharp screen scanned up close gives the sensor more than the nominal px/module). To measure the cliff in real millimetres:

```
python print_sheet.py            # writes print_sheet.pdf (server must be running)
```

Print it at **100% scale** (verify the 100 mm ruler on the page measures exactly 100 mm), then scan the six codes from one fixed distance. The smallest that reads reliably is your true minimum module size. These codes self-record to the same dashboard, so they land in the CSV alongside the screen results.

## The sample (22 on-screen codes + 6 printed) and what each group tests

| Group | Codes | Claim under test | Study prediction for a modern phone |
|---|---|---|---|
| occlusion | a00..a36 (0-36% centre logo, EC H) | Safe logo ceiling is ~9% worst-case / ~16% strong-tier, not 30% | pass to ~18%, fail by 24-30% |
| inversion | bno, bin | ZBar/OpenCV read inverted codes 0%; the strong tier is essentially unaffected | both pass (phone is strong-tier) |
| contrast | c45, c30, c20, c15 (4.5:1 down to 1.5:1) | Contrast floor is low, ~2:1, strong tier to ~1.5:1 | all pass at good resolution |
| style | dro, ddo, dga (rounded/dots/gapped) | Module style is a second-order penalty | all pass |
| ec-level | elr (L), ehr (H) at ~3 px/module | EC does **not** move the resolution cliff (C4) | same outcome for L and H |
| resolution | f02..f10 (2-10 px/module) | Decode collapses below ~3 px/module | fail at 2, edge at 3, pass from 4 |
| print | p20..p66 (0.20-0.66 mm/module) | Real minimum physical module size | smallest reliable size, measured in mm |

The fixed-size codes render large so resolution is not the binding constraint, isolating their factor. The `resolution` and `ec-level` codes render at **true pixel size** so physical module size varies honestly: hold the phone at one fixed distance for all of those.

## Interpreting the result

Your phone is a single modern decoder, so the relevant baseline is the study's **strong-tier** column (the `pred` shown per row). The dashboard reports how many codes your phone agreed with. High agreement supports the paper's claim that the strong-tier library decoders (zxing-cpp, WeChat) are a sound phone proxy; systematic disagreement (e.g. your phone reading 30% occlusion, or failing inverted codes) is itself a finding worth recording.

Outcomes rank fail < marginal < decoded, and predictions rank fail < edge < pass; a cell agrees when its outcome is within one rank of the prediction. So a `marginal` read of a predicted-fail resolution code counts as agreement (it sits on the cliff), and an `edge` cell is consistent with either outcome.

## Feeding results back into the paper

`Export CSV` writes one row per code with the rendered parameters, the study prediction, and your phone's outcome. Run it on 2-3 phones (a flagship, a mid-range, an older device) and keep each CSV. Aggregate agreement, plus any code where phones diverge from the library proxy, is the real-device validation the preprint's limitations section flags as future work. Note the phone model, OS, and scanner app (native camera vs a dedicated app) alongside each run: scanner pipeline, not the sensor, usually explains divergence.

Generated `codes/` and the print PDF are gitignored; `results.json` (the Pixel 7 run backing §4 of the preprint) is committed, and the per-device CSV export is the artifact to keep for a multi-device run.
