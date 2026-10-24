import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.evidence.chembl36 import (
    Chembl36Extractor,
    Chembl36Selection,
    ChemblExtractionStats,
    sha256_file,
)
from app.evidence.store import EvidenceStore, EvidenceStoreError

_SELECTION_KEYS = frozenset({"molecule_chembl_ids", "target_chembl_ids", "endpoints"})


def load_selection(path: str | Path) -> Chembl36Selection:
    selection_path = Path(path)
    try:
        payload: Any = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceStoreError(f"cannot read selection manifest: {selection_path}") from error
    if not isinstance(payload, dict):
        raise EvidenceStoreError("selection manifest must be a JSON object")
    unknown_keys = sorted(set(payload) - _SELECTION_KEYS)
    if unknown_keys:
        raise EvidenceStoreError(f"unknown selection-manifest fields: {unknown_keys}")
    try:
        molecules = tuple(payload["molecule_chembl_ids"])
        targets = tuple(payload["target_chembl_ids"])
        endpoints = tuple(payload.get("endpoints", ("IC50", "EC50", "Ki", "Kd")))
    except (KeyError, TypeError) as error:
        raise EvidenceStoreError(
            "selection manifest requires molecule_chembl_ids and target_chembl_ids arrays"
        ) from error
    if not all(isinstance(value, str) for value in (*molecules, *targets, *endpoints)):
        raise EvidenceStoreError("all selection-manifest identifiers must be strings")
    return Chembl36Selection(
        molecule_chembl_ids=molecules,
        target_chembl_ids=targets,
        endpoints=endpoints,
    )


def build_snapshot(
    *,
    source_database: str | Path,
    output_database: str | Path,
    selection: Chembl36Selection,
    snapshot_id: str,
    created_at: str,
    extracted_database_sha256: str | None = None,
) -> tuple[ChemblExtractionStats, str, str]:
    output_path = Path(output_database).resolve()
    if output_path.exists():
        raise EvidenceStoreError(f"refusing to overwrite existing output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_hash = extracted_database_sha256 or sha256_file(source_database)
    temporary_file = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".building",
        dir=output_path.parent,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()
    try:
        with EvidenceStore.create(temporary_path) as store:
            with store.batch():
                with Chembl36Extractor(source_database) as extractor:
                    stats = extractor.extract(
                        destination=store,
                        snapshot_id=snapshot_id,
                        selection=selection,
                        extracted_database_sha256=extracted_hash,
                        created_at=created_at,
                    )
                content_hash = store.seal_snapshot(snapshot_id)
            if not store.verify_snapshot(snapshot_id):
                raise EvidenceStoreError("sealed snapshot failed its content-hash verification")
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return stats, content_hash, extracted_hash


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a sealed ProvenanceLab pilot snapshot from ChEMBL 36 SQLite."
    )
    parser.add_argument("--source-db", required=True, help="Unpacked official ChEMBL 36 SQLite DB")
    parser.add_argument("--selection", required=True, help="JSON selection manifest")
    parser.add_argument("--output", required=True, help="New evidence SQLite output path")
    parser.add_argument("--snapshot-id", required=True, help="Immutable snapshot identifier")
    parser.add_argument(
        "--created-at",
        required=True,
        help="Explicit ISO-8601 construction timestamp; never generated implicitly",
    )
    parser.add_argument(
        "--extracted-sha256",
        help="Precomputed SHA-256 of the unpacked DB; computed when omitted",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selection = load_selection(args.selection)
    stats, content_hash, extracted_hash = build_snapshot(
        source_database=args.source_db,
        output_database=args.output,
        selection=selection,
        snapshot_id=args.snapshot_id,
        created_at=args.created_at,
        extracted_database_sha256=args.extracted_sha256,
    )
    print(
        json.dumps(
            {
                "snapshot_id": args.snapshot_id,
                "content_sha256": content_hash,
                "extracted_database_sha256": extracted_hash,
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
