from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, FeatureNotFound

from .constants import ARMORY_LAYOUT_SLOT_ORDER, CHARACTER_CLASSES
from .models import ArmoryItem, CharacterProfile, Glyph, TalentData, TalentPoint, TalentTree


def normalize_profile_url(url: str) -> str:
    normalized = url.strip()
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    return normalized


def _parse_level_line(level_line: str) -> tuple[int, str, str, str]:
    # Example: "Level 80 Tauren Warrior, Blackrock"
    match = re.search(r"Level\s+(\d+)\s+(.+?),\s*([^,]+)$", level_line)
    if not match:
        raise ValueError(f"Could not parse level/race/class line: {level_line!r}")

    level = int(match.group(1))
    race_plus_class = match.group(2).strip()
    realm = match.group(3).strip()

    race = ""
    klass = ""
    for class_name in sorted(CHARACTER_CLASSES, key=len, reverse=True):
        if race_plus_class.endswith(class_name):
            klass = class_name
            race = race_plus_class[: -len(class_name)].strip()
            break

    if not race or not klass:
        raise ValueError(f"Could not split race/class from line: {level_line!r}")

    return level, race, klass, realm


def _parse_stamina_from_html(raw_html: str) -> int:
    match = re.search(r"Stamina:\s*([0-9,]+)", raw_html, flags=re.IGNORECASE)
    if not match:
        raise ValueError("Could not find stamina value in profile.")
    return int(match.group(1).replace(",", ""))


def _parse_resilience_from_html(raw_html: str) -> int | None:
    patterns = (
        r"Resilience(?:\s*Rating)?\s*:\s*([0-9,]+)",
        r"Resilience\s*-\s*([0-9,]+)",
    )
    for pat in patterns:
        match = re.search(pat, raw_html, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _parse_item_id_from_href(href: str) -> int | None:
    match = re.search(r"item=(\d+)", href)
    return int(match.group(1)) if match else None


def _parse_enchant_from_rel(rel: str) -> int:
    match = re.search(r"(?:^|&)ench=(\d+)", rel)
    return int(match.group(1)) if match else 0


def _parse_gems_from_rel(rel: str) -> tuple[int, ...]:
    match = re.search(r"(?:^|&)gems=([0-9:]+)", rel)
    if not match:
        return ()
    gems_raw = str(match.group(1)).strip()
    if not gems_raw:
        return ()
    out: list[int] = []
    for token in gems_raw.split(":"):
        token = token.strip()
        if not token or token == "0":
            continue
        try:
            out.append(int(token))
        except Exception:
            continue
    return tuple(out)


def _parse_guild(soup: BeautifulSoup) -> str | None:
    guild_el = soup.select_one(".guild-name")
    if not guild_el:
        return None
    link = guild_el.find("a")
    if link:
        text = link.get_text(strip=True)
        return text if text else None
    text = guild_el.get_text(strip=True)
    return text if text and text != "\xa0" else None


def _parse_professions(soup: BeautifulSoup) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    h3_tags = soup.find_all("h3")
    for h3 in h3_tags:
        heading = h3.get_text(strip=True)
        if heading not in ("Professions", "Secondary Skills"):
            continue
        is_secondary = heading == "Secondary Skills"
        profskills_div = h3.find_next_sibling("div", class_="profskills")
        if not profskills_div:
            continue
        for stub in profskills_div.select(".stub"):
            text_div = stub.select_one(".text")
            if not text_div:
                continue
            name_text = ""
            for child in text_div.children:
                if hasattr(child, "name") and child.name:
                    break
                t = str(child).strip()
                if t:
                    name_text = t
                    break
            value_el = text_div.select_one(".value")
            current = 0
            maximum = 0
            if value_el:
                m = re.match(r"(\d+)\s*/\s*(\d+)", value_el.get_text(strip=True))
                if m:
                    current = int(m.group(1))
                    maximum = int(m.group(2))
            if name_text:
                result.append({
                    "name": name_text,
                    "current": current,
                    "max": maximum,
                    "secondary": is_secondary,
                })
    return result


def _parse_achievement_points(soup: BeautifulSoup) -> int | None:
    el = soup.select_one(".achievement-points")
    if not el:
        return None
    text = el.get_text(strip=True)
    m = re.search(r"(\d[\d,]*)", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _parse_pvp_basic(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    total_kills = None
    kills_today = None
    pvp_div = soup.select_one(".pvpbasic")
    if not pvp_div:
        return total_kills, kills_today
    for stub in pvp_div.select(".stub"):
        text_div = stub.select_one(".text")
        if not text_div:
            continue
        label = ""
        for child in text_div.children:
            if hasattr(child, "name") and child.name:
                break
            t = str(child).strip()
            if t:
                label = t
                break
        value_el = text_div.select_one(".value")
        if not value_el:
            continue
        raw = value_el.get_text(strip=True).replace(",", "")
        try:
            val = int(raw)
        except ValueError:
            continue
        if "total" in label.lower():
            total_kills = val
        elif "today" in label.lower():
            kills_today = val
    return total_kills, kills_today


def _extract_character_stats(soup: BeautifulSoup) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    stats_root = soup.select_one("div.character-stats")
    if not stats_root:
        return out

    for text_div in stats_root.select("div.stub div.text"):
        block = str(text_div)
        matches = re.findall(
            r"([A-Za-z ]+)<br\s*/?>\s*<span class=\"value\">\s*(.*?)\s*</span>",
            block,
            flags=re.IGNORECASE | re.S,
        )
        for raw_group, raw_payload in matches:
            group = re.sub(r"\s+", " ", str(raw_group)).strip()
            if not group:
                continue
            group_key = group.lower().replace(" ", "_")
            payload = html.unescape(str(raw_payload))
            lines = [
                re.sub(r"<[^>]+>", " ", line).strip()
                for line in re.split(r"<br\s*/?>", payload, flags=re.IGNORECASE)
            ]
            values: dict[str, str] = {}
            for line in lines:
                line = re.sub(r"\s+", " ", line).strip()
                if not line:
                    continue
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key_norm = re.sub(r"\s+", " ", key).strip().lower().replace(" ", "_")
                values[key_norm] = re.sub(r"\s+", " ", value).strip()
            if values:
                out[group_key] = values
    return out


def _extract_items(soup: BeautifulSoup) -> dict[int, ArmoryItem]:
    items: dict[int, ArmoryItem] = {}

    for group_class, slot_order in ARMORY_LAYOUT_SLOT_ORDER.items():
        group = soup.select_one(f".item-model .{group_class}")
        if not group:
            continue

        slot_divs = group.find_all("div", class_="item-slot", recursive=False)
        for index, slot_id in enumerate(slot_order):
            if index >= len(slot_divs):
                continue

            anchor = slot_divs[index].find("a", href=re.compile(r"item=\d+"))
            if not anchor:
                continue

            href = anchor.get("href", "")
            item_id = _parse_item_id_from_href(href)
            if not item_id:
                continue

            rel_raw = anchor.get("rel", "")
            rel_text = " ".join(rel_raw) if isinstance(rel_raw, list) else str(rel_raw)
            rel_text = html.unescape(rel_text)
            enchant_id = _parse_enchant_from_rel(rel_text)
            gem_ids = _parse_gems_from_rel(rel_text)
            items[slot_id] = ArmoryItem(
                slot=slot_id,
                item_id=item_id,
                enchant_id=enchant_id,
                rel=rel_text,
                gem_ids=gem_ids,
                href=href,
            )

    return items


def parse_profile(raw_html: str) -> CharacterProfile:
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(raw_html, "html.parser")

    name_element = soup.select_one("#character-sheet .information-left .name")
    if not name_element:
        raise ValueError("Could not find character name on profile page.")
    name = next(name_element.stripped_strings, "").strip()
    if not name:
        raise ValueError("Character name is empty on profile page.")

    line_element = soup.select_one("#character-sheet .level-race-class")
    if not line_element:
        raise ValueError("Could not find level/race/class line on profile page.")
    level, race, klass, realm = _parse_level_line(line_element.get_text(" ", strip=True))

    specialization = None
    specialization_element = soup.select_one(".specialization .value")
    if specialization_element:
        specialization = specialization_element.get_text(" ", strip=True)

    stamina = _parse_stamina_from_html(raw_html)
    resilience = _parse_resilience_from_html(raw_html)
    items = _extract_items(soup)
    character_stats = _extract_character_stats(soup)
    guild = _parse_guild(soup)
    professions = _parse_professions(soup)
    achievement_points = _parse_achievement_points(soup)
    total_kills, kills_today = _parse_pvp_basic(soup)

    return CharacterProfile(
        name=name,
        level=level,
        race=race,
        klass=klass,
        realm=realm,
        stamina=stamina,
        specialization=specialization,
        items=items,
        resilience=resilience,
        character_stats=character_stats,
        guild=guild,
        professions=professions,
        achievement_points=achievement_points,
        total_kills=total_kills,
        kills_today=kills_today,
    )


def parse_talents_page(raw_html: str, spec_index: int = 0) -> TalentData:
    """Extrai dados de talentos e glyphs da página /talents.

    Args:
        raw_html: HTML da página /character/{name}/{realm}/talents
        spec_index: 0 para spec primária, 1 para secundária
    """
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(raw_html, "html.parser")

    # Extrair árvores de talentos
    trees: list[TalentTree] = []
    # Cada spec tem seu container: div#spec-0, div#spec-1
    spec_container = soup.select_one(f"#spec-{spec_index}")
    if not spec_container:
        spec_container = soup  # fallback
    all_tree_divs = spec_container.select(".talent-tree")

    # Agrupar: cada talent-tree é seguida por talent-tree-info
    i = 0
    while i < len(all_tree_divs):
        tree_div = all_tree_divs[i]
        talents: list[TalentPoint] = []

        for anchor in tree_div.select("a.talent"):
            href = anchor.get("href", "")
            spell_match = re.search(r"spell=(\d+)", href)
            spell_id = int(spell_match.group(1)) if spell_match else 0

            points_div = anchor.select_one(".talent-points")
            current = 0
            maximum = 0
            if points_div:
                pt_match = re.match(r"(\d+)\s*/\s*(\d+)", points_div.get_text(strip=True))
                if pt_match:
                    current = int(pt_match.group(1))
                    maximum = int(pt_match.group(2))

            if spell_id:
                talents.append(TalentPoint(spell_id=spell_id, current=current, maximum=maximum))

        # Extrair nome e total da tree-info
        info_div = tree_div.find_next_sibling("div", class_="talent-tree-info")
        if not info_div:
            info_div = tree_div.select_one(".talent-tree-info")
        tree_name = ""
        tree_points = 0
        if info_div:
            spans = info_div.find_all("span")
            if len(spans) >= 2:
                tree_name = spans[0].get_text(strip=True)
                try:
                    tree_points = int(spans[1].get_text(strip=True))
                except ValueError:
                    tree_points = sum(t.current for t in talents)
            elif len(spans) == 1:
                tree_name = spans[0].get_text(strip=True)
                tree_points = sum(t.current for t in talents)

        if talents or tree_name:
            trees.append(TalentTree(
                name=tree_name,
                points=tree_points,
                talents=tuple(talents),
            ))
        i += 1

    # Extrair glyphs
    glyphs: list[Glyph] = []
    glyph_containers = soup.select(f'[data-glyphs="{spec_index}"]')
    if not glyph_containers:
        glyph_containers = soup.select('[data-glyphs="0"]')
    for container in glyph_containers[:1]:  # só a primeira para evitar duplicatas
        for glyph_div in container.select(".glyph"):
            classes = glyph_div.get("class", [])
            glyph_type = "major" if "major" in classes else "minor"
            anchor = glyph_div.find("a")
            if not anchor:
                continue
            glyph_name = anchor.get_text(strip=True)
            href = anchor.get("href", "")
            spell_match = re.search(r"spell=(\d+)", href)
            spell_id = int(spell_match.group(1)) if spell_match else 0
            if spell_id and glyph_name:
                glyphs.append(Glyph(
                    spell_id=spell_id,
                    name=glyph_name,
                    glyph_type=glyph_type,
                ))

    return TalentData(
        spec_index=spec_index,
        trees=tuple(trees),
        glyphs=tuple(glyphs),
    )
