"""robots.txt compliance (spec R2.5 / AC5).

Every URL is checked against dbu.dk's robots.txt before a request is made.
A disallowed URL raises — it is never silently skipped, because a silent
skip could hide a manifest/discovery bug. We also hard-code the two paths
the spec explicitly calls out (C1) as a defense-in-depth belt-and-braces
check, in case robots.txt itself is ever unreachable or changes shape.
"""

from __future__ import annotations

import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx

# Defense in depth: the spec explicitly names these as disallowed (C1/R2.5).
# Checked unconditionally, in addition to (not instead of) the live robots.txt.
HARD_DISALLOWED_PATH_PREFIXES: tuple[str, ...] = (
    "/resultater/kampsoegAdvanceret/",
    "/turneringer_og_resultater/resultatsoegning/",
)


class RobotsDisallowedError(RuntimeError):
    """Raised when a URL is disallowed by robots.txt or the hard-coded deny list."""


class RobotsChecker:
    """Wraps urllib.robotparser for a single base host, fetched once and cached."""

    def __init__(self, base_url: str, user_agent: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._parser = urllib.robotparser.RobotFileParser()
        self._parser.set_url(urljoin(self._base_url + "/", "robots.txt"))
        self._loaded = False

    def load(self) -> None:
        """Fetch robots.txt ourselves via httpx with our own honest UA.

        Deliberately NOT using RobotFileParser.read() — it fetches via
        urllib.request with urllib's default "Python-urllib/x.y" User-Agent,
        which dbu.dk returns 403 Forbidden for (confirmed empirically). A 401/403
        response makes RobotFileParser set disallow_all=True, which would make
        every URL look disallowed even though robots.txt itself permits it for a
        normal, honestly-identified client. Fetching with our real UA avoids that
        false negative entirely.
        """
        robots_url = urljoin(self._base_url + "/", "robots.txt")
        try:
            response = httpx.get(
                robots_url, headers={"User-Agent": self._user_agent}, timeout=10.0
            )
            if response.status_code >= 400:
                # Match RobotFileParser's own convention: 4xx (other than
                # explicit auth-denied) -> allow all; we go one step more
                # conservative and only allow-all, never disallow-all, on
                # fetch failure, since disallow-all would silently break the
                # whole pipeline on a transient robots.txt hiccup.
                self._parser.allow_all = True
            else:
                self._parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            self._parser.allow_all = True
        self._loaded = True

    def load_from_text(self, text: str) -> None:
        """Used by tests to avoid a real network fetch of robots.txt."""
        self._parser.parse(text.splitlines())
        self._loaded = True

    def check(self, url: str) -> None:
        """Raise RobotsDisallowedError if `url` may not be fetched. No-op otherwise."""
        path = urlparse(url).path
        for prefix in HARD_DISALLOWED_PATH_PREFIXES:
            if path.startswith(prefix):
                raise RobotsDisallowedError(
                    f"{url!r} matches a hard-coded disallowed prefix {prefix!r}"
                )

        if not self._loaded:
            self.load()

        if not self._parser.can_fetch(self._user_agent, url):
            raise RobotsDisallowedError(f"robots.txt disallows fetching {url!r}")
