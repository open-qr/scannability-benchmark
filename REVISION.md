# Scannability paper: peer-review revision plan (to V1)

Two early-stage reviews, both **major revision**. Shared verdict: the paper is valuable but **overconfident**, and thin on **QR-internal rigor**. The strong findings survive; they must be narrowed to what the design supports and backed with symbol-level analysis. This plan actions every point and tags feasibility so Sam sees exactly what is agent-doable now vs gated.

## Strategy (what makes V1 defensible)
Both reviewers agree the defensible findings are: the 30%/EC-H logo rule is wrong as stated; decoder choice materially changes scannability; low px/module is the dominant failure; inverted codes fail on common software pipelines. The revision keeps these and:
- **(A) Narrows every claim** to the tested envelope (synthetic capture proxy, four software decoders, centre-square logo, tested payloads/versions). Text-only; answers the bottom-line critique. **Do first.**
- **(B) Adds QR-internal rigor** the reviewers require: damage decomposition (visual area vs modules vs codewords vs RS blocks), quiet-zone / alignment-pattern / mask / exact-version reporting, and an oracle decode that separates front-end failure from channel capacity. Agent-doable from the committed matrices; the heavy technical lift.
- **(C) Calibrates the score** or demotes it to a ranking score. Agent-doable from held-out predictions.
- **(D) Fixes presentation**: figure numbering, "P95" terminology, decoder-version reporting, artifact-availability language. Text-only.
- **(E) Releases artifacts** (repo is built; split + deposit). Mostly gated on Sam (Zenodo) but the code/data/seeds already exist.
- **(F) Multi-device validation** and **scope expansion** are staged: hardware = Sam; scope = Sam decides expand vs explicitly bound.

## Feasibility legend
`TEXT` do now (edit) · `ANALYSIS` new script over committed matrices/data, agent-doable · `RERUN` re-run harness (compute, agent-doable) · `HW` needs real devices (Sam) · `DECIDE` Sam's scope call · `RELEASE` publish step (Sam-gated)

---

## Action table

| # | Reviewer point | Action | Feas. | Priority |
|---|---|---|---|---|
| 1 | R2-1 failure stages not isolated ("front-end-limited" unproven) | Build an **oracle decoder**: corrupt the known module matrix, bypass vision, feed to an RS-capacity checker; separate symbol-channel capacity from front-end. Until then, soften to "consistent with front-end-limited behaviour in the tested black-box decoders". | ANALYSIS + TEXT | P1 |
| 2 | R2-2/-3, controls 1-4 occlusion underspecified; area ≠ damage | Add a **damage-decomposition table** per (version, mask, occlusion): modules covered, dark modules changed, codewords affected, RS-block distribution, alignment patterns covered, quiet-zone preserved. State plainly that X% area ≠ X% codeword damage. | ANALYSIS + TEXT | P0 |
| 3 | R2-4 inversion may be a quiet-zone artifact | Re-render inversion in 4 conditions: normal; full-inverse (dark quiet zone); inverse-symbol-with-light-quiet-zone; pre-inverted-preprocessed. Attribute the failure precisely. | RERUN + TEXT | P1 |
| 4 | R2-5 contrast overgeneralized (WCAG ≠ print grading) | Reframe as synthetic-only: "under our capture proxy, contrast was not binding above ~2:1 WCAG, given adequate resolution." Note ISO/barcode-grading is the right instrument for print; flag as future work. | TEXT | P0 |
| 5 | R1, R2-6 synthetic proxy = biggest external-validity gap | Narrow all "phone/real-world" language to the proxy + tested decoders. Keep the proxy limitation prominent. Real devices via (12). | TEXT | P0 |
| 6 | R2-7 N=16 thin for 95% claims | Add per-cell **binomial (Clopper-Pearson) intervals**; round headline thresholds (report ~9%, ~16%, ~3 px/module; drop false precision like 8.9/16.2/3.17). Optionally `RERUN` higher N near boundaries. | ANALYSIS + TEXT | P1 |
| 7 | R2-8 bootstrap CIs understate uncertainty | Explicitly separate three uncertainty layers (capture / grid-spacing / design-space) and state the design-space layer is uncaptured; stop implying the bootstrap CI is total uncertainty. | TEXT | P1 |
| 8 | R2-9 AUC ≠ calibration | Compute **calibration curve, Brier, ECE, per-decoder calibration**; either calibrate (Platt/isotonic) or rename to a **ranking score**. | ANALYSIS + TEXT | P0 |
| 9 | R2-10 model uses `decoder` as a feature | Ship the score as **per-decoder** and **worst-case (min over decoders)** and a **target-profile** variant (phone / embedded / kiosk); a designer cannot supply `decoder`. | ANALYSIS + TEXT | P1 |
| 10 | R1, controls 1-5 quiet zone / alignment / mask / version / mode not reported | Report exact **version and mask per (EC, payload)**, quiet-zone handling, and add at least one **non-URL payload mode** (numeric/alphanumeric/byte) to show mode changes version/layout. | ANALYSIS (report) + RERUN (modes) | P1 |
| 11 | R1, control 6 logo geometry (only centre-square) | Either add corner/circular/padded-white-box conditions, or state explicitly the results bind to centre-square and must not be generalized to "all logos". | DECIDE (+ RERUN if expand) | P1 |
| 12 | R1, R2-6 one-device validation insufficient | Run the released `validation/` harness across a **6-10 device matrix** (iPhone native, mid/low Android, ZBar-app, ZXing-app, POS/industrial, webcam-kiosk). | HW | P1 |
| 13 | Presentation: figure-numbering mismatch (3.3 says "Fig 4", figure is "Figure 3") | Fix all in-text figure cross-references to match render order (contrast/polarity is Figure 3, cliff is Figure 4). | TEXT | P0 |
| 14 | Presentation: "P95" is ambiguous | Replace with "95%-success threshold" / "p ≥ 0.95 crossing" throughout. | TEXT | P0 |
| 15 | Presentation: artifacts still a promise | Change "to be deposited" to the released repo; deposit to Zenodo for the DOI. | TEXT + RELEASE | P0 / P1 |
| 16 | References thin on decoder versions | Report exact versions: OpenCV + contrib, WeChat model files, ZBar/pyzbar, zxing-cpp, segno, encoder settings, pipeline libs. | TEXT (from env) | P0 |
| 17 | Central-claim overreach | Rewrite abstract + conclusion + the "retire area-based advice" sentence to the reviewer's narrower, still-strong framing. | TEXT | P0 |
| 18 | C1-C5 each "narrower than written" | Add an explicit scope clause to each finding (centre-square, synthetic capture, four software decoders, tested payloads/versions). | TEXT | P0 |

---

## Execution order
1. **P0 text pass (no new data needed):** 17 central claim, 18 C1-C5 scope clauses, 4 contrast reframe, 5 phone/real-world narrowing, 13 figure numbering, 14 P95 terminology, 15 artifact language, 16 decoder versions, 2/6 "area ≠ damage" + de-precision wording. Gets the paper from "overconfident" to "defensible" immediately.
2. **P0/P1 analyses (agent, over committed matrices/data):** 2 damage decomposition (`analysis/damage.py`), 8 calibration (`analysis/calibration.py`), 9 per-decoder/worst-case scores, 6 binomial CIs (extend `analysis/ci.py`), 1 oracle decode (`analysis/oracle.py`), 10 version/mask reporting.
3. **P1 reruns (agent, compute):** 3 inversion quiet-zone conditions, 10 a non-URL payload mode, optional higher-N near boundaries.
4. **Gated (Sam):** 12 device matrix (HW), 11 logo-geometry scope call (DECIDE), 15 Zenodo deposit (RELEASE).

## Status (2026-07-06): agent-doable revision items COMPLETE

All P0 text + all agent-doable phase-2 analyses are done, verified, and wired into `paper/preprint.md` (PDF rebuilt):
- **#1 oracle** DONE, `analysis/oracle.py` → `data/oracle.json`. Pristine-capture decode separates front-end from RS capacity: even an undegraded capture tolerates only ~16% area at H (all four decoders fail together), the degraded ~9% is front-end/capture limited, and at L the ceiling is already codeword limited. §5 rewritten from "future work" to the result.
- **#2 damage**, **#8 calibration** DONE earlier (`damage.py`, `calibration.py`).
- **#3 inversion conditions** DONE, `analysis/inversion_conditions.py`. Four-condition rerun proves the ZBar/OpenCV inversion failure is genuine module-polarity, not a quiet-zone artifact (a compliant light quiet zone does not recover them; it even breaks ZXing). §3.3 caveat replaced with the result.
- **#6 binomial CIs** DONE, `analysis/binomial_ci.py` → `data/binomial_ci.json`. Exact Clopper-Pearson per-cell intervals; §2 Uncertainty rewritten.
- **#7 three-layer uncertainty** DONE (§2: capture / grid-spacing / design-space, design-space uncaptured).
- **#10 payload modes** DONE, `analysis/payload_modes.py` → `data/payload_modes.json`. Same 25 chars → version 2/3/4 (numeric/alphanumeric/byte); mode acts via version, cliff is mode-independent; wired into §3.4.
- **#9 scorer** DONE, `analysis/export_scorer.py` rewritten. Now fits a SEPARATE logistic per decoder (no decoder input), exposes worst-case + target profiles (modern-phone = zxing/WeChat, kiosk/embedded = ZBar/OpenCV), and emits a safe/risky/fragile GRADE calibrated to held-out worst-case decode rate (safe band decodes 98%, risky 86%, fragile 5%) instead of the miscalibrated logistic probability. Per-decoder held-out AUC 0.94 to 0.97. Verified: an inverted code grades fragile worst-case but safe for modern-phone (per-decoder opencv/zbar 0, zxing/wechat 1). §3.6 updated. Exports `scorer/scannability_score.{ts,py}` + `scannability_model.json`.

**Remaining before publication (all Sam-gated or blocked on the device scans):**
- **#12 device matrix** (HW, Sam scanning) under **capture protocol v1** (`validation/DEVICE-MATRIX.md`: measured 25 cm, lux-metered 200-600 lx per session, no zoom, flash off, default camera app; the harness stamps every scan with its session and MEASURES presentation-to-decode time in the guided `/run` mode, so the 10 s / 30 s outcome windows are server-timed; device details incl. camera capabilities auto-collected; no-session scans export as `pilot` and are excluded) → then `analysis/device_matrix.py` folds `device_matrix.csv` + `devices.json` into §4 (build it against the first REAL protocol CSV). Data restarted clean 2026-09-27: Pixel-7 pilot archived as `results-pilot-pixel7.json` (cited in §4), fresh `results.json`.
- Regenerate figures if any change; rebuild PDF; final claims-consistency read; Zenodo DOI (#15); commit + `tools/split.sh`.

## Decisions taken (2026-07-04, Sam)
- **(11) Bound to centre-square for V1**; note corner placement as an untested mitigation; geometry variety is a follow-up.
- **(12) Multi-device validation is IN V1.0** (not V1.1). Sam's inventory: 3 modern Android phones, 2 older Android tablets, 1 modern laptop webcam, 1 older laptop camera, + a mid-range iPhone to be acquired (fills the only-Android gap; iOS uses its own scan engine). Plus a ZBar-app and a ZXing-app on one Android to sample those engines directly on hardware. Target matrix ~8 devices x {native / ZBar-app / ZXing-app / webcam-library}.
- **Timing: V1.0 ships with narrowed claims + phase-2 analyses + the device matrix** (no V1.1 split).

## Device matrix build (agent prep + Sam scans)
- `validation/phone_test.py` upgraded to a **per-device** harness (set the active device on the Mac; each device's scans record to its own bucket; live matrix + combined export). Native-camera devices (phones, tablets, iPhone) use it directly.
- `validation/webcam_test.py` (new): runs the library decoders (OpenCV/ZBar/zxing-cpp) on a laptop webcam feed against the printed sheet, auto-logging pass/fail. Covers the webcam/kiosk/OpenCV-class hardware.
- `validation/DEVICE-MATRIX.md` (new): the runbook (which sheet, fixed distance, 100% print scale, the app pair, device labels).
- `analysis/device_matrix.py` (new, after Sam scans): aggregates all device buckets into the §4 per-device pass/marginal/fail + agreement table and a figure.
