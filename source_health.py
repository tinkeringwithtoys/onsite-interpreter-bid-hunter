#!/usr/bin/env python3
"""Persistent, stateful source-health incidents for the unified Hunt.

A scheduled procurement system must not email the same source error every run.
This module records source outcomes across runs and emits events only when a
source changes stable state:

- two consecutive failed checks open one incident;
- while degraded, later failures are recorded but do not notify again;
- two consecutive successful checks close the incident with one recovery event.

It deliberately has no network or email code. The Hunt owns delivery; this
module owns the durable state machine and its offline tests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

SCHEMA_VERSION = 1
FAILURES_TO_OPEN_INCIDENT = 2
SUCCESSES_TO_CLOSE_INCIDENT = 2
MAX_ERROR_LENGTH = 240


def _utc(now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(dt.timezone.utc)


def _iso(now: dt.datetime | None = None) -> str:
    return _utc(now).isoformat()


def _count(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def clean_error(error) -> str:
    """Keep a useful diagnostic without persisting full URLs or response pages."""
    text = " ".join(str(error or "unknown failure").split())
    text = re.sub(r"https?://\S+", "<url>", text)
    return text[:MAX_ERROR_LENGTH]


def normalise_state(state) -> dict:
    state = state if isinstance(state, dict) else {}
    sources = state.get("sources")
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": sources if isinstance(sources, dict) else {},
    }


def load_state(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return normalise_state(json.load(fh))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return normalise_state({})


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(normalise_state(state), fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def update_state(state: dict, outcomes: dict[str, str | None], now: dt.datetime | None = None):
    """Apply one Hunt's per-source outcomes and return ``(state, events)``.

    ``outcomes`` maps a source key to ``None`` for a successful check or a
    short error string for a failed check. Events have ``kind`` values
    ``opened`` or ``recovered`` and are intentionally suitable for one email.
    """
    state = normalise_state(state)
    records = state["sources"]
    stamp = _iso(now)
    events = []

    for source in sorted(str(key) for key in outcomes if str(key)):
        error = outcomes[source]
        record = records.get(source)
        if not isinstance(record, dict):
            record = {}
        status = record.get("status") if record.get("status") in {"healthy", "degraded"} else "healthy"

        if error:
            failures = _count(record.get("consecutive_failures")) + 1
            record["consecutive_failures"] = failures
            record["consecutive_successes"] = 0
            record["last_failure_at"] = stamp
            record["last_error"] = clean_error(error)
            if failures == 1:
                record["first_failure_at"] = stamp

            if status != "degraded" and failures >= FAILURES_TO_OPEN_INCIDENT:
                status = "degraded"
                record["status"] = status
                record["incident_opened_at"] = record.get("first_failure_at") or stamp
                record["suppressed_failures"] = 0
                events.append({
                    "kind": "opened",
                    "source": source,
                    "at": stamp,
                    "opened_at": record["incident_opened_at"],
                    "error": record["last_error"],
                })
            elif status == "degraded":
                record["status"] = status
                record["suppressed_failures"] = _count(record.get("suppressed_failures")) + 1
            else:
                record["status"] = "healthy"

        else:
            successes = _count(record.get("consecutive_successes")) + 1
            record["consecutive_successes"] = successes
            record["consecutive_failures"] = 0
            record["last_success_at"] = stamp

            if status == "degraded" and successes >= SUCCESSES_TO_CLOSE_INCIDENT:
                opened_at = record.get("incident_opened_at") or record.get("first_failure_at")
                record.update({
                    "status": "healthy",
                    "incident_opened_at": None,
                    "first_failure_at": None,
                    "last_error": None,
                    "suppressed_failures": 0,
                    "last_recovered_at": stamp,
                })
                events.append({
                    "kind": "recovered",
                    "source": source,
                    "at": stamp,
                    "opened_at": opened_at,
                })
            elif status == "degraded":
                # One successful response is not enough to call an unstable
                # source healthy; wait for the second consecutive success.
                record["status"] = "degraded"
            else:
                record.update({
                    "status": "healthy",
                    "first_failure_at": None,
                    "incident_opened_at": None,
                    "last_error": None,
                    "suppressed_failures": 0,
                })

        record["updated_at"] = stamp
        records[source] = record

    return state, events


def active_incidents(state: dict) -> list[dict]:
    records = normalise_state(state)["sources"]
    out = []
    for source, record in records.items():
        if isinstance(record, dict) and record.get("status") == "degraded":
            out.append({
                "source": source,
                "opened_at": record.get("incident_opened_at") or record.get("first_failure_at"),
                "last_error": record.get("last_error"),
            })
    return sorted(out, key=lambda row: row["source"])


def self_test() -> int:
    failures = []

    def check(name, condition):
        if not condition:
            failures.append(name)

    state = {}
    t0 = dt.datetime(2026, 8, 8, 8, 0, tzinfo=dt.timezone.utc)
    state, events = update_state(state, {"tuneps": "HTTP 403 https://example.test/secret"}, t0)
    check("first failure stays quiet", events == [])
    check("first failure is healthy pending threshold", state["sources"]["tuneps"]["status"] == "healthy")

    state, events = update_state(state, {"tuneps": "HTTP 403"}, t0 + dt.timedelta(hours=2))
    check("second failure opens one incident", len(events) == 1 and events[0]["kind"] == "opened")
    check("incident is degraded", state["sources"]["tuneps"]["status"] == "degraded")

    state, events = update_state(state, {"tuneps": "HTTP 403"}, t0 + dt.timedelta(hours=4))
    check("ongoing outage stays quiet", events == [])
    check("incident remains active", len(active_incidents(state)) == 1)

    state, events = update_state(state, {"tuneps": None}, t0 + dt.timedelta(hours=6))
    check("first success does not recover", events == [])
    check("first success remains degraded", state["sources"]["tuneps"]["status"] == "degraded")

    state, events = update_state(state, {"tuneps": None}, t0 + dt.timedelta(hours=8))
    check("second success emits recovery", len(events) == 1 and events[0]["kind"] == "recovered")
    check("recovery returns healthy", state["sources"]["tuneps"]["status"] == "healthy")
    check("error redacts URL", "<url>" in clean_error("HTTP https://portal.example/x"))

    if failures:
        print("SOURCE HEALTH SELF-TEST FAILED")
        for failure in failures:
            print(f"  x {failure}")
        return 1
    print("SOURCE HEALTH SELF-TEST PASSED (10/10 checks)")
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
