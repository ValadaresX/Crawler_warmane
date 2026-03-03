from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "check_tui_health.py"


def _run_checker(health_file: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--health-file", str(health_file), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_health_snapshot(
    path: Path,
    *,
    status: str,
    mode: str = "live",
    data_age_s: float = 0.2,
    render_age_s: float = 0.2,
    state_ok_age_s: float | None = 1.0,
    reads_ok: int = 1,
    reads_fail: int = 0,
) -> None:
    now_ms = int(time.time() * 1000)
    runtime: dict[str, object] = {
        "data_age_seconds": data_age_s,
        "render_age_seconds": render_age_s,
        "state_ok_age_seconds": state_ok_age_s,
    }
    payload = {
        "schema": "crawler_tui_rs.health.v1",
        "timestamp_epoch_ms": now_ms,
        "status": status,
        "mode": mode,
        "runtime": runtime,
        "reads": {"ok": reads_ok, "fail": reads_fail, "reused": 0},
        "snapshot": {
            "cycle": 100,
            "players_total": 10_000,
            "lat_ema_ms": 420.0,
            "err_seq": 1,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_health_checker_ok_status(tmp_path: Path) -> None:
    health_file = tmp_path / "health_ok.json"
    _write_health_snapshot(health_file, status="ok")

    proc = _run_checker(health_file, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    parsed = json.loads(proc.stdout)
    assert parsed["status"] == "OK"
    assert parsed["health_status"] == "ok"


def test_health_checker_degraded_status(tmp_path: Path) -> None:
    health_file = tmp_path / "health_degraded.json"
    _write_health_snapshot(health_file, status="degraded", reads_ok=0, reads_fail=2)

    proc = _run_checker(health_file, "--json")
    assert proc.returncode == 1, proc.stdout + proc.stderr

    parsed = json.loads(proc.stdout)
    assert parsed["status"] == "ALERT"
    assert parsed["health_status"] == "degraded"


def test_health_checker_stale_status(tmp_path: Path) -> None:
    health_file = tmp_path / "health_stale.json"
    _write_health_snapshot(
        health_file,
        status="stale",
        data_age_s=3.0,
        render_age_s=2.0,
        state_ok_age_s=91.0,
    )

    proc = _run_checker(health_file, "--json")
    assert proc.returncode == 1, proc.stdout + proc.stderr

    parsed = json.loads(proc.stdout)
    assert parsed["status"] == "ALERT"
    assert parsed["health_status"] == "stale"
