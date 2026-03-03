"""Camada de rede: wrappers HTTP, classificação de erro, delay adaptativo, detecção de bloqueio."""
from __future__ import annotations

import argparse
import contextlib
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawler import base as crawler_base
from crawler.base import now_iso, pause

from armory import analyze_character
from armory.fileio import append_jsonl_line
from armory.network import fetch_json, fetch_text, post_form_json
from armory.runtime import ensure_network_state


# ── Constantes ──────────────────────────────────────────────────────

_NETWORK_KEYWORDS = {"network error", "timeout", "temporarily", "connection"}
_BLOCK_KEYWORDS = {"access denied", "captcha", "cloudflare", "/cdn-cgi/challenge-platform/", "just a moment", "enable javascript and cookies"}
_BLOCK_STATUS = {403, 429}


# ── Classificação de erro ───────────────────────────────────────────

def parse_http_status(error_text: str) -> int | None:
    m = re.search(r"HTTP error\s+(\d{3})", str(error_text or ""))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def classify_failure_kind(error_text: str) -> str:
    msg = str(error_text or "").lower()
    if "resilience_below_min" in msg or "resilience_missing" in msg:
        return "policy"
    if "could not find character name on profile page" in msg:
        return "client"
    if "could not parse item level for item" in msg:
        return "client"
    if "could not parse item quality for item" in msg:
        return "client"
    if "could not parse item tooltip for item" in msg:
        return "client"
    if "invalid json response from:" in msg:
        return "transient"
    code = parse_http_status(msg)
    if code in (403, 408, 409, 425, 429):
        return "transient"
    if code is not None and 500 <= code <= 599:
        return "transient"
    if "timeout" in msg or "network error" in msg or "temporarily" in msg:
        return "transient"
    if code is not None and 400 <= code <= 499:
        return "client"
    return "other"


def is_network_like_error(error_text: str) -> bool:
    msg = str(error_text or "").lower()
    return parse_http_status(msg) is not None or any(k in msg for k in _NETWORK_KEYWORDS)


def is_block_signal(error_text: str) -> bool:
    msg = str(error_text or "").lower()
    return parse_http_status(msg) in _BLOCK_STATUS or any(k in msg for k in _BLOCK_KEYWORDS)


def is_block_detected(args: argparse.Namespace, state: dict[str, Any]) -> bool:
    net = ensure_network_state(state)
    consec = int(net.get("consecutive_errors", 0))
    need = max(1, int(getattr(args, "block_detect_consecutive_errors", 8)))
    if consec < need:
        return False
    last_err = str(net.get("last_error") or "")
    if is_block_signal(last_err):
        return True
    delay_x = float(net.get("delay_factor", 1.0))
    delay_cap = float(getattr(args, "adaptive_delay_max_factor", 8.0))
    if delay_x >= max(1.0, delay_cap * 0.95):
        return True
    return False


# ── Logging ─────────────────────────────────────────────────────────

def log_min_error(
    args: argparse.Namespace,
    state: dict[str, Any],
    scope: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    path = getattr(args, "error_log_file", None)
    if not path:
        return
    payload: dict[str, Any] = {
        "ts_utc": now_iso(),
        "cycle": int(state.get("cycle", 0) or 0),
        "scope": str(scope),
        "kind": classify_failure_kind(message),
        "http_status": parse_http_status(message),
        "message": str(message)[:260],
    }
    if isinstance(extra, dict):
        payload.update(extra)
    try:
        append_jsonl_line(Path(path), payload)
    except Exception:
        pass


def build_failure_record(args: argparse.Namespace, prev: dict[str, Any], error_text: str) -> dict[str, Any]:
    fail_count = int(prev.get("fail_count", 0)) + 1
    kind = classify_failure_kind(error_text)
    if kind == "policy":
        cooldown = float(args.failed_policy_retry_seconds)
    elif kind == "client":
        cooldown = float(args.failed_client_retry_seconds)
    elif kind == "transient":
        exp = min(int(args.failed_backoff_max_exp), max(0, fail_count - 1))
        cooldown = float(args.failed_retry_base_seconds) * (2 ** exp)
    else:
        cooldown = float(args.failed_other_retry_seconds)
    cooldown = max(0.0, min(cooldown, float(args.failed_retry_cap_seconds)))
    return {
        "fail_count": fail_count,
        "failure_kind": kind,
        "last_error": str(error_text)[:220],
        "last_attempt_utc": now_iso(),
        "next_retry_utc": datetime.fromtimestamp(time.time() + cooldown, tz=timezone.utc).isoformat(),
        "cooldown_seconds": int(round(cooldown)),
    }


# ── Delay adaptativo ───────────────────────────────────────────────

def adaptive_pause(args: argparse.Namespace, state: dict[str, Any]) -> None:
    if crawler_base.STOP:
        return
    if not bool(args.adaptive_delay):
        pause(args.min_delay_seconds, args.max_delay_seconds)
        return
    net = ensure_network_state(state)
    factor = max(float(args.adaptive_delay_min_factor), float(net.get("delay_factor", 1.0)))
    min_s = max(0.0, float(args.min_delay_seconds) * factor)
    max_s = max(min_s, float(args.max_delay_seconds) * factor)
    cap = float(args.max_delay_cap_seconds)
    if cap > 0:
        min_s = min(min_s, cap)
        max_s = min(max_s, cap)
    pause(min_s, max_s)


def record_network_event(
    args: argparse.Namespace,
    state: dict[str, Any],
    ok: bool,
    elapsed_ms: float,
    error_text: str | None = None,
) -> None:
    if not bool(args.adaptive_delay):
        return
    net = ensure_network_state(state)
    stats = net["stats"]
    lat_prev = stats.get("latency_ms_ema")
    lat_curr = float(elapsed_ms)
    if lat_prev is None:
        stats["latency_ms_ema"] = lat_curr
    else:
        stats["latency_ms_ema"] = (0.80 * float(lat_prev)) + (0.20 * lat_curr)

    factor = float(net.get("delay_factor", 1.0))
    if ok:
        stats["ok"] = int(stats.get("ok", 0)) + 1
        net["consecutive_errors"] = 0
        factor = max(float(args.adaptive_delay_min_factor), factor * float(args.adaptive_delay_success_decay))
    else:
        stats["err"] = int(stats.get("err", 0)) + 1
        net["consecutive_errors"] = int(net.get("consecutive_errors", 0)) + 1
        net["last_error"] = str(error_text or "")[:220]
        net["last_error_utc"] = now_iso()
        severity = 1.0
        code = parse_http_status(str(error_text or ""))
        if code in (403, 429):
            severity = 1.8
        elif code is not None and code >= 500:
            severity = 1.5
        elif "timeout" in str(error_text or "").lower():
            severity = 1.35
        factor = min(
            float(args.adaptive_delay_max_factor),
            factor * (float(args.adaptive_delay_error_growth) * severity) + 0.02,
        )
        hard_n = int(args.adaptive_delay_hard_backoff_errors)
        consec = int(net.get("consecutive_errors", 0))
        if hard_n > 0 and consec >= hard_n and consec % hard_n == 0:
            backoff_s = float(args.adaptive_delay_hard_backoff_seconds)
            if backoff_s > 0:
                cap = float(args.max_delay_cap_seconds)
                if cap > 0:
                    backoff_s = min(backoff_s, cap)
                if crawler_base.PROGRESS_MODE == "inline":
                    print()
                print(f"  Rede     backoff {backoff_s:.1f}s (erros consecutivos={consec})")
                time.sleep(backoff_s)

    net["delay_factor"] = max(
        float(args.adaptive_delay_min_factor),
        min(float(args.adaptive_delay_max_factor), factor),
    )


# ── Wrappers de request ────────────────────────────────────────────

@contextlib.contextmanager
def _tracked_request(args: argparse.Namespace, state: dict[str, Any], scope: str, extra: dict[str, Any] | None = None):
    t0 = time.perf_counter()
    try:
        yield
        record_network_event(args, state, ok=True, elapsed_ms=(time.perf_counter() - t0) * 1000.0)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        err = str(exc)
        log_min_error(args, state, scope=scope, message=err, extra=extra)
        if scope != "analyze_character" or is_network_like_error(err):
            record_network_event(args, state, ok=False, elapsed_ms=elapsed, error_text=err)
        raise


_SHUTDOWN_TIMEOUT_S = 3


def _resolve_wall(args: argparse.Namespace, explicit: float | None) -> float | None:
    if crawler_base.STOP:
        return float(_SHUTDOWN_TIMEOUT_S)
    w = explicit if explicit is not None else float(args.request_wall_timeout_seconds)
    return w if w > 0 else None


def _effective_timeout(nominal: int) -> int:
    if crawler_base.STOP:
        return min(int(nominal), _SHUTDOWN_TIMEOUT_S)
    return int(nominal)


def net_fetch_text(
    args: argparse.Namespace,
    state: dict[str, Any],
    url: str,
    timeout_seconds: int,
    max_wall_seconds: float | None = None,
) -> str:
    with _tracked_request(args, state, "http_get", {"url": str(url)}):
        return fetch_text(
            url,
            timeout_seconds=_effective_timeout(timeout_seconds),
            max_wall_seconds=_resolve_wall(args, max_wall_seconds),
        )


def net_post_form_json(
    args: argparse.Namespace,
    state: dict[str, Any],
    url: str,
    form_data: dict[str, str],
    timeout_seconds: int,
    max_wall_seconds: float | None = None,
) -> object:
    with _tracked_request(args, state, "http_post", {"url": str(url)}):
        return post_form_json(
            url,
            form_data,
            timeout_seconds=_effective_timeout(timeout_seconds),
            max_wall_seconds=_resolve_wall(args, max_wall_seconds),
        )


def net_fetch_json(
    args: argparse.Namespace,
    state: dict[str, Any],
    url: str,
    timeout_seconds: int,
    max_wall_seconds: float | None = None,
) -> dict | list:
    with _tracked_request(args, state, "http_get_json", {"url": str(url)}):
        return fetch_json(
            url,
            timeout_seconds=_effective_timeout(timeout_seconds),
            max_wall_seconds=_resolve_wall(args, max_wall_seconds),
        )


def net_analyze_character(args: argparse.Namespace, state: dict[str, Any], summary_url: str):
    with _tracked_request(args, state, "analyze_character", {"summary_url": str(summary_url)}):
        return analyze_character(summary_url, cache_path=args.item_cache_dir)


# ── Visita aleatória ────────────────────────────────────────────────

def maybe_random_visit(args: argparse.Namespace, state: dict[str, Any], reason: str) -> None:
    prob = float(args.random_visit_prob)
    if prob <= 0:
        return
    if random.random() > prob:
        return
    host = str(state.get("host") or "https://armory.warmane.com").rstrip("/")
    candidates = [
        f"{host}/",
        f"{host}/ladder",
        f"{host}/leaderboard",
        f"{host}/character",
        f"{host}/prestige",
    ]
    url = random.choice(candidates)
    try:
        adaptive_pause(args, state)
        _ = net_fetch_text(args, state, url, timeout_seconds=args.timeout_seconds)
        print(f"  Visit    diluicao={reason} ok {url}")
    except Exception as exc:
        print(f"  Visit    diluicao={reason} falha {url} ({str(exc)[:90]})")
