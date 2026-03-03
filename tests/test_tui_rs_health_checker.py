from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tui_rs" / "check_tui_health.py"


def _run_checker(health_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(CHECKER), "--health-file", str(health_file)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def test_checker_ok_payload(tmp_path: Path) -> None:
    payload = {
        "schema": "crawler_tui_rs.health.v1",
        "timestamp_epoch_ms": 9_999_999_999_999,
        "status": "ok",
        "mode": "live",
        "runtime": {
            "data_age_seconds": 0.2,
            "render_age_seconds": 0.1,
            "state_ok_age_seconds": 0.3,
        },
        "reads": {"ok": 5, "fail": 0, "reused": 2},
        "snapshot": {"cycle": 10, "players_total": 100, "lat_ema_ms": 500, "err_seq": 0},
    }
    health_file = tmp_path / "health_ok.json"
    health_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_checker(health_file)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "status=OK" in result.stdout


def test_checker_fail_when_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    result = _run_checker(missing)
    assert result.returncode == 2
    assert "status=FAIL" in result.stdout
