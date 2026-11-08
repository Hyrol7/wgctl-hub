"""Signal routing: the group gets everything, admins privately only critical events."""
import json

GROUP = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo="
ADMINS = ["+15551230001", "+15551230002"]


def sent(hub):
    hub.run("notify", "flush")              # most commands only queue; the monitor sends every minute
    out = []
    path = hub.root / "signal.jsonl"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        a = json.loads(line)
        if "send" in a:
            to = "group" if "-g" in a else a[-1]
            out.append((to, a[a.index("-m") + 1], a[a.index("--text-style") + 1] if "--text-style" in a else ""))
    return out


def setup_notify(hub, group=True):
    hub.run("notify", "set", "--sender", "+15550001111", "--admins", ",".join(ADMINS))
    if group:
        hub.run("notify", "set", f"--group={GROUP}", "--group-name", "VPN")
    (hub.root / "signal.jsonl").write_text("")


def test_info_goes_to_group_only(hub_en):
    setup_notify(hub_en)
    hub_en.run("add", "phone")
    msgs = sent(hub_en)
    assert [m[0] for m in msgs] == ["group"]
    assert "🔑" in msgs[0][1] and "phone" in msgs[0][1]


def test_critical_goes_to_group_and_admins(hub_en):
    hub_en.run("add", "phone")
    setup_notify(hub_en)
    hub_en.run("disable", "phone", "--reason", "suspicious")
    to = sorted(m[0] for m in sent(hub_en))
    assert to == sorted(ADMINS + ["group"])
    assert all("🚨" in m[1] for m in sent(hub_en))


def test_without_group_everything_goes_to_admins(hub_en):
    setup_notify(hub_en, group=False)
    hub_en.run("add", "phone")
    assert sorted(m[0] for m in sent(hub_en)) == sorted(ADMINS)


def test_header_is_bold_and_utf16_length_is_right(hub_en):
    setup_notify(hub_en)
    hub_en.run("add", "phone")
    to, text, style = sent(hub_en)[0]
    start, length, kind = style.split(":")
    head = text.split("\n", 1)[0]
    assert kind == "BOLD" and int(length) == len(head.encode("utf-16-le")) // 2


def test_panel_event_levels(hub_en):
    setup_notify(hub_en)
    hub_en.run("event", "--cat", "security", "--level", "warning", "--icon", "🔓", "--", "Panel sign-in from 10.77.0.10")
    assert [m[0] for m in sent(hub_en)] == ["group"]
    hub_en.run("event", "--cat", "security", "--level", "critical", "--", "Sign-in blocked")
    assert len(sent(hub_en)) == 1 + 1 + len(ADMINS)


def test_daily_report_to_group(hub_en):
    setup_notify(hub_en)
    hub_en.run("report")
    msgs = sent(hub_en)
    assert [m[0] for m in msgs] == ["group"] and msgs[0][1].startswith("📊")
