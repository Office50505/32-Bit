#!/usr/bin/env python3
"""Recompute a stored ProvenanceLab run and verify its locked output."""

import argparse
import json
import os

from app.services.runs import replay_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="Persisted ProvenanceLab run ID")
    parser.add_argument(
        "--database",
        help="Optional path to the SQLite run database",
    )
    arguments = parser.parse_args()
    if arguments.database:
        os.environ["PROVENANCELAB_DB_PATH"] = arguments.database
    verification = replay_run(arguments.run_id)
    if verification is None:
        parser.error(f"run not found: {arguments.run_id}")
    print(json.dumps(verification.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if verification.reproducible else 1


if __name__ == "__main__":
    raise SystemExit(main())
