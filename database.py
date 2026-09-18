"""
database.py

Handles real SQLite database operations:
1. Executing migration SQL scripts.
2. Catching real database errors and returning them cleanly.
3. Inspecting and verifying table schemas.
"""

import sqlite3
import os
from typing import Dict, Any, List, Optional

# Default path for the local SQLite database
DEFAULT_DB_PATH = "migration_test.db"


def reset_database(db_path: str = DEFAULT_DB_PATH) -> None:
    """Removes any existing test database file so we start with a clean state."""
    if db_path != ":memory:" and os.path.exists(db_path):
        os.remove(db_path)


def execute_migration_sql(sql: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Executes a SQL migration string against the target SQLite database.

    Args:
        sql: The SQL string to execute.
        db_path: Path to SQLite database file.

    Returns:
        A dictionary indicating success or failure, along with error details.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # executescript allows executing multiple statements separated by semicolons
        cursor.executescript(sql)
        conn.commit()
        conn.close()
        return {
            "success": True,
            "message": "Migration SQL executed successfully without syntax or execution errors.",
            "error": None,
        }
    except sqlite3.Error as err:
        return {
            "success": False,
            "message": "SQLite execution failed.",
            "error": str(err),
        }


def inspect_table_schema(table_name: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Inspects the schema of a created table in SQLite using PRAGMA table_info.

    Args:
        table_name: Name of the table to inspect.
        db_path: Path to SQLite database file.

    Returns:
        Schema details including column names, types, and primary key flags.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info('{table_name}');")
        columns = cursor.fetchall()
        conn.close()

        if not columns:
            return {
                "success": False,
                "error": f"Table '{table_name}' does not exist in database.",
                "columns": [],
            }

        parsed_columns: List[Dict[str, Any]] = [
            {
                "cid": col[0],
                "name": col[1],
                "type": col[2],
                "not_null": bool(col[3]),
                "default_value": col[4],
                "primary_key": bool(col[5]),
            }
            for col in columns
        ]

        return {
            "success": True,
            "table_name": table_name,
            "columns": parsed_columns,
        }
    except sqlite3.Error as err:
        return {
            "success": False,
            "error": str(err),
            "columns": [],
        }
