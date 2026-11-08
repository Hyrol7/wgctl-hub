# Changelog

## 1.0.0 — first public release

A WireGuard + Caddy hub that gives each device access to chosen services behind your routers, without opening ports at home.

Access

- Keys: one WireGuard config per device with its own list of sites (`*` = all), guest keys for a few hours, expiry dates, auto-revoke after 60 days without connections, key rotation reminders, admin keys that may open the panel.
- Sites by name (`nas.example.org`) with a wildcard certificate via Cloudflare DNS; a per-site allow-list of VPN addresses. Backends only by IPv4 address: in a location's network, on a device with a key, or on the VPS itself.
- Public sites through Cloudflare (proxied, port 443 open to Cloudflare only); per-site access log modes `full | hide-path | off` and `--log-skip`.
- TCP services (SSH, RDP, …) through the hub with `systemd-socket-proxyd`, per key.

Locations

- Your own list of locations (any router with WireGuard), managed from the CLI and the **Locations** page of the panel.
- Router configs as MikroTik commands, OpenWrt `uci` commands or a WireGuard file; new router keys; sites for the whole location network; `location adopt` for routers set up by hand.
- Location networks must be private IPv4 ranges that overlap neither the VPN, another location nor the VPS's own networks.

Panel (`vpnadmin`)

- One account: password + TOTP, backup codes; a fresh code for sensitive actions; strict CSP, CSRF, `__Host-` cookies.
- Overview with an orbital network map and **First steps** for a new hub; key, site, location, log, server and settings pages with charts.
- English and Ukrainian, switchable on the Settings page.
- The panel user can run only the `wgctl` commands the panel needs (enforced by `wgctl` itself).

Monitoring and notifications

- New country or provider, Tor, impossible travel, double activity (a copied config); flags never block automatically.
- Signal: the group gets info and warnings, admins also get critical events privately; emoji, event time, links to the panel; daily report.
- VPS health: disk, memory, updates, reboot, services, certificate, backups; visit journal from Caddy's access log; 90 days of history.

Operations

- `install.sh` (asks before each step, `--domain=` for unattended setup), `uninstall.sh` (keeps data unless `--purge`).
- `sudo wgctl-update`: shows the changes, backs up, installs the latest GitHub release, checks the services; `--check`, `--to`, `--rollback`. The Server page and the daily report say when a release is out.
- Encrypted daily backups with age; restore only of known paths, with owners.

Upgrading from the private 3.x versions: see [docs/en/install.md](docs/en/install.md#from-3x-before-the-public-release).
