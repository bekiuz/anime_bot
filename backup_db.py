import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = (
    os.getenv("SUPABASE_DB_URL", "").strip()
    or os.getenv("DATABASE_URL", "").strip()
)

if not DATABASE_URL:
    raise RuntimeError(
        "SUPABASE_DB_URL yoki DATABASE_URL topilmadi."
    )

TABLES = (
    "users",
    "animes",
    "episodes",
    "shorts",
    "broadcasts",
    "favorites",
    "watch_history",
    "anime_requests",
)

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def make_backup():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{timestamp}.json.gz"

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        autocommit=True,
    ) as conn:
        data = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tables": {},
        }

        for table in TABLES:
            rows = conn.execute(
                f'SELECT * FROM public."{table}" ORDER BY 1'
            ).fetchall()

            data["tables"][table] = [
                dict(row)
                for row in rows
            ]

    with gzip.open(
        backup_path,
        "wt",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    # Keep the newest 14 local snapshots.
    backups = sorted(
        BACKUP_DIR.glob("backup_*.json.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_backup in backups[14:]:
        old_backup.unlink(missing_ok=True)

    print(
        f"✅ Database backup saved: {backup_path}",
        flush=True,
    )

    return backup_path

if __name__ == "__main__":
    make_backup()
