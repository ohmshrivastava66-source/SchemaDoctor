"""
main.py

Entry point for SchemaDoctor.
Demonstrates autonomous database migration repair using our custom agent framework:
    PLAN → ACT → OBSERVE → RE-PLAN

Supports:
1. Real LLM Mode (GEMINI_API_KEY or OPENAI_API_KEY)
2. Fallback Mock Mode (--mock or when no API key is present)
3. Multiple scenarios:
   - Scenario 1: postgres_to_sqlite.sql (Requires repair: Failure -> Lookup -> Rewrite -> Verify)
   - Scenario 2: already_compatible.sql (Already valid: Success -> Verify -> Finish)
"""

import sys
import os
from pathlib import Path
from agent import Agent
from tools import create_default_registry
import database
import llm_client


def print_banner(mode_text: str):
    print("=" * 70)
    print("                         SchemaDoctor")
    print("             Autonomous Database Migration Repair Agent")
    print("       Custom PLAN → ACT → OBSERVE → RE-PLAN Control Framework")
    print("           Track 2: 'BUILD THE BRAIN, NOT THE PUPPET'")
    print("=" * 70)
    print(f"Mode: {mode_text}")
    print("=" * 70)


def format_step_trace(step):
    print("-" * 60)
    plan_label = "PLAN" if step.step_number == 1 else "RE-PLAN / PLAN"
    print(f"ITERATION {step.step_number}")
    print(f"{plan_label}")
    print(f"Thought:   {step.thought}")

    if step.action == "[PLANNER_API_ERROR]":
        print("Action:    [PLANNER FAILED]")
        print(f"Arguments: {step.action_args}")
        print()
        print("ACT")
        print("Tool:      [SKIPPED - Planner encountered an API error]")
        print()
        print("OBSERVE")
        print(f"Result:    {step.observation}")
    else:
        print(f"Action:    {step.action}")
        print(f"Arguments: {step.action_args}")
        print()
        print("ACT")
        print(f"Tool:      {step.action}")
        print()
        print("OBSERVE")
        print(f"Result:    {step.observation}")


def run_scenario(sql_file_path: Path, agent: Agent, scenario_title: str):
    print(f"\n▶ RUNNING: {scenario_title}")
    print(f"  File: {sql_file_path.name}")
    print("~" * 60)

    # 1. Reset database
    db_file = "migration_test.db"
    database.reset_database(db_file)

    # 2. Read migration SQL
    with open(sql_file_path, "r") as f:
        migration_sql = f.read().strip()

    print("Input Migration SQL:")
    for line in migration_sql.splitlines():
        print(f"  | {line}")
    print("~" * 60)

    # 3. Run the Agent Loop
    final_state = agent.run(task=migration_sql)

    # 4. Display step-by-step trace
    for step in final_state.history:
        format_step_trace(step)

    print("-" * 60)
    print(f"STATUS: {final_state.status.upper()}")
    print(f"RESULT: {final_state.final_result}")
    print("=" * 70)


def main():
    force_mock = "--mock" in sys.argv
    run_all = "--all" in sys.argv

    # Check for target file argument
    custom_file = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            custom_file = Path(arg)
            break

    # Setup ToolRegistry
    registry = create_default_registry()

    # Determine Mode
    if not force_mock and llm_client.is_configured():
        provider, model = llm_client.get_active_provider_info()
        mode_text = f"REAL LLM MODE ({provider} - {model})"
        planner = llm_client.llm_planner
        use_mock = False
    else:
        mode_text = "MOCK MODE (Development / Offline Fallback)"
        planner = None
        use_mock = True

    print_banner(mode_text)

    if use_mock and not force_mock:
        print("💡 Note: No API key detected. Running in Fallback Mock Mode.")
        print("   To switch to REAL LLM MODE, set an environment variable:")
        print("     export GEMINI_API_KEY='your_key'")
        print("     # OR: export OPENAI_API_KEY='your_key'\n")

    # Determine which scenarios to run
    examples_dir = Path(__file__).parent / "examples"
    scenario1_path = examples_dir / "postgres_to_sqlite.sql"
    scenario2_path = examples_dir / "already_compatible.sql"

    if custom_file:
        target_path = custom_file if custom_file.is_absolute() else Path.cwd() / custom_file
        if not target_path.exists():
            print(f"Error: File not found at {target_path}")
            return
        agent = Agent(tool_registry=registry, max_iterations=7, planner_func=planner, use_mock=use_mock)
        run_scenario(target_path, agent, f"Custom File: {target_path.name}")
    elif run_all:
        print("Running BOTH scenarios to demonstrate autonomous decision making:\n")
        agent1 = Agent(tool_registry=registry, max_iterations=7, planner_func=planner, use_mock=use_mock)
        run_scenario(scenario1_path, agent1, "Scenario 1: PostgreSQL Incompatible Migration (Requires Failure & Repair)")

        agent2 = Agent(tool_registry=registry, max_iterations=7, planner_func=planner, use_mock=use_mock)
        run_scenario(scenario2_path, agent2, "Scenario 2: Already SQLite-Compatible Migration (Proves No Hardcoded Sequence)")
    else:
        agent = Agent(tool_registry=registry, max_iterations=7, planner_func=planner, use_mock=use_mock)
        run_scenario(scenario1_path, agent, "Scenario 1: PostgreSQL Incompatible Migration (Requires Failure & Repair)")
        print("\n💡 TIP: Run Scenario 2 to prove tool sequence is NOT hardcoded:")
        print("     python3 main.py examples/already_compatible.sql")
        print("   Or run both scenarios back-to-back:")
        print("     python3 main.py --all")


if __name__ == "__main__":
    main()
