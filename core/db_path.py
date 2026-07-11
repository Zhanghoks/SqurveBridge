import sqlite3
from os import PathLike
from pathlib import Path
from typing import Iterable, Optional, Union


def sqlite_table_count(path: Union[str, PathLike]) -> Optional[int]:
    """Return table count for a SQLite file, or None when it is not readable."""
    try:
        conn = sqlite3.connect(path)
        try:
            return conn.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return None


def resolve_sqlite_file(
    db_root: Union[str, PathLike],
    db_id: str,
    fallback_db_ids: Iterable[str] = (),
) -> Path:
    """Resolve flat or nested SQLite layouts, preferring readable non-empty files."""
    root = Path(db_root)
    if root.suffix in (".sqlite", ".db"):
        return root

    db_ids = [db_id, *fallback_db_ids]
    candidates = []
    seen = set()
    for candidate_db_id in db_ids:
        if not candidate_db_id:
            continue
        for candidate in (
            root / f"{candidate_db_id}.sqlite",
            root / candidate_db_id / f"{candidate_db_id}.sqlite",
        ):
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)

    existing = [path for path in candidates if path.exists()]
    for path in existing:
        table_count = sqlite_table_count(path)
        if table_count and table_count > 0:
            return path

    if existing:
        return existing[0]
    return candidates[0] if candidates else root / f"{db_id}.sqlite"
