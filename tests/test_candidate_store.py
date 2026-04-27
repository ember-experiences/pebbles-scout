"""Tests for pebbles.scout.candidate_store.InMemoryCandidateStore."""

import pytest

from pebbles.scout.candidate import (
    Candidate,
    CandidateStatus,
    InvalidCandidateTransitionError,
)
from pebbles.scout.candidate_store import (
    CandidateStore,
    InMemoryCandidateStore,
)


def make_candidate(**overrides):
    defaults = dict(
        principal_id="harbor",
        cluster_id="maritime_tech",
        source="rss",
        platform="rss",
        target_ref="https://example.com/post",
        target_content="Test content",
    )
    defaults.update(overrides)
    return Candidate(**defaults)


def test_add_returns_id():
    s = InMemoryCandidateStore()
    cid = s.add(make_candidate())
    assert isinstance(cid, str) and len(cid) > 0


def test_add_assigns_candidate_id():
    s = InMemoryCandidateStore()
    cid = s.add(make_candidate())
    item = s.get(cid)
    assert item is not None
    assert item.candidate_id == cid


def test_get_returns_none_for_unknown():
    s = InMemoryCandidateStore()
    assert s.get("nonexistent") is None


def test_get_returns_deep_copy():
    s = InMemoryCandidateStore()
    cid = s.add(make_candidate())
    item = s.get(cid)
    item.metadata["leaked"] = True
    fresh = s.get(cid)
    assert "leaked" not in fresh.metadata


def test_valid_transition_new_to_consumed():
    s = InMemoryCandidateStore()
    cid = s.add(make_candidate())
    assert (
        s.transition(
            cid,
            CandidateStatus.CONSUMED,
            consumed_by="pebbles-presence",
            consumed_at="2026-04-26T00:00:00Z",
        )
        is True
    )
    item = s.get(cid)
    assert item.status == CandidateStatus.CONSUMED
    assert item.consumed_by == "pebbles-presence"


def test_invalid_transition_raises():
    s = InMemoryCandidateStore()
    cid = s.add(make_candidate())
    s.transition(cid, CandidateStatus.CONSUMED)
    # CONSUMED is terminal
    with pytest.raises(InvalidCandidateTransitionError):
        s.transition(cid, CandidateStatus.NEW)


def test_transition_unknown_id_raises_keyerror():
    s = InMemoryCandidateStore()
    with pytest.raises(KeyError):
        s.transition("nonexistent", CandidateStatus.CONSUMED)


def test_list_filters_by_principal():
    s = InMemoryCandidateStore()
    s.add(make_candidate(principal_id="harbor"))
    s.add(make_candidate(principal_id="harbor"))
    s.add(make_candidate(principal_id="other"))
    assert len(s.list("harbor")) == 2
    assert len(s.list("other")) == 1


def test_list_filters_by_status():
    s = InMemoryCandidateStore()
    a = s.add(make_candidate())
    s.add(make_candidate())
    s.transition(a, CandidateStatus.CONSUMED)
    new_items = s.list("harbor", status=CandidateStatus.NEW)
    consumed = s.list("harbor", status=CandidateStatus.CONSUMED)
    assert len(new_items) == 1
    assert len(consumed) == 1
    assert consumed[0].candidate_id == a


def test_list_filters_by_cluster():
    s = InMemoryCandidateStore()
    s.add(make_candidate(cluster_id="alpha"))
    s.add(make_candidate(cluster_id="beta"))
    alpha = s.list("harbor", cluster_id="alpha")
    assert len(alpha) == 1
    assert alpha[0].cluster_id == "alpha"


def test_list_orders_newest_first():
    import time

    s = InMemoryCandidateStore()
    a = s.add(make_candidate())
    time.sleep(0.001)
    b = s.add(make_candidate())
    items = s.list("harbor")
    assert items[0].candidate_id == b
    assert items[1].candidate_id == a


def test_inmemory_satisfies_protocol():
    """Runtime check (Protocol is structural here)."""
    s: CandidateStore = InMemoryCandidateStore()  # type: ignore[assignment]
    assert hasattr(s, "add")
    assert hasattr(s, "get")
    assert hasattr(s, "transition")
    assert hasattr(s, "list")
