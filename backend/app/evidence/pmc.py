import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.evidence.retractions import FrozenRetractionIndex
from app.evidence.store import EvidenceStore, EvidenceStoreError, SnapshotSpec
from app.models.evidence_assistant import RetractionStatus

_WHITESPACE = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s+|$)")
_NON_IDENTIFIER = re.compile(r"[^A-Za-z0-9]+")
_EXCLUDED_ANCESTORS = {"fig", "table-wrap", "ref-list", "supplementary-material"}
_SECTION_PRIORITY = {
    "abstract": 1,
    "result": 1,
    "results": 1,
    "method": 2,
    "methods": 2,
    "materials and methods": 2,
    "discussion": 3,
    "conclusion": 3,
    "conclusions": 3,
    "introduction": 4,
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _elements(root: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == name]


def _first(root: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next(iter(_elements(root, name)), None)


def _text(element: ElementTree.Element | None) -> str | None:
    if element is None:
        return None
    normalized = _WHITESPACE.sub(" ", "".join(element.itertext())).strip()
    return normalized or None


def _sha256(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _article_id(root: ElementTree.Element, identifier_type: str) -> str | None:
    for element in _elements(root, "article-id"):
        if element.attrib.get("pub-id-type") == identifier_type:
            return _text(element)
    return None


def _slug(value: str) -> str:
    return _NON_IDENTIFIER.sub("-", value).strip("-").upper()[:80] or "UNTITLED"


def _priority(section_name: str) -> int:
    lowered = section_name.casefold()
    for label, priority in _SECTION_PRIORITY.items():
        if label in lowered:
            return priority
    return 5


def _sentence_windows(text: str, *, maximum_characters: int) -> list[tuple[int, int, str]]:
    boundaries = [0]
    boundaries.extend(match.end() for match in _SENTENCE_END.finditer(text))
    if boundaries[-1] != len(text):
        boundaries.append(len(text))
    sentences = [
        (
            boundaries[index],
            boundaries[index + 1],
            text[boundaries[index] : boundaries[index + 1]].strip(),
        )
        for index in range(len(boundaries) - 1)
    ]
    sentences = [sentence for sentence in sentences if sentence[2]]
    windows: list[tuple[int, int, str]] = []
    current_start: int | None = None
    current_end: int | None = None
    current_parts: list[str] = []
    for start, end, sentence in sentences:
        proposed = " ".join([*current_parts, sentence])
        if current_parts and len(proposed) > maximum_characters:
            windows.append((current_start or 0, current_end or 0, " ".join(current_parts)))
            current_start, current_end, current_parts = start, end, [sentence]
        else:
            current_start = start if current_start is None else current_start
            current_end = end
            current_parts.append(sentence)
    if current_parts:
        windows.append((current_start or 0, current_end or 0, " ".join(current_parts)))
    return windows


@dataclass(frozen=True, slots=True)
class PmcArticleMetadata:
    pmcid: str
    pmid: str | None
    doi: str | None
    title: str
    article_license: str | None
    raw_xml_sha256: str


@dataclass(frozen=True, slots=True)
class PmcImportResult:
    metadata: PmcArticleMetadata
    passage_count: int
    retraction_status: RetractionStatus


@dataclass(frozen=True, slots=True)
class PmcSnapshotResult:
    snapshot_id: str
    article_count: int
    passage_count: int
    content_sha256: str


def import_jats_article(
    store: EvidenceStore,
    *,
    snapshot_id: str,
    xml_bytes: bytes,
    retraction_index: FrozenRetractionIndex,
    maximum_passage_characters: int = 1_200,
) -> PmcImportResult:
    if b"<!ENTITY" in xml_bytes.upper():
        raise EvidenceStoreError("JATS XML with entity declarations is not accepted")
    if not 200 <= maximum_passage_characters <= 5_000:
        raise ValueError("maximum passage characters must be between 200 and 5000")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as error:
        raise EvidenceStoreError("invalid JATS XML") from error
    if _local_name(root.tag) != "article":
        raise EvidenceStoreError("JATS document root must be article")

    pmcid = _article_id(root, "pmcid")
    title = _text(_first(root, "article-title"))
    if not pmcid or not title:
        raise EvidenceStoreError("JATS article requires PMCID and title")
    pmid = _article_id(root, "pmid")
    doi = _article_id(root, "doi")
    permissions = _first(root, "permissions")
    license_element = _first(permissions, "license") if permissions is not None else None
    license_type = (
        license_element.attrib.get("license-type") if license_element is not None else None
    )
    license_text = _text(license_element)
    article_license = ": ".join(
        value for value in (license_type, license_text) if value
    ) or None
    retraction_status = retraction_index.status_for(doi=doi, pmid=pmid)
    metadata = PmcArticleMetadata(
        pmcid=pmcid,
        pmid=pmid,
        doi=doi,
        title=title,
        article_license=article_license,
        raw_xml_sha256=_sha256(xml_bytes),
    )
    paper_id = f"PMCID:{pmcid}"
    store.add_paper(
        snapshot_id=snapshot_id,
        paper_id=paper_id,
        pmcid=pmcid,
        pmid=pmid,
        doi=doi,
        title=title,
        article_license=article_license,
        retraction_status=retraction_status.value,
        raw_record_sha256=metadata.raw_xml_sha256,
    )

    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    paragraphs: list[tuple[str, ElementTree.Element]] = []
    abstract = _first(root, "abstract")
    if abstract is not None:
        paragraphs.extend(("Abstract", paragraph) for paragraph in _elements(abstract, "p"))
    body = _first(root, "body")
    if body is not None:
        for paragraph in _elements(body, "p"):
            ancestors: list[ElementTree.Element] = []
            current = parent_by_child.get(paragraph)
            while current is not None and current is not body:
                ancestors.append(current)
                current = parent_by_child.get(current)
            if any(_local_name(ancestor.tag) in _EXCLUDED_ANCESTORS for ancestor in ancestors):
                continue
            section = next(
                (
                    ancestor
                    for ancestor in ancestors
                    if _local_name(ancestor.tag) == "sec"
                ),
                None,
            )
            section_title = _text(_first(section, "title")) if section is not None else None
            paragraphs.append((section_title or "Body", paragraph))

    paragraph_counts: dict[str, int] = defaultdict(int)
    passage_count = 0
    for section_name, paragraph in paragraphs:
        paragraph_text = _text(paragraph)
        if not paragraph_text:
            continue
        paragraph_counts[section_name] += 1
        paragraph_number = paragraph_counts[section_name]
        for start, end, passage_text in _sentence_windows(
            paragraph_text,
            maximum_characters=maximum_passage_characters,
        ):
            passage_id = (
                f"PMCID:{pmcid}:{_slug(section_name)}:P{paragraph_number}:C{start}-{end}"
            )
            store.add_passage(
                snapshot_id=snapshot_id,
                passage_id=passage_id,
                paper_id=paper_id,
                section_name=section_name,
                paragraph_number=paragraph_number,
                sentence_start=start,
                sentence_end=end,
                passage_text=passage_text,
                passage_sha256=_sha256(passage_text),
                priority=_priority(section_name),
            )
            passage_count += 1
    return PmcImportResult(
        metadata=metadata,
        passage_count=passage_count,
        retraction_status=retraction_status,
    )


def _import_pmc_snapshot(
    store: EvidenceStore,
    *,
    snapshot_id: str,
    source_version: str,
    created_at: str,
    articles: dict[str, bytes],
    retraction_index: FrozenRetractionIndex,
    source_uri: str = "https://europepmc.org/RestfulWebService",
    maximum_passage_characters: int = 1_200,
) -> PmcSnapshotResult:
    if not articles:
        raise ValueError("PMC snapshot requires at least one selected article")
    raw_hashes = {pmcid: _sha256(payload) for pmcid, payload in sorted(articles.items())}
    source_hash = _sha256(
        json.dumps(raw_hashes, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    store.register_snapshot(
        SnapshotSpec(
            snapshot_id=snapshot_id,
            source_name="Europe PMC Open Access full text",
            source_version=source_version,
            source_sha256=source_hash,
            source_uri=source_uri,
            license="Per-article open-access license",
            scope={"pmcids": sorted(articles)},
            created_at=created_at,
        )
    )
    total_passages = 0
    for expected_pmcid, payload in sorted(articles.items()):
        result = import_jats_article(
            store,
            snapshot_id=snapshot_id,
            xml_bytes=payload,
            retraction_index=retraction_index,
            maximum_passage_characters=maximum_passage_characters,
        )
        if result.metadata.pmcid != expected_pmcid:
            raise EvidenceStoreError(
                f"PMC file key {expected_pmcid} contains article {result.metadata.pmcid}"
            )
        total_passages += result.passage_count
    content_hash = store.seal_snapshot(snapshot_id)
    return PmcSnapshotResult(
        snapshot_id=snapshot_id,
        article_count=len(articles),
        passage_count=total_passages,
        content_sha256=content_hash,
    )


def import_pmc_snapshot(
    store: EvidenceStore,
    *,
    snapshot_id: str,
    source_version: str,
    created_at: str,
    articles: dict[str, bytes],
    retraction_index: FrozenRetractionIndex,
    source_uri: str = "https://europepmc.org/RestfulWebService",
    maximum_passage_characters: int = 1_200,
) -> PmcSnapshotResult:
    with store.batch():
        return _import_pmc_snapshot(
            store,
            snapshot_id=snapshot_id,
            source_version=source_version,
            created_at=created_at,
            articles=articles,
            retraction_index=retraction_index,
            source_uri=source_uri,
            maximum_passage_characters=maximum_passage_characters,
        )


def read_pmc_xml_files(
    directory: str | Path,
    pmcids: tuple[str, ...],
) -> dict[str, bytes]:
    root = Path(directory).resolve()
    articles: dict[str, bytes] = {}
    for pmcid in pmcids:
        if not re.fullmatch(r"PMC[1-9][0-9]*", pmcid):
            raise ValueError(f"invalid PMCID: {pmcid}")
        path = root / f"{pmcid}.xml"
        if not path.is_file():
            raise EvidenceStoreError(f"missing frozen Europe PMC XML: {path}")
        articles[pmcid] = path.read_bytes()
    return articles
