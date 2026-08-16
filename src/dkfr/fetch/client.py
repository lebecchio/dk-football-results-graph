"""The polite, serial, cached HTTP fetcher (spec R2.3-R2.8, AC5/AC6/AC7).

- Serial, ≥2.0s gate between actual *network* requests only — cache hits are free.
- Retries with exponential backoff (3x: 5/15/45s) on 429/5xx/timeout, honouring
  Retry-After when present.
- A 404 on a request the caller marks `critical=True` (i.e. a manifest pulje) is a
  fatal error, not a silent skip (R2.7).
- Every URL is robots-checked before any network request (AC5), and restricted to
  an explicit allow-list of path prefixes (R2.8 — no assets, ever).
- Every network request (and cache hit) is appended to data/logs/requests-<runid>.jsonl
  for AC5/AC6 evidence.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from dkfr.fetch.cache import CacheMeta, HtmlCache
from dkfr.fetch.robots import RobotsChecker

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised for a non-retryable failure, or after retries are exhausted."""


class DisallowedPathError(RuntimeError):
    """Raised when a URL's path is outside the configured allow-list."""


@dataclass
class FetchResult:
    url: str
    html: str
    meta: CacheMeta
    from_cache: bool


class RequestLog:
    def __init__(self, logs_dir: Path, run_id: str | None = None) -> None:
        self._run_id = run_id or uuid.uuid4().hex[:8]
        self._path = logs_dir / f"requests-{self._run_id}.jsonl"
        logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def record(self, **fields) -> None:
        entry = {"loggedAt": datetime.now(UTC).isoformat(), **fields}
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")


class Fetcher:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        cache: HtmlCache,
        request_log: RequestLog,
        allowed_path_prefixes: tuple[str, ...],
        min_interval_seconds: float = 2.0,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 5.0,
        robots_checker: RobotsChecker | None = None,
        sleep_fn=time.sleep,
        clock_fn=time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._cache = cache
        self._log = request_log
        self._allowed_path_prefixes = allowed_path_prefixes
        self._min_interval = min_interval_seconds
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay_seconds
        self._robots = robots_checker or RobotsChecker(base_url, user_agent)
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._last_request_at: float | None = None
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _check_allowed(self, url: str) -> None:
        path = urlparse(url).path
        if not any(path.startswith(p) for p in self._allowed_path_prefixes):
            raise DisallowedPathError(
                f"{url!r} path {path!r} is not in the configured allow-list "
                f"{self._allowed_path_prefixes!r}"
            )
        self._robots.check(url)

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._clock() - self._last_request_at
        remaining = self._min_interval - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def fetch(
        self, url: str, *, critical: bool = False, force_refresh: bool = False
    ) -> FetchResult:
        """Fetch `url`, using the cache unless force_refresh is set.

        `critical=True` marks this as a required manifest pulje: a 404 is fatal
        (raises FetchError) rather than a value the caller might silently skip.
        """
        self._check_allowed(url)

        if not force_refresh:
            cached = self._cache.get(url)
            if cached is not None:
                html, meta = cached
                self._log.record(url=url, event="cache_hit", status=meta.status)
                return FetchResult(url=url, html=html, meta=meta, from_cache=True)

        html, meta = self._fetch_with_retries(url, critical=critical)
        return FetchResult(url=url, html=html, meta=meta, from_cache=False)

    def _fetch_with_retries(self, url: str, *, critical: bool) -> tuple[str, CacheMeta]:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self._max_retries:
            self._throttle()
            start = self._clock()
            try:
                headers = {"User-Agent": self._user_agent}
                response = self._client.get(url, headers=headers)
                elapsed_ms = int((self._clock() - start) * 1000)
                self._last_request_at = self._clock()

                self._log.record(
                    url=url,
                    event="network_request",
                    status=response.status_code,
                    attempt=attempt,
                    elapsedMs=elapsed_ms,
                    userAgent=self._user_agent,
                )

                if response.status_code == 404:
                    if critical:
                        raise FetchError(f"404 fetching required pulje URL {url!r}")
                    raise FetchError(f"404 fetching {url!r}")

                if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                    delay = self._retry_delay(response, attempt)
                    self._log.record(url=url, event="retry_scheduled", delaySeconds=delay)
                    self._sleep(delay)
                    attempt += 1
                    continue

                if response.status_code >= 400:
                    raise FetchError(f"HTTP {response.status_code} fetching {url!r}")

                meta = self._cache.put(
                    url=url,
                    html=response.text,
                    status=response.status_code,
                    elapsed_ms=elapsed_ms,
                    request_headers=headers,
                )
                return response.text, meta

            except httpx.TimeoutException as exc:
                last_exc = exc
                self._last_request_at = self._clock()
                self._log.record(url=url, event="timeout", attempt=attempt)
                if attempt >= self._max_retries:
                    raise FetchError(
                        f"Timeout fetching {url!r} after {attempt + 1} attempts"
                    ) from exc
                delay = self._retry_base_delay * (3**attempt)
                self._sleep(delay)
                attempt += 1

        raise FetchError(f"Exhausted retries fetching {url!r}") from last_exc

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return self._retry_base_delay * (3**attempt)
