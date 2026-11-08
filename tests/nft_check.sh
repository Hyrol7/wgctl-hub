#!/usr/bin/env bash
# The nftables template from install.sh must parse (run as root: nft -c needs CAP_NET_ADMIN even for a dry check).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d)
printf 'define CLOUDFLARE = { 173.245.48.0/20, 103.21.244.0/22 }\n' > "$T/cf.nft"
cp "$REPO/templates/wgctl-tcp.nft.empty" "$T/tcp.nft"
sed -e "s|@WAN@|eth0|g" -e "s|@CLIENTS@|10.77.0.10-10.77.0.250|g" -e "s|@LOCATIONS@|10.77.0.2-10.77.0.9|g" \
    -e "s|@SSH_PORT@|22|g" -e "s|@WG_PORT@|51820|g" -e "s|@IFACE@|wg0|g" \
    -e "s|/etc/nftables.d/cloudflare.nft|$T/cf.nft|" -e "s|/etc/nftables.d/wgctl-tcp.nft|$T/tcp.nft|" \
    "$REPO/templates/nftables.conf.in" > "$T/nftables.conf"
nft -c -f "$T/nftables.conf"
echo "nftables template OK"
