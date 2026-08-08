#!/usr/bin/env python3
"""Static guard for the unified two-hour Hunt workflow.

This script protects the operating model that must never drift:

- exactly one scheduled Hunt, every two hours;
- one concurrency group and one state writer;
- a 55-minute runtime budget that agrees with the wrapper;
- Chromium for browser-capable sources;
- stateful source-health persistence;
- an alarm for unexpected workflow failures.

No network, secrets, or live portals are used here.
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
RETIRED_WORKFLOWS = ("fast.yml", "standard.yml", "heavy.yml")


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
        for problem in problems:
            print(f"x {problem}")
        return 1

    for retired in RETIRED_WORKFLOWS:
        if (WORKFLOW.parent / retired).exists():
            problems.append(f"retired workflow still exists: {retired}")

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
    if "source_health.json" not in runs:
        problems.append("Hunt workflow does not persist source_health.json")
    alarms = [step for step in steps
              if str(step.get("if", "")).strip() == "failure()"
              and "--notify-failure" in str(step.get("run", ""))]
    if not alarms:
        problems.append("Hunt workflow has no unexpected-failure alarm")

    cfg = load_yaml(ROOT / "config.yaml")
    active = [source.get("key") for source in cfg.get("sources", []) if source.get("poll")]
    if not active:
        problems.append("config.yaml has no poll:true sources for the unified Hunt")

    print("=" * 74)
    print("UNIFIED HUNT PARITY  (static, no network)")
    print("=" * 74)
    if problems:
        for problem in problems:
            print(f"  x {problem}")
        print(f"\nFAILED: {len(problems)} problem(s)")
        return 1
    print("  OK -- one every-two-hour state writer")
    print(f"       all {len(active)} enabled sources selected at runtime")
    print("       browser installed, stateful source health, timeout, and alarm verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
