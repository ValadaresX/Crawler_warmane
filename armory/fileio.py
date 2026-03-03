"""Atomic file I/O helpers for safe checkpoint writes."""
from __future__ import annotations

import contextlib
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Generator


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@contextlib.contextmanager
def atomic_path(path: Path) -> Generator[Path, None, None]:
    """Context manager that yields a temporary path in the same directory.

    On successful exit the temp file is atomically renamed to *path*.
    On exception the temp file is cleaned up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        yield tmp_path
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def write_json_atomic(path: Path, data: Any) -> None:
    with atomic_path(path) as tmp:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def append_jsonl_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


_CSV_FIELDS = [
    "name",
    "realm",
    "class",
    "race",
    "level",
    "specialization",
    "stamina",
    "resilience",
    "estimated_hp",
    "gear_score",
    "average_item_level",
    "item_count",
    "enchant_count",
    "gem_count",
    "melee_power",
    "spell_power",
    "armor",
    "dodge_pct",
    "parry_pct",
    "block_pct",
    "crit_melee_pct",
    "crit_spell_pct",
    "hit_melee_pct",
    "hit_spell_pct",
    "source_match_count",
    "source_match_ids",
    "summary_url",
    "items_json",
    "character_stats_json",
    "collected_at_utc",
]


def write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    with atomic_path(path) as tmp:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow(r)


def write_parquet_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    import pandas as pd

    with atomic_path(path) as tmp:
        pd.DataFrame(rows).to_parquet(tmp, index=False, compression="snappy")


def write_items_parquet_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    import pandas as pd

    item_rows: list[dict[str, Any]] = []
    for row in rows:
        raw_items = str(row.get("items_json", "")).strip()
        if not raw_items:
            continue
        try:
            items = json.loads(raw_items)
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            gems = it.get("gem_ids", [])
            if not isinstance(gems, list):
                gems = []
            item_rows.append({
                "name": row.get("name"),
                "realm": row.get("realm"),
                "class": row.get("class"),
                "specialization": row.get("specialization"),
                "gear_score": row.get("gear_score"),
                "summary_url": row.get("summary_url"),
                "collected_at_utc": row.get("collected_at_utc"),
                "slot": it.get("slot"),
                "item_id": it.get("item_id"),
                "enchant_id": it.get("enchant_id"),
                "gem_count": len(gems),
                "gem_ids_json": json.dumps(gems, ensure_ascii=False, separators=(",", ":")),
                "href": it.get("href"),
                "rel": it.get("rel"),
            })
    with atomic_path(path) as tmp:
        pd.DataFrame(item_rows).to_parquet(tmp, index=False, compression="snappy")
