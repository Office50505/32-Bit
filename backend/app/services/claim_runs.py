import json
import os
import sqlite3
from pathlib import Path

from app.core.provenance import canonical_json
from app.models.evidence_assistant import ClaimCheckRequest, ClaimCheckResponse


class ClaimRunIntegrityError(RuntimeError):
    """Raised if an immutable assistant run ID is reused with different content."""


def _database_path() -> Path:
    configured = os.environ.get("PROVENANCELAB_CLAIM_RUN_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / ".data" / "claim-check-runs.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS claim_check_runs (
            assistant_run_id TEXT PRIMARY KEY,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            input_sha256 TEXT NOT NULL,
            output_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def persist_claim_check_run(
    request: ClaimCheckRequest,
    response: ClaimCheckResponse,
) -> None:
    request_json = canonical_json(request.model_dump(mode="json"))
    response_json = canonical_json(response.model_dump(mode="json"))
    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT request_json, response_json
            FROM claim_check_runs
            WHERE assistant_run_id = ?
            """,
            (response.assistant_run_id,),
        ).fetchone()
        if existing is not None:
            if existing != (request_json, response_json):
                raise ClaimRunIntegrityError(
                    "An immutable claim-check run ID resolved to different content."
                )
            return
        connection.execute(
            """
            INSERT INTO claim_check_runs (
                assistant_run_id,
                request_json,
                response_json,
                input_sha256,
                output_sha256
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                response.assistant_run_id,
                request_json,
                response_json,
                response.manifest.input_sha256,
                response.manifest.output_sha256,
            ),
        )


def get_claim_check_run(assistant_run_id: str) -> ClaimCheckResponse | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT response_json FROM claim_check_runs WHERE assistant_run_id = ?",
            (assistant_run_id,),
        ).fetchone()
    if row is None:
        return None
    return ClaimCheckResponse.model_validate(json.loads(row[0]))
