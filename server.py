"""
server.py

Lightweight Python standard-library web server for SchemaDoctor.
Zero extra dependencies required.

Serves:
- GET /            -> Interactive Web UI (index.html)
- POST /api/repair -> Runs the real custom SchemaDoctor agent against SQLite and returns step trajectory
"""

import os
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from agent import Agent
from tools import create_default_registry
import database
import llm_client


PORT = int(os.getenv("PORT", 8080))
BASE_DIR = Path(__file__).parent


class SchemaDoctorHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html_file = BASE_DIR / "index.html"
            if not html_file.exists():
                self.send_error(404, "index.html not found")
                return

            with open(html_file, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/api/status":
            provider_info = llm_client.get_active_provider_info()
            self._send_json(200, {
                "configured": llm_client.is_configured(),
                "provider": provider_info[0],
                "model": provider_info[1]
            })
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/repair":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            try:
                payload = json.loads(body)
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON payload: {e}"})
                return

            sql = payload.get("sql", "").strip()
            mode = payload.get("mode", "real")

            if not sql:
                self._send_json(400, {"error": "Missing 'sql' in request body."})
                return

            # 1. Reset the web demo database cleanly
            db_file = "web_demo.db"
            database.reset_database(db_file)

            # 2. Setup ToolRegistry
            registry = create_default_registry()

            # 3. Configure Planner
            use_mock = (mode == "mock") or not llm_client.is_configured()
            planner = None if use_mock else llm_client.llm_planner

            # 4. Initialize and run our custom Agent
            agent = Agent(
                tool_registry=registry,
                max_iterations=7,
                planner_func=planner,
                use_mock=use_mock,
            )

            final_state = agent.run(task=sql)

            # 5. Format and return step trajectory
            steps_data = []
            for s in final_state.history:
                steps_data.append({
                    "step_number": s.step_number,
                    "thought": s.thought,
                    "action": s.action,
                    "action_args": s.action_args,
                    "observation": s.observation,
                })

            provider_info = ("Mock", "Deterministic") if use_mock else llm_client.get_active_provider_info()

            self._send_json(200, {
                "status": final_state.status,
                "result": final_state.final_result,
                "provider": provider_info,
                "steps": steps_data,
            })
        else:
            self.send_error(404, "Endpoint not found")


def run_server(port: int = PORT):
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, SchemaDoctorHandler)
    provider, model = llm_client.get_active_provider_info()
    print("=" * 70)
    print("      🏥 SchemaDoctor Web Demo Server Started")
    print(f"      📍 Local URL: http://127.0.0.1:{port}")
    print(f"      🧠 Brain: {provider} ({model})")
    print("=" * 70)
    print("Press Ctrl+C to stop the server.")
    httpd.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    try:
        run_server(port)
    except KeyboardInterrupt:
        print("\n[SchemaDoctor Server stopped.]")
