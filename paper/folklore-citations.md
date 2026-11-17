# Folklore citations (resolved 2026-11-17)

The paper's foil, the "cover ~30% of the code with a logo at error-correction level H" rule, is cited in §1 and the references with archived, verified instances. Every quote below was read from the live page on 2026-11-17 (via DataForSEO SERP discovery + full-page fetch) and snapshotted to the Wayback Machine.

## The area reading (the claim the benchmark refutes)
- MyQR Barcode Generator, "QR Code Design Tips": **"Keep logos within 30% of total QR code area. Larger than this risks breaking scannability."** and **"Use Level H (30%) error correction when adding logos."** Ref [15]. Archive: web.archive.org/web/20261117204101/https://myqrbarcodegenerator.com/en/blog/qr-code-design-tips
- QR-Verse, "QR Code Error Correction: Why Logos Still Scan": **"you can cover nearly a third of the code and still get a perfect read."** Ref [16]. Archive: web.archive.org/web/20261117204120/https://qr-verse.com/en/blog/qr-code-error-correction-explained

## The distinct width reading (circulates alongside; 30% of width = 9% of area for a square)
- QR-Verse, same page: **"a centered logo should not exceed 30% of the total code width."** Ref [16].

## Practitioners already correcting the misreading (converging evidence, cited in §1)
- Tabres, "How to Add Your Logo to a QR Code Without Breaking It": **"'Level H repairs 30% damage' gets read as 'so my logo can cover 30% of the code.' It can't."** (their own guidance: ~20% of width, i.e. 4-6% of area, close to our measured ceilings). Ref [17]. Archive: web.archive.org/web/20261117204139/https://tabres.com/articles/how-to-add-logo-to-qr-code-without-breaking-it

## The vendor source (defines the percentages as codeword rates, never area)
- DENSO WAVE, "Error correction feature": restoration rates "for total codewords". Ref [2]. https://www.qrcode.com/en/about/error_correction.html

## Inversion conformance threads (§3.3)
- zbar PR #18 "Add support for inverted codes", opened Feb 2019, MERGED: "This patch enables zbar to scan inverted codes." Our pinned default deployment path (pyzbar 0.1.9 wrapping host libzbar, default config) still reads 0% on inverted. Ref [18]. https://github.com/mchehab/zbar/pull/18
- OpenCV issue #30588 "QRCodeDetector does not detect inverted (white-on-black) QR codes", opened Oct 2026, open at access. Ref [19]. https://github.com/opencv/opencv/issues/30588

Discovery method (for reproducibility): DataForSEO SERP API (Google organic, US/en) queries "qr code logo 30% error correction", "qr code generator logo error correction level H guide", "zbar white on black qr code site:github.com", "opencv qr code detector inverted colors site:github.com"; candidates verified by full-page fetch before quoting. Total API spend, reconciled against the account balance: $0.038 (11 live SERP tasks).
