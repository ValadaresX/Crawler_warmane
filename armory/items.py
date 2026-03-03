from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from diskcache import Cache

from .constants import EVOWOW_INVSLOT_TO_INVTYPE, FIXED_SLOT_EQUIP_LOC
from .models import ArmoryItem, ItemMetadata
from .network import fetch_text


def _decode_js_single_quoted_string(value: str) -> str:
    chars: list[str] = []
    index = 0
    size = len(value)

    while index < size:
        char = value[index]
        if char != "\\":
            chars.append(char)
            index += 1
            continue

        index += 1
        if index >= size:
            chars.append("\\")
            break

        escaped = value[index]
        if escaped in {"\\", "'", '"', "/"}:
            chars.append(escaped)
        elif escaped == "n":
            chars.append("\n")
        elif escaped == "r":
            chars.append("\r")
        elif escaped == "t":
            chars.append("\t")
        elif escaped == "b":
            chars.append("\b")
        elif escaped == "f":
            chars.append("\f")
        elif escaped == "u" and index + 4 < size:
            hex_code = value[index + 1 : index + 5]
            if re.fullmatch(r"[0-9a-fA-F]{4}", hex_code):
                chars.append(chr(int(hex_code, 16)))
                index += 4
            else:
                chars.append("u")
        else:
            chars.append(escaped)

        index += 1

    return "".join(chars)


def _parse_js_single_quoted_field(raw_js: str, key: str) -> str | None:
    match = re.search(rf"{re.escape(key)}:\s*'((?:\\.|[^'])*)'", raw_js, flags=re.S)
    if not match:
        return None
    return _decode_js_single_quoted_string(match.group(1))


def _infer_weapon_equip_loc(slot: int, tooltip_html: str) -> str:
    tooltip_text = re.sub(r"<[^>]+>", " ", tooltip_html)
    tooltip_text = html.unescape(tooltip_text)
    tooltip_text = re.sub(r"\s+", " ", tooltip_text).strip().lower()

    if slot == 18:
        if "relic" in tooltip_text:
            return "INVTYPE_RELIC"
        if "thrown" in tooltip_text:
            return "INVTYPE_THROWN"
        if "wand" in tooltip_text:
            return "INVTYPE_RANGEDRIGHT"
        if "ranged" in tooltip_text:
            return "INVTYPE_RANGED"
        return "INVTYPE_RANGEDRIGHT"

    if "held in off-hand" in tooltip_text or "held in off hand" in tooltip_text:
        return "INVTYPE_HOLDABLE"
    if "shield" in tooltip_text and ("off hand" in tooltip_text or "off-hand" in tooltip_text):
        return "INVTYPE_SHIELD"
    if "two-hand" in tooltip_text or "two handed" in tooltip_text:
        return "INVTYPE_2HWEAPON"
    if "main hand" in tooltip_text:
        return "INVTYPE_WEAPONMAINHAND"
    if "off hand" in tooltip_text or "off-hand" in tooltip_text:
        return "INVTYPE_WEAPONOFFHAND"
    if "one-hand" in tooltip_text or "one handed" in tooltip_text:
        return "INVTYPE_WEAPON"

    return "INVTYPE_WEAPON" if slot == 16 else "INVTYPE_WEAPONOFFHAND"


class ItemMetadataStore:
    def __init__(self, cache_path: Path) -> None:
        cache_dir = self._resolve_cache_dir(cache_path)
        self._cache = Cache(str(cache_dir))

    @staticmethod
    def _resolve_cache_dir(cache_path: Path) -> Path:
        # Accepts either a directory path or a legacy JSON-file-like path.
        if cache_path.suffix:
            return cache_path.parent / cache_path.stem
        return cache_path

    def close(self) -> None:
        self._cache.close()

    def __enter__(self) -> "ItemMetadataStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _fetch_from_evowow(self, item: ArmoryItem) -> ItemMetadata | None:
        """Fallback: GET https://wotlk.evowow.com/?item={id}&xml (~1.5 KB XML)."""
        try:
            xml_text = fetch_text(f"https://wotlk.evowow.com/?item={item.item_id}&xml")
            root = ET.fromstring(xml_text)
            item_el = root.find(".//item")
            if item_el is None:
                return None
            level_el = item_el.find("level")
            quality_el = item_el.find("quality")
            inv_slot_el = item_el.find("inventorySlot")
            if level_el is None or quality_el is None or inv_slot_el is None:
                return None
            item_level = int(level_el.text or "0")
            quality = int(quality_el.get("id", "0"))
            inv_slot_id = int(inv_slot_el.get("id", "0"))
            equip_loc = FIXED_SLOT_EQUIP_LOC.get(item.slot)
            if not equip_loc:
                equip_loc = EVOWOW_INVSLOT_TO_INVTYPE.get(inv_slot_id, "INVTYPE_WEAPON")
            return ItemMetadata(
                item_id=item.item_id,
                quality=quality,
                item_level=item_level,
                equip_loc=equip_loc,
            )
        except Exception:
            return None

    def get(self, item: ArmoryItem) -> ItemMetadata:
        key = f"item:{item.item_id}"
        cached = self._cache.get(key)
        if cached:
            return ItemMetadata(
                item_id=item.item_id,
                quality=int(cached["quality"]),
                item_level=int(cached["item_level"]),
                equip_loc=str(cached["equip_loc"]),
            )

        try:
            raw_tooltip_data = fetch_text(f"https://wotlk.cavernoftime.com/item={item.item_id}&power=true")
            quality_match = re.search(r"quality:\s*(\d+)", raw_tooltip_data)
            if not quality_match:
                raise ValueError(f"Could not parse item quality for item {item.item_id}")
            quality = int(quality_match.group(1))

            tooltip_html = _parse_js_single_quoted_field(raw_tooltip_data, "tooltip_enus")
            if not tooltip_html:
                raise ValueError(f"Could not parse item tooltip for item {item.item_id}")

            level_match = re.search(r"Item Level (\d+)", tooltip_html, flags=re.IGNORECASE)
            if not level_match:
                raise ValueError(f"Could not parse item level for item {item.item_id}")
            item_level = int(level_match.group(1))

            equip_loc = FIXED_SLOT_EQUIP_LOC.get(item.slot)
            if not equip_loc:
                equip_loc = _infer_weapon_equip_loc(item.slot, tooltip_html)
        except Exception as primary_exc:
            # Fallback: tentar evowow XML
            fallback = self._fetch_from_evowow(item)
            if fallback is not None:
                self._cache.set(key, {
                    "quality": fallback.quality,
                    "item_level": fallback.item_level,
                    "equip_loc": fallback.equip_loc,
                })
                return fallback
            raise primary_exc

        metadata = ItemMetadata(
            item_id=item.item_id,
            quality=quality,
            item_level=item_level,
            equip_loc=equip_loc,
        )

        self._cache.set(key, {
            "quality": metadata.quality,
            "item_level": metadata.item_level,
            "equip_loc": metadata.equip_loc,
        })

        return metadata
