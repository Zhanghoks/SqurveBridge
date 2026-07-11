"""Process artifact helpers for Meta-Evo runs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def init_process_artifacts(evolve_dir: str | Path) -> None:
    evolve_dir = Path(evolve_dir)
    events_path = evolve_dir / "process-events.jsonl"
    if not events_path.exists():
        events_path.write_text("", encoding="utf-8")
    manifest_path = evolve_dir / "artifact-manifest.json"
    if not manifest_path.exists():
        write_json(manifest_path, {
            "version": 1,
            "evolve_slug": evolve_dir.name,
            "artifacts": {},
        })
    render_progress(evolve_dir)


def create_attempt_dir(evolve_dir: str | Path, node_id: str, stage: str) -> Path:
    attempts_root = Path(evolve_dir) / "nodes" / node_id / "attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    existing = sorted(attempts_root.glob(f"{stage}-*"))
    attempt_dir = attempts_root / f"{stage}-{len(existing) + 1:03d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    return attempt_dir


def append_process_event(evolve_dir: str | Path, event: dict[str, Any]) -> Path:
    evolve_dir = Path(evolve_dir)
    event = {
        "event_id": event.get("event_id") or _event_id(event),
        "type": event.get("type", "event"),
        "status": event.get("status", "completed"),
        "at": event.get("at") or now_iso(),
        **event,
    }
    path = evolve_dir / "process-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def update_artifact_manifest(
        evolve_dir: str | Path,
        artifact_refs: list[str | Path],
        *,
        kind: str,
        phase: str,
        round: int = 0,
        producer: str,
        consumes: list[str] | None = None,
        node_id: str | None = None,
) -> Path:
    evolve_dir = Path(evolve_dir)
    manifest_path = evolve_dir / "artifact-manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {
        "version": 1,
        "evolve_slug": evolve_dir.name,
        "artifacts": {},
    }
    artifacts = manifest.setdefault("artifacts", {})
    for ref in artifact_refs:
        path = Path(ref)
        full_path = path if path.is_absolute() else evolve_dir / path
        if not full_path.exists():
            continue
        rel = _relative_artifact(evolve_dir, full_path)
        artifacts[rel] = {
            "kind": kind,
            "phase": phase,
            "round": round,
            "node_id": node_id,
            "producer": producer,
            "consumes": consumes or [],
            "sha256": f"sha256:{sha256_file(full_path)}",
            "created_at": now_iso(),
        }
    return write_json(manifest_path, manifest)


def render_progress(evolve_dir: str | Path) -> Path:
    evolve_dir = Path(evolve_dir)
    state = read_json(evolve_dir / "evolve-state.json") if (evolve_dir / "evolve-state.json").exists() else {}
    events = _tail_events(evolve_dir / "process-events.jsonl", limit=8)
    lines = [
        f"# Evolution Progress: {evolve_dir.name}",
        "",
        f"- Phase: {state.get('phase', 'unknown')}",
        f"- Round: {state.get('round', 0)}",
        f"- Active stage: {state.get('active_stage') or '-'}",
        f"- Current node: {state.get('current_node') or '-'}",
        f"- Human gate: {state.get('human_gate') or '-'}",
        f"- Failure: {state.get('failure') or '-'}",
        "",
        "## Recent Events",
    ]
    if events:
        for event in events:
            lines.append(
                f"- {event.get('at', '-')} `{event.get('type', 'event')}` "
                f"{event.get('phase', '-')} {event.get('status', '-')}"
            )
    else:
        lines.append("- No events recorded yet.")
    path = evolve_dir / "progress.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: str | Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail_events(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _relative_artifact(evolve_dir: Path, full_path: Path) -> str:
    try:
        return str(full_path.resolve().relative_to(evolve_dir.resolve()))
    except ValueError:
        return str(full_path)


def _event_id(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("round", 0)),
        str(event.get("phase", "phase")),
        str(event.get("type", "event")),
        str(event.get("node_id", "run")),
        now_iso(),
    ]
    return ":".join(parts)
