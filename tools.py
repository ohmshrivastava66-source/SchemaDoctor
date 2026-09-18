"""
tools.py

Implements our custom tool system:
1. Tool: A lightweight wrapper around any Python function with rich metadata.
2. ToolRegistry: Stores tools, validates tool existence, and formats descriptions
   and expected arguments for the LLM planner.
"""

from typing import Callable, Dict, Any, List, Optional
import database
import dialect_knowledge


class Tool:
    """
    Represents a single tool the agent can use.

    Attributes:
        name: Unique string identifier (e.g., 'execute_sql').
        description: Non-prescriptive description of what the tool does and returns.
        expected_args: Dictionary describing expected argument names, types, and purposes.
        func: The underlying Python function.
    """

    def __init__(
        self,
        name: str,
        description: str,
        expected_args: Dict[str, str],
        func: Callable,
    ):
        self.name = name
        self.description = description
        self.expected_args = expected_args
        self.func = func

    def run(self, **kwargs) -> Any:
        """Executes the tool function with the provided keyword arguments."""
        return self.func(**kwargs)


class ToolRegistry:
    """
    Maintains the collection of available tools.
    The agent uses this registry to discover tools and execute them dynamically.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Adds a tool to the registry."""
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> Tool:
        """Retrieves a tool by name, or raises an error if not found."""
        if tool_name not in self._tools:
            available = ", ".join(f"'{k}'" for k in self._tools.keys())
            raise KeyError(f"Unknown tool '{tool_name}'. Available tools: [{available}]")
        return self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """Checks if a tool name exists in the registry."""
        return tool_name in self._tools

    def list_names(self) -> List[str]:
        """Returns the names of all registered tools."""
        return list(self._tools.keys())

    def get_descriptions(self) -> str:
        """
        Formats all tool names, descriptions, and expected arguments into a structured text block.
        This provides the LLM planner with the precise schema for every tool.
        """
        descriptions = []
        for name, tool in self._tools.items():
            args_lines = "\n".join(f"    - {arg}: {desc}" for arg, desc in tool.expected_args.items())
            block = (
                f"- Tool: '{name}'\n"
                f"  Description: {tool.description}\n"
                f"  Expected Arguments:\n{args_lines}"
            )
            descriptions.append(block)
        return "\n\n".join(descriptions)


# --- Tool Implementations ---

def tool_execute_sql(sql: str = "", **kwargs) -> str:
    """
    Executes migration SQL against the target SQLite database.
    """
    query_str = sql or kwargs.get("query") or kwargs.get("migration_sql") or ""
    if not query_str.strip():
        raise ValueError("Missing required argument 'sql'. You must provide the SQL string to execute.")

    result = database.execute_migration_sql(query_str)
    if result["success"]:
        return f"[SUCCESS]: {result['message']}"
    else:
        return f"[DATABASE ERROR]: {result['error']}"


def tool_lookup_dialect(query: str = "", **kwargs) -> str:
    """
    Looks up compatibility information for SQL dialect features.
    """
    search_term = query or kwargs.get("feature") or kwargs.get("keyword") or kwargs.get("error") or ""
    if not search_term.strip():
        raise ValueError("Missing required argument 'query'. Provide a keyword, feature, or error message to investigate.")

    return dialect_knowledge.lookup_dialect_rule(search_term)


def tool_verify_schema(table_name: str = "", **kwargs) -> str:
    """
    Inspects the resulting SQLite schema for a specified table.
    """
    name = table_name or kwargs.get("table") or ""
    if not name.strip():
        raise ValueError("Missing required argument 'table_name'. Provide the name of the table to inspect.")

    result = database.inspect_table_schema(name)
    if result["success"]:
        columns_summary = [f"{col['name']} ({col['type']})" for col in result["columns"]]
        return f"[VERIFIED SCHEMA] Table '{name}' columns: {', '.join(columns_summary)}"
    else:
        return f"[SCHEMA VERIFICATION FAILED]: {result['error']}"


def create_default_registry() -> ToolRegistry:
    """
    Creates and returns the default tool registry with SchemaDoctor's core tools.
    Descriptions are clear and non-prescriptive (no hardcoded routing rules).
    """
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="execute_sql",
            description="Execute migration SQL against the target SQLite database. Use this to test whether SQL executes successfully. Returns success or the real database error.",
            expected_args={"sql": "string - The raw SQL migration script to execute."},
            func=tool_execute_sql,
        )
    )

    registry.register(
        Tool(
            name="lookup_dialect_rule",
            description="Look up compatibility information for SQL dialect features. Use this when dialect differences or unsupported syntax need investigation.",
            expected_args={"query": "string - The SQL keyword, type, or error snippet to look up."},
            func=tool_lookup_dialect,
        )
    )

    registry.register(
        Tool(
            name="verify_schema",
            description="Inspect the resulting SQLite schema for a specified table. Use this after a migration succeeds when you need to confirm the expected schema exists.",
            expected_args={"table_name": "string - Name of the table to verify."},
            func=tool_verify_schema,
        )
    )

    return registry
