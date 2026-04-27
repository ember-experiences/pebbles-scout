"""RssSource — cluster-aware RSS feed monitoring.

Configuration shape (from principal.extra.scout.sources.rss):

    sources:
      rss:
        feeds:
          - url: https://example.com/feed.xml
            cluster: maritime_tech     # which cluster this feed belongs to
          - url: https://other.com/rss.xml
            cluster: ocean_ecology

A feed maps to exactly one cluster. Items from that feed are tagged with
that cluster_id.

Deduplication: each call to fetch() returns only entries with `entry.id`
(or `entry.link` as fallback) not seen before. Seen-state is stored in
the source instance — pass an existing instance across runs to preserve
dedup memory, or wrap with persistent storage (e.g. pebbles-core's
JsonStorage) for cross-process dedup. v0.1 ships with in-memory only.
"""

import logging
from typing import Optional

import feedparser

from pebbles.scout.candidate import Candidate
from pebbles.scout.clusters import Cluster

logger = logging.getLogger(__name__)


class RssSource:
    """Fetch new items from RSS feeds, tagged with their configured cluster."""

    def __init__(self, feeds: list[dict]):
        """Initialize with a list of feed configs.

        Each feed config: {"url": str, "cluster": str}
        """
        if not feeds:
            raise ValueError("RssSource requires at least one feed")
        for f in feeds:
            if "url" not in f or "cluster" not in f:
                raise ValueError(
                    f"RSS feed config requires 'url' and 'cluster': {f}"
                )
        self.feeds = feeds
        self._seen_ids: set[str] = set()

    def fetch(self, principal_id: str, clusters: list[Cluster]) -> list[Candidate]:
        """Fetch new entries from all configured feeds.

        Drops feeds whose configured cluster isn't in the principal's enabled
        clusters (logs warning). Returns only entries not seen on prior calls
        to this source instance.
        """
        enabled_cluster_ids = {c.cluster_id for c in clusters if c.enabled}
        candidates: list[Candidate] = []

        for feed_cfg in self.feeds:
            cluster_id = feed_cfg["cluster"]
            url = feed_cfg["url"]

            if cluster_id not in enabled_cluster_ids:
                logger.warning(
                    f"RSS feed {url} configured for cluster '{cluster_id}' "
                    f"not in principal's enabled clusters; skipping"
                )
                continue

            try:
                parsed = feedparser.parse(url)
            except Exception as e:
                logger.error(f"Failed to fetch RSS feed {url}: {e}")
                continue

            if parsed.bozo and not parsed.entries:
                logger.warning(
                    f"RSS feed {url} returned malformed content with no entries; skipping"
                )
                continue

            for entry in parsed.entries:
                entry_id = self._entry_id(entry)
                if not entry_id:
                    continue
                if entry_id in self._seen_ids:
                    continue
                self._seen_ids.add(entry_id)

                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                link = entry.get("link", entry_id)

                content = title
                if summary:
                    content = f"{title}\n\n{summary}"

                candidates.append(
                    Candidate(
                        principal_id=principal_id,
                        cluster_id=cluster_id,
                        source="rss",
                        platform="rss",
                        target_ref=link,
                        target_content=content,
                        target_author=entry.get("author"),
                        metadata={
                            "feed_url": url,
                            "entry_id": entry_id,
                            "published": entry.get("published"),
                        },
                    )
                )

        logger.info(
            f"RssSource fetched {len(candidates)} new candidates across {len(self.feeds)} feeds"
        )
        return candidates

    @staticmethod
    def _entry_id(entry) -> Optional[str]:
        """Best stable id for dedup."""
        return entry.get("id") or entry.get("link") or entry.get("title")

    @classmethod
    def from_config(cls, sources_config: dict) -> Optional["RssSource"]:
        """Construct from the principal's `extra.scout.sources` block.

        Returns None if no `rss` config present. Caller decides whether
        absence is an error or just "RSS not enabled for this principal."
        """
        rss_cfg = sources_config.get("rss")
        if not rss_cfg:
            return None
        feeds = rss_cfg.get("feeds", [])
        if not feeds:
            return None
        return cls(feeds=feeds)
