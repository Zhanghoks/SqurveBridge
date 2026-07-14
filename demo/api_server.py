"""HTTP API for the interactive Squrve demo workspace."""

from __future__ import annotations

import atexit
import codecs
import fcntl
import hashlib
import ipaddress
import json
import os
import pty
import re
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import Flask, jsonify, request
from flask_sock import Sock
from sqlglot import exp, parse

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from demo.file_to_db import process_uploaded_files, sqlite_to_schema
from demo.gradio_demo import (
    ACTOR_BY_TYPE,
    WORKFLOW_SKELETONS,
    SqurveDemo,
    get_available_databases,
    get_router_config_path,
    get_uploaded_db_root,
)
from reproduce.lib.env_config import (
    PROVIDER_ENV_VARS,
    api_key_ready,
    load_dotenv,
    resolve_api_key,
)
from tools.profile_weakness import build_weakness_json
from tools.evidence import EvidenceError, verify_bundle
from demo.security import AGENT_TERMINAL_ENV, agent_terminals_enabled


app = Flask(__name__)
sock = Sock(app)
_demo_instances: dict[tuple[str, str], SqurveDemo] = {}
_demo_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_processes: dict[str, subprocess.Popen] = {}
_run_dir = _project_root / "tmp" / "demo-runs"
_provider_validation = {"verified": False, "error": None}
_runtime_llm: dict[str, str | None] = {"provider": None, "model": None}
_sample_limits = {3, 10, 20, 50, 100, 200}
_provider_models = {
    "qwen": ["qwen-turbo", "qwen-plus", "qwen-max", "deepseek-v4-flash"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "zhipu": ["glm-4-plus", "glm-4-flash"],
    "openai": ["gpt-4o-mini", "gpt-4.1-mini"],
    "claude": ["claude-3-5-sonnet-latest"],
    "gemini": ["gemini-2.0-flash"],
}
_terminal_sessions: dict[str, "AgentPtySession"] = {}
_terminal_lock = threading.Lock()
_agent_commands = {"codex": "codex", "claude": "claude"}


class AgentPtySession:
    """One interactive coding agent attached to a pseudo-terminal."""

    def __init__(self, agent: str, command: str, cols: int = 110, rows: int = 34):
        self.session_id = uuid.uuid4().hex[:12]
        self.agent = agent
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._output = ""
        self._output_base = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.exit_code = None
        env = os.environ.copy()
        env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor"})
        argv = [command, "--no-alt-screen", "--sandbox", "workspace-write", "--ask-for-approval", "on-request", "-C", str(_project_root)] if agent == "codex" else [command, "--permission-mode", "manual"]
        pid, master_fd = pty.fork()
        if pid == 0:
            os.chdir(_project_root)
            os.execvpe(command, argv, env)
        self.pid = pid
        self.master_fd = master_fd
        self.resize(cols, rows)
        threading.Thread(target=self._read_output, daemon=True).start()

    @property
    def running(self) -> bool:
        with self._lock:
            if self.exit_code is not None:
                return False
        try:
            waited_pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return False
        if waited_pid == 0:
            return True
        with self._lock:
            self.exit_code = os.waitstatus_to_exitcode(status)
        return False

    def _read_output(self) -> None:
        try:
            while True:
                try:
                    chunk = os.read(self.master_fd, 32768)
                except OSError:
                    break
                if not chunk:
                    break
                self._append(self._decoder.decode(chunk))
        finally:
            try:
                _, status = os.waitpid(self.pid, 0)
                with self._lock:
                    self.exit_code = os.waitstatus_to_exitcode(status)
            except ChildProcessError:
                pass
            self._append(self._decoder.decode(b"", final=True))

    def _append(self, text: str) -> None:
        with self._condition:
            self._output += text
            if len(self._output) > 2_000_000:
                trim = len(self._output) - 1_500_000
                self._output = self._output[trim:]
                self._output_base += trim
            self._condition.notify_all()

    def read(self, cursor: int) -> tuple[str, int]:
        with self._lock:
            cursor = max(cursor, self._output_base)
            start = cursor - self._output_base
            return self._output[start:], self._output_base + len(self._output)

    def wait_read(self, cursor: int, timeout: float = .25) -> tuple[str, int]:
        with self._condition:
            if cursor >= self._output_base + len(self._output) and self.running:
                self._condition.wait(timeout)
            cursor = max(cursor, self._output_base)
            start = cursor - self._output_base
            return self._output[start:], self._output_base + len(self._output)

    def write(self, data: str) -> None:
        if not self.running:
            raise RuntimeError(f"{self.agent} terminal has exited.")
        os.write(self.master_fd, data.encode("utf-8"))

    def resize(self, cols: int, rows: int) -> None:
        cols = max(40, min(int(cols), 300))
        rows = max(12, min(int(rows), 100))
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def stop(self) -> None:
        if self.running:
            try:
                os.killpg(self.pid, signal.SIGTERM)
                deadline = time.monotonic() + 2
                while self.running and time.monotonic() < deadline:
                    time.sleep(.05)
            except ProcessLookupError:
                pass
            if self.running:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            os.close(self.master_fd)
        except OSError:
            pass

    def public_state(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent": self.agent,
            "running": self.running,
            "exit_code": self.exit_code,
            "cwd": str(_project_root),
        }


def _local_request_error():
    try:
        is_local = ipaddress.ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        is_local = False
    if not is_local:
        return _json_error("Agent access is restricted to localhost.", 403)
    origin = request.headers.get("Origin")
    allowed_origins = {"http://127.0.0.1:5173", "http://localhost:5173"}
    if origin and origin not in allowed_origins:
        return _json_error("Agent access is restricted to the local Squrve workspace.", 403)
    return None


def _agent_terminal_access_error():
    local_error = _local_request_error()
    if local_error:
        return local_error
    if not agent_terminals_enabled():
        return _json_error(
            f"Agent terminals are disabled. Set {AGENT_TERMINAL_ENV}=1 only in a trusted local workspace.",
            403,
        )
    return None


def _stop_terminal_sessions() -> None:
    with _terminal_lock:
        sessions = list(_terminal_sessions.values())
        _terminal_sessions.clear()
    for session in sessions:
        session.stop()


atexit.register(_stop_terminal_sessions)


def _json_error(message: str, status: int = 400):
    return jsonify({"status": "error", "message": message}), status


@app.after_request
def _allow_local_frontend(response):
    origin = request.headers.get("Origin", "")
    if origin.startswith(("http://127.0.0.1:", "http://localhost:")):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


def _get_demo(provider: str, model: str) -> SqurveDemo:
    key = (provider, model)
    if key not in _demo_instances:
        with _demo_lock:
            if key not in _demo_instances:
                _demo_instances[key] = SqurveDemo(provider=provider, model_name=model)
    return _demo_instances[key]


def _database_records() -> list[dict]:
    records = []
    for db_id, db_path, schema_path in get_available_databases():
        tables = []
        try:
            schema_file = Path(schema_path)
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
            item = schema[0] if isinstance(schema, list) else schema
            if len(item.get("column_names_original", [])) != len(item.get("column_types", [])):
                item = sqlite_to_schema(db_path, db_id=db_id)
                schema_file.write_text(json.dumps([item], ensure_ascii=False, indent=2), encoding="utf-8")
            tables = item.get("table_names_original") or item.get("table_names") or []
        except (OSError, ValueError, TypeError):
            pass
        records.append({
            "id": db_id,
            "db_path": db_path,
            "schema_path": schema_path,
            "tables": tables,
            "size_bytes": Path(db_path).stat().st_size if Path(db_path).exists() else 0,
        })
    return records


def _find_database(db_id: str) -> dict | None:
    return next((item for item in _database_records() if item["id"] == db_id), None)


def _config_catalog() -> list[dict]:
    configs = []
    base = _project_root / "reproduce" / "configs"
    for path in sorted(base.glob("*/*.json")):
        if path.parent.name == "evolution" or path.name in {"database-registration.json", "few_shot_examples.json"}:
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        task_meta = config.get("task", {}).get("task_meta", [])
        stages = []
        for task in task_meta:
            meta = task.get("meta", {}).get("task", {})
            actor = next((value for key, value in meta.items() if key.endswith("_type")), None)
            stages.append({
                "id": task.get("task_id"),
                "type": task.get("task_type"),
                "actor": actor,
            })
        llm = config.get("llm", {})
        method = path.stem
        if "smoke" in method.lower() or "slice" in method.lower():
            continue
        data_source = str(config.get("dataset", {}).get("data_source", ""))
        source_parts = data_source.split(":")
        split = source_parts[1] if len(source_parts) == 3 else config.get("split", "unknown")
        configs.append({
            "dataset": path.parent.name,
            "method": method,
            "label": f"{method} / {path.parent.name}",
            "config_path": str(path.relative_to(_project_root)),
            "split": split,
            "scope": "smoke config" if "smoke" in method else "slice config" if "slice" in method else "canonical config",
            "provider": llm.get("use"),
            "model": llm.get("model_name"),
            "stages": stages,
            "exec_process": config.get("engine", {}).get("exec_process", []),
        })
    return configs


def _benchmark_catalog() -> list[dict]:
    path = _project_root / "config" / "sys_config.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8")).get("benchmark", [])
    except (OSError, ValueError, TypeError):
        return []
    catalog = []
    preferred_splits = ("dev", "valid", "val", "test", "train")
    # Only expose benchmarks that can support a local, labeled 100-row evaluation.
    hidden_benchmarks = {"ambidb", "spider2", "spider_dk", "SquRL"}
    for record in records:
        benchmark_id = str(record.get("id", "")).strip()
        if not benchmark_id or benchmark_id in hidden_benchmarks:
            continue
        splits = [str(item.get("sub_id")) for item in record.get("sub_data", []) if item.get("sub_id")]
        default_split = next((split for split in preferred_splits if split in splits), splits[0] if splits else "")
        catalog.append({
            "id": benchmark_id,
            "splits": splits,
            "default_split": default_split,
            "db_type": record.get("db_type"),
        })
    return catalog


def _router_config() -> dict:
    config_path = Path(get_router_config_path())
    if not config_path.is_absolute():
        config_path = _project_root / config_path
    return json.loads(config_path.read_text(encoding="utf-8"))


def _quote_env_value(value: str) -> str:
    if re.search(r'[\s#"\'\\]', value):
        return json.dumps(value)
    return value


def _upsert_dotenv(updates: dict[str, str]) -> None:
    env_path = _project_root / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    remaining = dict(updates)
    rewritten: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            rewritten.append(line)
            continue
        body = stripped[len("export "):].strip() if stripped.startswith("export ") else stripped
        key, _ = body.split("=", 1)
        key = key.strip()
        if key in remaining:
            rewritten.append(f"{key}={_quote_env_value(remaining.pop(key))}")
        else:
            rewritten.append(line)
    for key, value in remaining.items():
        rewritten.append(f"{key}={_quote_env_value(value)}")
    if rewritten and rewritten[-1] != "":
        rewritten.append("")
    env_path.write_text("\n".join(rewritten), encoding="utf-8")


def _clear_demo_instances() -> None:
    with _demo_lock:
        _demo_instances.clear()


def _apply_provider_config(provider: str, model: str, api_key: str | None = None, persist: bool = True) -> dict:
    if provider not in _provider_models:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    models = _provider_models[provider]
    if model not in models:
        raise ValueError(f"Unsupported model for {provider}: {model}")

    env_name = PROVIDER_ENV_VARS.get(provider)
    if not env_name:
        raise ValueError(f"No environment variable mapping for provider: {provider}")

    key = (api_key or "").strip() or None
    if key:
        os.environ[env_name] = key
        if persist:
            _upsert_dotenv({env_name: key})
        _clear_demo_instances()
    elif not resolve_api_key(provider, None):
        raise ValueError(
            f"{provider} api_key is missing; paste a key here or set {env_name} in repo-root .env"
        )

    _runtime_llm.update(provider=provider, model=model)
    _provider_validation.update(verified=False, error=None)
    return _provider_status()


def _provider_status() -> dict:
    load_dotenv(_project_root / ".env")
    config = _router_config()
    llm = dict(config.get("llm") or {})
    provider = _runtime_llm.get("provider") or llm.get("use")
    model = _runtime_llm.get("model") or llm.get("model_name")
    if provider:
        llm["use"] = provider
    if model:
        llm["model_name"] = model
    status_config = {**config, "llm": llm}
    configured, message = api_key_ready(status_config)
    return {
        "configured": configured,
        "verified": _provider_validation["verified"],
        "ready": configured and _provider_validation["error"] is None,
        "message": _provider_validation["error"] or message,
        "provider": provider,
        "model": model,
        "env_var": PROVIDER_ENV_VARS.get(provider or "", None),
    }


def _llm_provider_catalog() -> list[dict]:
    load_dotenv(_project_root / ".env")
    default = _provider_status()
    return [
        {
            "id": provider,
            "configured": bool(resolve_api_key(provider, None)),
            "models": models,
            "default_model": default["model"] if provider == default["provider"] and default["model"] in models else models[0],
            "env_var": PROVIDER_ENV_VARS[provider],
        }
        for provider, models in _provider_models.items()
    ]


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "provider": _provider_status()})


@app.post("/api/provider")
def update_provider():
    local_error = _local_request_error()
    if local_error:
        return local_error
    payload = request.get_json(silent=True) or {}
    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    api_key = payload.get("api_key")
    persist = bool(payload.get("persist", True))
    if not provider:
        return _json_error("provider is required")
    if not model:
        catalog = next((item for item in _llm_provider_catalog() if item["id"] == provider), None)
        model = (catalog or {}).get("default_model") or (_provider_models.get(provider) or [""])[0]
    if api_key is not None and not isinstance(api_key, str):
        return _json_error("api_key must be a string")
    try:
        status = _apply_provider_config(provider, model, api_key=api_key, persist=persist)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify({"status": "ok", "provider": status, "llm_providers": _llm_provider_catalog()})


@app.get("/api/capabilities")
def capabilities():
    return jsonify({
        "actors": ACTOR_BY_TYPE,
        "workflows": WORKFLOW_SKELETONS,
        "llm_providers": _llm_provider_catalog(),
        "benchmarks": _benchmark_catalog(),
        "reproduce_configs": _config_catalog(),
    })


@app.get("/api/terminals")
def terminal_catalog():
    local_error = _local_request_error()
    if local_error:
        return local_error
    enabled = agent_terminals_enabled()
    if not enabled:
        return jsonify({
            "enabled": False,
            "agents": [],
            "cwd": str(_project_root),
            "active_sessions": 0,
            "max_active": 0,
        })
    with _terminal_lock:
        active_by_agent = {
            agent: next((session.public_state() for session in _terminal_sessions.values() if session.agent == agent and session.running), None)
            for agent in _agent_commands
        }
    return jsonify({
        "enabled": True,
        "agents": [
            {
                "id": agent,
                "name": "Claude Code" if agent == "claude" else "Codex",
                "available": bool(command := shutil.which(executable)),
                "command": Path(command).name if command else None,
                "mode": "pty",
                "session": active_by_agent[agent],
            }
            for agent, executable in _agent_commands.items()
        ],
        "cwd": str(_project_root),
        "active_sessions": sum(bool(session) for session in active_by_agent.values()),
        "max_active": 2,
    })


@app.post("/api/terminals")
def start_terminal_session():
    access_error = _agent_terminal_access_error()
    if access_error:
        return access_error
    payload = request.get_json(silent=True) or {}
    agent = str(payload.get("agent", "")).strip().lower()
    if agent not in _agent_commands:
        return _json_error("Agent must be either codex or claude.")
    try:
        cols = int(payload.get("cols", 110))
        rows = int(payload.get("rows", 34))
    except (TypeError, ValueError):
        return _json_error("Terminal rows and columns must be integers.")
    command = shutil.which(_agent_commands[agent])
    if not command:
        return _json_error(f"{agent} executable was not found.", 503)
    with _terminal_lock:
        if any(session.agent == agent and session.running for session in _terminal_sessions.values()):
            return _json_error(f"A {agent} terminal is already running.", 409)
        if sum(session.running for session in _terminal_sessions.values()) >= 2:
            return _json_error("At most two agent terminals may be active at once.", 409)
        session = AgentPtySession(agent, command, cols=cols, rows=rows)
        _terminal_sessions[session.session_id] = session
    return jsonify(session.public_state()), 201


def _terminal_session(session_id: str) -> AgentPtySession | None:
    with _terminal_lock:
        return _terminal_sessions.get(session_id)


@app.get("/api/terminals/<session_id>/output")
def terminal_output(session_id: str):
    access_error = _agent_terminal_access_error()
    if access_error:
        return access_error
    session = _terminal_session(session_id)
    if not session:
        return _json_error("Agent terminal not found.", 404)
    try:
        cursor = max(0, int(request.args.get("cursor", 0)))
    except ValueError:
        return _json_error("Terminal output cursor must be an integer.")
    output, next_cursor = session.read(cursor)
    return jsonify({**session.public_state(), "output": output, "cursor": next_cursor})


@app.post("/api/terminals/<session_id>/input")
def terminal_input(session_id: str):
    access_error = _agent_terminal_access_error()
    if access_error:
        return access_error
    session = _terminal_session(session_id)
    if not session:
        return _json_error("Agent terminal not found.", 404)
    data = str((request.get_json(silent=True) or {}).get("data", ""))
    if not data or len(data) > 65536:
        return _json_error("Terminal input must contain between 1 and 65536 characters.")
    try:
        session.write(data)
    except RuntimeError as exc:
        return _json_error(str(exc), 409)
    return jsonify({"status": "accepted"})


@app.post("/api/terminals/<session_id>/resize")
def resize_terminal(session_id: str):
    access_error = _agent_terminal_access_error()
    if access_error:
        return access_error
    session = _terminal_session(session_id)
    if not session:
        return _json_error("Agent terminal not found.", 404)
    payload = request.get_json(silent=True) or {}
    try:
        session.resize(int(payload.get("cols")), int(payload.get("rows")))
    except (TypeError, ValueError):
        return _json_error("Terminal rows and columns must be integers.")
    return jsonify({"status": "resized"})


@app.post("/api/terminals/<session_id>/stop")
def stop_terminal_session(session_id: str):
    access_error = _agent_terminal_access_error()
    if access_error:
        return access_error
    session = _terminal_session(session_id)
    if not session:
        return _json_error("Agent terminal not found.", 404)
    session.stop()
    return jsonify(session.public_state())


@sock.route("/api/terminals/<session_id>/ws")
def terminal_websocket(ws, session_id: str):
    access_error = _agent_terminal_access_error()
    if access_error:
        ws.close()
        return
    session = _terminal_session(session_id)
    if not session:
        ws.close()
        return

    closed = threading.Event()

    def receive_input():
        while not closed.is_set() and session.running:
            try:
                raw = ws.receive(timeout=1)
            except TimeoutError:
                continue
            except Exception:
                break
            if raw is None:
                continue
            try:
                message = json.loads(raw)
                if message.get("type") == "input":
                    data = str(message.get("data", ""))
                    if 0 < len(data) <= 65536:
                        session.write(data)
                elif message.get("type") == "resize":
                    session.resize(int(message.get("cols")), int(message.get("rows")))
            except (ValueError, TypeError, RuntimeError):
                continue
        closed.set()

    receiver = threading.Thread(target=receive_input, daemon=True)
    receiver.start()
    cursor = 0
    try:
        ws.send(json.dumps({"type": "ready", **session.public_state()}))
        while not closed.is_set():
            output, cursor = session.wait_read(cursor)
            if output:
                ws.send(json.dumps({"type": "output", "data": output, "cursor": cursor}))
            if not session.running:
                ws.send(json.dumps({"type": "exit", **session.public_state()}))
                break
    except Exception:
        pass
    finally:
        closed.set()


@app.get("/api/databases")
def databases():
    return jsonify({"databases": _database_records()})


@app.post("/api/databases/upload")
def upload_database():
    files = request.files.getlist("files")
    if not files:
        return _json_error("Select at least one .sqlite, .db, .csv, .xlsx, or .xls file.")

    allowed = {".sqlite", ".db", ".csv", ".xlsx", ".xls"}
    with tempfile.TemporaryDirectory(prefix="squrve-upload-") as temp_dir:
        paths = []
        used_names = set()
        for index, storage in enumerate(files):
            suffix = Path(storage.filename or "").suffix.lower()
            if suffix not in allowed:
                return _json_error(f"Unsupported file type: {suffix or 'unknown'}")
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(storage.filename).name)
            if safe_name in used_names:
                safe_name = f"{index:02d}-{safe_name}"
            used_names.add(safe_name)
            path = Path(temp_dir) / safe_name
            storage.save(path)
            paths.append(path)
        result = process_uploaded_files(paths, get_uploaded_db_root())
    return jsonify({"status": "success", "database": _find_database(result["db_id"])})


@app.post("/api/query")
def query():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    db_id = str(payload.get("db_id", "")).strip()
    database = _find_database(db_id)
    if not question:
        return _json_error("Question is required.")
    if not database:
        return _json_error("Select an uploaded database.")

    mode = payload.get("mode", "direct")
    actors = payload.get("actors") or []
    generator = payload.get("generator") or "DINSQLGenerator"
    provider = str(payload.get("provider") or _provider_status()["provider"])
    provider_config = next((item for item in _llm_provider_catalog() if item["id"] == provider), None)
    if not provider_config:
        return _json_error(f"Unsupported LLM provider: {provider}")
    model = str(payload.get("model") or provider_config["default_model"])
    if model not in provider_config["models"]:
        return _json_error(f"Unsupported model for {provider}: {model}")
    if not provider_config["configured"]:
        return _json_error(f"Provider {provider} is not configured in the local .env.")
    result = _get_demo(provider, model).generate_sql(
        question=question,
        db_id=db_id,
        schema_path=database["schema_path"],
        db_path=database["db_path"],
        use_workflow=mode == "workflow" and bool(actors),
        workflow_actor_lis=actors,
        generate_type=generator,
    )
    if result.get("status") == "success":
        _provider_validation.update(verified=True, error=None)
        result["run_config"] = {
            "database": db_id,
            "llm": {"provider": provider, "model": model},
            "actors": actors if mode == "workflow" else [generator],
        }
    else:
        message = str(result.get("message", ""))
        if "invalid_api_key" in message or "Incorrect API key" in message or "401" in message:
            _provider_validation.update(
                verified=False,
                error=f"The configured {provider} API key was rejected.",
            )
    status = 200 if result.get("status") == "success" else 422
    return jsonify(result), status


def _validate_readonly_sql(sql: str):
    try:
        statements = parse(sql, read="sqlite")
    except Exception as exc:
        raise ValueError(f"SQL parse failed: {exc}") from exc
    if len(statements) != 1:
        raise ValueError("Only one SQL statement can be executed at a time.")
    statement = statements[0]
    blocked = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)
    if isinstance(statement, blocked) or any(statement.find(kind) for kind in blocked):
        raise ValueError("The demo executes read-only SELECT queries only.")
    if not statement.find(exp.Select) and not isinstance(statement, exp.Select):
        raise ValueError("The demo executes read-only SELECT queries only.")


@app.post("/api/execute")
def execute():
    payload = request.get_json(silent=True) or {}
    db_id = str(payload.get("db_id", "")).strip()
    sql = str(payload.get("sql", "")).strip()
    database = _find_database(db_id)
    if not database:
        return _json_error("Select an uploaded database.")
    if not sql:
        return _json_error("SQL is required.")
    try:
        _validate_readonly_sql(sql)
    except ValueError as exc:
        return _json_error(str(exc))

    started = time.monotonic()
    deadline = started + 5.0
    uri = f"file:{quote(str(Path(database['db_path']).resolve()))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    try:
        cursor = connection.execute(sql)
        columns = [item[0] for item in cursor.description or []]
        rows = cursor.fetchmany(501)
    except sqlite3.Error as exc:
        return _json_error(f"Execution failed: {exc}", 422)
    finally:
        connection.close()
    truncated = len(rows) > 500
    rows = rows[:500]
    return jsonify({
        "status": "success",
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
    })


def _summarize_scores(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    aggregate = data.get("aggregate", {})
    metrics = {}
    for name in ("ex", "em", "sf1", "sc", "ves", "rves"):
        value = aggregate.get(name)
        if isinstance(value, dict):
            metrics[name] = value.get("avg")
    stages = []
    for stage_name, stage in data.get("stage_metrics", {}).items():
        stages.append({
            "name": stage_name,
            "task_type": stage.get("task_type"),
            "metrics": stage.get("metrics", {}),
        })
    component_f1 = {}
    for name, value in (aggregate.get("cf1") or {}).items():
        if isinstance(value, dict):
            component_f1[name.removeprefix("cf1_")] = value.get("avg")
    error_roots = []
    for name, value in (aggregate.get("error_root_distribution") or {}).items():
        if isinstance(value, dict):
            error_roots.append({
                "name": name,
                "count": value.get("count"),
                "rate": value.get("pct"),
            })
    error_roots.sort(key=lambda item: item.get("count") or 0, reverse=True)
    token = aggregate.get("token") or {}
    return {
        "run_id": data.get("run_id") or path.parent.name,
        "method": data.get("method"),
        "dataset": data.get("dataset"),
        "split": data.get("split"),
        "scope": data.get("scope"),
        "sample_count": data.get("sample_count"),
        "timestamp": data.get("timestamp"),
        "metrics": metrics,
        "component_f1": component_f1,
        "error_roots": error_roots[:6],
        "token": {
            "total_calls": token.get("total_calls"),
            "total_tokens": token.get("total_tokens"),
            "avg_per_sample": token.get("avg_per_sample"),
        },
        "stages": stages,
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    values = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 4)


def _sampling_metadata(scores: dict, job: dict | None = None) -> dict:
    job = job or {}
    config_snapshot = scores.get("config_snapshot") or {}
    snapshot_sampling = config_snapshot.get("sampling") or {}
    data_source = str(config_snapshot.get("data_source") or "")
    random_match = re.search(r"(?:^|[.:])random-(\d+)(?:\.|$)", data_source)
    seed_match = re.search(r"(?:^|[.:])seed-(\d+)(?:\.|$)", data_source)
    mode = job.get("sample_mode") or snapshot_sampling.get("mode")
    limit = job.get("sample_limit") or snapshot_sampling.get("limit")
    seed = job.get("sample_seed")
    if seed is None:
        seed = snapshot_sampling.get("seed")
    if random_match:
        mode = "random"
        limit = int(random_match.group(1))
        seed = int(seed_match.group(1)) if seed_match else seed
    elif not mode:
        scope_match = re.fullmatch(r"(random|slice)-(\d+)", str(scores.get("scope") or ""))
        if scope_match:
            mode = scope_match.group(1)
            limit = int(scope_match.group(2))
    return {
        "mode": mode,
        "limit": limit or scores.get("sample_count"),
        "seed": seed,
    }


def _latency_summary(scores: dict, job: dict | None = None) -> dict:
    per_sample = scores.get("per_sample") or []
    sample_values = [
        row.get("act_elapsed_s") for row in per_sample
        if isinstance(row.get("act_elapsed_s"), (int, float))
    ]
    stage_values: dict[str, list[float]] = {}
    workflow_rows = ((scores.get("workflow_trace") or {}).get("per_sample") or [])
    for row in workflow_rows:
        for stage_id, stage in (row.get("stages") or {}).items():
            elapsed = ((stage.get("runtime") or {}).get("elapsed_s"))
            if isinstance(elapsed, (int, float)):
                stage_values.setdefault(stage_id, []).append(float(elapsed))
    by_stage = {
        stage_id: {
            "sample_count": len(values),
            "mean_s": round(sum(values) / len(values), 4),
            "p95_s": _percentile(values, .95),
        }
        for stage_id, values in stage_values.items() if values
    }
    wall_time = None
    if job and isinstance(job.get("started_at"), (int, float)) and isinstance(job.get("finished_at"), (int, float)):
        wall_time = round(job["finished_at"] - job["started_at"], 4)
    return {
        "sample_count": len(sample_values),
        "mean_s": round(sum(sample_values) / len(sample_values), 4) if sample_values else None,
        "p50_s": _percentile(sample_values, .5),
        "p95_s": _percentile(sample_values, .95),
        "wall_time_s": wall_time,
        "by_stage": by_stage,
    }


def _serialize_comparison_run(scores: dict, job: dict | None = None, source: str = "artifact") -> dict:
    sample_ids = [
        str(row.get("instance_id")) for row in (scores.get("per_sample") or [])
        if row.get("instance_id") is not None
    ]
    sample_hash = hashlib.sha256("\n".join(sample_ids).encode("utf-8")).hexdigest()[:16]
    aggregate = scores.get("aggregate") or {}
    workflow = scores.get("workflow_trace") or {}
    return {
        "run_id": scores.get("run_id"),
        "method": scores.get("method"),
        "dataset": scores.get("dataset"),
        "split": scores.get("split"),
        "scope": scores.get("scope"),
        "sample_count": scores.get("sample_count"),
        "timestamp": scores.get("timestamp"),
        "source": source,
        "sampling": _sampling_metadata(scores, job),
        "sample_hash": sample_hash,
        "aggregate": aggregate,
        "stage_metrics": scores.get("stage_metrics") or {},
        "workflow": {
            "workflows": workflow.get("workflows") or [],
            "aggregate": workflow.get("aggregate") or {},
        },
        "by_sql_feature": scores.get("by_sql_feature") or {},
        "by_scenario": scores.get("by_scenario") or {},
        "qvt": scores.get("qvt") or {},
        "token": aggregate.get("token") or {},
        "errors": aggregate.get("error_root_distribution") or {},
        "latency": _latency_summary(scores, job),
    }


def _comparison_payload(runs: list[dict], expected_methods: list[str], comparison_id: str | None = None) -> dict:
    runs.sort(key=lambda item: expected_methods.index(item["method"]) if item["method"] in expected_methods else len(expected_methods))
    hashes = {run.get("sample_hash") for run in runs if run.get("sample_hash")}
    counts = {run.get("sample_count") for run in runs if run.get("sample_count") is not None}
    sampling_keys = {
        (run.get("dataset"), run.get("split"), run.get("scope"), *(run.get("sampling") or {}).values())
        for run in runs
    }
    complete = bool(expected_methods) and {run.get("method") for run in runs} >= set(expected_methods)
    aligned = complete and len(hashes) == 1 and len(counts) == 1 and len(sampling_keys) == 1
    sampling = runs[0].get("sampling") if runs else {}
    return {
        "comparison_id": comparison_id,
        "expected_methods": expected_methods,
        "missing_methods": [method for method in expected_methods if method not in {run.get("method") for run in runs}],
        "sampling": {
            "dataset": runs[0].get("dataset") if runs else None,
            "split": runs[0].get("split") if runs else None,
            **(sampling or {}),
        },
        "sample_alignment": {
            "aligned": aligned,
            "complete": complete,
            "sample_count": next(iter(counts)) if len(counts) == 1 else None,
            "hash": next(iter(hashes)) if aligned else None,
        },
        "runs": runs,
    }


def _read_scores(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _artifact_comparison(
        dataset: str,
        methods: list[str],
        split: str,
        sample_mode: str,
        sample_limit: int,
        sample_seed: int,
) -> dict:
    candidates = []
    for path in (_project_root / "artifacts").glob(f"{dataset}-*/scores.json"):
        scores = _read_scores(path)
        if not scores or scores.get("dataset") != dataset or scores.get("method") not in methods:
            continue
        if (scores.get("config_snapshot") or {}).get("generate_num") != 1:
            continue
        sampling = _sampling_metadata(scores)
        if scores.get("split") != split:
            continue
        if sampling.get("mode") != sample_mode or sampling.get("limit") != sample_limit:
            continue
        if sample_mode == "random" and sampling.get("seed") != sample_seed:
            continue
        candidates.append(_serialize_comparison_run(scores))

    groups: dict[tuple, list[dict]] = {}
    for run in candidates:
        sampling = run.get("sampling") or {}
        signature = (
            run.get("dataset"), run.get("split"), run.get("scope"), sampling.get("mode"), sampling.get("limit"),
            sampling.get("seed"), run.get("sample_hash"),
        )
        existing = groups.setdefault(signature, [])
        previous = next((item for item in existing if item.get("method") == run.get("method")), None)
        if previous is None:
            existing.append(run)
        elif str(run.get("timestamp") or "") > str(previous.get("timestamp") or ""):
            existing[existing.index(previous)] = run
    selected = max(
        groups.values(),
        key=lambda group: (len({run.get("method") for run in group}), max(str(run.get("timestamp") or "") for run in group)),
        default=[],
    )
    return _comparison_payload(selected, methods)


def _public_job(job: dict) -> dict:
    return {key: value for key, value in job.items() if key not in {"scores_path"}}


@app.get("/api/session")
def session_state():
    with _jobs_lock:
        jobs = [_public_job(dict(job)) for job in _jobs.values()]
    jobs.sort(key=lambda item: item.get("started_at", 0), reverse=True)
    return jsonify({"jobs": jobs})


def _monitor_job(job_id: str, process: subprocess.Popen, log_handle, scores_path: Path):
    return_code = process.wait()
    log_handle.close()
    with _jobs_lock:
        job = _jobs[job_id]
        if job.get("status") != "cancelled":
            job["status"] = "completed" if return_code == 0 and scores_path.exists() else "failed"
        job["return_code"] = return_code
        job["finished_at"] = time.time()
        if scores_path.exists():
            job["scores_path"] = str(scores_path)
            job["result"] = _summarize_scores(scores_path)
            job["run_id"] = job["result"].get("run_id")
        _processes.pop(job_id, None)


def _launch_evaluation(
        dataset: str,
        method: str,
        comparison_id: str | None = None,
        sample_limit: int = 100,
        sample_mode: str = "slice",
        sample_seed: int = 42,
) -> dict:
    config = next((item for item in _config_catalog() if item["dataset"] == dataset and item["method"] == method), None)
    if not config:
        raise ValueError(f"Unknown reproduce configuration: {method} / {dataset}")

    job_id = uuid.uuid4().hex[:10]
    job_dir = _run_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_dir / "run.log"
    score_dir = job_dir / "score-bundle"
    scores_path = score_dir / "scores.json"
    python = _project_root / ".venv" / "bin" / "python"
    executable = str(python if python.exists() else Path(sys.executable))
    log_handle = log_path.open("w", encoding="utf-8")
    child_env = os.environ.copy()
    child_env["SQURVE_EVAL_OUTPUT_DIR"] = str(score_dir)
    child_env["SQURVE_EVAL_RUN_ID"] = f"{dataset}-{method}-{job_id}"
    child_env["SQURVE_EVAL_SAMPLE_LIMIT"] = str(sample_limit)
    child_env["SQURVE_EVAL_SAMPLE_MODE"] = sample_mode
    child_env["SQURVE_EVAL_SAMPLE_SEED"] = str(sample_seed)
    child_env["SQURVE_EVAL_SCOPE"] = "smoke"
    process = subprocess.Popen(
        [executable, "reproduce/run.py", dataset, method],
        cwd=_project_root,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=child_env,
        text=True,
    )
    job = {
        "job_id": job_id,
        "dataset": dataset,
        "method": method,
        "config": config,
        "comparison_id": comparison_id,
        "sample_limit": sample_limit,
        "sample_mode": sample_mode,
        "sample_seed": sample_seed,
        "status": "running",
        "pid": process.pid,
        "log_path": str(log_path.relative_to(_project_root)),
        "started_at": time.time(),
        "run_id": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job
        _processes[job_id] = process
    threading.Thread(target=_monitor_job, args=(job_id, process, log_handle, scores_path), daemon=True).start()
    return _public_job(job)


@app.post("/api/evaluations")
def start_evaluation():
    payload = request.get_json(silent=True) or {}
    validation = _sampling_request(payload)
    if len(validation) == 2:
        return validation
    sample_limit, sample_mode, sample_seed = validation
    try:
        job = _launch_evaluation(
            str(payload.get("dataset", "")),
            str(payload.get("method", "")),
            str(payload.get("comparison_id")) if payload.get("comparison_id") else None,
            sample_limit,
            sample_mode,
            sample_seed,
        )
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(job), 202


@app.post("/api/comparisons")
def start_comparison():
    payload = request.get_json(silent=True) or {}
    pairs = payload.get("pairs") or []
    validation = _sampling_request(payload)
    if len(validation) == 2:
        return validation
    sample_limit, sample_mode, sample_seed = validation

    if not isinstance(pairs, list) or not 2 <= len(pairs) <= 6:
        return _json_error("Select between 2 and 6 method-benchmark pairs.")
    normalized = []
    seen = set()
    catalog = {(item["dataset"], item["method"]) for item in _config_catalog()}
    for pair in pairs:
        key = (str(pair.get("dataset", "")), str(pair.get("method", "")))
        if key not in catalog:
            return _json_error(f"Unknown reproduce configuration: {key[1]} / {key[0]}")
        if key not in seen:
            normalized.append(key)
            seen.add(key)
    if len(normalized) < 2:
        return _json_error("A comparison requires at least two distinct configurations.")
    comparison_id = uuid.uuid4().hex[:8]
    jobs = [
        _launch_evaluation(dataset, method, comparison_id, sample_limit, sample_mode, sample_seed)
        for dataset, method in normalized
    ]
    return jsonify({"comparison_id": comparison_id, "jobs": jobs}), 202


@app.get("/api/comparisons/<comparison_id>/results")
def comparison_results(comparison_id: str):
    with _jobs_lock:
        jobs = [dict(job) for job in _jobs.values() if job.get("comparison_id") == comparison_id]
    if not jobs:
        return _json_error("Comparison not found in the current session.", 404)
    expected_methods = list(dict.fromkeys(job.get("method") for job in jobs if job.get("method")))
    runs = []
    for job in jobs:
        scores_path = Path(job.get("scores_path") or "")
        if job.get("status") != "completed" or not scores_path.is_file():
            continue
        scores = _read_scores(scores_path)
        if scores:
            runs.append(_serialize_comparison_run(scores, job=job, source="session"))
    payload = _comparison_payload(runs, expected_methods, comparison_id=comparison_id)
    payload["statuses"] = {job.get("method"): job.get("status") for job in jobs if job.get("method")}
    return jsonify(payload)


@app.get("/api/comparisons/latest/results")
def latest_comparison_results():
    dataset = str(request.args.get("dataset", "spider")).strip()
    split = str(request.args.get("split", "dev")).strip()
    methods = [item.strip() for item in str(request.args.get("methods", "c3sql")).split(",") if item.strip()]
    sample_mode = str(request.args.get("sample_mode", "random")).strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset) or not re.fullmatch(r"[A-Za-z0-9_-]+", split):
        return _json_error("Dataset and split must be simple identifiers.")
    if not methods or len(methods) > 6 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", method) for method in methods):
        return _json_error("Methods must contain between one and six simple identifiers.")
    if sample_mode not in {"slice", "random"}:
        return _json_error("Sample mode must be slice or random.")
    try:
        sample_limit = int(request.args.get("sample_limit", 100))
        sample_seed = int(request.args.get("sample_seed", 42))
    except (TypeError, ValueError):
        return _json_error("Sample limit and seed must be integers.")
    if sample_limit not in _sample_limits:
        return _json_error("Sample limit must be 3, 10, 20, 50, 100, or 200.")
    return jsonify(_artifact_comparison(dataset, list(dict.fromkeys(methods)), split, sample_mode, sample_limit, sample_seed))


def _sampling_request(payload: dict):
    sample_limit = payload["sample_limit"] if "sample_limit" in payload else 100
    sample_mode = str(payload.get("sample_mode", "slice")).lower()
    if sample_mode not in {"slice", "random"}:
        return _json_error("Sample mode must be slice or random.")
    try:
        sample_seed = int(payload.get("sample_seed", 42))
    except (TypeError, ValueError):
        return _json_error("Sample seed must be an integer.")
    try:
        sample_limit = int(sample_limit)
    except (TypeError, ValueError):
        return _json_error("Sample limit must be an integer.")
    if sample_limit not in _sample_limits:
        return _json_error("Sample limit must be 3, 10, 20, 50, 100, or 200.")
    return sample_limit, sample_mode, sample_seed


@app.get("/api/evaluations/<job_id>")
def evaluation_detail(job_id: str):
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        return _json_error("Job not found.", 404)
    log_path = _project_root / job["log_path"]
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    job["log"] = log_text[-20000:]
    return jsonify(_public_job(job))


@app.post("/api/evaluations/<job_id>/cancel")
def cancel_evaluation(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        process = _processes.get(job_id)
        if not job:
            return _json_error("Evaluation not found.", 404)
        if job.get("status") != "running" or process is None:
            return _json_error("Only a running evaluation can be cancelled.", 409)
        job["status"] = "cancelled"
        job["finished_at"] = time.time()
        process.terminate()
        return jsonify(_public_job(dict(job)))


@app.post("/api/evaluations/<job_id>/profile")
def profile_evaluation(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return _json_error("Evaluation not found.", 404)
        scores_path = Path(job.get("scores_path", ""))
        if job.get("status") != "completed" or not scores_path.exists():
            return _json_error("A completed score bundle from this session is required.", 409)
    scores = json.loads(scores_path.read_text(encoding="utf-8"))
    profile = build_weakness_json(scores, top_n=5)
    profile_path = scores_path.parent.parent / "weakness-profile.json"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    with _jobs_lock:
        _jobs[job_id]["weakness_profile"] = profile
    return jsonify({
        "job_id": job_id,
        "status": "profiled",
        "profile": profile,
        "next_gate": "candidate_plan_review",
        "allowed_scope": ["actor", "prompt", "config", "task_method_branch"],
    })


_ARCHIVE_TEXT_SUFFIXES = {".json", ".md", ".txt", ".jsonl", ".log"}
_ARCHIVE_MAX_BYTES = 2_000_000


def _archive_roots() -> list[tuple[str, Path]]:
    return [
        ("evidence", _project_root / "evidence" / "reported-results"),
        ("artifacts", _project_root / "artifacts"),
        ("demo-runs", _project_root / "tmp" / "demo-runs"),
    ]


def _safe_archive_run_id(run_id: str) -> str | None:
    value = str(run_id or "").strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9._-]+", value) or ".." in value:
        return None
    return value


def _archive_run_dirs() -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    evidence_root = _project_root / "evidence" / "reported-results"
    if evidence_root.is_dir():
        for path in sorted(evidence_root.iterdir()):
            if not path.is_dir():
                continue
            try:
                verify_bundle(path)
            except EvidenceError:
                continue
            found.append(("evidence", path))
    artifacts_root = _project_root / "artifacts"
    if artifacts_root.is_dir():
        for path in sorted(artifacts_root.iterdir()):
            if path.is_dir() and (path / "scores.json").is_file():
                found.append(("artifacts", path))
    demo_root = _project_root / "tmp" / "demo-runs"
    if demo_root.is_dir():
        for job_dir in sorted(demo_root.iterdir()):
            bundle = job_dir / "score-bundle"
            if bundle.is_dir() and (bundle / "scores.json").is_file():
                found.append(("demo-runs", bundle))
    return found


def _archive_metric_avg(aggregate: dict, name: str):
    value = (aggregate or {}).get(name)
    if isinstance(value, dict):
        return value.get("avg")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _archive_entry(source: str, run_dir: Path) -> dict | None:
    scores_path = run_dir / "scores.json"
    if not scores_path.is_file():
        return None
    try:
        scores = json.loads(scores_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    run_id = str(scores.get("run_id") or run_dir.name)
    if source == "demo-runs":
        run_id = str(scores.get("run_id") or f"demo-{run_dir.parent.name}")
    aggregate = scores.get("aggregate") or {}
    token = aggregate.get("token") or {}
    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if path.suffix.lower() not in _ARCHIVE_TEXT_SUFFIXES:
            continue
        if any(part.startswith(".") for part in path.relative_to(run_dir).parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        files.append({
            "path": rel,
            "name": path.name,
            "suffix": path.suffix.lower(),
            "size_bytes": size,
            "kind": (
                "markdown" if path.suffix.lower() == ".md"
                else "json" if path.suffix.lower() in {".json", ".jsonl"}
                else "text"
            ),
        })
    sampling = _sampling_metadata(scores)
    return {
        "run_id": run_id,
        "dir_name": run_dir.name if source in {"artifacts", "evidence"} else run_dir.parent.name,
        "source": source,
        "dataset": scores.get("dataset"),
        "method": scores.get("method"),
        "split": scores.get("split"),
        "scope": scores.get("scope"),
        "sample_count": scores.get("sample_count"),
        "timestamp": scores.get("timestamp"),
        "sampling": sampling,
        "metrics": {
            name: _archive_metric_avg(aggregate, name)
            for name in ("ex", "em", "sf1", "sc", "ves", "rves")
        },
        "token": {
            "total_tokens": token.get("total_tokens"),
            "avg_per_sample": token.get("avg_per_sample"),
            "total_calls": token.get("total_calls"),
        },
        "files": files,
        "file_count": len(files),
        "has_scores": True,
        "has_report": any(item["name"] == "detailed-report.txt" for item in files),
        "has_markdown": any(item["kind"] == "markdown" for item in files),
    }


def _resolve_archive_run(run_id: str) -> tuple[str, Path] | None:
    safe = _safe_archive_run_id(run_id)
    if not safe:
        return None
    for source, run_dir in _archive_run_dirs():
        entry = _archive_entry(source, run_dir)
        if not entry:
            continue
        if entry["run_id"] == safe or entry["dir_name"] == safe:
            return source, run_dir
    return None


def _resolve_archive_file(run_dir: Path, relative: str) -> tuple[Path, Path] | None:
    rel = str(relative or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    root = run_dir.resolve()
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file() or path.suffix.lower() not in _ARCHIVE_TEXT_SUFFIXES:
        return None
    return root, path


@app.get("/api/archive")
def archive_catalog():
    query = str(request.args.get("q", "")).strip().lower()
    dataset = str(request.args.get("dataset", "")).strip().lower()
    method = str(request.args.get("method", "")).strip().lower()
    source_filter = str(request.args.get("source", "")).strip().lower()
    runs = []
    for source, run_dir in _archive_run_dirs():
        if source_filter and source != source_filter:
            continue
        entry = _archive_entry(source, run_dir)
        if not entry:
            continue
        haystack = " ".join([
            entry["run_id"],
            entry.get("dir_name") or "",
            str(entry.get("dataset") or ""),
            str(entry.get("method") or ""),
            str(entry.get("scope") or ""),
            " ".join(item["name"] for item in entry["files"]),
        ]).lower()
        if dataset and str(entry.get("dataset") or "").lower() != dataset:
            continue
        if method and str(entry.get("method") or "").lower() != method:
            continue
        if query and query not in haystack:
            continue
        runs.append(entry)
    runs.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    datasets = sorted({item.get("dataset") for item in runs if item.get("dataset")})
    methods = sorted({item.get("method") for item in runs if item.get("method")})
    return jsonify({
        "runs": runs,
        "total": len(runs),
        "filters": {
            "datasets": datasets,
            "methods": methods,
            "sources": ["evidence", "artifacts", "demo-runs"],
        },
    })


@app.get("/api/archive/<run_id>")
def archive_detail(run_id: str):
    resolved = _resolve_archive_run(run_id)
    if not resolved:
        return _json_error("Archive run not found.", 404)
    source, run_dir = resolved
    entry = _archive_entry(source, run_dir)
    if not entry:
        return _json_error("Archive run is unreadable.", 404)
    return jsonify(entry)


@app.get("/api/archive/<run_id>/files/<path:file_path>")
def archive_file(run_id: str, file_path: str):
    resolved = _resolve_archive_run(run_id)
    if not resolved:
        return _json_error("Archive run not found.", 404)
    _, run_dir = resolved
    resolved_file = _resolve_archive_file(run_dir, file_path)
    if not resolved_file:
        return _json_error("Archive file not found or not readable.", 404)
    root, path = resolved_file
    size = path.stat().st_size
    truncated = size > _ARCHIVE_MAX_BYTES
    raw = path.read_bytes()[:_ARCHIVE_MAX_BYTES]
    text = raw.decode("utf-8", errors="replace")
    payload = {
        "run_id": run_id,
        "path": path.relative_to(root).as_posix(),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "size_bytes": size,
        "truncated": truncated,
        "kind": (
            "markdown" if path.suffix.lower() == ".md"
            else "json" if path.suffix.lower() in {".json", ".jsonl"}
            else "text"
        ),
        "content": text,
    }
    if path.suffix.lower() == ".json":
        try:
            payload["json"] = json.loads(text)
        except json.JSONDecodeError:
            payload["json"] = None
    return jsonify(payload)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=7861, type=int)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
