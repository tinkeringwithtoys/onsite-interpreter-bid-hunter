#!/usr/bin/env python3
"""
.env loader + validator.  Zero dependencies.

Why this exists instead of `pip install python-dotenv`:

python-dotenv would have loaded your env.txt WITHOUT COMPLAINING, and you would
have shipped a broken pipeline. The file contains this line:

    SMTP_FROM=your-address@gmail.comALERT_EMAIL=aladinsliti@gmail.com

Two variables welded onto one line. A permissive parser reads that as
SMTP_FROM="your-address@gmail.comALERT_EMAIL=aladinsliti@gmail.com" and leaves
ALERT_EMAIL completely undefined. The result is an emailer that authenticates
fine, reports success, and sends to nobody.

So this parser is deliberately suspicious. It looks for the exact shapes that
break silently, and it refuses to guess.

Usage:
    python3 envfile.py --check env.txt          # validate, values masked
    python3 envfile.py --self-test
"""

import argparse
import os
import re
import sys

REQUIRED = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "ALERT_EMAIL",
    "AGNES_API_KEY",
]

OPTIONAL = [
    "AGNES_ENDPOINT",
    "AGNES_MODEL",
    "TUNEPS_USER",
    "TUNEPS_PASSWORD",
]

# Variables that should NOT be here at all.
UNNECESSARY = {
    "GITHUB_TOKEN": (
        "Not needed. Actions injects GITHUB_TOKEN automatically and "
        "`permissions: contents: write` is enough to commit state. "
        "A personal access token here is pure extra risk."
    ),
    "GH_TOKEN": "Same as GITHUB_TOKEN - not needed.",
    "GITHUB_PAT": "Same as GITHUB_TOKEN - not needed.",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# A value that still contains 'KEY=' means two assignments collided on one line.
WELDED_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")

PLACEHOLDERS = {
    "your-address@gmail.com",
    "your-email@example.com",
    "changeme",
    "xxx",
    "",
}


def mask(value):
    """Never print a secret in full - not to a terminal, not to a CI log."""
    if value is None:
        return "(unset)"
    v = str(value)
    if len(v) <= 4:
        return "*" * len(v)
    return v[:4] + "*" * min(len(v) - 4, 20)


def parse(text):
    """
    Returns (values, problems).
    Pure function, no I/O, so it is directly testable.
    """
    values, problems = {}, []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            problems.append((lineno, "no '=' on this line", raw[:60]))
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not KEY_RE.match(key):
            problems.append((lineno, f"'{key}' is not a valid variable name", raw[:60]))
            continue

        # THE BUG THAT BROKE YOUR FILE.
        if WELDED_RE.search(value):
            second = WELDED_RE.search(value).group(0).rstrip("=")
            problems.append(
                (
                    lineno,
                    f"TWO VARIABLES ON ONE LINE - '{key}' has swallowed '{second}'. "
                    f"Put '{second}' on its own line.",
                    raw[:60],
                )
            )
            continue

        if key in values:
            problems.append((lineno, f"'{key}' defined more than once", raw[:60]))

        values[key] = value

    return values, problems


def validate(values):
    """Semantic checks. Returns (errors, warnings)."""
    errors, warnings = [], []

    for key in REQUIRED:
        if key not in values:
            errors.append(f"{key} is missing")
        elif values[key].lower() in PLACEHOLDERS:
            errors.append(f"{key} is still a placeholder ({values[key]!r})")

    for key in ("SMTP_FROM", "ALERT_EMAIL", "SMTP_USER"):
        v = values.get(key)
        if v and v.lower() not in PLACEHOLDERS and not EMAIL_RE.match(v):
            errors.append(f"{key}={v!r} is not a valid email address")

    port = values.get("SMTP_PORT")
    if port:
        if not port.isdigit():
            errors.append(f"SMTP_PORT={port!r} is not a number")
        elif int(port) not in (25, 465, 587, 2525):
            warnings.append(f"SMTP_PORT={port} is unusual (expected 587 or 465)")

    # Gmail-specific, and a very common silent failure.
    host = (values.get("SMTP_HOST") or "").lower()
    user = values.get("SMTP_USER", "")
    frm = values.get("SMTP_FROM", "")
    if "gmail" in host and user and frm and user != frm:
        errors.append(
            f"Gmail requires SMTP_FROM to equal SMTP_USER. "
            f"You have SMTP_USER={user} but SMTP_FROM={frm}. "
            f"Gmail will either rewrite the header or reject the send."
        )

    pwd = values.get("SMTP_PASSWORD", "")
    if "gmail" in host and pwd:
        stripped = pwd.replace(" ", "")
        if len(stripped) != 16:
            warnings.append(
                f"Gmail app passwords are 16 characters; yours is {len(stripped)}. "
                f"If sending fails with 535, regenerate it."
            )

    for key, why in UNNECESSARY.items():
        if key in values:
            warnings.append(f"{key} present but unnecessary. {why}")

    known = set(REQUIRED) | set(OPTIONAL) | set(UNNECESSARY)
    for key in values:
        if key not in known:
            warnings.append(f"{key} is not a variable this project reads - typo?")

    return errors, warnings


def load_into_environ(path=".env", override=False):
    """Load a .env file into os.environ. Raises on parse problems."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        values, problems = parse(fh.read())
    if problems:
        lines = "\n".join(f"  line {n}: {msg}" for n, msg, _ in problems)
        raise ValueError(f"{path} is malformed:\n{lines}")
    for k, v in values.items():
        if override or k not in os.environ:
            os.environ[k] = v
    return values


def report(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    values, problems = parse(text)
    errors, warnings = validate(values)

    print(f"Checking {path}\n" + "=" * 64)

    print("\nPARSED (values masked):")
    for key in REQUIRED + OPTIONAL:
        if key in values:
            shown = values[key] if key in ("SMTP_HOST", "SMTP_PORT") else mask(values[key])
            print(f"  {key:<18} = {shown}")
    for key in values:
        if key not in REQUIRED and key not in OPTIONAL:
            print(f"  {key:<18} = {mask(values[key])}   <- unexpected")

    if problems:
        print("\nPARSE PROBLEMS:")
        for n, msg, snippet in problems:
            print(f"  x line {n}: {msg}")

    if errors:
        print("\nERRORS (must fix - the pipeline cannot work):")
        for e in errors:
            print(f"  x {e}")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")

    ok = not problems and not errors
    print("\n" + "=" * 64)
    print("RESULT:", "USABLE" if ok else "NOT USABLE YET")
    return 0 if ok else 1


def self_test():
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r} want {want!r}")

    # 1. The exact welded-line bug from env.txt must be caught.
    v, p = parse("SMTP_FROM=your-address@gmail.comALERT_EMAIL=alad@gmail.com")
    check("welded detected", len(p), 1)
    check("welded not stored", "SMTP_FROM" in v, False)

    # 2. Clean two-line version must parse fine.
    v, p = parse("SMTP_FROM=a@b.com\nALERT_EMAIL=c@d.com")
    check("clean parses", p, [])
    check("clean count", len(v), 2)

    # 3. Comments and blanks ignored.
    v, p = parse("# note\n\nA=1\n")
    check("comments ignored", v, {"A": "1"})

    # 4. Quotes stripped.
    v, _ = parse('A="hello"')
    check("quotes stripped", v["A"], "hello")

    # 5. Gmail FROM/USER mismatch is an ERROR, not a warning.
    e, w = validate({
        "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
        "SMTP_USER": "a@gmail.com", "SMTP_PASSWORD": "x" * 16,
        "SMTP_FROM": "b@gmail.com", "ALERT_EMAIL": "c@gmail.com",
        "AGNES_API_KEY": "sk-test",
    })
    check("gmail mismatch is error", any("equal SMTP_USER" in x for x in e), True)

    # 6. Matching FROM/USER produces no errors.
    e, w = validate({
        "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
        "SMTP_USER": "a@gmail.com", "SMTP_PASSWORD": "x" * 16,
        "SMTP_FROM": "a@gmail.com", "ALERT_EMAIL": "c@gmail.com",
        "AGNES_API_KEY": "sk-test",
    })
    check("matching ok", e, [])

    # 7. Placeholder FROM is an error.
    e, _ = validate({
        "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
        "SMTP_USER": "a@gmail.com", "SMTP_PASSWORD": "x" * 16,
        "SMTP_FROM": "your-address@gmail.com", "ALERT_EMAIL": "c@gmail.com",
        "AGNES_API_KEY": "sk-test",
    })
    check("placeholder caught", any("placeholder" in x for x in e), True)

    # 8. A stray PAT is flagged as unnecessary.
    _, w = validate({
        "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
        "SMTP_USER": "a@gmail.com", "SMTP_PASSWORD": "x" * 16,
        "SMTP_FROM": "a@gmail.com", "ALERT_EMAIL": "c@gmail.com",
        "AGNES_API_KEY": "sk-test", "GITHUB_TOKEN": "ghp_x",
    })
    check("PAT flagged", any("GITHUB_TOKEN" in x for x in w), True)

    # 9. Bogus key name rejected.
    _, p = parse("appname=SMTP_PASSWORD")
    check("bogus var accepted as name", len(p), 0)   # valid name, flagged later as unknown

    # 10. Secrets never printed in full.
    check("mask short", mask("abc"), "***")
    check("mask long", mask("ghp_ABCDEFGHIJ")[:4], "ghp_")
    check("mask hides tail", "IJ" in mask("ghp_ABCDEFGHIJ"), False)

    if fails:
        print("SELF-TEST FAILED")
        for f in fails:
            print("  x " + f)
        return 1
    print("SELF-TEST PASSED  (10/10 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="PATH")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.check:
        return report(args.check)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
