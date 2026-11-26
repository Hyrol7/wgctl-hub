# Changelog

## Unreleased

- SSH to servers for admins: `wgctl set KEY --ssh on|off|PORT` on a key with the server role creates the TCP service `KEY-ssh` to the device's own address, open to every key with the admin role (computed from roles, so new admins get in and former ones lose access at once). Removed when the key leaves the server role or is revoked; follows `move` and `rename`. Nothing is forwarded between keys. In the panel: an "SSH for admins" switch (with the port) on the page of a server key.
- TCP services: `--admins on|off` on `wgctl tcp add/set` opens a service to all admin keys. The panel shows admin keys as always allowed on such services.

## 1.1.0

- Key roles: `admin` (panel, SSH, may have all sites), `server` (hosts sites, no auto-revoke) and `client` (explicit sites only, guests). Each role has its own address range, by default `.10–.19`, `.20–.50` and `.51–.250` (`[roles]` in `config.toml`); new keys get an address from their range. `wgctl add/set --role`; `--admin` is the admin role. `*` (all sites) is now for admin keys only. Existing keys get a role automatically.
- `wgctl move NAME [--ip N]`: a new address in the role's range; sites and TCP services hosted on the device follow it.
- `wgctl rename NAME NEW`: keys, address and config stay; history and TCP permissions follow the new name.
- Key names may contain `_` (`macbook_m2`); site and location names stay DNS labels.
- Panel: role on key cards and in Overview filters, a role choice when issuing a key, a "Role and name" section on the key page (change role, move, rename), role-coloured device rings and a legend on the map.
- `wgctl ssh`: SSH to the hub follows panel access. `sudo wgctl ssh setup` replaces the world-open SSH rule in `/etc/nftables.conf` (or a hand-written one) with the chain `wgctl_ssh`, which wgctl keeps equal to the panel list (admin keys, locations with `--panel on`) plus `wgctl ssh allow` extras. Refuses to cut off the current session or leave nobody allowed; `wgctl ssh off` reverts.

## 1.0.1

- Panel login asks only for the password and a code (there is one account anyway).
- Keys with "all sites" (and locations with "all sites") can now lose a single site: untick them on the site page, or `wgctl deny KEY SITE`. New sites still reach them automatically; `grant` gives the site back. Public sites stay open to everyone.
- Overview map: sites hosted on the VPS itself have their own "This VPS" planet; device labels no longer overlap site labels.

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
