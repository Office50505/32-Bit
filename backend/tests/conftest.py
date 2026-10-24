import os

# Phase 1 contract tests intentionally exercise the explicit no-snapshot state.
# Tests that cover Phase 2 PubChem evidence opt in with an injected frozen client.
os.environ.setdefault("PROVENANCELAB_PROPERTY_EVIDENCE", "0")
os.environ.setdefault("PROVENANCELAB_DYNAMIC_CHEMBL", "0")
