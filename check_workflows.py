#!/usr/bin/env python3
"""
check_workflows.py -- static gate against workflow / config drift.

WHY THIS EXISTS

scraper.py derives its LLM scoring budget from
    scheduling.lanes.<lane>.timeout_minutes   (config.yaml)
but the job that actually gets killed is governed by
    jobs.<job>.timeout-minutes                (.github/workflows/<lane>.yml)

Two numbers, two files, nothing tying them together. If the workflow number
is the smaller one, the "budget" is a lie and the run dies mid-scoring with no
digest and no error mail -- which is exactly what happened at 10m16s on the
standard lane.

It also enforces the failure alarms. A lane that loses its `if: failure()`
step does not go quiet loudly; it goes quiet silently, and in an inbox that is
indistinguishable from "no new opportunities".

All checks are static. No network, no secrets, runs in under a second.

    python3 check_workflows.py
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
LANE_FILES = {
    "fast": WORKFLOW_DIR / "fast.yml",
    "standard": WORKFLOW_DIR / "standard.yml",
    "heavy": WORKFLOW_DIR / "heavy.yml",
}


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def triggers(wf):
    """PyYAML parses the bare key `on` as the boolean True (YAML 1.1)."""
    if "on" in wf:
        return wf["on"] or {}
    return wf.get(True) or {}


def crons(wf):
    schedule = triggers(wf).get("schedule") or []
    return [s.get("cron") for s in schedule if isinstance(s, dict)]


def main():
    problems, warnings = [], []

    cfg = load_yaml(ROOT / "config.yaml")
    scheduling = cfg.get("scheduling") or {}
    lanes = scheduling.get("lanes") or {}
    sources = cfg.get("sources") or []
    source_by_key = {s.get("key"): s for s in sources if s.get("key")}

    for lane, path in LANE_FILES.items():
        if not path.exists():
            problems.append(f"{lane}: {path.name} is missing")
            continue

        wf = load_yaml(path)
        lane_cfg = lanes.get(lane) or {}
        if not lane_cfg:
            problems.append(f"{lane}: no scheduling.lanes.{lane} block in config.yaml")
            continue

        jobs = wf.get("jobs") or {}
        if not jobs:
            problems.append(f"{lane}: {path.name} defines no jobs")
            continue
        job = next(iter(jobs.values()))

        # 1. TIMEOUT PARITY. The one that killed the standard lane.
        wf_timeout = job.get("timeout-minutes")
        cfg_timeout = lane_cfg.get("timeout_minutes")
        if wf_timeout is None:
            problems.append(
                f"{lane}: job has no timeout-minutes. The default is 360, so a "
                f"single hang burns 18% of the monthly allowance."
            )
        elif cfg_timeout is None:
            problems.append(
                f"{lane}: config has no scheduling.lanes.{lane}.timeout_minutes, "
                f"so scraper.py silently budgets scoring for 10 minutes."
            )
        elif int(wf_timeout) != int(cfg_timeout):
            problems.append(
                f"{lane}: TIMEOUT DRIFT - the workflow kills the job at "
                f"{wf_timeout} min but scraper.py budgets scoring against "
                f"config's {cfg_timeout} min. Make them equal."
            )

        # 2. The alarm must exist, in every lane, always.
        steps = job.get("steps") or []
        alarms = [
            s for s in steps
            if str(s.get("if", "")).strip() == "failure()"
            and "--notify-failure" in str(s.get("run", ""))
        ]
        if not alarms:
            problems.append(
                f"{lane}: no `if: failure()` step running --notify-failure. "
                f"A broken lane would look exactly like a quiet week."
            )

        # 3. Cron parity, so the documented cadence is the real cadence.
        cfg_cron = lane_cfg.get("cron_utc")
        wf_crons = crons(wf)
        if cfg_cron and cfg_cron not in wf_crons:
            problems.append(
                f"{lane}: cron drift - config says {cfg_cron!r}, workflow says "
                f"{wf_crons!r}"
            )

        # 4. Concurrency, so two runs never write state at once.
        cfg_group = lane_cfg.get("concurrency_group")
        wf_group = (wf.get("concurrency") or {}).get("group")
        if not wf_group:
            problems.append(f"{lane}: no concurrency group - overlapping runs can clobber state")
        elif cfg_group and wf_group != cfg_group:
            problems.append(
                f"{lane}: concurrency group drift - config {cfg_group!r} vs workflow {wf_group!r}"
            )

        # 5. A lane cannot poll a source that does not exist.
        for key in lane_cfg.get("polls") or []:
            src = source_by_key.get(key)
            if src is None:
                problems.append(f"{lane}: polls '{key}', which is not a source in config.yaml")
            elif not src.get("poll"):
                warnings.append(
                    f"{lane}: names '{key}' but that source is poll:false, so it is "
                    f"skipped at runtime. Remove it from the lane or enable it."
                )

    # 6. Sources that think they are on but no lane ever runs them.
    laned = {k for lane_cfg in lanes.values() for k in (lane_cfg.get("polls") or [])}
    for key, src in source_by_key.items():
        if src.get("poll") and key not in laned:
            warnings.append(
                f"{key}: poll:true but no lane lists it, so it never runs under any schedule"
            )

    # 7. The budget claim has to stay true -- but only while the repo is
    # private. A public repo has unlimited Actions minutes, so the gate is
    # skipped when budget.repo_public is set (flipped 2026-08-08).
    budget = scheduling.get("budget") or {}
    est = budget.get("estimated_monthly_minutes")
    cap = budget.get("free_tier_private_repo_minutes")
    repo_public = bool(budget.get("repo_public"))
    if not repo_public and isinstance(est, int) and isinstance(cap, int) and est > cap:
        problems.append(
            f"budget: estimated {est} min/month exceeds the {cap} min free allowance"
        )

    print("=" * 74)
    print("WORKFLOW / CONFIG PARITY  (static, no network)")
    print("=" * 74)
    for w in warnings:
        print(f"  ! {w}")
    if problems:
        for p in problems:
            print(f"  x {p}")
        print(f"\nFAILED: {len(problems)} problem(s)\n")
        return 1
    print(f"  OK -- {len(LANE_FILES)} lanes checked")
    print("       timeouts match config, so the scoring budget is real")
    print("       crons and concurrency groups match config")
    print("       every lane still has its if: failure() alarm")
    if repo_public:
        print("       budget gate skipped (repo is public - unlimited minutes)")
    if warnings:
        print(f"       {len(warnings)} warning(s) above are not build failures")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
