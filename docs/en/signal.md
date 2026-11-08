# Signal notifications

wgctl sends notifications through [signal-cli](https://github.com/AsamK/signal-cli) from a dedicated phone number (the *sender*). Without it everything works; messages wait in a queue for 24 hours and then are dropped.

What is sent:

| To | What |
|---|---|
| the group chat | everything: info 🔑, warnings ⚠️, critical 🚨, the daily report 📊 at 08:00 |
| admins privately | critical events that need attention right away (also posted to the group), changes of the admin list, backups 💾 |
| everything to admins privately | while no group is set |
| each user (optional, `--users on`) | their own key: expiry, auto-revoke warning, unusual place, reissue |
| (optional, `--connect on`) | every connect/disconnect |

## 1. Install signal-cli

Follow the [signal-cli installation guide](https://github.com/AsamK/signal-cli#installation) (the native Linux build needs no Java). Put the binary at `/usr/local/bin/signal-cli` and create a system user that owns its data:

```bash
sudo useradd --system --home /var/lib/signal-cli --shell /usr/sbin/nologin signal
sudo install -d -m 0700 -o signal -g signal /var/lib/signal-cli
```

## 2. Register the sender number

Use a number that can receive an SMS or call and is **not** used with another Signal app. Get a captcha token at <https://signalcaptchas.org/registration/generate.html>, then:

```bash
sudo -u signal signal-cli --config /var/lib/signal-cli -a +15550001111 register --captcha 'signalcaptcha://…'
sudo -u signal signal-cli --config /var/lib/signal-cli -a +15550001111 verify 123-456
```

## 3. Connect it to wgctl

```bash
sudo wgctl notify set --sender +15550001111 --admins +15551234567,+15557654321
sudo wgctl notify create-group "VPN"       # a group with the admins, used for general notifications
sudo wgctl notify test
sudo wgctl notify show
```

Options: `--connect on|off`, `--report on|off`, `--users on|off`. The same settings are on the panel's Settings page (changing admins or the group needs a code from the app).

A key's phone number for personal messages: `sudo wgctl set iphone-olena --phone +15551234567`.

## Troubleshooting

- `wgctl notify show` displays the queue and the last error.
- `wgctl notify flush` sends the queue now; `wgctl notify clear` drops it.
- If Signal asks for a new captcha (rate limits), repeat registration with a fresh token.
