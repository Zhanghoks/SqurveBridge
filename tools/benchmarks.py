#!/usr/bin/env python3
"""Build, inspect, and install the versioned Spider/BIRD benchmark archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks"
PACKAGE_ROOT = BENCHMARK_ROOT / "packages"
MANIFEST_PATH = PACKAGE_ROOT / "manifest.json"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
EXCLUDED_SUFFIXES = {".pyc", ".sqlite-shm", ".sqlite-wal", ".swp", ".tmp"}
SENSITIVE_SUFFIXES = {".env", ".key", ".pem", ".p12", ".pfx", ".secret"}
MAX_MEMBER_BYTES = 4 * 1024**3
MAX_TOTAL_BYTES = 8 * 1024**3
MAX_COMPRESSION_RATIO = 2_000


class BenchmarkError(RuntimeError):
    """Raised for an invalid archive, installation, or benchmark layout."""


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot load {MANIFEST_PATH.relative_to(PROJECT_ROOT)}: {exc}") from exc
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("benchmarks"), dict):
        raise BenchmarkError("unsupported or malformed benchmark manifest")
    return manifest


def _entry(manifest: dict[str, Any], slug: str) -> dict[str, Any]:
    try:
        return manifest["benchmarks"][slug]
    except KeyError as exc:
        choices = ", ".join(sorted(manifest["benchmarks"]))
        raise BenchmarkError(f"unknown benchmark {slug!r}; choose one of: {choices}") from exc


def _archive_path(entry: dict[str, Any]) -> Path:
    path = PROJECT_ROOT / entry["archive"]
    if path.parent != PACKAGE_ROOT or path.suffix != ".zip":
        raise BenchmarkError(f"archive must be a direct .zip child of {PACKAGE_ROOT.relative_to(PROJECT_ROOT)}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(slug: str) -> list[Path]:
    root = BENCHMARK_ROOT / slug
    if not root.is_dir():
        raise BenchmarkError(f"missing source directory {root}; install or prepare the benchmark first")
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BenchmarkError(f"symlinks are not allowed in benchmark sources: {path}")
        if not path.is_file():
            continue
        if path.name in EXCLUDED_NAMES or any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
            continue
        if path.name == "data_clean.py" or "__pycache__" in path.parts:
            continue
        files.append(path)
    if not files:
        raise BenchmarkError(f"no packageable files found under {root}")
    return sorted(files, key=lambda item: item.relative_to(BENCHMARK_ROOT).as_posix())


def _write_deterministic_zip(slug: str, destination: Path) -> None:
    files = _source_files(slug)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True
        ) as archive:
            for path in files:
                member = path.relative_to(BENCHMARK_ROOT).as_posix()
                info = zipfile.ZipInfo(member, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _is_lfs_pointer(path: Path) -> tuple[str, int] | None:
    if not path.is_file() or path.stat().st_size > 1024:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("version https://git-lfs.github.com/spec/v1\n"):
        return None
    values: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        key, _, value = line.partition(" ")
        values[key] = value
    oid = values.get("oid", "")
    size = values.get("size", "")
    if not oid.startswith("sha256:") or not size.isdigit():
        raise BenchmarkError(f"malformed Git LFS pointer: {path.relative_to(PROJECT_ROOT)}")
    return oid.removeprefix("sha256:"), int(size)


def _validate_member(
    info: zipfile.ZipInfo, top_level: str, seen: set[str], allowed_suffixes: set[str] | None = None
) -> None:
    name = info.filename
    pure = PurePosixPath(name)
    if name in seen:
        raise BenchmarkError(f"duplicate archive member: {name}")
    seen.add(name)
    if not name or "\\" in name or pure.is_absolute() or ".." in pure.parts:
        raise BenchmarkError(f"unsafe archive member path: {name!r}")
    if pure.parts[0] != top_level:
        raise BenchmarkError(f"archive member is outside {top_level}/: {name}")
    if pure.name in EXCLUDED_NAMES or pure.name.startswith("."):
        raise BenchmarkError(f"hidden or local-only files are forbidden in archives: {name}")
    if any(pure.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES | SENSITIVE_SUFFIXES):
        raise BenchmarkError(f"local state or credential-like files are forbidden in archives: {name}")
    if allowed_suffixes is not None and pure.suffix.lower() not in allowed_suffixes:
        raise BenchmarkError(f"undeclared file type in benchmark archive: {name}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise BenchmarkError(f"symbolic links are forbidden in archives: {name}")
    if info.flag_bits & 0x1:
        raise BenchmarkError(f"encrypted archive members are forbidden: {name}")
    if info.file_size > MAX_MEMBER_BYTES:
        raise BenchmarkError(f"archive member exceeds the size limit: {name}")
    if info.compress_size == 0:
        if info.file_size:
            raise BenchmarkError(f"invalid compressed size for archive member: {name}")
    elif info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise BenchmarkError(f"archive member exceeds the compression-ratio limit: {name}")


def _inspect_archive(path: Path, entry: dict[str, Any], *, content_hash: bool) -> dict[str, Any]:
    if not path.is_file():
        raise BenchmarkError(f"missing archive {path.relative_to(PROJECT_ROOT)}; run `git lfs pull`")
    pointer = _is_lfs_pointer(path)
    if pointer:
        raise BenchmarkError(f"{path.relative_to(PROJECT_ROOT)} is still a Git LFS pointer; run `git lfs pull`")
    expected_hash = entry.get("sha256")
    if content_hash and _sha256(path) != expected_hash:
        raise BenchmarkError(f"SHA-256 mismatch for {path.relative_to(PROJECT_ROOT)}")
    if path.stat().st_size != entry.get("archive_size"):
        raise BenchmarkError(f"archive size mismatch for {path.relative_to(PROJECT_ROOT)}")
    seen: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                _validate_member(info, entry["top_level"], seen, set(entry["allowed_suffixes"]))
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise BenchmarkError(f"archive exceeds the total extraction limit: {path.name}")
            bad = archive.testzip()
            if bad:
                raise BenchmarkError(f"CRC validation failed for archive member: {bad}")
    except zipfile.BadZipFile as exc:
        raise BenchmarkError(f"invalid ZIP archive {path.relative_to(PROJECT_ROOT)}: {exc}") from exc
    required = set(entry["required_files"])
    missing = sorted(required - seen)
    if missing:
        raise BenchmarkError(f"archive is missing required files: {', '.join(missing)}")
    if total != entry.get("uncompressed_size"):
        raise BenchmarkError(f"uncompressed size mismatch for {path.relative_to(PROJECT_ROOT)}")
    if len(seen) != entry.get("member_count"):
        raise BenchmarkError(f"member count mismatch for {path.relative_to(PROJECT_ROOT)}")
    return {"members": len(seen), "uncompressed_size": total}


def _dataset_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read dataset {path}: {exc}") from exc
    if not isinstance(data, list):
        raise BenchmarkError(f"dataset must be a JSON array: {path}")
    return len(data)


def _verify_tree(slug: str, root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    for relative in entry["required_files"]:
        inner = PurePosixPath(relative)
        if inner.parts[0] != slug:
            raise BenchmarkError(f"manifest required path does not start with {slug}/: {relative}")
        path = root.joinpath(*inner.parts[1:])
        if not path.is_file():
            raise BenchmarkError(f"missing required benchmark file: {path}")
    actual_counts: dict[str, int] = {}
    for split, expected in entry["dataset_counts"].items():
        actual = _dataset_count(root / split / "dataset.json")
        actual_counts[split] = actual
        if actual != expected:
            raise BenchmarkError(f"{slug}/{split} has {actual} samples, expected {expected}")
    sqlite_files = sorted(root.rglob("*.sqlite"))
    if len(sqlite_files) != entry["sqlite_count"]:
        raise BenchmarkError(f"{slug} has {len(sqlite_files)} SQLite files, expected {entry['sqlite_count']}")
    for database in sqlite_files:
        try:
            uri = f"file:{database.resolve().as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA schema_version").fetchone()
        except sqlite3.Error as exc:
            raise BenchmarkError(f"cannot open SQLite database {database}: {exc}") from exc
    return {"dataset_counts": actual_counts, "sqlite_count": len(sqlite_files)}


def command_list(manifest: dict[str, Any]) -> None:
    for slug, entry in sorted(manifest["benchmarks"].items()):
        archive = _archive_path(entry)
        state = "missing"
        if archive.exists():
            state = "lfs-pointer" if _is_lfs_pointer(archive) else "available"
        print(f"{slug:8} {entry['version']:12} {state:11} {entry['archive']}")


def command_verify_pointers(manifest: dict[str, Any]) -> None:
    for slug, entry in sorted(manifest["benchmarks"].items()):
        archive = _archive_path(entry)
        if not archive.is_file():
            raise BenchmarkError(f"missing tracked archive path: {archive.relative_to(PROJECT_ROOT)}")
        pointer = _is_lfs_pointer(archive)
        if pointer:
            oid, size = pointer
            if oid != entry["sha256"] or size != entry["archive_size"]:
                raise BenchmarkError(f"Git LFS pointer does not match manifest for {slug}")
        else:
            if archive.stat().st_size != entry["archive_size"]:
                raise BenchmarkError(f"archive size does not match manifest for {slug}")
            if _sha256(archive) != entry["sha256"]:
                raise BenchmarkError(f"archive SHA-256 does not match manifest for {slug}")
        print(f"OK {slug}: archive/LFS metadata matches manifest")


def command_verify_archives(manifest: dict[str, Any]) -> None:
    for slug, entry in sorted(manifest["benchmarks"].items()):
        result = _inspect_archive(_archive_path(entry), entry, content_hash=True)
        print(f"OK {slug}: {result['members']} members, {result['uncompressed_size']} bytes")


def _refresh_archive_metadata(entry: dict[str, Any], path: Path) -> None:
    total = 0
    members = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            total += info.file_size
            members += 1
    entry["sha256"] = _sha256(path)
    entry["archive_size"] = path.stat().st_size
    entry["uncompressed_size"] = total
    entry["member_count"] = members


def command_build(manifest: dict[str, Any], slugs: Iterable[str]) -> None:
    for slug in slugs:
        entry = _entry(manifest, slug)
        destination = _archive_path(entry)
        print(f"building {destination.relative_to(PROJECT_ROOT)} ...", flush=True)
        _write_deterministic_zip(slug, destination)
        _refresh_archive_metadata(entry, destination)
        _inspect_archive(destination, entry, content_hash=True)
        print(f"OK {slug}: {entry['archive_size']} bytes, sha256={entry['sha256']}")
    temporary_manifest = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, MANIFEST_PATH)


def command_install(manifest: dict[str, Any], slug: str, force: bool) -> None:
    entry = _entry(manifest, slug)
    archive = _archive_path(entry)
    _inspect_archive(archive, entry, content_hash=True)
    target = BENCHMARK_ROOT / slug
    if target.exists() and not force:
        raise BenchmarkError(f"{target} already exists; pass --force to replace a verified installation")
    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{slug}-install-", dir=BENCHMARK_ROOT))
    backup = BENCHMARK_ROOT / f".{slug}-backup"
    try:
        with zipfile.ZipFile(archive) as source:
            seen: set[str] = set()
            for info in source.infolist():
                _validate_member(info, slug, seen, set(entry["allowed_suffixes"]))
            source.extractall(temporary)
        extracted = temporary / slug
        _verify_tree(slug, extracted, entry)
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(extracted, target)
        except BaseException:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(f"OK {slug}: installed at {target.relative_to(PROJECT_ROOT)}")


def command_verify(manifest: dict[str, Any], slug: str) -> None:
    entry = _entry(manifest, slug)
    result = _verify_tree(slug, BENCHMARK_ROOT / slug, entry)
    print(f"OK {slug}: datasets={result['dataset_counts']}, sqlite={result['sqlite_count']}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("list", help="list packaged benchmarks and local archive state")
    subcommands.add_parser("verify-pointers", help="verify manifest against LFS pointers or local archive sizes")
    subcommands.add_parser("verify-archives", help="fully hash and inspect downloaded ZIP archives")
    build = subcommands.add_parser("build", help="build deterministic archives and refresh the manifest")
    build.add_argument("benchmark", help="spider, bird, or all")
    install = subcommands.add_parser("install", help="safely install a downloaded benchmark archive")
    install.add_argument("benchmark")
    install.add_argument("--force", action="store_true", help="replace an existing verified installation")
    verify = subcommands.add_parser("verify", help="verify an installed benchmark directory")
    verify.add_argument("benchmark")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = _load_manifest()
        if args.command == "list":
            command_list(manifest)
        elif args.command == "verify-pointers":
            command_verify_pointers(manifest)
        elif args.command == "verify-archives":
            command_verify_archives(manifest)
        elif args.command == "build":
            slugs = sorted(manifest["benchmarks"]) if args.benchmark == "all" else [args.benchmark]
            command_build(manifest, slugs)
        elif args.command == "install":
            command_install(manifest, args.benchmark, args.force)
        elif args.command == "verify":
            command_verify(manifest, args.benchmark)
    except BenchmarkError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
