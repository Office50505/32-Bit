import hashlib
import json
import platform
from typing import Any

from rdkit import rdBase

from app.models.analysis import RunManifest, ToolVersions

PIPELINE_VERSION = "0.1.0"
RULESET_VERSION = "hm-01.1"
SNAPSHOT_ID = "demo-evidence-fixture-v1"
SNAPSHOT_SCOPE = "curated development fixture; not full ChEMBL or PubChem coverage"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def tool_versions() -> ToolVersions:
    return ToolVersions(
        pipeline=PIPELINE_VERSION,
        python=platform.python_version(),
        rdkit=rdBase.rdkitVersion,
        ruleset=RULESET_VERSION,
    )


def create_manifest(input_payload: dict[str, Any], output_payload: dict[str, Any]) -> RunManifest:
    input_hash = sha256_text(canonical_json(input_payload))
    configuration = {
        "pipeline": PIPELINE_VERSION,
        "ruleset": RULESET_VERSION,
        "snapshot": SNAPSHOT_ID,
    }
    configuration_hash = sha256_text(canonical_json(configuration))
    output_hash = sha256_text(canonical_json(output_payload))
    analysis_id = f"PL-{input_hash[:8].upper()}-{configuration_hash[:4].upper()}"
    return RunManifest(
        analysis_id=analysis_id,
        input_sha256=input_hash,
        configuration_sha256=configuration_hash,
        output_sha256=output_hash,
        snapshot_id=SNAPSHOT_ID,
        snapshot_scope=SNAPSHOT_SCOPE,
        tool_versions=tool_versions(),
    )
