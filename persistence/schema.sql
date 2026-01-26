-- Talkie SQLite schema: interactions, sessions, user_settings

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    original_transcription TEXT NOT NULL,
    llm_response TEXT NOT NULL,
    corrected_response TEXT,
    exclude_from_profile INTEGER NOT NULL DEFAULT 0,
    weight REAL,
    speaker_id TEXT,
    session_id TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_created_at ON interactions(created_at);
CREATE INDEX IF NOT EXISTS idx_interactions_session_id ON interactions(session_id);
CREATE INDEX IF NOT EXISTS idx_interactions_corrected ON interactions(corrected_response) WHERE corrected_response IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Audio training: facts the user spoke to remember (e.g. "Star is my dog", "Susan is my wife")
CREATE TABLE IF NOT EXISTS training_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_training_facts_created_at ON training_facts(created_at);
