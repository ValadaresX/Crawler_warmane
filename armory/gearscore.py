from __future__ import annotations

import math

from .constants import GEARSCORE_SCALE, GS_FORMULA, GS_ITEM_TYPES
from .models import ArmoryItem, CharacterProfile, ItemMetadata


def _enchant_factor(equip_loc: str, enchant_id: int) -> float:
    item_type = GS_ITEM_TYPES.get(equip_loc)
    if not item_type:
        return 1.0
    if enchant_id != 0 or not bool(item_type["Enchantable"]):
        return 1.0

    slot_mod = float(item_type["SlotMOD"])
    percent = math.floor((-2 * slot_mod) * 100) / 100
    return 1 + (percent / 100)


def _item_score(item: ArmoryItem, metadata: ItemMetadata) -> tuple[int, int]:
    quality_scale = 1.0
    rarity = metadata.quality
    item_level = float(metadata.item_level)

    if rarity == 5:
        quality_scale = 1.3
        rarity = 4
    elif rarity in (0, 1):
        quality_scale = 0.005
        rarity = 2

    if rarity == 7:
        rarity = 3
        item_level = 187.05

    item_type = GS_ITEM_TYPES.get(metadata.equip_loc)
    if not item_type or not (2 <= rarity <= 4):
        return -1, int(item_level)

    formula_set = GS_FORMULA["A"] if item_level > 120 else GS_FORMULA["B"]
    formula = formula_set.get(rarity)
    if not formula:
        return -1, int(item_level)

    base_score = ((item_level - formula["A"]) / formula["B"]) * float(item_type["SlotMOD"])
    score = math.floor(base_score * GEARSCORE_SCALE * quality_scale)
    score = max(score, 0)
    score = math.floor(score * _enchant_factor(metadata.equip_loc, item.enchant_id))

    average_item_level = 0 if item_level == 187.05 else int(item_level)
    return score, average_item_level


def calculate_gearscore(profile: CharacterProfile, metadata_by_slot: dict[int, ItemMetadata]) -> tuple[int, int]:
    player_class = profile.klass.upper()
    gear_score = 0.0
    item_count = 0
    item_level_total = 0
    titan_grip_factor = 1.0

    offhand_item = profile.items.get(17)
    mainhand_item = profile.items.get(16)

    if mainhand_item and offhand_item and metadata_by_slot[16].equip_loc == "INVTYPE_2HWEAPON":
        titan_grip_factor = 0.5
    if offhand_item and metadata_by_slot[17].equip_loc == "INVTYPE_2HWEAPON":
        titan_grip_factor = 0.5

    if offhand_item:
        offhand_score, offhand_level = _item_score(offhand_item, metadata_by_slot[17])
        if player_class == "HUNTER":
            offhand_score *= 0.3164
        gear_score += offhand_score * titan_grip_factor
        item_count += 1
        item_level_total += offhand_level

    for slot in range(1, 19):
        if slot in (4, 17):
            continue

        item = profile.items.get(slot)
        if not item:
            continue

        item_score, item_level = _item_score(item, metadata_by_slot[slot])
        if slot == 16 and player_class == "HUNTER":
            item_score *= 0.3164
        if slot == 18 and player_class == "HUNTER":
            item_score *= 5.3224
        if slot == 16:
            item_score *= titan_grip_factor

        gear_score += item_score
        item_count += 1
        item_level_total += item_level

    average_item_level = math.floor(item_level_total / item_count) if item_count else 0
    return math.floor(gear_score), average_item_level
