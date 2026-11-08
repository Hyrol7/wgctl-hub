#!/usr/bin/env python3
"""Render panel pages with demo data into PNG files (for docs/img and visual checks).

Usage: python3 tools/screenshots.py OUT_DIR [--lang en|uk] [page ...]
Needs Playwright with Chromium. Everything runs in a temporary root; nothing touches the system.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from conftest import Client, Hub, Panel, _init  # noqa: E402

PAGES = {"overview": "/", "locations": "/locations", "location": "/l/home", "sites": "/sites",
         "key": "/c/anna-phone", "new": "/new", "log": "/log", "server": "/server", "settings": "/settings"}


def demo(hub, empty=False):
    if empty:
        return
    hub.run("location", "add", "home", "--title", "Home", "--networks", "192.168.1.0/24")
    hub.run("location", "add", "office", "--title", "Office", "--networks", "10.20.0.0/24")
    for name, url in (("nas", "http://192.168.1.10:5000"), ("photos", "http://192.168.1.11:2342"),
                      ("ha", "http://192.168.1.12:8123"), ("wiki", "http://10.20.0.5:3000")):
        hub.run("site", "add", name, url)
    hub.run("add", "anna-phone", "--sites", "nas,photos", "--admin")
    hub.run("add", "work-laptop", "--sites", "*")
    hub.run("add", "guest", "--hours", "4", "--sites", "photos")
    import time
    with open(hub.root / "dump", "a") as f:
        for i, (name, loc) in enumerate(hub.state()["locations"].items()):
            f.write("\t".join([loc["pubkey"], "psk", f"192.0.2.{10 + i}:13231", "10.77.0.0/32",
                               str(int(time.time()) - 20), "50000000", "90000000", "25"]) + "\n")
    import json
    sp = hub.root / "etc/wgctl/state.json"
    st = json.loads(sp.read_text())
    for i, s in enumerate(st["sites"].values()):
        s["health"] = {"ok": True, "ms": 8 + 5 * i, "ts": int(time.time())}
    sp.write_text(json.dumps(st))
    hub.set_online("anna-phone", "203.0.113.20:51000")
    hub.set_online("work-laptop", "198.51.100.30:42000", age=70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--mobile", action="store_true")
    ap.add_argument("--empty", action="store_true", help="fresh hub: shows the first-steps wizard")
    ap.add_argument("--brand", default="Demo VPN")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--height", type=int, help="cut the page at this height (CSS pixels)")
    ap.add_argument("pages", nargs="*")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        hub = Hub(Path(tmp), a.lang)
        _init(hub, a.lang)
        cf = hub.root / "etc/wgctl/config.toml"
        cf.write_text(cf.read_text().replace('brand = "Test VPN"', f'brand = "{a.brand}"'))
        demo(hub, a.empty)
        if a.empty:
            hub.run("add", "admin-phone", "--admin")
        panel = Panel(hub)
        try:
            c = Client(panel)
            c.login()
            name, value = c.cookie.split("=", 1)
            with sync_playwright() as pw:
                b = pw.chromium.launch()
                vp = {"width": 390, "height": 844} if a.mobile else {"width": 1280, "height": 900}
                ctx = b.new_context(viewport=vp, device_scale_factor=a.scale, color_scheme="dark" if a.dark else "light",
                                    extra_http_headers={"X-Forwarded-For": c.ip})
                ctx.add_cookies([{"name": name, "value": value, "url": panel.origin}])
                pg = ctx.new_page()
                for p in a.pages or PAGES:
                    pg.goto(panel.origin + PAGES.get(p, p))
                    pg.wait_for_timeout(400)
                    f = out / f"{p.strip('/').replace('/', '_') or 'root'}.png"
                    if a.height:
                        pg.screenshot(path=str(f), full_page=True,
                                      clip={"x": 0, "y": 0, "width": vp["width"], "height": a.height})
                    else:
                        pg.screenshot(path=str(f), full_page=True)
                    print(f)
                b.close()
        finally:
            panel.stop()


if __name__ == "__main__":
    main()
