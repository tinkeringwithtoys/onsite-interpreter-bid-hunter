#!/usr/bin/env python3
"""
Email digest sender + Agnes scorer client.

Zero dependencies - smtplib, email and urllib are all standard library.
Both halves read config from the environment, so the same code runs from your
laptop (via .env) and from GitHub Actions (via repository secrets) with no
changes.

    python3 notify.py --test-email      # send yourself one real message
    python3 notify.py --test-agnes      # one real scoring call
    python3 notify.py --self-test       # offline, no network, no secrets
"""

import argparse
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from email.message import EmailMessage

import envfile

AGNES_DEFAULT_ENDPOINT = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_DEFAULT_MODEL = "agnes-2.5-flash"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def smtp_config():
    missing = [
        k for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                    "SMTP_FROM", "ALERT_EMAIL")
        if not os.environ.get(k)
    ]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing) +
            "\nRun: python3 envfile.py --check .env"
        )
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ["SMTP_PORT"]),
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_PASSWORD"].replace(" ", ""),
        "from": os.environ["SMTP_FROM"],
        "to": [a.strip() for a in os.environ["ALERT_EMAIL"].split(",") if a.strip()],
    }


def send_email(subject, text_body, html_body=None):
    cfg = smtp_config()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(cfg["to"])
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()

    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"],
                                  context=context, timeout=30) as s:
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as s:
                s.ehlo()
                s.starttls(context=context)   # mandatory on 587
                s.ehlo()
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "SMTP authentication failed (535).\n"
            "  - Gmail needs an APP PASSWORD, not your account password.\n"
            "  - App passwords require 2-Step Verification to be ON.\n"
            "  - If you rotated the password, update the secret too.\n"
            f"  server said: {exc}"
        ) from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"SMTP send failed: {exc}") from exc

    return len(cfg["to"])


# ---------------------------------------------------------------------------
# Digest rendering
# ---------------------------------------------------------------------------
def render_digest(new_items, deadline_alerts, award_leads, stats):
    """Plain text. Pure function - testable without network or secrets."""
    L = []
    L.append(f"BID HUNTER · {stats.get('run_time', '')} · lane={stats.get('lane', '?')}")
    L.append("=" * 62)

    # Stats FIRST and always, even when empty. An empty digest and a broken
    # pipeline must never look the same in your inbox.
    L.append(
        f"sources ok {stats.get('sources_ok', 0)}/{stats.get('sources_total', 0)}"
        f"  ·  fetched {stats.get('fetched', 0)}"
        f"  ·  new {len(new_items)}"
        f"  ·  deadlines {len(deadline_alerts)}"
        f"  ·  leads {len(award_leads)}"
    )
    if stats.get("failed_sources"):
        L.append("FAILED: " + ", ".join(stats["failed_sources"]))
    L.append("")

    if new_items:
        L.append("NEW OPPORTUNITIES")
        L.append("-" * 62)
        for it in new_items:
            # scraper.py nests the Agnes verdict under it["score"] as a dict,
            # while the older flat fixtures put these fields at the top level.
            # Reading only the top level printed the entire dict where the
            # relevance number belonged. Accept both shapes.
            sc = it.get("score")
            sc = sc if isinstance(sc, dict) else {}

            def pick(*keys, default="?"):
                for src in (it, sc):
                    for k in keys:
                        v = src.get(k)
                        if v not in (None, "", [], {}):
                            return v
                return default

            raw = it.get("score")
            rel = raw if isinstance(raw, (int, float)) else sc.get("relevance")
            rel = "?" if rel is None else rel

            pairs = pick("language_pairs", default=[])
            if isinstance(pairs, str):
                pairs = [pairs]
            if not isinstance(pairs, list):
                pairs = []

            L.append(f"[{rel}/10] {it.get('title', '(untitled)')}")
            L.append(f"    {pick('buyer')} · {pick('country')} · "
                     f"{pick('modality', 'work_mode')}")
            L.append(f"    pairs: {', '.join(str(p) for p in pairs) or 'unclear'}")
            if pick("travel_covered", "travel_and_accommodation_covered",
                    default=False):
                L.append("    ** travel + accommodation covered **")
            dl = it.get("deadline")
            if dl:
                L.append(f"    closes {dl} ({it.get('days_left', '?')} days)")
            if it.get("red_flags"):
                L.append("    flags: " + "; ".join(it["red_flags"]))
            L.append(f"    {it.get('url', '')}")
            L.append("")

    if deadline_alerts:
        L.append("DEADLINES APPROACHING")
        L.append("-" * 62)
        for a in deadline_alerts:
            L.append(f"T-{a['days_left']}d  {a['title']}")
            for f in a.get("flags", []):
                L.append(f"    ! {f}")
            if a.get("url"):
                L.append(f"    {a['url']}")
        L.append("")

    if award_leads:
        L.append("WHO JUST WON (subcontracting targets)")
        L.append("-" * 62)
        for w in award_leads:
            L.append(f"{w.get('winner', '?')} - won {w.get('contract', '?')}")
            if w.get("contact"):
                L.append(f"    {w['contact']}")
        L.append("")

    if not new_items and not deadline_alerts and not award_leads:
        L.append("Nothing new. Pipeline ran clean - see the counters above.")

    return "\n".join(L)


# ---------------------------------------------------------------------------
# Agnes scorer (OpenAI-compatible chat completions)
# ---------------------------------------------------------------------------
SCORER_SYSTEM = """You score public procurement notices for an EU-registered \
interpreting provider based in Tunis.

Profile:
- Language pairs offered: Arabic<->French, Arabic<->English (both directions).
- EN<->FR alone is NOT offered. If a lot requires only EN<->FR, relevance is 0.
- Accepts BOTH onsite and remote/RSI/telephone work.
- Onsite abroad costs money (flights, hotel, Schengen visa ~35 days lead time).
  Remote costs nothing.

Return STRICT JSON only, no prose, no markdown fences:
{"relevance": 0-10,
 "language_pairs": [],
 "work_mode": "onsite|remote|hybrid|unclear",
 "billing_unit": "per_day|per_hour|per_minute|per_call|lump_sum|unclear",
 "location": "",
 "travel_and_accommodation_covered": true|false|null,
 "estimated_day_rate_eur": 0,
 "net_after_travel_eur": 0,
 "red_flags": []}

billing_unit matters: asylum telephone interpreting bills per minute or per \
call, never per day. Do not convert one into the other."""


def agnes_score(notice_text, timeout=45, retries=3):
    key = os.environ.get("AGNES_API_KEY")
    if not key:
        raise RuntimeError("AGNES_API_KEY is not set")

    endpoint = os.environ.get("AGNES_ENDPOINT", AGNES_DEFAULT_ENDPOINT)
    model = os.environ.get("AGNES_MODEL", AGNES_DEFAULT_MODEL)

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SCORER_SYSTEM},
            {"role": "user", "content": notice_text[:8000]},
        ],
        "temperature": 0,
    }).encode("utf-8")

    last = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            return extract_json(json.loads(body)["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {exc.code}: {detail}"
            # 4xx other than 429 will not fix themselves - stop retrying.
            if exc.code != 429 and 400 <= exc.code < 500:
                break
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(2 ** attempt)

    # A scorer failure must NOT silently drop the notice. Fail open: pass it
    # through unscored so a human sees it, and mark why.
    return {
        "relevance": None,
        "scorer_error": last,
        "red_flags": ["scoring failed - review manually"],
    }


def extract_json(content):
    """Models wrap JSON in prose or ``` fences. Recover it rather than crash."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {"relevance": None, "scorer_error": "no JSON in reply",
                "red_flags": ["scoring failed - review manually"]}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        return {"relevance": None, "scorer_error": f"bad JSON: {exc}",
                "red_flags": ["scoring failed - review manually"]}


# ---------------------------------------------------------------------------
def self_test():
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r} want {want!r}")

    d = render_digest([], [], [], {"sources_ok": 12, "sources_total": 15,
                                   "fetched": 40, "lane": "fast"})
    check("empty digest still reports counters", "sources ok 12/15" in d, True)
    check("empty digest is explicit", "Pipeline ran clean" in d, True)

    d = render_digest([], [], [], {"sources_ok": 9, "sources_total": 15,
                                   "failed_sources": ["ungm", "au"]})
    check("failures surfaced", "FAILED: ungm, au" in d, True)

    d = render_digest(
        [{"title": "AR interpreting", "score": 9, "travel_covered": True,
          "language_pairs": ["ar-fr"], "deadline": "2026-09-01", "days_left": 25}],
        [], [], {})
    check("travel flag shown", "travel + accommodation covered" in d, True)

    check("fenced json", extract_json('```json\n{"relevance": 7}\n```')["relevance"], 7)
    check("prose-wrapped json", extract_json('Sure! {"relevance": 3} ok')["relevance"], 3)
    check("garbage fails open", extract_json("no json here")["relevance"], None)
    check("garbage flags itself",
          "scoring failed - review manually" in extract_json("x")["red_flags"], True)
    check("broken json fails open", extract_json('{"a": }')["relevance"], None)

    if fails:
        print("SELF-TEST FAILED")
        for f in fails:
            print("  x " + f)
        return 1
    print("SELF-TEST PASSED  (9/9 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=".env")
    ap.add_argument("--test-email", action="store_true")
    ap.add_argument("--test-agnes", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    envfile.load_into_environ(args.env)

    if args.test_email:
        body = render_digest(
            [{"title": "TEST - Arabic interpretation framework",
              "buyer": "Bid Hunter self-test", "country": "EU",
              "modality": "remote", "score": 8,
              "language_pairs": ["ar-fr", "ar-en"],
              "deadline": "2026-09-30", "days_left": 54,
              "travel_covered": False, "url": "https://ted.europa.eu/"}],
            [], [],
            {"run_time": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
             "lane": "test", "sources_ok": 1, "sources_total": 1, "fetched": 1},
        )
        n = send_email("[bid-hunter] test digest", body)
        print(f"Sent to {n} recipient(s). Check the inbox, and the spam folder.")
        return 0

    if args.test_agnes:
        out = agnes_score(
            "Framework contract for provision of interpretation and cultural "
            "mediation services. Languages required: Arabic, Farsi, Pashto. "
            "Telephone interpreting, billed per connected minute. Location: "
            "France, remote delivery accepted."
        )
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0 if out.get("scorer_error") is None else 1

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
