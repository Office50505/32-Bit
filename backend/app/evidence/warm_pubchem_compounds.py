import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.pubchem_questions import FrozenPubChemClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SELECTION = PROJECT_ROOT / "backend/config/evidence/common-pubchem-compounds.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/snapshots/pubchem-compounds"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Acquire hash-verified PubChem compound records for the starter library."
    )
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    payload = json.loads(arguments.selection.read_text(encoding="utf-8"))
    compounds = tuple(str(name) for name in payload["compounds"])
    client = FrozenPubChemClient(arguments.output)
    with ThreadPoolExecutor(max_workers=max(1, arguments.workers)) as executor:
        records = tuple(executor.map(client.get, compounds))
    for record in records:
        print(f"CID {record.cid}: {record.title} -> {record.snapshot_id}")


if __name__ == "__main__":
    main()
