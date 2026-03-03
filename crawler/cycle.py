"""Corpo do ciclo principal do crawler."""
from __future__ import annotations

import argparse
import time
from typing import Any, Callable

from crawler import base as crawler_base
from crawler.base import cycle_header, now_iso, show_progress
from crawler.history import crawl_history
from crawler.profiles import collect_profiles
from crawler.discovery import choose_history_players_batch, discover_players_from_guilds
from crawler.http import adaptive_pause, is_block_detected, maybe_random_visit
from crawler.state import _accum_metrics, _HISTORY_METRIC_MAP, _PROFILE_METRIC_MAP, save_all

from armory.runtime import (
    append_cycle_telemetry,
    ensure_network_state,
)


def _run_cycle(
    args: argparse.Namespace,
    state: dict[str, Any],
    processed_match_ids: set[str],
    last_new_players_ts: float,
    runtime: dict[str, Any],
    emit_runtime: Callable[..., None],
) -> tuple[bool, float]:
    """Execute one crawler cycle.

    Returns ``(should_stop, last_new_players_ts)``.
    *should_stop* is ``True`` when the loop must break (block, idle, target,
    once, etc.); ``False`` means continue to the next cycle.
    """
    state["cycle"] = int(state.get("cycle", 0)) + 1
    cycle = int(state["cycle"])
    cycle_t0 = time.monotonic()
    cycle_max_s = max(0.0, float(getattr(args, "cycle_max_seconds", 0.0)))

    if args.phase == "discover":
        run_history, run_convert, phase = True, False, "discover"
    elif args.phase == "convert":
        run_history, run_convert, phase = False, True, "convert"
    else:  # auto ou hybrid
        run_history, run_convert, phase = True, True, "hybrid"

    cycle_header(
        cycle=cycle,
        players=len(state["players"]),
        dataset=len(state["processed_players"]),
        phase=phase,
    )
    net = ensure_network_state(state)
    ema = net.get("stats", {}).get("latency_ms_ema")
    ema_txt = "-" if ema is None else f"{float(ema):.0f}ms"
    print(
        f"  Rede     delay_x={float(net.get('delay_factor', 1.0)):.2f} "
        f"err_seq={int(net.get('consecutive_errors', 0))} lat_ema={ema_txt}"
    )
    maybe_random_visit(args, state, reason="cycle")

    new_matches = 0
    new_players = 0
    new_profiles = 0
    cycle_metrics: dict[str, Any] = {
        "cycle": cycle,
        "phase": phase,
        "at_utc": now_iso(),
        "history_roots": 0,
        "history_pages_ok": 0,
        "history_page_errors": 0,
        "history_matches_seen": 0,
        "history_new_match_ids": 0,
        "history_details_target": 0,
        "history_details_done": 0,
        "history_detail_errors": 0,
        "players_new": 0,
        "profiles_candidates": 0,
        "profiles_chosen": 0,
        "profiles_attempted": 0,
        "profiles_ok": 0,
        "profiles_failed": 0,
        "profiles_skipped_cooldown": 0,
        "profiles_fail_by_kind": {},
        "net_delay_factor": float(net.get("delay_factor", 1.0)),
        "net_err_seq": int(net.get("consecutive_errors", 0)),
        "net_latency_ema_ms": None if ema is None else float(ema),
    }
    runtime["phase"] = phase
    runtime["cycle_metrics"] = cycle_metrics
    emit_runtime("cycle_start", force=True)
    if run_history:
        picks = choose_history_players_batch(
            state=state,
            cooldown_s=args.history_cooldown_seconds,
            batch_size=args.history_players_per_cycle,
            selection_mode=getattr(args, "history_selection_mode", "auto"),
        )
        if not picks:
            print("  History  sem candidato")
            if not run_convert:
                print("  History  aguardando cooldown...")
                time.sleep(2.0)
                return (False, last_new_players_ts)
            print("  History  sem candidato; seguindo para profiles")
        print(f"  History  roots={len(picks)} neste ciclo")
        cycle_metrics["history_roots"] = len(picks)
        if picks:
            show_progress("history_roots", "roots", 0, len(picks), "processando match-history")
            for i, (pkey, player) in enumerate(picks, start=1):
                if cycle_max_s > 0 and (time.monotonic() - cycle_t0) >= cycle_max_s:
                    print(f"  Cycle    timeout>{cycle_max_s:.0f}s durante history; finalizando ciclo")
                    break
                root_stats = crawl_history(
                    args,
                    state,
                    processed_match_ids,
                    pkey,
                    player,
                    runtime_heartbeat=lambda stage, partial, force=False: emit_runtime(stage, partial, force),
                )
                new_matches += int(root_stats.get("details_done", 0))
                new_players += int(root_stats.get("players_new", 0))
                _accum_metrics(cycle_metrics, root_stats, _HISTORY_METRIC_MAP)
                show_progress("history_roots", "roots", i, len(picks), f"matches+={new_matches} players+={new_players}")
                emit_runtime("history_roots")
                if crawler_base.STOP:
                    break
    else:
        print("  History  pausado (fase convert)")

    if run_convert:
        if cycle_max_s > 0 and (time.monotonic() - cycle_t0) >= cycle_max_s:
            print(f"  Cycle    timeout>{cycle_max_s:.0f}s antes de profiles; pulando convert neste ciclo")
            profile_stats = {
                "ok": 0,
                "candidates": 0,
                "chosen": 0,
                "attempted": 0,
                "failed": 0,
                "skipped_failed_cooldown": 0,
                "fail_by_kind": {},
            }
        else:
            profile_stats = collect_profiles(
                args=args,
                state=state,
                runtime_heartbeat=lambda stage, partial, force=False: emit_runtime(stage, partial, force),
            )
        new_profiles = int(profile_stats.get("ok", 0))
        _accum_metrics(cycle_metrics, profile_stats, _PROFILE_METRIC_MAP)
        cycle_metrics["profiles_fail_by_kind"] = dict(profile_stats.get("fail_by_kind", {}))
    else:
        print("  Profiles pausado (fase discover)")
    # ── Guild discovery ──
    guild_max = int(getattr(args, "guild_discovery_max_per_cycle", 3))
    if run_convert and not crawler_base.STOP and guild_max > 0:
        guild_add, guild_done = discover_players_from_guilds(args, state, max_guilds=guild_max)
        if guild_add > 0:
            print(f"  Guilds   add={guild_add} guilds={guild_done}")
        new_players += guild_add
    cycle_metrics["players_new"] = new_players
    if new_matches == 0 and new_profiles == 0:
        state["no_progress_cycles"] = int(state.get("no_progress_cycles", 0)) + 1
    else:
        state["no_progress_cycles"] = 0

    print(
        "  Funil    "
        f"roots={int(cycle_metrics['history_roots'])} "
        f"pages={int(cycle_metrics['history_pages_ok'])}/{int(cycle_metrics['history_page_errors'])} "
        f"matches={int(cycle_metrics['history_matches_seen'])} "
        f"details={int(cycle_metrics['history_details_done'])}/{int(cycle_metrics['history_details_target'])} "
        f"d_err={int(cycle_metrics['history_detail_errors'])} "
        f"players_new={int(cycle_metrics['players_new'])}"
    )
    print(
        "  Funil    "
        f"prof cand={int(cycle_metrics['profiles_candidates'])} "
        f"pick={int(cycle_metrics['profiles_chosen'])} "
        f"try={int(cycle_metrics['profiles_attempted'])} "
        f"ok={int(cycle_metrics['profiles_ok'])} "
        f"fail={int(cycle_metrics['profiles_failed'])} "
        f"cd_skip={int(cycle_metrics['profiles_skipped_cooldown'])}"
    )
    net_end = ensure_network_state(state)
    cycle_metrics["net_delay_factor_end"] = float(net_end.get("delay_factor", 1.0))
    cycle_metrics["net_err_seq_end"] = int(net_end.get("consecutive_errors", 0))

    emit_runtime("cycle_end", force=True)
    append_cycle_telemetry(args, state, cycle_metrics)
    save_all(args, state, processed_match_ids)
    emit_runtime("checkpoint_saved", force=True)
    print(
        f"  Resultado matches+={new_matches} players+={new_players} "
        f"profiles+={new_profiles} no_progress={state['no_progress_cycles']}"
    )
    if new_players > 0:
        last_new_players_ts = time.monotonic()
    idle_s = max(0.0, time.monotonic() - last_new_players_ts)
    idle_limit_s = max(0, int(getattr(args, "idle_stop_seconds", 60)))
    print(f"  Stop     idle_sem_novos={idle_s:.1f}s limite={idle_limit_s}s")

    if bool(getattr(args, "stop_on_block_detected", True)) and is_block_detected(args, state):
        net_now = ensure_network_state(state)
        print(
            f"[done] bloqueio detectado (err_seq={int(net_now.get('consecutive_errors', 0))} "
            f"delay_x={float(net_now.get('delay_factor', 1.0)):.2f})."
        )
        return (True, last_new_players_ts)

    if idle_limit_s > 0 and idle_s >= float(idle_limit_s):
        print(f"[done] sem novos players por {idle_s:.1f}s (limite={idle_limit_s}s).")
        return (True, last_new_players_ts)

    if args.once:
        print("[done] ciclo único concluído.")
        return (True, last_new_players_ts)
    return (False, last_new_players_ts)
