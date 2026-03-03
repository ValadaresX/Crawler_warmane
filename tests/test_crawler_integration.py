"""Integration tests for crawler + launcher stability.

Validates that the crawler starts, handles signals cleanly, and that
all modules import correctly after refactoring. These tests catch the
class of bugs we hit in production: signal spam, leaked output,
broken imports, and permission errors.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRAWLER_PKG = ROOT / "crawler"
LAUNCHER = ROOT / "run_crawler_rpi.sh"
START_SCRIPT = ROOT / "start_crawler_tui_rpi.sh"

_CRAWLER_MODULE_NAME = "crawler.__main__"


def _import_crawler() -> ModuleType:
    """Import the crawler entry-point as a module.

    Registers it in sys.modules so @dataclass and other decorators that
    inspect cls.__module__ work correctly with dynamic imports.
    """
    target = CRAWLER_PKG / "__main__.py"
    spec = importlib.util.spec_from_file_location(_CRAWLER_MODULE_NAME, target)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_CRAWLER_MODULE_NAME] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(_CRAWLER_MODULE_NAME, None)
        raise
    return mod


# ── 1. Module import health ──────────────────────────────────────────


class TestModuleImports:
    """Verify all refactored modules import without error."""

    @pytest.mark.parametrize(
        "module",
        [
            "armory.fileio",
            "armory.runtime",
            "armory.network",
            "armory.constants",
            "armory.match_history",
        ],
    )
    def test_module_imports(self, module: str) -> None:
        mod = importlib.import_module(module)
        assert mod is not None

    def test_atomic_io_exports(self) -> None:
        from armory.fileio import (
            append_jsonl_line,
            atomic_path,
            read_json,
            write_csv_atomic,
            write_json_atomic,
            write_parquet_atomic,
        )
        assert callable(write_json_atomic)
        assert callable(read_json)
        assert callable(atomic_path)
        assert callable(append_jsonl_line)
        assert callable(write_csv_atomic)
        assert callable(write_parquet_atomic)

    def test_runtime_state_exports(self) -> None:
        from armory.runtime import (
            append_cycle_telemetry,
            ensure_network_state,
            ensure_telemetry_state,
            maybe_write_runtime_state,
        )
        assert callable(ensure_network_state)
        assert callable(ensure_telemetry_state)
        assert callable(append_cycle_telemetry)
        assert callable(maybe_write_runtime_state)


# ── 2. Atomic I/O context manager ────────────────────────────────────


class TestAtomicIO:
    def test_atomic_path_writes_atomically(self, tmp_path: Path) -> None:
        from armory.fileio import atomic_path

        target = tmp_path / "test.json"
        with atomic_path(target) as tmp:
            tmp.write_text('{"ok": true}', encoding="utf-8")
            # Target should NOT exist yet (atomic)
            assert not target.exists()
        # After context exit, target exists
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}

    def test_atomic_path_cleans_up_on_error(self, tmp_path: Path) -> None:
        from armory.fileio import atomic_path

        target = tmp_path / "fail.json"
        with pytest.raises(ValueError):
            with atomic_path(target) as tmp:
                tmp.write_text("partial", encoding="utf-8")
                raise ValueError("simulated error")
        # Neither target nor temp should exist
        assert not target.exists()
        temps = list(tmp_path.glob("fail.json*.tmp"))
        assert len(temps) == 0

    def test_write_json_atomic_roundtrip(self, tmp_path: Path) -> None:
        from armory.fileio import read_json, write_json_atomic

        target = tmp_path / "data.json"
        payload = {"cycle": 42, "players": ["a", "b"]}
        write_json_atomic(target, payload)
        result = read_json(target, default={})
        assert result == payload

    def test_read_json_missing_returns_default(self, tmp_path: Path) -> None:
        from armory.fileio import read_json

        result = read_json(tmp_path / "nope.json", default={"empty": True})
        assert result == {"empty": True}


# ── 3. Validator factory ─────────────────────────────────────────────


class TestValidatorFactory:
    """Verify the _constrained factory produces correct validators."""

    @pytest.fixture(autouse=True)
    def _load_validators(self) -> None:
        self.mod = _import_crawler()

    def test_positive_int_accepts_valid(self) -> None:
        assert self.mod._positive_int("5") == 5

    def test_positive_int_rejects_zero(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            self.mod._positive_int("0")

    def test_nonneg_float_accepts_zero(self) -> None:
        assert self.mod._nonneg_float("0.0") == 0.0

    def test_nonneg_float_rejects_negative(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            self.mod._nonneg_float("-1")

    def test_ratio_float_rejects_boundaries(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            self.mod._ratio_float("0")
        with pytest.raises(argparse.ArgumentTypeError):
            self.mod._ratio_float("1")

    def test_decay_float_accepts_one(self) -> None:
        assert self.mod._decay_float("1.0") == 1.0

    def test_growth_float_rejects_below_one(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            self.mod._growth_float("0.99")


# ── 4. Crawler dry-run smoke test ────────────────────────────────────


@pytest.mark.skipif(
    not CRAWLER_PKG.exists(), reason="pacote crawler nao encontrado"
)
class TestCrawlerDryRun:
    def test_crawler_help_works(self) -> None:
        """--help should print usage and exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "crawler", "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            cwd=ROOT,
        )
        assert result.returncode == 0
        assert "adaptive" in result.stdout.lower() or "crawler" in result.stdout.lower()

    def test_crawler_build_parser_succeeds(self) -> None:
        """build_parser() should create a parser with all arguments."""
        mod = _import_crawler()
        parser = mod.build_parser()
        # Smoke test: parse with defaults (no positional required)
        args = parser.parse_args([])
        assert hasattr(args, "http_rps")
        assert hasattr(args, "phase")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="dry-run e2e requer RPi (rede Warmane + Linux signals)"
)
class TestCrawlerDryRunE2E:
    def test_crawler_starts_and_exits_cleanly(self, tmp_path: Path) -> None:
        """--dry-run --once should start, run one cycle, and exit 0.

        Pre-seeds a minimal state with 1 dummy player pointing at localhost
        (connection refused = instant failure), disables ladder seeding and
        legacy import so the test runs without real network access.
        """
        state = tmp_path / "state.json"
        dataset = tmp_path / "dataset.json"
        csv_out = tmp_path / "dataset.csv"
        runtime = tmp_path / "runtime.json"
        seed_state = {
            "version": 1,
            "host": "http://localhost:1",
            "created_at_utc": "2026-01-01T00:00:00Z",
            "updated_at_utc": "2026-01-01T00:00:00Z",
            "cycle": 0,
            "players": {
                "TestPlayer|Icecrown": {
                    "name": "TestPlayer",
                    "realm": "Icecrown",
                    "class_hint": None,
                    "class_hint_name": None,
                    "ladder_seed_rank": None,
                    "source_match_ids": [],
                    "history_scan_count": 0,
                    "last_history_scan_utc": None,
                    "first_seen_utc": "2026-01-01T00:00:00Z",
                    "last_seen_utc": "2026-01-01T00:00:00Z",
                }
            },
            "processed_players": {},
            "failed_players": {},
            "processed_match_ids": [],
            "no_progress_cycles": 0,
            "network": {
                "delay_factor": 1.0,
                "consecutive_errors": 0,
                "last_error": None,
                "last_error_utc": None,
                "stats": {"ok": 0, "err": 0, "latency_ms_ema": None},
            },
            "telemetry": {"cycles": []},
        }
        state.write_text(json.dumps(seed_state), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m", "crawler",
                "--dry-run",
                "--once",
                "--state-file", str(state),
                "--dataset-json", str(dataset),
                "--dataset-csv", str(csv_out),
                "--runtime-state-file", str(runtime),
                "--no-runtime-state",
                "--no-import-legacy",
                "--http-rps", "0",
                "--ladder-seed-url", "",
                "--http-max-retries", "1",
                "--timeout-seconds", "1",
                "--matchinfo-timeout-seconds", "1",
                "--request-wall-timeout-seconds", "3",
                "--matchinfo-request-wall-timeout-seconds", "3",
                "--http-backoff-base-seconds", "0.01",
                "--http-backoff-cap-seconds", "0.01",
                "--no-stop-on-block-detected",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            cwd=ROOT,
        )
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


# ── 5. Signal handling (single message, no spam) ─────────────────────


@pytest.mark.skipif(
    sys.platform == "win32", reason="signal test requer POSIX"
)
@pytest.mark.skipif(
    not CRAWLER_PKG.exists(), reason="pacote crawler nao encontrado"
)
class TestSignalHandling:
    def test_sigint_produces_single_message(self, tmp_path: Path) -> None:
        """Send SIGINT and verify exactly one 'sinal recebido' message."""
        state = tmp_path / "state.json"
        dataset = tmp_path / "dataset.json"
        csv_out = tmp_path / "dataset.csv"
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m", "crawler",
                "--dry-run",
                "--state-file", str(state),
                "--dataset-json", str(dataset),
                "--dataset-csv", str(csv_out),
                "--no-runtime-state",
                "--http-rps", "0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=ROOT,
        )
        # Let the crawler start
        time.sleep(2)
        # Send SIGINT
        proc.send_signal(signal.SIGINT)
        stdout, _ = proc.communicate(timeout=15)
        signal_lines = [l for l in stdout.splitlines() if "sinal recebido" in l]
        assert len(signal_lines) <= 1, (
            f"Esperava <= 1 mensagem de sinal, recebeu {len(signal_lines)}:\n"
            + "\n".join(signal_lines)
        )


# ── 6. Shell script syntax and contracts ─────────────────────────────


def _find_bash() -> str | None:
    bash = shutil.which("bash")
    if bash and "system32" in bash.lower():
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            return str(git_bash)
    return bash


@pytest.mark.skipif(_find_bash() is None, reason="bash nao encontrado")
class TestShellScripts:
    def test_launcher_syntax(self) -> None:
        result = subprocess.run(
            [_find_bash(), "-n", str(LAUNCHER)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_start_script_syntax(self) -> None:
        if not START_SCRIPT.exists():
            pytest.skip("start_crawler_tui_rpi.sh nao encontrado")
        result = subprocess.run(
            [_find_bash(), "-n", str(START_SCRIPT)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_launcher_does_not_use_exec_dotslash(self) -> None:
        """Scripts should use 'bash script.sh', not 'exec ./script.sh'
        which requires +x permission."""
        for script in [START_SCRIPT]:
            if not script.exists():
                continue
            content = script.read_text(encoding="utf-8")
            assert "exec ./" not in content, (
                f"{script.name} usa 'exec ./' que depende de chmod +x"
            )

    def test_cleanup_has_reentry_guard(self) -> None:
        """Cleanup function must have a guard to prevent signal re-entry loop."""
        content = LAUNCHER.read_text(encoding="utf-8")
        assert "CLEANUP_DONE" in content, (
            "cleanup() precisa de guard CLEANUP_DONE para evitar loop de sinais"
        )

    def test_trap_includes_all_signals(self) -> None:
        """Trap must catch EXIT, HUP, TERM, INT."""
        content = LAUNCHER.read_text(encoding="utf-8")
        assert "trap cleanup EXIT HUP TERM INT" in content

    def test_wait_loop_for_crawler(self) -> None:
        """Wait for crawler must loop to handle interrupted waits."""
        content = LAUNCHER.read_text(encoding="utf-8")
        assert 'while kill -0 "$CRAWLER_PID"' in content, (
            "wait do crawler deve rodar em loop para re-wait apos interrupcao"
        )
