#!/usr/bin/env python3
"""
Source validator for onsite-interpreter-bid-hunter.

RUN THIS FIRST, before writing any scraper.

It answers the three questions that decide the whole architecture:
  1. Which sources respond at all?
  2. Which ones need a browser vs. plain HTTP?
  3. Which ones BLOCK GitHub Actions' datacenter IPs?

Usage:
    python3 validate_sources.py                 # run from your laptop
    python3 validate_sources.py --json report.json

Zero dependencies - standard library only. Works on any Python 3.8+.

Run it twice:
  (a) on your laptop in Tunis   -> baseline, proves the source works
  (b) inside GitHub Actions     -> proves the source works FROM A RUNNER
Any source that passes (a) but fails (b) is IP-blocked, and no amount of
code will fix it. That is the single most important thing to learn early.
"""

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

TIMEOUT = 30

# ---------------------------------------------------------------------------
# TED expert-query candidates.
# TED v3 field names come from the eForms SDK and are easy to get wrong.
# We try several syntaxes and report which one the server accepts, instead
# of guessing and hard-coding a broken query.
# ---------------------------------------------------------------------------
TED_URL = "https://api.ted.europa.eu/v3/notices/search"

TED_QUERY_CANDIDATES = [
    "classification-cpv IN (79540000 79530000)",
    "classification-cpv IN (79540000)",
    "classification-cpv=79540000",
    "CPV=79540000",
    "notice-title ~ (interpretation)",
]

# ---------------------------------------------------------------------------
# Arabic-pivot query candidates.
# CPV 79540000 alone returns every interpretation tender in Europe, most of
# which do not need Arabic. These probe whether TED can filter on the LANGUAGE
# inside the notice text, which is what actually makes the feed useful for an
# AR<>FR / AR<>EN provider.
#
# Note the vocabulary split: the asylum/migration market says "cultural
# mediation" and (in French) "interpretariat", while the conference market says
# "interpretation". A CPV-only query catches both; a keyword-only query built
# from conference vocabulary silently misses the largest Arabic buyer in Europe.
# ---------------------------------------------------------------------------
TED_ARABIC_CANDIDATES = [
    "notice-title ~ (arabic)",
    "notice-title ~ (arabe)",
    "description-lot ~ (arabic)",
    "full-text ~ (arabic)",
    "notice-title ~ (cultural mediation)",
    "notice-title ~ (interpretariat)",
]

# Award/result notices are a SEPARATE stream with a different purpose: the
# winners of a 4-year Arabic interpreting framework are companies that now need
# Arabic interpreters. Probe whether notice kind is filterable.
TED_AWARD_CANDIDATES = [
    "notice-type IN (can-standard)",
    "notice-kind=result",
    "notice-type=can-standard",
]

TED_DATE_CANDIDATES = [
    "publication-date>=today(-7)",
    "publication-date >= today(-7)",
    "publication-date>=20260101",
    "dispatch-date>=today(-7)",
]

# ---------------------------------------------------------------------------
# Plain reachability probes.
# 'blocked' heuristics catch Cloudflare / WAF interstitials that return 200.
# ---------------------------------------------------------------------------
GET_TARGETS = [
    # --- P1_ASYLUM: the largest Arabic interpreting market in Europe ------
    # Tender-procured, lotted by language family, multiple winners in cascade.
    # Requires an EU-registered entity to bid - which you have.
    ("Frontex open tenders", "https://www.frontex.europa.eu/about-us/open-tenders/"),
    ("EUAA procurements", "https://www.euaa.europa.eu/procurements"),
    ("France PLACE (state platform)", "https://www.marches-publics.gouv.fr/"),
    ("France BOAMP", "https://www.boamp.fr/"),
    ("Germany service.bund.de", "https://www.service.bund.de/"),
    ("Germany eVergabe", "https://www.evergabe-online.de/"),
    ("EU Publications Office procurement", "https://op.europa.eu/en/web/public-procurement/"),
    # --- P1_UN: Arabic is 1 of 6 official UN languages -------------------
    ("UNGM public notices", "https://www.ungm.org/Public/Notice"),
    ("UNDP procurement notices", "https://procurement-notices.undp.org/"),
    ("UN interpreter exams (CELP)", "https://www.un.org/dgacm/en/content/exams-interpreters"),
    # --- P1_AFRICA: Arabic is an AU working language ---------------------
    ("African Union bids", "https://au.int/en/bids"),
    ("AfDB procurement", "https://www.afdb.org/en/projects-and-operations/procurement"),
    # --- DEMOTED: Arabic is NOT an EU official language ------------------
    # Kept only to detect a rare Arabic accreditation cycle. Do not build on it.
    ("EU interpreter accreditation", "https://europa.eu/interpretation/freelance_en.html"),
    ("EU ACI test calendar (PDF)", "https://europa.eu/interpretation/doc/aci_test_calendar.pdf"),
    # --- P2/P3: Europe volume -------------------------------------------
    ("EU Funding & Tenders portal", "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/home"),
    ("Portugal BASE", "https://www.base.gov.pt/Base4/en/"),
    ("UK GCA Language Services RM6302", "https://www.gca.gov.uk/agreements/RM6302"),
    # --- P3/P4: Gulf -----------------------------------------------------
    ("Saudi Etimad (visitor list)", "https://tenders.etimad.sa/Tender/AllTendersForVisitor?PageNumber=1"),
    ("Qatar Monaqasat", "https://monaqasat.mof.gov.qa/"),
    ("Kuwait CAPT", "https://capt.gov.kw/en/"),
    ("Bahrain Tender Board", "https://www.tenderboard.gov.bh/Tenders/PublicTenders/"),
    ("Oman Tender Board", "https://etendering.tenderboard.gov.om/product/publicDash"),
    ("Dubai eSupply", "https://esupply.dubai.gov.ae/"),
    # --- Tunisia ---------------------------------------------------------
    ("TUNEPS", "https://www.tuneps.tn/"),
    ("HAICOP Tunisia", "https://www.marchespublics.gov.tn/"),
]

BLOCK_MARKERS = (
    "just a moment",
    "checking your browser",
    "cf-browser-verification",
    "attention required",
    "access denied",
    "request unsuccessful",
    "captcha",
    "incapsula",
    "datadome",
)


def _ctx():
    c = ssl.create_default_context()
    return c


def http(url, method="GET", payload=None, headers=None):
    """Return (status, body_text, elapsed_ms, error)."""
    hdrs = {"User-Agent": UA, "Accept-Language": "en,fr;q=0.8,ar;q=0.6"}
    if headers:
        hdrs.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
        hdrs.setdefault("Accept", "application/json")

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx()) as r:
            body = r.read(200_000).decode("utf-8", "replace")
            return r.status, body, int((time.time() - t0) * 1000), None
    except urllib.error.HTTPError as e:
        body = e.read(20_000).decode("utf-8", "replace") if e.fp else ""
        return e.code, body, int((time.time() - t0) * 1000), None
    except Exception as e:
        return 0, "", int((time.time() - t0) * 1000), f"{type(e).__name__}: {e}"


def looks_blocked(body):
    low = body[:4000].lower()
    return any(m in low for m in BLOCK_MARKERS)


def verdict(status, body, err):
    if err:
        return "UNREACHABLE"
    if status == 0:
        return "UNREACHABLE"
    if looks_blocked(body):
        return "BLOCKED (WAF/bot-wall)"
    if status in (401, 403):
        return "FORBIDDEN (needs auth or IP-blocked)"
    if status == 429:
        return "RATE-LIMITED"
    if 200 <= status < 300:
        return "OK"
    if 300 <= status < 400:
        return "REDIRECT"
    return f"HTTP {status}"


def probe_ted():
    """Find a TED expert query the API actually accepts."""
    print("\n" + "=" * 74)
    print("TED Search API  (POST /v3/notices/search, no authentication)")
    print("=" * 74)

    results = {
        "cpv_syntax": [],
        "date_syntax": [],
        "arabic_syntax": [],
        "award_syntax": [],
        "working_query": None,
    }
    working_cpv = None

    for q in TED_QUERY_CANDIDATES:
        status, body, ms, err = http(
            TED_URL, "POST", {"query": q, "limit": 3, "page": 1}
        )
        ok = 200 <= status < 300
        total = None
        if ok:
            try:
                j = json.loads(body)
                total = j.get("totalNoticeCount") or j.get("total") or len(
                    j.get("notices", []) or j.get("results", [])
                )
            except Exception:
                pass
        mark = "PASS" if ok else "fail"
        print(f"  [{mark}] {status:>3}  {ms:>5}ms  hits={total}  {q}")
        if not ok and body:
            print(f"         -> {body[:220].strip()}")
        results["cpv_syntax"].append(
            {"query": q, "status": status, "ok": ok, "hits": total,
             "error": err, "body_head": body[:400]}
        )
        if ok and working_cpv is None:
            working_cpv = q

    if working_cpv:
        print(f"\n  Working CPV filter: {working_cpv}")
        print("  Now testing date syntax (needed for the 24h alert window):")
        for d in TED_DATE_CANDIDATES:
            q = f"{working_cpv} AND {d}"
            status, body, ms, err = http(
                TED_URL, "POST", {"query": q, "limit": 3, "page": 1}
            )
            ok = 200 <= status < 300
            print(f"  [{'PASS' if ok else 'fail'}] {status:>3}  {ms:>5}ms  {d}")
            if not ok and body:
                print(f"         -> {body[:220].strip()}")
            results["date_syntax"].append(
                {"fragment": d, "status": status, "ok": ok,
                 "body_head": body[:400]}
            )
            if ok and results["working_query"] is None:
                results["working_query"] = q
    else:
        print("\n  No CPV syntax accepted. Read the error bodies above -")
        print("  TED error messages normally name the valid field.")
        print("  Cross-check: https://api.ted.europa.eu/swagger-ui/index.html")

    if working_cpv:
        # CPV 79540000 alone returns EVERY interpretation tender in Europe.
        # Most need Spanish, Polish, Ukrainian - not Arabic. Narrowing on the
        # language is what turns a noisy feed into a useful one.
        print("\n  Testing ARABIC narrowing (this is what makes the feed usable):")
        for a in TED_ARABIC_CANDIDATES:
            q = f"{working_cpv} AND {a}"
            status, body, ms, err = http(
                TED_URL, "POST", {"query": q, "limit": 3, "page": 1}
            )
            ok = 200 <= status < 300
            total = None
            if ok:
                try:
                    j = json.loads(body)
                    total = j.get("totalNoticeCount") or j.get("total")
                except Exception:
                    pass
            print(
                f"  [{'PASS' if ok else 'fail'}] {status:>3}  {ms:>5}ms  "
                f"hits={total}  {a}"
            )
            if not ok and body:
                print(f"         -> {body[:220].strip()}")
            results["arabic_syntax"].append(
                {"fragment": a, "status": status, "ok": ok, "hits": total,
                 "body_head": body[:400]}
            )

        # Award notices are not missed deadlines. They name the companies that
        # just won a multi-year Arabic interpreting framework and now have to
        # staff it. Output of this stream is a contact list, not a bid.
        print("\n  Testing AWARD/RESULT filter (subcontracting-lead stream):")
        for w in TED_AWARD_CANDIDATES:
            q = f"{working_cpv} AND {w}"
            status, body, ms, err = http(
                TED_URL, "POST", {"query": q, "limit": 3, "page": 1}
            )
            ok = 200 <= status < 300
            print(f"  [{'PASS' if ok else 'fail'}] {status:>3}  {ms:>5}ms  {w}")
            if not ok and body:
                print(f"         -> {body[:220].strip()}")
            results["award_syntax"].append(
                {"fragment": w, "status": status, "ok": ok,
                 "body_head": body[:400]}
            )

    return results


def probe_gets():
    print("\n" + "=" * 74)
    print("Reachability probes")
    print("=" * 74)
    out = []
    for name, url in GET_TARGETS:
        status, body, ms, err = http(url)
        v = verdict(status, body, err)
        flag = "PASS" if v == "OK" else "WARN"
        print(f"  [{flag}] {v:<28} {ms:>6}ms  {name}")
        if err:
            print(f"         -> {err}")
        out.append({
            "name": name, "url": url, "status": status,
            "verdict": v, "ms": ms, "error": err,
            "bytes": len(body),
        })
    return out


def check_config(path="config.yaml"):
    """
    Static integrity checks on config.yaml. No network, runs in under a second.

    These exist because v4.0 shipped two SILENT failures that a reachability
    probe cannot catch by design:

      - eligibility.by_tier said P3_NATIONAL_TN while sources said
        P3_NATIONAL, so tuneps / base_gov_pt / home_state_national_portal
        resolved to no action label at all.
      - eu_funding_tenders_portal had poll:true and no endpoint, so the fast
        lane "polled" it every hour, fetched nothing, and went green.

    A green run that did nothing is the worst failure mode in this system,
    because in your inbox it is indistinguishable from "no new opportunities".
    """
    import yaml
    problems = []
    with open(path) as fh:
        cfg = yaml.safe_load(fh)

    sources = cfg.get("sources", []) or []
    elig = cfg.get("eligibility", {}) or {}
    by_tier = elig.get("by_tier", {}) or {}
    override = elig.get("by_source_override", {}) or {}
    actions = set((elig.get("actions") or {}).keys())
    keys = {s["key"] for s in sources}

    # 1. a polled source with nowhere to poll is a silent no-op.
    #    EXCEPTION: a source may legitimately have no endpoint of its own if it
    #    delegates to another source via `via:` (e.g. the asylum sweep is just a
    #    differently-filtered TED query, not a separate site). But then the
    #    delegate MUST exist and MUST itself be fetchable, or the delegation is
    #    a no-op one level down -- which is even harder to spot.
    for s in sources:
        has_own = s.get("endpoint") or s.get("url") or s.get("urls")
        via = s.get("via")
        if not s.get("poll"):
            continue
        if has_own:
            continue
        if not via:
            problems.append(
                f"{s['key']}: poll:true but no endpoint/url/urls and no via: -- "
                f"SILENT NO-OP, runs green and fetches nothing"
            )
            continue
        target = next((x for x in sources if x["key"] == via), None)
        if target is None:
            problems.append(
                f"{s['key']}: via: '{via}' does not name any source -- broken delegation"
            )
        elif not (target.get("endpoint") or target.get("url") or target.get("urls")):
            problems.append(
                f"{s['key']}: delegates via '{via}', but '{via}' has no endpoint "
                f"either -- no-op one level down"
            )

    # 2. every source tier must resolve to an action
    for s in sources:
        if s["tier"] not in by_tier:
            problems.append(
                f"{s['key']}: tier {s['tier']} has no eligibility.by_tier rule -- "
                f"alerts would carry no action label"
            )

    # 3. orphan rules catch a rename made in the other direction
    used = {s["tier"] for s in sources}
    for t in by_tier:
        if t not in used:
            problems.append(f"eligibility.by_tier.{t} matches no source -- stale rule?")

    # 4. overrides must point at real source keys
    for k in override:
        if k not in keys:
            problems.append(f"eligibility.by_source_override.{k} is not a source key")

    # 5. every action referenced must be defined
    for name, val in list(by_tier.items()) + list(override.items()):
        if val not in actions:
            problems.append(f"{name} -> '{val}' is not a defined eligibility.actions entry")

    # 6. the parked EU profile must stay parked AND stay present
    prof = cfg.get("profile", {}) or {}
    if prof.get("active_profile") != "tunisian":
        problems.append(
            f"profile.active_profile is '{prof.get('active_profile')}' -- expected 'tunisian'"
        )
    if "eu_portugal" not in (prof.get("future_profiles") or {}):
        problems.append(
            "profile.future_profiles.eu_portugal is GONE -- the parked EU profile "
            "was deleted, it must survive until Portugal is activated"
        )

    print("\n" + "=" * 74)
    print("CONFIG INTEGRITY  (static, no network)")
    print("=" * 74)
    if problems:
        for p in problems:
            print(f"  x {p}")
        print(f"\nFAILED: {len(problems)} problem(s)\n")
    else:
        print(f"  OK -- {len(sources)} sources")
        print("       every polled source has an endpoint")
        print("       every tier resolves to an action")
        print("       EU profile parked and intact\n")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write full report to this path")
    ap.add_argument("--check-config", action="store_true",
                    help="static config integrity checks only, no network")
    ap.add_argument("--check-eligibility", action="store_true",
                    help="alias for --check-config")
    args = ap.parse_args()

    # Fast path: no network needed, safe to run as a pre-commit / CI gate.
    if args.check_config or args.check_eligibility:
        return 1 if check_config() else 0

    where = "GITHUB ACTIONS RUNNER" if _in_actions() else "LOCAL MACHINE"
    print(f"\nonsite-interpreter-bid-hunter :: source validation")
    print(f"Running from: {where}")
    print(f"UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "environment": where,
        "ted": probe_ted(),
        "reachability": probe_gets(),
    }

    ok = [r for r in report["reachability"] if r["verdict"] == "OK"]
    bad = [r for r in report["reachability"] if r["verdict"] != "OK"]

    print("\n" + "=" * 74)
    print(f"SUMMARY: {len(ok)} reachable / {len(bad)} need attention")
    print("=" * 74)
    for r in bad:
        print(f"  - {r['name']}: {r['verdict']}")
    print("\nNext: run this again inside GitHub Actions and diff the two")
    print("reports. Anything that flips OK -> BLOCKED is IP-filtered and")
    print("must move to a different source or a non-Actions runner.\n")

    cfg_problems = check_config()
    report["config_problems"] = cfg_problems

    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Full report written to {args.json}")

    # Reachability failures are expected and informational (that is the whole
    # point of diffing local vs runner). CONFIG failures are not -- they mean
    # the pipeline is lying about what it covers, so they fail the build.
    return 1 if cfg_problems else 0


def _in_actions():
    import os
    return os.environ.get("GITHUB_ACTIONS") == "true"


if __name__ == "__main__":
    sys.exit(main())
