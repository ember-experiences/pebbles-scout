"""Composition test — full Scout pipeline end-to-end with reference impls.

Walks: Source → Filter → RelevanceMatcher → CandidateStore + side-channel
ProposalFlow → ApprovalChannel → WatchlistStore.

No real LLM calls (uses _FakeLLM); no network (RSS patched). Proves the
pipeline composes against the v0.2 substrate (Principal, ApprovalChannel,
LLMAdapter, MetricsEmitter) without coupling.
"""

from unittest.mock import patch

import pytest

from pebbles.core.approval import ApprovalAction, MockApprovalChannel
from pebbles.core.metrics import InMemoryMetrics
from pebbles.core.principal import Principal

from pebbles.scout.candidate import CandidateStatus
from pebbles.scout.candidate_store import InMemoryCandidateStore
from pebbles.scout.filters import PassThroughFilter
from pebbles.scout.matcher import RelevanceMatcher
from pebbles.scout.principal import ScoutPrincipalConfig
from pebbles.scout.sources.rss import RssSource
from pebbles.scout.watchlist import InMemoryWatchlistStore, ProposalFlow


SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Maritime News</title>
  <item>
    <title>Autonomous Vessel Crosses North Atlantic</title>
    <link>https://example.com/maritime/1</link>
    <description>A new autonomous vessel completed an unmanned crossing.</description>
    <guid>https://example.com/maritime/1</guid>
  </item>
</channel>
</rss>
"""


class _FakeLLM:
    """Returns a canned relevance score so tests are deterministic."""

    def __init__(self, score=0.72, notes="canned response"):
        self.score = score
        self.notes = notes

    def complete(self, system, messages, **kwargs):
        raise NotImplementedError

    def complete_json(self, system, messages, schema=None, **kwargs):
        return {"score": self.score, "notes": self.notes}


@pytest.fixture
def harbor_principal(tmp_path):
    yaml_path = tmp_path / "harbor.yaml"
    yaml_path.write_text(
        """id: harbor
name: Harbor
mode: ai_persona
extra:
  scout:
    relevance_threshold: 0.6
    clusters:
      - cluster_id: maritime_tech
        description: Marine technology, autonomous vessels, ocean instrumentation
    sources:
      rss:
        feeds:
          - url: https://example.com/maritime.xml
            cluster: maritime_tech
"""
    )
    return Principal.from_yaml(yaml_path)


def _patched_feedparser():
    import feedparser
    real = feedparser.parse

    def fake(url_or_data, *args, **kwargs):
        if isinstance(url_or_data, str) and url_or_data.startswith("http"):
            return real(SAMPLE_FEED)
        return real(url_or_data, *args, **kwargs)

    return patch("pebbles.scout.sources.rss.feedparser.parse", side_effect=fake)


def test_pipeline_emits_above_threshold(harbor_principal):
    """Source -> Filter -> Matcher -> CandidateStore: above threshold ends in store with status=NEW."""
    config = ScoutPrincipalConfig.from_principal(harbor_principal)
    metrics = InMemoryMetrics()
    store = InMemoryCandidateStore()
    pre_filter = PassThroughFilter()
    matcher = RelevanceMatcher(llm=_FakeLLM(score=0.72))  # above threshold of 0.6
    rss = RssSource.from_config(config.sources)

    with _patched_feedparser():
        raw_candidates = rss.fetch(harbor_principal.id, config.clusters)

    for c in raw_candidates:
        keep, reason = pre_filter.keep(c)
        if not keep:
            metrics.emit(harbor_principal.id, "rejected_filter", metadata={"reason": reason})
            continue
        cluster = config.cluster_by_id(c.cluster_id)
        verdict = matcher.score(c, cluster)
        metrics.emit(harbor_principal.id, "rated", value=verdict.score)
        if verdict.score < config.relevance_threshold:
            metrics.emit(harbor_principal.id, "below_threshold", value=verdict.score)
            continue
        c.relevance_score = verdict.score
        c.relevance_notes = verdict.notes
        cid = store.add(c)
        metrics.emit(harbor_principal.id, "candidate_emitted", value=verdict.score, metadata={"id": cid})

    emitted = store.list(harbor_principal.id)
    assert len(emitted) == 1
    assert emitted[0].status == CandidateStatus.NEW
    assert emitted[0].relevance_score == 0.72
    assert emitted[0].cluster_id == "maritime_tech"

    # Metrics fan-in observed every step
    types = {e["metric_type"] for e in metrics.events}
    assert {"rated", "candidate_emitted"}.issubset(types)


def test_pipeline_drops_below_threshold(harbor_principal):
    """Items below the relevance threshold do NOT land in the store."""
    config = ScoutPrincipalConfig.from_principal(harbor_principal)
    store = InMemoryCandidateStore()
    matcher = RelevanceMatcher(llm=_FakeLLM(score=0.40))  # below 0.6
    rss = RssSource.from_config(config.sources)
    pre_filter = PassThroughFilter()

    with _patched_feedparser():
        raw = rss.fetch(harbor_principal.id, config.clusters)

    for c in raw:
        keep, _ = pre_filter.keep(c)
        if not keep:
            continue
        cluster = config.cluster_by_id(c.cluster_id)
        verdict = matcher.score(c, cluster)
        if verdict.score < config.relevance_threshold:
            continue
        c.relevance_score = verdict.score
        store.add(c)

    assert store.list(harbor_principal.id) == []


def test_consumer_consumes_emitted_candidate(harbor_principal):
    """A downstream consumer (e.g. Presence) marks a candidate as consumed."""
    store = InMemoryCandidateStore()
    config = ScoutPrincipalConfig.from_principal(harbor_principal)

    matcher = RelevanceMatcher(llm=_FakeLLM(score=0.85))
    rss = RssSource.from_config(config.sources)
    with _patched_feedparser():
        for c in rss.fetch(harbor_principal.id, config.clusters):
            cluster = config.cluster_by_id(c.cluster_id)
            verdict = matcher.score(c, cluster)
            c.relevance_score = verdict.score
            store.add(c)

    new_items = store.list(harbor_principal.id, status=CandidateStatus.NEW)
    assert len(new_items) == 1
    cid = new_items[0].candidate_id

    store.transition(
        cid,
        CandidateStatus.CONSUMED,
        consumed_by="pebbles-presence",
        consumed_at="2026-04-26T00:00:00Z",
    )
    item = store.get(cid)
    assert item.status == CandidateStatus.CONSUMED
    assert item.consumed_by == "pebbles-presence"


def test_principal_proposes_account_via_approval_flow(harbor_principal):
    """Side-channel: principal proposes via [SCOUT_OBSERVE], operator approves via ApprovalChannel."""
    store = InMemoryWatchlistStore()
    ch = MockApprovalChannel()
    flow = ProposalFlow(store=store, approval_channel=ch, operator="lucky")

    aid = flow.principal_propose(
        principal_id=harbor_principal.id,
        cluster_id="maritime_tech",
        handle="@maritime_researcher",
        reason="thoughtful threads on autonomous shipping",
    )
    assert store.get(aid).status == "pending_approval"
    assert len(ch.sent) == 1

    ch.simulate_decision(aid, ApprovalAction.APPROVE, approver="lucky")
    assert store.get(aid).status == "active"


def test_metrics_observes_without_coupling():
    """MetricsEmitter is fan-in only — no Scout primitive depends on metrics
    being wired."""
    # CandidateStore works without metrics
    store = InMemoryCandidateStore()
    from pebbles.scout.candidate import Candidate
    cid = store.add(
        Candidate(
            principal_id="x",
            cluster_id="y",
            source="rss",
            platform="rss",
            target_ref="https://example.com",
        )
    )
    assert store.get(cid) is not None

    # WatchlistStore works without metrics
    ws = InMemoryWatchlistStore()
    flow = ProposalFlow(store=ws)
    aid = flow.operator_propose(principal_id="x", cluster_id="y", handle="@a")
    assert ws.get(aid) is not None
