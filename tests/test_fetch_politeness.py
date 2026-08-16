"""Fetch/cache layer politeness tests — spec AC5/AC6/AC7.

Uses pytest_httpx to mock the network entirely; no real requests are made here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dkfr.fetch.cache import HtmlCache
from dkfr.fetch.client import DisallowedPathError, Fetcher, RequestLog
from dkfr.fetch.robots import RobotsChecker, RobotsDisallowedError

BASE_URL = "https://www.dbu.dk"
USER_AGENT = "dk-football-results-graph/1.0 (personal research; contact: test@example.com)"

ROBOTS_TXT = """
User-agent: *
Disallow: /resultater/kampsoegAdvanceret/
Disallow: /turneringer_og_resultater/resultatsoegning/
""".strip()

ALLOWED_PREFIXES = ("/resultater/pulje/", "/resultater/raekke/", "/resultater/Raekke/")


@pytest.fixture
def tmp_env(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    logs_dir = tmp_path / "logs"
    cache = HtmlCache(cache_dir)
    log = RequestLog(logs_dir, run_id="test")
    robots = RobotsChecker(BASE_URL, USER_AGENT)
    robots.load_from_text(ROBOTS_TXT)
    return cache, log, robots, logs_dir


def make_fetcher(
    tmp_env, sleep_calls: list[float] | None = None, clock_start: float = 0.0, **kwargs
):
    cache, log, robots, _ = tmp_env
    clock_state = {"t": clock_start}

    def clock_fn():
        return clock_state["t"]

    def sleep_fn(seconds: float):
        if sleep_calls is not None:
            sleep_calls.append(seconds)
        clock_state["t"] += seconds

    fetcher = Fetcher(
        base_url=BASE_URL,
        user_agent=USER_AGENT,
        cache=cache,
        request_log=log,
        allowed_path_prefixes=ALLOWED_PREFIXES,
        min_interval_seconds=2.0,
        max_retries=3,
        retry_base_delay_seconds=5.0,
        robots_checker=robots,
        sleep_fn=sleep_fn,
        clock_fn=clock_fn,
    )
    # Advancing the clock on real network calls (httpx_mock intercepts before
    # any real socket I/O) simulates elapsed time deterministically.
    return fetcher, clock_state


def test_disallowed_path_raises_before_any_request(tmp_env, httpx_mock):
    fetcher, _ = make_fetcher(tmp_env)
    with pytest.raises((RobotsDisallowedError, DisallowedPathError)):
        fetcher.fetch(f"{BASE_URL}/resultater/kampsoegAdvanceret/?q=foo")
    # No mocked request should have been registered/consumed.
    assert len(httpx_mock.get_requests()) == 0


def test_disallowed_legacy_search_path_raises(tmp_env, httpx_mock):
    fetcher, _ = make_fetcher(tmp_env)
    with pytest.raises((RobotsDisallowedError, DisallowedPathError)):
        fetcher.fetch(f"{BASE_URL}/turneringer_og_resultater/resultatsoegning/?q=foo")
    assert len(httpx_mock.get_requests()) == 0


def test_path_outside_allowlist_raises(tmp_env, httpx_mock):
    fetcher, _ = make_fetcher(tmp_env)
    with pytest.raises(DisallowedPathError):
        fetcher.fetch(f"{BASE_URL}/some/other/path/")
    assert len(httpx_mock.get_requests()) == 0


def test_user_agent_is_honest_and_not_a_browser_spoof(tmp_env, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/resultater/pulje/1/kampprogramFuld",
        html="<html>ok</html>",
    )
    fetcher, _ = make_fetcher(tmp_env)
    fetcher.fetch(f"{BASE_URL}/resultater/pulje/1/kampprogramFuld")
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    ua = requests[0].headers["User-Agent"]
    assert "dk-football-results-graph" in ua
    assert "test@example.com" in ua
    for browser_token in ("Mozilla", "Chrome", "Safari", "AppleWebKit"):
        assert browser_token not in ua


def test_consecutive_network_requests_are_at_least_min_interval_apart(tmp_env, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/resultater/pulje/1/kampprogramFuld", html="<html>a</html>"
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/resultater/pulje/2/kampprogramFuld", html="<html>b</html>"
    )
    sleep_calls: list[float] = []
    fetcher, clock_state = make_fetcher(tmp_env, sleep_calls=sleep_calls)

    fetcher.fetch(f"{BASE_URL}/resultater/pulje/1/kampprogramFuld")
    t_after_first = clock_state["t"]
    fetcher.fetch(f"{BASE_URL}/resultater/pulje/2/kampprogramFuld")
    t_after_second = clock_state["t"]

    assert t_after_second - t_after_first >= 2.0


def test_cache_hit_issues_zero_network_requests(tmp_env, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/resultater/pulje/1/kampprogramFuld", html="<html>a</html>"
    )
    fetcher, _ = make_fetcher(tmp_env)

    first = fetcher.fetch(f"{BASE_URL}/resultater/pulje/1/kampprogramFuld")
    assert not first.from_cache

    second = fetcher.fetch(f"{BASE_URL}/resultater/pulje/1/kampprogramFuld")
    assert second.from_cache
    assert second.html == first.html

    # Only one real network request should ever have hit httpx_mock.
    assert len(httpx_mock.get_requests()) == 1


def test_404_on_critical_fetch_is_fatal(tmp_env, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/resultater/pulje/999999/kampprogramFuld", status_code=404
    )
    fetcher, _ = make_fetcher(tmp_env)
    from dkfr.fetch.client import FetchError

    with pytest.raises(FetchError):
        fetcher.fetch(f"{BASE_URL}/resultater/pulje/999999/kampprogramFuld", critical=True)


def test_request_log_records_evidence(tmp_env, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/resultater/pulje/1/kampprogramFuld", html="<html>a</html>"
    )
    fetcher, _ = make_fetcher(tmp_env)
    fetcher.fetch(f"{BASE_URL}/resultater/pulje/1/kampprogramFuld")

    _, _, _, logs_dir = tmp_env
    log_files = list(logs_dir.glob("requests-*.jsonl"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "network_request" in content
    assert "userAgent" in content
