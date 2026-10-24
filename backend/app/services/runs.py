import json
import os
import sqlite3
from pathlib import Path

from app.core.provenance import canonical_json, configuration_sha256, sha256_text
from app.models.analysis import BatchAnalyzeRequest, RunResponse
from app.services.chemistry import analyze_structure


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


def create_run(request: BatchAnalyzeRequest) -> RunResponse:
    input_payload = request.model_dump(mode="json")
    results = [analyze_structure(item) for item in request.molecules]
    input_hash = sha256_text(canonical_json(input_payload))
    config_hash = configuration_sha256()
    output_payload = [result.model_dump(mode="json") for result in results]
    output_hash = sha256_text(canonical_json(output_payload))
    run = RunResponse(
        run_id=f"PLR-{input_hash[:10].upper()}-{config_hash[:6].upper()}",
        results=results,
        input_sha256=input_hash,
        configuration_sha256=config_hash,
        output_sha256=output_hash,
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
