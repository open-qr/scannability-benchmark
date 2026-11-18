# The Scannability Frontier

*An empirical, decoder-stratified benchmark of stylised QR codes.*
An [OpenQR Research](https://openqr.uk) study. Author: Sam Moreton.

An open benchmark of how far you can push QR-code **styling** (centre logos, brand colour/contrast, inversion, module shape, small print, resolution) before a code stops scanning, measured across four pinned decoders: ZBar, OpenCV `QRCodeDetector`, OpenCV-WeChat (CNN + super-resolution; decode core ZXing-derived) and ZXing (`zxing-cpp`). Conditional on: three payload strings, versions 2–4, one automatic mask each, the synthetic capture proxy. Preprint v1.1 (peer-review revision).

## Headline findings
- The "**cover ~30% with a logo at level H**" rule conflates a codeword error-correction rate with an area share. The reliable occlusion ceilings are **~9% of symbol area (bracket 8–12%)** if OpenCV-class readers must succeed, **~16% (bracket 16–20%)** for the other three libraries. A per-block Reed–Solomon audit shows the 16% pristine ceiling *is* the RS budget: a 16%-area pad corrupts 28 of the H symbol's 100 codewords ([7,7,7,7] of t=8 per block) and the first block overflow at 18% is where every tested decoder fails.
- **Error correction** does not move the ~3 px/module resolution cliff for short/medium payloads, but **doubles occlusion headroom** (M→H) and lowers the cliff for long payloads (3.9 → 3.0 px/module).
- Decoders are **not interchangeable**: stress-grid decode rate ranges 0.28–0.54, and at ≤2 px/module per-library success spans 0.02–0.25. The *weakest decoder your audience uses*, not the author's phone, defines real safety.
- Contrast can go **down to ~2:1** (below WCAG-AA) *if resolution is adequate*, but **inverted (light-on-dark) codes fail completely on two of four tested decoders** (a documented conformance difference: ZXing retries inverted images by default).
- A simple design-time model predicts decode success at leave-one-payload-out AUC **0.81–0.99** (held-out long payload 0.98), packaged as an open **Scannability Margin** score you can compute before printing.

## Layout
- `PROTOCOL.md`: protocol (frozen v1.0) + v1.1 amendments.
- `harness/`: reproducible render + degrade + 4-decoder harness (Apache-2.0).
- `data/`: decode results and summaries (CC-BY-4.0), incl. `codeword_audit.json` (per-block RS audit), `model_diagnostics.json`, `factor_report.json`.
- `analysis/`: models, headline reconciliation, codeword audit, figures.
- `scorer/`: the Scannability Margin scorer (TypeScript + Python + JSON).
- `validation/`: self-recording real-device harness (a single-device Pixel 7 pilot, 28/28 cells, is consistent with the strong-tier prediction; a multi-device matrix is the follow-up).
- `paper/preprint.md`: the preprint + figures.

## Reproduce
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r harness/requirements.txt
cd harness && python run.py --full -n 16 && python cliff.py
cd ../analysis && python analyze.py && python headline.py && python ci.py && python figures.py && python export_scorer.py
```
Note: `analyze.py`, `headline.py` and `ci.py` regenerate committed data files deterministically (seeded).

## Licence & citation
Code Apache-2.0 (`LICENSE`); data, figures and paper CC-BY-4.0 (`LICENSE-CC-BY-4.0.txt`).
Cite via the Zenodo DOI **10.5281/zenodo.24327737** (v1.1, published 2026-11-18: https://zenodo.org/records/24327737). Correspondence: research@openqr.uk
