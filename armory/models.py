from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass(frozen=True)
class ArmoryItem:
    slot: int
    item_id: int
    enchant_id: int
    rel: str
    gem_ids: tuple[int, ...] = ()
    href: str = ""


@dataclass(frozen=True)
class CharacterProfile:
    name: str
    level: int
    race: str
    klass: str
    realm: str
    stamina: int
    specialization: str | None
    items: dict[int, ArmoryItem]
    resilience: int | None = None
    character_stats: dict[str, dict[str, str]] = field(default_factory=dict)
    guild: str | None = None
    professions: list[dict[str, object]] = field(default_factory=list)
    achievement_points: int | None = None
    total_kills: int | None = None
    kills_today: int | None = None


@dataclass(frozen=True)
class TalentPoint:
    spell_id: int
    current: int
    maximum: int


@dataclass(frozen=True)
class Glyph:
    spell_id: int
    name: str
    glyph_type: str  # "major" ou "minor"


@dataclass(frozen=True)
class TalentTree:
    name: str
    points: int
    talents: tuple[TalentPoint, ...] = ()


@dataclass(frozen=True)
class TalentData:
    spec_index: int  # 0 ou 1
    trees: tuple[TalentTree, ...] = ()
    glyphs: tuple[Glyph, ...] = ()


@dataclass(frozen=True)
class ItemMetadata:
    item_id: int
    quality: int
    item_level: int
    equip_loc: str


@dataclass(frozen=True)
class AnalysisResult:
    url: str
    name: str
    realm: str
    level: int
    race: str
    klass: str
    specialization: str | None
    stamina: int
    gear_score: int
    average_item_level: int
    estimated_hp: int
    scored_slots: list[int]
    missing_slots: list[int]
    resilience: int | None = None
    items: list[dict[str, object]] = field(default_factory=list)
    character_stats: dict[str, dict[str, str]] = field(default_factory=dict)
    guild: str | None = None
    professions: list[dict[str, object]] = field(default_factory=list)
    achievement_points: int | None = None
    total_kills: int | None = None
    kills_today: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "name": self.name,
            "realm": self.realm,
            "level": self.level,
            "race": self.race,
            "class": self.klass,
            "specialization": self.specialization,
            "stamina": self.stamina,
            "gear_score": self.gear_score,
            "average_item_level": self.average_item_level,
            "estimated_hp": self.estimated_hp,
            "resilience": self.resilience,
            "scored_slots": self.scored_slots,
            "missing_slots": self.missing_slots,
            "items": self.items,
            "character_stats": self.character_stats,
            "guild": self.guild,
            "professions": self.professions,
            "achievement_points": self.achievement_points,
            "total_kills": self.total_kills,
            "kills_today": self.kills_today,
        }
