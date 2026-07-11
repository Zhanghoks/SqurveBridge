"""Markdown experience memory helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def append_success(memory_path: str | Path, *, title: str, body: str) -> Path:
    return _append(memory_path, "Successful Patterns", title=title, body=body)


def append_failed_pattern(memory_path: str | Path, *, title: str, body: str) -> Path:
    return _append(memory_path, "Failed Patterns", title=title, body=body)


def _append(memory_path: str | Path, section: str, *, title: str, body: str) -> Path:
    path = Path(memory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Evolution Memory\n\n"
    entry = f"\n## {section}\n### {title}\n- Date: {date.today().isoformat()}\n{body.rstrip()}\n"
    path.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")
    return path
