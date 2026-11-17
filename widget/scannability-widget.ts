// <scannability-widget>: a self-contained, zero-dependency Custom Element that
// runs the OpenQR Scannability Margin model live in the browser. No framework, no
// network. Embeddable anywhere (drops into React/Vue/plain HTML). Shadow DOM keeps
// its styles isolated. Themeable via CSS custom properties on the host.
//
//   <script type="module" src="scannability-widget.js"></script>
//   <scannability-widget></scannability-widget>
//
// Logic ports verbatim from ../scorer/scannability_score.ts (the study's per-decoder model).
// The margin RANKS a design; the safe/risky/fragile grade is calibrated to the held-out
// worst-case decode rate. It is not a calibrated decode probability, and the widget never
// presents it as one.

import { scannabilityVerdict, scoreByDecoder, type ScanFeatures, type Profile }
  from "../scorer/scannability_score.ts";

type Grade = "safe" | "risky" | "fragile";

const DEFAULTS: ScanFeatures = {
  ecLevel: "H",
  pxPerModule: 4,
  contrastRatio: 21,
  occlusionPct: 10,
  version: 6,
  inverted: false,
};

// The four library decoders the study benchmarks, in weak-tier-then-strong-tier order.
const DECODERS: { key: string; label: string }[] = [
  { key: "opencv", label: "OpenCV" },
  { key: "zbar", label: "ZBar" },
  { key: "zxing", label: "ZXing" },
  { key: "wechat", label: "WeChat" },
];

const GRADE_COLOR: Record<Grade, string> = {
  safe: "var(--sw-safe, #15803d)",
  risky: "var(--sw-risky, #b45309)",
  fragile: "var(--sw-fragile, #b91c1c)",
};

function decoderState(p: number): { color: string; mark: string } {
  if (p >= 0.9) return { color: "var(--sw-safe, #15803d)", mark: "reads" };
  if (p >= 0.6) return { color: "var(--sw-risky, #b45309)", mark: "marginal" };
  return { color: "var(--sw-fragile, #b91c1c)", mark: "fails" };
}

const styles = /* css */ `
  :host {
    --sw-bg: #ffffff; --sw-fg: #0f172a; --sw-muted: #64748b; --sw-line: #e2e8f0;
    --sw-track: #e2e8f0; --sw-accent: #2563eb;
    display: block; color: var(--sw-fg);
    font: 15px/1.5 var(--sw-font, system-ui, -apple-system, "Segoe UI", sans-serif);
    background: var(--sw-bg); border: 1px solid var(--sw-line); border-radius: 14px;
    container-type: inline-size;
  }
  @media (prefers-color-scheme: dark) {
    :host {
      --sw-bg: #0b1120; --sw-fg: #e2e8f0; --sw-muted: #94a3b8; --sw-line: #1e293b;
      --sw-track: #1e293b; --sw-accent: #60a5fa;
      --sw-safe: #4ade80; --sw-risky: #fbbf24; --sw-fragile: #f87171;
    }
  }
  .wrap { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 20px; }
  @container (max-width: 520px) { .wrap { grid-template-columns: 1fr; } }
  fieldset { border: 0; margin: 0; padding: 0; display: grid; gap: 14px; }
  legend { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .row { display: grid; gap: 5px; }
  .row label { font-weight: 600; display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .row .val { font-variant-numeric: tabular-nums; color: var(--sw-accent); font-weight: 700; }
  input[type="range"] { width: 100%; accent-color: var(--sw-accent); height: 24px; }
  select { width: 100%; padding: 7px 9px; border: 1px solid var(--sw-line); border-radius: 8px;
    background: var(--sw-bg); color: var(--sw-fg); font: inherit; }
  .toggles { display: flex; flex-wrap: wrap; gap: 16px; }
  .toggle { display: flex; align-items: center; gap: 7px; font-weight: 600; cursor: pointer; }
  .toggle input { width: 18px; height: 18px; accent-color: var(--sw-accent); }
  .seg { display: inline-flex; border: 1px solid var(--sw-line); border-radius: 8px; overflow: hidden; }
  .seg button { border: 0; background: var(--sw-bg); color: var(--sw-muted); font: inherit; font-weight: 600;
    padding: 6px 11px; cursor: pointer; }
  .seg button[aria-pressed="true"] { background: var(--sw-accent); color: #fff; }
  .out { display: grid; gap: 12px; align-content: start; padding-left: 20px; border-left: 1px solid var(--sw-line); }
  @container (max-width: 520px) { .out { padding-left: 0; border-left: 0; border-top: 1px solid var(--sw-line); padding-top: 18px; } }
  .pill { display: inline-block; padding: 5px 14px; border-radius: 999px; font-weight: 800; font-size: 15px;
    letter-spacing: .04em; text-transform: uppercase; color: #fff; }
  .cap { color: var(--sw-muted); font-size: 13.5px; }
  .decoders { display: grid; gap: 6px; }
  .dhead { font-weight: 600; font-size: 12.5px; color: var(--sw-muted); text-transform: uppercase; letter-spacing: .03em; }
  .drow { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 13.5px; }
  .drow .dot { width: 9px; height: 9px; border-radius: 999px; display: inline-block; margin-right: 7px; }
  .drow .dname { font-weight: 600; }
  .drow .dmark { font-variant-numeric: tabular-nums; }
  ul.reasons { margin: 4px 0 0; padding-left: 18px; display: grid; gap: 6px; }
  ul.reasons:empty::after { content: "No risk signals for this profile at these settings."; color: var(--sw-muted); }
  ul.reasons li { color: var(--sw-fg); }
  @media (prefers-reduced-motion: no-preference) { .pill, .drow .dot { transition: color .15s, background-color .15s; } }
`;

class ScannabilityWidget extends HTMLElement {
  private f: ScanFeatures = { ...DEFAULTS };
  private profile: Profile = "worst_case";
  private root: ShadowRoot;

  constructor() {
    super();
    this.root = this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this.root.innerHTML = `<style>${styles}</style>${this.template()}`;
    this.bind();
    this.render();
  }

  private template(): string {
    const f = this.f;
    return /* html */ `
    <div class="wrap">
      <fieldset>
        <legend>QR design settings</legend>
        <div class="row">
          <label for="ec">Error correction <span class="val" id="ec-v"></span></label>
          <select id="ec" aria-label="Error correction level">
            ${(["L", "M", "Q", "H"] as const).map((e) => `<option value="${e}" ${e === f.ecLevel ? "selected" : ""}>${e}</option>`).join("")}
          </select>
        </div>
        <div class="row">
          <label for="ppm">Resolution (px per module) <span class="val" id="ppm-v"></span></label>
          <input type="range" id="ppm" min="1" max="12" step="0.5" value="${f.pxPerModule}">
        </div>
        <div class="row">
          <label for="occ">Centre-logo cover (% area) <span class="val" id="occ-v"></span></label>
          <input type="range" id="occ" min="0" max="40" step="1" value="${f.occlusionPct}">
        </div>
        <div class="row">
          <label for="contrast">Contrast ratio <span class="val" id="contrast-v"></span></label>
          <input type="range" id="contrast" min="1" max="21" step="0.5" value="${f.contrastRatio}">
        </div>
        <div class="row">
          <label for="version">QR version <span class="val" id="version-v"></span></label>
          <input type="range" id="version" min="1" max="40" step="1" value="${f.version}">
        </div>
        <div class="toggles">
          <label class="toggle"><input type="checkbox" id="inverted" ${f.inverted ? "checked" : ""}> Inverted (light-on-dark)</label>
          <span class="seg" role="group" aria-label="Reader audience">
            <button type="button" id="aud-worst" aria-pressed="true">Any reader</button>
            <button type="button" id="aud-modern" aria-pressed="false">Modern phones</button>
          </span>
        </div>
      </fieldset>
      <div class="out" aria-live="polite">
        <div><span class="pill" id="pill">&middot;</span></div>
        <div class="cap" id="verdict"></div>
        <div class="decoders">
          <div class="dhead" id="dhead">Reads on each tested decoder</div>
          <div id="decoders"></div>
        </div>
        <ul class="reasons" id="reasons"></ul>
      </div>
    </div>`;
  }

  private $(id: string): HTMLElement {
    return this.root.getElementById(id) as HTMLElement;
  }

  private bind() {
    (this.$("ec") as HTMLSelectElement).addEventListener("change", (e) => {
      this.f.ecLevel = (e.target as HTMLSelectElement).value as ScanFeatures["ecLevel"];
      this.render();
    });
    const num = (id: string, key: keyof ScanFeatures) =>
      this.$(id).addEventListener("input", (e) => {
        (this.f[key] as number) = parseFloat((e.target as HTMLInputElement).value);
        this.render();
      });
    num("ppm", "pxPerModule");
    num("occ", "occlusionPct");
    num("contrast", "contrastRatio");
    num("version", "version");
    this.$("inverted").addEventListener("change", (e) => {
      this.f.inverted = (e.target as HTMLInputElement).checked;
      this.render();
    });
    this.$("aud-worst").addEventListener("click", () => this.setProfile("worst_case"));
    this.$("aud-modern").addEventListener("click", () => this.setProfile("modern_phone"));
  }

  private setProfile(p: Profile) {
    this.profile = p;
    this.$("aud-worst").setAttribute("aria-pressed", String(p === "worst_case"));
    this.$("aud-modern").setAttribute("aria-pressed", String(p === "modern_phone"));
    this.render();
  }

  private render() {
    const f = this.f;
    const { margin, grade, reasons } = scannabilityVerdict(f, this.profile);
    const perDec = scoreByDecoder(f);
    this.$("ec-v").textContent = f.ecLevel;
    this.$("ppm-v").textContent = `${f.pxPerModule} px`;
    this.$("occ-v").textContent = `${f.occlusionPct}%`;
    this.$("contrast-v").textContent = `${f.contrastRatio}:1`;
    this.$("version-v").textContent = `v${f.version}`;

    const pill = this.$("pill");
    pill.textContent = grade;
    pill.style.background = GRADE_COLOR[grade];
    const who = this.profile === "worst_case"
      ? "any reader (kiosks, POS and in-app scanners included)"
      : "modern phone cameras";
    const VERDICT: Record<Grade, string> = {
      safe: `Reliable for ${who}.`,
      risky: `Marginal for ${who}. Test on real hardware before printing.`,
      fragile: `Likely to fail for ${who}.`,
    };
    this.$("verdict").textContent = VERDICT[grade];

    // Per-decoder chips are the honest quantitative signal (the margin is a ranking, not a
    // calibrated probability, so we do not surface it as a percentage).
    this.$("decoders").innerHTML = DECODERS.map((d) => {
      const p = perDec[d.key as keyof typeof perDec];
      const s = decoderState(p);
      return `<div class="drow"><span class="dname"><span class="dot" style="background:${s.color}"></span>${d.label}</span>` +
        `<span class="dmark" style="color:${s.color}">${s.mark}</span></div>`;
    }).join("");

    this.$("reasons").innerHTML = reasons.map((r) => `<li>${r}</li>`).join("");
    this.dispatchEvent(new CustomEvent("scan-change", {
      detail: { margin, grade, reasons, profile: this.profile, perDecoder: perDec, features: { ...f } },
      bubbles: true,
    }));
  }
}

if (!customElements.get("scannability-widget")) {
  customElements.define("scannability-widget", ScannabilityWidget);
}

export { ScannabilityWidget };
