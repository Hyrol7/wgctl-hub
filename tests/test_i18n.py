"""The English catalog covers every template with the same placeholders."""
import json
import subprocess
import sys

from conftest import REPO


def test_catalog_complete():
    r = subprocess.run([sys.executable, str(REPO / "tools/i18n.py"), "check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_catalog_is_valid_json_and_no_cyrillic():
    cat = json.loads((REPO / "share/i18n/en.json").read_text())
    import re
    bad = [v for v in cat.values() if re.search("[А-Яа-яІіЇїЄєҐґ]", v)]
    assert not bad, bad[:3]
