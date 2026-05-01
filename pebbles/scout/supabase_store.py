"""SupabaseCandidateStore — persistent CandidateStore backed by Supabase.

Writes Scout candidates to the public.scout_candidates table in the Song
Supabase project (zznfzonnovkldmdrooxh). This is what connects pebbles-scout
output to the pebbles-presence pipeline.

Schema columns used (subset of scout_candidates):
    id              → candidate.candidate_id
    source_url      → candidate.target_ref
    source_type     → candidate.source
    title           → candidate.metadata.get('title', '')
    summary         → candidate.target_content (first 2000 chars)
    image_url       → candidate.metadata.get('image_url')
    quality_score   → candidate.relevance_score * 10 (0-1 → 0-10)
    status          → mapped from CandidateStatus
    created_at      → candidate.discovered_at

CandidateStatus mapping:
    new             → 'ready'       (Presence pipeline picks up 'ready' rows)
    consumed        → 'drafted'     (Presence marked it)
    expired         → 'stale'
    rejected_filter → 'skipped'

Usage:
    from pebbles.scout.supabase_store import SupabaseCandidateStore
    store = SupabaseCandidateStore.from_env()  # reads SUPABASE_URL + SUPABASE_SERVICE_KEY

    # In Scout CLI: pass --store supabase (Phase 2 CLI flag, wired below)
    # Or construct directly and pass to the Scout runner.
"""
from __future__ import annotations

import copy
import os
from typing import Optional

from pebbles.scout.candidate import (
    Candidate,
    CandidateStatus,
    InvalidCandidateTransitionError,
    VALID_TRANSITIONS,
)

# CandidateStatus → scout_candidates.status
_STATUS_MAP = {
    CandidateStatus.NEW: "ready",
    CandidateStatus.CONSUMED: "drafted",
    CandidateStatus.EXPIRED: "stale",
    CandidateStatus.REJECTED_FILTER: "skipped",
}

# scout_candidates.status → CandidateStatus (reverse, for reads)
_STATUS_REVERSE = {v: k for k, v in _STATUS_MAP.items()}


def _row_to_candidate(row: dict) -> Candidate:
    status_str = row.get("status", "ready")
    status = _STATUS_REVERSE.get(status_str, CandidateStatus.NEW)
    relevance = None
    qs = row.get("quality_score")
    if qs is not None:
        relevance = float(qs) / 10.0

    return Candidate(
        principal_id=row.get("metadata", {}).get("principal_id", "song"),
        cluster_id=row.get("metadata", {}).get("cluster_id", ""),
        source=row.get("source_type", ""),
        platform=row.get("metadata", {}).get("platform", row.get("source_type", "")),
        target_ref=row.get("source_url", ""),
        target_content=row.get("summary", "") or "",
        target_author=row.get("metadata", {}).get("target_author"),
        relevance_score=relevance,
        status=status,
        discovered_at=row.get("created_at", ""),
        consumed_at=row.get("metadata", {}).get("consumed_at"),
        consumed_by=row.get("metadata", {}).get("consumed_by"),
        metadata={
            "title": row.get("title", ""),
            "image_url": row.get("image_url"),
            **(row.get("metadata") or {}),
        },
        candidate_id=row.get("id"),
    )


def _candidate_to_row(candidate: Candidate) -> dict:
    # Title: explicit metadata key first, then first line of target_content
    title = candidate.metadata.get("title", "")
    if not title and candidate.target_content:
        title = candidate.target_content.split("\n")[0].strip()
    image_url = candidate.metadata.get("image_url")
    platform = candidate.metadata.get("platform", candidate.platform)
    quality_score = None
    if candidate.relevance_score is not None:
        quality_score = round(candidate.relevance_score * 10, 2)

    return {
        "source_url": candidate.target_ref,
        "source_type": candidate.source,
        "title": title[:500] if title else None,
        "summary": (candidate.target_content or "")[:2000] or None,
        "image_url": image_url,
        "quality_score": quality_score,
        "status": _STATUS_MAP.get(candidate.status, "ready"),
        "metadata": {
            "principal_id": candidate.principal_id,
            "cluster_id": candidate.cluster_id,
            "platform": platform,
            "target_author": candidate.target_author,
            "relevance_notes": candidate.relevance_notes,
            **(candidate.metadata or {}),
        },
    }


class SupabaseCandidateStore:
    """Persistent CandidateStore backed by Supabase scout_candidates table.

    Implements the CandidateStore Protocol (same interface as InMemoryCandidateStore).
    """

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        from supabase import create_client
        self._client = create_client(supabase_url, supabase_key)

    @classmethod
    def from_env(cls) -> "SupabaseCandidateStore":
        """Construct from SUPABASE_URL + SUPABASE_SERVICE_KEY env vars."""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SupabaseCandidateStore requires SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY (or SUPABASE_KEY) env vars"
            )
        return cls(url, key)

    def add(self, candidate: Candidate) -> str:
        """Insert a new candidate. Returns the DB-assigned UUID."""
        row = _candidate_to_row(candidate)
        if candidate.discovered_at:
            row["created_at"] = candidate.discovered_at
        result = self._client.table("scout_candidates").insert(row).execute()
        candidate_id = result.data[0]["id"]
        return candidate_id

    def get(self, candidate_id: str) -> Optional[Candidate]:
        result = (
            self._client.table("scout_candidates")
            .select("*")
            .eq("id", candidate_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return _row_to_candidate(result.data[0])

    def transition(
        self, candidate_id: str, to_status: CandidateStatus, **fields
    ) -> bool:
        existing = self.get(candidate_id)
        if existing is None:
            raise KeyError(f"Candidate not found: {candidate_id}")

        current = existing.status
        if to_status not in VALID_TRANSITIONS[current]:
            raise InvalidCandidateTransitionError(current, to_status, candidate_id)

        update: dict = {
            "status": _STATUS_MAP[to_status],
        }
        # Merge extra fields into metadata
        if fields:
            meta = copy.deepcopy(existing.metadata or {})
            for k, v in fields.items():
                meta[k] = v
            update["metadata"] = meta

        self._client.table("scout_candidates").update(update).eq("id", candidate_id).execute()
        return True

    def list(
        self,
        principal_id: str,
        status: Optional[CandidateStatus] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Candidate]:
        q = (
            self._client.table("scout_candidates")
            .select("*")
            .order("created_at", desc=True)
            .limit(min(limit, 200))
        )
        if status is not None:
            q = q.eq("status", _STATUS_MAP[status])

        result = q.execute()
        rows = result.data or []

        # Filter by principal_id and cluster_id in Python
        # (metadata JSON filtering in PostgREST is awkward; these are low-cardinality)
        candidates = []
        for row in rows:
            c = _row_to_candidate(row)
            if c.principal_id != principal_id:
                continue
            if cluster_id is not None and c.cluster_id != cluster_id:
                continue
            candidates.append(c)
        return candidates
