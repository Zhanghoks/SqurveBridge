#!/usr/bin/env python3
"""Build the explicit, security-scannable Hugging Face Space context."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


RUNTIME_DIRECTORIES = (
    "core",
    "demo",
    "demo-app",
    "pi",
    "skills",
    "templates",
    "reproduce",
    "config",
    "evidence/reported-results",
    "tools",
)
RUNTIME_FILES = ("LICENSE", "pyproject.toml", "requirements.txt")
SPACE_BENCHMARK_DATABASE_DIRECTORIES = (
    "benchmarks/spider/database",
    "benchmarks/bird/dev/database",
    "benchmarks/ambidb/database",
    "benchmarks/BookSQL/database",
    "benchmarks/bull-cn/database",
    "benchmarks/bull-en/database",
    "benchmarks/ehrsql-2024/database",
    "benchmarks/spider2/lite/database",
)
SPACE_BENCHMARK_SCHEMA_FILES = (
    "benchmarks/spider/dev/schema.json",
    "benchmarks/bird/dev/schema.json",
    "benchmarks/ambidb/schema.json",
    "benchmarks/BookSQL/val/schema.json",
    "benchmarks/bull-cn/dev/schema.json",
    "benchmarks/bull-en/dev/schema.json",
    "benchmarks/ehrsql-2024/valid/schema.json",
    "benchmarks/spider2/lite/schema.json",
)
SPACE_BENCHMARK_FILES = (
    *SPACE_BENCHMARK_SCHEMA_FILES,
)

SPACE_DIRECTORY = "deploy/huggingface"
SPACE_OVERLAYS = {
    "Dockerfile": f"{SPACE_DIRECTORY}/Dockerfile",
    "README.md": f"{SPACE_DIRECTORY}/README.space.md",
    ".dockerignore": f"{SPACE_DIRECTORY}/Dockerfile.dockerignore",
}

IGNORED_DIRECTORY_NAMES = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "venv",
}
IGNORED_FILE_NAMES = {
    ".DS_Store",
    ".env",
    "credentials.json",
    "service-account.json",
    "service_account.json",
    "Thumbs.db",
}
IGNORED_FILE_SUFFIXES = {".key", ".p12", ".pem", ".pfx", ".pyc", ".pyo"}
VENDORED_RUNTIME_CREDENTIAL_SOURCE = "pi/packages/ai/src/auth/credential-store.ts"


def _ignore_non_runtime_files(directory: str, names: list[str]) -> set[str]:
    base = Path(directory)
    ignored: set[str] = set()
    for name in names:
        candidate = base / name
        is_vendored_runtime_source = candidate.as_posix().endswith(
            VENDORED_RUNTIME_CREDENTIAL_SOURCE
        )
        lowered = name.lower()
        if candidate.is_symlink():
            ignored.add(name)
        elif name in IGNORED_DIRECTORY_NAMES or name in IGNORED_FILE_NAMES:
            ignored.add(name)
        elif lowered == "thumbs.db" or name.startswith("._"):
            ignored.add(name)
        elif lowered.startswith(".env.") or (
            "credential" in lowered and not is_vendored_runtime_source
        ):
            ignored.add(name)
        elif candidate.is_file() and candidate.suffix.lower() in IGNORED_FILE_SUFFIXES:
            ignored.add(name)
    return ignored


def _require_directory(path: Path) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"Required runtime directory is missing: {path}")


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required runtime file is missing: {path}")


def _validate_output(root: Path, output: Path) -> None:
    if output == root or output in root.parents:
        raise ValueError("Bundle output cannot replace the repository root or its parent")

    source_directories = [root / relative for relative in RUNTIME_DIRECTORIES]
    source_directories.append(root / SPACE_DIRECTORY)
    if any(source == output or source in output.parents for source in source_directories):
        raise ValueError("Bundle output cannot be nested inside an allowlisted source directory")


def _clear_output(output: Path) -> None:
    if output.is_symlink() or output.is_file():
        output.unlink()
    elif output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def _copy_benchmark_assets(root: Path, output: Path, *, require_benchmarks: bool) -> None:
    """Copy all installed SQLite databases plus schemas, excluding question/SQL data."""
    for relative in SPACE_BENCHMARK_DATABASE_DIRECTORIES:
        source_directory = root / relative
        if not source_directory.is_dir():
            if require_benchmarks:
                _require_directory(source_directory)
            continue
        for source in source_directory.rglob("*.sqlite"):
            destination = output / source.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    for relative in SPACE_BENCHMARK_SCHEMA_FILES:
        source = root / relative
        if not source.is_file():
            if require_benchmarks:
                _require_file(source)
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_space(
    root: Path,
    output: Path,
    *,
    include_benchmarks: bool = False,
    require_benchmarks: bool = False,
) -> list[str]:
    """Build a clean Space directory and return its sorted relative file list."""

    root = root.resolve()
    output = output.resolve()
    _validate_output(root, output)
    _clear_output(output)

    for relative in RUNTIME_DIRECTORIES:
        source = root / relative
        _require_directory(source)
        shutil.copytree(
            source,
            output / relative,
            ignore=_ignore_non_runtime_files,
        )

    for relative in RUNTIME_FILES:
        source = root / relative
        _require_file(source)
        shutil.copy2(source, output / relative)

    # Production Docker builds obtain all benchmark ZIPs from GitHub LFS and
    # extract them in-image. Local full-bundle checks may opt in to copying the
    # same SQLite/schema assets directly.
    if include_benchmarks or require_benchmarks:
        _copy_benchmark_assets(root, output, require_benchmarks=require_benchmarks)

    space_source = root / SPACE_DIRECTORY
    _require_directory(space_source)
    shutil.copytree(
        space_source,
        output / SPACE_DIRECTORY,
        ignore=_ignore_non_runtime_files,
    )

    for bundled, source_relative in SPACE_OVERLAYS.items():
        source = root / source_relative
        _require_file(source)
        shutil.copy2(source, output / bundled)

    return sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the clean Hugging Face Space upload context."
    )
    parser.add_argument("--output", default="build/hf-space")
    parser.add_argument(
        "--include-benchmarks",
        action="store_true",
        help="copy installed SQLite/schema assets into the upload context",
    )
    parser.add_argument(
        "--require-benchmarks",
        action="store_true",
        help="fail if any full Live Demo benchmark asset is not installed",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    files = build_space(
        root,
        output,
        include_benchmarks=args.include_benchmarks,
        require_benchmarks=args.require_benchmarks,
    )
    print(
        f"Built Hugging Face Space bundle with {len(files)} files: "
        f"{output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
