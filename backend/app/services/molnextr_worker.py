from __future__ import annotations

import json
import os
import sys
import traceback
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


@contextmanager
def _model_logging() -> Iterator[None]:
    """Keep library prints, including child-process prints, off the JSON protocol."""
    sys.stdout.flush()
    saved_stdout = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    try:
        with redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stderr.flush()
        os.dup2(saved_stdout, sys.stdout.fileno())
        os.close(saved_stdout)


def main() -> None:
    try:
        with _model_logging():
            from MolNexTR.molnextr import MolNexTRSingleton, get_predictions

            MolNexTRSingleton.get_instance()
        _, device_name = MolNexTRSingleton.get_device()
        _emit({"event": "ready", "device": device_name})
    except Exception as exc:
        _emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        traceback.print_exc(file=sys.stderr)
        return

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("action") != "predict":
                raise ValueError("unsupported worker action")
            image_path = Path(str(request.get("image_path", "")))
            if not image_path.is_file():
                raise ValueError("input image does not exist")
            with _model_logging():
                result = get_predictions(
                    str(image_path),
                    atoms_bonds=False,
                    smiles=True,
                    predicted_molfile=False,
                )
            _emit({"event": "prediction", "result": result})
        except Exception as exc:
            _emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
            traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
