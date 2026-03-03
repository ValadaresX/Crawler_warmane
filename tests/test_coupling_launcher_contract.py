from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "run_crawler_rpi.sh"


def test_launcher_contains_tui_rs_coupling_flags() -> None:
    content = LAUNCHER.read_text(encoding="utf-8")
    assert "--tui-rs-health-file" in content
    assert "--tui-rs-health-interval-seconds" in content
    assert "--no-stop-on-owner-exit" in content
    assert "--owner-exit-grace-seconds" in content
    assert "--quit-file" in content
    assert "--health-file" in content


@pytest.mark.skipif(
    shutil.which("bash") is None and not Path(r"C:\Program Files\Git\bin\bash.exe").exists(),
    reason="bash nao encontrado para validacao de sintaxe",
)
def test_launcher_shell_syntax() -> None:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    bash_bin = shutil.which("bash")
    if bash_bin and "system32\\bash.exe" in bash_bin.lower() and git_bash.exists():
        bash_bin = str(git_bash)
    if not bash_bin and git_bash.exists():
        bash_bin = str(git_bash)
    assert bash_bin is not None
    run = subprocess.run(  # noqa: S603
        [bash_bin, "-n", str(LAUNCHER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
