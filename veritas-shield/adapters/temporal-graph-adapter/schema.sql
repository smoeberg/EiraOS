-- Temporal Graph SQL Schema for EiraOS & Veritas Shield

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sender TEXT NOT NULL,
    date TEXT NOT NULL,
    risk_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    signature_status TEXT NOT NULL, -- VERIFIED_EUDI / UNVERIFIED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS narratives (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    first_seen TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS article_narrative (
    article_id TEXT NOT NULL,
    narrative_id TEXT NOT NULL,
    relation_type TEXT DEFAULT 'SUPPORTS', -- SUPPORTS / CONTRADICTS / EXPANDS
    FOREIGN KEY (article_id) REFERENCES articles(id),
    FOREIGN KEY (narrative_id) REFERENCES narratives(id),
    PRIMARY KEY (article_id, narrative_id)
);
