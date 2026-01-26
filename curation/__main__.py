"""
CLI entry point for running curation once or exporting for fine-tuning.
  pipenv run python -m curation              # run one curation pass
  pipenv run python -m curation --export out.jsonl   # export JSONL for fine-tuning
Uses TALKIE_CONFIG or default config.yaml for db_path and curation section.
"""
from __future__ import annotations

import argparse
import logging
import sys

from config import load_config
from curation.export import export_for_finetuning
from curation.scheduler import run_curation_from_config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Run curation or export for fine-tuning")
    parser.add_argument(
        "--export",
        metavar="FILE",
        help="Export interactions to JSONL file for fine-tuning instead of running curation",
    )
    parser.add_argument("--limit", type=int, default=5000, help="Max rows for export (default 5000)")
    args = parser.parse_args()

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    persistence = config.get("persistence", {})
    db_path = persistence.get("db_path", "data/talkie.db")

    if args.export:
        llm_cfg = config.get("llm", {})
        system_instruction = llm_cfg.get("export_instruction") or llm_cfg.get("system_prompt")
        n = export_for_finetuning(
            db_path,
            args.export,
            limit=args.limit,
            system_instruction=system_instruction,
        )
        print("exported", n, "records to", args.export)
    else:
        curation_config = config.get("curation", {})
        counts = run_curation_from_config(db_path, curation_config)
        print("curation done:", counts)


if __name__ == "__main__":
    main()
