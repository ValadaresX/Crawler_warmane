#!/usr/bin/env python3
"""Validador compacto de saúde da TUI Rust (sem log crescente)."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica a saude do health snapshot da TUI Rust."
    )
    parser.add_argument(
        "--health-file",
        default="../data/raw/tui_rs_health.json",
        help="Caminho do arquivo de health snapshot.",
    )
    parser.add_argument(
        "--max-data-age-seconds",
        type=float,
        default=6.0,
        help="Idade maxima do ultimo refresh de dados para status OK.",
    )
    parser.add_argument(
        "--max-render-age-seconds",
        type=float,
        default=4.0,
        help="Idade maxima do ultimo render para status OK.",
    )
    parser.add_argument(
        "--max-state-ok-age-seconds",
        type=float,
        default=90.0,
        help="Idade maxima da ultima leitura bem-sucedida do state (modo live).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime resumo em JSON (linha unica).",
    )
    return parser.parse_args()


def _safe_float(value: object, fallback: float) -> float:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return fallback
    try:
        v = float(value)
        if math.isfinite(v):
            return v
    except (TypeError, ValueError):
        return fallback
    return fallback


def _safe_int(value: object, fallback: int = 0) -> int:
    if not isinstance(value, (str, bytes, bytearray, int)):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def main() -> int:
    args = _parse_args()
    now_ms = int(time.time() * 1000)
    health_path = Path(args.health_file).expanduser().resolve()

    if not health_path.exists():
        print(f"status=FAIL reason=arquivo_ausente file={health_path}")
        return 2

    try:
        payload = json.loads(health_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"status=FAIL reason=json_invalido erro={exc.__class__.__name__} file={health_path}")
        return 2

    mode = str(payload.get("mode", "unknown"))
    status_hint = str(payload.get("status", "unknown")).lower()
    runtime = payload.get("runtime") or {}
    reads = payload.get("reads") or {}
    snapshot = payload.get("snapshot") or {}
    ts_epoch_ms = _safe_int(payload.get("timestamp_epoch_ms"), 0)
    file_age_s = max(0.0, (now_ms - ts_epoch_ms) / 1000.0) if ts_epoch_ms > 0 else float("inf")

    data_age_s = _safe_float(runtime.get("data_age_seconds"), float("inf"))
    render_age_s = _safe_float(runtime.get("render_age_seconds"), float("inf"))
    state_ok_age_raw = runtime.get("state_ok_age_seconds")
    state_ok_age_s = _safe_float(state_ok_age_raw, float("inf"))

    reads_ok = _safe_int(reads.get("ok"), 0)
    reads_fail = _safe_int(reads.get("fail"), 0)
    reads_reused = _safe_int(reads.get("reused"), 0)

    cycle = _safe_int(snapshot.get("cycle"), 0)
    players = _safe_int(snapshot.get("players_total"), 0)
    lat_ms = _safe_float(snapshot.get("lat_ema_ms"), 0.0)
    err_seq = _safe_int(snapshot.get("err_seq"), 0)

    if (
        file_age_s > max(args.max_data_age_seconds, args.max_render_age_seconds) * 3.0
        or data_age_s > args.max_data_age_seconds * 3.0
        or render_age_s > args.max_render_age_seconds * 3.0
    ):
        level = "FAIL"
        code = 2
    elif (
        data_age_s > args.max_data_age_seconds
        or render_age_s > args.max_render_age_seconds
        or (mode == "live" and reads_ok > 0 and state_ok_age_s > args.max_state_ok_age_seconds)
        or status_hint in {"stale", "degraded"}
    ):
        level = "ALERT"
        code = 1
    else:
        level = "OK"
        code = 0

    if args.json:
        summary = {
            "status": level,
            "mode": mode,
            "health_status": status_hint,
            "cycle": cycle,
            "players_total": players,
            "lat_ms": round(lat_ms, 2),
            "err_seq": err_seq,
            "data_age_s": round(data_age_s, 3),
            "render_age_s": round(render_age_s, 3),
            "state_ok_age_s": None if not math.isfinite(state_ok_age_s) else round(state_ok_age_s, 3),
            "reads_ok": reads_ok,
            "reads_fail": reads_fail,
            "reads_reused": reads_reused,
            "file_age_s": round(file_age_s, 3) if math.isfinite(file_age_s) else None,
            "file": str(health_path),
        }
        print(json.dumps(summary, ensure_ascii=False))
    else:
        state_ok_txt = "na" if not math.isfinite(state_ok_age_s) else f"{state_ok_age_s:.2f}s"
        file_age_txt = "na" if not math.isfinite(file_age_s) else f"{file_age_s:.2f}s"
        print(
            " ".join(
                [
                    f"status={level}",
                    f"mode={mode}",
                    f"health={status_hint}",
                    f"cycle={cycle}",
                    f"players={players}",
                    f"lat_ms={lat_ms:.1f}",
                    f"err_seq={err_seq}",
                    f"data_age={data_age_s:.2f}s",
                    f"render_age={render_age_s:.2f}s",
                    f"state_ok_age={state_ok_txt}",
                    f"reads_ok={reads_ok}",
                    f"reads_fail={reads_fail}",
                    f"reads_reused={reads_reused}",
                    f"file_age={file_age_txt}",
                    f"file={health_path}",
                ]
            )
        )

    return code


if __name__ == "__main__":
    raise SystemExit(main())
