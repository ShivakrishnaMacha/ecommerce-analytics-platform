"""Orchestrate the pipeline: generate -> validate -> transform.

Exits non-zero if any data-quality check fails.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from pipeline.generate_data import generate  # noqa: E402
from pipeline.transform import build  # noqa: E402
from pipeline.validate import run_checks  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

TINY = {"n_customers": 200, "n_orders": 1000}
FULL = {"n_customers": 5000, "n_orders": 60000}


def run(scale: str = "full", skip_generate: bool = False) -> dict:
    raw_dir = BASE_DIR / "data" / "raw"
    started = time.time()
    summary: dict = {}

    if not skip_generate:
        t0 = time.time()
        params = TINY if scale == "tiny" else FULL
        summary["generated"] = generate(raw_dir, **params)
        log.info("extract: generated raw tables %s (%.1fs)",
                 summary["generated"], time.time() - t0)
    else:
        log.info("extract: skipped (--skip-generate)")

    t0 = time.time()
    checks = run_checks(raw_dir)
    failed = [c for c in checks if not c["passed"]]
    summary["checks_passed"] = len(checks) - len(failed)
    summary["checks_total"] = len(checks)
    for c in failed:
        log.error("validate FAILED: %s.%s %s",
                  c["table"], c["check"], c["details"])
    if failed:
        raise RuntimeError(
            f"{len(failed)}/{len(checks)} data-quality checks failed — aborting")
    log.info("validate: %d/%d checks passed (%.1fs)",
             summary["checks_passed"], summary["checks_total"],
             time.time() - t0)

    t0 = time.time()
    summary["warehouse"] = build(raw_dir)
    log.info("transform+load: warehouse tables %s (%.1fs)",
             summary["warehouse"], time.time() - t0)

    summary["elapsed_s"] = round(time.time() - started, 1)
    log.info("pipeline complete in %ss", summary["elapsed_s"])
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the e-commerce pipeline")
    parser.add_argument("--scale", choices=["tiny", "full"], default="full")
    parser.add_argument("--skip-generate", action="store_true",
                        help="reuse existing raw CSVs")
    args = parser.parse_args()
    try:
        run(scale=args.scale, skip_generate=args.skip_generate)
    except RuntimeError as exc:
        log.error(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
