"""Tests for pebbles.scout.candidate."""

import pytest

from pebbles.scout.candidate import (
    Candidate,
    CandidateStatus,
    InvalidCandidateTransitionError,
    VALID_TRANSITIONS,
)


def test_minimal_construction():
    c = Candidate(
        principal_id="harbor",
        cluster_id="maritime_tech",
        source="rss",
        platform="rss",
        target_ref="https://example.com/post/1",
    )
    assert c.principal_id == "harbor"
    assert c.cluster_id == "maritime_tech"
    assert c.status == CandidateStatus.NEW
    assert c.discovered_at is not None
    assert c.candidate_id is None  # not assigned until store.add()


def test_principal_id_required():
    with pytest.raises(ValueError, match="principal_id"):
        Candidate(
            principal_id="",
            cluster_id="x",
            source="rss",
            platform="rss",
            target_ref="https://example.com",
        )


def test_cluster_id_required():
    with pytest.raises(ValueError, match="cluster_id"):
        Candidate(
            principal_id="harbor",
            cluster_id="",
            source="rss",
            platform="rss",
            target_ref="https://example.com",
        )


def test_target_ref_required():
    with pytest.raises(ValueError, match="target_ref"):
        Candidate(
            principal_id="harbor",
            cluster_id="x",
            source="rss",
            platform="rss",
            target_ref="",
        )


def test_relevance_score_clamped():
    Candidate(
        principal_id="harbor",
        cluster_id="x",
        source="rss",
        platform="rss",
        target_ref="https://example.com",
        relevance_score=0.5,
    )
    with pytest.raises(ValueError, match="relevance_score"):
        Candidate(
            principal_id="harbor",
            cluster_id="x",
            source="rss",
            platform="rss",
            target_ref="https://example.com",
            relevance_score=1.5,
        )


def test_valid_transitions_table_completeness():
    """Every CandidateStatus is a key in VALID_TRANSITIONS."""
    for s in CandidateStatus:
        assert s in VALID_TRANSITIONS


def test_terminal_statuses_have_empty_targets():
    """CONSUMED, EXPIRED, REJECTED_FILTER are terminal — no outgoing transitions."""
    assert VALID_TRANSITIONS[CandidateStatus.CONSUMED] == set()
    assert VALID_TRANSITIONS[CandidateStatus.EXPIRED] == set()
    assert VALID_TRANSITIONS[CandidateStatus.REJECTED_FILTER] == set()


def test_invalid_transition_error_message():
    err = InvalidCandidateTransitionError(
        CandidateStatus.NEW, CandidateStatus.NEW, "test-id"
    )
    assert "test-id" in str(err)
    assert "new" in str(err)
