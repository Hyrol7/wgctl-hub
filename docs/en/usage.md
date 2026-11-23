# Everyday use

Everything can be done in the panel (`https://vpnadmin.<domain>`, admin keys only) or with `sudo wgctl …` over SSH. The panel calls the same commands.

## Keys

A key is one WireGuard config for one device. Names: lowercase Latin letters, digits, hyphens and `_`, up to 31 characters (`iphone-olena`, `macbook_m2`).

**Roles.** Every key has a role, and the role decides its address:

| Role | Addresses (default) | For |
|---|---|---|
| `admin` | `.10–.19` | your own devices: the panel, SSH to the VPS (`wgctl ssh`), may have `*` (all sites) |
| `server` | `.20–.50` | a device that hosts sites; no auto-revoke |
| `client` | `.51–.250` | a person or someone else's computer, guests; an explicit site list only |

The `[roles]` section of `config.toml` sets the ranges (`admin = "10-19"` and so on). A new key gets the first free address of its range. The panel shows the role on the key card, in the Overview filters and as the ring colour on the map. Keys created before roles get one automatically: admin if they had panel access, server if a site or TCP service lives on them, client otherwise.

```bash
sudo wgctl add iphone-olena --sites nas,photos --phone +15551234567 --qr
sudo wgctl add macbook_m2 --admin --sites '*'     # admin: all sites, including future ones
sudo wgctl add pi-bot --role server              # server: address from .20–.50
sudo wgctl add anna --hours 4 --sites photos     # guest key, revoked automatically in 4 h
sudo wgctl list                                  # --all also shows revoked keys
sudo wgctl show iphone-olena
```

| Command | What it does |
|---|---|
| `wgctl conf NAME` / `wgctl qr NAME` | print the saved config / QR again |
| `wgctl grant NAME site…` / `wgctl deny NAME site…` | add or remove sites; for a key with `*` (all sites) `deny` closes just that site, new sites still come automatically |
| `wgctl set NAME --sites nas,photos` | replace the site list (`*` = all, `none`) |
| `wgctl set NAME --expires 2026-12-31` | expiry date; the key is disabled after it |
| `wgctl extend NAME` | restart the 60-day inactivity countdown; for a guest: `--hours 2` |
| `wgctl disable NAME` / `enable` | temporarily off; the device sees an "Access disabled" page |
| `wgctl reissue NAME` | new keys; the old config stops working (key rotation) |
| `wgctl revoke NAME` | permanently remove the key |
| `wgctl set NAME --admin on` | the key may open the panel (permanent keys only); the same as the admin role |
| `wgctl set NAME --role server` | change the role (the address stays; if the key has `*`, add `--sites …`) |
| `wgctl move NAME [--ip N]` | a new address in the role's range; sites and TCP services on the device move along. The device needs the new `Address` line in its config |
| `wgctl rename NAME NEW` | rename; keys, address and config stay, nothing changes on the device |

**Auto-revoke.** A key that has not connected for 60 days (`policy.inactive_days`) is revoked; the user and admins get a warning 7 days before. Turn it off per key with `--no-autorevoke` or `--autorevoke off`.

**Key rotation.** After `rotate_days` (default 180) the panel marks the key "time to rotate the key" and a reminder is sent. Change the period: `sudo wgctl config --rotate-days 90` (0 = off).

## Sites

```bash
sudo wgctl site add nas http://192.168.1.10:5000
sudo wgctl site add pve https://192.168.1.11:8006 --insecure        # self-signed backend certificate
sudo wgctl site add ha http://192.168.1.12:8123 --upstream-host     # backend expects its own Host header
sudo wgctl site list
sudo wgctl site set nas --backend http://192.168.1.10:5001
sudo wgctl site rm nas
```

The site is `https://nas.<domain>`. A backend is always an IPv4 address (no host names, so DNS tricks cannot point a site somewhere else): inside a location's networks, a device with a key, or the VPS itself (`http://127.0.0.1:3000`). Sites on the VPS itself need no location: on the overview map they sit on their own "This VPS" planet. On the VPS only ports from 1024 are allowed, except Caddy's admin API (2019), the panel (8090) and the TCP service ports (2201–2999).

A key without access to a site sees a friendly "no access" page; a site whose backend is down shows "Site temporarily unavailable".

### Public sites

A site can also be published to the internet through Cloudflare (proxied, so the VPS address stays behind Cloudflare and only Cloudflare can reach port 443):

```bash
sudo wgctl cloudflare --zone <Zone ID>
sudo wgctl site set blog --public on        # creates a proxied DNS record name.<domain> -> VPS
sudo wgctl site set blog --public off       # removes it; VPN only again
```

To keep secrets in URLs (webhook paths, tokens in the query) out of `/var/log/caddy/wgctl-access.log` (works for VPN-only and public sites): `sudo wgctl site set blog --log hide-path` logs only the first path segment (`/hook/[hidden]`); `--log off` stops logging the site. `--log-skip /s,/health` skips only these paths (Caddy path patterns, `/static/*` works too; `none` clears). Headers `Authorization` and `Cookie` are never written to the log.

Everyone on the internet can open a public site, so publish only what is meant to be public and protected by its own login.

## Monitoring and security signals

`wgctl-monitor.timer` runs `wgctl monitor` every minute. It records connections and traffic, checks sites and services, and raises events:

- a key connects from a **new country** or a hosting/VPN provider, through **Tor**, or with an **impossible travel** speed between two places — the key is marked *suspected*;
- **double activity** (the same key switching addresses back and forth — the config is probably copied);
- a location is offline for more than 10 minutes, a backend or TCP service stops answering;
- expiry, auto-revoke and guest-time warnings; certificate expiry; disk, updates, backups.

`wgctl trust NAME` ("it's me") trusts the current country/provider and clears the flag; `wgctl disable NAME --reason suspicious` blocks it.

## Log, visits and charts

```bash
sudo wgctl log -n 50 --cat security
sudo wgctl visits --days 7               # requests per site and key, daily totals (from Caddy's access log)
sudo wgctl history on:iphone-olena,up:nas --range 7d
sudo wgctl server                        # disk, memory, updates, services, certificate, backups
sudo wgctl status
```

The panel shows the same data with charts on the key, site, location and server pages. History is kept for 90 days.
