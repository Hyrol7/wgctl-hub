"""vpnadmin web panel: authentication, CSRF, sensitive actions, page rendering."""
import re
import socket
import time

from conftest import Client, PASSWORD


def wait_log(panel, text, timeout=8):
    """Panel events are written in the background: poll the log for a while."""
    end = time.time() + timeout
    while time.time() < end:
        log = panel.hub.read("/var/log/wgctl.log")
        if text in log:
            return log
        time.sleep(0.2)
    raise AssertionError(f"{text!r} not in log")


def logged_in(panel, ip="10.77.0.10"):
    c = Client(panel, ip)
    st, loc, _, _ = c.login()
    assert st == 303 and loc == "/" and c.cookie
    st, _, t, _ = c.req("GET", "/")
    return c, c.csrf(t)


def test_redirects_and_security_headers(panel):
    c = Client(panel)
    st, loc, _, _ = c.req("GET", "/")
    assert st == 303 and loc == "/login"
    st, _, _, r = c.req("GET", "/login")
    h = dict(r.getheaders())
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "max-age" in h["Strict-Transport-Security"]
    assert h["Cross-Origin-Opener-Policy"] == "same-origin"
    assert h.get("Server", "").strip() == "vpnadmin"


def test_login_requires_same_origin(panel):
    c = Client(panel)
    st, *_ = c.req("POST", "/login", {"user": "admin", "password": PASSWORD, "code": "1"}, origin=False)
    assert st == 403
    st, *_ = c.req("POST", "/login", {"user": "admin", "password": PASSWORD, "code": "1"},
                   origin=False, headers={"Origin": "https://evil.example"})
    assert st == 403


def test_non_ascii_login_is_401_not_500(panel):
    st, *_ = Client(panel).req("POST", "/login", {"password": "пароль", "code": "1"})
    assert st == 401


def test_lockout_after_five_failures(panel):
    c = Client(panel, "10.77.0.50")
    for _ in range(5):
        c.req("POST", "/login", {"user": "admin", "password": "wrong", "code": "1"})
    st, loc, t, _ = c.login()
    assert not c.cookie and "Too many failed attempts" in t


def test_spoofed_first_forwarded_for_is_ignored(panel):
    c = Client(panel, "1.2.3.4, 10.77.0.51")
    c.req("POST", "/login", {"user": "admin", "password": "wrong", "code": "1"})
    log = wait_log(panel, "10.77.0.51")
    assert "1.2.3.4" not in log


def test_csrf_and_origin_on_actions(panel):
    c, tok = logged_in(panel)
    assert c.req("POST", "/c/phone", {"act": "extend"})[0] == 403
    assert c.req("POST", "/c/phone", {"act": "extend", "csrf": tok}, origin=False,
                 headers={"Origin": "https://evil.example"})[0] == 403
    assert c.req("POST", "/c/phone", {"act": "extend", "csrf": "щось"})[0] == 403
    assert c.req("POST", "/c/phone", {"act": "extend", "csrf": tok})[0] == 303


def test_config_needs_code(panel):
    c, tok = logged_in(panel)
    st, _, t, _ = c.req("GET", "/c/phone/conf")
    assert "PrivateKey" not in t
    st, _, t, _ = c.req("POST", "/c/phone/conf", {"csrf": tok, "act": "file"})
    assert st == 303 and "PrivateKey" not in t, "right after login the config needs a fresh code"
    st, _, t, r = c.req("POST", "/c/phone/conf", {"csrf": tok, "act": "file", "code": panel.code()})
    assert st == 200 and "PrivateKey" in t
    assert "attachment" in (r.getheader("Content-Disposition") or "")
    wait_log(panel, "Config phone downloaded from the panel")


def test_five_wrong_codes_end_session(panel):
    c, tok = logged_in(panel)
    for _ in range(5):
        c.req("POST", "/c/phone", {"csrf": tok, "act": "admin_off", "code": "000000"})
    assert c.req("GET", "/")[1] == "/login"


def test_form_text_never_becomes_options(panel):
    c, tok = logged_in(panel)
    st, loc, _, _ = c.req("POST", "/new", {"csrf": tok, "name": "Audit1", "note": "--admin", "autorevoke": "1",
                                          "kind": "perm", "site": "nas"})
    assert loc == "/c/audit1", "uppercase is normalised"
    cl = panel.hub.state()["clients"]["audit1"]
    assert cl["note"] == "--admin" and not cl["admin"]


def test_dangerous_backends_rejected_in_panel(panel):
    c, tok = logged_in(panel)
    for bk in ("http://127.0.0.1:8090", "http://localhost:2019", "http://10.77.0.1:443",
               "http://169.254.169.254:80", "--insecure"):
        c.req("POST", "/sites", {"csrf": tok, "name": "audit-s", "backend": bk})
        assert "audit-s" not in panel.hub.state()["sites"], bk


def test_negative_content_length(panel):
    c, _ = logged_in(panel)
    s = socket.create_connection(("127.0.0.1", panel.port), timeout=10)
    s.sendall(f"POST /settings HTTP/1.1\r\nHost: x\r\nCookie: {c.cookie}\r\nContent-Length: -1\r\n"
              f"Origin: {panel.origin}\r\n\r\n".encode())
    assert s.recv(100).decode(errors="replace").split(" ")[1] == "400"


def test_pages_render_in_english(panel):
    c, _ = logged_in(panel)
    for p in ("/", "/?f=online", "/?f=server", "/sites", "/s/nas", "/c/phone", "/new", "/log", "/log?cat=security",
              "/server", "/settings", "/locations", "/l/home"):
        st, _, t, _ = c.req("GET", p)
        assert st == 200 and "<footer>" in t and "Traceback" not in t, p
        visible = re.sub(r"<[^>]+>", " ", t).replace("Українська", "")   # language names stay native
        assert not re.search("[А-Яа-яІіЇїЄє]", visible), (p, re.findall("[А-Яа-яІіЇїЄє][^<]{0,40}", visible)[:3])
    st, _, t, _ = c.req("GET", "/nope")
    assert st == 404


def test_logout(panel):
    c, tok = logged_in(panel)
    c.req("POST", "/logout", {"csrf": tok})
    assert c.req("GET", "/")[1] == "/login"


def test_location_add_and_router_config(panel):
    c, tok = logged_in(panel)
    st, _, t, _ = c.req("GET", "/locations")
    assert st == 200 and "/l/home" in t
    form = {"csrf": tok, "act": "add", "name": "office", "title": "Office", "networks": "10.20.0.0/24"}
    st, *_ = c.req("POST", "/locations", dict(form, code="000000"))
    assert "office" not in panel.hub.state()["locations"], "adding a location needs a valid code"
    st, loc, *_ = c.req("POST", "/locations", dict(form, code=panel.code()))
    assert st == 303 and "office" in panel.hub.state()["locations"]
    # right after creation the router config is shown without another code
    st, _, t, _ = c.req("POST", "/l/office/conf", {"csrf": tok, "fmt": "mikrotik"})
    assert st == 200 and "/interface wireguard add" in t
    wait_log(panel, "office")


def test_location_networks_change_needs_code(panel):
    c, tok = logged_in(panel)
    c.req("POST", "/l/home", {"csrf": tok, "act": "save", "title": "Home", "networks": "192.168.1.0/24,10.9.0.0/24"})
    assert panel.hub.state()["locations"]["home"]["networks"] == ["192.168.1.0/24"]
    c.req("POST", "/l/home", {"csrf": tok, "act": "save", "title": "Home", "networks": "192.168.1.0/24,10.9.0.0/24",
                              "code": panel.code()})
    assert panel.hub.state()["locations"]["home"]["networks"] == ["192.168.1.0/24", "10.9.0.0/24"]


def test_location_conf_needs_code_later(panel):
    c, tok = logged_in(panel)
    st, _, t, _ = c.req("POST", "/l/home/conf", {"csrf": tok, "fmt": "wg"})
    assert "PrivateKey" not in t
    st, _, t, _ = c.req("POST", "/l/home/conf", {"csrf": tok, "fmt": "wg", "code": panel.code()})
    assert st == 200 and "PrivateKey" in t


def test_language_switch_keeps_session(panel):
    c, tok = logged_in(panel)
    st, *_ = c.req("POST", "/settings", {"csrf": tok, "act": "language", "language": "uk"})
    assert st == 303
    assert 'language = "uk"' in panel.hub.read("/etc/wgctl/config.toml")
    end = time.time() + 15
    while time.time() < end:
        try:
            st, _, t, _ = c.req("GET", "/settings")
            if st == 200 and "Налаштування" in t:
                break
        except OSError:
            pass
        time.sleep(0.3)
    else:
        raise AssertionError("panel did not come back in Ukrainian with the same session")


def test_location_reissue_and_delete_need_code(panel):
    c, tok = logged_in(panel)
    pub = panel.hub.state()["locations"]["home"]["pubkey"]
    c.req("POST", "/l/home", {"csrf": tok, "act": "reissue", "code": "000000"})
    assert panel.hub.state()["locations"]["home"]["pubkey"] == pub
    c.req("POST", "/l/home", {"csrf": tok, "act": "reissue", "code": panel.code()})
    assert panel.hub.state()["locations"]["home"]["pubkey"] != pub
    st, loc, *_ = c.req("POST", "/l/home", {"csrf": tok, "act": "rm", "code": panel.code()})
    assert "home" not in panel.hub.state()["locations"]


def test_login_is_password_and_code_only(panel):
    st, _, t, _ = Client(panel).req("GET", "/login")
    assert 'for="u"' not in t and 'name="password"' in t and 'name="code"' in t
    c = Client(panel)
    st, loc, _, _ = c.login()                      # no user field at all
    assert st == 303 and loc == "/" and c.cookie


def test_site_page_can_close_site_for_all_sites_key(panel):
    panel.hub.run("add", "mac", "--sites", "*", "--admin")
    c, tok = logged_in(panel)
    st, _, t, _ = c.req("GET", "/s/nas")
    assert 'value="mac" checked' in t and 'value="mac" checked disabled' not in t
    cand = re.search(r'name="cand" value="([^"]*)"', t).group(1)
    assert "mac" in cand.split(",")
    c.req("POST", "/s/nas", {"csrf": tok, "act": "access", "cand": cand, "who": ["phone"]})
    assert panel.hub.state()["clients"]["mac"]["except"] == ["nas"]
    assert panel.hub.state()["clients"]["phone"]["sites"] == ["nas"]


def test_roles_in_panel(panel):
    c, tok = logged_in(panel)
    st, loc, _, _ = c.req("POST", "/new", {"csrf": tok, "name": "pi_4b", "kind": "perm", "role": "server", "autorevoke": "1"})
    assert loc == "/c/pi_4b"
    cl = panel.hub.state()["clients"]["pi_4b"]
    assert (cl["role"], cl["ip"], cl["admin"]) == ("server", "10.77.0.20", False)
    _, _, t, _ = c.req("GET", "/c/pi_4b")
    assert "Role and name" in t and "10.77.0.20" in t
    _, _, t, _ = c.req("GET", "/?f=server")
    keys = t.split('<div class="keys">', 1)[1]
    assert 'href="/c/pi_4b"' in keys and 'href="/c/phone"' not in keys
    _, _, t, _ = c.req("GET", "/")
    assert "r-server" in t and "r-admin" in t, "device rings are coloured by role"
    c.req("POST", "/c/pi_4b", {"csrf": tok, "act": "role", "role": "client"})
    assert panel.hub.state()["clients"]["pi_4b"]["role"] == "client"
    _, _, t, _ = c.req("GET", "/c/pi_4b")
    assert "Move to the role" in t, "10.77.0.20 is outside the client range"
    c.req("POST", "/c/pi_4b", {"csrf": tok, "act": "move"})
    assert panel.hub.state()["clients"]["pi_4b"]["ip"] == "10.77.0.51"
    _, loc, _, _ = c.req("POST", "/c/pi_4b", {"csrf": tok, "act": "rename", "new": "Pi-Bot"})
    assert loc == "/c/pi-bot" and "pi-bot" in panel.hub.state()["clients"]
    c.req("POST", "/c/pi-bot", {"csrf": tok, "act": "role", "role": "admin"})
    assert panel.hub.state()["clients"]["pi-bot"]["role"] == "client", "admin only through the code-protected button"


def test_underscore_key_on_site_and_log_pages(panel):
    panel.hub.run("add", "macbook_m2")
    c, tok = logged_in(panel)
    c.req("POST", "/s/nas", {"csrf": tok, "act": "access", "cand": "phone,macbook_m2", "who": ["phone", "macbook_m2"]})
    assert "nas" in panel.hub.state()["clients"]["macbook_m2"]["sites"]
    st, _, t, _ = c.req("GET", "/log?client=macbook_m2")
    assert st == 200 and "Traceback" not in t


def test_admin_ssh_service_page(panel):
    panel.hub.run("add", "pi", "--role", "server")
    panel.hub.run("add", "guest1")
    panel.hub.run("set", "pi", "--ssh", "on")
    c = Client(panel)
    c.login()
    st, _, body, _ = c.req("GET", "/t/pi-ssh")
    assert st == 200
    assert "All keys with the admin role have access automatically" in body
    assert '<input type="checkbox" checked disabled><span>phone (admin)' in body
    assert 'name="cand" value="pi,guest1"' in body or 'name="cand" value="guest1,pi"' in body
