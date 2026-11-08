#!/usr/bin/env python3
"""Translation tool (for developers).

The source language of wgctl and vpnadmin is Ukrainian: every user-facing string is a template in T("...").

  tools/i18n.py wrap FILE...      wrap Ukrainian strings into T("template", args) (done once)
  tools/i18n.py extract           collect all T("...") templates from src/ and update share/i18n/en.json
                                  (new strings are added with an empty translation, unused ones removed)
  tools/i18n.py check             check that every template has a translation with the same placeholders

Templates use str.format: {0}, {1:.1f}; literal braces are doubled.
To add a language: copy en.json to <code>.json and translate the values; it appears in the language list.
"""
import ast
import json
import re
import string
import sys
from pathlib import Path

CY = re.compile("[А-Яа-яІіЇїЄєҐґ]")
ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "share" / "i18n" / "en.json"


def esc(t):
    return t.replace("{", "{{").replace("}", "}}")


def lit(t):
    return json.dumps(t, ensure_ascii=False)


def wrap(path):
    src = Path(path).read_text()
    b = src.encode()
    tree = ast.parse(src)
    starts = [0]
    for line in b.split(b"\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)

    def off(line, col):
        return starts[line - 1] + col

    docs, inner, skip = set(), set(), set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            docs.add(id(n.body[0].value))
        if isinstance(n, ast.JoinedStr):
            for v in n.values:
                if isinstance(v, ast.Constant):
                    inner.add(id(v))
                elif isinstance(v, ast.FormattedValue) and v.format_spec is not None:
                    for x in ast.walk(v.format_spec):
                        skip.add(id(x))
        if isinstance(n, ast.Compare):               # input synonyms: ("так", "yes") stay as they are
            for c in [n.left] + n.comparators:
                if isinstance(c, (ast.Tuple, ast.List, ast.Set)):
                    for x in c.elts:
                        skip.add(id(x))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "T":
            for x in ast.walk(n):
                skip.add(id(x))

    def qualifies(n):
        if id(n) in skip or id(n) in docs:
            return False
        if isinstance(n, ast.JoinedStr):
            return any(isinstance(v, ast.Constant) and CY.search(v.value) for v in n.values)
        return isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in inner and bool(CY.search(n.value))

    cands = [(off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset), n)
             for n in ast.walk(tree) if qualifies(n)]

    def sub(a, z):
        inside = sorted([c for c in cands if a <= c[0] and c[1] <= z and (c[0], c[1]) != (a, z)], key=lambda c: (c[0], -c[1]))
        top, last_end = [], -1
        for c in inside:
            if c[0] >= last_end:
                top.append(c)
                last_end = c[1]
        out, pos = [], a
        for s0, s1, n in top:
            out.append(b[pos:s0].decode())
            out.append(build(n))
            pos = s1
        out.append(b[pos:z].decode())
        return "".join(out)

    def build(n):
        if isinstance(n, ast.Constant):
            return f"T({lit(esc(n.value))})"
        tpl, args = [], []
        for v in n.values:
            if isinstance(v, ast.Constant):
                tpl.append(esc(v.value))
                continue
            i = len(args)
            conv = {-1: "", 115: "!s", 114: "!r", 97: "!a"}[v.conversion]
            spec = ""
            if v.format_spec is not None:
                spec = ":" + "".join(x.value if isinstance(x, ast.Constant) else "" for x in v.format_spec.values)
            tpl.append("{" + str(i) + conv + spec + "}")
            e = v.value
            args.append(sub(off(e.lineno, e.col_offset), off(e.end_lineno, e.end_col_offset)))
        return "T(" + ", ".join([lit("".join(tpl))] + args) + ")"

    new = sub(0, len(b))
    ast.parse(new)
    Path(path).write_text(new)
    print(f"{path}: wrapped {len(cands)} strings")


def templates():
    out = {}
    for p in (ROOT / "src" / "wgctl", ROOT / "src" / "vpnadmin"):
        tree = ast.parse(p.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "T" and n.args \
                    and isinstance(n.args[0], ast.Constant):
                out.setdefault(n.args[0].value, p.name)
    return out


def fields(t):
    return sorted((f or "") + (c and "!" + c or "") + ":" + (s or "")
                  for _, f, s, c in string.Formatter().parse(t) if f is not None)


def extract():
    cat = json.loads(CATALOG.read_text()) if CATALOG.exists() else {}
    tpls = templates()
    new = {k: cat.get(k, "") for k in sorted(tpls)}
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(new)} templates, untranslated: {sum(1 for v in new.values() if not v)}, removed: {len(set(cat) - set(new))}")


def check():
    cat = json.loads(CATALOG.read_text())
    bad = 0
    for k in templates():
        v = cat.get(k)
        if not v:
            print("no translation:", k[:80])
            bad += 1
        elif fields(k) != fields(v):
            print("different placeholders:", k[:80], "->", v[:80])
            bad += 1
        else:
            try:
                v.format(*range(20)) if not any(":" in f and f.split(":")[1] for f in fields(v)) else None
            except (IndexError, KeyError, ValueError) as ex:
                print("format error:", v[:80], ex)
                bad += 1
    print("OK" if not bad else f"problems: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "wrap":
        for f in sys.argv[2:]:
            wrap(f)
    elif cmd == "extract":
        extract()
    elif cmd == "check":
        check()
    else:
        print(__doc__)
