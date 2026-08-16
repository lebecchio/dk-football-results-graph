"""Convenience factory: build a Fetcher wired up from Settings."""

from __future__ import annotations

from dkfr.config import Settings
from dkfr.fetch.cache import HtmlCache
from dkfr.fetch.client import Fetcher, RequestLog
from dkfr.fetch.robots import RobotsChecker


def build_fetcher(settings: Settings, run_id: str | None = None) -> Fetcher:
    cache = HtmlCache(settings.cache_dir)
    request_log = RequestLog(settings.logs_dir, run_id=run_id)
    robots = RobotsChecker(settings.base_url, settings.user_agent())
    return Fetcher(
        base_url=settings.base_url,
        user_agent=settings.user_agent(),
        cache=cache,
        request_log=request_log,
        allowed_path_prefixes=settings.allowed_path_prefixes,
        min_interval_seconds=settings.min_request_interval_seconds,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
        robots_checker=robots,
    )
