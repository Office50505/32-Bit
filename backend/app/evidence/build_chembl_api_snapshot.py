import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.evidence.chembl_api import (
    ChemblApiImportStats,
    ChemblApiSelection,
    acquire_chembl_api_snapshot,
    import_chembl_api_snapshot,
    inspect_frozen_chembl_api_snapshot,
)
from app.evidence.retractions import FrozenRetractionIndex
from app.evidence.store import EvidenceStore, EvidenceStoreError

_SELECTION_KEYS = frozenset(
    {"expected_release", "molecule_chembl_ids", "target_chembl_ids", "endpoints"}
)


def load_api_selection(path: str | Path) -> ChemblApiSelection:
    selection_path = Path(path)
    try:
        payload: Any = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceStoreError(f"cannot read API selection manifest: {selection_path}") from error
    if not isinstance(payload, dict):
        raise EvidenceStoreError("API selection manifest must be a JSON object")
    if unknown_keys := sorted(set(payload) - _SELECTION_KEYS):
        raise EvidenceStoreError(f"unknown API selection-manifest fields: {unknown_keys}")
    try:
        release = payload["expected_release"]
        molecules = tuple(payload["molecule_chembl_ids"])
        targets = tuple(payload["target_chembl_ids"])
        endpoints = tuple(payload.get("endpoints", ("IC50", "EC50", "Ki", "Kd")))
    except (KeyError, TypeError) as error:
        raise EvidenceStoreError(
            "API selection requires expected_release, molecule_chembl_ids, and "
            "target_chembl_ids"
        ) from error
    if not isinstance(release, str) or not all(
        isinstance(value, str) for value in (*molecules, *targets, *endpoints)
    ):
        raise EvidenceStoreError("all API selection fields and identifiers must be strings")
    return ChemblApiSelection(
        expected_release=release,
        molecule_chembl_ids=molecules,
        target_chembl_ids=targets,
        endpoints=endpoints,
    )


def build_api_snapshot(
    *,
    raw_directory: str | Path,
    output_database: str | Path,
    snapshot_id: str,
    created_at: str,
    retraction_watch_csv: str | Path,
) -> tuple[ChemblApiImportStats, str]:
    output_path = Path(output_database).resolve()
    if output_path.exists():
        raise EvidenceStoreError(f"refusing to overwrite existing output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".building",
        dir=output_path.parent,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()
    try:
        retraction_index = FrozenRetractionIndex.from_csv(retraction_watch_csv)
        with EvidenceStore.create(temporary_path) as store:
            stats = import_chembl_api_snapshot(
                store,
                raw_directory=raw_directory,
                snapshot_id=snapshot_id,
                created_at=created_at,
                retraction_index=retraction_index,
            )
            content_hash = store.verified_snapshot_hash(snapshot_id)
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return stats, content_hash


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire a release-pinned ChEMBL API corpus and build a sealed local evidence DB."
        )
    )
    parser.add_argument("--selection", required=True, help="Pinned API selection JSON")
    parser.add_argument("--raw-dir", required=True, help="New or existing frozen response folder")
    parser.add_argument("--output", required=True, help="New evidence SQLite output path")
    parser.add_argument("--snapshot-id", required=True, help="Immutable snapshot identifier")
    parser.add_argument(
        "--created-at",
        required=True,
        help="Explicit ISO-8601 snapshot timestamp; never generated implicitly",
    )
    parser.add_argument(
        "--retraction-watch-csv",
        required=True,
        help="Frozen Crossref Retraction Watch CSV used to screen source papers",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Require --raw-dir to exist; make no network requests",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selection = load_api_selection(args.selection)
    raw_path = Path(args.raw_dir).resolve()
    if raw_path.exists():
        if not raw_path.is_dir():
            raise EvidenceStoreError(f"raw ChEMBL path is not a directory: {raw_path}")
        frozen_manifest = inspect_frozen_chembl_api_snapshot(raw_path)
        if frozen_manifest.selection != selection:
            raise EvidenceStoreError(
                "existing raw ChEMBL snapshot does not match the requested selection"
            )
    elif args.offline:
        raise EvidenceStoreError(f"offline raw ChEMBL snapshot does not exist: {raw_path}")
    else:
        acquire_chembl_api_snapshot(
            raw_path,
            selection=selection,
            retrieved_at=args.created_at,
        )
        frozen_manifest = inspect_frozen_chembl_api_snapshot(raw_path)

    stats, content_hash = build_api_snapshot(
        raw_directory=raw_path,
        output_database=args.output,
        snapshot_id=args.snapshot_id,
        created_at=args.created_at,
        retraction_watch_csv=args.retraction_watch_csv,
    )
    print(
        json.dumps(
            {
                "snapshot_id": args.snapshot_id,
                "content_sha256": content_hash,
                "release": selection.expected_release,
                "raw_source_sha256": frozen_manifest.source_sha256,
                "counts": {
                    "molecules": stats.molecules,
                    "targets": stats.targets,
                    "target_components": stats.target_components,
                    "papers": stats.papers,
                    "assays": stats.assays,
                    "activities": stats.activities,
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
