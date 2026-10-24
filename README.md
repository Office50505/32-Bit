# ProvenanceLab

ProvenanceLab helps biotechnology students validate, standardize, compare, and reproduce molecular analyses without silently repairing invalid inputs or inventing missing evidence.

## Current milestone

The first milestone provides:

- a React + TypeScript source-confirmation workflow;
- an atomic component structure;
- real RDKit SMILES validation through FastAPI;
- distinct invalid, ambiguous, unavailable, and outside-coverage states;
- annotated SVG molecular depictions;
- computed molecular descriptors for valid structures;
- a reproducible analysis manifest returned with every API response.

Paper and image uploads are represented in the interface, but optical chemical-structure recognition is intentionally not yet connected. Uploaded structures must eventually be shown as untrusted candidates and confirmed by the student before analysis.

## Repository structure

```text
frontend/  React, Vite, TypeScript
backend/   FastAPI, Pydantic, RDKit
docs/      accepted visual concepts and architecture notes
```

## Development

The backend currently targets Python 3.11 because the host's Python 3.14 environment does not provide RDKit.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e './backend[dev]'
uvicorn app.main:app --app-dir backend --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Scientific boundaries

- The submitted source and raw molecular text are preserved.
- A missing value always carries a reason code.
- Snapshot absence and snapshot coverage limitations are different states.
- Document/image recognition will never silently become an accepted molecule.
- Full frozen PubChem and ChEMBL adapters are not yet connected; the current evidence label is explicitly a demo fixture.
