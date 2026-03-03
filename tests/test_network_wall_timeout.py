from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import armory.network as nw


class _FakeCache:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def get(self, key: str, default: object | None = None) -> object | None:
        return self._data.get(key, default)

    def set(self, key: str, value: object) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@dataclass
class _FakeResponse:
    status_code: int
    headers: dict[str, str]
    text: str = "<html></html>"

    def json(self) -> object:
        return {"ok": True}


class _Always503Client:
    def get(self, *_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse(status_code=503, headers={})

    def post(self, *_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse(status_code=503, headers={})


def _install_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = nw.HttpRuntimeConfig(
        cache_dir=Path(),
        rps=0.0,
        max_connections=1,
        max_retries=100,
        backoff_base_seconds=1.0,
        backoff_cap_seconds=1.0,
        conditional_cache=False,
    )
    cache = _FakeCache()
    client = _Always503Client()
    monkeypatch.setattr(nw, "_ensure_runtime", lambda: (cfg, cache, client))
    monkeypatch.setattr(nw, "_sleep_rate_limit", lambda _rps: None)
    monkeypatch.setattr(nw, "_compute_backoff_s", lambda *_a, **_k: 0.05)
    monkeypatch.setattr(nw.time, "sleep", lambda _s: None)


def _advance_monotonic(monkeypatch: pytest.MonkeyPatch, step: float = 0.06) -> None:
    current = {"v": 0.0}

    def fake_monotonic() -> float:
        current["v"] += step
        return current["v"]

    monkeypatch.setattr(nw.time, "monotonic", fake_monotonic)


def test_fetch_text_wall_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_runtime(monkeypatch)
    _advance_monotonic(monkeypatch, step=0.07)

    with pytest.raises(RuntimeError):
        nw.fetch_text("https://example.com/a", timeout_seconds=1, max_wall_seconds=0.15)


def test_post_form_json_wall_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_runtime(monkeypatch)
    _advance_monotonic(monkeypatch, step=0.07)

    with pytest.raises(RuntimeError):
        nw.post_form_json(
            "https://example.com/b",
            {"matchinfo": "1"},
            timeout_seconds=1,
            max_wall_seconds=0.15,
        )
