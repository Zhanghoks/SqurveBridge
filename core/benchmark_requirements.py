"""Fail-loud helpers for benchmark assets required by the Squrve runtime."""

from __future__ import annotations

from pathlib import Path


def require_benchmark_file(path: str | Path, benchmark_id: str, kind: str) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(_install_message(candidate, benchmark_id, kind))
    return candidate


def require_benchmark_directory(path: str | Path, benchmark_id: str, kind: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        raise FileNotFoundError(_install_message(candidate, benchmark_id, kind))
    return candidate


def _install_message(path: Path, benchmark_id: str, kind: str) -> str:
    return (
        f"Benchmark {kind} is not installed: {path}. "
        f"Run `python tools/benchmarks.py install {benchmark_id}` from the repository root."
    )
