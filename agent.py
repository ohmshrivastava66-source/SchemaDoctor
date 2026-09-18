"""
agent.py

Our custom, lightweight Agent Framework built from scratch.

Core Loop:
    PLAN → ACT → OBSERVE → RE-PLAN / REPEAT

Autonomous Execution:
- The agent loop is controlled strictly by Python code (Agent.run).
- The planner (LLM or mock) decides the NEXT action based on observations.
- ToolRegistry executes the tool.
- Tool failures are caught safely and fed back into memory as observations.
- LLM API failures are captured cleanly as planner error states without
  improperly querying ToolRegistry for fake tools.
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import re
from tools import ToolRegistry


@dataclass
class StepRecord:
    """
    Represents a single step in the agent's trajectory:
    - step_number: 1, 2, 3...
    - thought: Reasoning/rationale behind the step
    - action: The chosen tool name (or 'finish')
    - action_args: Parameters passed to the tool
    - observation: Real output or error observed from the environment/tool
    """
    step_number: int
    thought: str
    action: str
    action_args: Dict[str, Any]
    observation: Optional[str] = None


@dataclass
class AgentState:
    """
    Stores the memory and current state of the agent run.
    """
    task: str
    history: List[StepRecord] = field(default_factory=list)
    status: str = "initialized"  # "initialized", "running", "completed", "max_iterations_reached", "error"
    final_result: Optional[str] = None

    def add_step(self, step: StepRecord) -> None:
        self.history.append(step)

    def get_trajectory_summary(self) -> str:
        """Returns a formatted summary of past steps for context."""
        if not self.history:
            return "No previous steps taken yet. This is Iteration 1."

        summary_lines = []
        for s in self.history:
            summary_lines.append(
                f"Step {s.step_number}:\n"
                f"  Thought: {s.thought}\n"
                f"  Action Taken: {s.action}\n"
                f"  Arguments: {s.action_args}\n"
                f"  Observation: {s.observation}"
            )
        return "\n\n".join(summary_lines)


class Agent:
    """
    The Brain: Coordinates the custom PLAN → ACT → OBSERVE → RE-PLAN loop.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        max_iterations: int = 7,
        planner_func: Optional[Callable[[str, AgentState, str], Dict[str, Any]]] = None,
        use_mock: bool = False,
    ):
        """
        Args:
            tool_registry: ToolRegistry containing tools available to the agent.
            max_iterations: Safety ceiling to prevent infinite loops.
            planner_func: Pluggable planner function (e.g. llm_client.llm_planner).
            use_mock: If True, forces the mock planner regardless of API keys.
        """
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.planner_func = planner_func
        self.use_mock = use_mock

    # -------------------------------------------------------------------------
    # 1. PLAN STEP
    # -------------------------------------------------------------------------
    def plan(self, state: AgentState) -> Dict[str, Any]:
        """
        PLAN step:
        Requests a decision from the planner (LLM or mock) based on the task,
        tool descriptions, and full observation history.

        Returns a dictionary:
          {
            "thought": "short rationale",
            "action": "tool_name_or_finish",
            "args": {...}
          }
        """
        if self.use_mock or not self.planner_func:
            return self._default_mock_planner(state)

        tools_doc = self.tool_registry.get_descriptions()
        return self.planner_func(state.task, state, tools_doc)

    # -------------------------------------------------------------------------
    # 2. ACT STEP
    # -------------------------------------------------------------------------
    def act(self, action_name: str, action_args: Dict[str, Any]) -> str:
        """
        ACT step:
        Dispatches the chosen tool through ToolRegistry.
        Rejects unknown tools safely, catches missing arguments,
        and converts all failures into formatted observations.
        Does NOT crash the agent.
        """
        if action_name == "finish":
            return action_args.get("message", "Migration complete and verified.")

        # Rejection of unknown tools
        if not self.tool_registry.has_tool(action_name):
            available = ", ".join(f"'{k}'" for k in self.tool_registry.list_names())
            return f"[AGENT ERROR]: Unknown tool '{action_name}'. Available tools are: [{available}]"

        try:
            tool = self.tool_registry.get(action_name)
            result = tool.run(**action_args)
            return str(result)
        except TypeError as type_err:
            return f"[AGENT ERROR]: Invalid arguments for tool '{action_name}': {str(type_err)}"
        except ValueError as val_err:
            return f"[AGENT ERROR]: {str(val_err)}"
        except Exception as err:
            return f"[AGENT ERROR]: Tool '{action_name}' encountered an error: {str(err)}"

    # -------------------------------------------------------------------------
    # 3. OBSERVE STEP
    # -------------------------------------------------------------------------
    def observe(self, current_step: StepRecord, observation: str) -> None:
        """
        OBSERVE step:
        Records the tool's real result (or error message) into the step record.
        """
        current_step.observation = observation

    # -------------------------------------------------------------------------
    # 4. CORE AGENT LOOP (PLAN → ACT → OBSERVE → RE-PLAN / REPEAT)
    # -------------------------------------------------------------------------
    def run(self, task: str) -> AgentState:
        """
        Executes the main agent loop.
        Repeats until the agent chooses 'finish' or reaches max_iterations.
        """
        state = AgentState(task=task)
        state.status = "running"

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # --- STEP 1: PLAN (or RE-PLAN on subsequent iterations) ---
            decision = self.plan(state)

            # Check if planner experienced an API / HTTP / Parsing error
            # This handles LLM failures properly without sending fake tools to ToolRegistry!
            if decision.get("is_error"):
                thought = decision.get("thought", "Planner error encountered.")
                error_msg = decision.get("error", "Unknown API error")
                current_step = StepRecord(
                    step_number=iteration,
                    thought=thought,
                    action="[PLANNER_API_ERROR]",
                    action_args={"error": error_msg},
                    observation=f"[LLM API ERROR]: {thought} - Details: {error_msg}",
                )
                state.add_step(current_step)
                state.status = "error"
                state.final_result = f"Stopped: LLM planning failed ({thought})."
                break

            thought = decision.get("thought", "No thought provided.")
            action = decision.get("action", "finish")
            action_args = decision.get("args", {})

            current_step = StepRecord(
                step_number=iteration,
                thought=thought,
                action=action,
                action_args=action_args,
            )

            # Stopping condition check
            if action == "finish":
                current_step.observation = "Goal satisfied and verified."
                state.add_step(current_step)
                state.status = "completed"
                state.final_result = action_args.get("message", "Task completed.")
                break

            # --- STEP 2: ACT ---
            observation = self.act(action, action_args)

            # --- STEP 3: OBSERVE ---
            self.observe(current_step, observation)
            state.add_step(current_step)

            # --- STEP 4: RE-PLAN happens automatically in the next loop iteration! ---

        if state.status not in ("completed", "error"):
            state.status = "max_iterations_reached"
            state.final_result = "Stopped: Maximum iteration limit reached before completion."

        return state

    # -------------------------------------------------------------------------
    # Fallback Mock Planner (for offline testing & development)
    # -------------------------------------------------------------------------
    def _default_mock_planner(self, state: AgentState) -> Dict[str, Any]:
        """
        An observation-driven fallback planner for offline demonstration:
        - If no steps: executes the SQL.
        - If previous step observed [SUCCESS]: moves directly to verify_schema!
        - If previous step observed [DATABASE ERROR]: looks up dialect rules.
        - If previous step observed dialect rules: rewrites SQL and re-executes.
        - If previous step observed [VERIFIED SCHEMA]: concludes with finish.
        """
        table_match = re.search(r"CREATE\s+TABLE\s+(\w+)", state.task, re.IGNORECASE)
        table_name = table_match.group(1) if table_match else "unknown_table"

        if not state.history:
            return {
                "thought": "First, test executing the migration SQL to observe if SQLite accepts it.",
                "action": "execute_sql",
                "args": {"sql": state.task},
            }

        last_step = state.history[-1]
        last_obs = last_step.observation or ""

        # SCENARIO A: The previous execution SUCCEEDED immediately!
        if "[SUCCESS]" in last_obs and last_step.action == "execute_sql":
            return {
                "thought": f"SQL executed successfully. Now inspecting schema of table '{table_name}' to confirm columns.",
                "action": "verify_schema",
                "args": {"table_name": table_name},
            }

        # SCENARIO B: The previous execution encountered a DATABASE ERROR!
        if "[DATABASE ERROR]" in last_obs:
            return {
                "thought": f"Execution failed with error: '{last_obs}'. Investigating dialect differences for SQLite.",
                "action": "lookup_dialect_rule",
                "args": {"query": "BIGSERIAL JSONB NOW()"},
            }

        # SCENARIO C: Dialect rules have been retrieved!
        if last_step.action == "lookup_dialect_rule":
            fixed_sql = (
                f"CREATE TABLE {table_name} (\n"
                "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                "    profile TEXT,\n"
                "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
                ");"
            )
            return {
                "thought": "Translating PostgreSQL features (BIGSERIAL -> INTEGER PRIMARY KEY AUTOINCREMENT, JSONB -> TEXT, NOW() -> CURRENT_TIMESTAMP). Executing rewritten SQL.",
                "action": "execute_sql",
                "args": {"sql": fixed_sql},
            }

        # SCENARIO D: Schema verification succeeded!
        if "[VERIFIED SCHEMA]" in last_obs:
            return {
                "thought": f"Table schema confirmed: {last_obs}. Migration is verified and complete.",
                "action": "finish",
                "args": {"message": f"Table '{table_name}' successfully migrated and verified in SQLite."},
            }

        return {
            "thought": "Observation confirmed. Concluding process.",
            "action": "finish",
            "args": {"message": "Process concluded based on latest observation."},
        }
