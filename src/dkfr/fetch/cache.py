"""HTML response cache: URL -> data/cache/pulje/<puljeId>/<view>.html + .meta.json.

Human-inspectable paths for the common case (pulje pages), a hash fallback
for anything else. This is the boundary that makes parser iteration free
(spec R2.6) — a cache hit costs nothing and issues no network request.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

PULJE_URL_RE = re.compile(r"^/resultater/pulje/(?P<pulje_id>\d+)/(?P<view>[A-Za-z]+)/?$")


@dataclass(frozen=True)
class CacheMeta:
    url: str
    fetched_at: str  # ISO 8601 UTC instant
    status: int
    elapsed_ms: int
    content_sha256: str
    request_headers: dict[str, str]

    def to_json(self) -> dict:
        return {
            "url": self.url,
            "fetchedAt": self.fetched_at,
            "status": self.status,
            "elapsedMs": self.elapsed_ms,
            "contentSha256": self.content_sha256,
            "requestHeaders": self.request_headers,
        }

    @classmethod
    def from_json(cls, data: dict) -> CacheMeta:
        return cls(
            url=data["url"],
            fetched_at=data["fetchedAt"],
            status=data["status"],
            elapsed_ms=data["elapsedMs"],
            content_sha256=data["contentSha256"],
            request_headers=data.get("requestHeaders", {}),
        )


def _paths_for_url(cache_dir: Path, url: str) -> tuple[Path, Path]:
    """Return (html_path, meta_path) for a URL, without touching disk."""
    parsed = urlparse(url)
    m = PULJE_URL_RE.match(parsed.path)
    if m:
        pulje_id = m.group("pulje_id")
        view = m.group("view")
        base = cache_dir / "pulje" / pulje_id / view
    else:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        base = cache_dir / "misc" / digest
    return base.with_suffix(".html"), Path(str(base) + ".meta.json")


class HtmlCache:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def paths_for(self, url: str) -> tuple[Path, Path]:
        return _paths_for_url(self._cache_dir, url)

    def get(self, url: str) -> tuple[str, CacheMeta] | None:
        html_path, meta_path = self.paths_for(url)
        if not (html_path.exists() and meta_path.exists()):
            return None
        html = html_path.read_text(encoding="utf-8")
        meta = CacheMeta.from_json(json.loads(meta_path.read_text(encoding="utf-8")))
        return html, meta

    def put(
        self,
        url: str,
        html: str,
        status: int,
        elapsed_ms: int,
        request_headers: dict[str, str],
        fetched_at: datetime | None = None,
    ) -> CacheMeta:
        html_path, meta_path = self.paths_for(url)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")

        content_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
        fetched_at = fetched_at or datetime.now(UTC)
        meta = CacheMeta(
            url=url,
            fetched_at=fetched_at.isoformat(),
            status=status,
            elapsed_ms=elapsed_ms,
            content_sha256=content_sha256,
            request_headers=request_headers,
        )
        meta_path.write_text(
            json.dumps(meta.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return meta
