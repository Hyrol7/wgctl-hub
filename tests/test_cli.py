"""wgctl command line: setup, keys, sites, locations, TCP services; both languages."""
import json
import re

import pytest


def test_init_writes_config_and_wireguard(hub):
    cfg = hub.read("/etc/wgctl/config.toml")
    assert f'language = "{hub.lang}"' in cfg
    assert 'domain = "example.org"' in cfg
    wg = hub.read("/etc/wireguard/wg0.conf")
    assert "Address = 10.77.0.1/24" in wg and "PrivateKey = " in wg
    assert hub.state()["clients"] == {}
    # init refuses to overwrite
    r = hub.run("init", "--yes", "--domain", "x.org", "--public-ip", "1.2.3.4", ok=False)
    assert r.returncode != 0


def test_messages_follow_language(hub):
    out = hub.run("list").stdout
    if hub.lang == "en":
        assert "No clients" in out and not re.search("[а-яіїє]", out, re.I)
    else:
        assert "Клієнтів немає" in out


def test_add_client_with_site_and_render(hub):
    hub.run("location", "add", "home", "--networks", "192.168.1.0/24")
    hub.run("site", "add", "nas", "http://192.168.1.10:5000")
    hub.run("add", "phone", "--sites", "nas")
    st = hub.state()
    assert st["clients"]["phone"]["ip"] == "10.77.0.10"
    conf = hub.read("/etc/wgctl/clients/phone.conf")
    assert "AllowedIPs = 10.77.0.1/32" in conf, "clients must reach only the hub, not the home network"
    assert "Endpoint = 198.51.100.7:51820" in conf
    caddy = hub.read("/etc/caddy/wgctl.caddy")
    assert "@site_nas host nas.example.org" in caddy
    assert re.search(r"@allow_nas remote_ip 10\.77\.0\.10\b", caddy)
    wg = hub.read("/etc/wireguard/wg0.conf")
    assert "AllowedIPs = 10.77.0.2/32, 192.168.1.0/24" in wg or "192.168.1.0/24" in wg


def test_site_access_is_explicit(hub_en):
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    hub_en.run("site", "add", "nas", "http://192.168.1.10:5000")
    hub_en.run("add", "tablet")
    caddy = hub_en.read("/etc/caddy/wgctl.caddy")
    assert "10.77.0.10" not in caddy, "a new key gets no sites by default"
    hub_en.run("grant", "tablet", "nas")
    assert "10.77.0.10" in hub_en.read("/etc/caddy/wgctl.caddy")
    hub_en.run("deny", "tablet", "nas")
    assert "10.77.0.10" not in hub_en.read("/etc/caddy/wgctl.caddy")


@pytest.mark.parametrize("name", ["-x", "x-", "a" * 32, "ph one", "a_b", "a.b"])
def test_bad_names_rejected(hub_en, name):
    assert hub_en.run("add", name, ok=False).returncode != 0


def test_uppercase_is_normalised(hub_en):
    hub_en.run("add", "Phone")
    assert "phone" in hub_en.state()["clients"]


@pytest.mark.parametrize("name", ["vpnadmin", "www"])
def test_reserved_site_names(hub_en, name):
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    assert hub_en.run("site", "add", name, "http://192.168.1.10:80", ok=False).returncode != 0


@pytest.mark.parametrize("backend", [
    "http://198.51.100.7:22", "http://10.77.0.1:8090", "http://127.0.0.1:2019",
    "http://169.254.169.254:80", "ftp://192.168.1.10", "http://192.168.1.10:99999",
])
def test_dangerous_backends_rejected(hub_en, backend):
    r = hub_en.run("site", "add", "bad", backend, ok=False)
    assert r.returncode != 0, backend


def test_guest_key_expires(hub_en):
    hub_en.run("add", "guest", "--hours", "2")
    c = hub_en.state()["clients"]["guest"]
    assert c["guest_until"] > 0 and c["status"] == "active"
    r = hub_en.run("add", "guest2", "--hours", "100", ok=False)
    assert r.returncode != 0
    r = hub_en.run("add", "guest3", "--hours", "2", "--admin", ok=False)
    assert r.returncode != 0, "guest keys never get the panel"


def test_revoke_removes_peer(hub_en):
    hub_en.run("add", "old")
    pub = hub_en.state()["clients"]["old"]["pubkey"]
    assert pub in hub_en.read("/etc/wireguard/wg0.conf")
    hub_en.run("revoke", "old", "--yes")
    assert pub not in hub_en.read("/etc/wireguard/wg0.conf")
    assert hub_en.state()["clients"]["old"]["status"] == "revoked"


def test_location_router_config(hub_en):
    out = hub_en.run("location", "add", "office", "--title", "Office", "--networks", "10.20.0.0/24").stdout
    assert "/interface wireguard add" in out
    conf = hub_en.read("/etc/wgctl/clients/location-office.conf")
    assert "AllowedIPs = 10.77.0.1/32" in conf
    r = hub_en.run("location", "add", "bad", "--networks", "10.77.0.0/24", ok=False)
    assert r.returncode != 0, "a location network must not overlap the VPN"


def test_tcp_service_rules(hub_en):
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    hub_en.run("add", "laptop")
    hub_en.run("tcp", "add", "nas-ssh", "192.168.1.10:22")
    hub_en.run("tcp", "allow", "nas-ssh", "laptop")
    svc = hub_en.state()["services"]["nas-ssh"]
    assert svc["port"] == 2201 and svc["allow"] == ["laptop"]
    r = hub_en.run("tcp", "add", "evil", "198.51.100.7:22", ok=False)
    assert r.returncode != 0


def test_json_list(hub_en):
    hub_en.run("add", "a1")
    rows = json.loads(hub_en.run("list", "--json").stdout)
    assert rows[0]["name"] == "a1"


def test_public_site_log_modes(hub_en):
    hub_en.run("site", "add", "hook", "http://127.0.0.1:8787")
    hub_en.run("site", "add", "other", "http://127.0.0.1:8788")
    hub_en.run("cloudflare", "--zone", "0123456789abcdef0123456789abcdef")
    env_fake = dict(hub_en.env, WGCTL_CF_FAKE="1")
    import subprocess
    import sys
    from conftest import WGCTL
    for name in ("hook", "other"):
        subprocess.run([sys.executable, "-I", str(WGCTL), "site", "set", name, "--public", "on"], env=env_fake, check=True,
                       capture_output=True)

    def block(name):
        caddy = hub_en.read("/etc/caddy/wgctl.caddy")
        return caddy.split(f"{name}.example.org {{", 1)[1].split("\n}", 1)[0]

    assert "format json" in block("hook") and "regexp" not in block("hook")
    hub_en.run("site", "set", "hook", "--log", "hide-path")
    assert 'request>uri regexp "^(/[^/?]*)[/?].*$" "$1/[hidden]"' in block("hook")
    assert "format json" in block("other") and "regexp" not in block("other"), "other sites keep the full log"
    hub_en.run("site", "set", "hook", "--log", "off")
    assert "log {" not in block("hook") and "log {" in block("other")
    assert hub_en.run("site", "set", "hook", "--log", "maybe", ok=False).returncode != 0


def test_public_site_log_skip(hub_en):
    import subprocess
    import sys
    from conftest import WGCTL
    hub_en.run("site", "add", "hook", "http://127.0.0.1:8787")
    hub_en.run("site", "add", "other", "http://127.0.0.1:8788")
    hub_en.run("cloudflare", "--zone", "0123456789abcdef0123456789abcdef")
    for name in ("hook", "other"):
        subprocess.run([sys.executable, "-I", str(WGCTL), "site", "set", name, "--public", "on"],
                       env=dict(hub_en.env, WGCTL_CF_FAKE="1"), check=True, capture_output=True)

    def block(name):
        return hub_en.read("/etc/caddy/wgctl.caddy").split(f"{name}.example.org {{", 1)[1].split("\n}", 1)[0]

    hub_en.run("site", "set", "hook", "--log-skip", "/s,/health", "--log-skip", "/static/*", "--log", "hide-path")
    assert "@nolog path /s /health /static/*" in block("hook") and "log_skip @nolog" in block("hook")
    assert "regexp" in block("hook"), "hide-path keeps working"
    assert "@nolog" not in block("other")
    for bad in ("s", "/a b", "/x{y}", '/"q"'):
        assert hub_en.run("site", "set", "hook", f"--log-skip={bad}", ok=False).returncode != 0, bad
    hub_en.run("site", "set", "hook", "--log-skip", "none")
    assert "@nolog" not in block("hook")


def test_vpn_site_log_and_cf_headers(hub_en):
    hub_en.run("site", "add", "vpnhook", "http://127.0.0.1:8791")
    hub_en.run("site", "add", "plain", "http://127.0.0.1:8792")
    hub_en.run("add", "laptop", "--sites", "*")
    caddy = hub_en.read("/etc/caddy/wgctl.caddy")
    assert "log_name" not in caddy, "without hide-path sites the config stays as before"
    assert "header_up -Cf-Connecting-Ip" in caddy and "header_up -True-Client-Ip" in caddy
    hub_en.run("site", "set", "vpnhook", "--log", "hide-path", "--log-skip", "/s,/health")
    hub_en.run("site", "set", "plain", "--log", "off")
    caddy = hub_en.read("/etc/caddy/wgctl.caddy")
    wild = caddy.split("*.example.org {", 1)[1]
    assert "\tlog_name wgctl\n" in wild and "log wgctl {" in wild and "log wgctl_hidden {" in wild
    site = wild.split("handle @site_vpnhook {", 1)[1].split("\n\t}", 1)[0]
    assert "log_name wgctl_hidden" in site and "@nolog_vpnhook path /s /health" in site and "log_skip @nolog_vpnhook" in site
    plain = wild.split("handle @site_plain {", 1)[1].split("\n\t}", 1)[0]
    assert "\t\tlog_skip\n" in plain


def test_location_lifecycle(hub_en):
    assert "No locations" in hub_en.run("location", "list").stdout
    hub_en.run("location", "add", "office", "--title", "Office", "--networks", "10.20.0.0/24")
    st = hub_en.state()["locations"]["office"]
    pub, ip = st["pubkey"], st["ip"]
    assert ip == "10.77.0.2"
    mt = hub_en.run("location", "conf", "office", "--format", "mikrotik").stdout
    assert "/interface wireguard add" in mt and "allowed-address=10.77.0.1/32" in mt
    ow = hub_en.run("location", "conf", "office", "--format", "openwrt").stdout
    assert "uci commit network" in ow and "10.77.0.2/24" in ow
    wg = hub_en.run("location", "conf", "office", "--format", "wg").stdout
    assert "AllowedIPs = 10.77.0.1/32" in wg
    assert "AllowedIPs = 10.77.0.2/32, 10.20.0.0/24" in hub_en.read("/etc/wireguard/wg0.conf")
    # a second location may not overlap the first one's networks
    r = hub_en.run("location", "add", "branch", "--networks", "10.20.0.128/25", ok=False)
    assert r.returncode != 0
    hub_en.run("location", "reissue", "office")
    assert hub_en.state()["locations"]["office"]["pubkey"] != pub
    hub_en.run("location", "set", "office", "--networks", "10.20.0.0/24,10.21.0.0/24", "--title", "HQ")
    loc = hub_en.state()["locations"]["office"]
    assert loc["networks"] == ["10.20.0.0/24", "10.21.0.0/24"] and loc["title"] == "HQ"
    hub_en.run("location", "rm", "office", "-y")
    assert "office" not in hub_en.state()["locations"]
    assert "10.20.0.0/24" not in hub_en.read("/etc/wireguard/wg0.conf")


def test_location_names_and_range(hub_en):
    for bad in ("Bad Name", "vpnadmin", "-x"):
        assert hub_en.run("location", "add", bad, "--networks", "10.30.0.0/24", ok=False).returncode != 0
    for i in range(8):
        hub_en.run("location", "add", f"l{i}", "--networks", f"10.{40 + i}.0.0/24")
    r = hub_en.run("location", "add", "l9", "--networks", "10.60.0.0/24", ok=False)
    assert r.returncode != 0, "only locations_from..locations_to addresses are available"


def test_location_adopt(hub_en):
    """A router added by hand to wg0.conf (before wgctl managed locations) is taken over with its keys."""
    import json
    import os
    import subprocess
    import sys
    from conftest import WGCTL
    pub = "HOMEPUBKEYHOMEPUBKEYHOMEPUBKEYHOMEPUBKEY0="
    wg = hub_en.root / "etc/wireguard/wg0.conf"
    wg.write_text(wg.read_text() + f"\n[Peer]\n# home router\nPublicKey = {pub}\nAllowedIPs = 10.77.0.2/32, 192.168.40.0/24\n")
    sp = hub_en.root / "etc/wgctl/state.json"
    st = json.loads(sp.read_text())
    st["locations"] = {"home": {"title": "Home", "pubkey": pub, "ip": "10.77.0.2", "networks": ["192.168.40.0/24"]},
                       "work": {"title": "Work"}}                       # an old placeholder without a router
    sp.write_text(json.dumps(st))
    assert list(hub_en.state()["locations"]) == ["home", "work"]
    assert "work" not in hub_en.run("location", "list").stdout, "placeholders are dropped"
    assert hub_en.run("location", "set", "home", "--networks", "192.168.41.0/24", ok=False).returncode != 0
    assert hub_en.run("location", "adopt", "home", ok=False, input="").returncode != 0, "terminal only"
    master, slave = os.openpty()
    r = subprocess.run([sys.executable, "-I", str(WGCTL), "location", "adopt", "home"], env=hub_en.env,
                       stdin=slave, capture_output=True, text=True, timeout=60)
    os.close(master)
    os.close(slave)
    assert r.returncode == 0, r.stderr
    conf = wg.read_text()
    assert conf.count(pub) == 1 and "AllowedIPs = 10.77.0.2/32, 192.168.40.0/24" in conf
    assert (hub_en.root / "etc/wireguard/wg0.conf.before-adopt").exists()
    hub_en.run("location", "set", "home", "--networks", "192.168.40.0/24,192.168.41.0/24")
    assert "192.168.41.0/24" in wg.read_text()


@pytest.mark.parametrize("net", ["0.0.0.0/0", "127.0.0.0/8", "169.254.0.0/16", "8.8.8.0/24", "10.0.0.0/7"])
def test_location_network_must_be_private_lan(hub_en, net):
    assert hub_en.run("location", "add", "x", "--networks", net, ok=False).returncode != 0


def test_location_network_cannot_take_vps_network(hub_en):
    hub_en.env["WGCTL_HOST_NETS"] = "10.0.0.0/24"
    r = hub_en.run("location", "add", "x", "--networks", "10.0.0.0/16", ok=False)
    assert r.returncode != 0 and "VPS" in r.stderr + r.stdout
