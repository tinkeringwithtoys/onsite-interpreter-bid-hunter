#!/usr/bin/env python3
"""
Deadline watcher.

The scraper answers "what is NEW?".
This answers "what is about to CLOSE?"

Those are different questions, and the second one is the one that quietly loses
you money. A 45-day framework contract is CORRECTLY parked the day you first see
it -- you have time, no action needed. But a new-notice pipeline never mentions
it again. Six weeks later the deadline passes and you never knew, because nothing
in the system was watching the clock.

That is the real gap in a "runs 24/7" design. Polling frequency does not fix it.
Running hourly instead of daily still never re-surfaces a parked tender.

This reads watchlist.json and emits reminders at T-14 / T-7 / T-3 / T-1 days.
Each milestone fires exactly ONCE per item, so you get four emails over six
weeks, not forty.

Zero dependencies - standard library only.

Usage:
    python3 deadline_watch.py --watchlist watchlist.json
    python3 deadline_watch.py --self-test        # no files needed
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

# Reminder bands, in days remaining. Ordered loosest -> tightest.
MILESTONES = [14, 7, 3, 1]

# Below this many days, an onsite bid outside Tunisia is probably not feasible
# anyway because of Schengen appointment lead time. Flagged, not filtered --
# remote/RSI work has no such constraint, and neither does anything in Tunisia.
ONSITE_TRAVEL_INFEASIBLE_DAYS = 35


def parse_deadline(raw):
    """Accept 'YYYY-MM-DD' or full ISO-8601. Return a date, or None."""
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    for parse in (
        lambda v: datetime.fromisoformat(v).date(),
        lambda v: datetime.strptime(v[:10], "%Y-%m-%d").date(),
    ):
        try:
            return parse(s)
        except Exception:
            continue
    return None


def days_until(deadline, today):
    return (deadline - today).days


def due_milestones(days_left, already_fired):
    """
    Which bands are due now?

    Returns (band_to_report, bands_to_mark_fired).

    The subtlety: if you first see an item with 5 days left, bands 14 and 7 are
    both technically "entered", but reporting "14 days left" when 5 remain is
    misleading. So we report the TIGHTEST sensible band once, and mark the
    looser ones as fired so they never re-trigger later.
    """
    eligible = [m for m in MILESTONES if days_left <= m and m not in already_fired]
    if not eligible:
        return None, []
    return min(eligible), eligible


def run(items, today):
    """
    Returns (alerts, kept_items, expired_items).
    Pure function - no I/O - so it is trivially testable.
    """
    alerts, kept, expired = [], [], []

    for item in items:
        deadline = parse_deadline(item.get("deadline"))

        if deadline is None:
            # Keep it, but say so out loud. Silent data problems are worse than
            # noisy ones.
            item.setdefault("warnings", [])
            if "unparseable_deadline" not in item["warnings"]:
                item["warnings"].append("unparseable_deadline")
            kept.append(item)
            continue

        left = days_until(deadline, today)

        if left < 0:
            item["closed_on"] = deadline.isoformat()
            item["bid_submitted"] = bool(item.get("bid_submitted"))
            expired.append(item)
            continue

        fired = list(item.get("fired_milestones", []))
        band, to_mark = due_milestones(left, fired)

        if band is not None:
            flags = []
            modality = (item.get("modality") or "").lower()
            is_onsite = modality in ("onsite", "hybrid", "")
            outside_tn = (item.get("country") or "").upper() not in ("TN", "")

            if is_onsite and outside_tn and left < ONSITE_TRAVEL_INFEASIBLE_DAYS:
                flags.append(
                    f"onsite abroad with {left}d left - check visa lead time"
                )
            if item.get("travel_covered"):
                flags.append("travel + accommodation covered")
            if modality in ("remote", "telephone", "rsi"):
                flags.append("remote - no travel constraint")

            alerts.append(
                {
                    "band": band,
                    "days_left": left,
                    "deadline": deadline.isoformat(),
                    "title": item.get("title", "(untitled)"),
                    "source": item.get("source", "?"),
                    "url": item.get("url", ""),
                    "modality": item.get("modality", "unknown"),
                    "flags": flags,
                }
            )
            fired.extend(m for m in to_mark if m not in fired)
            item["fired_milestones"] = sorted(set(fired), reverse=True)

        kept.append(item)

    # Tightest deadline first - that is the order you want to read them in.
    alerts.sort(key=lambda a: a["days_left"])
    return alerts, kept, expired


def render(alerts, expired):
    if not alerts and not expired:
        return "No deadline milestones due today."

    lines = []
    if alerts:
        lines.append("DEADLINES APPROACHING")
        lines.append("=" * 60)
        for a in alerts:
            lines.append(
                f"  T-{a['days_left']}d  [{a['source']}]  {a['title']}"
            )
            lines.append(f"          closes {a['deadline']} · {a['modality']}")
            for f in a["flags"]:
                lines.append(f"          ! {f}")
            if a["url"]:
                lines.append(f"          {a['url']}")
            lines.append("")

    if expired:
        lines.append("CLOSED SINCE LAST RUN")
        lines.append("=" * 60)
        for e in expired:
            tag = "bid submitted" if e.get("bid_submitted") else "NO BID SUBMITTED"
            lines.append(f"  {e.get('title','(untitled)')}  ({tag})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test. Runs without network, without files, without secrets.
# ---------------------------------------------------------------------------
def self_test():
    today = date(2026, 8, 7)
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # 1. A far-off item must stay silent. This is the whole point of parking.
    alerts, kept, exp = run(
        [{"title": "far", "deadline": "2026-10-30"}], today
    )
    check("far item silent", len(alerts), 0)
    check("far item kept", len(kept), 1)

    # 2. Entering the 14-day band fires once.
    item = {"title": "t14", "deadline": "2026-08-19"}   # 12 days out
    a1, k1, _ = run([item], today)
    check("t14 fires", len(a1), 1)
    check("t14 band", a1[0]["band"], 14)
    # 3. ...and does NOT fire again on the next run.
    a2, _, _ = run(k1, today)
    check("t14 no repeat", len(a2), 0)

    # 4. Late discovery: 5 days left should report band 7, not band 14,
    #    and must burn band 14 so it never fires afterwards.
    late = {"title": "late", "deadline": "2026-08-12"}   # 5 days out
    a3, k3, _ = run([late], today)
    check("late band", a3[0]["band"], 7)
    check("late burns 14", k3[0]["fired_milestones"], [14, 7])

    # 5. Tightening from 5 days to 2 days fires band 3.
    a4, k4, _ = run(k3, date(2026, 8, 10))
    check("tighten band", a4[0]["band"], 3)

    # 6. Past deadline expires and is removed from the kept list.
    a5, k5, e5 = run([{"title": "gone", "deadline": "2026-08-01"}], today)
    check("expired removed", len(k5), 0)
    check("expired reported", len(e5), 1)

    # 7. Unparseable deadline is kept and flagged, never silently dropped.
    a6, k6, _ = run([{"title": "bad", "deadline": "soon-ish"}], today)
    check("bad kept", len(k6), 1)
    check("bad flagged", k6[0]["warnings"], ["unparseable_deadline"])

    # 8. Onsite-abroad with short runway raises the visa flag.
    a7, _, _ = run(
        [{"title": "abroad", "deadline": "2026-08-12",
          "modality": "onsite", "country": "DE"}], today
    )
    check("visa flag", any("visa" in f for f in a7[0]["flags"]), True)

    # 9. Remote work must NOT raise a travel flag.
    a8, _, _ = run(
        [{"title": "rsi", "deadline": "2026-08-12",
          "modality": "remote", "country": "DE"}], today
    )
    check("remote no visa flag", any("visa" in f for f in a8[0]["flags"]), False)

    # 10. ISO-8601 with timezone must parse.
    check("iso tz parse",
          parse_deadline("2026-08-19T17:00:00Z"), date(2026, 8, 19))

    if failures:
        print("SELF-TEST FAILED")
        for f in failures:
            print("  x " + f)
        return 1
    print("SELF-TEST PASSED  (10/10 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default="watchlist.json")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--today", help="override today (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    today = (
        parse_deadline(args.today)
        or datetime.now(timezone.utc).date()
    )

    if not os.path.exists(args.watchlist):
        print(f"No {args.watchlist} yet - nothing to watch. Exiting cleanly.")
        return 0

    with open(args.watchlist, encoding="utf-8") as fh:
        items = json.load(fh)
    if isinstance(items, dict):
        items = items.get("items", [])

    alerts, kept, expired = run(items, today)
    print(render(alerts, expired))

    with open(args.watchlist, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, indent=2, ensure_ascii=False)

    # Emit for the workflow to pick up and email.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"alert_count={len(alerts)}\n")
            fh.write(f"expired_count={len(expired)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
