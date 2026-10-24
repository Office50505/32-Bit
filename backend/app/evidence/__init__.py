"""Frozen evidence storage for the ProvenanceLab evidence assistant."""

from app.evidence.store import (
    EvidenceStore,
    EvidenceStoreError,
    PassageSearchHit,
    SnapshotSealedError,
    SnapshotSpec,
)

__all__ = [
    "EvidenceStore",
    "EvidenceStoreError",
    "PassageSearchHit",
    "SnapshotSealedError",
    "SnapshotSpec",
]
