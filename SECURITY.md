# Security policy

wgctl guards access to home networks, so security reports are welcome and handled first.

## Reporting

Please **do not open a public issue** for a vulnerability. Use GitHub's private reporting instead:
repository → **Security** → **Report a vulnerability**.

Include what you found, how to reproduce it and which version (`grep ^VERSION /usr/local/sbin/wgctl`). You will get an answer within a week; fixes are released as soon as they are ready and credited unless you prefer otherwise.

## Scope

In scope: `wgctl`, `vpnadmin`, `install.sh`, the generated Caddy/nftables/WireGuard/systemd configuration, and the documented router rules.

Out of scope: vulnerabilities in WireGuard, Caddy, signal-cli, the OS, or a misconfiguration that contradicts the documentation (for example a router that forwards everything from the tunnel).

## Supported versions

Only the latest release receives fixes. Upgrade with `git pull && sudo ./install.sh --upgrade`.
