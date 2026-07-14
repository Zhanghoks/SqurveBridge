#!/usr/bin/env python3
"""Run the deterministic gates required for a SqurveBridge release candidate."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path = PROJECT_ROOT


def _python(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


def discover_evidence_checks(root: Path) -> list[Check]:
    evidence_root = root / "evidence" / "reported-results"
    if not evidence_root.is_dir():
        return []
    return [
        Check(
            f"evidence bundle {manifest.parent.name}",
            _python("tools/evidence.py", "verify", str(manifest.parent)),
            root,
        )
        for manifest in sorted(evidence_root.glob("*/manifest.json"))
    ]


def build_checks(root: Path, *, full: bool, history: bool, tests: bool) -> list[Check]:
    checks = [Check("public-tree security", _python("tools/security_scan.py"), root)]
    if history:
        checks.append(
            Check("reachable-history security", _python("tools/security_scan.py", "--history"), root)
        )
    checks.append(
        Check("benchmark package pointers", _python("tools/benchmarks.py", "verify-pointers"), root)
    )
    if full:
        checks.append(
            Check("benchmark package payloads", _python("tools/benchmarks.py", "verify-archives"), root)
        )

    for config in (
        "reproduce/configs/spider/c3sql.json",
        "reproduce/configs/bird/e-sql-smoke.json",
    ):
        checks.append(
            Check(
                f"reproduce contract {config}",
                _python("tools/verify.py", "reproduce-contract", "--path", config),
                root,
            )
        )

    if tests:
        checks.append(
            Check(
                "Python regressions",
                _python("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"),
                root,
            )
        )
    checks.extend(discover_evidence_checks(root))

    if full:
        checks.extend(
            [
                Check("Python package build", _python("-m", "build"), root),
                Check("reviewer workspace install", ("npm", "ci"), root / "demo-app"),
                Check("reviewer workspace build", ("npm", "run", "build"), root / "demo-app"),
            ]
        )
    return checks


def validate_document_links(root: Path) -> list[str]:
    missing: list[str] = []
    documents = [*sorted(root.glob("*.md")), *sorted((root / "docs").glob("*.md"))]
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            decoded = unquote(target.split("#", 1)[0])
            if not decoded:
                continue
            candidate = (document.parent / decoded).resolve()
            if not candidate.exists():
                missing.append(f"{document.relative_to(root)} -> {target}")
    return missing


def validate_release_metadata(root: Path) -> list[str]:
    errors: list[str] = []
    required = ("README.md", "LICENSE", "CITATION.cff", "SECURITY.md", "CONTRIBUTING.md")
    for name in required:
        if not (root / name).is_file():
            errors.append(f"missing required release file: {name}")

    citation = root / "CITATION.cff"
    if citation.is_file():
        text = citation.read_text(encoding="utf-8")
        for field in ("cff-version:", "title:", "authors:", "license:", "version:"):
            if field not in text:
                errors.append(f"CITATION.cff missing field: {field[:-1]}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also verify LFS payloads and build the Python package and reviewer workspace",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="skip the reachable-history scan (intended only for shallow PR checkouts)",
    )
    parser.add_argument("--skip-tests", action="store_true", help="skip Python unit tests")
    args = parser.parse_args(argv)

    static_errors = validate_release_metadata(PROJECT_ROOT) + validate_document_links(PROJECT_ROOT)
    if static_errors:
        print("Release metadata check failed:", file=sys.stderr)
        for error in static_errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    checks = build_checks(
        PROJECT_ROOT,
        full=args.full,
        history=not args.skip_history,
        tests=not args.skip_tests,
    )
    for index, check in enumerate(checks, start=1):
        print(f"[{index}/{len(checks)}] {check.name}", flush=True)
        try:
            subprocess.run(check.command, cwd=check.cwd, check=True)
        except FileNotFoundError as exc:
            print(f"Release check failed: command not found: {exc.filename}", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(
                f"Release check failed: {check.name} exited with status {exc.returncode}",
                file=sys.stderr,
            )
            return exc.returncode or 1

    print("Release check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
