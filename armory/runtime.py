"""Runtime state heartbeat and telemetry helpers for the adaptive crawler."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Any

from .fileio import write_json_atomic
from .constants import CHARACTER_CLASSES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_network_state(state: dict[str, Any]) -> dict[str, Any]:
    net = state.get("network")
    if not isinstance(net, dict):
        net = {}
        state["network"] = net
    stats = net.get("stats")
    if not isinstance(stats, dict):
        stats = {}
        net["stats"] = stats
    net.setdefault("delay_factor", 1.0)
    net.setdefault("consecutive_errors", 0)
    net.setdefault("last_error", None)
    net.setdefault("last_error_utc", None)
    stats.setdefault("ok", 0)
    stats.setdefault("err", 0)
    stats.setdefault("latency_ms_ema", None)
    return net


def ensure_telemetry_state(state: dict[str, Any]) -> dict[str, Any]:
    telemetry = state.get("telemetry")
    if not isinstance(telemetry, dict):
        telemetry = {}
        state["telemetry"] = telemetry
    cycles = telemetry.get("cycles")
    if not isinstance(cycles, list):
        cycles = []
        telemetry["cycles"] = cycles
    return telemetry


def append_cycle_telemetry(args: argparse.Namespace, state: dict[str, Any], cycle_metrics: dict[str, Any]) -> None:
    telemetry = ensure_telemetry_state(state)
    cycles = telemetry["cycles"]
    cycles.append(cycle_metrics)
    keep = max(10, int(args.telemetry_keep_cycles))
    if len(cycles) > keep:
        del cycles[:-keep]


def _class_counts_discovered(players: dict[str, Any]) -> dict[str, int]:
    canon = {"".join(c for c in k.lower() if c.isalpha()): k for k in CHARACTER_CLASSES}
    out = {k: 0 for k in CHARACTER_CLASSES}
    for row in players.values():
        if not isinstance(row, dict):
            continue
        token = "".join(c for c in str(row.get("class_hint_name") or "").lower() if c.isalpha())
        cls = canon.get(token)
        if cls:
            out[cls] += 1
    return out


def _class_counts_processed(processed_players: dict[str, Any]) -> dict[str, int]:
    canon = {"".join(c for c in k.lower() if c.isalpha()): k for k in CHARACTER_CLASSES}
    out = {k: 0 for k in CHARACTER_CLASSES}
    for row in processed_players.values():
        if not isinstance(row, dict):
            continue
        token = "".join(c for c in str(row.get("class") or "").lower() if c.isalpha())
        c = canon.get(token)
        if c:
            out[c] += 1
    return out


def maybe_write_runtime_state(
    args: argparse.Namespace,
    state: dict[str, Any],
    phase: str,
    stage: str,
    cycle_metrics: dict[str, Any] | None,
    timer: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    if args.dry_run or not bool(getattr(args, "runtime_state_enabled", True)):
        return

    interval_s = max(0.0, float(getattr(args, "runtime_state_interval_seconds", 2.0)))
    if interval_s <= 0.0 and not force:
        return

    now_mono = time.monotonic()
    next_due = float(timer.get("next_due", 0.0))
    if not force and now_mono < next_due:
        return
    timer["next_due"] = now_mono + max(interval_s, 0.25)

    metrics = cycle_metrics if isinstance(cycle_metrics, dict) else {}
    net = ensure_network_state(state)
    stats = net.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}
    players_map = state.get("players", {})
    if not isinstance(players_map, dict):
        players_map = {}
    processed_map = state.get("processed_players", {})
    if not isinstance(processed_map, dict):
        processed_map = {}
    failed_map = state.get("failed_players", {})
    if not isinstance(failed_map, dict):
        failed_map = {}

    dataset_total = len(processed_map)
    players_total = len(players_map)
    class_counts_cache = timer.get("class_counts")
    class_counts_processed_cache = timer.get("class_counts_processed")
    class_counts_cached_players_total = int(timer.get("class_counts_players_total", -1) or -1)
    class_counts_cached_dataset_total = int(timer.get("class_counts_dataset_total", -1) or -1)
    class_counts_last_calc = float(timer.get("class_counts_last_calc", 0.0) or 0.0)
    class_counts_refresh_seconds = max(
        0.25,
        float(getattr(args, "runtime_class_counts_refresh_seconds", 3.0)),
    )
    needs_class_recalc = (
        force
        or not isinstance(class_counts_cache, dict)
        or not isinstance(class_counts_processed_cache, dict)
        or class_counts_cached_players_total != players_total
        or class_counts_cached_dataset_total != dataset_total
        or (now_mono - class_counts_last_calc) >= class_counts_refresh_seconds
    )
    if needs_class_recalc:
        class_counts_cache = _class_counts_discovered(players_map)
        class_counts_processed_cache = _class_counts_processed(processed_map)
        timer["class_counts"] = dict(class_counts_cache)
        timer["class_counts_processed"] = dict(class_counts_processed_cache)
        timer["class_counts_players_total"] = players_total
        timer["class_counts_dataset_total"] = dataset_total
        timer["class_counts_last_calc"] = now_mono
    if not isinstance(class_counts_cache, dict):
        class_counts_cache = {klass: 0 for klass in CHARACTER_CLASSES}
    if not isinstance(class_counts_processed_cache, dict):
        class_counts_processed_cache = {klass: 0 for klass in CHARACTER_CLASSES}

    telemetry_last = {
        "phase": str(metrics.get("phase") or phase or "unknown"),
        "history_roots": int(metrics.get("history_roots", 0) or 0),
        "history_details_done": int(metrics.get("history_details_done", 0) or 0),
        "history_details_target": int(metrics.get("history_details_target", 0) or 0),
        "players_new": int(metrics.get("players_new", 0) or 0),
        "profiles_attempted": int(metrics.get("profiles_attempted", 0) or 0),
        "profiles_ok": int(metrics.get("profiles_ok", 0) or 0),
        "profiles_failed": int(metrics.get("profiles_failed", 0) or 0),
    }
    crawler_status = str(state.get("crawler_status", "running") or "running")
    from armory import __version__
    payload = {
        "schema": "adaptive_crawler_runtime_state.v1",
        "crawler_version": __version__,
        "updated_at_utc": _now_iso(),
        "cycle": int(state.get("cycle", 0) or 0),
        "phase": str(metrics.get("phase") or phase or "unknown"),
        "stage": str(stage or "runtime"),
        "crawler_status": crawler_status,
        "players_total": players_total,
        "dataset_total": dataset_total,
        "failed_total": len(failed_map),
        "delay_x": float(net.get("delay_factor", 1.0) or 1.0),
        "err_seq": int(net.get("consecutive_errors", 0) or 0),
        "lat_ema_ms": float(stats.get("latency_ms_ema", 0.0) or 0.0),
        "class_counts": {klass: int(class_counts_cache.get(klass, 0) or 0) for klass in CHARACTER_CLASSES},
        "class_counts_processed": {
            klass: int(class_counts_processed_cache.get(klass, 0) or 0)
            for klass in CHARACTER_CLASSES
        },
        "class_counts_source": "players_discovered",
        "runtime_state_interval_seconds": float(interval_s),
        "source_state_file": str(args.state_file),
        "source_dataset_json": str(args.dataset_json),
        "network": {
            "delay_factor": float(net.get("delay_factor", 1.0) or 1.0),
            "consecutive_errors": int(net.get("consecutive_errors", 0) or 0),
            "stats": {
                "latency_ms_ema": float(stats.get("latency_ms_ema", 0.0) or 0.0),
            },
        },
        "telemetry_last": telemetry_last,
        "rps": float(getattr(args, "http_rps", 0.0) or 0.0),
        "delay_min_seconds": float(getattr(args, "pause_min", 0.0) or 0.0),
        "delay_max_seconds": float(getattr(args, "pause_max", 0.0) or 0.0),
        "history_players_per_cycle": int(getattr(args, "history_players_per_cycle", 0) or 0),
        "profiles_per_cycle": int(getattr(args, "profiles_per_cycle", 0) or 0),
        "max_matchinfo_per_cycle": int(getattr(args, "max_matchinfo_per_cycle", 0) or 0),
    }
    try:
        write_json_atomic(args.runtime_state_file, payload)
        timer["last_error"] = ""
    except Exception as exc:
        msg = f"{type(exc).__name__}:{exc}"
        if timer.get("last_error") != msg:
            print(f"[warn] runtime-state heartbeat falhou: {exc}")
            timer["last_error"] = msg
