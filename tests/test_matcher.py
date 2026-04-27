"""Tests for pebbles.scout.matcher.RelevanceMatcher."""

import pytest

from pebbles.scout.candidate import Candidate
from pebbles.scout.clusters import Cluster
from pebbles.scout.matcher import (
    RelevanceMatcher,
    RelevanceVerdict,
    SCOUT_RELEVANCE_SYSTEM_PROMPT,
)


class _FakeLLM:
    """Records what was sent, returns canned response."""

    def __init__(self, response):
        self.response = response
        self.last_system = None
        self.last_messages = None

    def complete(self, system, messages, **kwargs):
        raise NotImplementedError("RelevanceMatcher uses complete_json via LLMJudgeRater")

    def complete_json(self, system, messages, schema=None, **kwargs):
        self.last_system = system
        self.last_messages = messages
        return self.response


def make_candidate(cluster_id="maritime_tech"):
    return Candidate(
        principal_id="harbor",
        cluster_id=cluster_id,
        source="rss",
        platform="rss",
        target_ref="https://example.com/post",
        target_content="A new autonomous vessel just launched in the North Sea.",
    )


def make_cluster(cluster_id="maritime_tech"):
    return Cluster(
        cluster_id=cluster_id,
        description="Marine technology, autonomous vessels, ocean instrumentation.",
    )


def test_relevance_verdict_validates_score():
    with pytest.raises(ValueError, match="must be in"):
        RelevanceVerdict(score=1.5, notes="x")
    with pytest.raises(ValueError, match="must be in"):
        RelevanceVerdict(score=-0.1, notes="x")


def test_score_calls_llm_with_scout_prompt():
    llm = _FakeLLM(response={"score": 0.81, "notes": "matches autonomous vessels"})
    matcher = RelevanceMatcher(llm=llm)
    verdict = matcher.score(make_candidate(), make_cluster())
    assert verdict.score == 0.81
    assert "autonomous vessels" in verdict.notes
    # Confirm Scout prompt was used (not the default LLMJudgeRater prompt)
    assert "TOPICAL RELEVANCE" in llm.last_system
    assert llm.last_system == SCOUT_RELEVANCE_SYSTEM_PROMPT


def test_score_includes_cluster_description_in_user_msg():
    llm = _FakeLLM(response={"score": 0.5, "notes": "ok"})
    matcher = RelevanceMatcher(llm=llm)
    cluster = make_cluster()
    matcher.score(make_candidate(), cluster)
    user_msg = llm.last_messages[0]["content"]
    assert cluster.description in user_msg
    assert cluster.cluster_id in user_msg


def test_score_includes_candidate_text_in_user_msg():
    llm = _FakeLLM(response={"score": 0.5, "notes": "ok"})
    matcher = RelevanceMatcher(llm=llm)
    candidate = make_candidate()
    matcher.score(candidate, make_cluster())
    user_msg = llm.last_messages[0]["content"]
    assert "autonomous vessel" in user_msg


def test_cluster_mismatch_raises():
    """Defensive: candidate tagged with one cluster, scoring against another."""
    llm = _FakeLLM(response={"score": 0.5, "notes": "ok"})
    matcher = RelevanceMatcher(llm=llm)
    candidate = make_candidate(cluster_id="alpha")
    cluster = make_cluster(cluster_id="beta")
    with pytest.raises(ValueError, match="cluster mismatch"):
        matcher.score(candidate, cluster)
