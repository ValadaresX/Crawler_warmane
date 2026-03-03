"""Coleta de dados: profile processing (análise completa de personagens)."""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from crawler import base as crawler_base
from crawler.base import (
    flatten_character_stats,
    iso_to_ts,
    latest_mid,
    now_iso,
    show_progress,
)
from crawler.http import (
    adaptive_pause,
    build_failure_record,
    classify_failure_kind,
    maybe_random_visit,
    net_analyze_character,
    net_fetch_json,
)

from armory.analyzer import fetch_talents
from armory.match_history import build_summary_url


@dataclass
class ProfileStats:
    candidates: int = 0
    chosen: int = 0
    attempted: int = 0
    ok: int = 0
    failed: int = 0
    skipped_failed_cooldown: int = 0
    api_triaged: int = 0
    fail_by_kind: dict[str, int] = field(default_factory=lambda: {"transient": 0, "policy": 0, "client": 0, "other": 0})


def _api_triage(
    args: argparse.Namespace,
    state: dict[str, Any],
    name: str,
    realm: str,
    host: str,
) -> dict | None:
    """GET /api/character/{name}/{realm}/summary. Retorna dict ou None (falha silenciosa)."""
    url = f"{host}/api/character/{name}/{realm}/summary"
    try:
        data = net_fetch_json(
            args, state, url,
            timeout_seconds=min(int(args.timeout_seconds), 15),
            max_wall_seconds=20.0,
        )
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def collect_profiles(
    args: argparse.Namespace,
    state: dict[str, Any],
    runtime_heartbeat: Callable[[str, dict[str, Any], bool], None] | None = None,
) -> dict[str, Any]:
    now_ts = time.time()
    stats = ProfileStats()
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    recollect_all = bool(args.recollect_all_processed)
    recollect_and_append = bool(getattr(args, "recollect_and_append", False))
    recollect_missing = bool(getattr(args, "recollect_missing_fields", False))
    recollect_batch = int(getattr(args, "recollect_batch_size", 10))

    missing_field_keys: set[str] = set()
    if recollect_missing:
        _enriched_fields = ("guild", "achievement_points", "total_kills", "professions_json")
        for mk, mp in state.get("processed_players", {}).items():
            if mk not in state["players"]:
                continue
            if all(mp.get(f) in (None, "", 0) for f in _enriched_fields):
                missing_field_keys.add(mk)
        if len(missing_field_keys) > recollect_batch:
            import random as _rnd
            missing_field_keys = set(_rnd.sample(sorted(missing_field_keys), recollect_batch))

    for k, p in state["players"].items():
        already_processed = k in state["processed_players"]
        is_missing_fields = k in missing_field_keys
        if recollect_and_append:
            pass
        elif is_missing_fields:
            pass
        elif recollect_all and not already_processed:
            continue
        elif already_processed and not recollect_all:
            continue
        if k in state["failed_players"] and args.skip_failed:
            f = state["failed_players"].get(k, {})
            next_retry_ts = iso_to_ts(f.get("next_retry_utc"))
            if next_retry_ts is not None and now_ts < next_retry_ts:
                stats.skipped_failed_cooldown += 1
                continue
        score = min(latest_mid(p) / 50_000_000.0, 1.5) * 0.2
        if already_processed and (recollect_all or recollect_and_append):
            old = state["processed_players"].get(k, {})
            ts = iso_to_ts(old.get("collected_at_utc"))
            if ts is not None:
                age_days = max(0.0, (time.time() - ts) / 86400.0)
                score += min(age_days, 90.0) * 0.02
            score += 0.15
        candidates.append((score, k, p))
    stats.candidates = len(candidates)
    if not candidates:
        print("  Profiles sem alvos elegiveis")
        return asdict(stats)
    candidates.sort(key=lambda x: x[0], reverse=True)
    n = args.profiles_per_cycle
    if n <= 0:
        n = len(candidates)
    if n <= 0:
        print("  Profiles sem lote neste ciclo")
        return asdict(stats)
    chosen = candidates[:n]
    stats.chosen = len(chosen)
    host = str(state.get("host") or "https://armory.warmane.com")
    ok = 0
    show_progress("profiles", "profiles", 0, len(chosen), "coletando")
    for i, (_, k, p) in enumerate(chosen, start=1):
        if crawler_base.STOP:
            break
        if int(args.random_visit_every_profiles) > 0 and i % int(args.random_visit_every_profiles) == 0:
            maybe_random_visit(args, state, reason="profiles")
        stats.attempted += 1
        name, realm = str(p["name"]), str(p["realm"])
        url = build_summary_url(name, realm, host=host)
        # ── Triagem via API JSON (economia ~30% de bandwidth) ──
        adaptive_pause(args, state)
        api_data = _api_triage(args, state, name, realm, host)
        if api_data is not None:
            api_level = str(api_data.get("level", ""))
            if bool(getattr(args, "only_level_80", True)) and api_level != "80":
                err = f"level_not_80_api ({api_level})"
                prev = state["failed_players"].get(k, {"fail_count": 0})
                state["failed_players"][k] = build_failure_record(args, prev, err)
                stats.failed += 1
                stats.api_triaged += 1
                stats.fail_by_kind["policy"] += 1
                show_progress("profiles", "profiles", i, len(chosen), f"ok={ok}")
                if runtime_heartbeat is not None:
                    runtime_heartbeat("profiles", asdict(stats), False)
                continue
            # Enriquecer player com dados da API
            api_class = str(api_data.get("class", "")).strip()
            if api_class and not p.get("class_hint_name"):
                p["class_hint_name"] = api_class
            api_guild = api_data.get("guild")
            if isinstance(api_guild, str) and api_guild.strip():
                p["api_guild"] = api_guild.strip()
        adaptive_pause(args, state)
        try:
            r = net_analyze_character(args, state, url)
            resilience = None
            try:
                resilience = int(r.resilience) if r.resilience is not None else None
            except Exception:
                resilience = None
            if bool(getattr(args, "only_level_80", True)) and int(getattr(r, "level", 0) or 0) != 80:
                err = f"level_not_80 ({int(getattr(r, 'level', 0) or 0)})"
                prev = state["failed_players"].get(k, {"fail_count": 0})
                state["failed_players"][k] = build_failure_record(args, prev, err)
                stats.failed += 1
                stats.fail_by_kind["policy"] += 1
                show_progress("profiles", "profiles", i, len(chosen), f"ok={ok}")
                if runtime_heartbeat is not None:
                    runtime_heartbeat("profiles", asdict(stats), False)
                continue
            stats_dict = r.character_stats if isinstance(r.character_stats, dict) else {}
            flat_stats = flatten_character_stats(stats_dict)
            items = r.items if isinstance(r.items, list) else []
            enchant_count = 0
            gem_count = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                try:
                    ench = int(it.get("enchant_id", 0) or 0)
                except Exception:
                    ench = 0
                if ench > 0:
                    enchant_count += 1
                gems = it.get("gem_ids", [])
                if isinstance(gems, list):
                    gem_count += sum(1 for g in gems if str(g).strip() not in {"", "0"})

            profs = r.professions if isinstance(r.professions, list) else []
            # ── Coleta de talentos (dual-spec) ──
            talents_json_str = ""
            try:
                adaptive_pause(args, state)
                td_list = fetch_talents(url)
                if td_list:
                    talents_data = []
                    for td in td_list:
                        spec_entry: dict[str, Any] = {
                            "spec_index": td.spec_index,
                            "trees": [
                                {"name": t.name, "points": t.points,
                                 "talents": [{"spell_id": tp.spell_id, "current": tp.current, "max": tp.maximum} for tp in t.talents]}
                                for t in td.trees
                            ],
                            "glyphs": [
                                {"spell_id": g.spell_id, "name": g.name, "type": g.glyph_type}
                                for g in td.glyphs
                            ],
                        }
                        talents_data.append(spec_entry)
                    talents_json_str = json.dumps(talents_data, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                pass
            state["processed_players"][k] = {
                "name": r.name, "realm": r.realm, "class": r.klass, "race": r.race, "level": r.level,
                "specialization": r.specialization or "", "stamina": r.stamina, "resilience": resilience, "estimated_hp": r.estimated_hp,
                "gear_score": r.gear_score, "average_item_level": r.average_item_level,
                "item_count": len(items), "enchant_count": enchant_count, "gem_count": gem_count,
                "melee_power": flat_stats.get("melee_power"), "melee_damage": flat_stats.get("melee_damage"),
                "spell_power": flat_stats.get("spell_power"), "spell_damage_bonus": flat_stats.get("spell_damage_bonus"),
                "ranged_damage": flat_stats.get("ranged_damage"),
                "armor": flat_stats.get("armor"), "dodge_pct": flat_stats.get("dodge_pct"),
                "parry_pct": flat_stats.get("parry_pct"), "block_pct": flat_stats.get("block_pct"),
                "crit_melee_pct": flat_stats.get("crit_melee_pct"), "crit_spell_pct": flat_stats.get("crit_spell_pct"),
                "hit_melee_pct": flat_stats.get("hit_melee_pct"), "hit_spell_pct": flat_stats.get("hit_spell_pct"),
                "melee_speed": flat_stats.get("melee_speed"), "melee_haste_pct": flat_stats.get("melee_haste_pct"),
                "spell_haste_pct": flat_stats.get("spell_haste_pct"),
                "guild": r.guild or "", "achievement_points": r.achievement_points,
                "total_kills": r.total_kills, "kills_today": r.kills_today,
                "professions_json": json.dumps(profs, ensure_ascii=False, separators=(",", ":")),
                "source_match_count": len(p.get("source_match_ids", [])),
                "source_match_ids": ",".join(p.get("source_match_ids", [])),
                "items_json": json.dumps(items, ensure_ascii=False, separators=(",", ":")),
                "character_stats_json": json.dumps(stats_dict, ensure_ascii=False, separators=(",", ":")),
                "talents_json": talents_json_str, "glyphs_json": "",
                "summary_url": url, "collected_at_utc": now_iso(),
            }
            state["failed_players"].pop(k, None)
            ok += 1
        except Exception as exc:
            err = str(exc)
            prev = state["failed_players"].get(k, {"fail_count": 0})
            state["failed_players"][k] = build_failure_record(args, prev, err)
            kind = classify_failure_kind(err)
            stats.failed += 1
            if kind not in stats.fail_by_kind:
                kind = "other"
            stats.fail_by_kind[kind] += 1
        show_progress("profiles", "profiles", i, len(chosen), f"ok={ok}")
        if runtime_heartbeat is not None:
            runtime_heartbeat("profiles", asdict(stats), False)
    stats.ok = ok
    return asdict(stats)
