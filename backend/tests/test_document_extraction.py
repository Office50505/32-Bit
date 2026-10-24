from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.main import app
from app.services.document_extraction import extract_candidates_from_pages

client = TestClient(app)


def _pdf_bytes(pages: list[str]) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    for text in pages:
        document.drawString(72, 740, text)
        document.showPage()
    document.save()
    return output.getvalue()


def test_page_extraction_deduplicates_identity_and_retains_mentions() -> None:
    candidates, total_mentions = extract_candidates_from_pages(
        [
            "Compound A SMILES: CCO. The first measurement.",
            "Compound A canonical SMILES = OCC. The follow-up measurement.",
            "Compound B SMILES: c1ccccc1",
            "Compound X SMILES: c(c)(c)(c)(c)",
        ]
    )

    assert len(candidates) == 3
    assert total_mentions == 4
    ethanol = next(item for item in candidates if item.canonical_smiles == "CCO")
    assert ethanol.mention_count == 2
    assert [mention.page for mention in ethanol.mentions] == [1, 2]
    unresolved = next(item for item in candidates if item.canonical_smiles is None)
    assert unresolved.confidence == "needs-review"
    assert unresolved.smiles == "c(c)(c)(c)(c)"


def test_pdf_endpoint_returns_multiple_provenanced_candidates() -> None:
    payload = _pdf_bytes(
        [
            "Compound 1 SMILES: CC(=O)Oc1ccccc1C(=O)O",
            "Compound 2 SMILES: c1ccccc1",
        ]
    )
    response = client.post(
        "/api/extract/document",
        files={"document": ("paper.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "candidates"
    assert body["total_mentions"] == 2
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["mentions"][0]["page"] == 1
    assert body["candidates"][1]["mentions"][0]["page"] == 2


def test_document_endpoint_rejects_non_pdf() -> None:
    response = client.post(
        "/api/extract/document",
        files={"document": ("notes.txt", b"SMILES: CCO", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"

