import hashlib
import json
import platform
from typing import Any

from rdkit import rdBase

from app.core.chemistry_config import (
    CANONICAL_SERIALIZATION_VERSION,
    CHEMISTRY_POLICY_VERSION,
    DEPICTION_CONFIGURATION,
    DESCRIPTOR_CONFIGURATION,
    INPUT_NORMALIZATION_CONFIGURATION,
    OUTPUT_SCHEMA_VERSION,
    STANDARDIZATION_CONFIGURATION,
    VALIDATION_CONFIGURATION,
    VALIDATION_POLICY_VERSION,
)
from app.models.analysis import RunManifest, ToolVersions

PIPELINE_VERSION = "0.3.0"
RULESET_VERSION = "hm-01.3-approved"
SNAPSHOT_ID = "not-configured"
SNAPSHOT_SCOPE = "No frozen PubChem or ChEMBL snapshot is configured in this build."


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def tool_versions() -> ToolVersions:
    return ToolVersions(
        pipeline=PIPELINE_VERSION,
        python=platform.python_version(),
        rdkit=rdBase.rdkitVersion,
        ruleset=RULESET_VERSION,
    )


def configuration_payload(snapshot_id: str = SNAPSHOT_ID) -> dict[str, Any]:
    return {
        "pipeline": PIPELINE_VERSION,
        "ruleset": RULESET_VERSION,
        "chemistry_policy": CHEMISTRY_POLICY_VERSION,
        "validation_policy": VALIDATION_POLICY_VERSION,
        "validation": {
            key: list(value) if isinstance(value, list) else value
            for key, value in VALIDATION_CONFIGURATION.items()
        },
        "input_normalization": INPUT_NORMALIZATION_CONFIGURATION,
        "depiction": DEPICTION_CONFIGURATION,
        "standardization": [dict(step) for step in STANDARDIZATION_CONFIGURATION],
        "descriptors": [dict(descriptor) for descriptor in DESCRIPTOR_CONFIGURATION],
        "rdkit": rdBase.rdkitVersion,
        "output_schema": OUTPUT_SCHEMA_VERSION,
        "canonical_serialization": CANONICAL_SERIALIZATION_VERSION,
        "snapshot": snapshot_id,
    }


def configuration_sha256(configuration: dict[str, Any] | None = None) -> str:
    selected_configuration = configuration_payload() if configuration is None else configuration
    return sha256_text(canonical_json(selected_configuration))


def create_manifest(
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    configuration: dict[str, Any] | None = None,
    *,
    snapshot_id: str = SNAPSHOT_ID,
    snapshot_scope: str = SNAPSHOT_SCOPE,
) -> RunManifest:
    input_hash = sha256_text(canonical_json(input_payload))
    configuration_hash = configuration_sha256(configuration)
    output_hash = sha256_text(canonical_json(output_payload))
    analysis_id = f"PL-{input_hash[:8].upper()}-{configuration_hash[:4].upper()}"
    return RunManifest(
        analysis_id=analysis_id,
        input_sha256=input_hash,
        configuration_sha256=configuration_hash,
        output_sha256=output_hash,
        snapshot_id=snapshot_id,
        snapshot_scope=snapshot_scope,
        tool_versions=tool_versions(),
    )
