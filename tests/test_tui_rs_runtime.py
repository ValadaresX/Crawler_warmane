from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tui_rs" / "Cargo.toml"
STATE_FILE = ROOT / "data" / "raw" / "adaptive_crawler_state.json"
CHECKER = ROOT / "tui_rs" / "check_tui_health.py"


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo nao encontrado")
def test_tui_rs_text_once_generates_health_snapshot(tmp_path: Path) -> None:
    if not STATE_FILE.exists():
        pytest.skip("state file nao encontrado para teste live/text")

    health_file = tmp_path / "health_runtime.json"
    run_cmd = [
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(MANIFEST),
        "--",
        "--mode",
        "text",
        "--once",
        "--state-file",
        str(STATE_FILE),
        "--health-file",
        str(health_file),
        "--health-interval-seconds",
        "0.2",
        "--refresh-seconds",
        "0.2",
    ]
    run = subprocess.run(  # noqa: S603
        run_cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert health_file.exists()

    payload = json.loads(health_file.read_text(encoding="utf-8"))
    assert payload["schema"] == "crawler_tui_rs.health.v2"
    assert payload["snapshot"]["players_total"] >= 0

    check = subprocess.run(  # noqa: S603
        [sys.executable, str(CHECKER), "--health-file", str(health_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
