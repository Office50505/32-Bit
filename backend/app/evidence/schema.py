SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK(length(source_sha256) = 64),
    license TEXT,
    scope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sealed INTEGER NOT NULL DEFAULT 0 CHECK(sealed IN (0, 1)),
    content_sha256 TEXT CHECK(content_sha256 IS NULL OR length(content_sha256) = 64),
    schema_version INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS molecules (
    snapshot_id TEXT NOT NULL,
    inchikey TEXT NOT NULL,
    canonical_smiles TEXT NOT NULL,
    parent_inchikey TEXT,
    preferred_name TEXT,
    chembl_id TEXT,
    pubchem_cid INTEGER,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, inchikey),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
) STRICT;

CREATE TABLE IF NOT EXISTS molecule_aliases (
    snapshot_id TEXT NOT NULL,
    inchikey TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, inchikey, normalized_alias, source),
    FOREIGN KEY (snapshot_id, inchikey)
        REFERENCES molecules(snapshot_id, inchikey)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_molecule_aliases_normalized
    ON molecule_aliases(snapshot_id, normalized_alias);

CREATE TABLE IF NOT EXISTS targets (
    snapshot_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    preferred_name TEXT NOT NULL,
    organism TEXT,
    target_type TEXT,
    accession TEXT,
    gene_symbol TEXT,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, target_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
) STRICT;

CREATE TABLE IF NOT EXISTS target_aliases (
    snapshot_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, target_id, normalized_alias, source),
    FOREIGN KEY (snapshot_id, target_id)
        REFERENCES targets(snapshot_id, target_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_target_aliases_normalized
    ON target_aliases(snapshot_id, normalized_alias);

CREATE TABLE IF NOT EXISTS papers (
    snapshot_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    pmcid TEXT,
    pmid TEXT,
    doi TEXT,
    title TEXT NOT NULL,
    article_license TEXT,
    retraction_status TEXT NOT NULL,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, paper_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
    CHECK(retraction_status IN (
        'CLEAR', 'RETRACTED', 'EXPRESSION_OF_CONCERN',
        'CORRECTED', 'REINSTATED', 'UNKNOWN'
    ))
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi
    ON papers(snapshot_id, doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_papers_pmid
    ON papers(snapshot_id, pmid) WHERE pmid IS NOT NULL;

CREATE TABLE IF NOT EXISTS assays (
    snapshot_id TEXT NOT NULL,
    assay_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('CHEMBL', 'PUBCHEM')),
    target_id TEXT,
    organism TEXT,
    assay_type TEXT,
    description TEXT NOT NULL,
    target_confidence_score INTEGER,
    paper_id TEXT,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, assay_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (snapshot_id, target_id)
        REFERENCES targets(snapshot_id, target_id),
    FOREIGN KEY (snapshot_id, paper_id)
        REFERENCES papers(snapshot_id, paper_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_assays_target
    ON assays(snapshot_id, target_id, organism, assay_type);

CREATE TABLE IF NOT EXISTS activities (
    snapshot_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    assay_id TEXT NOT NULL,
    molecule_inchikey TEXT NOT NULL,
    measurement_type TEXT NOT NULL,
    original_value REAL,
    original_unit TEXT,
    original_relation TEXT,
    standard_value REAL,
    standard_unit TEXT,
    standard_relation TEXT,
    pchembl_value REAL,
    activity_outcome TEXT,
    data_validity_comment TEXT,
    potential_duplicate INTEGER NOT NULL DEFAULT 0
        CHECK(potential_duplicate IN (0, 1)),
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, activity_id),
    FOREIGN KEY (snapshot_id, assay_id)
        REFERENCES assays(snapshot_id, assay_id),
    FOREIGN KEY (snapshot_id, molecule_inchikey)
        REFERENCES molecules(snapshot_id, inchikey),
    CHECK(original_relation IS NULL OR original_relation IN ('=', '<', '>', '<=', '>=')),
    CHECK(standard_relation IS NULL OR standard_relation IN ('=', '<', '>', '<=', '>='))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_activities_lookup
    ON activities(
        snapshot_id, molecule_inchikey, measurement_type,
        standard_unit, standard_value
    );
CREATE INDEX IF NOT EXISTS idx_activities_assay
    ON activities(snapshot_id, assay_id);

CREATE TABLE IF NOT EXISTS passages (
    snapshot_id TEXT NOT NULL,
    passage_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    section_name TEXT NOT NULL,
    paragraph_number INTEGER,
    sentence_start INTEGER,
    sentence_end INTEGER,
    passage_text TEXT NOT NULL,
    passage_sha256 TEXT NOT NULL CHECK(length(passage_sha256) = 64),
    priority INTEGER NOT NULL DEFAULT 5 CHECK(priority BETWEEN 1 AND 5),
    PRIMARY KEY (snapshot_id, passage_id),
    FOREIGN KEY (snapshot_id, paper_id)
        REFERENCES papers(snapshot_id, paper_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_passages_paper
    ON passages(snapshot_id, paper_id, section_name, paragraph_number);

CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    passage_id UNINDEXED,
    snapshot_id UNINDEXED,
    article_title,
    section_name,
    passage_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS retractions (
    snapshot_id TEXT NOT NULL,
    retraction_id TEXT NOT NULL,
    doi TEXT,
    pmid TEXT,
    notice_type TEXT NOT NULL,
    notice_date TEXT,
    reason TEXT,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, retraction_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
    CHECK(notice_type IN (
        'RETRACTION', 'EXPRESSION_OF_CONCERN', 'CORRECTION', 'REINSTATEMENT'
    ))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_retractions_doi
    ON retractions(snapshot_id, doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_retractions_pmid
    ON retractions(snapshot_id, pmid) WHERE pmid IS NOT NULL;

CREATE TABLE IF NOT EXISTS run_records (
    snapshot_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    molecule_inchikey TEXT,
    property_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    unit TEXT,
    manifest_json TEXT NOT NULL,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    PRIMARY KEY (snapshot_id, record_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (snapshot_id, molecule_inchikey)
        REFERENCES molecules(snapshot_id, inchikey)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_run_records_lookup
    ON run_records(snapshot_id, molecule_inchikey, property_key);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    basis TEXT NOT NULL,
    molecule_inchikey TEXT,
    target_id TEXT,
    endpoint TEXT,
    relation TEXT,
    value REAL,
    unit TEXT,
    paper_id TEXT,
    retraction_status TEXT NOT NULL,
    raw_record_sha256 TEXT NOT NULL CHECK(length(raw_record_sha256) = 64),
    payload_json TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (snapshot_id, molecule_inchikey)
        REFERENCES molecules(snapshot_id, inchikey),
    FOREIGN KEY (snapshot_id, target_id)
        REFERENCES targets(snapshot_id, target_id),
    FOREIGN KEY (snapshot_id, paper_id)
        REFERENCES papers(snapshot_id, paper_id),
    CHECK(source_type IN (
        'CHEMBL_ACTIVITY', 'PUBCHEM_BIOASSAY', 'PAPER_PASSAGE', 'RUN_RECORD'
    )),
    CHECK(basis IN ('EXPERIMENTAL', 'COMPUTED', 'LITERATURE_CONTEXT')),
    CHECK(relation IS NULL OR relation IN ('=', '<', '>', '<=', '>=')),
    CHECK(retraction_status IN (
        'CLEAR', 'RETRACTED', 'EXPRESSION_OF_CONCERN',
        'CORRECTED', 'REINSTATED', 'UNKNOWN'
    ))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_evidence_structured_lookup
    ON evidence_items(
        snapshot_id, molecule_inchikey, target_id, endpoint, source_type
    );
CREATE INDEX IF NOT EXISTS idx_evidence_paper
    ON evidence_items(snapshot_id, paper_id);
"""
