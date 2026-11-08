#!/usr/bin/env bash
# Render a demo hub and check the result with a real Caddy binary (with the Cloudflare module).
set -euo pipefail
CADDY=${1:?path to caddy}
REPO=$(cd "$(dirname "$0")/.." && pwd)
R=$(mktemp -d)
mkdir -p "$R"/etc/{wgctl,caddy,wireguard,nftables.d} "$R"/var/lib/wgctl "$R"/var/log "$R"/run
printf 'hdr\n' > "$R/dump"
export PATH="$REPO/tests/bin:$PATH" WGCTL_ROOT="$R" WGCTL_DRY=1 WGCTL_SRV_PUB=SRVPUB= WGCTL_DUMP="$R/dump" \
       WGCTL_NO_PROBE=1 WGCTL_SHARE="$REPO/share" WGCTL_CONFIG="$R/etc/wgctl/config.toml" HOME="$R"
w() { python3 -I "$REPO/src/wgctl" "$@"; }
w init --yes --domain example.org --public-ip 198.51.100.7 --language en --timezone UTC >/dev/null
w location add home --networks 192.168.1.0/24 >/dev/null
w site add nas http://192.168.1.10:5000 >/dev/null
w site add pve https://192.168.1.11:8006 >/dev/null
w add phone --sites nas,pve --admin >/dev/null
w panel on >/dev/null
CF_API_TOKEN=dummy "$CADDY" validate --adapter caddyfile --config "$R/etc/caddy/Caddyfile"
echo "Caddyfile OK"
