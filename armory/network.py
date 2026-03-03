from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import threading
import time
import string
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from diskcache import Cache
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    stop_any,
)

from .constants import HTTP_HEADER_PROFILES, USER_AGENT, USER_AGENT_POOL


@dataclass
class HttpRuntimeConfig:
    cache_dir: Path
    rps: float
    max_connections: int
    max_retries: int
    backoff_base_seconds: float
    backoff_cap_seconds: float
    conditional_cache: bool


_CONFIG_LOCK = threading.Lock()
_RATE_LOCK = threading.Lock()

_CONFIG: HttpRuntimeConfig | None = None
_CACHE: Cache | None = None
_HTTP_CLIENT: httpx.Client | None = None
_NEXT_REQUEST_AT = 0.0

_RETRYABLE_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.WriteError,
    httpx.ReadError,
    httpx.PoolTimeout,
)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _env(name: str, default: Any, cast: type | None = None) -> Any:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return cast(raw) if cast else raw
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    return _env(name, default, float)


def _env_int(name: str, default: int) -> int:
    return _env(name, default, int)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def configure_http(
    cache_dir: Path | str | None = None,
    rps: float | None = None,
    max_connections: int | None = None,
    max_retries: int | None = None,
    backoff_base_seconds: float | None = None,
    backoff_cap_seconds: float | None = None,
    conditional_cache: bool | None = None,
) -> None:
    global _CONFIG, _CACHE, _HTTP_CLIENT, _NEXT_REQUEST_AT
    with _CONFIG_LOCK:
        base = _CONFIG or HttpRuntimeConfig(
            cache_dir=Path(str(os.getenv("WARMANE_HTTP_CACHE_DIR", "data/cache/http_cache"))),
            rps=max(0.0, _env_float("WARMANE_HTTP_RPS", 0.90)),
            max_connections=max(1, _env_int("WARMANE_HTTP_MAX_CONNECTIONS", 4)),
            max_retries=max(1, _env_int("WARMANE_HTTP_MAX_RETRIES", 5)),
            backoff_base_seconds=max(0.1, _env_float("WARMANE_HTTP_BACKOFF_BASE", 1.0)),
            backoff_cap_seconds=max(0.5, _env_float("WARMANE_HTTP_BACKOFF_CAP", 45.0)),
            conditional_cache=_env_bool("WARMANE_HTTP_CONDITIONAL_CACHE", True),
        )

        _CLAMP: dict[str, tuple[type, float]] = {
            "cache_dir": (Path, 0), "rps": (float, 0.0), "max_connections": (int, 1),
            "max_retries": (int, 1), "backoff_base_seconds": (float, 0.1),
            "backoff_cap_seconds": (float, 0.5), "conditional_cache": (bool, 0),
        }
        overrides: dict[str, Any] = {}
        for k, v in dict(cache_dir=cache_dir, rps=rps, max_connections=max_connections,
                         max_retries=max_retries, backoff_base_seconds=backoff_base_seconds,
                         backoff_cap_seconds=backoff_cap_seconds, conditional_cache=conditional_cache).items():
            if v is not None:
                cast, lo = _CLAMP[k]
                overrides[k] = max(lo, cast(v)) if cast in (int, float) else cast(v)
        cfg = replace(base, **overrides) if overrides else base

        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        if _CACHE is not None:
            _CACHE.close()
        try:
            _CACHE = Cache(str(cfg.cache_dir))
        except Exception:
            # Recuperação automática de cache SQLite corrompido.
            corrupted_dir = cfg.cache_dir.parent / f"{cfg.cache_dir.name}_corrupted_{int(time.time())}"
            try:
                if cfg.cache_dir.exists():
                    cfg.cache_dir.rename(corrupted_dir)
            except Exception:
                shutil.rmtree(cfg.cache_dir, ignore_errors=True)
            cfg.cache_dir.mkdir(parents=True, exist_ok=True)
            _CACHE = Cache(str(cfg.cache_dir))

        if _HTTP_CLIENT is not None:
            _HTTP_CLIENT.close()
        limits = httpx.Limits(max_connections=cfg.max_connections, max_keepalive_connections=cfg.max_connections)
        _HTTP_CLIENT = httpx.Client(follow_redirects=True, limits=limits)

        _NEXT_REQUEST_AT = 0.0
        _CONFIG = cfg


def _rebuild_cache_runtime(config: HttpRuntimeConfig, cache: Cache | None) -> Cache:
    global _CACHE
    with _CONFIG_LOCK:
        try:
            if cache is not None:
                cache.close()
        except Exception:
            pass
        corrupted_dir = config.cache_dir.parent / f"{config.cache_dir.name}_corrupted_{int(time.time())}"
        try:
            if config.cache_dir.exists():
                config.cache_dir.rename(corrupted_dir)
        except Exception:
            shutil.rmtree(config.cache_dir, ignore_errors=True)
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        _CACHE = Cache(str(config.cache_dir))
        return _CACHE


def _ensure_runtime() -> tuple[HttpRuntimeConfig, Cache, httpx.Client]:
    if _CONFIG is None or _CACHE is None or _HTTP_CLIENT is None:
        configure_http()
    assert _CONFIG is not None
    assert _CACHE is not None
    assert _HTTP_CLIENT is not None
    return _CONFIG, _CACHE, _HTTP_CLIENT


def _parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    token = str(value).strip()
    if not token:
        return None
    if token.isdigit():
        return max(0.0, float(token))
    try:
        dt = parsedate_to_datetime(token)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, float(delta))
    except Exception:
        return None


def _sleep_rate_limit(rps: float) -> None:
    global _NEXT_REQUEST_AT
    if rps <= 0:
        return
    wait_s = 0.0
    min_interval = 1.0 / float(rps)
    with _RATE_LOCK:
        now = time.monotonic()
        if _NEXT_REQUEST_AT > now:
            wait_s = _NEXT_REQUEST_AT - now
            now = _NEXT_REQUEST_AT
        _NEXT_REQUEST_AT = now + min_interval
    if wait_s > 0:
        time.sleep(wait_s)


def _compute_backoff_s(config: HttpRuntimeConfig, attempt: int, retry_after_s: float | None = None) -> float:
    if retry_after_s is not None:
        base = min(float(config.backoff_cap_seconds), max(0.0, float(retry_after_s)))
        jitter = random.uniform(0.05, 0.35)
        return min(float(config.backoff_cap_seconds), base + jitter)
    base = float(config.backoff_base_seconds) * (2 ** max(0, attempt))
    base = min(base, float(config.backoff_cap_seconds))
    jitter = random.uniform(0.05, max(0.10, base * 0.30))
    return min(float(config.backoff_cap_seconds), base + jitter)


def _url_cache_keys(url: str) -> tuple[str, str]:
    digest = hashlib.sha1(url.encode("utf-8", errors="ignore")).hexdigest()
    return f"url:{digest}:meta", f"url:{digest}:body"


def _read_cache(cache: Cache, url: str) -> tuple[dict[str, Any], str | None]:
    meta_key, body_key = _url_cache_keys(url)
    meta = cache.get(meta_key, default={})
    body = cache.get(body_key, default=None)
    if not isinstance(meta, dict):
        meta = {}
    if body is not None and not isinstance(body, str):
        body = str(body)
    return meta, body


def _write_cache(cache: Cache, url: str, response: httpx.Response, body: str) -> None:
    meta_key, body_key = _url_cache_keys(url)
    meta = {
        "etag": str(response.headers.get("ETag", "")).strip(),
        "last_modified": str(response.headers.get("Last-Modified", "")).strip(),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": int(response.status_code),
    }
    cache.set(meta_key, meta)
    cache.set(body_key, body)


def _pick_headers(extra: dict[str, str] | None = None) -> httpx.Headers:
    ua = random.choice(USER_AGENT_POOL) if USER_AGENT_POOL else USER_AGENT
    profile = random.choice(HTTP_HEADER_PROFILES) if HTTP_HEADER_PROFILES else ()
    ordered: list[tuple[str, str]] = [("User-Agent", ua)]
    ordered.extend(profile)
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            ordered.append((str(k), str(v)))
    return httpx.Headers(ordered)


def _looks_like_text_html(body: str) -> bool:
    if not body:
        return False
    lowered = body.lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        return True
    sample = body[:512]
    if not sample:
        return False
    printable = sum(1 for ch in sample if ch in string.printable or ch in "\n\r\t")
    ratio = printable / max(1, len(sample))
    return ratio >= 0.85


class _RetryableError(RuntimeError):
    """Raised to trigger a tenacity retry. Inherits RuntimeError for caller compat."""

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


def _build_retrier(config: HttpRuntimeConfig, max_wall_seconds: float | None) -> Retrying:
    def _wait(retry_state: RetryCallState) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        retry_after = getattr(exc, "retry_after_s", None) if exc else None
        backoff = _compute_backoff_s(
            config, retry_state.attempt_number - 1, retry_after_s=retry_after
        )
        if max_wall_seconds is not None and max_wall_seconds > 0:
            elapsed = retry_state.seconds_since_start
            remain = float(max_wall_seconds) - elapsed
            if remain > 0:
                backoff = min(backoff, remain)
            else:
                backoff = 0
        return backoff

    def _before(_retry_state: RetryCallState) -> None:
        _sleep_rate_limit(config.rps)

    stops: list = [stop_after_attempt(config.max_retries)]
    if max_wall_seconds is not None and max_wall_seconds > 0:
        stops.append(stop_after_delay(max_wall_seconds))

    return Retrying(
        stop=stop_any(*stops),
        wait=_wait,
        retry=retry_if_exception_type(_RetryableError),
        before=_before,
        reraise=True,
    )


def fetch_text(url: str, timeout_seconds: int = 25, max_wall_seconds: float | None = None) -> str:
    config, cache, client = _ensure_runtime()
    try:
        meta, cached_body = _read_cache(cache, url)
    except Exception:
        cache = _rebuild_cache_runtime(config, cache)
        meta, cached_body = {}, None

    retrier = _build_retrier(config, max_wall_seconds)
    for attempt in retrier:
        with attempt:
            cond_headers: dict[str, str] = {}
            if config.conditional_cache:
                etag = str(meta.get("etag", "")).strip()
                lm = str(meta.get("last_modified", "")).strip()
                if etag:
                    cond_headers["If-None-Match"] = etag
                if lm:
                    cond_headers["If-Modified-Since"] = lm
            headers = _pick_headers(cond_headers)

            try:
                response = client.get(url, headers=headers, timeout=timeout_seconds)
            except _RETRYABLE_HTTP_ERRORS as exc:
                raise _RetryableError(f"Network error while loading {url}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Network error while loading {url}: {exc}") from exc

            if response.status_code == 304 and cached_body is not None:
                if _looks_like_text_html(cached_body):
                    return cached_body
                meta_key, body_key = _url_cache_keys(url)
                cache.delete(meta_key)
                cache.delete(body_key)

            if response.status_code in _RETRYABLE_STATUS_CODES:
                retry_after_s = _parse_retry_after_seconds(
                    response.headers.get("Retry-After")
                )
                raise _RetryableError(
                    f"HTTP error {response.status_code} while loading: {url}",
                    retry_after_s=retry_after_s,
                )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP error {response.status_code} while loading: {url}"
                )

            body = response.text
            if not _looks_like_text_html(body):
                raise _RetryableError(
                    f"Invalid non-text response while loading: {url}"
                )

            try:
                _write_cache(cache, url, response, body)
            except Exception:
                cache = _rebuild_cache_runtime(config, cache)
                try:
                    _write_cache(cache, url, response, body)
                except Exception:
                    pass
            return body

    raise RuntimeError(f"Failed to load URL after retries: {url}")


def fetch_json(
    url: str,
    timeout_seconds: int = 25,
    max_wall_seconds: float | None = None,
) -> dict | list:
    """GET que retorna JSON parseado. Cache funciona igual a fetch_text()."""
    config, cache, client = _ensure_runtime()
    try:
        meta, cached_body = _read_cache(cache, url)
    except Exception:
        cache = _rebuild_cache_runtime(config, cache)
        meta, cached_body = {}, None

    retrier = _build_retrier(config, max_wall_seconds)
    for attempt in retrier:
        with attempt:
            cond_headers: dict[str, str] = {}
            if config.conditional_cache:
                etag = str(meta.get("etag", "")).strip()
                lm = str(meta.get("last_modified", "")).strip()
                if etag:
                    cond_headers["If-None-Match"] = etag
                if lm:
                    cond_headers["If-Modified-Since"] = lm
            headers = _pick_headers(cond_headers)

            try:
                response = client.get(url, headers=headers, timeout=timeout_seconds)
            except _RETRYABLE_HTTP_ERRORS as exc:
                raise _RetryableError(f"Network error while loading {url}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Network error while loading {url}: {exc}") from exc

            if response.status_code == 304 and cached_body is not None:
                try:
                    return json.loads(cached_body)
                except (ValueError, json.JSONDecodeError):
                    meta_key, body_key = _url_cache_keys(url)
                    cache.delete(meta_key)
                    cache.delete(body_key)

            if response.status_code in _RETRYABLE_STATUS_CODES:
                retry_after_s = _parse_retry_after_seconds(
                    response.headers.get("Retry-After")
                )
                raise _RetryableError(
                    f"HTTP error {response.status_code} while loading: {url}",
                    retry_after_s=retry_after_s,
                )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP error {response.status_code} while loading: {url}"
                )

            body = response.text
            try:
                parsed = json.loads(body)
            except (ValueError, json.JSONDecodeError) as exc:
                raise _RetryableError(f"Invalid JSON response from: {url}") from exc

            # Detectar rate-limit da API Warmane
            if isinstance(parsed, dict) and parsed.get("error") == "Too many requests.":
                raise _RetryableError(
                    f"API rate-limit (Too many requests) from: {url}",
                    retry_after_s=5.0,
                )

            try:
                _write_cache(cache, url, response, body)
            except Exception:
                cache = _rebuild_cache_runtime(config, cache)
                try:
                    _write_cache(cache, url, response, body)
                except Exception:
                    pass
            return parsed

    raise RuntimeError(f"Failed to load JSON after retries: {url}")


def post_form_json(
    url: str,
    form_data: dict[str, str],
    timeout_seconds: int = 25,
    max_wall_seconds: float | None = None,
) -> object:
    config, _, client = _ensure_runtime()

    retrier = _build_retrier(config, max_wall_seconds)
    for attempt in retrier:
        with attempt:
            headers = _pick_headers({
                "Accept": "application/json, text/javascript, */*; q=0.1",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            })

            try:
                response = client.post(
                    url, data=form_data, headers=headers, timeout=timeout_seconds
                )
            except _RETRYABLE_HTTP_ERRORS as exc:
                raise _RetryableError(
                    f"Network error while posting to {url}: {exc}"
                ) from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"Network error while posting to {url}: {exc}"
                ) from exc

            if response.status_code in _RETRYABLE_STATUS_CODES:
                retry_after_s = _parse_retry_after_seconds(
                    response.headers.get("Retry-After")
                )
                raise _RetryableError(
                    f"HTTP error {response.status_code} while posting to: {url}",
                    retry_after_s=retry_after_s,
                )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP error {response.status_code} while posting to: {url}"
                )

            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Invalid JSON response from: {url}") from exc
            return payload

    raise RuntimeError(f"Failed to post after retries: {url}")
