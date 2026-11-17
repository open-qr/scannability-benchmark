"""Real-device validation harness for the Scannability study (multi-device).

The preprint's central external-validity caveat is that the four *library* decoders
(especially the strong-tier pair, WeChat and ZXing) are a proxy for a real phone
camera. This tool tests that directly: it renders a small, targeted sample of the
exact styled codes the benchmark uses (same qrgen renderer, no simulated degradation,
because the device camera is the real capture channel), each encoding a unique URL on
this machine. You scan each with the device's normal camera; a successful scan opens
the URL and self-records a PASS. Codes that will not scan you mark on the dashboard.
Every cell carries the study's *modern-decoder* prediction, so the dashboard scores
how well each device agrees with the paper.

Multi-device: devices identify themselves from their own request (a first-party cookie
groups one phone's scans; client hints name it), so there is no add/select step.
For laptop webcams (which cannot tap-to-open a URL) use `webcam_test.py` instead.

Standardised protocol v1 (DEVICE-MATRIX.md): every scan is stamped with the active
SESSION (lux, distance, operator, camera app), started from the dashboard before each
device pass. Scans with no active session export as `pilot` (pre-protocol data,
excluded from the paper's matrix).

Guided run (`/run`): the Mac presents the codes one at a time with a live clock; the
server timestamps presentation and the phone's URL-open, so time-to-decode is measured,
not judged. Auto-flags slow (>10 s) reads; marginal/no-scan are one-tap.

Device details are collected automatically: the confirmation page (on the device)
posts screen/model/hardware metrics, and a one-tap camera probe (over https) adds the
camera's zoom/torch/focus capabilities.

Run:  python phone_test.py            (devices must be on the same Wi-Fi)
Then: open the dashboard URL on this Mac, start a session, start a guided run, scan
      each presented code with the device, start a new session per device. Export when
      done. /sheet remains for free-order scanning.
"""
from __future__ import annotations
import os, sys, json, socket, csv, io, re, uuid, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
from qrgen import build_matrix, render, apply_center_logo, grey_for_ratio, contrast_ratio  # noqa: E402

CODES_DIR = os.path.join(HERE, "codes")
STATE_PATH = os.path.join(HERE, "results.json")
WHITE, BLACK = (255, 255, 255), (0, 0, 0)


# Each cell isolates one factor. `pred` is the study's prediction for a MODERN decoder
# (WeChat/ZXing), i.e. what a current phone should do if the library proxy is valid.
# pred: "pass" | "fail" | "edge" (near a measured threshold, either outcome is consistent).
def _cells():
    C = []
    def add(cid, group, pred, why, **r):
        C.append({"cid": cid, "group": group, "pred": pred, "why": why, "render": r})

    for cid, occ, pred in [("a00", 0, "pass"), ("a09", 9, "pass"), ("a18", 18, "edge"),
                           ("a24", 24, "fail"), ("a30", 30, "fail"), ("a36", 36, "fail")]:
        add(cid, "occlusion", pred, f"{occ}% logo at H (modern ceiling ~18%)", ec="H", occ=occ)
    add("bno", "inversion", "pass", "normal polarity, H", ec="H")
    add("bin", "inversion", "pass", "inverted light-on-dark, H (classical decoders fail here)",
        ec="H", inverted=True)
    for cid, ratio, pred in [("c45", 4.5, "pass"), ("c30", 3.0, "pass"),
                             ("c20", 2.0, "edge"), ("c15", 1.5, "edge")]:
        add(cid, "contrast", pred, f"{ratio}:1 contrast, H", ec="H", contrast=ratio)
    for cid, style in [("dro", "rounded"), ("ddo", "dots"), ("dga", "gapped")]:
        add(cid, "style", "pass", f"{style} modules, H", ec="H", style=style)
    add("elr", "ec-level", "edge", "EC L at 3 px/module (compare to ehr: EC should not rescue resolution)",
        ec="L", module_px=3)
    add("ehr", "ec-level", "edge", "EC H at 3 px/module (compare to elr: same cliff as L)",
        ec="H", module_px=3)
    for cid, mpx, pred in [("f02", 2, "fail"), ("f03", 3, "edge"), ("f04", 4, "pass"),
                           ("f06", 6, "pass"), ("f10", 10, "pass")]:
        add(cid, "resolution", pred, f"{mpx} screen-px/module at H (cliff ~3 px/module)",
            ec="H", module_px=mpx)
    for cid, mm, pred in [("p20", 0.20, "edge"), ("p25", 0.25, "edge"), ("p30", 0.30, "edge"),
                          ("p40", 0.40, "pass"), ("p50", 0.50, "pass"), ("p66", 0.66, "pass")]:
        add(cid, "print", pred, f"{mm:.2f} mm/module at H (printed size test)",
            ec="H", module_px=10, mm=mm)
    return C

CELLS = _cells()
BY_ID = {c["cid"]: c for c in CELLS}


def render_cell(cell, payload):
    r = cell["render"]
    ec = r.get("ec", "H")
    sym = build_matrix(payload, ec)
    fg, bg = BLACK, WHITE
    if r.get("inverted"):
        fg, bg = WHITE, BLACK
    elif "contrast" in r:
        fg = grey_for_ratio(r["contrast"])
    img = render(sym, module_px=r.get("module_px", 12), fg=fg, bg=bg, style=r.get("style", "square"))
    if r.get("occ", 0) > 0:
        img = apply_center_logo(img, sym, r["occ"] / 100.0, mode="hard", bg=bg)
    return img, sym


def build_assets(base_url):
    os.makedirs(CODES_DIR, exist_ok=True)
    meta = {}
    for cell in CELLS:
        payload = f"{base_url}/s/{cell['cid']}"
        img, sym = render_cell(cell, payload)
        img.save(os.path.join(CODES_DIR, f"{cell['cid']}.png"))
        meta[cell["cid"]] = {"version": sym.version, "modules": sym.n, "payload": payload}
    return meta


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# ---- device state (each scanning device identifies itself, no manual entry) ----
# STATE = {"active": <dev_id>|None, "current_session": <sid>|None, "run": <run>|None,
#          "sessions": {sid: {lux, distance_cm, operator, camera_app, display, deviations, started}},
#          "devices": {dev_id: {label, class, os, app, ua, probe:{...}, results:{cid:{...}}}}}
# A result without `sid` predates the protocol (or the session was forgotten): pilot data.
# run = {"rid": str, "i": <index into CELLS>, "cid": str, "t_present": epoch}
# A result recorded while its cell is the current run step gains run/rid and t_decode_s.
# A phone is identified from its own request: a first-party `sl_dev` cookie gives a stable
# per-device id (all of one phone's scans group into one bucket; two phones separate), and
# the User-Agent (upgraded by Sec-CH-UA-Model client hints on Chromium) gives the label.
# `active` = the device the Mac dashboard is viewing; it auto-follows the last phone to scan.
_GENERIC = {"phone", "tablet", "computer", "device"}

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "device"


def parse_ua(ua):
    ua = ua or ""
    os_name, model, app = "unknown OS", "", "browser"
    m = re.search(r"Android (\d+(?:\.\d+)?)", ua)
    if m:
        os_name = f"Android {m.group(1)}"
        mm = re.search(r";\s*([^;)]+?)\s+Build/", ua) or re.search(r"Android [^;]+;\s*([^;)]+?)\)", ua)
        if mm:
            model = mm.group(1).strip()
        if model in ("K", "wv"):  # Chrome froze the model in its reduced UA; client hints fill it
            model = ""
    elif "iPhone" in ua:
        os_name, model = "iOS", "iPhone"
        v = re.search(r"OS (\d+[_.]\d+)", ua)
        if v: os_name = "iOS " + v.group(1).replace("_", ".")
    elif "iPad" in ua:
        os_name, model = "iPadOS", "iPad"
        v = re.search(r"OS (\d+[_.]\d+)", ua)
        if v: os_name = "iPadOS " + v.group(1).replace("_", ".")
    elif "Mac OS X" in ua: os_name, model = "macOS", "Mac"
    elif "Windows" in ua: os_name, model = "Windows", "PC"
    elif "Linux" in ua: os_name, model = "Linux", "Linux"
    if "SamsungBrowser" in ua: app = "Samsung Internet"
    elif "EdgA" in ua or "Edg/" in ua: app = "Edge"
    elif "Firefox" in ua or "FxiOS" in ua: app = "Firefox"
    elif "CriOS" in ua or "Chrome" in ua: app = "Chrome"
    elif "Safari" in ua: app = "Safari"
    if "iPad" in ua or ("Android" in ua and "Mobile" not in ua): cls = "tablet"
    elif "iPhone" in ua or "Mobile" in ua: cls = "phone"
    elif os_name in ("macOS", "Windows", "Linux"): cls = "desktop"
    else: cls = "other"
    return {"model": model, "class": cls, "os": os_name, "app": app}


def device_meta(headers):
    ua = headers.get("User-Agent", "")
    p = parse_ua(ua)
    model = (headers.get("Sec-CH-UA-Model", "") or "").strip().strip('"') or p["model"]
    plat = (headers.get("Sec-CH-UA-Platform", "") or "").strip().strip('"')
    pver = (headers.get("Sec-CH-UA-Platform-Version", "") or "").strip().strip('"')
    os_name = (f"{plat} {pver.split('.')[0]}".strip() if pver else plat) if plat else p["os"]
    name = model or {"phone": "phone", "tablet": "tablet", "desktop": "computer"}.get(p["class"], "device")
    return {"label": f"{name} · {os_name} · {p['app']}", "class": p["class"],
            "os": os_name, "app": p["app"], "ua": ua}


def load_state():
    st = {"active": None, "devices": {}}
    if os.path.exists(STATE_PATH):
        d = json.load(open(STATE_PATH))
        if isinstance(d, dict) and "devices" in d:
            st = d
        elif isinstance(d, dict) and d and all(k in BY_ID for k in d):
            # migrate the committed flat single-device file (the Pixel 7 run)
            st = {"active": "pixel7-native", "devices": {"pixel7-native": {
                "label": "Pixel 7 (native camera)", "class": "modern phone",
                "os": "Android", "app": "native camera", "ua": "", "results": d}}}
    devs = {}
    for k, v in st.get("devices", {}).items():
        v.setdefault("label", k)
        v.setdefault("results", {})
        nid = k if re.fullmatch(r"[A-Za-z0-9_-]+", k or "") else slug(v["label"])
        base, i = nid, 2
        while nid in devs:
            nid = f"{base}-{i}"; i += 1
        devs[nid] = v
    st["devices"] = devs
    if st.get("active") not in devs:
        st["active"] = next(iter(devs), None)
    st.setdefault("sessions", {})
    st.setdefault("current_session", None)
    st.setdefault("run", None)
    return st

def save_state():
    json.dump(STATE, open(STATE_PATH, "w"), indent=1)

STATE = load_state()
META = {}

PROTOCOL = "v1"
_SESSION_FIELDS = ("lux", "distance_cm", "operator", "camera_app", "display", "deviations")


def current_session():
    sid = STATE.get("current_session")
    return STATE["sessions"].get(sid) if sid else None


def active():
    return STATE.get("active")

def results_of(did):
    d = STATE["devices"].get(did)
    return d["results"] if d else {}

def active_results():
    return results_of(active())


def resolve_device(headers, query):
    """(dev_id, set_cookie|None). Precedence: explicit ?dev= (a Mac-dashboard correction on
    the viewed device) then the sl_dev cookie (a phone identifying itself, minted on first scan)."""
    dev = query.get("dev", [None])[0]
    if dev and dev in STATE["devices"]:
        return dev, None
    m = re.search(r"sl_dev=([A-Za-z0-9]+)", headers.get("Cookie", "") or "")
    did = m.group(1) if m else uuid.uuid4().hex[:12]
    if did in STATE["devices"]:
        d = STATE["devices"][did]
        meta = device_meta(headers)  # upgrade the label once a real model arrives (e.g. via client hints)
        if meta["label"].split(" · ")[0] not in _GENERIC and meta["label"] != d.get("label"):
            d.update({k: meta[k] for k in ("label", "class", "os", "app", "ua")})
        return did, None
    STATE["devices"][did] = {**device_meta(headers), "results": {}}
    setck = None if m else f"sl_dev={did}; Max-Age=31536000; Path=/; SameSite=Lax"
    return did, setck


_OUT_RANK = {"failed": 0, "marginal": 1, "decoded": 2}
_PRED_RANK = {"fail": 0, "edge": 1, "pass": 2}


def status_of(cid, results):
    s = results.get(cid, {})
    for k in ("decoded", "marginal", "failed"):
        if s.get(k):
            return k
    return "pending"


def agrees(cid, results):
    st = status_of(cid, results)
    if st == "pending":
        return None
    return abs(_OUT_RANK[st] - _PRED_RANK[BY_ID[cid]["pred"]]) <= 1


def device_summary(did):
    res = results_of(did)
    attempted = sum(1 for c in CELLS if status_of(c["cid"], res) != "pending")
    ag = [agrees(c["cid"], res) for c in CELLS]
    pilot = sum(1 for c in CELLS
                if status_of(c["cid"], res) != "pending" and "sid" not in res.get(c["cid"], {}))
    return attempted, sum(1 for a in ag if a is True), sum(1 for a in ag if a is not None), pilot


# ---- HTML ----
# Shown ON THE DEVICE after a self-recorded scan. A clean scan lands here as `decoded`;
# if the phone struggled (only read after moving closer, several tries, or a long dwell)
# the scanner taps "it struggled" to downgrade the same cell to `marginal` in one tap,
# without needing to reach the Mac dashboard.
# Appended to the on-device confirmation page: passively posts what the browser knows
# (no permission prompts), plus a one-tap camera-capabilities probe (needs https, i.e.
# the tunnel; on plain-LAN http the button reports the failure and the passive part
# still works).
_PROBE_SCRIPT = """
<script>
(function(){
 function post(d){try{fetch('/probe',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify(d)})}catch(e){}}
 (async function(){
   var d={passive:{screen:[screen.width,screen.height],dpr:devicePixelRatio,
     cores:navigator.hardwareConcurrency||null,mem:navigator.deviceMemory||null,
     touch:navigator.maxTouchPoints||0,bd:'BarcodeDetector' in window,
     lang:(navigator.languages||[]).slice(0,2)}};
   try{if(navigator.userAgentData&&navigator.userAgentData.getHighEntropyValues){
     var h=await navigator.userAgentData.getHighEntropyValues(['model','platformVersion']);
     d.passive.model=h.model||'';d.passive.platform_version=h.platformVersion||'';}}catch(e){}
   post(d);
 })();
 window.sendCam=function(btn){
   btn.disabled=true;btn.textContent='asking for camera...';
   navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}}).then(function(s){
     var t=s.getVideoTracks()[0],c=t.getCapabilities?t.getCapabilities():{};
     post({camera:{label:t.label||'',zoom:c.zoom||null,torch:!!c.torch,
       focus:c.focusMode||null,width:c.width||null,height:c.height||null,fr:c.frameRate||null}});
     s.getTracks().forEach(function(x){x.stop()});
     btn.textContent='camera details sent';
   })['catch'](function(e){btn.textContent='camera probe failed ('+e.name+')';});
 };
})();
</script>
<div style='margin-top:1.2em'>
<a href='#' onclick="sendCam(this);return false" style="display:inline-block;padding:.5em 1em;
border-radius:8px;background:rgba(255,255,255,.2);color:#fff;text-decoration:none;font-size:14px">
Send this camera's details (zoom / torch / focus)</a>
<a href='/distance' style="display:inline-block;padding:.5em 1em;margin-left:.6em;
border-radius:8px;background:rgba(255,255,255,.2);color:#fff;text-decoration:none;font-size:14px">
Distance check</a></div>
"""


def _confirm_page(cid, did, marginal=False):
    res = results_of(did)
    label = STATE["devices"].get(did, {}).get("label", "this device")
    done = sum(1 for c in CELLS if status_of(c["cid"], res) != "pending")
    c = BY_ID[cid]
    sid = res.get(cid, {}).get("sid")
    sess = STATE["sessions"].get(sid) if sid else None
    sess_line = (f"session {sid} &middot; {sess.get('lux','?')} lx &middot; {sess.get('distance_cm','?')} cm"
                 if sess else "<b style='color:#ffe9a8'>PILOT: no session was set on the dashboard</b>")
    if marginal:
        bg, head, sub = "#d80", "MARGINAL", "recorded as a struggle (read only after extra effort)"
        struggle = ""
    else:
        bg, head, sub = "#0b7", "OK", "recorded as a clean scan"
        struggle = (f"<a href='/marginal/{cid}?d=1' style='display:inline-block;margin-top:1.2em;"
                    f"padding:.6em 1em;border-radius:8px;background:rgba(255,255,255,.2);color:#fff;"
                    f"text-decoration:none;font-size:16px'>It struggled &rarr; mark marginal</a>")
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{{font:600 20px/1.5 system-ui;margin:0;display:grid;place-items:center;min-height:100vh;
padding:1em;box-sizing:border-box;background:{bg};color:#fff;text-align:center}}
.k{{opacity:.85;font-weight:400;font-size:16px}}</style>
<div><div style="font-size:56px">{head}</div>
<div>{cid} &middot; {c['group']}</div>
<div class=k>detected as <b>{label}</b></div>
<div class=k>{sess_line}</div>
<div class=k>{sub}</div>
<div class=k>{c['why']}</div>{struggle}
<div class=k style="margin-top:1.2em">{done} of {len(CELLS)} attempted on this device. Scan the next code.</div></div>
""" + _PROBE_SCRIPT


def _matrix(view):
    if not STATE["devices"]:
        return ("<p style='color:#c33'>No devices yet. Scan a code with a phone and it appears "
                "here automatically, identified from its own request.</p>")
    rows = ["<tr><th>device</th><th>class</th><th>app</th><th>attempted</th><th>agree/scored</th></tr>"]
    for did, d in STATE["devices"].items():
        att, ag, sc, pil = device_summary(did)
        sel = "background:#eefaf5" if did == view else ""
        tag = " <span style='color:#c33'>pilot</span>" if att and pil == att else ""
        rows.append(f"<tr style='{sel}'><td><a href='/device/view/{did}'><b>{d.get('label','?')}</b></a></td>"
                    f"<td>{d.get('class','')}</td><td>{d.get('app','')}</td>"
                    f"<td>{att}/{len(CELLS)}{tag}</td><td>{ag}/{sc}</td></tr>")
    return ("<h3>Device matrix (auto-detected)</h3><table class=mx>" + "".join(rows) +
            "</table><p><a href='/export-all'>Export combined CSV (all devices)</a> &middot; "
            "<a href='/export-devices'>Device details (JSON)</a></p>")


_DASH_HEAD = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Scannability validation (auto-detected devices)</title>
<script>// live refresh, paused while the session form is being filled (a meta refresh
// would wipe half-typed lux values every 4 s)
setInterval(function(){var a=document.activeElement;
if(!a||(a.tagName!="INPUT"&&a.tagName!="TEXTAREA"&&a.tagName!="BUTTON"))location.reload()},4000)</script>
<style>body{font:15px/1.5 system-ui;max-width:860px;margin:2em auto;padding:0 1em}
table{border-collapse:collapse;width:100%}td,th{padding:6px 8px;border-bottom:1px solid #eee;text-align:left}
.g{background:#f4f4f4;font-weight:700;text-transform:capitalize}a{color:#06c;text-decoration:none}
.bar{background:#0b7;color:#fff;padding:1em;border-radius:8px;margin-bottom:1em}
.sess{background:#f4f8ff;border:1px solid #cdd9ee;border-radius:8px;padding:1em;margin-bottom:1em}
.sess label{display:inline-block;margin:.3em 1em .3em 0;font-size:13px}
.sess input{display:block;margin-top:.2em;padding:.4em;width:230px;font:inherit}
.sess button{padding:.5em 1em;margin-right:.6em;font:inherit}
table.mx td,table.mx th{font-size:13px}</style>"""


# The fixed-variable half of the capture protocol (DEVICE-MATRIX.md is canonical; this
# page is the reference card shown while scanning).
_PROTOCOL_ROWS = [
    ("Print target", "one physical sheet, printed at 100% (verify the 100 mm ruler), taped at a marked spot, never moved between devices"),
    ("Screen target", "the same Mac showing /sheet; brightness set once and recorded; True Tone + Night Shift off"),
    ("Distance", "25 cm, measured with a ruler + tape mark (not estimated), device square-on; same for screen, print and webcams"),
    ("Lighting", "no daylight (after dark or blinds closed), fixed room lighting, no lamp in frame, shadow off the sheet; 200-600 lx measured at the sheet, every session"),
    ("Camera app", "default camera app, settings reset; 1x, never pinch-zoom; flash + auto-flash off; no filters; scene optimiser / night mode at device default; record app + mode"),
    ("Focus", "autofocus left alone; one tap-to-focus only if AF never locks, logged as a deviation"),
    ("Operator", "the same person for every device"),
    ("Order", "the same fixed sheet order, one full pass per device"),
]

_PROTOCOL_WINDOWS = [
    ("scan", "reads within 10 s held steady at 25 cm"),
    ("marginal", "reads only with extra effort: closer than 25 cm, longer than 10 s, many retries, or a focus tap"),
    ("no-scan", "nothing within 30 s total, including one deliberate closer approach (~15 cm)"),
]


def _protocol_page():
    rows = "".join(f"<tr><td style='white-space:nowrap'><b>{k}</b></td><td>{v}</td></tr>" for k, v in _PROTOCOL_ROWS)
    wins = "".join(f"<tr><td style='white-space:nowrap'><b>{k}</b></td><td>{v}</td></tr>" for k, v in _PROTOCOL_WINDOWS)
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Capture protocol v1</title>
<style>body{{font:15px/1.5 system-ui;max-width:860px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:6px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}
h2{{margin-top:1.5em}}</style>
<h1>Standardised capture protocol (v1)</h1>
<p>Fixed for the whole matrix, never changed mid-run. What varies is the device, and
nothing else. The full runbook is <code>DEVICE-MATRIX.md</code>.</p>
<h2>Fixed variables</h2><table>{rows}</table>
<h2>Outcome windows</h2><table>{wins}</table>
<h2>Per-session record</h2>
<p>Start a session on the <a href="/">dashboard</a> before each device pass: lux at the sheet,
distance, operator, camera app + mode, deviations. Every scan is stamped with it;
scans with no session export as <b>pilot</b> and are excluded from the paper's matrix.</p>
<p>Distance: set the 25 cm mark once with the print sheet's own 100 mm ruler (or a tape),
device at the mark. The <a href='/distance'>distance check</a> page verifies the hold per
device (camera focus readout where the hardware reports it, else one-time calibrated
ruler capture).</p>"""


# On-device distance check. Two mechanisms, both stored per device via /probe:
# - focusDistance from the camera track (Android Chrome typically; reported by the AF
#   system, no calibration; quantised, so a CHECK not ground truth). Heuristic: values
#   > 1 read as diopters (1/v), <= 1 as metres (sane for 10-100 cm working range).
# - calibrated pinhole geometry: distance = f_px * target_cm / target_px_on_screen.
#   One-time calibration at the taped 25 cm mark against the printed 100 mm ruler gives
#   f_px per device; afterwards any capture of the ruler measures the distance.
# Needs https (the tunnel) for camera access; on plain LAN http the page says so.
_DISTANCE_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Distance check</title>
<style>body{font:15px/1.5 system-ui;max-width:640px;margin:0 auto;padding:1em;background:#111;color:#eee}
video,canvas{width:100%;border-radius:8px;background:#000}
#big{font:700 44px/1.2 system-ui;margin:.4em 0}
button{font:600 16px system-ui;padding:.7em 1.2em;margin:.3em .3em .3em 0;border:0;border-radius:8px}
.g{background:#0b7;color:#fff}.k{background:#444;color:#eee}.b{background:#06c;color:#fff}
.mut{color:#aaa;font-size:14px}.h{position:absolute;width:34px;height:34px;border:3px solid #0f8;
border-radius:50%;margin:-17px;touch-action:none}
#wrap{position:relative;display:none}
</style>
<h2>Distance check <span class=mut>(25 cm protocol)</span></h2>
<div id=big>&hellip;</div><div class=mut id=how>starting camera</div>
<video id=v playsinline muted autoplay></video>
<div id=wrap><canvas id=c></canvas><div class=h id=h1></div><div class=h id=h2></div></div>
<div id=fall style='display:none'>
<p>Tap <b>Capture</b> with the printed ruler in frame, then drag the two circles onto the
<b>0 and 100 marks</b> of the ruler (it spans exactly 100 mm), then calibrate (once,
while at the 25 cm mark) or measure.</p>
<button class=k id=snap>Capture frame</button>
<button class=g id=cal>Lock calibration (I am at the 25 cm mark)</button>
<button class=b id=measure>Measure my distance</button>
</div>
<div>
<button class=k id=retake style='display:none'>Retake</button>
<button class=g id=send style='display:none'>Save this reading to my device</button>
</div>
<p class=mut>Camera access needs the https tunnel URL. The focus readout appears
automatically where the device reports focus distance; otherwise use the capture path.
The saved reading lands in this device's details (devices.json).</p>
<script>
const RULE_CM = 10, MARK_CM = 25;
let stream=null, fPx=null, mode='none', last=null;
const $ = id => document.getElementById(id);
function post(d){fetch('/probe',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({distance_check:d})})}
function fmt(cm){last=cm;$('big').textContent = cm==null ? 'no reading' :
  cm.toFixed(1)+' cm' + (Math.abs(cm-MARK_CM)<1.5 ? ' \\u2713 at the mark' : ' \\u2192 move to '+MARK_CM)}
async function start(){
  try{
    stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment',width:{ideal:1280}}});
  }catch(e){ $('how').textContent='camera unavailable ('+e.name+')'; return; }
  $('v').srcObject = stream;
  const t = stream.getVideoTracks()[0];
  try{ await t.applyConstraints({advanced:[{focusMode:'continuous'}]}); }catch(e){}
  const has = t.getSettings && ('focusDistance' in t.getSettings());
  if (has){
    mode='focus'; $('fall').style.display='none';
    setInterval(()=>{
      if (mode !== 'focus') return;  // yield if the page ever switches to the manual path
      const v = (t.getSettings().focusDistance);
      if (v==null || v<=0) return;
      const m = v > 1 ? 1/v : v;          // diopters vs metres heuristic
      const cm = m*100;
      fmt(cm>=5 && cm<=200 ? cm : null);
      $('how').textContent='camera focus reports: '+v;
    }, 600);
  } else {
    mode='manual'; $('how').textContent='this device hides focus distance: use the capture path';
    $('fall').style.display='block';
  }
}
function capture(){
  const v=$('v'), c=$('c');
  if(!v.videoWidth){ $('how').textContent='camera warming up, try again in a second'; return; }
  c.width=v.videoWidth; c.height=v.videoHeight;
  c.getContext('2d').drawImage(v,0,0);
  v.style.display='none'; $('wrap').style.display='block'; $('retake').style.display='inline-block';
  const r=$('wrap').getBoundingClientRect(), s=c.width/r.width;
  let p=[{x:.3,y:.5},{x:.7,y:.5}];
  [['h1',0],['h2',1]].forEach(([id,i])=>{
    const el=$(id); el.style.left=(p[i].x*100)+'%'; el.style.top=(p[i].y*100)+'%';
    el.ondragstart=e=>e.preventDefault();
    el.onpointerdown=e=>{el.setPointerCapture(e.pointerId)};
    el.onpointermove=e=>{const br=$('wrap').getBoundingClientRect();
      el.style.left=Math.max(0,Math.min(100,(e.clientX-br.left)/br.width*100))+'%';
      el.style.top =Math.max(0,Math.min(100,(e.clientY-br.top )/br.height*100))+'%';};
  });
  $('cal').onclick=()=>{
    const px=handleSepPx(s); if(!px) return;
    fPx = px*MARK_CM/RULE_CM;
    $('how').textContent='calibrated (f='+Math.round(fPx)+' px). Capture again any time to measure.';
    $('send').style.display='inline-block'; fmt(MARK_CM);
  };
  $('measure').onclick=()=>{
    const px=handleSepPx(s); if(!px) return;
    if(!fPx){ $('how').textContent='calibrate once first (at the mark)'; return; }
    fmt(fPx*RULE_CM/px); $('send').style.display='inline-block';
  };
}
function handleSepPx(scale){
  // handle boxes are 34px + 2*3px border = 40px wide, so centre = offset + 20
  const a=$('h1').offsetLeft+20, b=$('h2').offsetLeft+20;
  const px=Math.abs(a-b)*scale;   // display px -> canvas px
  if(px<20){ $('how').textContent='handles too close: put them on the ruler ends'; return null }
  return px;
}
$('retake').onclick=()=>{ $('wrap').style.display='none'; $('v').style.display='block';
  $('retake').style.display='none'; $('send').style.display='none'; fmt(null); };
$('snap').onclick=capture;
$('send').onclick=()=>post({method:mode, cm:last, ts:new Date().toISOString()});
if(!window.isSecureContext){ $('how').textContent='not a secure context: open this page via the https tunnel URL'; }
start();
</script>"""


def _session_panel():
    sess = current_session()
    sid = STATE.get("current_session")
    if sess:
        lux = str(sess.get("lux", "")).strip()
        warn = "" if lux else " · <b style='color:#c33'>lux not recorded</b>"
        head = (f"<b>Active session {sid}</b> &middot; {lux or '?'} lx &middot; "
                f"{sess.get('distance_cm', '?')} cm &middot; {sess.get('operator', '?')} &middot; "
                f"{sess.get('camera_app', '?')}{warn}")
    else:
        head = "<b style='color:#c33'>No active session: scans record as PILOT</b> and are excluded from the paper's matrix."
    fields = [
        ("lux", "e.g. 380 (meter at the sheet)"),
        ("distance_cm", "25"),
        ("operator", "Sam"),
        ("camera_app", "stock camera, photo mode, 1x, flash off"),
        ("display", "MacBook /sheet, fixed brightness"),
        ("deviations", "e.g. one focus tap on f03"),
    ]
    inputs = []
    for k, ph in fields:
        v = (sess or {}).get(k, "")
        if k == "distance_cm" and not str(v).strip():
            v = "25"
        inputs.append(f"<label>{k.replace('_', ' ')}<input name='{k}' value=\"{v}\" placeholder='{ph}'></label>")
    update = (f"<button name='action' value='update'>Update active session</button>" if sess else "")
    return f"""<div class=sess>
<div style='margin-bottom:.4em'>{head} &nbsp;<a href='/protocol'>protocol v1</a></div>
<form method=post action='/session'>
<input type=hidden name=sid value="{sid or ''}">
{''.join(inputs)}
<div style='margin-top:.6em'><button name='action' value='new'>Start new session</button>{update}</div>
</form></div>"""


# ---- guided run: the Mac presents one code at a time; the server times presentation
# -> URL-open, so the 10 s / 30 s protocol windows are measured, not judged ----
def run_json():
    run = STATE.get("run")
    if not run:
        return {"run": None}
    c = CELLS[run["i"]]
    did = active()
    return {"run": run["rid"], "i": run["i"], "total": len(CELLS), "cid": c["cid"],
            "group": c["group"], "why": c["why"], "pred": c["pred"],
            "is_print": c["group"] == "print",
            # resolution/ec cells MUST display at true pixel size (same as /sheet):
            # they test px/module; every other cell displays at the sheet's fixed 190px
            "cls": "nat" if c["group"] in ("resolution", "ec-level") else "fix",
            "t_present": run["t_present"], "now": time.time(),
            "session": STATE.get("current_session"),
            "device": did, "device_label": STATE["devices"].get(did, {}).get("label", ""),
            "status": status_of(c["cid"], results_of(did)),
            "t_decode_s": results_of(did).get(c["cid"], {}).get("t_decode_s")}


_RUN_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Guided run</title>
<style>body{font:15px/1.5 system-ui;margin:0;padding:1.5em;background:#111;color:#eee;
display:flex;flex-direction:column;align-items:center;min-height:95vh}
#clock{font:700 64px/1 system-ui;margin:.3em 0}
#bar{width:420px;max-width:90%;height:10px;background:#333;border-radius:5px;overflow:hidden}
#fill{height:100%;width:0%;background:#0b7}
img{width:min(430px,60vmin);image-rendering:pixelated;background:#fff;margin:1em 0}
figcaption,.muted{color:#aaa;font-size:14px;text-align:center}
button{font:600 16px system-ui;padding:.7em 1.3em;margin:.4em;border:0;border-radius:8px;cursor:pointer}
.g{background:#0b7;color:#fff}.o{background:#d80;color:#fff}.r{background:#c33;color:#fff}.k{background:#444;color:#eee}
#rec{font:700 22px system-ui;color:#0b7;margin:.3em 0;min-height:1.4em}
.warn{color:#f5c}
</style>
<div id=body><h2>Guided run</h2><div class=muted id=head>starting...</div></div>
<script>
let lastKey = null, fired = false;
async function tick(){
  let s; try { s = await (await fetch('/run/json')).json(); } catch(e) { return void schedule(); }
  const b = document.getElementById('body');
  if (!s.run) {
    b.innerHTML = `<h2>Guided run</h2>
      <p class=muted>Presents each code in the fixed protocol order with a live clock.
      The server times presentation to scan, so the 10 s / 30 s windows are measured
      automatically. Start a session on the <a href='/' style='color:#8cf'>dashboard</a> first.</p>
      <a href='/run/start'><button class=g>Start run</button></a>
      <a href='/'><button class=k>Back to dashboard</button></a>`;
    return void schedule();
  }
  const key = s.run + ':' + s.i;
  if (key !== lastKey) { lastKey = key; fired = false; }
  const el = s.now - s.t_present;
  const shown = Math.min(el, 99).toFixed(0);
  const clockCol = el <= 10 ? '#eee' : el <= 30 ? '#f5c' : '#f77';
  const phase = el <= 10 ? 'scan window' : el <= 30 ? 'marginal if it needs you closer' : 'no-scan territory';
  const sizing = s.cls === 'nat' ? 'width:auto;height:auto' : 'width:190px';
  const img = s.is_print
    ? `<img src='/codes/${s.cid}.png' style='width:110px;opacity:.9'>
       <figcaption><b>find ${s.cid} on the printed sheet</b> and scan it at the 25 cm mark</figcaption>`
    : `<img src='/codes/${s.cid}.png' style='${sizing}'>
       <figcaption><b>${s.cid}</b> &middot; ${s.why}</figcaption>`;
  const dev = s.device ? `&middot; scanning as <b>${s.device_label || s.device}</b>` : '';
  const sessWarn = s.session ? '' :
    `<div class=warn style='margin:.4em 0'><b>NO ACTIVE SESSION: these scans record as PILOT.</b>
     <a href='/' style='color:#8cf'>Start one on the dashboard</a> first.</div>`;
  const rec = s.status === 'pending' ? '' :
    `<div id=rec>recorded: ${s.status}${s.t_decode_s != null ? ' in ' + s.t_decode_s + ' s' : ''}</div>`;
  const btns = !s.device
    ? '<span class=muted>no device yet: scan once first (marks need a device bucket)</span>'
    : s.status === 'pending'
    ? `<a href="/marginal/${s.cid}?dev=${s.device}"><button class=o>It struggled (marginal)</button></a>
       <a href="/fail/${s.cid}?dev=${s.device}"><button class=r>No-scan</button></a>`
    : `<a href='/run/next'><button class=g>Next code</button></a>`;
  b.innerHTML = `<h2>${s.i + 1} / ${s.total} &middot; ${s.group} ${dev}</h2>
    ${sessWarn}
    <div id=clock style='color:${clockCol}'>${shown}s</div>
    <div id=bar><div id=fill style='width:${Math.min(100, el / 30 * 100)}%'></div></div>
    <div class=muted>${phase}</div>${img}${rec}
    <div>${btns}<a href='/run/stop'><button class=k>Stop run</button></a></div>
    <div class=muted>25 cm mark (<a href='/distance' style='color:#8cf'>check it</a>) &middot; 1x &middot; no zoom &middot; flash off &middot; square-on</div>`;
  if (s.status === 'decoded' && !fired) {
    fired = true;  // one auto-advance per step, never two (a double /run/next skips a code)
    setTimeout(() => fetch('/run/next'), 2500);
  }
  schedule();
}
function schedule(){ setTimeout(tick, 500); }
tick();
</script>"""


def _dashboard():
    view = active()
    if not view:
        return f"""{_DASH_HEAD}
<div class=bar><b>Waiting for the first scan.</b><br>
<span style='font-weight:400;font-size:13px'>Start a session below, open the sheet on this Mac and scan
a code with a phone. Each device identifies itself and appears below automatically, no set-up needed.</span></div>
{_session_panel()}
<p><a href="/run"><b>Guided run</b></a> (paced + timed) &nbsp;·&nbsp; <a href="/sheet">Free-order code sheet</a></p>
{_matrix(view)}"""
    res = results_of(view)
    vlabel = STATE["devices"].get(view, {}).get("label", "?")
    groups = {}
    for c in CELLS:
        groups.setdefault(c["group"], []).append(c)
    done = sum(1 for c in CELLS if status_of(c["cid"], res) != "pending")
    ag = [agrees(c["cid"], res) for c in CELLS]
    agree_n = sum(1 for a in ag if a is True)
    scored = sum(1 for a in ag if a is not None)
    dq = f"?dev={view}"
    rows = []
    for g, cells in groups.items():
        rows.append(f"<tr><td colspan=5 class=g>{g}</td></tr>")
        for c in cells:
            cid = c["cid"]; st = status_of(cid, res); a = agrees(cid, res)
            color = {"decoded": "#0b7", "marginal": "#d80", "failed": "#c33", "pending": "#999"}[st]
            amark = {True: "✓", False: "✗", None: ""}[a]
            if st == "pending":
                btns = f"<a href='/marginal/{cid}{dq}'>marginal</a> · <a href='/fail/{cid}{dq}'>no-scan</a>"
            else:
                btns = f"<a href='/marginal/{cid}{dq}'>marginal</a> · <a href='/undo/{cid}{dq}'>undo</a>"
            rows.append(
                f"<tr><td><b>{cid}</b></td><td>{c['why']}</td>"
                f"<td style='color:{color}'><b>{st}</b></td>"
                f"<td>pred: {c['pred']} {amark}</td><td>{btns}</td></tr>")
    return f"""{_DASH_HEAD}
<div class=bar><b>Viewing: {vlabel}</b><br>
<span style='font-weight:400;font-size:13px'>Devices identify themselves when they scan.
Click any device in the matrix below to view it here.</span></div>
<div style='font-size:14px'><b>{done} / {len(CELLS)}</b> codes attempted on this device &nbsp;·&nbsp;
agrees with study on <b>{agree_n} / {scored}</b> scored.</div>
{_session_panel()}
<p><a href="/run"><b>Guided run</b></a> (paced + timed) &nbsp;·&nbsp;
<a href="/sheet">Free-order code sheet</a> &nbsp;·&nbsp;
<a href="/export">Export this device (CSV)</a> &nbsp;·&nbsp; <a href="/reset">Reset this device</a></p>
<table>{''.join(rows)}</table>
{_matrix(view)}
<p style="color:#666">Scan each code with a phone's camera; a good scan turns the row green
automatically and the phone can tag a struggle as marginal. Mark any code that will not scan
"no-scan" here. "pred" is what the study expects of a modern phone; a check means the device
agreed within one step.</p>"""


def _sheet():
    truesize = {"resolution", "ec-level"}
    items = []
    for c in CELLS:
        if c["group"] == "print":
            continue
        cid = c["cid"]
        cls = "nat" if c["group"] in truesize else "fix"
        items.append(
            f"<figure class='{cls}'><img src='/codes/{cid}.png' alt='{cid}'>"
            f"<figcaption><b>{cid}</b> · {c['group']}<br>{c['why']}</figcaption></figure>")
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Scan sheet</title><style>body{{font:14px/1.4 system-ui;margin:1.5em}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:1.5em;align-items:end}}
figure{{margin:0;text-align:center}}img{{image-rendering:pixelated;background:#fff;border:1px solid #ddd}}
figure.fix img{{width:190px;height:190px}}
figure.nat img{{width:auto;height:auto}}
figcaption{{font-size:12px;color:#333;margin-top:.4em}}</style>
<h2>Scan each code with a phone's camera, in any order</h2>
<p><b>Protocol v1 (fair cross-device test):</b> every device at the <b>measured 25 cm mark</b>,
square-on, <b>1x, no pinch-zoom, flash off</b>, default camera app. A code that reads within
<b>10 s</b> steady at 25 cm is a <b>scan</b>; a code that reads <b>only</b> after you move closer,
hold longer, or retry many times is a <b>marginal</b> (tap <b>&ldquo;it struggled&rdquo;</b> on the
confirmation screen); a code that will not read within 30 s at all is a <b>no-scan</b>.
Do not creep closer to chase a read: that is a marginal by definition, and the fixed
distance is what makes the cliffs comparable across devices. Full protocol:
<a href='/protocol'>protocol v1</a>; start a session on the <a href='/'>dashboard</a> before
each device pass.</p>
<p>The fixed-size codes test occlusion, contrast, polarity and module style. The small
<b>resolution</b> (f02..f10) and <b>ec-level</b> (elr/ehr) codes render at true pixel size to probe
the ~3 px/module cliff, so the standard distance matters most for those.</p>
<div class=grid>{''.join(items)}</div>"""


def _csv_rows(w, d):
    results = d.get("results", {})
    for c in CELLS:
        r = c["render"]; cid = c["cid"]
        sid = results.get(cid, {}).get("sid")
        sess = STATE["sessions"].get(sid, {}) if sid else {}
        st = status_of(cid, results)
        proto = (PROTOCOL if sid else "pilot") if st != "pending" else ""
        w.writerow([d.get("label", ""), d.get("class", ""), d.get("os", ""), d.get("app", ""),
                    cid, c["group"], r.get("ec", "H"), r.get("occ", 0),
                    r.get("contrast", ""), bool(r.get("inverted", False)),
                    r.get("style", "square"), r.get("module_px", 12), r.get("mm", ""),
                    META.get(cid, {}).get("version", ""), c["pred"],
                    st, {True: "yes", False: "no", None: ""}[agrees(cid, results)],
                    proto, sid or "",
                    sess.get("lux", ""), sess.get("distance_cm", ""),
                    sess.get("operator", ""), sess.get("camera_app", ""),
                    results.get(cid, {}).get("run", ""), results.get(cid, {}).get("t_decode_s", "")])

CSV_HEAD = ["device", "device_class", "os", "app", "cid", "group", "ec", "occ_pct", "contrast_ratio",
            "inverted", "style", "module_px", "module_mm", "version", "prediction_modern",
            "device_outcome", "agrees", "protocol", "session_id", "lux", "distance_cm",
            "operator", "camera_app", "run", "t_decode_s"]

def _csv(all_devices=False):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(CSV_HEAD)
    if all_devices:
        for d in STATE["devices"].values():
            _csv_rows(w, d)
    else:
        a = active()
        if a and a in STATE["devices"]:
            _csv_rows(w, STATE["devices"][a])
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # Ask Chromium to send the real device model on subsequent requests (frozen out of the UA);
    # no-store keeps the live dashboard/state fresh through the tunnel.
    def _send(self, body, ct="text/html; charset=utf-8", code=200, headers=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Accept-CH", "Sec-CH-UA-Model, Sec-CH-UA-Platform, Sec-CH-UA-Platform-Version")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _redirect(self, to="/", headers=None):
        h = {"Location": to}
        h.update(headers or {})
        self._send("", code=302, headers=h)

    def do_POST(self):
        if urlparse(self.path).path == "/probe":
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8", "replace") or "{}")
            except ValueError:
                return self._send("bad json", code=400)
            did, _ = resolve_device(self.headers, {})  # cookie identifies the device
            d = STATE["devices"].setdefault(did, {})
            if isinstance(data, dict) and data:
                d.setdefault("probe", {}).update(data)
                save_state()
            return self._send("ok", "text/plain")
        if urlparse(self.path).path == "/session":
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
            val = lambda k: (body.get(k, [""])[0] or "").strip()
            vals = {k: val(k) for k in _SESSION_FIELDS}
            if not vals.get("distance_cm"):
                vals["distance_cm"] = "25"
            sid = val("sid")
            if val("action") == "update" and sid in STATE["sessions"]:
                STATE["sessions"][sid].update(vals)
            else:
                sid = uuid.uuid4().hex[:6]
                STATE["sessions"][sid] = {**vals, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
            STATE["current_session"] = sid
            save_state()
            return self._redirect()
        return self._send("not found", code=404)

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        parts = path.strip("/").split("/")
        head = parts[0] if parts else ""
        if path == "/":
            return self._send(_dashboard())
        if path == "/sheet":
            return self._send(_sheet())
        if path == "/protocol":
            return self._send(_protocol_page())
        if path == "/distance":
            return self._send(_DISTANCE_PAGE)
        if path == "/run":
            return self._send(_RUN_PAGE)
        if path == "/run/json":
            return self._send(json.dumps(run_json()), "application/json")
        if path == "/run/start":
            STATE["run"] = {"rid": uuid.uuid4().hex[:6], "i": 0,
                            "cid": CELLS[0]["cid"], "t_present": time.time()}
            save_state()
            return self._redirect("/run")
        if path == "/run/next":
            run = STATE.get("run")
            if run and run["i"] + 1 < len(CELLS):
                run["i"] += 1
                run["cid"] = CELLS[run["i"]]["cid"]
                run["t_present"] = time.time()
            else:
                STATE["run"] = None  # finished the pass
            save_state()
            return self._redirect("/run")
        if path == "/run/stop":
            STATE["run"] = None
            save_state()
            return self._redirect("/")
        if path == "/export":
            return self._send(_csv(False), "text/csv",
                              headers={"Content-Disposition": f"attachment; filename={slug(active() or 'device')}.csv"})
        if path == "/export-all":
            return self._send(_csv(True), "text/csv",
                              headers={"Content-Disposition": "attachment; filename=device_matrix.csv"})
        if path == "/export-devices":
            payload = {did: {k: v.get(k) for k in ("label", "class", "os", "app", "ua", "probe")}
                       for did, v in STATE["devices"].items()}
            return self._send(json.dumps(payload, indent=1), "application/json",
                              headers={"Content-Disposition": "attachment; filename=devices.json"})
        if head == "device" and len(parts) == 3 and parts[1] == "view":
            if parts[2] in STATE["devices"]:
                STATE["active"] = parts[2]; save_state()
            return self._redirect()
        if path == "/reset":
            a = active()
            if a and a in STATE["devices"]:
                STATE["devices"][a]["results"] = {}; save_state()
            return self._redirect()
        if head == "codes" and len(parts) == 2:
            fp = os.path.join(CODES_DIR, os.path.basename(parts[1]))
            if os.path.exists(fp):
                return self._send(open(fp, "rb").read(), "image/png")
            return self._send("not found", code=404)
        if head in ("s", "fail", "undo", "marginal") and len(parts) == 2 and parts[1] in BY_ID:
            cid = parts[1]
            did, setck = resolve_device(self.headers, q)  # phone self-identifies (or ?dev= from the Mac)
            STATE["active"] = did                          # dashboard auto-follows the scanning device
            flag = {"s": "decoded", "fail": "failed", "marginal": "marginal"}.get(head)
            rec = {"decoded": False, "marginal": False, "failed": False,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if flag:
                rec[flag] = True
            sid = STATE.get("current_session")
            if sid and sid in STATE["sessions"]:
                rec["sid"] = sid
            run = STATE.get("run")
            if run and run.get("cid") == cid:  # guided run: measured presentation -> decode
                rec["run"] = run["rid"]
                rec["t_decode_s"] = round(time.time() - run["t_present"], 1)
            results_of(did)[cid] = rec
            save_state()
            extra = {"Set-Cookie": setck} if setck else None
            if head == "s":
                return self._send(_confirm_page(cid, did), headers=extra)
            # `?d=1` = tapped from the device confirm page (downgrade a scan to marginal);
            # show a device confirmation rather than redirecting the phone to the Mac dashboard.
            if head == "marginal" and q.get("d", [""])[0] == "1":
                return self._send(_confirm_page(cid, did, marginal=True), headers=extra)
            return self._redirect(headers=extra)
        return self._send("not found", code=404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    # For off-network device testing, front the server with a tunnel (e.g.
    # `cloudflared tunnel --url http://localhost:<port>`) and set PUBLIC_BASE_URL to the
    # printed https URL so it is baked into the QR codes. Without this the codes encode the
    # LAN IP, which an off-network phone cannot reach. The server still binds 0.0.0.0:<port>;
    # the tunnel forwards to it. Re-run with the override set so the codes re-render.
    public = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public:
        if not re.match(r"^https?://", public):
            sys.exit(f"PUBLIC_BASE_URL must start with http:// or https:// (got {public!r})")
        base, mode = public, "public tunnel URL"
    else:
        base, mode = f"http://{lan_ip()}:{port}", "LAN IP (same-Wi-Fi only)"
    global META
    META = build_assets(base)
    print(f"Rendered {len(CELLS)} codes into {CODES_DIR}")
    print(f"  Codes encode: {base}  ({mode})")
    print(f"\n  On this Mac, open the dashboard:   {base}/")
    print(f"  Display the codes to scan:         {base}/sheet")
    print(f"  Add a device on the dashboard, scan with it, then switch device and repeat.")
    if public:
        print(f"  Off-network scanning is live via the tunnel. /reset and /device/* are open, so")
        print(f"  treat this quick-tunnel session as ephemeral (stop it when the matrix is done).\n")
    else:
        print(f"  Devices must be on the same Wi-Fi. Off-network? Set PUBLIC_BASE_URL to a tunnel URL.")
        print(f"  Webcams: use webcam_test.py instead.\n")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    main()
