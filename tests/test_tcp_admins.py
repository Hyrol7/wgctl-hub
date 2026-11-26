"""SSH to server keys for every admin key (wgctl set KEY --ssh, wgctl tcp ... --admins)."""
import json

from test_ssh import nft_conf, run


def services(hub):
    return {s["name"]: s for s in json.loads(hub.run("tcp", "list", "--json").stdout)["services"]}


def chain(hub):
    return hub.read("/etc/nftables.d/wgctl-tcp.nft")


def setup(hub):
    nft_conf(hub)
    run(hub, "tcp", "setup", "-y")
    hub.run("add", "mac", "--admin")                       # .10
    hub.run("add", "pi", "--role", "server")               # .20
    hub.run("add", "phone")                                # .51


def test_server_ssh_follows_admin_role(hub_en):
    setup(hub_en)
    hub_en.run("set", "pi", "--ssh", "on")
    sv = hub_en.state()["services"]["pi-ssh"]
    assert (sv["target"], sv["target_port"], sv["port"], sv["admins"], sv["auto"]) == ("10.77.0.20", 22, 2201, True, "pi")
    assert services(hub_en)["pi-ssh"]["allow"] == ["mac"]
    rule = next(ln for ln in chain(hub_en).splitlines() if "# pi-ssh" in ln)
    assert "10.77.0.10" in rule and "10.77.0.51" not in rule and "tcp dport 2201" in rule
    hub_en.run("add", "air", "--admin")                    # a new admin gets in without touching the service
    assert "10.77.0.11" in chain(hub_en)
    hub_en.run("set", "air", "--admin", "off")             # and loses it with the role
    assert "10.77.0.11" not in chain(hub_en)
    hub_en.run("disable", "mac")
    assert "# pi-ssh" not in chain(hub_en), "no active admin, no rule"


def test_only_servers_and_cleanup(hub_en):
    setup(hub_en)
    assert hub_en.run("set", "phone", "--ssh", "on", ok=False).returncode != 0
    assert hub_en.run("set", "mac", "--ssh", "on", ok=False).returncode != 0
    hub_en.run("set", "pi", "--ssh", "2222")
    assert hub_en.state()["services"]["pi-ssh"]["target_port"] == 2222
    hub_en.run("set", "pi", "--ssh", "off")
    assert "pi-ssh" not in hub_en.state()["services"]
    hub_en.run("set", "pi", "--ssh", "on")
    hub_en.run("set", "pi", "--role", "client")            # leaving the server role removes it
    assert "pi-ssh" not in hub_en.state()["services"]
    hub_en.run("set", "pi", "--role", "server", "--ssh", "on")
    hub_en.run("revoke", "pi", "--yes")                    # the address may later go to another device
    assert "pi-ssh" not in hub_en.state()["services"] and "# pi-ssh" not in chain(hub_en)


def test_move_and_rename_follow(hub_en):
    setup(hub_en)
    hub_en.run("set", "pi", "--ssh", "on")
    hub_en.run("move", "pi", "--ip", "33")
    assert hub_en.state()["services"]["pi-ssh"]["target"] == "10.77.0.33"
    hub_en.run("rename", "pi", "pi_lab")
    assert hub_en.state()["services"]["pi-ssh"]["auto"] == "pi_lab"
    hub_en.run("set", "pi_lab", "--ssh", "off")
    assert "pi-ssh" not in hub_en.state()["services"]


def test_admins_flag_on_any_service(hub_en):
    setup(hub_en)
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    hub_en.run("tcp", "add", "nas-ssh", "192.168.1.10:22", "--admins", "on")
    hub_en.run("tcp", "allow", "nas-ssh", "phone")
    assert services(hub_en)["nas-ssh"]["allow"] == ["mac", "phone"]
    hub_en.run("tcp", "set", "nas-ssh", "--admins", "off")
    assert services(hub_en)["nas-ssh"]["allow"] == ["phone"]
    hub_en.run("set", "pi", "--ssh", "on")
    assert hub_en.run("tcp", "set", "pi-ssh", "--admins", "off", ok=False).returncode != 0
