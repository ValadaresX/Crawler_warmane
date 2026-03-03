from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urljoin, urlparse


@dataclass(frozen=True)
class PlayerRef:
    name: str
    realm: str
    class_hint: str | None = None

    @property
    def key(self) -> str:
        return f"{self.name}|{self.realm}"


def normalize_match_history_url(character_url: str) -> str:
    url = character_url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Character URL must start with http:// or https://")

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    match = re.search(r"^/character/([^/]+)/([^/]+)/(summary|profile|talents|statistics|match-history)$", path)
    if not match:
        raise ValueError(
            "URL must be a Warmane character page, e.g. "
            "https://armory.warmane.com/character/Narako/Blackrock/summary"
        )

    name = match.group(1)
    realm = match.group(2)
    return f"{parsed.scheme}://{parsed.netloc}/character/{name}/{realm}/match-history"


def parse_game_ids(match_history_html: str) -> list[str]:
    seen: set[str] = set()
    game_ids: list[str] = []

    for game_id in re.findall(r'data-gameid="(\d+)"', match_history_html):
        if game_id in seen:
            continue
        seen.add(game_id)
        game_ids.append(game_id)

    return game_ids


def discover_match_history_pages(match_history_html: str, current_url: str) -> list[str]:
    parsed_current = urlparse(current_url)
    current_path = parsed_current.path.rstrip("/")
    if not current_path.endswith("/match-history"):
        current_path = f"{current_path}/match-history"

    pages: list[str] = [f"{parsed_current.scheme}://{parsed_current.netloc}{current_path}"]
    seen = set(pages)

    for href in re.findall(r'href="([^"]+)"', match_history_html):
        if "match-history" not in href:
            continue
        absolute = urljoin(current_url, href)
        parsed = urlparse(absolute)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if normalized.rstrip("/") != current_path:
            continue
        full = absolute
        if full not in seen:
            seen.add(full)
            pages.append(full)

    return pages


def parse_players_from_match_details(payload: object) -> list[PlayerRef]:
    if not isinstance(payload, list):
        return []

    players: list[PlayerRef] = []
    seen: set[str] = set()

    for entry in payload:
        if not isinstance(entry, dict):
            continue

        name_raw = entry.get("charname")
        realm_raw = entry.get("realm")
        class_raw = entry.get("class")

        if not isinstance(name_raw, str) or not name_raw.strip():
            continue
        if not isinstance(realm_raw, str) or not realm_raw.strip():
            continue

        name = name_raw.strip()
        realm = realm_raw.strip()
        class_hint = class_raw.strip() if isinstance(class_raw, str) and class_raw.strip() else None
        key = f"{name}|{realm}"
        if key in seen:
            continue

        seen.add(key)
        players.append(PlayerRef(name=name, realm=realm, class_hint=class_hint))

    return players


def normalize_ladder_url(ladder_url: str) -> str:
    url = ladder_url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Ladder URL must start with http:// or https://")
    parsed = urlparse(url)
    if not parsed.path.startswith("/ladder/"):
        raise ValueError("URL must be a Warmane ladder URL, e.g. https://armory.warmane.com/ladder/SoloQ/1/80")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def parse_players_from_ladder_html(ladder_html: str) -> list[PlayerRef]:
    tbody_match = re.search(r'<tbody[^>]*id="data-table-list"[^>]*>(.*?)</tbody>', ladder_html, flags=re.S | re.I)
    body = tbody_match.group(1) if tbody_match else ladder_html

    players: list[PlayerRef] = []
    seen: set[str] = set()
    rows = re.findall(r"<tr>(.*?)</tr>", body, flags=re.S | re.I)
    for row in rows:
        m = re.search(r'href="/character/([^/"]+)/([^/"]+)/summary"', row, flags=re.I)
        if not m:
            continue
        name = unquote(m.group(1)).strip()
        realm = unquote(m.group(2)).strip()
        if not name or not realm:
            continue
        class_match = re.search(r"/images/icons/classes/(\d+)\.gif", row, flags=re.I)
        class_hint = class_match.group(1).strip() if class_match else None
        key = f"{name}|{realm}"
        if key in seen:
            continue
        seen.add(key)
        players.append(PlayerRef(name=name, realm=realm, class_hint=class_hint))
    return players


def build_summary_url(name: str, realm: str, host: str = "https://armory.warmane.com") -> str:
    encoded_name = quote(name, safe="")
    encoded_realm = quote(realm, safe="")
    return f"{host}/character/{encoded_name}/{encoded_realm}/summary"
