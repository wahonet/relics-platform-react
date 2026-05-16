"""Data pipeline orchestrator.

Usage:
    python run_pipeline.py
    python run_pipeline.py --from 02
    python run_pipeline.py --to 04
    python run_pipeline.py --only 03
    python run_pipeline.py --skip 01 --skip 05
    python run_pipeline.py --list
    python run_pipeline.py --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from _common import PROJECT_ROOT, detect_features, get_logger, load_config

SCRIPTS_DIR = Path(__file__).resolve().parent


STEPS = [
    {
        "id": "01",
        "name": "Convert DOCX archives to Markdown",
        "script": "step01_convert_docs.py",
        "requires": ["archives"],
        "optional": False,
    },
    {
        "id": "02",
        "name": "Build structured dataset",
        "script": "step02_build_dataset.py",
        "requires": [],
        "optional": False,
    },
    {
        "id": "03",
        "name": "Extract photos",
        "script": "step03_extract_photos.py",
        "requires": ["archives"],
        "optional": False,
    },
    {
        "id": "04",
        "name": "Extract drawings",
        "script": "step04_extract_drawings.py",
        "requires": ["archives"],
        "optional": False,
    },
    {
        "id": "05",
        "name": "Convert worklogs to PDF",
        "script": "step05_convert_worklogs.py",
        "requires": ["worklogs"],
        "optional": True,
    },
    {
        "id": "06",
        "name": "Prepare administrative boundaries",
        "script": "step06_prepare_boundaries.py",
        "requires": ["boundaries"],
        "optional": True,
    },
    {
        "id": "07",
        "name": "Build SQLite database",
        "script": "step07_build_db.py",
        "requires": [],
        "optional": False,
    },
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Relics Platform data pipeline")
    p.add_argument("--from", dest="from_id", default=None, help="Start step id, for example 02")
    p.add_argument("--to", dest="to_id", default=None, help="End step id, inclusive, for example 04")
    p.add_argument("--only", dest="only_id", default=None, help="Run only one step id, for example 03")
    p.add_argument("--skip", dest="skip_ids", action="append", default=[],
                   help="Skip a step id. Can be repeated, for example --skip 01 --skip 05")
    p.add_argument("--list", action="store_true", help="List all steps and exit")
    p.add_argument("--dry-run", action="store_true", help="Print planned steps without running them")
    return p.parse_args()


def _list_steps() -> None:
    print("Pipeline steps:")
    for s in STEPS:
        tag = "[optional]" if s["optional"] else "[required]"
        print(f"  {s['id']}  {tag}  {s['name']}  ({s['script']})")


def _select_steps(args: argparse.Namespace) -> list[dict]:
    skip = set(args.skip_ids or [])
    if args.only_id:
        return [s for s in STEPS if s["id"] == args.only_id and s["id"] not in skip]
    selected = STEPS[:]
    if args.from_id:
        selected = [s for s in selected if s["id"] >= args.from_id]
    if args.to_id:
        selected = [s for s in selected if s["id"] <= args.to_id]
    if skip:
        selected = [s for s in selected if s["id"] not in skip]
    return selected


def _run_step(step: dict, log) -> int:
    script_path = SCRIPTS_DIR / step["script"]
    if not script_path.exists():
        log.error("Script not found: %s", script_path)
        return 1
    log.info("-> start step%s: %s", step["id"], step["name"])
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(SCRIPTS_DIR),
    )
    dt = time.time() - t0
    if proc.returncode == 0:
        log.info("OK step%s completed in %.1fs", step["id"], dt)
    else:
        log.error("FAIL step%s exited with %s in %.1fs", step["id"], proc.returncode, dt)
    return proc.returncode


def main() -> int:
    args = _parse_args()
    if args.list:
        _list_steps()
        return 0

    log = get_logger("pipeline")
    selected = _select_steps(args)

    if not selected:
        log.error("No matching steps")
        return 2

    if not args.dry_run:
        try:
            load_config()
        except FileNotFoundError as e:
            log.error(str(e))
            return 2

    features = detect_features().as_dict

    log.info("Project root: %s", PROJECT_ROOT)
    log.info("Input feature status: %s", features)
    log.info("Planned steps: %d", len(selected))

    for step in selected:
        needs = step["requires"]
        missing = [r for r in needs if not features.get(r, False)]

        if args.dry_run:
            if missing and not step["optional"]:
                log.info("[dry-run] step%s: %s (would fail, missing %s)",
                         step["id"], step["name"], missing)
            elif missing and step["optional"]:
                log.info("[dry-run] step%s: %s (would skip optional, missing %s)",
                         step["id"], step["name"], missing)
            else:
                log.info("[dry-run] step%s: %s", step["id"], step["name"])
            continue

        if missing:
            if step["optional"]:
                log.warning("Skip optional step%s, missing input: %s", step["id"], missing)
                continue
            log.error("step%s requires missing input: %s", step["id"], missing)
            return 3

        rc = _run_step(step, log)
        if rc != 0:
            log.error("Pipeline stopped at step%s", step["id"])
            return rc

    if args.dry_run:
        log.info("[dry-run] plan printed; no step was executed")
    else:
        log.info("All selected steps completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
