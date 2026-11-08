# Backups

wgctl keeps an encrypted copy of everything needed to rebuild the hub: settings and keys (`/etc/wgctl`, `/etc/wireguard`, `/etc/caddy`, `/etc/vpnadmin`), the firewall, the systemd units, the programs, Signal data and the history database.

Backups are encrypted with [age](https://age-encryption.org) to a public key. **The secret key is shown once and is never stored on the server**, so a stolen server or backup file reveals nothing.

## Set up

```bash
sudo wgctl backup init
```

- prints `AGE-SECRET-KEY-…` — save it in a password manager now;
- writes the public key to `/etc/wgctl/backup-recipient.txt`;
- enables `wgctl-backup.timer` (daily at 03:40 in the hub's time zone).

## What happens daily

- a file `/var/backups/wgctl/wgctl-YYYYMMDD-HHMM.tar.gz.age` is created; the last 14 are kept;
- if Signal is set up, the file is sent to the admins when the configuration changed, and at least once a week;
- if there was no backup for 36 hours, the server page and a notification say so.

```bash
sudo wgctl backup run         # now
sudo wgctl backup status
sudo wgctl backup verify      # paste the secret key: checks that it really decrypts the latest copy
```

## Restore

On the same or a new server (install wgctl first with `./install.sh`, you may skip `wgctl init`):

```bash
sudo wgctl backup restore wgctl-20261029-0340.tar.gz.age            # preview: lists files, changes nothing
sudo wgctl backup restore wgctl-20261029-0340.tar.gz.age --apply    # writes the files; asks you to type "yes"
sudo wgctl render
sudo systemctl restart wg-quick@wg0 caddy vpnadmin
```

The current files are saved first. If the new server has a different public IP, update `public_ip`/`endpoint_host` in `/etc/wgctl/config.toml` — or better, use a DNS name as `endpoint_host` from the start, so clients never need new configs.

Restore asks for the secret key interactively; run it from an SSH terminal.
