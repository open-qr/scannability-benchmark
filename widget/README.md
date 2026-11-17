# Scannability Score widget

A self-contained, zero-dependency Custom Element (`<scannability-widget>`) that runs
the study's Scannability Margin model live in the browser. No framework, no network.
It is the interactive companion to the scannability study and is embeddable anywhere.

## Try it

Open `demo.html` (serve over HTTP so the ES module loads):

```bash
python3 -m http.server 8000   # then open http://localhost:8000/widget/demo.html
```

`demo.html` also carries a `<noscript>` static fallback table, so it degrades to a
readable worked example when JavaScript is off.

## Embed

```html
<script type="module" src="dist/scannability-widget.js"></script>
<scannability-widget></scannability-widget>
```

It uses Shadow DOM, so it will not collide with host styles. Theme it by setting CSS
custom properties on the element (`--sw-bg`, `--sw-fg`, `--sw-accent`, `--sw-safe`,
`--sw-risky`, `--sw-fragile`, `--sw-font`). It emits a `scan-change`
`CustomEvent` (`detail: { p, grade, reasons, features }`) on every change.

Works inside React/Vue/Svelte unchanged (Custom Elements are framework-agnostic). In
React, import the module once and render `<scannability-widget />`.

## Build

The bundle in `dist/` is produced from the TypeScript source, which imports the
model verbatim from `../scorer/scannability_score.ts`:

```bash
npx esbuild scannability-widget.ts --bundle --format=esm --outfile=dist/scannability-widget.js
```

The model (`scannability_score.ts`) is the single source of truth for the numbers;
the widget is only its UI. CC-BY-4.0.
