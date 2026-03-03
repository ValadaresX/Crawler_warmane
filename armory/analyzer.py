from __future__ import annotations

from pathlib import Path
from typing import Any

from .parser import normalize_profile_url, parse_profile, parse_talents_page
from .gearscore import calculate_gearscore
from .health import estimate_max_hp
from .items import ItemMetadataStore
from .models import AnalysisResult, TalentData
from .network import fetch_text


def analyze_character(profile_url: str, cache_path: Path) -> AnalysisResult:
    url = normalize_profile_url(profile_url)
    profile_html = fetch_text(url)
    profile = parse_profile(profile_html)

    with ItemMetadataStore(cache_path=cache_path) as metadata_store:
        metadata_by_slot = {
            slot: metadata_store.get(item)
            for slot, item in sorted(profile.items.items())
            if slot not in (4, 19)
        }

    gear_score, average_item_level = calculate_gearscore(profile, metadata_by_slot)
    estimated_hp = estimate_max_hp(profile)

    scored_slots = sorted(slot for slot in profile.items if slot not in (4, 19))
    missing_slots = sorted(slot for slot in range(1, 19) if slot not in profile.items and slot != 4)
    items_out: list[dict[str, Any]] = []
    for slot, item in sorted(profile.items.items()):
        items_out.append({
            "slot": int(slot),
            "item_id": int(item.item_id),
            "enchant_id": int(item.enchant_id),
            "gem_ids": [int(g) for g in item.gem_ids],
            "href": str(item.href),
            "rel": str(item.rel),
        })

    return AnalysisResult(
        url=url,
        name=profile.name,
        realm=profile.realm,
        level=profile.level,
        race=profile.race,
        klass=profile.klass,
        specialization=profile.specialization,
        stamina=profile.stamina,
        gear_score=gear_score,
        average_item_level=average_item_level,
        estimated_hp=estimated_hp,
        scored_slots=scored_slots,
        missing_slots=missing_slots,
        resilience=profile.resilience,
        items=items_out,
        character_stats=profile.character_stats,
        guild=profile.guild,
        professions=profile.professions,
        achievement_points=profile.achievement_points,
        total_kills=profile.total_kills,
        kills_today=profile.kills_today,
    )


def fetch_talents(summary_url: str) -> list[TalentData]:
    """Busca e parseia a página /talents (dual-spec) a partir da URL do /summary.

    Retorna lista com 1 ou 2 specs. Lista vazia se falhar.
    """
    talents_url = summary_url.replace("/summary", "/talents")
    try:
        html = fetch_text(talents_url)
    except Exception:
        return []

    specs: list[TalentData] = []
    try:
        td0 = parse_talents_page(html, spec_index=0)
        if td0.trees:
            specs.append(td0)
    except Exception:
        pass

    try:
        td1 = parse_talents_page(html, spec_index=1)
        # Guard: se #spec-1 não existe, o parser faz fallback para soup inteiro
        # e retornaria árvores idênticas à spec 0 — filtrar duplicatas
        if td1.trees and (not specs or td1.trees != specs[0].trees):
            specs.append(td1)
    except Exception:
        pass

    return specs
