#!/usr/bin/env python3
"""High-signal source adapters used by the one unified Hunt.

The generic HTML harvester is intentionally broad. These adapters tighten the
three sources that otherwise produce the most expensive false positives:

- open-web discovery must fetch a result's detail page before Agnes sees it;
- UNGM must return real /Public/Notice/<id> records, never site navigation;
- UN language announcements must be Arabic-interpreter announcements, not the
  entire DGACM navigation tree or old unrelated language pages.

All functions are installed temporarily by run_hunt.py. The normal scraper
continues to own dedupe, state, scoring, and email rendering.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import urllib.parse

MAX_WEB_DETAIL_CANDIDATES = 35

TAG_RX = re.compile(r"<[^>]+>")
ANCHOR_RX = re.compile(
    r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S
)
ARABIC_SIGNAL_RX = re.compile(
    r"\b(?:arabic|arabe|ar-fr|ar/en)\b|العرب(?:ية|ي)|مترجم", re.I
)
OPPORTUNITY_SIGNAL_RX = re.compile(
    r"\b(?:tender|rfp|rfq|itb|eoi|procurement|bid|notice|deadline|closing)\b|"
    r"appel\s+d['’]offres?|marché|consultation", re.I
)
SPECIFIC_NOTICE_URL_RX = re.compile(
    r"/(?:notice|consultation|tender|opportunity|rfp|rfq|ao)[/-]?\d", re.I
)
GENERIC_DISCOVERY_TITLE_RX = re.compile(
    r"^(?:"
    r"latest\s+|"
    r"interpretation(?:\s+services?)?\s+(?:tenders?|rfps?|bids?)\b|"
    r"translation(?:\s+services?)?\s+rfps?\b|"
    r"(?:translation/)?interpretation.*(?:tender news|eprocurement|government contracts|bids?\s*&\s*rfps?)|"
    r"appel d['’]offre\s+(?:traduction|informatique)\b|"
    r"tunisie appels d['’]offres\b|"
    r"appels d['’]offres,\s*tous\b"
    r")",
    re.I,
)
UNGM_NOTICE_URL_RX = re.compile(r"/Public/Notice/\d+(?:[/?#]|$)", re.I)
_MISSING = object()


def plain_text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(TAG_RX.sub(" ", fragment or ""))).strip()


def is_generic_discovery_listing(title: str, url: str) -> bool:
    """Reject category/aggregator pages while preserving numbered notices."""
    return bool(GENERIC_DISCOVERY_TITLE_RX.search(title or "")) and not bool(
        SPECIFIC_NOTICE_URL_RX.search(url or "")
    )


def has_arabic_tender_signal(title: str, detail: str) -> bool:
    text = f"{title or ''}\n{detail or ''}"
    return bool(ARABIC_SIGNAL_RX.search(text) and OPPORTUNITY_SIGNAL_RX.search(text))


def is_target_celp_announcement(title: str) -> bool:
    lower = (title or "").lower()
    interpreter = "interpreter" in lower or "interprète" in lower or "interprétation" in lower
    return bool(interpreter and ARABIC_SIGNAL_RX.search(lower))


def web_discovery_handler(scraper):
    """Fetch public result pages before scoring, not search-engine titles."""
    def handler(src, cfg, keywords):
        candidates, meta = scraper.fetch_search(src, cfg, keywords)
        accepted, seen = [], set()
        generic, navigation, detail_failed, no_arabic_tender, capped = 0, 0, 0, 0, 0

        for index, item in enumerate(candidates):
            if index >= MAX_WEB_DETAIL_CANDIDATES:
                capped += 1
                continue
            url = str(item.get("url") or "")
            title = str(item.get("title") or "")
            canonical = scraper.canonical_url(url) or url
            if not url.startswith(("https://", "http://")) or canonical in seen:
                continue
            seen.add(canonical)

            if scraper.looks_like_navigation(url, title):
                navigation += 1
                continue
            if is_generic_discovery_listing(title, url):
                generic += 1
                continue

            detail = scraper.fetch_notice_text(url, timeout=10)
            if not detail:
                detail_failed += 1
                continue
            if not has_arabic_tender_signal(title, detail):
                no_arabic_tender += 1
                continue

            item["summary"] = detail[:5500]
            item["raw"] = {**(item.get("raw") or {}), "detail_fetched": True}
            accepted.append(item)

        return accepted, {
            **(meta or {}),
            "detail_fetched": len(accepted),
            "filtered_generic_listing": generic,
            "filtered_navigation": navigation,
            "filtered_no_arabic_tender_signal": no_arabic_tender,
            "detail_fetch_failed": detail_failed,
            "detail_cap_deferred": capped,
        }

    return handler


def ungm_browser_session_handler(scraper):
    """Use a browser session to call UNGM's notice endpoint, never scrape menu links."""
    def handler(src, cfg, keywords):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise scraper.FetchError("playwright not installed for UNGM browser session") from exc

        payload = {
            "pageIndex": 0,
            "pageSize": 50,
            "sortField": "DatePosted",
            "sortOrder": "Descending",
            "keyword": "",
            "UNSPSCCodes": [],
            "AgencyGovId": [],
            "StatusId": 1,
            "DeadlineDateFrom": None,
            "DeadlineDateTo": None,
        }
        url = src.get("url") or "https://www.ungm.org/Public/Notice"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(user_agent=scraper.UA, locale="en-US")
                    page.set_default_timeout(30000)
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1200)
                    response = page.evaluate(
                        """async (args) => {
                            const response = await fetch(args.url, {
                              method: 'POST',
                              credentials: 'same-origin',
                              headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest'
                              },
                              body: JSON.stringify(args.payload)
                            });
                            return {status: response.status, body: await response.text()};
                        }""",
                        {"url": scraper.UNGM_SEARCH_API, "payload": payload},
                    )
                finally:
                    browser.close()
        except Exception as exc:
            raise scraper.FetchError(f"UNGM browser-session request failed: {type(exc).__name__}: {exc}") from exc

        status = int((response or {}).get("status") or 0)
        body = str((response or {}).get("body") or "")
        if status != 200:
            raise scraper.FetchError(f"UNGM browser-session API HTTP {status}: {body[:220]}")
        try:
            parsed = scraper.parse_ungm_json(json.loads(body))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise scraper.FetchError(f"UNGM browser-session API returned invalid JSON: {exc}") from exc
        if not parsed:
            raise scraper.FetchError("UNGM browser-session API returned no parseable notice rows")

        terms = {str(term).lower() for term in (keywords or []) if str(term)}
        terms.update({"interpreter", "interpreters", "interprète", "interprètes"})
        items = []
        for row in parsed:
            row_url = str(row.get("url") or "")
            haystack = f"{row.get('title') or ''} {row.get('summary') or ''}".lower()
            if not UNGM_NOTICE_URL_RX.search(row_url):
                continue
            if terms and not any(term in haystack for term in terms):
                continue
            items.append(scraper.normalise(
                src["key"], src.get("tier"), row.get("title"), row_url,
                published=row.get("published"), deadline=row.get("deadline"),
                summary=row.get("summary"), country=row.get("country"),
                raw=row.get("raw"),
            ))
        return items, {
            "strategy": "browser_session_notice_api",
            "raw_count": len(parsed),
            "matched_count": len(items),
        }

    return handler


def celp_announcement_handler(scraper):
    """Extract only Arabic-interpreter announcements from DGACM listing pages."""
    def handler(src, cfg, keywords):
        urls = src.get("urls") or ([src["url"]] if src.get("url") else [])
        errors, items, seen = [], [], set()
        listing_pages = 0
        detail_fetched = 0

        for listing_url in urls:
            try:
                _, page_html = scraper.http_get(listing_url)
                listing_pages += 1
            except scraper.FetchError as exc:
                errors.append(f"{listing_url} -> {exc}")
                continue

            for match in ANCHOR_RX.finditer(page_html):
                candidate_url = urllib.parse.urljoin(listing_url, html_lib.unescape(match.group(1)))
                title = plain_text(match.group(2))
                canonical = scraper.canonical_url(candidate_url) or candidate_url
                if canonical in seen or not is_target_celp_announcement(title):
                    continue
                seen.add(canonical)
                detail = scraper.fetch_notice_text(candidate_url, timeout=10)
                if not detail:
                    continue
                detail_fetched += 1
                items.append(scraper.normalise(
                    src["key"], src.get("tier"), title, candidate_url,
                    summary=detail[:5500], raw={"detail_fetched": True},
                ))

        if urls and len(errors) == len(urls):
            raise scraper.FetchError("; ".join(errors)[:280])
        return items, {
            "listing_pages": listing_pages,
            "detail_fetched": detail_fetched,
            "errors": errors,
        }

    return handler


def install(scraper):
    """Install quality adapters for one run and return the original handlers."""
    keys = ("web_discovery", "ungm", "un_celp_exams")
    originals = {key: scraper.HANDLERS.get(key, _MISSING) for key in keys}
    scraper.HANDLERS["web_discovery"] = web_discovery_handler(scraper)
    scraper.HANDLERS["ungm"] = ungm_browser_session_handler(scraper)
    scraper.HANDLERS["un_celp_exams"] = celp_announcement_handler(scraper)
    return originals


def restore(scraper, originals):
    for key, prior in (originals or {}).items():
        if prior is _MISSING:
            scraper.HANDLERS.pop(key, None)
        else:
            scraper.HANDLERS[key] = prior


def self_test() -> int:
    failures = []

    def check(name, condition):
        if not condition:
            failures.append(name)

    check("generic discovery page rejected", is_generic_discovery_listing(
        "Latest Interpretation Services Tenders and RFP", "https://example.test/rfp/interpreting"))
    check("numbered notice retained", not is_generic_discovery_listing(
        "Interpretation services - Find a Tender", "https://example.test/Notice/044841-2026"))
    check("arabic tender detail accepted", has_arabic_tender_signal(
        "Framework services", "Tender notice: Arabic-French interpreting. Closing date 2026-09-01."))
    check("no Arabic signal rejected", not has_arabic_tender_signal(
        "Interpreting services", "Tender notice for German and Polish interpreters."))
    check("Arabic CELP accepted", is_target_celp_announcement(
        "Global Language Roster examination for Arabic Interpreters"))
    check("unrelated CELP rejected", not is_target_celp_announcement(
        "Competitive examination for Russian Interpreters"))

    if failures:
        print("UNIFIED SOURCE QUALITY SELF-TEST FAILED")
        for failure in failures:
            print(f"  x {failure}")
        return 1
    print("UNIFIED SOURCE QUALITY SELF-TEST PASSED (6/6 checks)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
