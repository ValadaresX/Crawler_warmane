"""Argparse: validadores, build_parser, parse_seed."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from armory.match_history import (
    normalize_ladder_url,
    normalize_match_history_url,
)


def _constrained(
    type_fn: Callable,
    *,
    gt: float | None = None,
    ge: float | None = None,
    lt: float | None = None,
    le: float | None = None,
    label: str = "",
) -> Callable[[str], int | float]:
    def _validator(value: str) -> int | float:
        v = type_fn(value)
        if gt is not None and v <= gt:
            raise argparse.ArgumentTypeError(f"{label or 'valor'} deve ser > {gt}, recebeu {v}")
        if ge is not None and v < ge:
            raise argparse.ArgumentTypeError(f"{label or 'valor'} deve ser >= {ge}, recebeu {v}")
        if lt is not None and v >= lt:
            raise argparse.ArgumentTypeError(f"{label or 'valor'} deve ser < {lt}, recebeu {v}")
        if le is not None and v > le:
            raise argparse.ArgumentTypeError(f"{label or 'valor'} deve ser <= {le}, recebeu {v}")
        return v
    return _validator


_positive_int = _constrained(int, gt=0)
_nonneg_int = _constrained(int, ge=0)
_positive_float = _constrained(float, gt=0)
_nonneg_float = _constrained(float, ge=0)
_ratio_float = _constrained(float, gt=0, lt=1)
_unit_float = _constrained(float, ge=0, le=1)
_decay_float = _constrained(float, gt=0, le=1)
_growth_float = _constrained(float, ge=1.0)
_min10_int = _constrained(int, ge=10)


def parse_seed(url: str) -> tuple[str, str, str]:
    u = normalize_match_history_url(url)
    p = urlparse(u)
    parts = p.path.strip("/").split("/")
    if len(parts) < 4:
        raise ValueError("URL de seed inválida.")
    return parts[1], parts[2], f"{p.scheme}://{p.netloc}"


def build_parser() -> argparse.ArgumentParser:
    from armory import __version__

    ap = argparse.ArgumentParser(description="Crawler adaptativo em grafo para Warmane (rodagem dinâmica, sem limite de ciclos por padrão).")
    ap.add_argument("--version", action="version", version=f"warmane-crawler {__version__}")
    ap.add_argument("character_url", nargs="?")
    ap.add_argument("--state-file", type=Path, default=Path("data/raw/adaptive_crawler_state.json"))
    ap.add_argument("--dataset-json", type=Path, default=Path("data/processed/players_dataset.json"))
    ap.add_argument("--dataset-csv", type=Path, default=Path("data/processed/players_dataset.csv"))
    ap.add_argument("--dataset-parquet", type=Path, default=Path("data/processed/players_dataset.parquet"))
    ap.add_argument("--items-parquet", type=Path, default=Path("data/processed/players_items.parquet"))
    ap.add_argument("--legacy-state-file", type=Path, default=Path("data/raw/state_match_history.json"))
    ap.add_argument("--item-cache-dir", type=Path, default=Path("data/cache/item_metadata"))
    ap.add_argument("--http-cache-dir", type=Path, default=Path("data/cache/http_cache"))
    ap.add_argument("--http-rps", type=_nonneg_float, default=0.90)
    ap.add_argument("--http-max-connections", type=_positive_int, default=4)
    ap.add_argument("--http-max-retries", type=_positive_int, default=5)
    ap.add_argument("--http-backoff-base-seconds", type=_positive_float, default=1.0)
    ap.add_argument("--http-backoff-cap-seconds", type=_positive_float, default=45.0)
    ap.add_argument("--timeout-seconds", type=_positive_int, default=30)
    ap.add_argument("--request-wall-timeout-seconds", type=_nonneg_float, default=90.0,
                    help="Tempo máximo total por request (tentativas+backoff). 0 desativa.")
    ap.add_argument("--matchinfo-timeout-seconds", type=_positive_int, default=18,
                    help="Timeout por tentativa de matchinfo (POST).")
    ap.add_argument("--matchinfo-request-wall-timeout-seconds", type=_nonneg_float, default=45.0,
                    help="Tempo máximo total por request de matchinfo (tentativas+backoff). 0 desativa.")
    ap.add_argument("--history-root-max-seconds", type=_nonneg_float, default=180.0,
                    help="Tempo máximo por root de match-history. 0 desativa.")
    ap.add_argument("--history-detail-error-streak-stop", type=_nonneg_int, default=12,
                    help="Interrompe root após N erros seguidos em details. 0 desativa.")
    ap.add_argument("--cycle-max-seconds", type=_nonneg_float, default=420.0,
                    help="Tempo máximo por ciclo; ao atingir, encerra ciclo e segue. 0 desativa.")
    ap.add_argument("--progress-mode", choices=("line", "inline", "auto"), default="auto")
    ap.add_argument("--min-delay-seconds", type=_nonneg_float, default=1.3)
    ap.add_argument("--max-delay-seconds", type=_nonneg_float, default=3.1)
    ap.add_argument("--max-delay-cap-seconds", type=_nonneg_float, default=20.0)
    ap.add_argument("--no-adaptive-delay", dest="adaptive_delay", action="store_false")
    ap.set_defaults(adaptive_delay=True)
    ap.add_argument("--adaptive-delay-min-factor", type=_positive_float, default=0.35)
    ap.add_argument("--adaptive-delay-max-factor", type=_positive_float, default=8.0)
    ap.add_argument("--adaptive-delay-success-decay", type=_decay_float, default=0.985)
    ap.add_argument("--adaptive-delay-error-growth", type=_growth_float, default=1.20)
    ap.add_argument("--adaptive-delay-hard-backoff-errors", type=_nonneg_int, default=6)
    ap.add_argument("--adaptive-delay-hard-backoff-seconds", type=_nonneg_float, default=8.0)
    ap.add_argument("--history-cooldown-seconds", type=_nonneg_float, default=600.0)
    ap.add_argument("--max-history-pages-per-cycle", type=_nonneg_int, default=0)
    ap.add_argument("--max-matchinfo-per-cycle", type=_nonneg_int, default=120)
    ap.add_argument("--history-players-per-cycle", type=_positive_int, default=10)
    ap.add_argument("--history-selection-mode", choices=["auto", "discovery", "balanced"], default="auto",
                    help="Modo de selecao de players para history scan: auto|discovery|balanced")
    ap.add_argument("--ladder-seed-url", default="https://armory.warmane.com/ladder/SoloQ/1/80")
    ap.add_argument("--ladder-seed-max-players", type=_nonneg_int, default=50)
    ap.add_argument("--phase", choices=("auto", "discover", "convert", "hybrid"), default="auto")
    ap.add_argument("--profiles-per-cycle", type=int, default=3)
    ap.add_argument("--recollect-all-processed", action="store_true")
    ap.add_argument("--recollect-and-append", action="store_true",
                    help="Atualiza players já processados e também coleta players novos no mesmo ciclo.")
    ap.add_argument("--recollect-missing-fields", action="store_true",
                    help="Revisitar players que nao tem campos enriquecidos (guild, professions, etc).")
    ap.add_argument("--recollect-batch-size", type=int, default=10,
                    help="Maximo de players com campos faltantes por ciclo (default: 10).")
    ap.add_argument("--guild-discovery-max-per-cycle", type=_nonneg_int, default=3,
                    help="Guilds consultadas por ciclo para descoberta. 0 desativa.")
    ap.add_argument("--random-visit-prob", type=_unit_float, default=0.18)
    ap.add_argument("--random-visit-every-pages", type=_nonneg_int, default=7)
    ap.add_argument("--random-visit-every-matchinfos", type=_nonneg_int, default=40)
    ap.add_argument("--random-visit-every-profiles", type=_nonneg_int, default=20)
    ap.add_argument("--skip-failed", action="store_true")
    ap.add_argument("--failed-retry-base-seconds", type=_nonneg_float, default=1200.0)
    ap.add_argument("--failed-policy-retry-seconds", type=_nonneg_float, default=21600.0)
    ap.add_argument("--failed-client-retry-seconds", type=_nonneg_float, default=43200.0)
    ap.add_argument("--failed-other-retry-seconds", type=_nonneg_float, default=10800.0)
    ap.add_argument("--failed-retry-cap-seconds", type=_nonneg_float, default=172800.0)
    ap.add_argument("--failed-backoff-max-exp", type=_nonneg_int, default=6)
    ap.add_argument("--allow-non80", dest="only_level_80", action="store_false")
    ap.set_defaults(only_level_80=True)
    ap.add_argument("--telemetry-keep-cycles", type=_min10_int, default=400)
    ap.add_argument(
        "--runtime-state-file",
        type=Path,
        default=Path("data/raw/adaptive_crawler_runtime.json"),
        help="Arquivo JSON leve para heartbeat de runtime (usado pela TUI em tempo real).",
    )
    ap.add_argument(
        "--runtime-state-interval-seconds",
        type=_nonneg_float,
        default=2.0,
        help="Intervalo de escrita do heartbeat de runtime. 0 desativa atualizacao periodica.",
    )
    ap.add_argument(
        "--runtime-class-counts-refresh-seconds",
        type=_positive_float,
        default=3.0,
        help="Intervalo maximo para recalc da contagem por classe no runtime-state.",
    )
    ap.add_argument("--no-runtime-state", dest="runtime_state_enabled", action="store_false")
    ap.set_defaults(runtime_state_enabled=True)
    ap.add_argument("--idle-stop-seconds", type=_nonneg_int, default=300)
    ap.add_argument("--block-detect-consecutive-errors", type=_positive_int, default=8)
    ap.add_argument("--no-stop-on-block-detected", dest="stop_on_block_detected", action="store_false")
    ap.set_defaults(stop_on_block_detected=True)
    ap.add_argument("--error-log-file", type=Path, default=Path("logs/crawler_errors_min.jsonl"))
    ap.add_argument("--no-reset-network-adaptive-on-start", dest="reset_network_adaptive_on_start", action="store_false")
    ap.set_defaults(reset_network_adaptive_on_start=True)
    ap.add_argument("--start-paused", action="store_true",
                    help="Inicia o crawler em modo pausado, aguardando comando 'start' via IPC.")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-import-legacy", dest="import_legacy", action="store_false")
    ap.set_defaults(import_legacy=True)
    return ap
