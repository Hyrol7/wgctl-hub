# Architecture and security model

## Goals

1. A key opens **only** the sites and services explicitly given to it.
2. No general access to home networks, no access to routers, no client-to-client traffic.
3. Client internet traffic never goes through the VPS.
4. Nothing at home is exposed to the internet; nothing on the hub is exposed except SSH, WireGuard and (optionally) public sites via Cloudflare.
5. Losing the panel password, a phone or a backup file must not give away the network.

## Layers

| Layer | Enforcement |
|---|---|
| Client config | `AllowedIPs = 10.77.0.1/32`: the device routes only the hub's address into the tunnel. |
| Hub WireGuard | Each client peer has `AllowedIPs = <its /32>`; spoofed sources are dropped by WireGuard. |
| Hub firewall (nftables) | Input policy `drop`; `forward` policy `drop` — the hub routes nothing between peers or to home networks. Clients may reach only TCP 80/443 on the hub and the TCP service ports allowed to them. |
| Caddy | Every site has an allow-list of client VPN addresses (`remote_ip`); other keys get a "no access" page. The panel host is allowed only for admin keys. On the VPN path `CF-Connecting-IP` and similar headers are removed, so a backend can trust them only from Cloudflare. |
| Location router | Accepts from the tunnel only `src 10.77.0.1` to listed LAN ports; router management from the tunnel is dropped. |
| TCP services | `systemd-socket-proxyd` per service, `DynamicUser`, sandboxed, plus an nftables rule per allowed key. |

The hub itself reaches home services only through Caddy (sites) or a TCP proxy (services), and only to addresses inside a location's networks or a key's address. Its own management ports, loopback (except chosen ports for sites on the VPS) and link-local/metadata addresses are refused as backends.

## The web panel (vpnadmin)

- Runs as an unprivileged user `vpnadmin`, listens on `127.0.0.1:8090`; Caddy exposes it only to admin keys over the tunnel.
- May only run `sudo -n /usr/local/sbin/wgctl …` (sudoers), always with `--option=value` arguments, so form text can never become an option.
- Login: password (scrypt) **and** TOTP; constant-time checks; 5 failures per address → 15-minute block; a TOTP code is accepted only once.
- Sensitive actions (download a config, show a QR, grant admin, revoke, publish a site, change notification recipients) need a **fresh code**; 5 wrong codes end the session.
- Sessions: HttpOnly `__Host-` cookie, SameSite=Strict, 30-minute idle timeout, at most 10 sessions; password change ends all sessions.
- CSRF token on every form plus an Origin/Sec-Fetch-Site check; strict CSP (no inline scripts), HSTS, COOP/CORP, `frame-ancestors 'none'`.
- Only the last `X-Forwarded-For` value is trusted, and only from Caddy on 127.0.0.1.
- Even a fully compromised panel stays limited: when `wgctl` runs through sudo from user `vpnadmin`, it accepts only the commands the panel uses. `init`, `backup restore/init/verify`, `tcp setup`, `location adopt`, `panel`, `cloudflare`, `render` and `geo update` work only from an SSH terminal.
- After 20 failed logins from all addresses within 15 minutes the login is closed for everyone for 15 minutes. Only admin keys reach the panel, so this mostly protects against a stolen key; if it ever locks you out, wait or restart `vpnadmin` over SSH.

## Monitoring

`wgctl monitor` (every minute) flags a key when it appears from a new country or a hosting/VPN provider, through Tor, with impossible travel speed, or with "double activity" (a copied config). Flags never block automatically; the admin decides (`trust` or `disable`). Geolocation uses local DB-IP Lite databases — no IP is sent to third parties.

## Secrets on the server

| File | Protection |
|---|---|
| `/etc/wireguard/wg0.conf`, `/etc/wgctl/` (client configs with private keys) | root only (600/700). Configs are kept so a lost QR can be shown again; `wgctl reissue` rotates a key. |
| `/etc/vpnadmin/auth.json` | user `vpnadmin`, 600; scrypt hash, TOTP secret, hashed backup codes. |
| `/etc/caddy/cloudflare.env` | root, 600; token limited to one zone's DNS. |
| Backups | age-encrypted to a public key; the secret key is not on the server. |

## Hardening checklist

- SSH with keys only (`PasswordAuthentication no`), ideally from a few addresses.
- `unattended-upgrades` on; reboot when the Server page asks.
- Keep the backup secret key and the TOTP secret in a password manager, not on the VPS.
- Grant sites per key; use `*` (all sites) only for your own devices.
- Check the Log page after a "suspected" notification; use **Block**, not **It's me**, if unsure.

## Reporting a vulnerability

See [SECURITY.md](../../SECURITY.md).
