"""
llm_client.py

Handles LLM communications for SchemaDoctor:
1. Provider-configurable:
   - Ollama (Local real LLM via OpenAI-compatible endpoint at http://127.0.0.1:11434/v1)
   - Google Gemini (via REST API)
   - OpenAI / OpenAI-compatible (via REST API)
2. Formulates the planning prompt with:
   - System instructions (autonomous decision making)
   - Available tools and expected arguments
   - Original migration task
   - Complete execution history (actions, database results, errors)
3. Enforces valid JSON response:
   {
       "thought": "short decision rationale",
       "action": "tool_name_or_finish",
       "args": {}
   }
4. Strips markdown fences, parses JSON, and safely reports API / HTTP errors.
"""

import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Tuple, Optional


# =============================================================================
# 0. Environment File Auto-Loader & Local Discovery
# =============================================================================

def _load_env_if_present() -> None:
    """Loads environment variables from local .env file if present."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val

_load_env_if_present()


def _check_ollama_alive() -> bool:
    """Checks if local Ollama instance is responding."""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


# =============================================================================
# 1. Configuration & Provider Detection
# =============================================================================

def is_configured() -> bool:
    """Returns True if a valid real LLM provider is available."""
    _load_env_if_present()
    provider = os.getenv("LLM_PROVIDER", "").lower()
    if provider == "ollama":
        return _check_ollama_alive()
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))

    # Auto-detection: Ollama local service, then Gemini, then OpenAI
    if _check_ollama_alive():
        return True
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))


def get_active_provider_info() -> Tuple[str, str]:
    """
    Returns: (provider_name, model_name)
    """
    _load_env_if_present()
    provider = os.getenv("LLM_PROVIDER", "").lower()

    if provider == "ollama" or (not provider and _check_ollama_alive() and not os.getenv("GEMINI_API_KEY")):
        model = os.getenv("OLLAMA_MODEL", "gemma4:latest")
        return "Ollama (Local)", model
    elif provider == "gemini":
        model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        return "Gemini", model
    elif provider == "openai" or (not provider and os.getenv("OPENAI_API_KEY")):
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return "OpenAI-Compatible", model
    elif _check_ollama_alive():
        # Fallback to local Ollama if running
        model = os.getenv("OLLAMA_MODEL", "gemma4:latest")
        return "Ollama (Local)", model
    elif os.getenv("GEMINI_API_KEY"):
        model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        return "Gemini", model

    return "None", "mock"


# =============================================================================
# 2. JSON Parser & Sanitizer
# =============================================================================

def extract_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """
    Safely extracts and parses JSON from the LLM's response.
    Handles markdown code block fences (```json ... ```) and leading/trailing chatter.
    """
    cleaned = raw_text.strip()

    # Remove markdown code block fences if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Find outermost JSON object brackets { ... }
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        cleaned = cleaned[start_idx : end_idx + 1]

    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object (dict), but got {type(parsed).__name__}")

    return parsed


# =============================================================================
# 3. HTTP API Callers (Standard Library urllib - Zero extra dependencies)
# =============================================================================

def _call_gemini(api_key: str, model: str, prompt: str) -> str:
    """Calls Google Gemini REST API with retry for transient 503/429 errors."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "maxOutputTokens": 2048,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini API returned no candidates: {result}")
                return candidates[0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as http_err:
            if http_err.code == 503 and attempt < max_attempts:
                time.sleep(2 * attempt)
                continue
            raise


def _call_openai(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: Optional[str] = None,
) -> str:
    """Calls OpenAI-compatible /v1/chat/completions endpoint (supports OpenAI, Groq, Ollama)."""
    if not base_url:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
        choices = result.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM API returned no choices: {result}")
        return choices[0]["message"]["content"]


# =============================================================================
# 4. System Prompt & Planner
# =============================================================================

def build_system_prompt(tools_description: str) -> str:
    return f"""You are the planning component of SchemaDoctor.
You do NOT execute tools yourself.
You must choose exactly one next action from the available tools or finish.
Base your decision on the current migration task and the complete history of previous observations.
Do not assume that a particular tool must always be called next.

Empirical Baseline Principle:
On the first action for a migration task, test the input migration SQL as provided against the target database. Do not pre-emptively rewrite the migration before observing database feedback. After observing the database result, choose the next action based on that observation.

If the previous action succeeded, decide whether more work or verification is necessary.
If the previous action failed, analyze the error and decide what information or action is needed to recover.
You may call the same tool more than once when appropriate.
Do not claim that an action succeeded unless an observation confirms it.
Return ONLY valid JSON.

AVAILABLE TOOLS:
{tools_description}

SPECIAL ACTION:
- Tool: 'finish'
  Description: Conclude the migration repair process once execution has succeeded and table schema is verified.
  Expected Arguments:
    - message: string - A clear explanation of what was accomplished and confirmed.

RESPONSE FORMAT:
You must respond with raw JSON matching this structure:
{{
  "thought": "short reasoning for the decision",
  "action": "tool_name_or_finish",
  "args": {{
    "argument_name": "value"
  }}
}}
Do NOT output any markdown, explanations, or text outside the JSON object.
"""


def build_user_prompt(task: str, history_summary: str) -> str:
    return f"""ORIGINAL MIGRATION TASK:
==================================================
{task}
==================================================

EXECUTION HISTORY & PREVIOUS OBSERVATIONS:
==================================================
{history_summary}
==================================================

Analyze the history and observations above. Decide your single next action.
Respond with raw JSON only."""


def llm_planner(task: str, state: Any, tools_description: str) -> Dict[str, Any]:
    """
    The autonomous LLM planner:
    Calls configured LLM API (Ollama, Gemini, OpenAI) with task, history, and available tool schemas.
    Catches API / HTTP errors and returns structured error objects.
    """
    history_summary = state.get_trajectory_summary()
    system_prompt = build_system_prompt(tools_description)
    user_prompt = build_user_prompt(task, history_summary)

    provider, model = get_active_provider_info()

    try:
        if "Ollama" in provider:
            base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
            raw_response = _call_openai("ollama", model, system_prompt, user_prompt, base_url=base_url)
        elif "Gemini" in provider:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                raise RuntimeError("GEMINI_API_KEY is not set.")
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            raw_response = _call_gemini(gemini_key, model, full_prompt)
        elif "OpenAI" in provider:
            openai_key = os.getenv("OPENAI_API_KEY")
            raw_response = _call_openai(openai_key, model, system_prompt, user_prompt)
        else:
            raise RuntimeError(f"No configured LLM provider found (active: {provider}).")

    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8") if hasattr(http_err, "read") else ""
        return {
            "is_error": True,
            "error_type": "HTTP_ERROR",
            "status_code": http_err.code,
            "thought": f"LLM API request failed with HTTP {http_err.code}",
            "error": err_body.strip(),
        }
    except Exception as err:
        return {
            "is_error": True,
            "error_type": "API_ERROR",
            "thought": f"Error calling LLM API: {str(err)}",
            "error": str(err),
        }

    # Parse JSON safely
    try:
        decision = extract_and_parse_json(raw_response)
    except Exception as parse_err:
        return {
            "is_error": True,
            "error_type": "INVALID_JSON",
            "thought": f"Invalid JSON received from LLM: {parse_err}",
            "error": f"Raw response was: {raw_response[:200]}",
        }

    thought = decision.get("thought", "No thought rationale provided.")
    action = decision.get("action", "unknown_tool")
    args = decision.get("args", {})
    if not isinstance(args, dict):
        args = {}

    return {
        "is_error": False,
        "thought": thought,
        "action": action,
        "args": args,
    }
