"""
dialect_knowledge.py

Provides dialect-specific SQL knowledge to help translate PostgreSQL syntax to SQLite.
The agent will call this as a tool when it encounters database errors it needs to diagnose.
"""

from typing import Dict, Any

# Knowledge base mapping PostgreSQL-specific concepts to SQLite equivalents.
# In a full system, this could be an external document or vector search,
# but keeping it as a clean Python dictionary makes it deterministic, fast, and easy to explain.
DIALECT_RULES: Dict[str, str] = {
    "BIGSERIAL": (
        "PostgreSQL 'BIGSERIAL PRIMARY KEY' does not exist in SQLite. "
        "In SQLite, use 'INTEGER PRIMARY KEY AUTOINCREMENT'."
    ),
    "SERIAL": (
        "PostgreSQL 'SERIAL PRIMARY KEY' does not exist in SQLite. "
        "In SQLite, use 'INTEGER PRIMARY KEY AUTOINCREMENT'."
    ),
    "JSONB": (
        "SQLite does not have a native 'JSONB' type. "
        "Use 'TEXT' instead (SQLite supports json functions on standard text columns)."
    ),
    "NOW()": (
        "SQLite does not have a 'NOW()' function for timestamps. "
        "Use 'CURRENT_TIMESTAMP' instead (e.g., 'DEFAULT CURRENT_TIMESTAMP')."
    ),
    "BOOLEAN": (
        "SQLite does not have a distinct BOOLEAN type. "
        "Use 'INTEGER' (0 for false, 1 for true)."
    ),
}


def lookup_dialect_rule(feature_or_error: str) -> str:
    """
    Search the dialect knowledge base for advice on how to translate a PostgreSQL feature or error.

    Args:
        feature_or_error: A keyword, SQL snippet, or error message (e.g. 'BIGSERIAL', 'syntax error near NOW()').

    Returns:
        Guidance string explaining how to fix or translate the syntax for SQLite.
    """
    query = feature_or_error.upper()
    matches = []

    for keyword, advice in DIALECT_RULES.items():
        if keyword in query:
            matches.append(f"[{keyword}]: {advice}")

    if matches:
        return "\n".join(matches)

    return (
        f"No specific rule matched for '{feature_or_error}'. "
        f"Available keywords in knowledge base: {', '.join(DIALECT_RULES.keys())}. "
        "General advice: Ensure standard SQLite data types (INTEGER, REAL, TEXT, BLOB)."
    )
