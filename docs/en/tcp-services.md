# TCP services: SSH, RDP, VNC and others

Not everything is a web site. A **TCP service** maps a port on the hub to a host:port behind a location, for chosen keys only:

```
laptop ──► 10.77.0.1:2201 ──(systemd-socket-proxyd)──► 192.168.1.20:22
```

## One-time setup

```bash
sudo wgctl tcp setup
```

It installs two systemd template units (`wgctl-tcp@.socket`, `wgctl-tcp@.service`) and makes sure `/etc/nftables.conf` jumps to the `wgctl_tcp` chain (the installer's firewall already does). Run it in an SSH terminal: it shows the changes and asks for confirmation.

The proxy runs as a throw-away `DynamicUser` with a strict sandbox, listens only on the hub's VPN address, and is reachable only from the keys you allow (an nftables rule per service).

## Adding a service

```bash
sudo wgctl tcp add nas-ssh 192.168.1.20:22          # gets the first free hub port from 2201
sudo wgctl tcp add laptop-rdp 192.168.1.30:3389 --port 2389
sudo wgctl tcp allow nas-ssh work-laptop
sudo wgctl tcp list
```

Then, from the allowed device with the tunnel on:

```bash
ssh -p 2201 user@nas-ssh.example.org        # the name resolves to 10.77.0.1 like any site
```

For RDP connect to `laptop-rdp.example.org:2389`.

Other commands: `wgctl tcp set NAME --target 192.168.1.21:22`, `wgctl tcp deny NAME KEY…`, `wgctl tcp rm NAME`. A disabled or revoked key loses access immediately.

## Router

The location's firewall must let the hub reach the target port (add `22`, `3389`, `5900`… to the forward rule from [locations](locations.md)). The target sees connections from `10.77.0.1` (or from the router's LAN address if you use the optional source NAT) — allow that in the device's own firewall, e.g. the Windows Remote Desktop rule.

## Limits

- Hub ports 2201–2999; targets must be inside a location's networks or on a device with a key.
- The hub's own ports (SSH, 80, 443, Caddy admin, the panel) can never be targets.
- Up to 32 simultaneous connections per service.
