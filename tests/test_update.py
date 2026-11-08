"""wgctl-update: release check and download validation (with a fake curl, nothing leaves the machine)."""
import io
import os
import subprocess
import tarfile

from conftest import REPO

UPDATE = REPO / "src" / "wgctl-update"

FAKE_CURL = r"""#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift ;; -H|--proto|--max-time) shift ;; -*) ;; *) url="$1" ;; esac
  shift
done
case "$url" in
  https://api.github.com/repos/*/releases/latest) printf '{"tag_name": "%s"}' "$FAKE_TAG" ;;
  https://github.com/*/archive/refs/tags/*.tar.gz) cp "$FAKE_TARBALL" "$out" ;;
  *) echo "unexpected url $url" >&2; exit 22 ;;
esac
"""


def setup(tmp_path, installed="1.0.0", tag="v1.1.0", released=None):
    root = tmp_path / "root"
    (root / "usr/local/sbin").mkdir(parents=True)
    (root / "etc/wgctl").mkdir(parents=True)
    (root / "etc/wgctl/config.toml").write_text('[update]\nrepo = "someone/wgctl-hub"\n')
    (root / "usr/local/sbin/wgctl").write_text(f'VERSION = "{installed}"\n')
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "curl").write_text(FAKE_CURL)
    (bin_ / "curl").chmod(0o755)
    tb = tmp_path / "release.tar.gz"
    with tarfile.open(tb, "w:gz") as t:
        for name, text in {"install.sh": "#!/bin/sh\nexit 0\n",
                           "src/wgctl": f'VERSION = "{released or tag.lstrip("v")}"\n',
                           "src/vpnadmin": 'VERSION = "x"\n',
                           "CHANGELOG.md": "# Changelog\n\n## 1.1.0\n\n- shiny\n\n## 1.0.0\n\n- first\n"}.items():
            data = text.encode()
            ti = tarfile.TarInfo(f"wgctl-hub-{tag}/{name}")
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    env = dict(os.environ, WGCTL_ROOT=str(root), PATH=f"{bin_}:{os.environ['PATH']}",
               FAKE_TAG=tag, FAKE_TARBALL=str(tb))
    return env


def run(env, *args, input="n\n"):
    return subprocess.run(["bash", str(UPDATE), *args], env=env, input=input, capture_output=True, text=True, timeout=60)


def test_check_reports_newer_release(tmp_path):
    r = run(setup(tmp_path), "--check")
    assert r.returncode == 10 and "1.0.0 -> 1.1.0" in r.stdout


def test_check_up_to_date(tmp_path):
    r = run(setup(tmp_path, installed="1.1.0"), "--check")
    assert r.returncode == 0 and "Up to date" in r.stdout


def test_update_shows_changes_and_can_be_declined(tmp_path):
    r = run(setup(tmp_path))
    assert "shiny" in r.stdout and "first" not in r.stdout, "only changes newer than the installed version"
    assert "Nothing changed" in r.stdout and r.returncode == 1


def test_release_with_wrong_version_is_refused(tmp_path):
    r = run(setup(tmp_path, released="6.6.6"))
    assert r.returncode != 0 and "contains version" in r.stderr


def test_bad_tag_and_repo_are_refused(tmp_path):
    assert run(setup(tmp_path, tag="v1;rm -rf /")).returncode != 0
    env = setup(tmp_path / "b")
    (tmp_path / "b/root/etc/wgctl/config.toml").write_text('[update]\nrepo = "x/../../evil y"\n')
    assert run(env, "--check").returncode != 0


def test_server_page_mentions_new_release(hub_en):
    import json
    hub_en.env["WGCTL_FAKE_RELEASE"] = "9.9.9"
    info = json.loads(hub_en.run("server", "--json").stdout)
    assert info["release"] == "9.9.9"
    assert any(i["key"] == "release:9.9.9" and i["level"] == "info" and "wgctl-update" in i["text"] for i in info["issues"])
