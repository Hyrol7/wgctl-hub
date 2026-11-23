"""SSH to the hub follows panel access (wgctl ssh ...)."""
import subprocess
import sys

from conftest import REPO, WGCTL

INTERIM = '        iifname "wg0" ip saddr { 10.77.0.2, 10.77.0.10, 10.77.0.11 } tcp dport 22 accept   # SSH: hand-written\n'


def nft_conf(hub, extra_line=None):
    text = (REPO / "templates/nftables.conf.in").read_text()
    for k, v in {"@WAN@": "eth0", "@CLIENTS@": "10.77.0.10-10.77.0.254", "@LOCATIONS@": "10.77.0.2-10.77.0.9",
                 "@SSH_PORT@": "22", "@WG_PORT@": "51820", "@IFACE@": "wg0"}.items():
        text = text.replace(k, v)
    if extra_line:
        text = text.replace("        tcp dport 22 accept\n", extra_line)
    (hub.root / "etc/nftables.conf").write_text(text)


def run(hub, *args, ok=True, ssh_from=None):
    env = dict(hub.env, WGCTL_ALLOW_NOTTY="1")
    env.pop("SSH_CONNECTION", None)
    if ssh_from:
        env["SSH_CONNECTION"] = f"{ssh_from} 50000 198.51.100.7 22"
    r = subprocess.run([sys.executable, "-I", str(WGCTL), *args], env=env, capture_output=True, text=True, timeout=60)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def test_setup_needs_an_admin(hub_en):
    nft_conf(hub_en)
    hub_en.run("add", "laptop")
    r = run(hub_en, "ssh", "setup", "-y", ok=False)
    assert r.returncode != 0
    assert "jump wgctl_ssh" not in hub_en.read("/etc/nftables.conf")


def test_setup_replaces_open_rule_and_follows_admin_flag(hub_en):
    nft_conf(hub_en)
    hub_en.run("add", "mac", "--admin")
    hub_en.run("add", "tv")
    run(hub_en, "ssh", "setup", "-y")
    conf = hub_en.read("/etc/nftables.conf")
    assert "jump wgctl_ssh" in conf and "\n        tcp dport 22 accept" not in conf
    assert 'include "/etc/nftables.d/wgctl-ssh.nft"' in conf
    chain = hub_en.read("/etc/nftables.d/wgctl-ssh.nft")
    assert "10.77.0.10" in chain and "10.77.0.11" not in chain and 'iifname "wg0"' in chain
    hub_en.run("set", "tv", "--admin", "on")
    assert "10.77.0.11" in hub_en.read("/etc/nftables.d/wgctl-ssh.nft")
    hub_en.run("set", "tv", "--admin", "off")
    assert "10.77.0.11" not in hub_en.read("/etc/nftables.d/wgctl-ssh.nft")


def test_setup_migrates_hand_written_rule(hub_en):
    nft_conf(hub_en, INTERIM)
    hub_en.run("add", "mac", "--admin")
    run(hub_en, "ssh", "setup", "-y")
    conf = hub_en.read("/etc/nftables.conf")
    assert "hand-written" not in conf and conf.count("jump wgctl_ssh") == 1


def test_setup_refuses_to_cut_current_session(hub_en):
    nft_conf(hub_en)
    hub_en.run("add", "mac", "--admin")
    r = run(hub_en, "ssh", "setup", "-y", ssh_from="203.0.113.9", ok=False)
    assert r.returncode != 0 and "203.0.113.9" in r.stderr
    assert "jump wgctl_ssh" not in hub_en.read("/etc/nftables.conf")
    run(hub_en, "ssh", "setup", "-y", ssh_from="10.77.0.10")


def test_extra_addresses(hub_en):
    nft_conf(hub_en)
    hub_en.run("add", "mac", "--admin")
    run(hub_en, "ssh", "setup", "-y")
    run(hub_en, "ssh", "allow", "192.168.40.0/24", "203.0.113.5")
    chain = hub_en.read("/etc/nftables.d/wgctl-ssh.nft")
    vpn_line = next(ln for ln in chain.splitlines() if "iifname" in ln)
    assert "192.168.40.0/24" in vpn_line, "private networks only through the tunnel"
    assert "ip saddr { 203.0.113.5 } tcp dport 22 accept" in chain
    r = run(hub_en, "ssh", "deny", "203.0.113.5", ssh_from="203.0.113.5", ok=False)
    assert r.returncode != 0
    run(hub_en, "ssh", "deny", "203.0.113.5")
    assert "203.0.113.5" not in hub_en.read("/etc/nftables.d/wgctl-ssh.nft")
    assert run(hub_en, "ssh", "allow", "0.0.0.0/0", ok=False).returncode != 0


def test_last_admin_gone_keeps_previous_rules(hub_en):
    nft_conf(hub_en)
    hub_en.run("add", "mac", "--admin")
    run(hub_en, "ssh", "setup", "-y")
    hub_en.run("revoke", "mac", "-y", ok=False)
    assert "10.77.0.10" in hub_en.read("/etc/nftables.d/wgctl-ssh.nft")


def test_off_restores_open_rule(hub_en):
    nft_conf(hub_en)
    hub_en.run("add", "mac", "--admin")
    run(hub_en, "ssh", "setup", "-y")
    run(hub_en, "ssh", "off", "-y")
    conf = hub_en.read("/etc/nftables.conf")
    assert "wgctl_ssh" not in conf and "wgctl-ssh.nft" not in conf
    assert "        tcp dport 22 accept\n" in conf
    assert "jump wgctl_tcp" in conf
