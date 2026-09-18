-- Scenario 2: Migration script that is ALREADY valid in SQLite
-- This test proves that the agent does NOT follow a rigid sequence:
-- Because execution succeeds immediately, the agent can skip dialect lookup
-- and move straight to verification!

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
