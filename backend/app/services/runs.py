import json
import os
import platform
import sqlite3
from pathlib import Path

from rdkit import rdBase

from app.core.provenance import canonical_json, configuration_sha256, sha256_text
from app.models.analysis import (
    BatchAnalyzeRequest,
    ReplayEnvironment,
    ReplayVerification,
    RunResponse,
)
from app.services.chemistry import analyze_structure
from app.services.identity import pairwise_identity_comparisons

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEPENDENCY_LOCK = _REPOSITORY_ROOT / "backend" / "requirements.lock.txt"


def _database_path() -> Path:
    configured = os.environ.get("PROVENANCELAB_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / ".data" / "provenancelab.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def current_replay_environment() -> ReplayEnvironment:
    lock_hash = (
        sha256_text(_DEPENDENCY_LOCK.read_text(encoding="utf-8"))
        if _DEPENDENCY_LOCK.is_file()
        else "missing"
    )
    payload = {
        "python": platform.python_version(),
        "rdkit": rdBase.rdkitVersion,
        "platform": platform.system(),
        "machine": platform.machine(),
        "dependency_lock_sha256": lock_hash,
    }
    return ReplayEnvironment(
        **payload,
        environment_sha256=sha256_text(canonical_json(payload)),
    )


def _output_payload(results: list, identity_comparisons: list) -> dict[str, object]:
    return {
        "results": [result.model_dump(mode="json") for result in results],
        "identity_comparisons": [
            comparison.model_dump(mode="json") for comparison in identity_comparisons
        ],
    }


def create_run(request: BatchAnalyzeRequest) -> RunResponse:
    input_payload = request.model_dump(mode="json")
    results = [analyze_structure(item) for item in request.molecules]
    identity_comparisons = pairwise_identity_comparisons(results)
    input_hash = sha256_text(canonical_json(input_payload))
    config_hash = configuration_sha256()
    output_payload = _output_payload(results, identity_comparisons)
    output_hash = sha256_text(canonical_json(output_payload))
    run = RunResponse(
        run_id=f"PLR-{input_hash[:10].upper()}-{config_hash[:6].upper()}",
        results=results,
        identity_comparisons=identity_comparisons,
        input_sha256=input_hash,
        configuration_sha256=config_hash,
        output_sha256=output_hash,
        environment=current_replay_environment(),
    )
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO analysis_runs (run_id, request_json, response_json)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                request_json = excluded.request_json,
                response_json = excluded.response_json
            """,
            (
                run.run_id,
                canonical_json(input_payload),
                canonical_json(run.model_dump(mode="json")),
            ),
        )
    return run


def get_run(run_id: str) -> RunResponse | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT response_json FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return RunResponse.model_validate(json.loads(row[0]))


def replay_run(run_id: str) -> ReplayVerification | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT request_json, response_json FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None

    request = BatchAnalyzeRequest.model_validate(json.loads(row[0]))
    expected = RunResponse.model_validate(json.loads(row[1]))
    current_environment = current_replay_environment()
    results = [analyze_structure(item) for item in request.molecules]
    identity_comparisons = pairwise_identity_comparisons(results)
    actual_output_hash = sha256_text(
        canonical_json(_output_payload(results, identity_comparisons))
    )
    differences: list[str] = []
    if expected.environment is None:
        status = "LEGACY_RUN_NO_ENVIRONMENT"
        differences.append("The stored run predates environment fingerprinting.")
    elif expected.environment.environment_sha256 != current_environment.environment_sha256:
        status = "ENVIRONMENT_MISMATCH"
        differences.append("The current execution environment differs from the stored run.")
    elif expected.output_sha256 != actual_output_hash:
        status = "OUTPUT_MISMATCH"
        differences.append("Recomputed canonical output does not match the stored output hash.")
    else:
        status = "MATCH"
    return ReplayVerification(
        run_id=run_id,
        status=status,
        reproducible=status == "MATCH",
        expected_output_sha256=expected.output_sha256,
        actual_output_sha256=actual_output_hash,
        expected_environment_sha256=(
            expected.environment.environment_sha256 if expected.environment else None
        ),
        actual_environment_sha256=current_environment.environment_sha256,
        differences=differences,
    )
