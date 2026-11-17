#!/usr/bin/env bash
# Start the device-validation harness behind the named Cloudflare tunnel so devices
# on ANY network can scan it. Stable URL: https://scanlab.clinicalwebdesign.co.uk
# Tunnel = openqr-scanlab (id 630e7dcd-0ba3-4e32-9e58-df029010c179), config in
# ~/.cloudflared/openqr-scanlab.yml, ingress -> localhost:PORT.
set -euo pipefail
PORT=8009
HOST="https://scanlab.clinicalwebdesign.co.uk"
DIR="$(cd "$(dirname "$0")" && pwd)"
CF=/opt/homebrew/bin/cloudflared
PY="$DIR/../../.venv/bin/python"

# One cloudflared per tunnel (competing connectors cause flapping 404s), so replace any prior.
tmux kill-session -t scanlab-tunnel  2>/dev/null || true
tmux kill-session -t scanlab-harness 2>/dev/null || true

tmux new-session -d -s scanlab-tunnel  "$CF tunnel --config $HOME/.cloudflared/openqr-scanlab.yml run"
tmux new-session -d -s scanlab-harness "cd '$DIR' && PUBLIC_BASE_URL='$HOST' '$PY' phone_test.py $PORT"

echo "Tunnel + harness started in tmux (scanlab-tunnel, scanlab-harness)."
echo "  Dashboard: $HOST/"
echo "  Sheet:     $HOST/sheet"
echo "Codes bake $HOST, so any device on any network can scan them."
echo "Stop when done (closes the open /reset + /device/* endpoints):"
echo "  tmux kill-session -t scanlab-harness; tmux kill-session -t scanlab-tunnel"
