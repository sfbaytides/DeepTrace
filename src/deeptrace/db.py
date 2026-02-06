"""SQLite database manager for case files."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

# Table creation order matters for foreign key references:
# 1. schema_version (no FK)
# 2. sources (no FK)
# 3. entities (FK -> sources, entities)
# 4. events (FK -> sources)
# 5. hypotheses (no FK)
# 6. suspect_pools (no FK)
# 7. evidence_items (FK -> sources)
# 8. hypothesis_evidence_scores (FK -> hypotheses, evidence_items)
# 9. indicators (FK -> hypotheses)
# 10. statements (FK -> sources, statements)
# 11. anomalies (FK -> sources, hypotheses)
# 12. victim_profile (FK -> sources)
# 13. relationships (FK -> entities, sources)
# 14. case_review_items (no FK)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT,
    raw_text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    reliability_score REAL DEFAULT 0.5,
    source_reliability TEXT CHECK(source_reliability IN ('A','B','C','D','E','F')),
    information_accuracy TEXT CHECK(information_accuracy IN ('1','2','3','4','5','6')),
    access_assessment TEXT,
    bias_assessment TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    description TEXT,
    source_id INTEGER REFERENCES sources(id),
    canonical_id INTEGER REFERENCES entities(id),
    confidence TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_start TEXT,
    timestamp_end TEXT,
    description TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    source_id INTEGER REFERENCES sources(id),
    layer TEXT DEFAULT 'general',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'plausible',
    supporting_evidence TEXT,
    contradicting_evidence TEXT,
    open_questions TEXT,
    key_assumptions TEXT,
    consequence_if_true TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suspect_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    supporting_evidence TEXT,
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'known'
        CHECK(status IN ('known', 'processed', 'pending',
                         'inconclusive', 'missing')),
    source_id INTEGER REFERENCES sources(id),
    original_testing TEXT,
    contemporary_testing_available TEXT,
    resubmission_status TEXT DEFAULT 'not_needed'
        CHECK(resubmission_status IN ('not_needed', 'recommended',
                                      'submitted', 'completed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hypothesis_evidence_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id),
    evidence_id INTEGER NOT NULL REFERENCES evidence_items(id),
    consistency TEXT NOT NULL CHECK(consistency IN ('C', 'I', 'N')),
    diagnostic_weight TEXT NOT NULL DEFAULT 'M' CHECK(diagnostic_weight IN ('H', 'M', 'L')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id),
    description TEXT NOT NULL,
    expected_timeframe TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'observed', 'not_observed')),
    observed_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    speaker TEXT NOT NULL,
    content TEXT NOT NULL,
    context TEXT,
    date TEXT,
    source_id INTEGER REFERENCES sources(id),
    supersedes_id INTEGER REFERENCES statements(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id),
    related_hypothesis_id INTEGER REFERENCES hypotheses(id),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS victim_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_name TEXT NOT NULL UNIQUE,
    field_value TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_a_id INTEGER NOT NULL REFERENCES entities(id),
    entity_b_id INTEGER NOT NULL REFERENCES entities(id),
    relationship_type TEXT NOT NULL,
    description TEXT,
    strength REAL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    source_id INTEGER REFERENCES sources(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS case_review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    item_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_available'
        CHECK(status IN ('located', 'reviewed', 'not_available',
                         'not_applicable', 'needs_followup')),
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp_start);
CREATE INDEX IF NOT EXISTS idx_events_layer ON events(layer);
CREATE INDEX IF NOT EXISTS idx_hypotheses_tier ON hypotheses(tier);
CREATE INDEX IF NOT EXISTS idx_evidence_status ON evidence_items(status);
CREATE INDEX IF NOT EXISTS idx_statements_speaker ON statements(speaker);
CREATE INDEX IF NOT EXISTS idx_hes_hypothesis ON hypothesis_evidence_scores(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_hes_evidence ON hypothesis_evidence_scores(evidence_id);
CREATE INDEX IF NOT EXISTS idx_indicators_hypothesis ON indicators(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_indicators_status ON indicators(status);
CREATE INDEX IF NOT EXISTS idx_review_category ON case_review_items(category);
CREATE INDEX IF NOT EXISTS idx_review_status ON case_review_items(status);
"""


class CaseDatabase:
    """Manages a single-case SQLite database."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def open(self) -> "CaseDatabase":
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        return self

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> "CaseDatabase":
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def initialize_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA_SQL)
            self.conn.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )

    @contextmanager
    def transaction(self):
        cursor = self.conn.cursor()
        try:
            yield cursor
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()
