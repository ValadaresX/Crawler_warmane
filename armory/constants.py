from __future__ import annotations

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# UAs reais e modernos para rotação leve durante coleta.
USER_AGENT_POOL = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
        "Gecko/20100101 Firefox/135.0"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.3 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Mobile Safari/537.36"
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.3 Mobile/15E148 Safari/604.1"
    ),
]

# Perfis básicos para variar header-set sem paralelismo agressivo.
HTTP_HEADER_PROFILES: list[tuple[tuple[str, str], ...]] = [
    (
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Accept-Encoding", "gzip, deflate"),
        ("Connection", "keep-alive"),
        ("Upgrade-Insecure-Requests", "1"),
    ),
    (
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"),
        ("Accept-Encoding", "gzip, deflate"),
        ("Connection", "keep-alive"),
        ("Upgrade-Insecure-Requests", "1"),
    ),
    (
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-GB,en;q=0.9"),
        ("Accept-Encoding", "gzip, deflate"),
        ("Connection", "keep-alive"),
        ("Upgrade-Insecure-Requests", "1"),
    ),
]

GEARSCORE_SCALE = 1.8618

CHARACTER_CLASSES = [
    "Death Knight",
    "Warrior",
    "Paladin",
    "Hunter",
    "Rogue",
    "Priest",
    "Shaman",
    "Mage",
    "Warlock",
    "Druid",
]

ARMORY_LAYOUT_SLOT_ORDER: dict[str, list[int]] = {
    "item-left": [1, 2, 3, 15, 5, 4, 19, 9],
    "item-right": [10, 6, 7, 8, 11, 12, 13, 14],
    "item-bottom": [16, 17, 18],
}

FIXED_SLOT_EQUIP_LOC: dict[int, str] = {
    1: "INVTYPE_HEAD",
    2: "INVTYPE_NECK",
    3: "INVTYPE_SHOULDER",
    4: "INVTYPE_BODY",
    5: "INVTYPE_CHEST",
    6: "INVTYPE_WAIST",
    7: "INVTYPE_LEGS",
    8: "INVTYPE_FEET",
    9: "INVTYPE_WRIST",
    10: "INVTYPE_HAND",
    11: "INVTYPE_FINGER",
    12: "INVTYPE_FINGER",
    13: "INVTYPE_TRINKET",
    14: "INVTYPE_TRINKET",
    15: "INVTYPE_CLOAK",
    19: "INVTYPE_BODY",
}

GS_ITEM_TYPES: dict[str, dict[str, float | int | bool]] = {
    "INVTYPE_RELIC": {"SlotMOD": 0.3164, "ItemSlot": 18, "Enchantable": False},
    "INVTYPE_TRINKET": {"SlotMOD": 0.5625, "ItemSlot": 33, "Enchantable": False},
    "INVTYPE_2HWEAPON": {"SlotMOD": 2.0000, "ItemSlot": 16, "Enchantable": True},
    "INVTYPE_WEAPONMAINHAND": {"SlotMOD": 1.0000, "ItemSlot": 16, "Enchantable": True},
    "INVTYPE_WEAPONOFFHAND": {"SlotMOD": 1.0000, "ItemSlot": 17, "Enchantable": True},
    "INVTYPE_RANGED": {"SlotMOD": 0.3164, "ItemSlot": 18, "Enchantable": True},
    "INVTYPE_THROWN": {"SlotMOD": 0.3164, "ItemSlot": 18, "Enchantable": False},
    "INVTYPE_RANGEDRIGHT": {"SlotMOD": 0.3164, "ItemSlot": 18, "Enchantable": False},
    "INVTYPE_SHIELD": {"SlotMOD": 1.0000, "ItemSlot": 17, "Enchantable": True},
    "INVTYPE_WEAPON": {"SlotMOD": 1.0000, "ItemSlot": 36, "Enchantable": True},
    "INVTYPE_HOLDABLE": {"SlotMOD": 1.0000, "ItemSlot": 17, "Enchantable": False},
    "INVTYPE_HEAD": {"SlotMOD": 1.0000, "ItemSlot": 1, "Enchantable": True},
    "INVTYPE_NECK": {"SlotMOD": 0.5625, "ItemSlot": 2, "Enchantable": False},
    "INVTYPE_SHOULDER": {"SlotMOD": 0.7500, "ItemSlot": 3, "Enchantable": True},
    "INVTYPE_CHEST": {"SlotMOD": 1.0000, "ItemSlot": 5, "Enchantable": True},
    "INVTYPE_ROBE": {"SlotMOD": 1.0000, "ItemSlot": 5, "Enchantable": True},
    "INVTYPE_WAIST": {"SlotMOD": 0.7500, "ItemSlot": 6, "Enchantable": False},
    "INVTYPE_LEGS": {"SlotMOD": 1.0000, "ItemSlot": 7, "Enchantable": True},
    "INVTYPE_FEET": {"SlotMOD": 0.7500, "ItemSlot": 8, "Enchantable": True},
    "INVTYPE_WRIST": {"SlotMOD": 0.5625, "ItemSlot": 9, "Enchantable": True},
    "INVTYPE_HAND": {"SlotMOD": 0.7500, "ItemSlot": 10, "Enchantable": True},
    "INVTYPE_FINGER": {"SlotMOD": 0.5625, "ItemSlot": 31, "Enchantable": False},
    "INVTYPE_CLOAK": {"SlotMOD": 0.5625, "ItemSlot": 15, "Enchantable": True},
    "INVTYPE_BODY": {"SlotMOD": 0.0000, "ItemSlot": 4, "Enchantable": False},
}

GS_FORMULA: dict[str, dict[int, dict[str, float]]] = {
    "A": {
        4: {"A": 91.4500, "B": 0.6500},
        3: {"A": 81.3750, "B": 0.8125},
        2: {"A": 73.0000, "B": 1.0000},
    },
    "B": {
        4: {"A": 26.0000, "B": 1.2000},
        3: {"A": 0.7500, "B": 1.8000},
        2: {"A": 8.0000, "B": 2.0000},
        1: {"A": 0.0000, "B": 2.2500},
    },
}

# WotLK 3.3.5a class base HP on level 80 (player_class_stats)
CLASS_BASE_HP_80: dict[str, int] = {
    "WARRIOR": 8121,
    "PALADIN": 6934,
    "HUNTER": 7324,
    "ROGUE": 7604,
    "PRIEST": 6960,
    "DEATH KNIGHT": 8121,
    "SHAMAN": 6939,
    "MAGE": 6963,
    "WARLOCK": 7136,
    "DRUID": 7417,
}

# Mapeamento evowow inventorySlot.id → INVTYPE_* (fallback para metadados de item)
EVOWOW_INVSLOT_TO_INVTYPE: dict[int, str] = {
    1: "INVTYPE_HEAD",
    2: "INVTYPE_NECK",
    3: "INVTYPE_SHOULDER",
    4: "INVTYPE_BODY",
    5: "INVTYPE_CHEST",
    6: "INVTYPE_WAIST",
    7: "INVTYPE_LEGS",
    8: "INVTYPE_FEET",
    9: "INVTYPE_WRIST",
    10: "INVTYPE_HAND",
    11: "INVTYPE_FINGER",
    12: "INVTYPE_TRINKET",
    13: "INVTYPE_WEAPON",
    14: "INVTYPE_SHIELD",
    15: "INVTYPE_RANGED",
    16: "INVTYPE_CLOAK",
    17: "INVTYPE_2HWEAPON",
    20: "INVTYPE_ROBE",
    21: "INVTYPE_WEAPONMAINHAND",
    22: "INVTYPE_WEAPONOFFHAND",
    23: "INVTYPE_HOLDABLE",
    25: "INVTYPE_THROWN",
    26: "INVTYPE_RANGEDRIGHT",
    28: "INVTYPE_RELIC",
}
