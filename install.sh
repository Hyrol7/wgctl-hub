#!/usr/bin/env bash
# wgctl installer for Ubuntu 24.04+ / Debian 12+ (needs Python 3.11+).
#
#   sudo ./install.sh              first install: packages, files, firewall, services (asks before each step)
#   sudo ./install.sh --upgrade    replace wgctl/vpnadmin and the shared files only, keep all settings
#                                  (once installed, `sudo wgctl-update` downloads the latest release and does this)
#   sudo ./install.sh --yes        do not ask (for automation); the firewall is still checked with nft -c
#   sudo ./install.sh --domain=example.com   hub settings without questions (defaults for everything else)
#
# The script never removes your data. Files it replaces are copied to *.before-wgctl first.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
SBIN=/usr/local/sbin
SHARE=/usr/local/share/wgctl
YES=0
MODE=install
DOMAIN=""
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --domain=*) DOMAIN="${a#--domain=}" ;;
    --upgrade) MODE=upgrade ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { [ "$YES" = 1 ] && return 0; read -r -p "$1 [y/N] " r; [[ "$r" =~ ^[YyТт] ]]; }
keep() { if [ -e "$1" ] && [ ! -e "$1.before-wgctl" ]; then cp -a "$1" "$1.before-wgctl"; fi; }

[ "$(id -u)" = 0 ] || die "run as root: sudo $0"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die "Python 3.11+ is required (tomllib)"

install_files() {
  say "Installing wgctl and vpnadmin to $SBIN, shared files to $SHARE"
  install -m 0755 "$SRC/src/wgctl" "$SBIN/wgctl"
  install -m 0755 "$SRC/src/vpnadmin" "$SBIN/vpnadmin"
  install -m 0755 "$SRC/src/wgctl-update" "$SBIN/wgctl-update"
  rm -rf "$SHARE.new"
  mkdir -p "$SHARE.new"
  cp -r "$SRC/share/." "$SHARE.new/"
  find "$SHARE.new" -type d -exec chmod 0755 {} +
  find "$SHARE.new" -type f -exec chmod 0644 {} +
  rm -rf "$SHARE.old"
  [ -d "$SHARE" ] && mv "$SHARE" "$SHARE.old"
  mv "$SHARE.new" "$SHARE"
  rm -rf "$SHARE.old"
  for u in "$SRC"/systemd/*; do install -m 0644 "$u" /etc/systemd/system/; done
  # the panel (user vpnadmin) reads /etc/wgctl/config.toml; everything else in /etc/wgctl stays root-only (0600/0700)
  [ -d /etc/wgctl ] && chmod 0711 /etc/wgctl
  [ -f /etc/wgctl/config.toml ] && chmod 0644 /etc/wgctl/config.toml
  report_tz
}

# the daily report runs at 08:00 in the hub's time zone (from config.toml once it exists)
report_tz() {
  local tz
  tz=$(python3 -c 'import tomllib;print(tomllib.load(open("/etc/wgctl/config.toml","rb")).get("general",{}).get("timezone","UTC"))' 2>/dev/null || echo UTC)
  sed -i "s|^OnCalendar=\*-\*-\* 08:00:00.*|OnCalendar=*-*-* 08:00:00 $tz|" /etc/systemd/system/wgctl-report.timer
  systemctl daemon-reload
}

if [ "$MODE" = upgrade ]; then
  [ -f /etc/wgctl/config.toml ] || die "/etc/wgctl/config.toml not found; run without --upgrade first"
  install_files
  wgctl render
  systemctl restart vpnadmin 2>/dev/null || true
  say "Upgraded: $(grep -m1 "^VERSION" "$SBIN/wgctl")"
  exit 0
fi

# ---- 1. packages -----------------------------------------------------------
say "1/6 Packages: wireguard-tools nftables qrencode python3-maxminddb age curl, Caddy with the Cloudflare DNS plugin"
if ask "Install them with apt?"; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard-tools nftables qrencode python3-maxminddb age curl \
      debian-keyring debian-archive-keyring apt-transport-https gnupg
  if ! command -v caddy >/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update && apt-get install -y caddy
  fi
  if ! caddy list-modules 2>/dev/null | grep -q '^dns.providers.cloudflare'; then
    caddy add-package github.com/caddy-dns/cloudflare
  fi
fi

# ---- 2. files and users ------------------------------------------------------
install_files
id vpnadmin >/dev/null 2>&1 || useradd --system --home /nonexistent --shell /usr/sbin/nologin vpnadmin
install -d -m 0700 -o vpnadmin -g vpnadmin /etc/vpnadmin
install -d -m 0755 /var/lib/wgctl /etc/nftables.d
if id caddy >/dev/null 2>&1; then
  install -d -m 0750 -o caddy -g caddy /var/log/caddy     # Caddy writes the access log for the visit journal
else
  warn "user caddy not found: install Caddy, then: sudo install -d -m 0750 -o caddy -g caddy /var/log/caddy"
fi
install -m 0440 "$SRC/templates/sudoers-vpnadmin" /etc/sudoers.d/vpnadmin.new
visudo -cf /etc/sudoers.d/vpnadmin.new >/dev/null || { rm -f /etc/sudoers.d/vpnadmin.new; die "sudoers check failed"; }
mv /etc/sudoers.d/vpnadmin.new /etc/sudoers.d/vpnadmin
install -d /etc/systemd/system/caddy.service.d
install -m 0644 "$SRC/templates/caddy-cloudflare.conf" /etc/systemd/system/caddy.service.d/cloudflare.conf
[ -e /etc/caddy/cloudflare.env ] || install -m 0600 "$SRC/templates/cloudflare.env.example" /etc/caddy/cloudflare.env
systemctl daemon-reload

# ---- 3. hub settings ---------------------------------------------------------
say "2/6 Hub settings (/etc/wgctl/config.toml, WireGuard key)"
if [ -f /etc/wgctl/config.toml ]; then
  echo "Already configured, keeping it."
elif [ -n "$DOMAIN" ]; then
  wgctl init --yes --domain "$DOMAIN"
  report_tz
else
  wgctl init
  report_tz
fi
eval "$(python3 - <<'PY'
import ipaddress, tomllib
c = tomllib.load(open("/etc/wgctl/config.toml", "rb"))
n = c.get("network", {})
net = ipaddress.ip_network(n.get("subnet", "10.77.0.0/24"))
b = str(net.network_address).rsplit(".", 1)[0] + "."
print(f'IFACE={n.get("interface", "wg0")}')
print(f'WG_PORT={n.get("listen_port", 51820)}')
print(f'CLIENTS={b}{n.get("clients_from", 10)}-{b}{n.get("clients_to", 250)}')
print(f'LOCATIONS={b}{n.get("locations_from", 2)}-{b}{n.get("locations_to", 9)}')
PY
)"

# ---- 4. firewall -------------------------------------------------------------
say "3/6 Firewall (nftables)"
WAN=$( (ip -4 route show default || true) | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')
SSH_PORT=$( (sshd -T 2>/dev/null || true) | awk '$1=="port"{print $2; exit}')
SSH_PORT=${SSH_PORT:-22}
if grep -q 'wgctl_tcp' /etc/nftables.conf 2>/dev/null; then
  echo "/etc/nftables.conf already has the wgctl rules, keeping it."
else
  echo "Inbound will be allowed only for: SSH (tcp $SSH_PORT), WireGuard (udp $WG_PORT),"
  echo "HTTPS on $IFACE from $CLIENTS and $LOCATIONS, and HTTPS on $WAN from Cloudflare."
  echo "Everything else, including forwarding between clients, is dropped."
  if ask "Replace /etc/nftables.conf (a copy is kept as /etc/nftables.conf.before-wgctl)?"; then
    {
      echo "# Cloudflare IPv4 ranges (https://www.cloudflare.com/ips-v4) for public sites, written by install.sh"
      printf 'define CLOUDFLARE = { %s }\n' "$(curl -fsS https://www.cloudflare.com/ips-v4 | paste -sd, | sed 's/,/, /g')"
    } > /etc/nftables.d/cloudflare.nft.new
    grep -q '/' /etc/nftables.d/cloudflare.nft.new || die "could not download the Cloudflare ranges"
    mv /etc/nftables.d/cloudflare.nft.new /etc/nftables.d/cloudflare.nft
    [ -e /etc/nftables.d/wgctl-tcp.nft ] || install -m 0644 "$SRC/templates/wgctl-tcp.nft.empty" /etc/nftables.d/wgctl-tcp.nft
    sed -e "s|@WAN@|$WAN|g" -e "s|@CLIENTS@|$CLIENTS|g" -e "s|@LOCATIONS@|$LOCATIONS|g" \
        -e "s|@SSH_PORT@|$SSH_PORT|g" -e "s|@WG_PORT@|$WG_PORT|g" -e "s|@IFACE@|$IFACE|g" \
        "$SRC/templates/nftables.conf.in" > /etc/nftables.conf.new
    nft -c -f /etc/nftables.conf.new || die "nft rejected the new rules; nothing changed"
    keep /etc/nftables.conf
    mv /etc/nftables.conf.new /etc/nftables.conf
    systemctl enable --now nftables
    nft -f /etc/nftables.conf
    echo "Firewall applied. Check that a NEW SSH session still works before closing this one."
  fi
fi

# ---- 5. services -------------------------------------------------------------
say "4/6 WireGuard, Caddy and timers"
systemctl enable --now "wg-quick@$IFACE"
if grep -q '^CF_API_TOKEN=.\+' /etc/caddy/cloudflare.env; then
  wgctl render
  systemctl restart caddy
else
  warn "Put your Cloudflare API token into /etc/caddy/cloudflare.env, then run: sudo wgctl render && sudo systemctl restart caddy"
fi
systemctl enable --now wgctl-monitor.timer wgctl-geo.timer wgctl-report.timer
wgctl geo update || warn "geo databases not downloaded yet; the weekly timer will retry"

say "5/6 Web panel account"
if [ -s /etc/vpnadmin/auth.json ]; then
  echo "Account exists, keeping it."
elif ask "Create the panel account now (password + authenticator app)?"; then
  vpnadmin setup
fi
[ -s /etc/vpnadmin/auth.json ] && systemctl enable --now vpnadmin

say "6/6 Done"
cat <<EOF
Next steps:
  sudo wgctl location add home --networks 192.168.1.0/24     # router at home (see docs/en/locations.md)
  sudo wgctl site add nas http://192.168.1.10:5000            # nas.<your domain>, VPN only
  sudo wgctl add my-phone --sites nas --admin                 # first key; --admin opens the panel to it
  sudo wgctl panel on
  sudo wgctl backup init                                      # encrypted daily backups
Docs: $SRC/docs/en/  (Ukrainian: docs/uk/)
EOF
