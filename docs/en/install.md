# Installation

This guide sets up a hub on a fresh VPS. Allow about 20 minutes.

## 1. Before you start

You need:

| What | Why |
|---|---|
| VPS with a public IPv4, Ubuntu 24.04+ / Debian 12+ | the hub; Python 3.11+ is required |
| A domain on Cloudflare, e.g. `example.org` | site names `*.example.org`, certificates, optional public sites |
| SSH access as a user with sudo | everything is done over SSH |

Keep your current SSH session open while you install: the firewall step changes inbound rules, and you should confirm that a **new** SSH session still works before closing the old one.

## 2. Cloudflare

1. **DNS record for private sites.** In the Cloudflare dashboard → your domain → DNS, add
   `A  *  10.77.0.1`  with the cloud **grey (DNS only)**.
   Every `name.example.org` now resolves to the hub's VPN address, which is reachable only through the tunnel. (If you change the VPN subnet, use its `.1`.)
2. **API token.** My Profile → API Tokens → Create Token → "Edit zone DNS" template, limited to your domain (Zone · DNS · Edit and Zone · Zone · Read). Caddy uses it to get the wildcard certificate by DNS-01, and wgctl uses it to create records for public sites.
3. **Zone ID.** Domain → Overview → API → Zone ID (32 characters). Needed only for public sites: `sudo wgctl cloudflare --zone <Zone ID>`.

The token goes into `/etc/caddy/cloudflare.env` on the server (mode 600). Never paste it into chats or issues.

## 3. Run the installer

```bash
git clone https://github.com/Hyrol7/wgctl-hub.git
cd wgctl-hub
sudo ./install.sh
```

What it does, step by step (it asks before each one):

1. **Packages:** `wireguard-tools nftables qrencode python3-maxminddb age curl`, Caddy from the official repository plus the `caddy-dns/cloudflare` module (`caddy add-package`).
2. **Files:** `wgctl` and `vpnadmin` to `/usr/local/sbin`, shared files (styles, fonts, translations) to `/usr/local/share/wgctl`, systemd units, a system user `vpnadmin`, `/etc/sudoers.d/vpnadmin` (the panel may run only `wgctl`), a drop-in that gives Caddy the token file.
3. **Hub settings:** `wgctl init` asks for the domain, public IP, WireGuard port, VPN subnet, time zone, language and panel name; writes `/etc/wgctl/config.toml`, generates the server key in `/etc/wireguard/wg0.conf` and the main `/etc/caddy/Caddyfile`.
4. **Firewall:** writes `/etc/nftables.conf` from [templates/nftables.conf.in](../../templates/nftables.conf.in) — inbound SSH, WireGuard, HTTPS on `wg0` for clients and locations, HTTPS on the public interface from Cloudflare only; no forwarding. The previous file is kept as `/etc/nftables.conf.before-wgctl`. The rules are checked with `nft -c` before they are applied.
5. **Services:** `wg-quick@wg0`, Caddy (once the token is in place), timers `wgctl-monitor` (every minute), `wgctl-geo` (weekly), `wgctl-report` (08:00).
6. **Panel account:** `vpnadmin setup` — a password (12+ characters) and an authenticator app (TOTP); the panel asks only for the password and a code. Save the backup codes it prints.

If you skipped the token: put it into `/etc/caddy/cloudflare.env` as `CF_API_TOKEN=...`, then

```bash
sudo wgctl render && sudo systemctl restart caddy
```

## 4. First location, site and key

The easiest way is the panel: open it with an admin key and follow **First steps** on the overview page (add a location → add a site → issue a key). The same over SSH:

```bash
sudo wgctl location add home --title Home --networks 192.168.1.0/24
```

This prints ready terminal commands for MikroTik; `sudo wgctl location conf home --format openwrt` (or `wg` for a plain WireGuard file) gives the config for other routers. Name locations as you like (`home`, `office`, `dacha`, `parents`…); there can be up to 8 by default (`locations_from`/`locations_to`). Set up the router as described in [locations](locations.md), then:

```bash
sudo wgctl status                                     # "Location home  normal, handshake 12 s ago"
sudo wgctl site add nas http://192.168.1.10:5000
sudo wgctl add my-phone --sites nas --admin --qr      # scan in the WireGuard app
sudo wgctl panel on
```

Open `https://nas.example.org` on the phone with the tunnel on. The panel is at `https://vpnadmin.example.org`, only for keys with `--admin`.

## 5. Recommended next steps

```bash
sudo wgctl backup init        # encrypted daily backups; keep the printed secret key safe
sudo wgctl geo update         # country/provider checks for connections
```

Optional: [Signal notifications](signal.md), [TCP services](tcp-services.md), [public sites](usage.md#public-sites).

## Settings file

`/etc/wgctl/config.toml` (created by `wgctl init`):

```toml
[general]
language = "en"            # en | uk
timezone = "Europe/Kyiv"

[network]
domain = "example.org"
public_ip = "198.51.100.7"
endpoint_host = "198.51.100.7"   # what clients connect to (IP or DNS name)
listen_port = 51820
subnet = "10.77.0.0/24"          # .1 hub, locations from locations_from to locations_to, clients from clients_from to clients_to
locations_from = 2
locations_to = 9
clients_from = 10
clients_to = 250
interface = "wg0"
reserved_names = []              # names sites must not take (other DNS records)

[panel]
subdomain = "vpnadmin"
brand = "VPN hub"

[policy]
inactive_days = 60               # auto-revoke after this many days without connections
warn_days = 7
guest_max_hours = 72
rotate_days = 180                # key rotation reminder, 0 = off

[update]
repo = "Hyrol7/wgctl-hub"        # where sudo wgctl-update gets releases from
```

After editing: `sudo wgctl render && sudo systemctl restart vpnadmin`.

## Updating

```bash
sudo wgctl-update                # shows the changes, asks, makes an encrypted backup (if set up), installs, checks services
sudo wgctl-update --check        # only check (exit code 10 = an update is available)
sudo wgctl-update --to v1.0.0    # a specific release
sudo wgctl-update --rollback     # put back the programs from before the last update
```

Your settings, keys and data are never touched by an update. The Server page of the panel and the daily report say when a new release is out.

From a git checkout instead: `git pull && sudo ./install.sh --upgrade`.

### From 3.x (before the public release)

`sudo wgctl-update` is not on such a hub yet, so the first update goes through git:

```bash
sudo wgctl backup run                         # if backups are set up
git clone https://github.com/Hyrol7/wgctl-hub.git && cd wgctl-hub
sudo ./install.sh --upgrade
sudo wgctl location list                      # locations without a router key (old placeholders) are gone
sudo wgctl location adopt home                # a router set up by hand in wg0.conf: let wgctl manage it (keeps its keys)
```

Version numbers restart at 1.0.0, so `--check` on 3.x would wrongly say "up to date"; after this update it works normally.

## Removing

```bash
sudo ./uninstall.sh              # programs, services, sudoers rule; keeps /etc/wgctl, /etc/vpnadmin, /var/lib/wgctl
sudo ./uninstall.sh --purge      # also deletes all keys, sites, backups and the panel account (asks to type "purge")
```

It offers to put back `/etc/nftables.conf` and `/etc/caddy/Caddyfile` from their `*.before-wgctl` copies. Packages stay installed.
