# Locations: connecting your routers

A **location** is any router that keeps a WireGuard tunnel to the hub and lets the hub reach the services behind it: a home, an office, a summer house, your parents' flat. You name them yourself; nothing is predefined. By default up to 8 locations get addresses `.2`–`.9` of the VPN subnet (`locations_from`/`locations_to` in `config.toml`).

**In the panel:** Locations → *New location* (a name in Latin letters, a title, the networks behind the router, a code from the app). The location page then shows the router config as MikroTik commands, OpenWrt commands or a WireGuard file; afterwards it needs a code again, because it contains the router's private key.

**From SSH:**

```bash
sudo wgctl location add home --title Home --networks 192.168.1.0/24
```

The command prints ready RouterOS 7 commands for MikroTik and saves a standard WireGuard config (`/etc/wgctl/clients/location-home.conf`). For other routers:

```bash
sudo wgctl location conf home --format openwrt   # uci commands
sudo wgctl location conf home --format wg        # a WireGuard file for any router
```

The router always dials out to the hub (`persistent-keepalive`), so **no ports need to be open at home**. On the hub the location's peer gets `AllowedIPs = 10.77.0.2/32, 192.168.1.0/24`; on the router the hub's peer gets only `10.77.0.1/32`.

Networks must be private IPv4 ranges that do not overlap the VPN, another location or the VPS's own networks.

| Command | What it does |
|---|---|
| `wgctl location list` | all locations with their state |
| `wgctl location set home --networks 192.168.1.0/24,192.168.2.0/24 --title "Home" --note "…"` | change networks, title, note |
| `wgctl location set home --sites nas,photos` | sites the whole location network may open (see step 4 below) |
| `wgctl location set home --panel on` | the location network may open the panel |
| `wgctl location reissue home` | new router keys (the old config stops working) |
| `wgctl location rm home` | delete the location |
| `wgctl location adopt home` | a router added by hand to `wg0.conf` before wgctl managed locations: take it over (keys stay) |

## MikroTik (RouterOS 7)

Before any change: make a backup and turn on **Safe Mode** (Ctrl+X in the terminal, or the Safe Mode button in WinBox), so a mistake rolls back when the session drops.

```
/system backup save name=before-wgctl
```

### 1. Tunnel

Paste the three commands that `wgctl location add` printed (`/interface wireguard add …`, `/interface wireguard peers add …`, `/ip address add …`). Check:

```
/interface wireguard peers print detail
```

`last-handshake` should be a few seconds; on the hub `sudo wgctl status` shows `Location home  normal`.

### 2. Firewall: only the hub, only the ports you need

The tunnel must not give access to the router itself or to anything you did not choose. Add three rules and move them **above** the default `defconf` rules (right after "accept established,related"):

```
/ip firewall filter
add chain=input in-interface=wg-hub action=drop comment="wgctl: no router management from the tunnel"
add chain=forward in-interface=wg-hub src-address=10.77.0.1 dst-address=192.168.1.0/24 protocol=tcp dst-port=80,443,5000 action=accept comment="wgctl: hub to allowed services"
add chain=forward in-interface=wg-hub action=drop comment="wgctl: nothing else from the tunnel"
/ip firewall filter print
/ip firewall filter move [find comment~"wgctl"] destination=1
```

List in `dst-port` exactly the ports your sites and [TCP services](tcp-services.md) use (for example `80,443,5000,22,3389`). When you add a site on a new port, extend this rule.

Leave Safe Mode (Ctrl+X again) only after checking that WinBox/SSH to the router still works and a site opens through the VPN.

### 3. Optional: devices with their own firewall

Some services (Windows RDP, some NAS apps) accept only clients from the local network. Either allow `10.77.0.1` in that device's firewall, or let the router present the hub as a local address:

```
/ip firewall nat add chain=srcnat src-address=10.77.0.1 dst-address=192.168.1.0/24 action=masquerade comment="wgctl: hub as a LAN address"
```

### 4. Optional: open the sites from the home network without a key

Devices at home can reach `https://nas.example.org` through the router, which then appears to the hub as `10.77.0.2`:

```
/ip firewall nat add chain=srcnat dst-address=10.77.0.1 out-interface=wg-hub action=masquerade comment="wgctl: LAN to hub sites"
```

```bash
sudo wgctl location set home --sites nas,photos   # sites the whole home network may open (also on the location page)
sudo wgctl location set home --panel on           # only if the home network may open the panel too
```

## OpenWrt

Paste the output of `sudo wgctl location conf home --format openwrt` into an SSH session on the router (or take the commands from the location page in the panel). It creates interface `wghub` with the keys, the hub as the only peer and `allowed_ips = 10.77.0.1/32`. Then in LuCI → Network → Firewall create a zone `wghub` with input **reject**, forward **reject**, and a traffic rule: from zone `wghub`, source `10.77.0.1`, to `lan`, TCP, the ports you need → accept.

## Other routers (pfSense, Linux, …)

Import `sudo wgctl location conf home --format wg` as a WireGuard interface (it already contains the keys, `Endpoint`, `AllowedIPs = 10.77.0.1/32` and keepalive). Then apply the same policy as above:

- drop everything from the tunnel to the router itself (input);
- forward from the tunnel only `src 10.77.0.1` → your LAN, TCP, the needed ports;
- drop all other forwarded traffic from the tunnel.

For a Linux box with nftables:

```
table inet wgctl_location {
  chain input   { type filter hook input priority 0;   iifname "wg-hub" ct state established,related accept; iifname "wg-hub" drop; }
  chain forward { type filter hook forward priority 0; iifname "wg-hub" ct state established,related accept;
                  iifname "wg-hub" ip saddr 10.77.0.1 ip daddr 192.168.1.0/24 tcp dport { 80, 443, 5000 } accept;
                  iifname "wg-hub" drop; }
}
```

and enable forwarding (`net.ipv4.ip_forward=1`).

## Troubleshooting

| Symptom | Check |
|---|---|
| `Location home  no contact` | Router clock and DNS, `endpoint-address`/port, UDP 51820 allowed on the VPS (`sudo nft list ruleset`). |
| Handshake fine, site shows "Site temporarily unavailable" | The router forward rule (port list), the backend address, the device's own firewall (step 3). `curl -v http://192.168.1.10:5000` from the hub. |
| Site page says "This device has not been granted access" | Give the key the site: `sudo wgctl grant my-phone nas` or tick it in the panel. |
