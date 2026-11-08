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
    st, *_ = Client(panel).req("POST", "/login", {"user": "адмін", "password": "x", "code": "1"})
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
    for p in ("/", "/?f=online", "/sites", "/s/nas", "/c/phone", "/new", "/log", "/log?cat=security",
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
