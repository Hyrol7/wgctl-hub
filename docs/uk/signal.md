# Сповіщення в Signal

wgctl надсилає сповіщення через [signal-cli](https://github.com/AsamK/signal-cli) з окремого номера (*відправника*). Без нього все працює; повідомлення чекають у черзі 24 години, потім відкидаються.

Що надсилається:

| Кому | Що |
|---|---|
| у груповий чат | усе: інформація 🔑, попередження ⚠️, критичне 🚨, щоденний звіт 📊 о 08:00 |
| адмінам приватно | критичне, що потребує негайної уваги (дублюється в групу), зміни складу адміністраторів, резервні копії 💾 |
| усе адмінам приватно | поки групу не задано |
| кожному користувачу (за бажання, `--users on`) | про його ключ: термін дії, попередження про автовідкликання, незвичне місце, перевидання |
| (за бажання, `--connect on`) | кожне підключення й відключення |

## 1. Встановлення signal-cli

Дотримуйтесь [інструкції signal-cli](https://github.com/AsamK/signal-cli#installation) (нативна збірка для Linux не потребує Java). Покладіть програму в `/usr/local/bin/signal-cli` і створіть системного користувача для її даних:

```bash
sudo useradd --system --home /var/lib/signal-cli --shell /usr/sbin/nologin signal
sudo install -d -m 0700 -o signal -g signal /var/lib/signal-cli
```

## 2. Реєстрація номера-відправника

Візьміть номер, який може отримати SMS чи дзвінок і **не** використовується в іншому застосунку Signal. Отримайте captcha на <https://signalcaptchas.org/registration/generate.html>, потім:

```bash
sudo -u signal signal-cli --config /var/lib/signal-cli -a +380500001111 register --captcha 'signalcaptcha://…'
sudo -u signal signal-cli --config /var/lib/signal-cli -a +380500001111 verify 123-456
```

## 3. Підключення до wgctl

```bash
sudo wgctl notify set --sender +380500001111 --admins +380671234567,+380501234567
sudo wgctl notify create-group "VPN"       # група з адмінами для загальних сповіщень
sudo wgctl notify test
sudo wgctl notify show
```

Параметри: `--connect on|off`, `--report on|off`, `--users on|off`. Ті самі налаштування є на сторінці «Налаштування» панелі (зміна адмінів чи групи потребує коду з застосунку).

Номер для особистих повідомлень користувачу ключа: `sudo wgctl set iphone-olena --phone +380671234567`.

## Якщо щось не працює

- `wgctl notify show` показує чергу й останню помилку.
- `wgctl notify flush` надсилає чергу зараз; `wgctl notify clear` очищає її.
- Якщо Signal просить нову captcha (обмеження частоти), повторіть реєстрацію з новим токеном.
