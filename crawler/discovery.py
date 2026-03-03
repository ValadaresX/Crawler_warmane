"""Lógica de descoberta: contagem por classe, scoring, seleção de batch, seeding de ladder."""
from __future__ import annotations

import argparse
import random
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from crawler import base as crawler_base
from crawler.base import class_from_hint, key_of, norm_class, now_iso
from crawler.http import adaptive_pause, net_fetch_json, net_fetch_text
from crawler.state import ensure_player

from armory.constants import CHARACTER_CLASSES
from armory.match_history import (
    normalize_ladder_url,
    parse_players_from_ladder_html,
)


# ── Contagem ────────────────────────────────────────────────────────

def _count_by_class(
    items: dict[str, Any],
    class_key: str = "class",
    exclude_keys: set[str] | None = None,
) -> dict[str, int]:
    out = {k: 0 for k in CHARACTER_CLASSES}
    excl = exclude_keys or set()
    for key, row in items.items():
        if not isinstance(row, dict) or key in excl:
            continue
        c = norm_class(row.get(class_key))
        if c:
            out[c] += 1
    return out


def class_counts(processed_players: dict[str, Any]) -> dict[str, int]:
    return _count_by_class(processed_players, "class")


def class_counts_discovered(players: dict[str, Any]) -> dict[str, int]:
    return _count_by_class(players, "class_hint_name")


# ── Seleção de batch ────────────────────────────────────────────────

def choose_history_players_batch(
    state: dict[str, Any],
    cooldown_s: float,
    batch_size: int,
    selection_mode: str = "auto",
) -> list[tuple[str, dict[str, Any]]]:
    """Seleciona players para varredura de histórico."""
    if batch_size <= 0:
        return []
    now = time.time()

    w_discovery = {"auto": 2.0, "discovery": 3.0, "balanced": 1.5}.get(selection_mode, 2.0)
    w_recency = 1.0

    scored: list[tuple[float, str, dict[str, Any]]] = []
    for k, p in state["players"].items():
        if not isinstance(p, dict):
            continue

        source_count = len(p.get("source_match_ids", []))
        discovery_score = min(source_count / 10.0, 1.5) * w_discovery
        scans = int(p.get("history_scan_count", 0))
        recency_score = (0.4 / (1.0 + scans)) * w_recency
        score = discovery_score + recency_score

        ladder_rank = p.get("ladder_seed_rank")
        if isinstance(ladder_rank, int) and ladder_rank > 0:
            if scans == 0:
                score += 100.0 - min(ladder_rank, 100)
            else:
                score += max(0.2, 3.0 / float(ladder_rank))

        last = p.get("last_history_scan_utc")
        if last:
            try:
                age = now - datetime.fromisoformat(str(last)).timestamp()
                if age < cooldown_s:
                    continue
            except Exception:
                pass
        scored.append((score + random.random() * 0.02, k, p))
    if not scored:
        return []
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: min(max(batch_size * 3, 20), len(scored))]
    out: list[tuple[str, dict[str, Any]]] = []
    chosen: set[str] = set()
    for _, key, player in top:
        if key in chosen:
            continue
        chosen.add(key)
        out.append((key, player))
        if len(out) >= batch_size:
            break
    return out


# ── Seeding de ladder ──────────────────────────────────────────────

def seed_players_from_ladder(args: argparse.Namespace, state: dict[str, Any]) -> tuple[int, int]:
    ladder_url = str(args.ladder_seed_url or "").strip()
    if not ladder_url:
        return 0, 0
    url = normalize_ladder_url(ladder_url)
    parsed = urlparse(url)
    state["host"] = f"{parsed.scheme}://{parsed.netloc}"
    adaptive_pause(args, state)
    html = net_fetch_text(args, state, url, timeout_seconds=args.timeout_seconds)
    refs = parse_players_from_ladder_html(html)
    if args.ladder_seed_max_players > 0:
        refs = refs[: args.ladder_seed_max_players]

    added = 0
    refreshed = 0
    for rank, ref in enumerate(refs, start=1):
        key = key_of(ref.name, ref.realm)
        existed = key in state["players"]
        p = ensure_player(state, ref.name, ref.realm)
        hint = str(ref.class_hint or "").strip()
        if hint and not p.get("class_hint"):
            p["class_hint"] = hint
        hint_name = class_from_hint(hint)
        if hint_name:
            p["class_hint_name"] = hint_name
        prev_rank = p.get("ladder_seed_rank")
        if not isinstance(prev_rank, int) or rank < prev_rank:
            p["ladder_seed_rank"] = rank
        p["last_seen_utc"] = now_iso()
        if existed:
            refreshed += 1
        else:
            added += 1
    return added, refreshed


# ── Descoberta via guild roster ──────────────────────────────────

def discover_players_from_guilds(
    args: argparse.Namespace,
    state: dict[str, Any],
    max_guilds: int = 3,
) -> tuple[int, int]:
    """Descobre players via GET /api/guild/{name}/{realm}/members.

    Retorna (players_adicionados, guilds_processadas).
    """
    if max_guilds <= 0:
        return 0, 0

    host = str(state.get("host") or "https://armory.warmane.com").rstrip("/")
    fetched_guilds: set[str] = set(state.get("fetched_guilds", []))

    # Coletar guilds conhecidas de processed_players
    guild_candidates: dict[str, str] = {}  # guild_name → realm
    for _pk, pp in state.get("processed_players", {}).items():
        if not isinstance(pp, dict):
            continue
        guild = str(pp.get("guild") or "").strip()
        realm = str(pp.get("realm") or "").strip()
        if guild and realm:
            gkey = f"{guild}|{realm}"
            if gkey not in fetched_guilds:
                guild_candidates[gkey] = realm

    # Também coletar de api_guild nos players
    for _pk, p in state.get("players", {}).items():
        if not isinstance(p, dict):
            continue
        guild = str(p.get("api_guild") or "").strip()
        realm = str(p.get("realm") or "").strip()
        if guild and realm:
            gkey = f"{guild}|{realm}"
            if gkey not in fetched_guilds:
                guild_candidates[gkey] = realm

    if not guild_candidates:
        return 0, 0

    # Pegar até max_guilds em ordem determinística mas variada
    import random as _rnd
    candidate_list = sorted(guild_candidates.keys())
    _rnd.shuffle(candidate_list)
    to_fetch = candidate_list[:max_guilds]

    total_added = 0
    guilds_done = 0

    for gkey in to_fetch:
        if crawler_base.STOP:
            break
        guild_name, realm = gkey.rsplit("|", 1)
        url = f"{host}/api/guild/{guild_name}/{realm}/roster"
        adaptive_pause(args, state)
        try:
            data = net_fetch_json(
                args, state, url,
                timeout_seconds=min(int(args.timeout_seconds), 15),
                max_wall_seconds=20.0,
            )
        except Exception:
            fetched_guilds.add(gkey)
            guilds_done += 1
            continue

        if not isinstance(data, list):
            fetched_guilds.add(gkey)
            guilds_done += 1
            continue

        added = 0
        for member in data:
            if not isinstance(member, dict):
                continue
            mname = str(member.get("name") or "").strip()
            mrealm = str(member.get("realm") or realm).strip()
            mlevel = str(member.get("level") or "")
            if not mname or not mrealm:
                continue
            if mlevel != "80":
                continue
            mkey = key_of(mname, mrealm)
            if mkey in state["players"]:
                continue
            p = ensure_player(state, mname, mrealm)
            mclass = str(member.get("class") or "").strip()
            if mclass:
                p["class_hint_name"] = mclass
            p["last_seen_utc"] = now_iso()
            added += 1

        total_added += added
        fetched_guilds.add(gkey)
        guilds_done += 1

    state["fetched_guilds"] = sorted(fetched_guilds)
    return total_added, guilds_done
