#!/usr/bin/env python3
"""Extract the complete versioned benchmark archives needed by the Space."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path, PurePosixPath


ARCHIVES = (
    "ambidb.zip",
    "BookSQL.zip",
    "bird.zip",
    "bull-cn.zip",
    "bull-en.zip",
    "ehrsql-2024.zip",
    "spider.zip",
    "spider2.zip",
)
def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe archive member: {name!r}")
    return path


def extract_space_assets(archive_root: Path, output_root: Path) -> int:
    copied = 0
    for archive_name in ARCHIVES:
        archive_path = archive_root / archive_name
        if not archive_path.is_file():
            raise FileNotFoundError(f"missing required benchmark archive: {archive_path}")
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                member = _safe_member(info.filename)
                if info.is_dir():
                    continue
                target = output_root.joinpath(*member.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)
                copied += 1
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(f"Extracted {extract_space_assets(args.archive_root, args.output_root)} Space database assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
