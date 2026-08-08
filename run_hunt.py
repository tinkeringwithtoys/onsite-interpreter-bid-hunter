#!/usr/bin/env python3
"""Run the one unified, all-source Bid Hunter pass.

This is the only operational entry point for scheduled and manual Hunts. It
selects every ``poll: true`` source, regardless of transport, and sends one
combined lead digest. There is no secondary execution mode for a subset of
sources.

Source failures use persistent incident state rather than per-run email:
repeated failures stay visible in state and logs, but only a stable outage and
its later recovery generate a source-health message.

Usage:
    python run_hunt.py
    python run_hunt.py --dry-run
    python run_hunt.py --lookback-hours 24
    python run_hunt.py --self-test
"""

import argparse
import datetime as dt
import traceback
from pathlib import Path

import yaml

import scraper
import source_health

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
HEALTH_PATH = ROOT / "source_health.json"
HUNT_TIMEOUT_MINUTES = 55


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    lanes = cfg.setdefault("scheduling", {}).setdefault("lanes", {})
    # No polls list is intentional: select_sources(..., "all") takes every
    # explicitly enabled source. The runtime entry prevents an old config
    # description from creating a second scheduler or state writer.
    lanes["all"] = {
        "timeout_minutes": HUNT_TIMEOUT_MINUTES,
        "concurrency_group": "bid-hunter-all",
    }
    return cfg


def active_source_keys(cfg):
    return [str(source["key"]) for source in cfg.get("sources", [])
            if source.get("key") and source.get("poll")]


def outcomes_from_stats(active_sources):
    """Read the just-written stats snapshot for a non-total-failure Hunt."""
    data = scraper.load_json(scraper.DATA_PATH, {})
    stats = data.get("stats") if isinstance(data, dict) else None
    per_source = stats.get("per_source") if isinstance(stats, dict) else None
    if not isinstance(per_source, dict):
        return None

    outcomes = {}
    for source in active_sources:
        row = per_source.get(source)
        if not isinstance(row, dict):
            return None
        error = row.get("error")
        outcomes[source] = str(error) if error else None
    return outcomes


def outcomes_from_total_failure(active_sources):
    """Recover per-source errors when scraper intentionally preserved data.json.

    On an all-source outage scraper.py keeps the previous data snapshot safe,
    but writes debug/last_error.txt in the same worker. That is enough to make
    a durable source-health decision without overwriting good hunt state.
    """
    try:
        lines = scraper.LAST_ERROR_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    errors = {}
    allowed = set(active_sources)
    for line in lines:
        source, separator, error = line.partition(":")
        if separator and source in allowed:
            errors[source] = error.strip() or "unknown failure"
    if active_sources and all(source in errors for source in active_sources):
        return {source: errors[source] for source in active_sources}
    return None


def capture_delivery(cfg, args):
    """Let scraper render its digest, then send only useful state changes.

    scraper.py owns harvesting, scoring, and plain-text rendering. This wrapper
    temporarily captures its requested mail so a raw recurring source error
    cannot bypass the durable incident state machine below.
    """
    import notify

    requested = []
    real_send = notify.send_email

    def capture(subject, text_body, html_body=None):
        requested.append({"subject": subject, "text": text_body, "html": html_body})
        return 0

    notify.send_email = capture
    try:
        result = scraper.run("all", cfg, dry_run=args.dry_run,
                             lookback_hours=args.lookback_hours)
    finally:
        notify.send_email = real_send
    return result, requested, real_send


def actionable_digest(text):
    """A rendered email is actionable only when it contains a lead or deadline."""
    return any(header in (text or "") for header in (
        "NEW OPPORTUNITIES", "DEADLINES APPROACHING", "WHO JUST WON",
    ))


def human_duration(opened_at, closed_at):
    if not opened_at:
        return "an unknown duration"
    try:
        start = dt.datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(str(closed_at).replace("Z", "+00:00"))
        minutes = max(0, int((end - start).total_seconds() // 60))
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"about {hours}h {minutes}m"
        return f"about {minutes}m"
    except ValueError:
        return "an unknown duration"


def health_text(events, state, include_ongoing=False):
    lines = ["SOURCE HEALTH", "-" * 62]
    for event in events:
        if event["kind"] == "opened":
            lines.append(f"UNAVAILABLE  ·  {event['source']}")
            lines.append(
                f"    failed {source_health.FAILURES_TO_OPEN_INCIDENT} consecutive checks; "
                f"latest: {event.get('error') or 'unknown failure'}"
            )
            lines.append("    This is a state-change alert and will not repeat while it stays unavailable.")
        else:
            lines.append(f"RECOVERED  ·  {event['source']}")
            lines.append(
                f"    checked successfully {source_health.SUCCESSES_TO_CLOSE_INCIDENT} consecutive times "
                f"after {human_duration(event.get('opened_at'), event.get('at'))}."
            )
        lines.append("")

    if include_ongoing:
        ongoing = source_health.active_incidents(state)
        if ongoing:
            lines.append("ONGOING UNAVAILABLE SOURCES  ·  no repeat alert")
            for incident in ongoing:
                since = incident.get("opened_at") or "unknown time"
                lines.append(f"    {incident['source']} — since {since}")
            lines.append("")

    return "\n".join(lines).rstrip()


def health_subject(events):
    opened = [event["source"] for event in events if event["kind"] == "opened"]
    recovered = [event["source"] for event in events if event["kind"] == "recovered"]

    def names(values):
        if len(values) <= 3:
            return ", ".join(values)
        return ", ".join(values[:3]) + f" +{len(values) - 3}"

    if opened and not recovered:
        return f"[bid-hunter] Source health: {names(opened)} unavailable"
    if recovered and not opened:
        return f"[bid-hunter] Source health: {names(recovered)} recovered"
    return (f"[bid-hunter] Source health changed: {len(opened)} unavailable, "
            f"{len(recovered)} recovered")


def deliver_requested_mail(real_send, requested, events, state):
    """Send actual leads plus state transitions; suppress empty failure noise."""
    actionable = next((mail for mail in reversed(requested) if actionable_digest(mail["text"])), None)

    if actionable:
        section = health_text(events, state, include_ongoing=True)
        body = actionable["text"]
        if section:
            body += "\n\n" + section
        subject = actionable["subject"]
        if events:
            subject += " / source health changed"
        real_send(subject, body)
        return True

    if events:
        real_send(health_subject(events), health_text(events, state))
        return True

    scraper.log("no actionable lead, deadline, or source-health state change; no email sent")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lookback-hours", type=int,
                    default=scraper.DEFAULT_LOOKBACK_HOURS)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return source_health.self_test()

    try:
        import envfile
        if Path(".env").exists():
            envfile.load_into_environ(".env", override=False)
    except Exception as exc:
        scraper.log(f"note: .env not loaded ({exc}); relying on real env vars")

    cfg = load_config()
    if args.dry_run:
        return scraper.run("all", cfg, dry_run=True, lookback_hours=args.lookback_hours)

    try:
        result, requested, real_send = capture_delivery(cfg, args)
        active_sources = active_source_keys(cfg)
        outcomes = outcomes_from_stats(active_sources) if result == 0 else None
        all_sources_unavailable = False
        if outcomes is None and result != 0:
            outcomes = outcomes_from_total_failure(active_sources)
            all_sources_unavailable = outcomes is not None

        # A code crash or an incomplete run has no trustworthy outcome map.
        # Leave it non-zero for the workflow's unexpected-failure alarm.
        if outcomes is None:
            return result

        state = source_health.load_state(HEALTH_PATH)
        state, events = source_health.update_state(state, outcomes)
        source_health.save_state(HEALTH_PATH, state)
        deliver_requested_mail(real_send, requested, events, state)

        if all_sources_unavailable:
            scraper.log("all sources unavailable; recorded one durable source-health incident instead of a repeating per-run alarm")
            # This is a source-availability condition, not a crash. The state
            # file has been persisted and will notify only on transition/recovery.
            return 0
        return result
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
