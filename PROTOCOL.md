# The Scannability Frontier: Pre-Registered Study Design

**Working title of the paper:** *Aesthetics vs. Scannability: An Empirical Frontier for Stylised QR Codes across Decoders, Occlusion, Contrast and Resolution*

**Status:** pre-registration (design frozen before data collection). Version 1.0.
**Authors:** OpenQR Research. **License:** artifacts CC-BY-4.0, code Apache-2.0.
**Amendments:** v1.1 (2026-11-17) appended at the end. The v1.0 text above is frozen and unchanged; §0 item 1's "codeword-erasure budget" phrasing is corrected by amendment A6.

---

## 0. Why this study exists (first principles)

A QR code is not a picture; it is a **channel**. Denso Wave (1994) designed it as a 2-D matrix of modules carrying a bitstream protected by Reed–Solomon (RS) error correction. The decoder's job is an estimation problem: *locate* the symbol (finder/alignment patterns), *sample* each module to a bit, *binarise*, *de-interleave*, and *RS-correct* up to the redundancy budget. Everything a designer does for beauty, a centre logo, low-contrast brand colours, rounded "fluid" modules, printing small, is **noise injected into that channel**. The whole practice of "styling a QR code" is, information-theoretically, *spending margin*.

The industry manages this spend with folklore, not measurement. The single most repeated claim is:

> "Use error-correction level H: it tolerates 30% damage, so you can cover ~30% of the code with a logo."

This is **wrong in a specific, quantifiable way**, and nobody has published the correction with data:

1. **The 30% is a codeword-erasure budget, not a visual-area budget.** RS level H recovers up to ~30% of *codewords*, and only when erasures are spread so no single RS block exceeds its per-block correction capacity. A logo is a *contiguous* occlusion, it concentrates erasures into a few interleaved blocks. The *effective* visual ceiling is therefore lower than 30%, and the gap depends on version, masking and the interleaving geometry.
2. **Correction never runs if detection fails first.** Below a resolution/contrast threshold the decoder cannot even locate or sample the grid, so the RS budget is irrelevant. Real failure is dominated by the *front end*, not the RS back end, the opposite of the folklore's mental model.
3. **Higher EC is not free.** At a **fixed physical size**, raising EC inflates the symbol version (more modules), shrinking each module. Under a resolution or blur limit this *reduces* samplability. So "more error correction" can **lower** real-world decode success. We call this the **EC paradox** and predict it is observable.

No open, decoder-stratified, reproducible dataset maps where the true cliff edges are. Vendors publish none (their advice is liability-driven: "keep it simple"). Academic QR work concentrates on *capacity extension* (colour/high-density codes) and *aesthetic generation* (diffusion-based beautiful codes), not on **robustness measurement of ordinary stylised codes**, the thing 100% of real designers actually ship. That is the gap.

### Contributions we commit to (falsifiable)
- **C1: The occlusion gap.** Quantify effective centre-logo occlusion ceiling per EC level and show it sits materially *below* the nominal RS percentage. *Prediction:* ceiling(H) < 30% of area; ordering L<M<Q<H holds for occlusion tolerance.
- **C2: Decoder-stratified frontiers.** Show decode success is dominated by the **worst-case decoder**, and that decoders differ enough that a code "works" (author's phone) yet fails in the field. Publish a per-decoder robustness frontier.
- **C3: The contrast floor, in WCAG units.** Locate the minimum foreground/background **luminance contrast ratio** (the same metric used for web accessibility, WCAG 2.x) for reliable decode, and test whether **light-on-dark ("inverted")** codes underperform. Bridges QR robustness to an accessibility-native metric designers already understand.
- **C4: The EC paradox at fixed physical size.** Demonstrate at least one regime (small size / blur) where raising EC *reduces* decode success because of version inflation.
- **C5: A predictive Scannability Margin score.** Fit a simple, interpretable model from the data that predicts decode probability from design-time features (EC, modules-per-inch-equivalent, contrast ratio, occlusion %, module style). Ship it as an open scoring function OpenQR (and anyone) can compute *before* printing, turning folklore into a design-time metric.

C5 is the connective leap: reframe five scattered heuristics as **one budget equation** and expose it as a tool.

---

## 1. Factors and levels

Baseline (reference) symbol unless a factor is being swept: payload = a realistic dynamic-code URL, EC = Q, black-on-white, square modules, no logo, rendered at high resolution.

**Payloads (fixed set, to control version/density):**
- `P_short` = `https://oqr.to/aB3xK` (21 chars: realistic short dynamic link → low version)
- `P_med`   = `https://openqr.uk/r/aB3xK9` (26 chars)
- `P_long`  = 120-char URL with query params (forces a higher version at fixed EC)

**Factor A: Error-correction level:** L, M, Q, H.

**Factor B: Centre-logo occlusion** (opaque square knockout at symbol centre, mimicking the dominant real pattern): 0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40 % of total symbol **area**. (√area gives the side fraction.) Two knockout styles: *hard* (solid white pad, the common "excavate + quiet zone" logo) and *overlay* (opaque block with no module clearing) to separate "designed" vs "naive" logo placement.

**Factor C: Contrast / colour:**
- *Luminance sweep* (hue fixed, dark-on-light): foreground greys giving WCAG contrast ratios ≈ {1.5, 2, 3, 4.5, 7, 10, 15, 21}:1 against white.
- *Inversion:* the same ratios light-on-dark.
- *Hue-at-fixed-luminance:* colour pairs (e.g. navy/cream, red/white, green/white) held at matched contrast ratios to isolate hue from luminance.

**Factor D: Module style** (deformation of the ideal square lattice): `square`, `rounded`, `dots`, `gapped` (reduced module fill factor). Generated by post-processing the module matrix so geometry is controlled and reproducible.

**Factor E: Capture resolution / degradation (the camera proxy).** Each rendered symbol is passed through a degradation pipeline emulating a real capture at a given **pixels-per-module (ppm)** ∈ {1, 1.5, 2, 3, 4, 6, 8}, then optional Gaussian blur (σ tied to ppm), sensor noise (Gaussian, σ ∈ {0, 3, 8} DN), JPEG compression (Q ∈ {40, 75, 100}), and small perspective+rotation jitter (±10°, ±8° tilt). ppm is the key external-validity axis: it converts "module size × print size × camera distance" into one number.

**Decoders (the response is measured on all, independently):**
- `zbar` (pyzbar): ubiquitous embedded decoder.
- `opencv`: OpenCV `QRCodeDetector`.
- `wechat`: OpenCV WeChat CNN detector+super-resolution (proxy for modern phone-grade robustness; billions of real scans).
- `zxing`: `zxing-cpp` (canonical ZXing lineage; Android heritage).

Native iOS/Android camera stacks cannot be headlessly automated at scale; `wechat` + `zxing` are their closest open proxies. A small **manual real-device validation sample** (Appendix M) checks that the library frontier is conservative vs real phones.

---

## 2. Design

Full-factorial over A×B×C×D×E is ~10^5 cells; we use a **fractional design**: one-factor-at-a-time sweeps from baseline for main effects, plus three **targeted interaction grids** where theory predicts the interesting physics:
- **G1 = A × B × E** (EC × occlusion × ppm) → C1, C4.
- **G2 = A × C(luminance+inversion) × E** → C3.
- **G3 = A × D × E** → module-style penalty.

**Replication of stochastic degradation:** every (cell) is rendered once deterministically, then degraded with **N = 12 random capture samples** (fresh noise/JPEG/jitter seeds) per cell; the response for a (cell, decoder) is the **decode success rate** over those 12. Seeds are logged (reproducible). Total decode attempts target ≈ 1.5–3 × 10^5 across all decoders, feasible headless overnight.

**Primary response:** `p_decode` ∈ [0,1] per (cell, decoder), and the pooled **worst-case** and **any-decoder** rates.
**Secondary:** decode latency (ms), and detected-but-not-decoded vs not-detected (front-end vs back-end failure attribution, where the decoder exposes it).

---

## 3. Analysis plan (fixed in advance)

- **Frontiers.** For each decoder and EC level, fit a logistic curve of `p_decode` vs the swept factor; report the **P50 and P95 thresholds** (factor value giving 50% / 95% decode). "Safe design limit" = P95 of the **worst-case decoder**.
- **C1 occlusion gap** = nominal RS area budget − measured P95 occlusion ceiling. Report per EC/version.
- **C3** = P95 contrast ratio; two-sample test of inverted vs normal at matched ratios.
- **C4 EC paradox** = sign of ∂p_decode/∂EC at fixed physical size within the small-ppm regime; we look for a crossover where H < L.
- **C5 model.** Logistic regression (and a gradient-boosted comparator) predicting decode from {EC ordinal, ppm, contrast ratio, occlusion %, inverted flag, module style, version}. Report AUC on a held-out payload (`P_long` held out for external validity) and publish coefficients as the interpretable **Scannability Margin** score. Pre-registered success bar: **AUC ≥ 0.85** held-out.

**Stopping rule:** design frozen here; we run the full planned grid before looking at C5 fit quality; no factor added post hoc without labelling it exploratory.

---

## 4. Threats to validity (stated up front)
- **Library ≠ camera.** Mitigated by the ppm/blur/noise/JPEG proxy and the manual device sample; we report library decoders as a *conservative lower bound* on modern phones (which use CNN detectors closer to `wechat`).
- **Logo = centre square** is the dominant but not only pattern; we scope the claim to centre occlusion and flag corner/scatter logos as future work.
- **Print physics** (ink bleed, substrate) not simulated; ppm+blur approximate it; flagged.
- **Decoder versions** pinned in `requirements.txt` and reported (results are version-specific by construction, that is the point of C2).

---

## 5. Artifacts to publish
- `harness/` reproducible pipeline (Apache-2.0).
- `data/results.parquet` + `data/summary.csv` (every attempt + per-cell rates).
- `data/corpus/` sample rendered symbols.
- Zenodo deposit → DOI; preprint (SSRN/arXiv cs.CV·cs.HC); figures; the Scannability Margin scorer as a standalone function.

---

## Amendments, v1.1 (2026-11-17, post hoc, after external peer review)

Written and to be externally timestamped (OSF) **before** the amended analyses below are run. The v1.0 design and analysis plan above are frozen; these amendments correct errors found in review and extend the analysis of the **already-collected** data. No new capture data enters v1.1.

**A1. Estimator (change of primary, disclosed).** The primary occlusion/threshold estimator becomes piecewise-linear interpolation between measured factor levels (`analysis/headline.py`), with the v1.0-registered logistic fit retained as a smoothed cross-check. Both artifacts (`data/headline.json`, `data/summary.json`) remain published side by side. Reason: the worst-case occlusion curve is plateau-then-cliff; a symmetric sigmoid's P95 crossing lands inside the zero tail (H: ~14% vs the measured edge ~9%). Reported thresholds will additionally be given as **bracketing grid levels** (the honest resolution of a 4-point grid), with interpolated values secondary.

**A2. Codeword-level damage audit (new analysis of existing symbols).** v1.0's §0 item 1 and the preprint's "codeword-erasure budget" framing are **wrong as written**: the nominal 7/15/25/30% figures are capacities for errors at *unknown positions* (t = floor(r/2) per RS block); erasure capacity is roughly double. The amended analysis (`analysis/codeword_audit.py`) will, for the exact benchmark symbols: implement ISO/IEC 18004 module placement and block de-interleaving, map each occlusion level's changed modules to corrupted codewords **per interleaved RS block**, compare against each block's t, and locate the first occlusion at which any block overflows t. Validation: total codeword counts must match the spec for v2-v4, and the de-interleaved data codewords of the undamaged matrix must round-trip to the exact payload (byte-mode parse). The per-block table at the pristine-decode failure point will be reported in the paper, and the RS mechanism prose rewritten to follow the measured result (codeword granularity plus per-block capacity), whether or not it confirms the pristine ceiling as an RS limit.

**A3. Encoder EC-boosting (newly discovered deviation, disclosed).** `segno.make`'s default `boost_error=True` was never disabled, so requested-L symbols with spare capacity are silently encoded at a higher effective EC. For the 26-char payload, requested L and M are the **identical symbol** (v2, effective M): the EC axis has three distinct configurations, not four. v1.1 will report the effective EC per cell (from `analysis/payload_modes.py`), relabel accordingly, and mark true-L as untested. A true-L column is deferred to the follow-up study.

**A4. damage.py payload correction (bug fix).** `analysis/damage.py` analysed a 28-char stand-in payload rather than the benchmark's 26-char string, so its version/mask/dark-fraction table described different symbols than the occlusion grid used. Corrected to the exact benchmark payload; `data/damage.json` and the dependent metadata in `data/oracle.json` regenerated. Decode results in `oracle.json` are unaffected (they were rendered from the correct payload; only the version/changed-modules context came from damage.json).

**A5. Scorer grade cutoffs (fixing circularity).** v1.0's safe/risky/fragile cutoffs were fitted over all 907 cells (training included) while described as calibrated against the held-out payload. Amended: cutoffs refitted on training cells only; both the refit values and the held-out band rates reported. Additionally: permutation feature importance on the held-out set (impurity importance is biased against low-cardinality features), leave-one-payload-out cross-validation, and a boundary-band discrimination check (px/module 2-4, occlusion near the step) will be reported.

**A6. Reporting additions from already-collected grids (no new data).** Numeric results for module style (G3), hue pairs (G5h) and overlay-vs-excavated occlusion (G5), collected but unreported in v1.0; thresholds additionally reported at 90/95/99% success; nominal-vs-realised occlusion coverage side by side; Clopper-Pearson bounds at all EC levels; the composition of pooled n stated explicitly.

**A7. Claims scoping (editorial, binding).** v1.1 scopes every headline number to: three payload strings, one automatically selected mask each, versions 2-4, four pinned software decoders, the synthetic capture proxy. Worst-case (min-over-decoders) thresholds are labelled a conservative summary; per-decoder ceilings become primary. Uncited deployment claims about kiosks/POS/embedded readers are removed. WeChat's ZXing-derived decode stage is disclosed. The Pixel 7 check is reported as a single-device pilot, not proxy validation.

**A8. Registration practice (going forward).** The v1.0 protocol lacked an external timestamp (protocol, dataset and preprint share one repository commit), so "pre-registered before data collection" is not independently verifiable; v1.1 claims only protocol-first design with fully disclosed deviations. The **follow-up study's** protocol (multi-payload/mask generalisation, versions >=5, additional decoders incl. Apple Vision and ML Kit, fixed-print-size EC comparison, proxy ablation) will be deposited on OSF **before** any of its data is collected.

