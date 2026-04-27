"""Tests for pebbles.scout.watchlist — store, account, ProposalFlow."""

import pytest

from pebbles.core.approval import (
    ApprovalAction,
    ApprovalDecision,
    MockApprovalChannel,
)

from pebbles.scout.watchlist import (
    InMemoryWatchlistStore,
    ProposalFlow,
    WatchlistAccount,
)


# -- WatchlistAccount validation -----------------------------------------------


def test_account_minimal_construction():
    a = WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@y")
    assert a.principal_id == "harbor"
    assert a.platform == "twitter"
    assert a.status == "active"
    assert a.proposed_by == "operator"


def test_account_invalid_status_rejected():
    with pytest.raises(ValueError, match="status"):
        WatchlistAccount(
            principal_id="harbor", cluster_id="x", handle="@y", status="bogus"
        )


def test_account_invalid_proposed_by_rejected():
    with pytest.raises(ValueError, match="proposed_by"):
        WatchlistAccount(
            principal_id="harbor",
            cluster_id="x",
            handle="@y",
            proposed_by="invalid",
        )


# -- InMemoryWatchlistStore ----------------------------------------------------


def test_store_add_returns_id():
    s = InMemoryWatchlistStore()
    aid = s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))
    assert isinstance(aid, str) and len(aid) > 0


def test_store_add_duplicate_raises():
    s = InMemoryWatchlistStore()
    s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))
    with pytest.raises(ValueError, match="already exists"):
        s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))


def test_store_get_returns_deep_copy():
    s = InMemoryWatchlistStore()
    aid = s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))
    item = s.get(aid)
    item.notes = "MUTATED"
    fresh = s.get(aid)
    assert fresh.notes != "MUTATED"


def test_store_find_by_handle():
    s = InMemoryWatchlistStore()
    aid = s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))
    found = s.find_by_handle("harbor", "twitter", "@a")
    assert found.account_id == aid
    assert s.find_by_handle("harbor", "twitter", "@nonexistent") is None
    assert s.find_by_handle("other", "twitter", "@a") is None


def test_store_set_status():
    s = InMemoryWatchlistStore()
    aid = s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))
    s.set_status(aid, "dropped")
    assert s.get(aid).status == "dropped"


def test_store_set_status_invalid_raises():
    s = InMemoryWatchlistStore()
    aid = s.add(WatchlistAccount(principal_id="harbor", cluster_id="x", handle="@a"))
    with pytest.raises(ValueError, match="Invalid status"):
        s.set_status(aid, "invalid_status")


def test_store_list_filters():
    s = InMemoryWatchlistStore()
    a = s.add(WatchlistAccount(principal_id="harbor", cluster_id="alpha", handle="@a"))
    b = s.add(WatchlistAccount(principal_id="harbor", cluster_id="beta", handle="@b"))
    s.add(WatchlistAccount(principal_id="other", cluster_id="alpha", handle="@c"))

    harbor_all = s.list("harbor")
    assert len(harbor_all) == 2

    harbor_alpha = s.list("harbor", cluster_id="alpha")
    assert len(harbor_alpha) == 1
    assert harbor_alpha[0].handle == "@a"


# -- ProposalFlow --------------------------------------------------------------


def test_operator_propose_inserts_active():
    s = InMemoryWatchlistStore()
    flow = ProposalFlow(store=s)
    aid = flow.operator_propose(
        principal_id="harbor", cluster_id="x", handle="@a", notes="seeded"
    )
    item = s.get(aid)
    assert item.status == "active"
    assert item.proposed_by == "operator"
    assert item.notes == "seeded"


def test_principal_propose_without_channel_auto_approves():
    """When no ApprovalChannel is wired, principal proposals go straight to active.
    Useful for tests; production code should always wire a channel."""
    s = InMemoryWatchlistStore()
    flow = ProposalFlow(store=s)  # no channel
    aid = flow.principal_propose(
        principal_id="harbor",
        cluster_id="x",
        handle="@a",
        reason="they write thoughtful threads",
    )
    item = s.get(aid)
    assert item.status == "active"
    assert item.proposed_by == "principal"
    assert "thoughtful threads" in item.notes


def test_principal_propose_with_channel_pending_then_approved():
    s = InMemoryWatchlistStore()
    ch = MockApprovalChannel()
    flow = ProposalFlow(store=s, approval_channel=ch)

    aid = flow.principal_propose(
        principal_id="harbor", cluster_id="x", handle="@a", reason="r"
    )

    # Should be pending
    assert s.get(aid).status == "pending_approval"
    # Card was sent
    assert len(ch.sent) == 1
    assert ch.sent[0]["item_id"] == aid
    assert ch.sent[0]["payload"]["handle"] == "@a"

    # Operator approves
    ch.simulate_decision(aid, ApprovalAction.APPROVE, approver="lucky")
    assert s.get(aid).status == "active"


def test_principal_propose_with_channel_pending_then_rejected():
    s = InMemoryWatchlistStore()
    ch = MockApprovalChannel()
    flow = ProposalFlow(store=s, approval_channel=ch)

    aid = flow.principal_propose(
        principal_id="harbor", cluster_id="x", handle="@a", reason="r"
    )
    ch.simulate_decision(
        aid, ApprovalAction.REJECT, approver="lucky", reason="not a fit"
    )
    assert s.get(aid).status == "dropped"


def test_principal_propose_expire_drops():
    s = InMemoryWatchlistStore()
    ch = MockApprovalChannel()
    flow = ProposalFlow(store=s, approval_channel=ch)
    aid = flow.principal_propose(
        principal_id="harbor", cluster_id="x", handle="@a", reason="r"
    )
    ch.simulate_decision(aid, ApprovalAction.EXPIRE, approver="system")
    assert s.get(aid).status == "dropped"


def test_decision_for_unknown_account_ignored():
    """Channel might send decisions for items from other consumers; ignore silently."""
    s = InMemoryWatchlistStore()
    ch = MockApprovalChannel()
    flow = ProposalFlow(store=s, approval_channel=ch)
    # Inject a decision for an account that doesn't exist
    ch.simulate_decision("nonexistent-id", ApprovalAction.APPROVE)
    # No exception raised; nothing changes
    assert s.list("anything") == []


def test_decision_for_already_active_ignored():
    """If the account isn't pending_approval, decisions don't change it."""
    s = InMemoryWatchlistStore()
    ch = MockApprovalChannel()
    flow = ProposalFlow(store=s, approval_channel=ch)
    aid = flow.operator_propose(
        principal_id="harbor", cluster_id="x", handle="@a"
    )  # status=active
    ch.simulate_decision(aid, ApprovalAction.REJECT)
    # Still active
    assert s.get(aid).status == "active"


def test_remove_drops_account():
    s = InMemoryWatchlistStore()
    flow = ProposalFlow(store=s)
    aid = flow.operator_propose(principal_id="harbor", cluster_id="x", handle="@a")
    flow.remove(aid)
    assert s.get(aid).status == "dropped"
