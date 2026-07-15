#!/usr/bin/env python3
"""Fail closed on secrets and credential files in the public repository tree.

The scanner never prints a matched value. It reports only a path, line number,
and finding category so CI logs cannot become a second disclosure surface.
"""

from __future__ import annotations

import argparse
import re
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_TEXT_BYTES = 2_000_000
MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 20_000_000_000
MAX_COMPRESSION_RATIO = 200

SENSITIVE_BASENAMES = {
    ".env",
    "credentials.json",
    "service-account.json",
    "service_account.json",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
FORBIDDEN_ARCHIVE_NAMES = {".ds_store", "thumbs.db"}
FORBIDDEN_ARCHIVE_PARTS = {"__macosx"}

HIGH_CONFIDENCE_PATTERNS = {
    "private-key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "openai-style-token": re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "github-token": re.compile(
        rb"\b(?:ghp_|gho_|ghu_|ghs_|github_pat_)[A-Za-z0-9_]{16,}\b"
    ),
    "aws-access-key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "slack-token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    "google-api-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
}

GENERIC_ASSIGNMENT = re.compile(
    rb"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    rb"password|private[_-]?key)\b\s*[:=]\s*[\"']([^\"']{8,})[\"']"
)

PLACEHOLDER_MARKERS = (
    b"${env:",
    b"<",
    b"changeme",
    b"dummy",
    b"example",
    b"getenv",
    b"none",
    b"null",
    b"os.environ",
    b"placeholder",
    b"redacted",
    b"replace",
    b"test",
    b"your_",
)

HISTORY_PATTERNS = {
    "private-key": r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY",
    "openai-style-token": r"sk-[A-Za-z0-9_-]{16,}",
    "github-token": r"(ghp_|gho_|ghu_|ghs_|github_pat_)[A-Za-z0-9_]{16,}",
    "aws-access-key": r"AKIA[0-9A-Z]{16}",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    category: str

    def render(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"{location}: {self.category}"


def discover_public_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / raw.decode("utf-8", errors="surrogateescape")
        if path.is_file():
            paths.append(path)
    return paths


def _is_placeholder(value: bytes) -> bool:
    lowered = value.strip().lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _scan_bytes(
    data: bytes,
    display_path: str,
    *,
    generic_assignments: bool = True,
) -> list[Finding]:
    findings: list[Finding] = []
    if len(data) > MAX_TEXT_BYTES or b"\x00" in data:
        return findings

    for category, pattern in HIGH_CONFIDENCE_PATTERNS.items():
        for match in pattern.finditer(data):
            line = data.count(b"\n", 0, match.start()) + 1
            line_start = data.rfind(b"\n", 0, match.start()) + 1
            line_end = data.find(b"\n", match.end())
            if line_end < 0:
                line_end = len(data)
            if _is_placeholder(data[line_start:line_end]):
                continue
            findings.append(Finding(display_path, line, category))

    if generic_assignments:
        for match in GENERIC_ASSIGNMENT.finditer(data):
            if _is_placeholder(match.group(2)):
                continue
            line = data.count(b"\n", 0, match.start()) + 1
            findings.append(Finding(display_path, line, "literal-credential-assignment"))

    return findings


def _archive_member_path(name: str) -> PurePosixPath:
    return PurePosixPath(name.replace("\\", "/"))


def scan_zip_path(path: Path, root: Path) -> list[Finding]:
    """Inspect a release archive without extracting it or logging its contents."""
    relative = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    if path.stat().st_size <= 1_024:
        header = path.read_bytes()
        if header.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            return _scan_bytes(header, relative)
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return [Finding(relative, 0, "invalid-zip-archive")]

    with archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            findings.append(Finding(relative, 0, "archive-member-limit-exceeded"))

        total_uncompressed = sum(member.file_size for member in members)
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            findings.append(Finding(relative, 0, "archive-size-limit-exceeded"))

        seen: set[str] = set()
        for member in members:
            member_path = _archive_member_path(member.filename)
            display_path = f"{relative}!{member.filename}"
            normalized = member_path.as_posix()
            lowered_parts = {part.lower() for part in member_path.parts}
            lowered_name = member_path.name.lower()

            if normalized in seen:
                findings.append(Finding(display_path, 0, "duplicate-archive-member"))
            seen.add(normalized)

            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or re.match(r"^[A-Za-z]:", normalized)
            ):
                findings.append(Finding(display_path, 0, "unsafe-archive-path"))
            if member.flag_bits & 0x1:
                findings.append(Finding(display_path, 0, "encrypted-archive-member"))

            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                findings.append(Finding(display_path, 0, "archive-symlink"))
            if lowered_name in FORBIDDEN_ARCHIVE_NAMES or (
                lowered_parts & FORBIDDEN_ARCHIVE_PARTS
            ):
                findings.append(Finding(display_path, 0, "archive-system-file"))
            if lowered_name in SENSITIVE_BASENAMES and lowered_name != ".env.example":
                findings.append(Finding(display_path, 0, "archive-credential-file"))
            if member_path.suffix.lower() in SENSITIVE_SUFFIXES:
                findings.append(Finding(display_path, 0, "archive-private-credential-file"))
            if "credential" in lowered_name:
                findings.append(Finding(display_path, 0, "archive-credential-named-file"))

            if member.file_size and member.compress_size == 0:
                findings.append(Finding(display_path, 0, "abnormal-compression-ratio"))
            elif member.compress_size and (
                member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
            ):
                findings.append(Finding(display_path, 0, "abnormal-compression-ratio"))

            if member.is_dir() or member.file_size > MAX_TEXT_BYTES:
                continue
            try:
                data = archive.read(member)
            except (RuntimeError, OSError, zipfile.BadZipFile):
                findings.append(Finding(display_path, 0, "unreadable-archive-member"))
                continue
            findings.extend(_scan_bytes(data, display_path))

    return findings


def scan_path(path: Path, root: Path) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    vendored_pi = relative == "pi" or relative.startswith("pi/")
    lowered_name = path.name.lower()
    findings: list[Finding] = []

    if lowered_name in SENSITIVE_BASENAMES and lowered_name != ".env.example":
        findings.append(Finding(relative, 0, "credential-file"))
    if path.suffix.lower() in SENSITIVE_SUFFIXES:
        findings.append(Finding(relative, 0, "private-credential-file"))
    if (
        not vendored_pi
        and "credential" in lowered_name
        and lowered_name != ".env.example"
    ):
        findings.append(Finding(relative, 0, "credential-named-file"))

    if path.suffix.lower() == ".zip":
        findings.extend(scan_zip_path(path, root))
        return findings

    if path.stat().st_size > MAX_TEXT_BYTES:
        return findings
    return findings + _scan_bytes(
        path.read_bytes(),
        relative,
        generic_assignments=not vendored_pi,
    )


def scan_paths(paths: list[Path], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        findings.extend(scan_path(path, root))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.category))


def scan_history(root: Path) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for category, pattern in HISTORY_PATTERNS.items():
        result = subprocess.run(
            ["git", "log", "--all", "--format=%H", f"-G{pattern}", "--", "."],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        commits = sorted(set(result.stdout.splitlines()))
        if commits:
            matches[category] = commits
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        action="store_true",
        help="also fail when high-confidence secret patterns exist in reachable Git history",
    )
    args = parser.parse_args(argv)

    findings = scan_paths(discover_public_paths(PROJECT_ROOT), PROJECT_ROOT)
    if findings:
        print("Public-tree security scan failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding.render()}", file=sys.stderr)
        return 1

    if args.history:
        history_matches = scan_history(PROJECT_ROOT)
        if history_matches:
            print("Git-history security scan failed:", file=sys.stderr)
            for category, commits in sorted(history_matches.items()):
                preview = ", ".join(commit[:12] for commit in commits[:5])
                suffix = " ..." if len(commits) > 5 else ""
                print(
                    f"- {category}: {len(commits)} reachable commit(s): {preview}{suffix}",
                    file=sys.stderr,
                )
            print(
                "Rotate affected credentials before rewriting and force-pushing history.",
                file=sys.stderr,
            )
            return 1

    print("Security scan: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
