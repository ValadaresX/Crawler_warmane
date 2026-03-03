#!/usr/bin/env python3
"""Entry point do crawler adaptativo em grafo — orquestração, IPC, run(), main()."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from crawler import base as crawler_base
from crawler.base import class_from_hint, configure_progress_mode, now_iso, setup_signals
from crawler.cli import build_parser, parse_seed
from crawler.cycle import _run_cycle
from crawler.discovery import seed_players_from_ladder
from crawler.state import default_state, ensure_player, save_all

from armory.fileio import read_json
from armory.match_history import normalize_ladder_url
from armory.network import configure_http
from armory.runtime import (
    ensure_network_state,
    ensure_telemetry_state,
    maybe_write_runtime_state,
)

# ── Re-exports para compatibilidade com testes ──────────────────────
# Os testes importam via importlib e acessam mod.<symbol> diretamente.
from crawler.cli import (  # noqa: F401
    _positive_int,
    _nonneg_int,
    _positive_float,
    _nonneg_float,
    _ratio_float,
    _unit_float,
    _decay_float,
    _growth_float,
    _min10_int,
)

# Re-export dataclasses usadas externamente
from crawler.history import HistoryStats  # noqa: F401
from crawler.profiles import ProfileStats  # noqa: F401

# ── IPC: mapeamento de config TUI → args ───────────────────────────

_TUI_CONFIG_MAP: dict[str, tuple[str, type]] = {
    # Coleta
    "history_players_per_cycle": ("history_players_per_cycle", int),
    "profiles_per_cycle": ("profiles_per_cycle", int),
    "max_matchinfo_per_cycle": ("max_matchinfo_per_cycle", int),
    "phase": ("phase", str),
    "history_selection_mode": ("history_selection_mode", str),
    # Limites
    "cycle_max_seconds": ("cycle_max_seconds", float),
    "history_cooldown_seconds": ("history_cooldown_seconds", float),
    "history_root_max_seconds": ("history_root_max_seconds", float),
    "idle_stop_seconds": ("idle_stop_seconds", int),
    "ladder_seed_max_players": ("ladder_seed_max_players", int),
    # Filtros
    "only_level_80": ("only_level_80", bool),
    # Funcionalidades
    "adaptive_delay": ("adaptive_delay", bool),
    "recollect_missing_fields": ("recollect_missing_fields", bool),
}


# ── IPC helper ──────────────────────────────────────────────────────

def _ipc_wait_for_command(
    cmd_path: Path,
    emit_runtime: Any,
    accepted: tuple[str, ...] = ("start", "cancel"),
) -> str:
    """Bloqueia até receber um comando aceito via IPC. Retorna o nome do comando."""
    while not crawler_base.STOP:
        time.sleep(2)
        emit_runtime("paused", force=True)
        if cmd_path.exists():
            try:
                cmd = read_json(cmd_path, default={})
                cmd_path.unlink(missing_ok=True)
                name = str(cmd.get("command", "")) if isinstance(cmd, dict) else ""
                if name in accepted:
                    return name
            except Exception:
                pass
    return "stop"


# ── run() ───────────────────────────────────────────────────────────

def run(args) -> int:
    import random
    setup_signals()
    random.seed()
    configure_progress_mode(args.progress_mode)
    configure_http(
        cache_dir=args.http_cache_dir,
        rps=args.http_rps,
        max_connections=args.http_max_connections,
        max_retries=args.http_max_retries,
        backoff_base_seconds=args.http_backoff_base_seconds,
        backoff_cap_seconds=args.http_backoff_cap_seconds,
        conditional_cache=True,
    )
    host = "https://armory.warmane.com"
    if args.character_url:
        _, _, host = parse_seed(args.character_url)
    raw = read_json(args.state_file, default={})
    state = raw if isinstance(raw, dict) and raw.get("version") == 1 else default_state(host)
    state.setdefault("players", {})
    state.setdefault("processed_players", {})
    state.setdefault("failed_players", {})
    state.setdefault("processed_match_ids", [])
    state.setdefault("fetched_guilds", [])
    for p in state["players"].values():
        if not isinstance(p, dict):
            continue
        hint_name = class_from_hint(p.get("class_hint"))
        if hint_name:
            p["class_hint_name"] = hint_name
    processed_match_ids = {str(x) for x in state["processed_match_ids"]}

    if args.import_legacy and args.legacy_state_file.exists():
        legacy = read_json(args.legacy_state_file, default={})
        if isinstance(legacy, dict):
            for mid in legacy.get("processed_match_ids", []):
                processed_match_ids.add(str(mid))
            for v in (legacy.get("players", {}) or {}).values():
                if not isinstance(v, dict):
                    continue
                name, realm = str(v.get("name") or ""), str(v.get("realm") or "")
                if not name or not realm:
                    continue
                p = ensure_player(state, name, realm)
                if v.get("class_hint") and not p.get("class_hint"):
                    p["class_hint"] = v.get("class_hint")
                if not p.get("class_hint_name"):
                    p["class_hint_name"] = class_from_hint(v.get("class_hint"))
            for k, v in (legacy.get("processed_players", {}) or {}).items():
                if k not in state["processed_players"] and isinstance(v, dict):
                    state["processed_players"][k] = v

    if args.character_url:
        name, realm, host = parse_seed(args.character_url)
        state["host"] = host
        ensure_player(state, name, realm)
    ladder_added = 0
    ladder_refreshed = 0
    if str(args.ladder_seed_url or "").strip():
        ladder_added, ladder_refreshed = seed_players_from_ladder(args, state)
        print(f"  Ladder   seed add={ladder_added} refresh={ladder_refreshed}")
    if not state["players"]:
        raise RuntimeError("Sem players no estado. Forneça character_url ou --ladder-seed-url válido para seed inicial.")

    net_state = ensure_network_state(state)
    if bool(args.reset_network_adaptive_on_start):
        net_state["delay_factor"] = 1.0
        net_state["consecutive_errors"] = 0
    ensure_telemetry_state(state)
    last_new_players_ts = time.monotonic()
    runtime_timer: dict[str, Any] = {"next_due": 0.0, "last_error": ""}
    runtime: dict[str, Any] = {"phase": "startup", "cycle_metrics": {"phase": "startup"}}

    def emit_runtime(stage: str, extra_metrics: dict[str, Any] | None = None, force: bool = False) -> None:
        merged = dict(runtime["cycle_metrics"])
        if isinstance(extra_metrics, dict):
            merged.update(extra_metrics)
        maybe_write_runtime_state(
            args=args,
            state=state,
            phase=runtime["phase"],
            stage=stage,
            cycle_metrics=merged,
            timer=runtime_timer,
            force=force,
        )

    # IPC: paths
    _ipc_dir = args.state_file.parent if hasattr(args.state_file, 'parent') else Path(str(args.state_file)).parent
    _tui_config_path = _ipc_dir / "tui_config.json"
    _tui_cmd_path = _ipc_dir / "tui_commands.json"

    if getattr(args, "start_paused", False):
        state["crawler_status"] = "paused"
        emit_runtime("startup_paused", force=True)
        print("[info] crawler iniciado em modo pausado — aguardando comando 'start' via TUI...")
        ipc_cmd = _ipc_wait_for_command(_tui_cmd_path, emit_runtime)
        if ipc_cmd == "start":
            print("[ipc] crawler retomado pela TUI")
        elif ipc_cmd == "cancel":
            crawler_base.STOP = True
            print("[ipc] crawler cancelado pela TUI (durante pausa inicial)")

    state["crawler_status"] = "running"
    emit_runtime("startup", force=True)
    # Rastrear mudanças reais para evitar save desnecessário no shutdown
    snapshot_players = len(state["processed_players"])
    snapshot_matches = len(processed_match_ids)

    while not crawler_base.STOP:
        # IPC: ler config da TUI
        if _tui_config_path.exists():
            try:
                _tui_cfg = read_json(_tui_config_path, default={})
                if isinstance(_tui_cfg, dict):
                    for tui_key, (arg_key, cast) in _TUI_CONFIG_MAP.items():
                        if tui_key in _tui_cfg and _tui_cfg[tui_key] is not None:
                            try:
                                setattr(args, arg_key, cast(_tui_cfg[tui_key]))
                            except Exception:
                                pass
            except Exception:
                pass

        # IPC: ler comandos da TUI
        if _tui_cmd_path.exists():
            try:
                _tui_cmd = read_json(_tui_cmd_path, default={})
                _tui_cmd_path.unlink(missing_ok=True)
                if isinstance(_tui_cmd, dict):
                    _cmd_name = str(_tui_cmd.get("command", ""))
                    if _cmd_name == "pause":
                        state["crawler_status"] = "paused"
                        emit_runtime("paused", force=True)
                        print("[ipc] crawler pausado pela TUI — aguardando start...")
                        ipc_cmd = _ipc_wait_for_command(_tui_cmd_path, emit_runtime)
                        if ipc_cmd == "start":
                            print("[ipc] crawler retomado pela TUI")
                        elif ipc_cmd == "cancel":
                            crawler_base.STOP = True
                            print("[ipc] crawler cancelado pela TUI (durante pausa)")
                        state["crawler_status"] = "running"
                    elif _cmd_name == "cancel":
                        crawler_base.STOP = True
                        state["crawler_status"] = "stopped"
                        emit_runtime("cancelled", force=True)
                        print("[ipc] crawler cancelado pela TUI")
                    elif _cmd_name == "recollect":
                        _filter = str(_tui_cmd.get("filter", "missing_fields"))
                        if _filter == "missing_fields":
                            setattr(args, "recollect_missing_fields", True)
                            print("[ipc] revisita de campos ausentes ativada pela TUI")
            except Exception:
                pass

        if crawler_base.STOP:
            break

        should_stop, last_new_players_ts = _run_cycle(
            args, state, processed_match_ids, last_new_players_ts,
            runtime, emit_runtime,
        )
        if should_stop:
            break
    runtime["phase"] = "shutdown"
    emit_runtime("shutdown_start", force=True)
    data_changed = (
        len(state["processed_players"]) != snapshot_players
        or len(processed_match_ids) != snapshot_matches
    )
    if data_changed:
        save_all(args, state, processed_match_ids)
        emit_runtime("shutdown_saved", force=True)
        print(f"[done] final dataset={len(state['processed_players'])} players={len(state['players'])} matches={len(processed_match_ids)}")
    else:
        emit_runtime("shutdown_skipped", force=True)
        print("[done] sem mudanças de dados nesta sessão — checkpoint ignorado")
    return 0


# ── main() ──────────────────────────────────────────────────────────

def main() -> int:
    args = build_parser().parse_args()
    from armory import __version__
    print(f"[warmane-crawler v{__version__}]", flush=True)
    try:
        if args.request_wall_timeout_seconds > 0 and args.request_wall_timeout_seconds < float(args.timeout_seconds):
            raise ValueError("--request-wall-timeout-seconds deve ser >= --timeout-seconds.")
        if args.matchinfo_request_wall_timeout_seconds > 0 and args.matchinfo_request_wall_timeout_seconds < float(args.matchinfo_timeout_seconds):
            raise ValueError("--matchinfo-request-wall-timeout-seconds deve ser >= --matchinfo-timeout-seconds.")
        if args.max_delay_seconds < args.min_delay_seconds:
            raise ValueError("--max-delay-seconds deve ser >= --min-delay-seconds.")
        if args.adaptive_delay_max_factor < args.adaptive_delay_min_factor:
            raise ValueError("--adaptive-delay-max-factor deve ser >= --adaptive-delay-min-factor.")
        if str(args.ladder_seed_url or "").strip():
            normalize_ladder_url(str(args.ladder_seed_url))
        return run(args)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
