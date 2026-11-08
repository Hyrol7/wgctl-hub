"""Regression tests for the security review (each test names the issue it guards against)."""
import io
import os
import shutil
import subprocess
import tarfile

import pytest

from conftest import Client, WGCTL


@pytest.fixture
def home(hub_en):
    hub_en.run("location", "add", "home", "--networks", "192.168.1.0/24")
    return hub_en


# --- site backends: only IP literals inside a location, a key, or allowed VPS ports -------------
@pytest.mark.parametrize("backend", [
    "http://127.1:2019",              # short form of 127.0.0.1 -> Caddy admin API
    "http://0x7f000001:8090",         # hex loopback -> the panel without the admin-key filter
    "http://2130706433:2019",         # integer loopback
    "http://localtest.me:8090",       # a public name that resolves to 127.0.0.1
    "http://example.com",             # any hostname
    "http://10.77.0.1:2201",          # a TCP service port: would bypass its per-key rule
    "http://127.0.0.1:22",
    "http://8.8.8.8:80",              # outside every location
    "http://192.168.1.10:80/path",
])
def test_backend_rejected(home, backend):
    assert home.run("site", "add", "x", backend, ok=False).returncode != 0, backend


@pytest.mark.parametrize("backend", ["http://192.168.1.10:5000", "https://192.168.1.11:8006", "http://127.0.0.1:3000",
                                     "192.168.1.12"])
def test_backend_accepted(home, backend):
    home.run("site", "add", "ok", backend)


def test_backend_on_a_key_device(home):
    home.run("add", "laptop")
    home.run("site", "add", "dev", "http://10.77.0.10:8080")


# --- guest keys never get the panel, also through `set` -----------------------------------------
def test_guest_cannot_become_admin(hub_en):
    hub_en.run("add", "guest", "--hours", "2")
    assert hub_en.run("set", "guest", "--admin", "on", ok=False).returncode != 0
    assert not hub_en.state()["clients"]["guest"]["admin"]


# --- one network may belong to one location only (WireGuard routes it to a single peer) ---------
def test_location_networks_do_not_overlap(home):
    assert home.run("location", "add", "work", "--networks", "192.168.0.0/16", ok=False).returncode != 0
    assert home.run("location", "add", "work", "--networks", "10.20.0.0/24,10.20.0.0/25", ok=False).returncode != 0
    home.run("location", "add", "work", "--networks", "10.20.0.0/24")
    home.run("location", "set", "home", "--networks", "192.168.1.0/24,192.168.2.0/24")


# --- Signal arguments cannot become signal-cli options -----------------------------------------
@pytest.mark.parametrize("group", ["--foo", "-a +1555", "x"])
def test_signal_group_id_validated(hub_en, group):
    assert hub_en.run("notify", "set", f"--group={group}", ok=False).returncode != 0


def test_signal_test_recipient_validated(hub_en):
    hub_en.run("notify", "set", "--admins", "+15551234567", "--sender", "+15550001111")
    assert hub_en.run("notify", "test", "--to=-g", ok=False).returncode != 0


# --- the panel (sudo from user vpnadmin) can only run what it uses -----------------------------
@pytest.mark.parametrize("args", [["init", "--yes", "--domain", "x.org", "--public-ip", "1.2.3.4", "--force"],
                                  ["backup", "restore", "/tmp/x", "--apply", "-y"], ["backup", "init"],
                                  ["tcp", "setup", "-y"], ["location", "adopt", "evil"], ["panel", "off"],
                                  ["render"], ["cloudflare", "--zone", "0" * 32], ["geo", "update"], ["notify", "clear"]])
def test_panel_user_cannot_run_admin_only_commands(hub_en, args):
    env = dict(hub_en.env, SUDO_USER="vpnadmin")
    r = subprocess.run(["python3", "-I", str(WGCTL), *args], env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "web panel" in (r.stderr + r.stdout)


def test_panel_user_can_run_panel_commands(hub_en):
    env = dict(hub_en.env, SUDO_USER="vpnadmin")
    for args in (["list", "--json"], ["status", "--json"], ["add", "pc"], ["site", "list", "--json"],
                 ["backup", "status", "--json"], ["notify", "show", "--json"]):
        r = subprocess.run(["python3", "-I", str(WGCTL), *args], env=env, capture_output=True, text=True)
        assert r.returncode == 0, (args, r.stderr)


# --- config values are validated before they reach Caddy / bash --------------------------------
@pytest.mark.parametrize("key,value", [("domain", '"x.org {"'), ("interface", '"wg0; reboot"'),
                                       ("public_ip", '"not-an-ip"'), ("clients_to", "300")])
def test_bad_config_rejected(hub_en, key, value):
    cfg = hub_en.root / "etc/wgctl/config.toml"
    text = cfg.read_text()
    import re
    cfg.write_text(re.sub(rf"(?m)^{key} = .*$", f"{key} = {value}", text))
    r = hub_en.run("status", ok=False)
    assert r.returncode != 0 and "config.toml" in r.stderr and "Traceback" not in r.stderr


def test_broken_toml_is_a_clear_error(hub_en):
    (hub_en.root / "etc/wgctl/config.toml").write_text("[general\n")
    r = hub_en.run("status", ok=False)
    assert r.returncode != 0 and "Traceback" not in r.stderr


# --- backup restore writes only the backup's own paths, with the right owners ------------------
@pytest.mark.skipif(not shutil.which("age"), reason="age not installed")
def test_restore_ignores_paths_outside_backup(hub_en, tmp_path):
    key = subprocess.run(["age-keygen"], capture_output=True, text=True).stdout
    secret = next(ln for ln in key.splitlines() if ln.startswith("AGE-SECRET-KEY-"))
    pub = subprocess.run(["age-keygen", "-y"], input=secret + "\n", capture_output=True, text=True).stdout.strip()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("MANIFEST.json", b"{}"), ("etc/sudoers.d/evil", b"ALL ALL=(ALL) NOPASSWD: ALL\n"),
                           ("root/.ssh/authorized_keys", b"ssh-ed25519 AAAA evil\n"),
                           ("etc/wgctl/marker.txt", b"ok\n")):
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
    arc = tmp_path / "evil.tar.gz.age"
    subprocess.run(["age", "-r", pub, "-o", str(arc)], input=buf.getvalue(), check=True)
    env = dict(hub_en.env, WGCTL_AGE_KEY=secret, WGCTL_ALLOW_NOTTY="1")
    r = subprocess.run(["python3", "-I", str(WGCTL), "backup", "restore", str(arc), "--apply", "-y"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (hub_en.root / "etc/wgctl/marker.txt").exists()
    assert not (hub_en.root / "etc/sudoers.d/evil").exists()
    assert not (hub_en.root / "root/.ssh/authorized_keys").exists()


# --- Signal attachments: a symlink planted by the signal user is not followed by root ----------
def test_signal_outgoing_symlink_not_followed(hub_en, tmp_path):
    hub_en.run("notify", "set", "--admins", "+15551234567", "--sender", "+15550001111")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n")
    out = hub_en.root / "var/lib/signal-cli/outgoing"
    out.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(tmp_path, out)                       # the whole directory replaced by a link
    if not shutil.which("age"):
        pytest.skip("age not installed")
    key = subprocess.run(["age-keygen"], capture_output=True, text=True).stdout
    pub = next(ln.split(": ")[1] for ln in key.splitlines() if ln.startswith("# public key"))
    (hub_en.root / "etc/wgctl/backup-recipient.txt").write_text(pub + "\n")
    hub_en.run("backup", "run", "--signal")
    assert victim.read_text() == "keep me\n"
    assert not out.is_symlink() and out.is_dir()
    assert not any(p.name.endswith(".age") for p in tmp_path.iterdir() if p.is_file() and p != victim)


# --- panel routes never pass option-like names to wgctl -----------------------------------------
def test_panel_route_names(panel):
    c = Client(panel)
    c.login()
    st, _, t, _ = c.req("GET", "/")
    tok = c.csrf(t)
    for path in ("/c/--admin", "/c/-y", "/s/--public", "/t/-x"):
        assert c.req("POST", path, {"csrf": tok, "act": "disable"})[0] == 404, path
