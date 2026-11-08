# Встановлення

Інструкція для чистого VPS. Займе близько 20 хвилин.

## 1. Перед початком

Потрібно:

| Що | Навіщо |
|---|---|
| VPS із публічною IPv4, Ubuntu 24.04+ / Debian 12+ | хаб; потрібен Python 3.11+ |
| Домен у Cloudflare, напр. `example.org` | імена сайтів `*.example.org`, сертифікати, за бажання публічні сайти |
| Доступ SSH користувачем із sudo | усе робиться через SSH |

Не закривайте поточну SSH-сесію під час встановлення: крок із брандмауером змінює вхідні правила, і перед тим як закрити стару сесію, перевірте, що **нова** SSH-сесія відкривається.

## 2. Cloudflare

1. **Запис DNS для приватних сайтів.** Панель Cloudflare → ваш домен → DNS, додайте
   `A  *  10.77.0.1` із **сірою хмаркою (DNS only)**.
   Тепер кожне `ім'я.example.org` вказує на VPN-адресу хаба, яка досяжна лише через тунель. (Якщо змінюєте VPN-мережу, вкажіть її `.1`.)
2. **API-токен.** My Profile → API Tokens → Create Token → шаблон «Edit zone DNS», лише для вашого домену (Zone · DNS · Edit і Zone · Zone · Read). Caddy отримує ним сертифікат `*.домен` через DNS-01, а wgctl створює записи для публічних сайтів.
3. **Zone ID.** Домен → Overview → API → Zone ID (32 символи). Потрібен лише для публічних сайтів: `sudo wgctl cloudflare --zone <Zone ID>`.

Токен записується в `/etc/caddy/cloudflare.env` на сервері (права 600). Ніколи не вставляйте його в чати чи issues.

## 3. Запуск інсталятора

```bash
git clone https://github.com/Hyrol7/wgctl-hub.git
cd wgctl-hub
sudo ./install.sh
```

Що він робить (перед кожним кроком питає):

1. **Пакети:** `wireguard-tools nftables qrencode python3-maxminddb age curl`, Caddy з офіційного репозиторію і модуль `caddy-dns/cloudflare` (`caddy add-package`).
2. **Файли:** `wgctl` і `vpnadmin` у `/usr/local/sbin`, спільні файли (стилі, шрифти, переклади) у `/usr/local/share/wgctl`, служби systemd, системний користувач `vpnadmin`, `/etc/sudoers.d/vpnadmin` (панель може запускати лише `wgctl`), доповнення служби Caddy з файлом токена.
3. **Налаштування хаба:** `wgctl init` питає домен, публічну IP, порт WireGuard, VPN-мережу, часовий пояс, мову й назву панелі; записує `/etc/wgctl/config.toml`, створює ключ сервера в `/etc/wireguard/wg0.conf` і головний `/etc/caddy/Caddyfile`.
4. **Брандмауер:** записує `/etc/nftables.conf` із [templates/nftables.conf.in](../../templates/nftables.conf.in) — вхідні SSH, WireGuard, HTTPS на `wg0` для клієнтів і локацій, HTTPS на публічному інтерфейсі лише від Cloudflare; жодного пересилання. Попередній файл зберігається як `/etc/nftables.conf.before-wgctl`. Правила перевіряються `nft -c` перед застосуванням.
5. **Служби:** `wg-quick@wg0`, Caddy (коли токен на місці), таймери `wgctl-monitor` (щохвилини), `wgctl-geo` (щотижня), `wgctl-report` (08:00).
6. **Обліковий запис панелі:** `vpnadmin setup` — пароль (від 12 символів) і застосунок-автентифікатор (TOTP); панель питає лише пароль і код. Збережіть резервні коди, які він покаже.

Якщо токен пропустили: запишіть його в `/etc/caddy/cloudflare.env` як `CF_API_TOKEN=...`, потім

```bash
sudo wgctl render && sudo systemctl restart caddy
```

## 4. Перша локація, сайт і ключ

Найпростіше — через панель: відкрийте її з адмін-ключем і пройдіть **Перші кроки** на сторінці огляду (додати локацію → додати сайт → видати ключ). Те саме через SSH:

```bash
sudo wgctl location add home --title Дім --networks 192.168.1.0/24
```

Команда покаже готові команди терміналу для MikroTik; `sudo wgctl location conf home --format openwrt` (або `wg` для звичайного файлу WireGuard) дасть конфіг для інших роутерів. Називайте локації як хочете (`home`, `office`, `dacha`, `parents`…); типово їх може бути до 8 (`locations_from`/`locations_to`). Налаштуйте роутер за інструкцією [локації](locations.md), потім:

```bash
sudo wgctl status                                     # «Локація home  в нормі, handshake 12 с тому»
sudo wgctl site add nas http://192.168.1.10:5000
sudo wgctl add my-phone --sites nas --admin --qr      # відскануйте в застосунку WireGuard
sudo wgctl panel on
```

Відкрийте `https://nas.example.org` на телефоні з увімкненим тунелем. Панель — `https://vpnadmin.example.org`, лише для ключів із `--admin`.

## 5. Що зробити далі

```bash
sudo wgctl backup init        # щоденні зашифровані копії; збережіть показаний секретний ключ
sudo wgctl geo update         # перевірки країни й провайдера для підключень
```

За бажання: [сповіщення Signal](signal.md), [TCP-сервіси](tcp-services.md), [публічні сайти](usage.md#публічні-сайти).

## Файл налаштувань

`/etc/wgctl/config.toml` (створює `wgctl init`):

```toml
[general]
language = "uk"            # uk | en
timezone = "Europe/Kyiv"

[network]
domain = "example.org"
public_ip = "198.51.100.7"
endpoint_host = "198.51.100.7"   # куди підключаються клієнти (IP або DNS-ім'я)
listen_port = 51820
subnet = "10.77.0.0/24"          # .1 хаб, локації з locations_from по locations_to, клієнти з clients_from по clients_to
locations_from = 2
locations_to = 9
clients_from = 10
clients_to = 250
interface = "wg0"
reserved_names = []              # імена, яких не можна давати сайтам (інші записи DNS)

[panel]
subdomain = "vpnadmin"
brand = "VPN hub"

[policy]
inactive_days = 60               # автовідкликання після стількох днів без підключень
warn_days = 7
guest_max_hours = 72
rotate_days = 180                # нагадування змінити ключ, 0 = вимкнено

[update]
repo = "Hyrol7/wgctl-hub"        # звідки sudo wgctl-update бере релізи
```

Після змін: `sudo wgctl render && sudo systemctl restart vpnadmin`.

## Оновлення

```bash
sudo wgctl-update                # покаже зміни, спитає, зробить зашифровану копію (якщо налаштовано), встановить, перевірить служби
sudo wgctl-update --check        # лише перевірити (код виходу 10 = є оновлення)
sudo wgctl-update --to v1.0.0    # конкретний реліз
sudo wgctl-update --rollback     # повернути програми, що стояли до останнього оновлення
```

Налаштувань, ключів і даних оновлення не торкається. Про новий реліз скажуть сторінка «Сервер» у панелі та щоденний звіт.

Із git-копії замість цього: `git pull && sudo ./install.sh --upgrade`.

### З версій 3.x (до публічного релізу)

На такому хабі ще немає `sudo wgctl-update`, тож перше оновлення — через git:

```bash
sudo wgctl backup run                         # якщо копії налаштовано
git clone https://github.com/Hyrol7/wgctl-hub.git && cd wgctl-hub
sudo ./install.sh --upgrade
sudo wgctl location list                      # локацій без ключа роутера (старих заготовок) більше немає
sudo wgctl location adopt home                # роутер, налаштований вручну у wg0.conf: передати під керування wgctl (ключі не змінюються)
```

Нумерація версій починається знову з 1.0.0, тож `--check` на 3.x помилково скаже «актуальна»; після цього оновлення все працює як слід.

## Видалення

```bash
sudo ./uninstall.sh              # програми, служби, правило sudoers; лишає /etc/wgctl, /etc/vpnadmin, /var/lib/wgctl
sudo ./uninstall.sh --purge      # ще й видаляє всі ключі, сайти, копії й обліковий запис панелі (попросить ввести "purge")
```

Запропонує повернути `/etc/nftables.conf` і `/etc/caddy/Caddyfile` з копій `*.before-wgctl`. Пакети лишаються встановленими.
