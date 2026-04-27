"""Watchlist — accounts the principal monitors per cluster, with proposal flow.

Three routes for an account to enter a watchlist:

1. **Operator proposes** — `pebbles scout propose <handle> --cluster=<x>`
   Inserts with status='active' immediately. Operator is the trusted party.

2. **Principal proposes** — agent emits `[SCOUT_OBSERVE: cluster: @handle: reason]`.
   Inserts with status='pending_approval'. Operator gets a card via the
   ApprovalChannel (per design D5-A — reuses pebbles-core's Protocol).
   On approve → status='active'. On reject → status='dropped'.

3. **Scout auto-proposes** (v0.2+, stubbed) — if an account consistently
   produces high-relevance candidates. v0.1 has the slot but doesn't compute.

State machine:
    pending_approval → active     (operator approves)
    pending_approval → dropped    (operator rejects)
    active           → dropped    (operator removes)
    dropped          → (terminal)
"""

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol

from pebbles.core.approval import ApprovalAction, ApprovalChannel, ApprovalDecision


# ----- Account model + statuses ------------------------------------------------


@dataclass
class WatchlistAccount:
    """A row in scout_accounts."""

    principal_id: str
    cluster_id: str
    handle: str
    platform: str = "twitter"
    status: str = "active"  # 'active' | 'pending_approval' | 'dropped'
    proposed_by: str = "operator"  # 'operator' | 'principal' | 'scout_auto'
    notes: str = ""
    follower_count: Optional[int] = None
    last_seen_at: Optional[str] = None
    engagements_count: int = 0
    follower_conversions: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    account_id: Optional[str] = None  # set on insert

    def __post_init__(self):
        if self.status not in {"active", "pending_approval", "dropped"}:
            raise ValueError(f"Invalid watchlist status: {self.status}")
        if self.proposed_by not in {"operator", "principal", "scout_auto"}:
            raise ValueError(f"Invalid proposed_by: {self.proposed_by}")


# ----- Storage protocol --------------------------------------------------------


class WatchlistStore(Protocol):
    """Protocol for watchlist storage."""

    def add(self, account: WatchlistAccount) -> str:
        """Insert. Returns account_id. Raises ValueError on duplicate (principal_id, platform, handle)."""
        ...

    def get(self, account_id: str) -> Optional[WatchlistAccount]:
        ...

    def find_by_handle(
        self, principal_id: str, platform: str, handle: str
    ) -> Optional[WatchlistAccount]:
        """Find existing account row, if any. Used to check duplicates before propose."""
        ...

    def set_status(self, account_id: str, status: str) -> bool:
        """Update status. Returns True. Raises KeyError if not found."""
        ...

    def list(
        self,
        principal_id: str,
        cluster_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[WatchlistAccount]:
        ...


class InMemoryWatchlistStore:
    """Reference impl. Dict-backed."""

    def __init__(self):
        self._items: dict[str, WatchlistAccount] = {}

    def add(self, account: WatchlistAccount) -> str:
        existing = self.find_by_handle(
            account.principal_id, account.platform, account.handle
        )
        if existing is not None:
            raise ValueError(
                f"Account already exists: ({account.principal_id}, "
                f"{account.platform}, {account.handle}) → {existing.account_id}"
            )

        account_id = str(uuid.uuid4())
        stored = copy.deepcopy(account)
        stored.account_id = account_id
        self._items[account_id] = stored
        return account_id

    def get(self, account_id: str) -> Optional[WatchlistAccount]:
        item = self._items.get(account_id)
        return copy.deepcopy(item) if item else None

    def find_by_handle(
        self, principal_id: str, platform: str, handle: str
    ) -> Optional[WatchlistAccount]:
        for a in self._items.values():
            if (
                a.principal_id == principal_id
                and a.platform == platform
                and a.handle == handle
            ):
                return copy.deepcopy(a)
        return None

    def set_status(self, account_id: str, status: str) -> bool:
        if account_id not in self._items:
            raise KeyError(f"Account not found: {account_id}")
        if status not in {"active", "pending_approval", "dropped"}:
            raise ValueError(f"Invalid status: {status}")
        self._items[account_id].status = status
        self._items[account_id].updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def list(
        self,
        principal_id: str,
        cluster_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[WatchlistAccount]:
        items = [a for a in self._items.values() if a.principal_id == principal_id]
        if cluster_id is not None:
            items = [a for a in items if a.cluster_id == cluster_id]
        if status is not None:
            items = [a for a in items if a.status == status]
        items.sort(key=lambda a: a.created_at, reverse=True)
        return [copy.deepcopy(a) for a in items]


# ----- Proposal flow -----------------------------------------------------------


class ProposalFlow:
    """Coordinates watchlist proposals across the three routes.

    Wires together: WatchlistStore (persistence) + ApprovalChannel (operator gate).
    Per D5-A, reuses pebbles-core's ApprovalChannel Protocol — same shape Presence
    uses for draft approvals.
    """

    def __init__(
        self,
        store: WatchlistStore,
        approval_channel: Optional[ApprovalChannel] = None,
        operator: str = "operator",
    ):
        """Initialize.

        Args:
            store: Where accounts live.
            approval_channel: Where to send 'principal_proposes' cards. If None,
                principal-proposed accounts go straight to active (useful for tests).
            operator: Identifier passed to ApprovalChannel.send().
        """
        self.store = store
        self.approval_channel = approval_channel
        self.operator = operator

        if approval_channel is not None:
            approval_channel.register_callback(self._on_decision)

    def operator_propose(
        self,
        principal_id: str,
        cluster_id: str,
        handle: str,
        platform: str = "twitter",
        notes: str = "",
    ) -> str:
        """Route 1: operator adds account directly. Status=active immediately."""
        account = WatchlistAccount(
            principal_id=principal_id,
            cluster_id=cluster_id,
            handle=handle,
            platform=platform,
            notes=notes,
            status="active",
            proposed_by="operator",
        )
        return self.store.add(account)

    def principal_propose(
        self,
        principal_id: str,
        cluster_id: str,
        handle: str,
        reason: str,
        platform: str = "twitter",
    ) -> str:
        """Route 2: agent proposes. Status=pending_approval; operator card sent.

        Returns the account_id. If no approval_channel was configured, account
        goes straight to active (test path).
        """
        notes = f"Proposed by principal: {reason}"
        if self.approval_channel is None:
            # No gate configured — auto-approve
            account = WatchlistAccount(
                principal_id=principal_id,
                cluster_id=cluster_id,
                handle=handle,
                platform=platform,
                notes=notes,
                status="active",
                proposed_by="principal",
            )
            return self.store.add(account)

        account = WatchlistAccount(
            principal_id=principal_id,
            cluster_id=cluster_id,
            handle=handle,
            platform=platform,
            notes=notes,
            status="pending_approval",
            proposed_by="principal",
        )
        account_id = self.store.add(account)

        # Send approval card
        payload = {
            "kind": "watchlist_proposal",
            "principal_id": principal_id,
            "cluster_id": cluster_id,
            "platform": platform,
            "handle": handle,
            "reason": reason,
        }
        self.approval_channel.send(account_id, payload, approver=self.operator)
        return account_id

    def remove(self, account_id: str) -> None:
        """Drop an account from the watchlist."""
        self.store.set_status(account_id, "dropped")

    def _on_decision(self, decision: ApprovalDecision) -> None:
        """Callback from ApprovalChannel when operator decides on a pending account."""
        existing = self.store.get(decision.item_id)
        if existing is None:
            # Could be a decision routed to a different consumer; ignore silently
            return
        if existing.status != "pending_approval":
            # Not in a state we care about
            return

        if decision.action == ApprovalAction.APPROVE:
            self.store.set_status(decision.item_id, "active")
        elif decision.action in (ApprovalAction.REJECT, ApprovalAction.EXPIRE):
            self.store.set_status(decision.item_id, "dropped")
        # EDIT doesn't apply to watchlist proposals — ignored
