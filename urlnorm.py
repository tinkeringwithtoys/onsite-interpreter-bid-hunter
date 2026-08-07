#!/usr/bin/env python3
"""
urlnorm.py -- link hygiene: canonical URLs, and cheap rejection of site chrome.

Two jobs. Both exist to stop the pipeline paying for the same page twice.

  canonical_url(url)
      Collapse the cosmetic differences that make one page look like two:
      tracking parameters (utm_*, gclid, fbclid, session ids), fragments,
      parameter order, default ports, a trailing slash, an index.html.

      A portal that appends ?utm_source=newsletter on Tuesday and
      ?utm_source=rss on Wednesday published ONE notice, not two. Before this,
      those were two different dedupe keys and two different item ids, so the
      notice was scored twice (two LLM calls) and could be emailed twice.

  looks_like_navigation(url, title)
      Reject site chrome before it reaches the scorer. The HTML harvester in
      scraper.py is deliberately dumb - precision is supposed to come from the
      keyword gate and the LLM - but that means homepages, cookie notices and
      Facebook links reach the scorer and cost an LLM call each. The 21:02 run
      spent 176 scoring calls to reject almost entirely this kind of thing.

      Deliberately CONSERVATIVE. Returning a false positive here silently
      loses a real tender, which is far worse than wasting one API call, so it
      only rejects things that cannot be a notice: a bare homepage, a social
      network profile, an obvious cookie/privacy/login page.

Returns a REASON string rather than True, so the log says why.

Zero dependencies - standard library only.

    python3 urlnorm.py --self-test
"""

import argparse
import re
import sys
import urllib.parse

# Parameters that never identify a document, only how you arrived at it.
TRACKING_PREFIXES = (
    "utm_", "pk_", "mtm_", "matomo_", "hsa_", "_hs", "vero_", "ns_",
)
TRACKING_EXACT = {
    "gclid", "dclid", "gbraid", "wbraid", "fbclid", "msclkid", "yclid",
    "twclid", "igshid", "mc_cid", "mc_eid", "cmpid", "campaign", "spm",
    "ref", "referer", "referrer", "source", "src", "trk", "trkcampaign",
    "at_medium", "at_campaign", "xtor", "originalsubdomain",
    "sessionid", "session_id", "jsessionid", "phpsessid", "aspsessionid",
    "cfid", "cftoken", "_ga", "_gl", "gclsrc",
}

DEFAULT_PORTS = {"http": "80", "https": "443"}
INDEX_FILES = ("index.html", "index.htm", "index.php", "index.jsp",
               "default.aspx", "default.htm")

SOCIAL_HOSTS = {
    "facebook.com", "m.facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "youtu.be", "t.me", "wa.me",
    "pinterest.com", "flickr.com", "tiktok.com", "threads.net",
}

# Path segments that cannot be part of a tender notice URL.
# NOTE: 'search', 'jobs' and 'careers' are deliberately ABSENT. Roster calls
# and freelance-interpreter openings live under exactly those paths.
CHROME_SEGMENTS = {
    "privacy", "privacy-policy", "privacy-statement", "cookie", "cookies",
    "cookie-policy", "terms", "terms-of-use", "legal-notice", "disclaimer",
    "sitemap", "accessibility", "login", "logon", "signin", "sign-in",
    "register", "registration", "contact", "contact-us", "faq",
    "rss", "feed", "newsletter", "subscribe", "share", "print",
}

CHROME_TITLE_RX = re.compile(
    r"\b(cookie|privacy (policy|notice|statement)|accessibility statement"
    r"|terms of (use|service)|sitemap|skip to (main )?content|follow us"
    r"|create an account|log ?in|sign ?in)\b",
    re.I,
)


def is_tracking_param(name):
    low = (name or "").lower()
    if low in TRACKING_EXACT:
        return True
    return any(low.startswith(p) for p in TRACKING_PREFIXES)


def canonical_url(url):
    """Return a stable key for a URL. Never raises. '' for empty input.

    Anything that is not an absolute http(s) URL is returned untouched -- we
    do not model mailto:, javascript: or bare fragments, and mangling them
    would be worse than leaving them alone.
    """
    if not url:
        return ""
    raw = str(url).strip()
    if not raw:
        return ""
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return raw
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https") or not parts.netloc:
        return raw

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and str(port) != DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    low = path.lower()
    for f in INDEX_FILES:
        if low.endswith("/" + f):
            path = path[: -len(f)]
            break
    if len(path) > 1:
        path = path.rstrip("/")
    if not path:
        path = "/"

    kept = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not is_tracking_param(k)
    ]
    kept.sort()
    query = urllib.parse.urlencode(kept)

    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def same_page(a, b):
    """True when two URLs address the same document."""
    ca, cb = canonical_url(a), canonical_url(b)
    return bool(ca) and ca == cb


def looks_like_navigation(url, title=""):
    """Return a reason string if this cannot be a tender notice, else None."""
    canon = canonical_url(url)
    if not canon:
        return "no url"

    parts = urllib.parse.urlsplit(canon)
    if parts.scheme in ("http", "https"):
        host = (parts.hostname or "").lower()
        if host in SOCIAL_HOSTS:
            return f"social link ({host})"
        path = parts.path or "/"
        if path in ("", "/") and not parts.query:
            return "site root, not a notice"
        for seg in (s.lower() for s in path.split("/") if s):
            if seg in CHROME_SEGMENTS:
                return f"site chrome path segment '{seg}'"

    t = (title or "").strip()
    if t and CHROME_TITLE_RX.search(t):
        return "site chrome title"
    return None


# ---------------------------------------------------------------------------
# Self-test. Offline, no files, no secrets.
# ---------------------------------------------------------------------------
def self_test():
    checks, failed = 0, []

    def ck(name, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failed.append(f"{name}: got {got!r} want {want!r}")

    # --- canonical_url ----------------------------------------------------
    ck("strips tracking, keeps identity",
       canonical_url("https://www.ungm.org/Public/Notice?utm_source=rss&id=42"),
       "https://ungm.org/Public/Notice?id=42")
    ck("strips fragment",
       canonical_url("https://x.eu/n/1#top"), "https://x.eu/n/1")
    ck("orders parameters",
       canonical_url("https://x.eu/n?b=2&a=1"), "https://x.eu/n?a=1&b=2")
    ck("drops default port",
       canonical_url("https://x.eu:443/n"), "https://x.eu/n")
    ck("keeps non-default port",
       canonical_url("https://x.eu:8443/n"), "https://x.eu:8443/n")
    ck("drops trailing slash",
       canonical_url("https://x.eu/n/"), "https://x.eu/n")
    ck("root keeps its slash",
       canonical_url("https://x.eu/"), "https://x.eu/")
    ck("drops index file",
       canonical_url("https://x.eu/list/index.html"), "https://x.eu/list")
    ck("lowercases host, preserves path case",
       canonical_url("HTTPS://WWW.X.EU/Notice"), "https://x.eu/Notice")
    ck("empty is empty", canonical_url(None), "")
    ck("non-http passes through",
       canonical_url("mailto:a@b.com"), "mailto:a@b.com")

    # The whole point: two links to one notice must collapse to one key.
    ck("tracking variants are one page",
       same_page("https://x.eu/n/1?utm_source=a", "https://x.eu/n/1?gclid=b"),
       True)
    ck("different notices stay different",
       same_page("https://x.eu/n/1", "https://x.eu/n/2"), False)
    ck("empty is never a match", same_page("", ""), False)

    # --- looks_like_navigation -------------------------------------------
    ck("homepage rejected",
       looks_like_navigation("https://www.boamp.fr/", "BOAMP accueil") is not None,
       True)
    ck("facebook rejected",
       looks_like_navigation("https://www.facebook.com/AfricanUnionCommission",
                             "African Union") is not None, True)
    ck("cookie page rejected",
       looks_like_navigation("https://x.eu/en/cookies", "Cookie policy") is not None,
       True)
    # The expensive mistake would be rejecting a real one.
    ck("real notice kept",
       looks_like_navigation(
           "https://au.int/en/bids/interpretation-services-roster-2026",
           "Call for expression of interest: Arabic interpreters"), None)
    ck("roster call under /jobs kept",
       looks_like_navigation("https://x.int/en/jobs/ar-interpreter-roster",
                             "Arabic interpreter roster"), None)
    ck("search result with an id kept",
       looks_like_navigation("https://x.eu/search?noticeId=771",
                             "Interpretation services framework"), None)

    print(f"SELF-TEST {'PASSED' if not failed else 'FAILED'} "
          f"({checks - len(failed)}/{checks} checks)")
    for f in failed:
        print(f"  x {f}")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--url", help="print the canonical form of one URL")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.url:
        print(canonical_url(args.url))
        reason = looks_like_navigation(args.url)
        print(f"navigation: {reason or 'no - looks like a real page'}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
