#!/usr/bin/env python3
"""Fail closed on identity and submission details in the public repository tree.

Findings intentionally contain only a path, line number, and category. Matched
text and local denylist values are never printed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_TEXT_BYTES = 2_000_000
VENDORED_IDENTITY_PREFIXES = {"pi"}

SENSITIVE_PATH_PARTS = {
    "camera-ready",
    "manuscript",
    "paper",
    "private",
    "private-notes",
    "rebuttal",
    "review",
    "reviews",
    "submission",
    "submissions",
}
SENSITIVE_FILE_PATTERNS = (
    re.compile(r"^(?:author-info|affiliations)(?:\..+)?$", re.IGNORECASE),
    re.compile(r"^(?:submission|rebuttal|review|camera-ready).+\.pdf$", re.IGNORECASE),
)

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
HOME_PATTERNS = (
    re.compile(r"/(?:Users|home)/([^/\s]+)(?:/|\b)"),
    re.compile(r"[A-Z]:\\Users\\([^\\\s]+)(?:\\|\b)", re.IGNORECASE),
)
PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}
PLACEHOLDER_HOME_USERS = {"example", "runner"}

PUBLIC_NARRATIVE_PATHS = {
    "README.md",
    "CITATION.cff",
    "pyproject.toml",
    "demo-app/package.json",
    "demo/README.md",
    "demo/README_EN.md",
    "evidence/README.md",
}
SUBMISSION_NARRATIVE_PATTERNS = (
    re.compile(r"\bpaper at a glance\b", re.IGNORECASE),
    re.compile(r"\baccompanying (?:paper|manuscript)\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this) paper\b", re.IGNORECASE),
    re.compile(r"\bpaper(?:'s)? (?:evidence|experiment|result|table|workflow)\b", re.IGNORECASE),
    re.compile(r"\b(?:reviewer|rebuttal|camera[- ]ready|submission id)\b", re.IGNORECASE),
    re.compile(r"\b(?:ACL|EMNLP|NAACL|NeurIPS|ICML|ICLR)\b"),
)
PERSONAL_PROJECT_URL = re.compile(
    r"https?://github\.com/[^/\s)'\"]+/SqurveBridge(?:\.git)?", re.IGNORECASE
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    category: str

    def render(self, root: Path) -> str:
        relative = self.path.relative_to(root).as_posix()
        location = f"{relative}:{self.line}" if self.line else relative
        return f"{location}: {self.category}"


def discover_public_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / raw.decode("utf-8", errors="surrogateescape")
        if path.is_file():
            paths.append(path)
    return paths


def load_denylist(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append(term)
    return tuple(terms)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _is_public_narrative_path(relative: str) -> bool:
    return relative in PUBLIC_NARRATIVE_PATHS or (
        relative.startswith("docs/") and relative.endswith(".md")
    )


def _metadata_findings(path: Path, relative: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if relative == "CITATION.cff" and 'name: "Anonymous Authors"' not in text:
        findings.append(Finding(path, 1, "non-anonymous author metadata"))
    if relative == "pyproject.toml" and '{ name = "Anonymous Authors" }' not in text:
        findings.append(Finding(path, 1, "non-anonymous author metadata"))
    if relative == "demo-app/package.json" and re.search(
        r'"repository"\s*:', text
    ):
        match = re.search(r'"repository"\s*:', text)
        assert match is not None
        findings.append(
            Finding(path, _line_number(text, match.start()), "personal project metadata")
        )
    return findings


def scan_path(
    path: Path,
    root: Path,
    deny_terms: tuple[str, ...] = (),
) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    relative_path = Path(relative)
    lowered_parts = {part.lower() for part in relative_path.parts[:-1]}
    if lowered_parts & SENSITIVE_PATH_PARTS or any(
        pattern.match(relative_path.name) for pattern in SENSITIVE_FILE_PATTERNS
    ):
        findings.append(Finding(path, 0, "private submission path"))

    if path.stat().st_size > MAX_TEXT_BYTES:
        return findings
    data = path.read_bytes()
    if b"\x00" in data:
        return findings
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return findings

    for match in EMAIL_PATTERN.finditer(text):
        if match.group(2).lower() in PLACEHOLDER_EMAIL_DOMAINS:
            continue
        findings.append(Finding(path, _line_number(text, match.start()), "personal email"))

    for pattern in HOME_PATTERNS:
        for match in pattern.finditer(text):
            if match.group(1).lower() in PLACEHOLDER_HOME_USERS:
                continue
            findings.append(
                Finding(path, _line_number(text, match.start()), "absolute user path")
            )

    lowered = text.casefold()
    for term in deny_terms:
        if not term:
            continue
        start = lowered.find(term.casefold())
        while start >= 0:
            findings.append(Finding(path, _line_number(text, start), "denylist term"))
            start = lowered.find(term.casefold(), start + max(len(term), 1))

    if _is_public_narrative_path(relative):
        for pattern in SUBMISSION_NARRATIVE_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(
                    Finding(path, _line_number(text, match.start()), "submission narrative")
                )
        for match in PERSONAL_PROJECT_URL.finditer(text):
            findings.append(
                Finding(path, _line_number(text, match.start()), "personal project URL")
            )
        findings.extend(_metadata_findings(path, relative, text))

    return findings


def scan_paths(
    paths: list[Path],
    root: Path,
    deny_terms: tuple[str, ...] = (),
) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in VENDORED_IDENTITY_PREFIXES:
            continue
        findings.extend(scan_path(path, root, deny_terms))
    return sorted(
        set(findings),
        key=lambda item: (item.path.as_posix(), item.line, item.category),
    )


def scan_repository(
    root: Path = PROJECT_ROOT,
    deny_terms: tuple[str, ...] = (),
) -> list[Finding]:
    return scan_paths(discover_public_paths(root), root, deny_terms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--denylist",
        type=Path,
        default=PROJECT_ROOT / ".anonymity-denylist",
        help="local ignored file containing one literal deny term per line",
    )
    parser.add_argument(
        "--deny-term",
        action="append",
        default=[],
        help="one additional literal deny term; matched values are never printed",
    )
    args = parser.parse_args(argv)

    denylist_path = args.denylist
    if not denylist_path.is_absolute():
        denylist_path = PROJECT_ROOT / denylist_path
    terms = (*load_denylist(denylist_path), *args.deny_term)
    findings = scan_repository(PROJECT_ROOT, terms)
    if findings:
        print("Anonymous-submission scan failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding.render(PROJECT_ROOT)}", file=sys.stderr)
        return 1

    print("Anonymous-submission scan: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
