#!/usr/bin/env python3
"""Static guard for the unified two-hour Hunt workflow.

The repository is public and runs one scheduled workflow instead of separate
Fast / Standard / Heavy state writers. This script protects the things that
must never drift:

- actual cron is every two hours
- job timeout agrees with run_hunt.py's scoring budget
- one concurrency group owns state writes
- an if: failure() email alarm remains
- the workflow runs the all-source wrapper and installs Chromium

No network, secrets or live portals are used here.
"""

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "hunt.yml"
WRAPPER = ROOT / "run_hunt.py"
EXPECTED_CRON = "0 */2 * * *"
EXPECTED_GROUP = "bid-hunter-all"


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def triggers(workflow):
    # PyYAML 1.1 parses bare `on` as True.
    return workflow.get("on") or workflow.get(True) or {}


def wrapper_timeout():
    tree = ast.parse(WRAPPER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "HUNT_TIMEOUT_MINUTES":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                        return node.value.value
    return None


def main():
    problems = []
    if not WORKFLOW.exists():
        problems.append("hunt.yml is missing")
    if not WRAPPER.exists():
        problems.append("run_hunt.py is missing")
    if problems:
        for p in problems:
            print(f"x {p}")
        return 1

    workflow = load_yaml(WORKFLOW)
    schedule = triggers(workflow).get("schedule") or []
    crons = [row.get("cron") for row in schedule if isinstance(row, dict)]
    if crons != [EXPECTED_CRON]:
        problems.append(f"cron drift: expected {EXPECTED_CRON!r}, got {crons!r}")

    group = (workflow.get("concurrency") or {}).get("group")
    if group != EXPECTED_GROUP:
        problems.append(f"concurrency drift: expected {EXPECTED_GROUP!r}, got {group!r}")

    jobs = workflow.get("jobs") or {}
    job = jobs.get("hunt") or {}
    timeout = job.get("timeout-minutes")
    wrapper = wrapper_timeout()
    if wrapper is None:
        problems.append("could not read HUNT_TIMEOUT_MINUTES from run_hunt.py")
    elif timeout != wrapper:
        problems.append(f"timeout drift: workflow {timeout!r} vs wrapper {wrapper!r}")

    steps = job.get("steps") or []
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    if "python run_hunt.py" not in runs:
        problems.append("Hunt workflow does not run run_hunt.py")
    if "playwright install chromium" not in runs:
        problems.append("Hunt workflow does not install Chromium")
    alarms = [step for step in steps
              if str(step.get("if", "")).strip() == "failure()"
              and "--notify-failure" in str(step.get("run", ""))]
    if not alarms:
        problems.append("Hunt workflow has no if: failure() notification alarm")

    cfg = load_yaml(ROOT / "config.yaml")
    active = [source.get("key") for source in cfg.get("sources", []) if source.get("poll")]
    if not active:
        problems.append("config.yaml has no poll:true sources for the unified hunt")

    print("=" * 74)
    print("UNIFIED HUNT PARITY  (static, no network)")
    print("=" * 74)
    if problems:
        for p in problems:
            print(f"  x {p}")
        print(f"\nFAILED: {len(problems)} problem(s)")
        return 1
    print("  OK -- one every-two-hour state writer")
    print(f"       all {len(active)} enabled sources selected at runtime")
    print("       browser installed, timeout real, failure alarm present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
