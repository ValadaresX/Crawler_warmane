"""Fundação do crawler: globals, constantes, signal handling, utilitários puros."""
from __future__ import annotations

import random
import re
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

from armory.constants import CHARACTER_CLASSES

# ── Globals mutáveis ────────────────────────────────────────────────
STOP = False

PROGRESS_CACHE: dict[str, int] = {}
PROGRESS_MODE = "line"
PROGRESS_IS_TTY = bool(getattr(sys.stdout, "isatty", lambda: False)())
PROGRESS_LINE_STEP_PCT = 100

# WotLK class ids on Warmane payloads:
# 1 Warrior, 2 Paladin, 3 Hunter, 4 Rogue, 5 Priest, 6 Death Knight, 7 Shaman, 8 Mage, 9 Warlock, 11 Druid
CLASS_ID_TO_NAME = {
    "1": "Warrior",
    "2": "Paladin",
    "3": "Hunter",
    "4": "Rogue",
    "5": "Priest",
    "6": "Death Knight",
    "7": "Shaman",
    "8": "Mage",
    "9": "Warlock",
    "11": "Druid",
}
CLASS_CANON = {"".join(c for c in k.lower() if c.isalpha()): k for k in CHARACTER_CLASSES}


# ── Progresso ───────────────────────────────────────────────────────

def progress_bar(current: int, total: int, width: int = 24) -> str:
    total_safe = max(total, 1)
    ratio = min(max(current / total_safe, 0.0), 1.0)
    fill = int(width * ratio)
    return "[" + ("#" * fill) + ("-" * (width - fill)) + "]"


def configure_progress_mode(mode: str) -> None:
    global PROGRESS_MODE
    mode = str(mode or "line").strip().lower()
    if mode == "auto":
        PROGRESS_MODE = "inline" if PROGRESS_IS_TTY else "line"
    elif mode in {"inline", "line"}:
        PROGRESS_MODE = mode
    else:
        PROGRESS_MODE = "line"


def show_progress(key: str, label: str, current: int, total: int, detail: str = "") -> None:
    pct = int((current * 100) / max(total, 1))
    last = PROGRESS_CACHE.get(key, -1)
    if current not in (0, total) and pct == last:
        return
    PROGRESS_CACHE[key] = pct
    bar = progress_bar(current, total)
    msg = f"  {label:<10} {bar} {current:>4}/{total:<4} {detail}".rstrip()
    if PROGRESS_MODE == "inline":
        end = "\n" if current >= total else ""
        print("\r\033[2K" + msg, end=end, flush=True)
        return

    # Modo estável para Raspberry/logs: em linhas, sem carriage return.
    step_pct = max(1, int(PROGRESS_LINE_STEP_PCT))
    if current in (0, total) or pct % step_pct == 0:
        print(msg, flush=True)


def progress_break_line() -> None:
    if PROGRESS_MODE == "inline":
        print("", flush=True)


def cycle_header(cycle: int, players: int, dataset: int, phase: str) -> None:
    print(f"\n=== Ciclo {cycle} ===")
    print(f"  Estado   players={players} dataset={dataset}")
    print(f"  Fase     {phase}")


# ── Signal handling ─────────────────────────────────────────────────

def on_signal(signum: int, _frame: Any) -> None:
    global STOP
    already = STOP
    STOP = True
    if not already:
        print(f"\n[warn] sinal recebido ({signum}); finalizando...", flush=True)


def setup_signals() -> None:
    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)


# ── Utilitários puros ──────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def key_of(name: str, realm: str) -> str:
    return f"{name}|{realm}"


def class_from_hint(hint: Any) -> str | None:
    v = str(hint or "").strip()
    if not v:
        return None
    if v in CLASS_ID_TO_NAME:
        return CLASS_ID_TO_NAME[v]
    return CLASS_CANON.get("".join(c for c in v.lower() if c.isalpha()))


def norm_class(v: Any) -> str | None:
    token = "".join(c for c in str(v or "").lower() if c.isalpha())
    return CLASS_CANON.get(token)


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace(",", ".")
    pct = text.endswith("%")
    if pct:
        text = text[:-1].strip()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def flatten_character_stats(stats: dict[str, dict[str, str]]) -> dict[str, float | None]:
    def get_value(group: str, key: str) -> float | None:
        return _to_float(stats.get(group, {}).get(key))

    return {
        "melee_power": get_value("melee", "power"),
        "melee_damage": stats.get("melee", {}).get("damage"),
        "spell_power": get_value("spell", "power"),
        "spell_damage_bonus": get_value("spell", "healing"),
        "ranged_damage": stats.get("ranged", {}).get("damage"),
        "armor": get_value("defense", "armor"),
        "dodge_pct": get_value("defense", "dodge"),
        "parry_pct": get_value("defense", "parry"),
        "block_pct": get_value("defense", "block"),
        "crit_melee_pct": get_value("melee", "critical"),
        "crit_spell_pct": get_value("spell", "critical"),
        "hit_melee_pct": get_value("melee", "hit_rating"),
        "hit_spell_pct": get_value("spell", "hit_rating"),
        "melee_speed": get_value("melee", "speed"),
        "melee_haste_pct": get_value("melee", "haste"),
        "spell_haste_pct": get_value("spell", "haste"),
        "resilience": get_value("defense", "resilience"),
    }


def pause(min_s: float, max_s: float) -> None:
    if max_s <= 0:
        return
    t = random.uniform(min_s, max_s)
    if t > 0:
        time.sleep(t)


def iso_to_ts(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


def latest_mid(player: dict[str, Any]) -> int:
    best = 0
    for m in player.get("source_match_ids", []):
        try:
            best = max(best, int(str(m)))
        except Exception:
            pass
    return best
