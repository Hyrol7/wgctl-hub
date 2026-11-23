"""Key roles (admin / server / client), their address ranges, `move` and `rename`."""
import json


def test_roles_get_addresses_from_their_ranges(hub_en):
    hub_en.run("add", "phone")
    hub_en.run("add", "mac", "--admin")
    hub_en.run("add", "pi", "--role", "server")
    st = hub_en.state()["clients"]
    assert (st["phone"]["role"], st["phone"]["ip"]) == ("client", "10.77.0.51")
    assert (st["mac"]["role"], st["mac"]["ip"], st["mac"]["admin"]) == ("admin", "10.77.0.10", True)
    assert (st["pi"]["role"], st["pi"]["ip"]) == ("server", "10.77.0.20")
    assert st["pi"]["autorevoke"] is False, "a server is online by design"
    assert hub_en.run("add", "x", "--role", "server", "--ip", "60", ok=False).returncode != 0
    hub_en.run("add", "pi2", "--role", "server", "--ip", "33")
    assert hub_en.state()["clients"]["pi2"]["ip"] == "10.77.0.33"


def test_all_sites_only_for_admin(hub_en):
    hub_en.run("site", "add", "a", "http://127.0.0.1:8791")
    assert hub_en.run("add", "phone", "--sites", "*", ok=False).returncode != 0
    assert hub_en.run("add", "pi", "--role", "server", "--sites", "*", ok=False).returncode != 0
    hub_en.run("add", "phone", "--sites", "a")
    assert hub_en.run("set", "phone", "--sites", "*", ok=False).returncode != 0
    hub_en.run("add", "mac", "--admin", "--sites", "*")
    r = hub_en.run("set", "mac", "--role", "server", ok=False)
    assert r.returncode != 0, "leaving admin with '*' needs an explicit list"
    hub_en.run("set", "mac", "--role", "server", "--sites", "none")
    c = hub_en.state()["clients"]["mac"]
    assert (c["role"], c["admin"], c["sites"]) == ("server", False, [])


def test_admin_flag_is_the_admin_role(hub_en):
    hub_en.run("add", "phone")
    hub_en.run("set", "phone", "--admin", "on")
    c = hub_en.state()["clients"]["phone"]
    assert (c["role"], c["admin"]) == ("admin", True)
    out = hub_en.run("set", "phone", "--admin", "off").stdout
    c = hub_en.state()["clients"]["phone"]
    assert (c["role"], c["admin"]) == ("client", False)
    assert "wgctl move phone" not in out, "10.77.0.51 is already in the client range"
    hub_en.run("add", "guest", "--hours", "2")
    assert hub_en.run("set", "guest", "--role", "server", ok=False).returncode != 0
    assert hub_en.run("add", "g2", "--hours", "2", "--role", "server", ok=False).returncode != 0


def test_old_keys_get_a_role(hub_en):
    hub_en.run("add", "mac", "--admin")
    hub_en.run("add", "pi", "--role", "server")
    hub_en.run("add", "phone")
    hub_en.run("site", "add", "bot", "http://10.77.0.20:8347")
    path = hub_en.root / "etc/wgctl/state.json"
    st = json.loads(path.read_text())
    for c in st["clients"].values():
        c.pop("role")
    path.write_text(json.dumps(st))
    roles = {v["name"]: (v["role"], v["role_ok"]) for v in json.loads(hub_en.run("list", "--json").stdout)}
    assert roles == {"mac": ("admin", True), "pi": ("server", True), "phone": ("client", True)}


def test_underscore_in_key_names(hub_en):
    hub_en.run("add", "macbook_m2", "--admin")
    assert hub_en.state()["clients"]["macbook_m2"]["ip"] == "10.77.0.10"
    assert hub_en.run("site", "add", "a_b", "http://127.0.0.1:8791", ok=False).returncode != 0, "sites stay DNS labels"


def test_move_follows_sites_and_services(hub_en):
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    hub_en.run("add", "pi", "--ip", "60")                           # an old key in the client range
    hub_en.run("set", "pi", "--role", "server")
    hub_en.run("site", "add", "bot", "http://10.77.0.60:8347")
    hub_en.run("tcp", "add", "pi-ssh", "10.77.0.60:22")
    hub_en.run("add", "mac", "--admin")
    hub_en.run("tcp", "allow", "pi-ssh", "mac")
    hub_en.run("grant", "mac", "bot")
    assert not json.loads(hub_en.run("show", "pi", "--json").stdout)["role_ok"]
    out = hub_en.run("move", "pi").stdout
    assert "10.77.0.20" in out and "Address" in out
    st = hub_en.state()
    assert st["clients"]["pi"]["ip"] == "10.77.0.20"
    assert st["sites"]["bot"]["backend"] == "http://10.77.0.20:8347"
    assert st["services"]["pi-ssh"]["target"] == "10.77.0.20"
    assert "Address = 10.77.0.20/32" in hub_en.read("/etc/wgctl/clients/pi.conf")
    assert "10.77.0.20:8347" in hub_en.read("/etc/caddy/wgctl.caddy")
    assert "10.77.0.60" not in hub_en.read("/etc/wireguard/wg0.conf")
    assert hub_en.run("move", "pi", "--ip", "10", ok=False).returncode != 0, "not outside the role range"


def test_rename_keeps_keys_and_address(hub_en):
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    hub_en.run("add", "mac", "--admin")
    hub_en.run("tcp", "add", "nas-ssh", "192.168.1.10:22")
    hub_en.run("tcp", "allow", "nas-ssh", "mac")
    before = hub_en.state()["clients"]["mac"]
    conf = hub_en.read("/etc/wgctl/clients/mac.conf")
    hub_en.run("rename", "mac", "macbook_m2")
    st = hub_en.state()
    assert "mac" not in st["clients"]
    after = st["clients"]["macbook_m2"]
    assert (after["ip"], after["pubkey"], after["role"]) == (before["ip"], before["pubkey"], "admin")
    assert st["services"]["nas-ssh"]["allow"] == ["macbook_m2"]
    assert hub_en.read("/etc/wgctl/clients/macbook_m2.conf") == conf
    assert not (hub_en.root / "etc/wgctl/clients/mac.conf").exists()
    hub_en.run("add", "phone")
    assert hub_en.run("rename", "phone", "macbook_m2", ok=False).returncode != 0
    assert hub_en.run("rename", "phone", "home", ok=False).returncode != 0, "a location's name"
