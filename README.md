# SchemaDoctor

> Autonomous database migration repair agent powered by a custom-built **PLAN → ACT → OBSERVE → RE-PLAN** framework.

Built for **EPOCHESQUE 2.0 — Track 2: "BUILD THE BRAIN, NOT THE PUPPET"**.

---

## Problem

Database migration scripts written for one database dialect often fail when executed on another due to dialect-specific syntax differences.

For example, executing a PostgreSQL table definition on SQLite:
```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    profile JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```
SQLite rejects PostgreSQL-specific types (`BIGSERIAL`, `JSONB`) and functions (`NOW()`), immediately halting database provisioning.

---

## Solution

**SchemaDoctor** is an autonomous migration repair agent that:
1. **Plans** actions based on empirical database feedback.
2. **Executes** the incoming SQL against the real target database.
3. **Observes** the genuine SQLite syntax error (`near "(": syntax error`).
4. **Re-plans** dynamically, diagnosing the failure and rewriting the SQL.
5. **Retries** execution until success is achieved.
6. **Verifies** the resulting table schema in the target database.

---

## Architecture: Custom Agent Framework

SchemaDoctor's control loop is **100% our own implementation** in Python standard library (`agent.py`). It does **NOT** use LangChain, CrewAI, AutoGen, or any third-party agent orchestration framework.

```text
                     Incoming Migration Task
                               │
                               ▼
                        ┌──────────────┐
                        │   1. PLAN    │ ◄─────────────────────────┐
                        └──────┬───────┘                           │
                               │                                   │
                               ▼                                   │
                        ┌──────────────┐                           │
                        │   2. ACT     │ ──▶ ToolRegistry          │
                        └──────┬───────┘     Dispatches Tool       │
                               │                                   │
                               ▼                                   │
                        ┌──────────────┐                           │
                        │  3. OBSERVE  │                           │
                        └──────┬───────┘                           │
                               │                                   │
                               ▼                                   │
                        ┌──────────────┐                           │
                        │  4. RE-PLAN  │ ──────────────────────────┘
                        └──────────────┘ (Next loop iteration evaluates
                                          real database observation)
```

The LLM acts as the **reasoning brain** inside `plan()`, while our Python runtime manages state memory, tool dispatching, iteration bounds, and error recovery.

---

## Tools

All tools are standard Python functions registered with rich metadata in our custom `ToolRegistry` (`tools.py`):

| Tool Name | Purpose | Expected Arguments |
| :--- | :--- | :--- |
| **`execute_sql`** | Executes migration SQL against the target SQLite database. Returns success or the real database error. | `sql` (string) |
| **`lookup_dialect_rule`** | Queries dialect compatibility documentation for syntax conversion rules between PostgreSQL and SQLite. | `query` (string) |
| **`verify_schema`** | Inspects SQLite's internal catalog (`PRAGMA table_info`) to verify columns and data types after migration. | `table_name` (string) |

---

## Autonomous Decision-Making (No Hardcoded Routing)

A core requirement of Track 2 is that the agent must autonomously choose its tools. In SchemaDoctor:
- **No hardcoded `if` statements** decide which tool to call (`if "BIGSERIAL" in sql: lookup_dialect_rule()`).
- **No fixed sequences** exist in the code (`execute_sql → lookup → rewrite → verify`).
- **The LLM planner** receives:
  1. The migration task.
  2. The available tool definitions and argument schemas.
  3. The complete observation history (including past execution errors).
- The LLM returns a structured JSON decision:
  ```json
  {
    "thought": "short explanation of why this action is appropriate",
    "action": "tool_name_or_finish",
    "args": { "argument_name": "value" }
  }
  ```
- Tool selection is dynamically driven by the environment. In **Scenario 2** (`already_compatible.sql`), because the initial execution succeeds immediately, the agent autonomously skips dialect repair and moves straight to verification.

---

## Real Failure Detection & Recovery

SchemaDoctor follows an **Empirical Baseline Principle**: it always tests the unmodified migration script first to observe real database feedback.

When PostgreSQL syntax runs on SQLite:
1. SQLite fails with: `[DATABASE ERROR]: near "(": syntax error`.
2. This failure is captured safely as an observation without crashing the program.
3. On the next planning iteration, the LLM reads the error, diagnoses the incompatibility, rewrites the SQL, and retries.

---

## Real LLM Provider Configuration

SchemaDoctor is provider-configurable via environment variables (`llm_client.py`):

### Option 1: Local Ollama (Zero Cost, No Rate Limits)
SchemaDoctor supports local Ollama models (such as `gemma4:latest` or `llama2-uncensored:latest`):
```bash
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=gemma4:latest
export OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
```

### Option 2: Google Gemini
```bash
export LLM_PROVIDER=gemini
export GEMINI_API_KEY="your-gemini-api-key"
export GEMINI_MODEL=gemini-3.6-flash
```

### Option 3: OpenAI / Groq / OpenRouter
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY="your-openai-or-groq-key"
export OPENAI_MODEL=gpt-4o-mini
# Optional custom base URL:
# export OPENAI_BASE_URL="https://api.groq.com/openai/v1"
```

*(API keys are read strictly from environment variables or a local untracked `.env` file — never committed to source control).*

---

## Running SchemaDoctor

### 1. Interactive Browser Demo (Recommended for Judges)

Launch the zero-dependency standard-library web UI:
```bash
python3 server.py
```
Then open your browser to:
👉 **[http://localhost:8080](http://localhost:8080)**

Features:
- Paste any migration SQL or click the pre-filled example buttons.
- Click **"Run SchemaDoctor"** to observe the real agent execute live against SQLite.
- Inspect the complete trajectory: `PLAN` $\rightarrow$ `ACT` $\rightarrow$ `OBSERVE` $\rightarrow$ `RE-PLAN` $\rightarrow$ `VERIFY`.
- Toggle between Real LLM Mode (local Ollama / Gemini) and Offline Mock Planner.

### 2. Command-Line Trace

```bash
# Run both scenarios back-to-back in REAL LLM Mode:
python3 main.py --all

# Run individual migration scenario:
python3 main.py examples/postgres_to_sqlite.sql
python3 main.py examples/already_compatible.sql

# Run in offline Mock Planner mode (for development / framework testing):
python3 main.py --mock --all
```

---

## Track 2 Compliance Checklist

| Requirement | Implementation in SchemaDoctor | Status |
| :--- | :--- | :---: |
| **1. Custom Agent Framework** | Built from scratch in `agent.py` and `tools.py` using Python standard library. | ✅ Pass |
| **2. No External Frameworks** | Zero LangChain, CrewAI, AutoGen, or third-party agent loop libraries. | ✅ Pass |
| **3. At Least 2 Tools** | 3 tools registered in `ToolRegistry` (`execute_sql`, `lookup_dialect_rule`, `verify_schema`). | ✅ Pass |
| **4. Autonomous Tool Selection** | Planner chooses actions from tool schemas; no hardcoded routing in Python. | ✅ Pass |
| **5. Failure & Recovery** | Real SQLite parser error is captured as an observation and used to re-plan repairs. | ✅ Pass |
| **6. Real End-to-End Problem** | Successfully migrates incompatible PostgreSQL schema to SQLite and verifies it. | ✅ Pass |

---

## Current Limitations

1. **Multi-Table DDL Scripts**: Current schema verification inspects one table at a time; composite migrations with multiple `CREATE TABLE` statements require multiple verification passes.
2. **Advanced SQL Features**: Dialect knowledge currently focuses on core incompatible types (`BIGSERIAL`, `JSONB`, `NOW()`, `SERIAL`, `BOOLEAN`); advanced features (e.g., custom domains, partial indexes, triggers) will be added in future versions.
