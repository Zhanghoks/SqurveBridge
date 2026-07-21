"""Persistence helpers for scores and token artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from reproduce.lib.env_config import redact_config_secrets
from reproduce.metrics.profile import build_weakness_profile
from reproduce.metrics.eval_store import persist_eval_store


def persist_scores_bundle(
        *,
        output_dir: str | Path,
        scores: dict[str, Any],
        token_data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        eval_store_path: str | Path | None = None,
) -> Dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    token_data = token_data or {}

    scores_path = output_dir / "scores.json"
    scores_path.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")

    weakness_path = output_dir / "weakness_profile.md"
    weakness_path.write_text(build_weakness_profile(scores), encoding="utf-8")

    paths = {"scores": scores_path, "weakness_profile": weakness_path}

    # Persist a redacted config copy — never write resolved API keys to disk.
    if config:
        config_copy_path = output_dir / "config.json"
        config_copy_path.write_text(
            json.dumps(redact_config_secrets(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths["config"] = config_copy_path

    if token_data:
        usage_path = output_dir / "token-usage.jsonl"
        with usage_path.open("w", encoding="utf-8") as f:
            for record in token_data.get("records") or []:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        summary_path = output_dir / "token-summary.json"
        summary_path.write_text(
            json.dumps({k: v for k, v in token_data.items() if k != "records"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths["token_usage"] = usage_path
        paths["token_summary"] = summary_path
    store_path = Path(eval_store_path) if eval_store_path is not None else output_dir.parent / "eval-store.sqlite"
    paths["eval_store"] = persist_eval_store(scores, store_path)
    return paths
