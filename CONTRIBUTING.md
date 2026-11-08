# Contributing

Thank you for helping! Issues and pull requests are welcome in English or Ukrainian.

## Ground rules

- **Security first.** A change must not widen what a key can reach. New options default to the strict side.
- **No new runtime dependencies** unless unavoidable: both programs use only the Python 3.11+ standard library (plus optional `python3-maxminddb`).
- `wgctl` is the only thing that changes the system; `vpnadmin` only calls it.

## Development setup

```bash
pip install pytest pyflakes
python3 -m pytest -q tests        # a throw-away hub in a temp dir; no root, no WireGuard needed
pyflakes src/wgctl src/vpnadmin tools/*.py tests/*.py
shellcheck install.sh uninstall.sh src/wgctl-update
python3 tools/i18n.py check
```

The tests run `wgctl` with `WGCTL_ROOT` (all system paths under a temp dir) and `WGCTL_DRY` (no `wg`, `systemctl`, `nft`), and start `vpnadmin` on a free port. See `tests/conftest.py`.

## Texts and translations

User-facing strings are written in Ukrainian inside `T("...")` and translated through `share/i18n/<lang>.json`:

```python
die(T("Сайту {0} немає. Список: wgctl site list", name))
```

- Use positional placeholders `{0}`, `{1:.0f}`; double literal braces `{{ }}`.
- After adding or changing strings run `python3 tools/i18n.py extract` (adds new keys with empty values), translate them in `share/i18n/en.json`, then `python3 tools/i18n.py check`.
- **A new language:** copy `en.json` to `<code>.json`, translate the values and open a PR. Every `share/i18n/*.json` file shows up in the language list of the CLI and the panel automatically.

## Screenshots

`python3 tools/screenshots.py OUT_DIR [--dark] [--mobile] [--lang uk] [--empty] [page …]` starts a demo hub with sample data in a temp dir and saves PNGs of the panel (needs Playwright with Chromium). The images in `docs/img` are made with `--scale 1`.

## Releases

Bump `VERSION` in `src/wgctl` and `src/vpnadmin` (the same value), add a `## X.Y.Z` section to `CHANGELOG.md`, tag `vX.Y.Z` and publish a GitHub release: `sudo wgctl-update` installs the latest release and shows the changelog sections newer than the installed version.

## Pull requests

- One topic per PR, with a test for new behaviour or a fixed bug.
- Describe user-visible changes in `CHANGELOG.md`.
- CI must be green (lint, tests on Python 3.11–3.13, translations, Caddy config validation, shellcheck, nftables template, a real install on Ubuntu 24.04).
