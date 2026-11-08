# Локації: підключення ваших роутерів

**Локація** — будь-який роутер, який тримає тунель WireGuard до хаба і дає хабу дістатися сервісів за ним: дім, офіс, дача, квартира батьків. Назви ви даєте самі, нічого не задано наперед. Типово до 8 локацій отримують адреси `.2`–`.9` VPN-мережі (`locations_from`/`locations_to` у `config.toml`).

**У панелі:** Локації → *Нова локація* (ім'я латиницею, назва, мережі за роутером, код із застосунку). На сторінці локації далі є конфіг роутера: команди MikroTik, команди OpenWrt або файл WireGuard; пізніше для нього знову потрібен код, бо в ньому приватний ключ роутера.

**Через SSH:**

```bash
sudo wgctl location add home --title Дім --networks 192.168.1.0/24
```

Команда покаже готові команди RouterOS 7 для MikroTik і збереже стандартний конфіг WireGuard (`/etc/wgctl/clients/location-home.conf`). Для інших роутерів:

```bash
sudo wgctl location conf home --format openwrt   # команди uci
sudo wgctl location conf home --format wg        # файл WireGuard для будь-якого роутера
```

Роутер завжди сам підключається до хаба (`persistent-keepalive`), тому **вдома не треба відкривати портів**. На хабі пір локації має `AllowedIPs = 10.77.0.2/32, 192.168.1.0/24`; на роутері пір хаба — лише `10.77.0.1/32`.

Мережі — лише приватні діапазони IPv4, що не перетинаються з VPN, іншою локацією чи власними мережами VPS.

| Команда | Що робить |
|---|---|
| `wgctl location list` | усі локації та їхній стан |
| `wgctl location set home --networks 192.168.1.0/24,192.168.2.0/24 --title "Дім" --note "…"` | змінити мережі, назву, примітку |
| `wgctl location set home --sites nas,photos` | сайти, які може відкривати вся мережа локації (див. крок 4 нижче) |
| `wgctl location set home --panel on` | мережі локації можна відкривати панель |
| `wgctl location reissue home` | нові ключі роутера (старий конфіг перестає працювати) |
| `wgctl location rm home` | видалити локацію |
| `wgctl location adopt home` | роутер, доданий вручну у `wg0.conf` до того, як wgctl почав керувати локаціями: взяти під керування (ключі не змінюються) |

## MikroTik (RouterOS 7)

Перед будь-якими змінами: зробіть резервну копію і ввімкніть **Safe Mode** (Ctrl+X у терміналі або кнопка Safe Mode у WinBox) — якщо помилитесь і сесія обірветься, зміни відкотяться.

```
/system backup save name=before-wgctl
```

### 1. Тунель

Вставте три команди, які показав `wgctl location add` (`/interface wireguard add …`, `/interface wireguard peers add …`, `/ip address add …`). Перевірка:

```
/interface wireguard peers print detail
```

`last-handshake` має бути кілька секунд; на хабі `sudo wgctl status` покаже `Локація home  в нормі`.

### 2. Брандмауер: лише хаб і лише потрібні порти

Тунель не повинен давати доступу ні до самого роутера, ні до того, що ви не вибрали. Додайте три правила і перемістіть їх **вище** стандартних правил `defconf` (одразу після «accept established,related»):

```
/ip firewall filter
add chain=input in-interface=wg-hub action=drop comment="wgctl: no router management from the tunnel"
add chain=forward in-interface=wg-hub src-address=10.77.0.1 dst-address=192.168.1.0/24 protocol=tcp dst-port=80,443,5000 action=accept comment="wgctl: hub to allowed services"
add chain=forward in-interface=wg-hub action=drop comment="wgctl: nothing else from the tunnel"
/ip firewall filter print
/ip firewall filter move [find comment~"wgctl"] destination=1
```

У `dst-port` перелічіть саме ті порти, які використовують ваші сайти й [TCP-сервіси](tcp-services.md) (напр. `80,443,5000,22,3389`). Коли додаєте сайт на новому порту, доповніть це правило.

Виходьте з Safe Mode (ще раз Ctrl+X) лише після того, як перевірили, що WinBox/SSH до роутера працює, а сайт відкривається через VPN.

### 3. За потреби: пристрої з власним брандмауером

Деякі сервіси (Віддалений робочий стіл Windows, частина застосунків NAS) приймають лише клієнтів із локальної мережі. Або дозвольте `10.77.0.1` у брандмауері пристрою, або нехай роутер подає хаб як локальну адресу:

```
/ip firewall nat add chain=srcnat src-address=10.77.0.1 dst-address=192.168.1.0/24 action=masquerade comment="wgctl: hub as a LAN address"
```

### 4. За потреби: відкривати сайти з домашньої мережі без ключа

Пристрої вдома можуть відкривати `https://nas.example.org` через роутер; для хаба вони тоді виглядають як `10.77.0.2`:

```
/ip firewall nat add chain=srcnat dst-address=10.77.0.1 out-interface=wg-hub action=masquerade comment="wgctl: LAN to hub sites"
```

```bash
sudo wgctl location set home --sites nas,photos   # сайти, які може відкривати вся домашня мережа (і на сторінці локації)
sudo wgctl location set home --panel on           # лише якщо домашній мережі можна й панель
```

## OpenWrt

Вставте вивід `sudo wgctl location conf home --format openwrt` у сесію SSH на роутері (або візьміть команди зі сторінки локації в панелі). Він створить інтерфейс `wghub` із ключами, хабом як єдиним піром і `allowed_ips = 10.77.0.1/32`. Потім у LuCI → Network → Firewall створіть зону `wghub` з input **reject**, forward **reject** і правило трафіку: із зони `wghub`, джерело `10.77.0.1`, до `lan`, TCP, потрібні порти → accept.

## Інші роутери (pfSense, Linux, …)

Імпортуйте `sudo wgctl location conf home --format wg` як інтерфейс WireGuard (у ньому вже є ключі, `Endpoint`, `AllowedIPs = 10.77.0.1/32` і keepalive). Потім застосуйте ту саму політику:

- усе з тунелю до самого роутера — відкидати (input);
- пересилати з тунелю лише `src 10.77.0.1` → ваша LAN, TCP, потрібні порти;
- решту пересилання з тунелю — відкидати.

Для Linux із nftables:

```
table inet wgctl_location {
  chain input   { type filter hook input priority 0;   iifname "wg-hub" ct state established,related accept; iifname "wg-hub" drop; }
  chain forward { type filter hook forward priority 0; iifname "wg-hub" ct state established,related accept;
                  iifname "wg-hub" ip saddr 10.77.0.1 ip daddr 192.168.1.0/24 tcp dport { 80, 443, 5000 } accept;
                  iifname "wg-hub" drop; }
}
```

і ввімкніть пересилання (`net.ipv4.ip_forward=1`).

## Якщо щось не працює

| Ознака | Що перевірити |
|---|---|
| `Локація home  немає зв'язку` | Годинник і DNS роутера, `endpoint-address`/порт, чи дозволено UDP 51820 на VPS (`sudo nft list ruleset`). |
| Зв'язок є, але сайт показує «Сайт тимчасово недоступний» | Правило forward на роутері (перелік портів), адреса бекенда, власний брандмауер пристрою (крок 3). `curl -v http://192.168.1.10:5000` із хаба. |
| Сайт пише «Цьому пристрою не надано доступу» | Дайте ключу сайт: `sudo wgctl grant my-phone nas` або позначте в панелі. |
