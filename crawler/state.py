"""Gerenciamento de estado, persistência, acúmulo de métricas."""
from __future__ import annotations

import argparse
from typing import Any

from crawler.base import class_from_hint, key_of, now_iso

from armory.match_history import PlayerRef
from armory.fileio import (
    write_csv_atomic,
    write_items_parquet_atomic,
    write_json_atomic,
    write_parquet_atomic,
)


# ── State ───────────────────────────────────────────────────────────

def default_state(host: str) -> dict[str, Any]:
    return {
        "version": 1,
        "host": host,
        "created_at_utc": now_iso(),
        "updated_at_utc": now_iso(),
        "cycle": 0,
        "players": {},
        "processed_players": {},
        "failed_players": {},
        "processed_match_ids": [],
        "fetched_guilds": [],
        "no_progress_cycles": 0,
        "network": {
            "delay_factor": 1.0,
            "consecutive_errors": 0,
            "last_error": None,
            "last_error_utc": None,
            "stats": {"ok": 0, "err": 0, "latency_ms_ema": None},
        },
        "telemetry": {"cycles": []},
    }


def ensure_player(state: dict[str, Any], name: str, realm: str) -> dict[str, Any]:
    p = state["players"].get(key_of(name, realm))
    if p is None:
        p = {
            "name": name,
            "realm": realm,
            "class_hint": None,
            "class_hint_name": None,
            "ladder_seed_rank": None,
            "source_match_ids": [],
            "history_scan_count": 0,
            "last_history_scan_utc": None,
            "first_seen_utc": now_iso(),
            "last_seen_utc": now_iso(),
        }
        state["players"][key_of(name, realm)] = p
    return p


def update_player_from_ref(state: dict[str, Any], player_ref: PlayerRef, match_id: str) -> None:
    p = ensure_player(state, player_ref.name, player_ref.realm)
    hint = str(player_ref.class_hint or "").strip()
    if hint and not p.get("class_hint"):
        p["class_hint"] = hint
    hint_name = class_from_hint(hint)
    if hint_name:
        p["class_hint_name"] = hint_name
    mids = p.get("source_match_ids", [])
    if isinstance(mids, list) and match_id not in mids:
        mids.append(match_id)
    p["last_seen_utc"] = now_iso()


# ── Persistência ────────────────────────────────────────────────────

_SAVE_LAST_DATASET_SIZE: int = -1


def save_all(args: argparse.Namespace, state: dict[str, Any], processed_match_ids: set[str]) -> None:
    global _SAVE_LAST_DATASET_SIZE
    if args.dry_run:
        return
    state["updated_at_utc"] = now_iso()
    state["processed_match_ids"] = sorted(processed_match_ids, key=lambda x: int(x) if str(x).isdigit() else str(x))
    write_json_atomic(args.state_file, state)
    rows = sorted(state["processed_players"].values(), key=lambda r: (r["realm"], r["class"], r["name"]))
    write_json_atomic(args.dataset_json, rows)
    dataset_changed = len(rows) != _SAVE_LAST_DATASET_SIZE
    if dataset_changed:
        write_csv_atomic(args.dataset_csv, rows)
        if getattr(args, "dataset_parquet", None):
            write_parquet_atomic(args.dataset_parquet, rows)
        if getattr(args, "items_parquet", None):
            write_items_parquet_atomic(args.items_parquet, rows)
        _SAVE_LAST_DATASET_SIZE = len(rows)


# ── Métricas ────────────────────────────────────────────────────────

_HISTORY_METRIC_MAP = {
    "history_pages_ok": "pages_scanned",
    "history_page_errors": "page_errors",
    "history_matches_seen": "matches_seen",
    "history_new_match_ids": "new_match_ids",
    "history_details_target": "details_target",
    "history_details_done": "details_done",
    "history_detail_errors": "detail_errors",
}

_PROFILE_METRIC_MAP = {
    "profiles_candidates": "candidates",
    "profiles_chosen": "chosen",
    "profiles_attempted": "attempted",
    "profiles_ok": "ok",
    "profiles_failed": "failed",
    "profiles_skipped_cooldown": "skipped_failed_cooldown",
}


def _accum_metrics(target: dict[str, Any], source: dict[str, Any], mapping: dict[str, str]) -> None:
    for tkey, skey in mapping.items():
        target[tkey] = int(target.get(tkey, 0)) + int(source.get(skey, 0))
