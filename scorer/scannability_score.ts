// Scannability Margin, OpenQR Research. Per-decoder held-out AUC {"opencv": 0.9651, "zbar": 0.9744, "zxing": 0.9636, "wechat": 0.9388}. CC-BY-4.0.
// Predicts, from design-time features, P(a single camera capture decodes) for EACH decoder,
// then combines them: worstCase = weakest deployed reader (the safe spec), or a target profile.
// The scalar margin RANKS; the safe/risky/fragile grade is calibrated to held-out decode rates.
// It is not a calibrated probability (use the gradient-boosted model for that).

export interface ScanFeatures {
  ecLevel: 'L' | 'M' | 'Q' | 'H';
  pxPerModule: number;        // rendered/printed resolution (camera px per module)
  contrastRatio: number;      // WCAG fg/bg contrast ratio, e.g. 21 for black-on-white
  occlusionPct: number;       // centre-logo area as % of symbol (0..40)
  version: number;            // QR version (1..40)
  inverted: boolean;          // light modules on dark field
}
export type Profile = 'worst_case' | 'modern_phone' | 'kiosk_embedded';

const EC = { L: 0, M: 1, Q: 2, H: 3 } as const;
const M = {
  opencv: { b0: -6.936831, c: {"ec_ord": -0.229233, "ppm": 1.874114, "contrast_ratio": 0.036393, "occ": -0.595234, "version": 0.758883, "inverted_i": -13.805743} },
  zbar: { b0: -4.927565, c: {"ec_ord": -0.053928, "ppm": 1.306306, "contrast_ratio": 0.03722, "occ": -0.397301, "version": 0.621991, "inverted_i": -11.475897} },
  zxing: { b0: -4.454886, c: {"ec_ord": -0.103343, "ppm": 1.58174, "contrast_ratio": 0.032596, "occ": -0.46881, "version": 0.483104, "inverted_i": -0.098011} },
  wechat: { b0: -4.332219, c: {"ec_ord": -0.019996, "ppm": 1.36952, "contrast_ratio": 0.069208, "occ": -0.431907, "version": 0.548228, "inverted_i": -0.976405} }
} as const;
const PROFILE: Record<Profile, (keyof typeof M)[]> = {
  worst_case: ["opencv", "zbar", "zxing", "wechat"],
  modern_phone: ["zxing", "wechat"],
  kiosk_embedded: ["opencv", "zbar"],
};
const CUT = { risky: 0.5775, safe: 0.9917 };

function feat(f: ScanFeatures): Record<string, number> {
  return { ec_ord: EC[f.ecLevel], ppm: f.pxPerModule, contrast_ratio: f.contrastRatio,
           occ: f.occlusionPct, version: f.version, inverted_i: f.inverted ? 1 : 0 };
}
export function scoreByDecoder(f: ScanFeatures): Record<keyof typeof M, number> {
  const x = feat(f); const out: any = {};
  for (const d of Object.keys(M) as (keyof typeof M)[]) {
    const m = M[d]; let z = m.b0;
    for (const k of Object.keys(m.c)) z += (m.c as any)[k] * x[k];
    out[d] = 1 / (1 + Math.exp(-z));
  }
  return out;
}
export function scannabilityMargin(f: ScanFeatures, profile: Profile = 'worst_case'): number {
  const s = scoreByDecoder(f);
  return Math.min(...PROFILE[profile].map(d => s[d]));  // weakest reader in the profile
}
export function scannabilityVerdict(f: ScanFeatures, profile: Profile = 'worst_case'):
    { margin: number; grade: 'safe'|'risky'|'fragile'; reasons: string[] } {
  const margin = scannabilityMargin(f, profile);
  const reasons: string[] = [];
  if (f.pxPerModule < 3.3) reasons.push('resolution below ~3.3 px/module, the dominant failure cause');
  if (f.occlusionPct > 9) reasons.push('logo covers >9% of area, above the worst-case decoder ceiling');
  if (f.inverted) reasons.push('inverted (light-on-dark) codes fail on 2 of 4 tested libraries (ZBar, OpenCV)');
  if (f.contrastRatio < 2) reasons.push('contrast below ~2:1');
  const grade = margin >= CUT.safe ? 'safe' : margin >= CUT.risky ? 'risky' : 'fragile';
  return { margin, grade, reasons };
}
