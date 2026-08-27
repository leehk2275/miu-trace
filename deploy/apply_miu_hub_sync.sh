#!/usr/bin/env bash
# Install the MIU Hub read-only source configuration and refreshed units.
set -euo pipefail

ENV_FILE=/etc/miu-trace.env
SOURCE=https://raw.githubusercontent.com/315seconds/miu-hub/main/receiving/js/supabase-client.js
KEY="$(curl -fsSL "$SOURCE" | sed -n 's/.*SUPABASE_ANON_KEY = "\([^"]*\)".*/\1/p')"

test -n "$KEY"
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
{ grep -v '^MIU_HUB_SUPABASE_' "$ENV_FILE" || true; printf 'MIU_HUB_SUPABASE_URL=https://yqnocnzjrcsrwrvsvsyg.supabase.co\nMIU_HUB_SUPABASE_ANON_KEY=%s\n' "$KEY"; } > "$temporary"
install -m 600 "$temporary" "$ENV_FILE"
install -m 644 deploy/miu-trace-beta.service /etc/systemd/system/miu-trace-beta.service
install -m 644 deploy/miu-trace-sync.service /etc/systemd/system/miu-trace-sync.service
install -m 644 deploy/miu-trace-sync.timer /etc/systemd/system/miu-trace-sync.timer
systemctl daemon-reload
systemctl enable --now miu-trace-sync.timer
