#!/usr/bin/env bash
# wgctl uninstaller.
#
#   sudo ./uninstall.sh            stop and remove the programs, services, timers, sudoers rule and Caddy drop-in;
#                                  keep all data (keys, configs, backups, history) so a later install picks it up
#   sudo ./uninstall.sh --purge    also delete the data: /etc/wgctl, /etc/vpnadmin, /var/lib/wgctl, the WireGuard
#                                  interface config, the Caddy site config and the access log (asks to type "purge")
#
# The firewall and the main Caddyfile are put back from the *.before-wgctl copies if they exist (asks first).
# Packages (WireGuard, Caddy, nftables, age, signal-cli) are left installed.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
PURGE=0 YES=0
for a in "$@"; do
  case "$a" in
    --purge) PURGE=1 ;;
    --yes|-y) YES=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ask()  { [ "$YES" = 1 ] && return 0; read -r -p "$1 [y/N] " r; [[ "$r" =~ ^[YyТт] ]]; }
[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }

IFACE=wg0
if [ -f /etc/wgctl/config.toml ]; then
  IFACE=$(python3 -c 'import tomllib;print(tomllib.load(open("/etc/wgctl/config.toml","rb")).get("network",{}).get("interface","wg0"))' 2>/dev/null || echo wg0)
fi

if [ "$PURGE" = 1 ] && [ "$YES" = 0 ]; then
  echo "This deletes every key, site, location, backup and the panel account. It cannot be undone."
  read -r -p 'Type "purge" to continue: ' r
  [ "$r" = purge ] || { echo "Nothing changed."; exit 1; }
fi

say "Stopping services and timers"
units=$(systemctl list-units --all --plain --no-legend 'wgctl-*' 2>/dev/null | awk '{print $1}')
for u in vpnadmin.service wgctl-monitor.timer wgctl-geo.timer wgctl-report.timer wgctl-backup.timer $units; do
  systemctl disable --now "$u" 2>/dev/null || true
done
if [ "$PURGE" = 1 ]; then
  systemctl disable --now "wg-quick@$IFACE" 2>/dev/null || true
else
  echo "WireGuard ($IFACE) keeps running; stop it with: sudo systemctl disable --now wg-quick@$IFACE"
fi

say "Removing programs, units and the sudoers rule"
rm -f /usr/local/sbin/wgctl /usr/local/sbin/vpnadmin /usr/local/sbin/wgctl-update
rm -rf /usr/local/share/wgctl
rm -f /etc/systemd/system/vpnadmin.service /etc/systemd/system/wgctl-*.service /etc/systemd/system/wgctl-*.timer \
      /etc/systemd/system/wgctl-tcp@.socket /etc/systemd/system/wgctl-tcp@.service
rm -f /etc/sudoers.d/vpnadmin /etc/systemd/system/caddy.service.d/cloudflare.conf
rmdir /etc/systemd/system/caddy.service.d 2>/dev/null || true
systemctl daemon-reload

for f in /etc/nftables.conf /etc/caddy/Caddyfile; do
  if [ -e "$f.before-wgctl" ] && ask "Put back $f from $f.before-wgctl?"; then
    cp -a "$f.before-wgctl" "$f"
    [ "$f" = /etc/nftables.conf ] && nft -f /etc/nftables.conf
    [ "$f" = /etc/caddy/Caddyfile ] && { systemctl reload caddy 2>/dev/null || true; }
  fi
done
if grep -q 'wgctl' /etc/nftables.conf 2>/dev/null; then
  # the rules stay; only the per-key TCP service rules go (the include must keep a valid, empty chain)
  install -m 0644 "$SRC/templates/wgctl-tcp.nft.empty" /etc/nftables.d/wgctl-tcp.nft
  nft -f /etc/nftables.conf || true
  echo "/etc/nftables.conf still has the wgctl rules (SSH, WireGuard and HTTPS only). Edit it if you need other ports."
else
  rm -f /etc/nftables.d/wgctl-tcp.nft
fi

if [ "$PURGE" = 1 ]; then
  say "Deleting data"
  rm -rf /etc/wgctl /etc/vpnadmin /var/lib/wgctl /var/log/wgctl.log* /var/log/caddy/wgctl-access.log* \
         /etc/caddy/wgctl.caddy /etc/caddy/cloudflare.env "/etc/wireguard/$IFACE.conf"
  grep -q 'cloudflare.nft' /etc/nftables.conf 2>/dev/null || rm -f /etc/nftables.d/cloudflare.nft
  if id vpnadmin >/dev/null 2>&1; then userdel vpnadmin || true; fi
  if grep -q 'wgctl.caddy' /etc/caddy/Caddyfile 2>/dev/null; then
    echo "/etc/caddy/Caddyfile still imports wgctl.caddy: edit it, then: sudo systemctl restart caddy"
  else
    systemctl restart caddy 2>/dev/null || true
  fi
  echo "Done. Packages are still installed; remove them with apt if you no longer need them."
else
  say "Done"
  echo "Data is kept in /etc/wgctl, /etc/vpnadmin, /var/lib/wgctl and /etc/wireguard/$IFACE.conf."
  echo "Install again with install.sh to continue where you left off, or run: sudo ./uninstall.sh --purge"
fi
