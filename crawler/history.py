"""Coleta de dados: history crawling (match-history → discovery de players)."""
from __future__ import annotations

import argparse
import random
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from crawler import base as crawler_base
from crawler.base import now_iso, progress_break_line, show_progress
from crawler.http import (
    adaptive_pause,
    maybe_random_visit,
    net_fetch_text,
    net_post_form_json,
)
from crawler.state import update_player_from_ref

from armory.match_history import (
    build_summary_url,
    discover_match_history_pages,
    parse_game_ids,
    parse_players_from_match_details,
)


@dataclass
class HistoryStats:
    root: str = ""
    pages_scanned: int = 0
    page_errors: int = 0
    matches_seen: int = 0
    new_match_ids: int = 0
    details_target: int = 0
    details_done: int = 0
    detail_errors: int = 0
    players_new: int = 0
    root_error: str = ""


def crawl_history(
    args: argparse.Namespace,
    state: dict[str, Any],
    processed_match_ids: set[str],
    player_key: str,
    player: dict[str, Any],
    runtime_heartbeat: Callable[[str, dict[str, Any], bool], None] | None = None,
) -> dict[str, int | str]:
    host = str(state.get("host") or "https://armory.warmane.com")
    name, realm = str(player["name"]), str(player["realm"])
    history_url = build_summary_url(name, realm, host=host).rsplit("/", 1)[0] + "/match-history"
    stats = HistoryStats(root=f"{name}@{realm}")
    progress_break_line()
    print(f"  History  {name}@{realm}")
    root_t0 = time.monotonic()
    root_max_s = max(0.0, float(getattr(args, "history_root_max_seconds", 0.0)))
    detail_err_streak_stop = max(0, int(getattr(args, "history_detail_error_streak_stop", 0)))

    def root_timed_out() -> bool:
        if root_max_s <= 0:
            return False
        return (time.monotonic() - root_t0) >= root_max_s

    try:
        adaptive_pause(args, state)
        first_html = net_fetch_text(args, state, history_url, timeout_seconds=args.timeout_seconds)
    except Exception as exc:
        stats.root_error = str(exc)[:220]
        stats.page_errors = 1
        player["history_scan_count"] = int(player.get("history_scan_count", 0)) + 1
        player["last_history_scan_utc"] = now_iso()
        return asdict(stats)

    pages = discover_match_history_pages(first_html, history_url)
    all_ids: list[str] = []
    seen: set[str] = set()
    pages_to_scan = pages[:]
    if args.max_history_pages_per_cycle > 0:
        pages_to_scan = pages[: args.max_history_pages_per_cycle]
    if len(pages_to_scan) > 2:
        head = pages_to_scan[:1]
        tail = pages_to_scan[1:]
        random.shuffle(tail)
        pages_to_scan = head + tail
    show_progress("history_pages", "pages", 0, len(pages_to_scan), "lendo paginas")
    for i, page in enumerate(pages_to_scan, start=1):
        if root_timed_out():
            stats.root_error = f"history_root_timeout_{int(root_max_s)}s"
            print(f"  History  timeout root>{root_max_s:.0f}s; encerrando root")
            break
        try:
            if i == 1:
                html = first_html
            else:
                adaptive_pause(args, state)
                html = net_fetch_text(args, state, page, timeout_seconds=args.timeout_seconds)
        except Exception:
            stats.page_errors += 1
            continue

        stats.pages_scanned += 1
        for mid in parse_game_ids(html):
            if mid in seen:
                continue
            seen.add(mid)
            all_ids.append(mid)
        if int(args.random_visit_every_pages) > 0 and i % int(args.random_visit_every_pages) == 0:
            maybe_random_visit(args, state, reason="history_pages")
        show_progress("history_pages", "pages", i, len(pages_to_scan), f"matches={len(all_ids)}")
        if runtime_heartbeat is not None:
            runtime_heartbeat("history_pages", asdict(stats), False)

    stats.matches_seen = len(all_ids)
    new_ids = [m for m in all_ids if m not in processed_match_ids]
    random.shuffle(new_ids)
    stats.new_match_ids = len(new_ids)
    if not new_ids:
        print("  matches    sem IDs novos neste root")
    work_ids = new_ids
    if args.max_matchinfo_per_cycle > 0:
        work_ids = new_ids[: args.max_matchinfo_per_cycle]
    stats.details_target = len(work_ids)
    if len(new_ids) > len(work_ids):
        print(f"  matches    limitando details: {len(work_ids)}/{len(new_ids)} neste ciclo")
    new_players = 0
    details_done = 0
    show_progress("history_matches", "matches", 0, len(work_ids), "coletando details")
    detail_err_streak = 0
    for i, mid in enumerate(work_ids, start=1):
        if crawler_base.STOP:
            break
        if root_timed_out():
            stats.root_error = f"history_root_timeout_{int(root_max_s)}s"
            print(f"  matches    timeout root>{root_max_s:.0f}s; interrompendo details")
            break
        if int(args.random_visit_every_matchinfos) > 0 and i % int(args.random_visit_every_matchinfos) == 0:
            maybe_random_visit(args, state, reason="matchinfo")
        adaptive_pause(args, state)
        try:
            payload = net_post_form_json(
                args,
                state,
                history_url,
                {"matchinfo": mid},
                timeout_seconds=int(args.matchinfo_timeout_seconds),
                max_wall_seconds=float(args.matchinfo_request_wall_timeout_seconds),
            )
        except Exception:
            stats.detail_errors += 1
            detail_err_streak += 1
            if detail_err_streak_stop > 0 and detail_err_streak >= detail_err_streak_stop:
                stats.root_error = f"history_detail_error_streak_{detail_err_streak}"
                print(f"  matches    muitos erros seguidos ({detail_err_streak}); abortando root")
                stats.details_done = details_done
                stats.players_new = new_players
                show_progress("history_matches", "matches", i, len(work_ids), f"players_novos={new_players}")
                if runtime_heartbeat is not None:
                    runtime_heartbeat("history_matches", asdict(stats), True)
                break
            stats.details_done = details_done
            stats.players_new = new_players
            show_progress("history_matches", "matches", i, len(work_ids), f"players_novos={new_players}")
            if runtime_heartbeat is not None:
                runtime_heartbeat("history_matches", asdict(stats), False)
            continue
        detail_err_streak = 0
        for ref in parse_players_from_match_details(payload):
            before = len(state["players"])
            update_player_from_ref(state, ref, mid)
            if len(state["players"]) > before:
                new_players += 1
        processed_match_ids.add(mid)
        details_done += 1
        stats.details_done = details_done
        stats.players_new = new_players
        show_progress("history_matches", "matches", i, len(work_ids), f"players_novos={new_players}")
        if runtime_heartbeat is not None:
            runtime_heartbeat("history_matches", asdict(stats), False)
    player["history_scan_count"] = int(player.get("history_scan_count", 0)) + 1
    player["last_history_scan_utc"] = now_iso()
    stats.details_done = details_done
    stats.players_new = new_players
    return asdict(stats)
