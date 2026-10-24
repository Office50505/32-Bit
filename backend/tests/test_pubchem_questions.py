import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from app.models.evidence_assistant import ClaimCheckRequest, Verdict
from app.services.pubchem_questions import (
    FrozenPubChemClient,
    PubChemQuestionAssistant,
    parse_molecule_question,
)


def pubchem_payload(name: str) -> bytes:
    is_l = name == "L-Alanine"
    return json.dumps(
        {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 5950 if is_l else 71080,
                        "Title": name,
                        "IUPACName": (
                            "(2S)-2-aminopropanoic acid"
                            if is_l
                            else "(2R)-2-aminopropanoic acid"
                        ),
                        "ConnectivitySMILES": "CC(C(=O)O)N",
                        "SMILES": "C[C@@H](C(=O)O)N" if is_l else "C[C@H](C(=O)O)N",
                        "InChIKey": (
                            "QNAYBMKLOCPYGJ-REOHCLBHSA-N"
                            if is_l
                            else "QNAYBMKLOCPYGJ-UWTATZPHSA-N"
                        ),
                        "MolecularFormula": "C3H7NO2",
                        "MolecularWeight": "89.09",
                        "ExactMass": "89.047678",
                        "XLogP": -2.8,
                        "TPSA": 63.3,
                        "HBondDonorCount": 2,
                        "HBondAcceptorCount": 3,
                        "RotatableBondCount": 1,
                    }
                ]
            }
        },
        separators=(",", ":"),
    ).encode()


def test_parser_normalizes_stereo_comparison_word_orders() -> None:
    first = parse_molecule_question("What is the difference between alanine L and D?")
    second = parse_molecule_question("difference between L and D alanine")
    assert first is not None
    assert second is not None
    assert first.names == ("L-alanine", "D-alanine")
    assert second.names == ("L-alanine", "D-alanine")


def test_pubchem_question_fetches_once_then_reuses_verified_snapshot(tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str, _timeout: float) -> bytes:
        calls.append(url)
        name = "L-Alanine" if "L-alanine" in url else "D-Alanine"
        return pubchem_payload(name)

    client = FrozenPubChemClient(tmp_path, transport=transport)
    assistant = PubChemQuestionAssistant(client)
    request = ClaimCheckRequest(
        claim="What is the difference between alanine L and D?"
    )
    first = assistant.try_check(request)
    second = assistant.try_check(request)

    assert first is not None
    assert first == second
    assert len(calls) == 2
    verdict = first.verdicts[0]
    assert verdict.verdict == Verdict.SUPPORTED
    assert "enantiomers" in verdict.reason
    assert len(verdict.citations) == 2
    assert verdict.citations[0].source_record_id == "PUBCHEM:CID:5950"
    assert verdict.citations[1].source_record_id == "PUBCHEM:CID:71080"
    assert all("pubchem-pug-cid" in item.snapshot_id for item in verdict.citations)
    assert first.manifest.model_name == "deterministic-pubchem-structure-v1"


def test_concurrent_snapshot_writes_share_one_valid_cache_record(tmp_path: Path) -> None:
    barrier = Barrier(2)

    def transport(_url: str, _timeout: float) -> bytes:
        barrier.wait(timeout=2)
        return pubchem_payload("L-Alanine")

    client = FrozenPubChemClient(tmp_path, transport=transport)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.get, "L-Alanine") for _ in range(2)]
        records = [future.result(timeout=5) for future in futures]

    assert records[0] == records[1]
    assert client.get("L-Alanine") == records[0]


def test_non_molecule_chat_falls_through_without_an_api_call(tmp_path: Path) -> None:
    def unexpected_transport(_url: str, _timeout: float) -> bytes:
        raise AssertionError("transport must not be called")

    assistant = PubChemQuestionAssistant(
        FrozenPubChemClient(tmp_path, transport=unexpected_transport)
    )
    assert assistant.try_check(ClaimCheckRequest(claim="hey")) is None


def test_parser_routes_additional_pubchem_property_questions() -> None:
    parsed = parse_molecule_question("What is the exact mass of aspirin?")
    assert parsed is not None
    assert parsed.kind == "exact_mass"
    assert parsed.names == ("aspirin",)

    described = parse_molecule_question("Give me facts about caffeine")
    assert described is not None
    assert described.kind == "describe"
    assert described.names == ("caffeine",)
