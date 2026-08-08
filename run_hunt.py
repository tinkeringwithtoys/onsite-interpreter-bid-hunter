#!/usr/bin/env python3
"""Run every enabled Bid Hunter source in one unified two-hour pass.

This wrapper is deliberately small. It supplies a runtime `all` lane to the
existing config rather than duplicating the 22-source configuration in another
file. `scraper.select_sources(..., 'all')` selects every source with
`poll: true`, regardless of whether it is JSON, HTTP, Playwright, or open-web
discovery.

The workflow installs Chromium, so browser-only sources can run in the same
job as APIs and static portals. Sources configured `poll: false` remain parked:
no scheduler can make a login/certificate-only or duplicate source usable.

Usage:
    python run_hunt.py
    python run_hunt.py --dry-run
    python run_hunt.py --lookback-hours 24
"""

import argparse
import traceback
from pathlib import Path

import yaml

import scraper

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
HUNT_TIMEOUT_MINUTES = 55


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    lanes = cfg.setdefault("scheduling", {}).setdefault("lanes", {})
    # No `polls` list is intentional: scraper.select_sources selects every
    # poll:true source when a lane has no explicit list.
    lanes["all"] = {
        "timeout_minutes": HUNT_TIMEOUT_MINUTES,
        "concurrency_group": "bid-hunter-all",
    }
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lookback-hours", type=int,
                    default=scraper.DEFAULT_LOOKBACK_HOURS)
    args = ap.parse_args()

    try:
        import envfile
        if Path(".env").exists():
            envfile.load_into_environ(".env", override=False)
    except Exception as exc:
        scraper.log(f"note: .env not loaded ({exc}); relying on real env vars")

    try:
        return scraper.run("all", load_config(), dry_run=args.dry_run,
                           lookback_hours=args.lookback_hours)
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
