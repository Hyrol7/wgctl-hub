"""Test harness: a throw-away hub under a temporary root.

wgctl and vpnadmin honour a few test-only environment variables:
  WGCTL_ROOT      prefix for every system path (/etc, /var, /run)
  WGCTL_DRY       never call wg-quick, systemctl or nft
  WGCTL_DUMP      file used instead of `wg show wg0 dump`
  WGCTL_SRV_PUB   server public key instead of reading wg0.conf
  WGCTL_NO_PROBE  skip HTTP/TCP health probes
  WGCTL_SIGNAL_FAKE  append outgoing Signal messages to this file
"""
import http.client
import json
import os
import re
import runpy
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WGCTL = REPO / "src" / "wgctl"
VPNADMIN = REPO / "src" / "vpnadmin"
BIN = Path(__file__).resolve().parent / "bin"
SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
PASSWORD = "correct horse battery"


class Hub:
    def __init__(self, root: Path, lang: str):
        self.root = root
        self.lang = lang
        for d in ("etc/wgctl", "etc/caddy", "etc/wireguard", "etc/nftables.d", "etc/vpnadmin",
                  "etc/systemd/system", "var/lib/wgctl", "var/log/caddy", "run"):
            (root / d).mkdir(parents=True, exist_ok=True)
        (root / "dump").write_text("hdr\n")
        self.env = dict(os.environ,
                        PATH=f"{BIN}:{os.environ['PATH']}",
                        WGCTL_ROOT=str(root), WGCTL_DRY="1", WGCTL_SRV_PUB="SRVPUB=",
                        WGCTL_DUMP=str(root / "dump"), WGCTL_CADDY_BIN=str(BIN / "caddy"),
                        WGCTL_TEST_TLS="internal", WGCTL_NO_PROBE="1", HOME=str(root),
                        WGCTL_SIGNAL_FAKE=str(root / "signal.jsonl"),
                        WGCTL_SHARE=str(REPO / "share"),
                        WGCTL_CONFIG=str(root / "etc/wgctl/config.toml"))

    def run(self, *args, ok=True, input=None):
        r = subprocess.run([sys.executable, "-I", str(WGCTL), *args], env=self.env, input=input,
                           capture_output=True, text=True, timeout=60)
        if ok and r.returncode != 0:
            raise AssertionError(f"wgctl {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def state(self):
        return json.loads((self.root / "etc/wgctl/state.json").read_text())

    def read(self, path):
        return (self.root / path.lstrip("/")).read_text()

    def set_online(self, name, endpoint="176.122.105.209:5000", age=10):
        """Pretend a client has a fresh handshake."""
        pub = self.state()["clients"][name]["pubkey"]
        line = "\t".join([pub, "psk", endpoint, "10.77.0.0/32", str(int(time.time()) - age), "1000", "2000", "25"])
        with open(self.root / "dump", "a") as f:
            f.write(line + "\n")


def _init(hub, lang):
    hub.run("init", "--yes", "--domain", "example.org", "--public-ip", "198.51.100.7",
            "--language", lang, "--brand", "Test VPN", "--timezone", "Europe/Kyiv")


@pytest.fixture(params=["en", "uk"])
def hub(tmp_path, request):
    h = Hub(tmp_path, request.param)
    _init(h, request.param)
    return h


@pytest.fixture
def hub_en(tmp_path):
    h = Hub(tmp_path, "en")
    _init(h, "en")
    return h


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Panel:
    """A running vpnadmin bound to a free port, using a wrapper that calls wgctl in the same root."""

    def __init__(self, hub: Hub):
        self.hub = hub
        self.port = free_port()
        self.origin = f"http://127.0.0.1:{self.port}"
        wrap = hub.root / "wgctl-wrap"
        wrap.write_text("#!/bin/sh\n" + " ".join(
            f"{k}='{v}'" for k, v in hub.env.items() if k.startswith("WGCTL_") or k in ("PATH", "HOME")) +
            f" exec {sys.executable} -I {WGCTL} \"$@\"\n")
        wrap.chmod(0o755)
        self.env = dict(hub.env, VPNADMIN_DIR=str(hub.root / "etc/vpnadmin"), VPNADMIN_WGCTL=str(wrap),
                        VPNADMIN_PORT=str(self.port), VPNADMIN_ORIGIN=self.origin, VPNADMIN_COOKIE="vpnadmin")
        os.environ.update({k: v for k, v in self.env.items() if k.startswith(("WGCTL_", "VPNADMIN_"))})
        self.mod = runpy.run_path(str(VPNADMIN))          # for make_pw / totp_at
        auth = {"user": "admin", "pw": self.mod["make_pw"](PASSWORD), "totp": SECRET, "totp_last": 0,
                "backup": [], "created": int(time.time()), "pw_changed": int(time.time()), "epoch": 1}
        (hub.root / "etc/vpnadmin/auth.json").write_text(json.dumps(auth))
        self.proc = subprocess.Popen([sys.executable, "-I", str(VPNADMIN), "serve"], env=self.env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        self.last = 0

    def code(self):
        """Next unused TOTP code (waits for a new 30-s window if needed)."""
        while True:
            now = int(time.time()) // 30
            c = max(now, self.last + 1)
            if c <= now + 1:
                self.last = c
                return self.mod["totp_at"](SECRET, c)
            time.sleep(1)

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)


class Client:
    def __init__(self, panel: Panel, ip="10.77.0.10"):
        self.p, self.cookie, self.ip = panel, "", ip

    def req(self, method, path, data=None, origin=True, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.p.port, timeout=60)
        h = {"X-Forwarded-For": self.ip}
        if self.cookie:
            h["Cookie"] = self.cookie
        h.update(headers or {})
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data, doseq=True)
            h["Content-Type"] = "application/x-www-form-urlencoded"
            if origin:
                h["Origin"] = self.p.origin
        c.request(method, path, body, h)
        r = c.getresponse()
        text = r.read().decode("utf-8", "replace")
        sc = r.getheader("Set-Cookie")
        if sc and sc.startswith("vpnadmin="):
            v = sc.split(";")[0]
            self.cookie = v if v.split("=", 1)[1] else ""
        return r.status, r.getheader("Location"), text, r

    def login(self, code=None, password=PASSWORD):
        return self.req("POST", "/login", {"user": "admin", "password": password, "code": code or self.p.code()})

    @staticmethod
    def csrf(text):
        return re.search(r'name="csrf" value="([^"]+)"', text).group(1)


@pytest.fixture
def panel(hub_en):
    hub_en.run("location", "add", "home", "--title", "Home", "--networks", "192.168.1.0/24")
    hub_en.run("site", "add", "nas", "http://192.168.1.10:5000")
    hub_en.run("add", "phone", "--sites", "nas", "--admin")
    p = Panel(hub_en)
    yield p
    p.stop()
