#!/usr/bin/env python3
"""High-signal adapters for the unified Hunt."""
from __future__ import annotations
import argparse
import html as html_lib
import json
import re
import urllib.parse

MAX_WEB_DETAIL_CANDIDATES = 35
# Search-index fallback for UNGM's unreliable internal endpoint. These are
# direct official notice URLs, not aggregator results.
OFFICIAL_UNGM_INDEX_QUERIES = [
    'site:ungm.org/Public/Notice "interpretation"',
    'site:ungm.org/Public/Notice "simultaneous interpretation"',
]
OFFICIAL_UNGM_REVIEW_MARKER = "OFFICIAL_UNGM_OPEN_NOTICE_LANGUAGE_MATRIX_UNVERIFIED"
TAG_RX = re.compile(r"<[^>]+>")
ANCHOR_RX = re.compile(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
ARABIC_SIGNAL_RX = re.compile(r"\b(?:arabic|arabe|ar-fr|ar/en)\b|العرب(?:ية|ي)|مترجم", re.I)
OPPORTUNITY_SIGNAL_RX = re.compile(r"\b(?:tender|rfp|rfq|itb|eoi|procurement|bid|notice|deadline|closing)\b|appel\s+d['’]offres?|marché|consultation", re.I)
SPECIFIC_NOTICE_URL_RX = re.compile(r"/(?:notice|consultation|tender|opportunity|rfp|rfq|ao)[/-]?\d", re.I)
UNGM_NOTICE_URL_RX = re.compile(r"^https?://(?:www\.)?ungm\.org/Public/Notice/\d+(?:[/?#]|$)", re.I)
GENERIC_DISCOVERY_TITLE_RX = re.compile(r"^(?:latest\s+|interpretation(?:\s+services?)?\s+(?:tenders?|rfps?|bids?)\b|translation(?:\s+services?)?\s+rfps?\b|(?:translation/)?interpretation.*(?:tender news|eprocurement|government contracts|bids?\s*&\s*rfps?)|appel d['’]offre\s+(?:traduction|informatique)\b|tunisie appels d['’]offres\b|appels d['’]offres,\s*tous\b)", re.I)
_MISSING = object()

def plain_text(fragment):
    return re.sub(r"\s+", " ", html_lib.unescape(TAG_RX.sub(" ", fragment or ""))).strip()

def is_official_ungm_notice(url):
    return bool(UNGM_NOTICE_URL_RX.search(url or ""))

def is_generic_discovery_listing(title, url):
    return bool(GENERIC_DISCOVERY_TITLE_RX.search(title or "")) and not bool(SPECIFIC_NOTICE_URL_RX.search(url or ""))

def has_arabic_tender_signal(title, detail):
    text = f"{title or ''}\n{detail or ''}"
    return bool(ARABIC_SIGNAL_RX.search(text) and OPPORTUNITY_SIGNAL_RX.search(text))

def is_target_celp_announcement(title):
    lower = (title or "").lower()
    return bool(("interpreter" in lower or "interprète" in lower or "interprétation" in lower) and ARABIC_SIGNAL_RX.search(lower))

def web_discovery_handler(scraper):
    def handler(src, cfg, keywords):
        search_src = dict(src)
        queries = list(src.get("queries") or [])
        for query in OFFICIAL_UNGM_INDEX_QUERIES:
            if query not in queries:
                queries.append(query)
        search_src["queries"] = queries
        candidates, meta = scraper.fetch_search(search_src, cfg, keywords)
        accepted, seen = [], set()
        generic = navigation = detail_failed = no_signal = official = capped = 0
        for index, item in enumerate(candidates):
            if index >= MAX_WEB_DETAIL_CANDIDATES:
                capped += 1
                continue
            url, title = str(item.get("url") or ""), str(item.get("title") or "")
            canonical = scraper.canonical_url(url) or url
            if not url.startswith(("https://", "http://")) or canonical in seen:
                continue
            seen.add(canonical)
            direct_ungm = is_official_ungm_notice(url)
            if scraper.looks_like_navigation(url, title):
                navigation += 1
                continue
            if not direct_ungm and is_generic_discovery_listing(title, url):
                generic += 1
                continue
            detail = scraper.fetch_notice_text(url, timeout=10)
            if not detail:
                detail_failed += 1
                continue
            # Direct official UNGM interpretation notices are real open leads
            # even when the language matrix lives only in an attachment.
            if not has_arabic_tender_signal(title, detail) and not (direct_ungm and OPPORTUNITY_SIGNAL_RX.search(f"{title} {detail}")):
                no_signal += 1
                continue
            raw = {**(item.get("raw") or {}), "detail_fetched": True}
            if direct_ungm:
                official += 1
                raw.update({"official_ungm_notice": True, "manual_review_required": True})
                item["title"] = "[MANUAL REVIEW] " + title
                detail += ("\n\n" + OFFICIAL_UNGM_REVIEW_MARKER + ": This is a numbered, "
                           "official, open UNGM interpretation notice. The language matrix, "
                           "delivery mode, and bidder eligibility require Annex verification.")
            item["summary"] = detail[:5500]
            item["raw"] = raw
            accepted.append(item)
        return accepted, {**(meta or {}), "queries_run": len(queries), "detail_fetched": len(accepted), "official_ungm_indexed_notices": official, "filtered_generic_listing": generic, "filtered_navigation": navigation, "filtered_no_signal": no_signal, "detail_fetch_failed": detail_failed, "detail_cap_deferred": capped}
    return handler

def ungm_browser_session_handler(scraper):
    def handler(src, cfg, keywords):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise scraper.FetchError("playwright not installed for UNGM browser session") from exc
        payload = {"pageIndex": 0, "pageSize": 50, "sortField": "DatePosted", "sortOrder": "Descending", "keyword": "", "UNSPSCCodes": [], "AgencyGovId": [], "StatusId": 1, "DeadlineDateFrom": None, "DeadlineDateTo": None}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(user_agent=scraper.UA, locale="en-US")
                    page.goto(src.get("url") or "https://www.ungm.org/Public/Notice", wait_until="domcontentloaded")
                    response = page.evaluate("""async (args) => { const r = await fetch(args.url, {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','Accept':'application/json','X-Requested-With':'XMLHttpRequest'}, body:JSON.stringify(args.payload)}); return {status:r.status, body:await r.text()}; }""", {"url": scraper.UNGM_SEARCH_API, "payload": payload})
                finally:
                    browser.close()
        except Exception as exc:
            raise scraper.FetchError(f"UNGM browser-session request failed: {type(exc).__name__}: {exc}") from exc
        status, body = int((response or {}).get("status") or 0), str((response or {}).get("body") or "")
        if status != 200:
            raise scraper.FetchError(f"UNGM browser-session API HTTP {status}: {body[:220]}")
        try:
            parsed = scraper.parse_ungm_json(json.loads(body))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise scraper.FetchError(f"UNGM browser-session API returned invalid JSON: {exc}") from exc
        if not parsed:
            raise scraper.FetchError("UNGM browser-session API returned no parseable notice rows")
        terms = {str(term).lower() for term in (keywords or []) if str(term)} | {"interpreter", "interpreters", "interprète", "interprètes"}
        items = []
        for row in parsed:
            url = str(row.get("url") or "")
            haystack = f"{row.get('title') or ''} {row.get('summary') or ''}".lower()
            if not is_official_ungm_notice(url) or (terms and not any(term in haystack for term in terms)):
                continue
            items.append(scraper.normalise(src["key"], src.get("tier"), row.get("title"), url, published=row.get("published"), deadline=row.get("deadline"), summary=row.get("summary"), country=row.get("country"), raw=row.get("raw")))
        return items, {"strategy": "browser_session_notice_api", "raw_count": len(parsed), "matched_count": len(items)}
    return handler

def celp_announcement_handler(scraper):
    def handler(src, cfg, keywords):
        urls = src.get("urls") or ([src["url"]] if src.get("url") else [])
        errors, items, seen = [], [], set()
        for listing_url in urls:
            try:
                _, page_html = scraper.http_get(listing_url)
            except scraper.FetchError as exc:
                errors.append(f"{listing_url} -> {exc}")
                continue
            for match in ANCHOR_RX.finditer(page_html):
                url, title = urllib.parse.urljoin(listing_url, html_lib.unescape(match.group(1))), plain_text(match.group(2))
                canonical = scraper.canonical_url(url) or url
                if canonical in seen or not is_target_celp_announcement(title):
                    continue
                seen.add(canonical)
                detail = scraper.fetch_notice_text(url, timeout=10)
                if detail:
                    items.append(scraper.normalise(src["key"], src.get("tier"), title, url, summary=detail[:5500], raw={"detail_fetched": True}))
        if urls and len(errors) == len(urls):
            raise scraper.FetchError("; ".join(errors)[:280])
        return items, {"errors": errors, "detail_fetched": len(items)}
    return handler

def install(scraper):
    keys = ("web_discovery", "ungm", "un_celp_exams")
    originals = {key: scraper.HANDLERS.get(key, _MISSING) for key in keys}
    scraper.HANDLERS["web_discovery"] = web_discovery_handler(scraper)
    scraper.HANDLERS["ungm"] = ungm_browser_session_handler(scraper)
    scraper.HANDLERS["un_celp_exams"] = celp_announcement_handler(scraper)
    return originals

def restore(scraper, originals):
    for key, prior in (originals or {}).items():
        if prior is _MISSING: scraper.HANDLERS.pop(key, None)
        else: scraper.HANDLERS[key] = prior

def self_test():
    checks = [
        is_official_ungm_notice("https://www.ungm.org/Public/Notice/308530"),
        not is_generic_discovery_listing("Interpretation services", "https://www.ungm.org/Public/Notice/308530"),
        is_generic_discovery_listing("Latest Interpretation Services Tenders and RFP", "https://example.test/rfp/interpreting"),
        has_arabic_tender_signal("Framework", "Tender for Arabic-French interpretation"),
        is_target_celp_announcement("Global Language Roster examination for Arabic Interpreters"),
        not is_target_celp_announcement("Competitive examination for Russian Interpreters"),
    ]
    if not all(checks):
        print("UNIFIED SOURCE QUALITY SELF-TEST FAILED")
        return 1
    print("UNIFIED SOURCE QUALITY SELF-TEST PASSED (6/6 checks)")
    return 0

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--self-test", action="store_true"); args = parser.parse_args()
    return self_test() if args.self_test else 1
if __name__ == "__main__":
    raise SystemExit(main())
