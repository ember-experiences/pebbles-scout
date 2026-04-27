"""Tests for pebbles.scout.sources.rss.RssSource.

Tests use feedparser's parsing on string input — feedparser.parse() accepts
string content directly, so we can build fixtures without network calls.
"""

from unittest.mock import patch

import pytest

from pebbles.scout.clusters import Cluster
from pebbles.scout.sources.rss import RssSource


SAMPLE_FEED_A = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Maritime News</title>
  <item>
    <title>Autonomous Vessel Crosses North Atlantic</title>
    <link>https://example.com/maritime/1</link>
    <description>A new autonomous vessel completed an unmanned crossing.</description>
    <guid>https://example.com/maritime/1</guid>
  </item>
  <item>
    <title>Port Automation Reaches New Milestone</title>
    <link>https://example.com/maritime/2</link>
    <description>Robotic cranes now handle 80% of throughput at major ports.</description>
    <guid>https://example.com/maritime/2</guid>
  </item>
</channel>
</rss>
"""

SAMPLE_FEED_B = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Ocean Ecology</title>
  <item>
    <title>Coral Reef Recovery in the Pacific</title>
    <link>https://example.com/ecology/1</link>
    <description>Reef systems showing partial recovery after thermal stress.</description>
    <guid>https://example.com/ecology/1</guid>
  </item>
</channel>
</rss>
"""


def _patched_feedparser():
    """Return a context manager that maps feed URLs to canned XML."""
    import feedparser

    real_parse = feedparser.parse

    def fake_parse(url_or_data, *args, **kwargs):
        if isinstance(url_or_data, str) and url_or_data.startswith("http"):
            if "maritime" in url_or_data:
                return real_parse(SAMPLE_FEED_A)
            if "ecology" in url_or_data:
                return real_parse(SAMPLE_FEED_B)
            return real_parse("")  # empty feed for unknown URLs
        return real_parse(url_or_data, *args, **kwargs)

    return patch("pebbles.scout.sources.rss.feedparser.parse", side_effect=fake_parse)


def test_rss_requires_feeds():
    with pytest.raises(ValueError, match="at least one feed"):
        RssSource(feeds=[])


def test_rss_requires_url_and_cluster():
    with pytest.raises(ValueError, match="url.*cluster"):
        RssSource(feeds=[{"url": "https://x.com/feed"}])
    with pytest.raises(ValueError, match="url.*cluster"):
        RssSource(feeds=[{"cluster": "x"}])


def test_rss_fetches_per_cluster():
    feeds = [
        {"url": "https://example.com/maritime.xml", "cluster": "maritime_tech"},
        {"url": "https://example.com/ecology.xml", "cluster": "ocean_ecology"},
    ]
    clusters = [
        Cluster(cluster_id="maritime_tech", description="Marine tech"),
        Cluster(cluster_id="ocean_ecology", description="Marine biology"),
    ]
    source = RssSource(feeds=feeds)

    with _patched_feedparser():
        candidates = source.fetch("harbor", clusters)

    assert len(candidates) == 3  # 2 from maritime, 1 from ecology

    by_cluster = {}
    for c in candidates:
        by_cluster.setdefault(c.cluster_id, []).append(c)

    assert len(by_cluster["maritime_tech"]) == 2
    assert len(by_cluster["ocean_ecology"]) == 1
    # Verify content + cluster tagging
    titles = [c.target_content.split("\n")[0] for c in by_cluster["maritime_tech"]]
    assert "Autonomous Vessel Crosses North Atlantic" in titles


def test_rss_dedups_across_calls():
    feeds = [{"url": "https://example.com/maritime.xml", "cluster": "maritime_tech"}]
    clusters = [Cluster(cluster_id="maritime_tech", description="Marine tech")]
    source = RssSource(feeds=feeds)

    with _patched_feedparser():
        first = source.fetch("harbor", clusters)
        second = source.fetch("harbor", clusters)

    assert len(first) == 2
    assert len(second) == 0  # all dedup'd


def test_rss_skips_disabled_clusters():
    feeds = [{"url": "https://example.com/maritime.xml", "cluster": "maritime_tech"}]
    clusters = [Cluster(cluster_id="maritime_tech", description="d", enabled=False)]
    source = RssSource(feeds=feeds)

    with _patched_feedparser():
        candidates = source.fetch("harbor", clusters)
    assert candidates == []


def test_rss_skips_unknown_clusters():
    """Feed mapped to a cluster not in principal's enabled list is skipped, not crashed."""
    feeds = [
        {"url": "https://example.com/maritime.xml", "cluster": "maritime_tech"},
        {"url": "https://example.com/ecology.xml", "cluster": "deep_sea"},  # not in principal
    ]
    clusters = [Cluster(cluster_id="maritime_tech", description="d")]
    source = RssSource(feeds=feeds)

    with _patched_feedparser():
        candidates = source.fetch("harbor", clusters)
    # Only maritime's items, not ecology's
    assert all(c.cluster_id == "maritime_tech" for c in candidates)
    assert len(candidates) == 2


def test_rss_from_config_returns_none_if_absent():
    assert RssSource.from_config({}) is None
    assert RssSource.from_config({"rss": {}}) is None
    assert RssSource.from_config({"rss": {"feeds": []}}) is None


def test_rss_from_config_constructs():
    src = RssSource.from_config({
        "rss": {"feeds": [{"url": "https://x.com/f.xml", "cluster": "c"}]}
    })
    assert src is not None
    assert src.feeds == [{"url": "https://x.com/f.xml", "cluster": "c"}]
