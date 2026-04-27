"""Pre-filter Protocol — deterministic rules to drop candidates before LLM scoring.

v0.1 ships only `PassThroughFilter` (lets everything through). v0.2 will add
real filters (rage-farm detection, self-promo-from-strangers, spam heuristics)
per Wake's spec.

Filters return True to KEEP, False to DROP. Dropped candidates are logged
to scout_metrics as `rejected_filter` and never reach the relevance matcher.
"""

from typing import Protocol

from pebbles.scout.candidate import Candidate


class CandidateFilter(Protocol):
    """Protocol for pre-filters."""

    def keep(self, candidate: Candidate) -> tuple[bool, str]:
        """Return (keep, reason).

        keep=True: candidate passes filter; proceed to relevance matcher.
        keep=False: candidate is rejected; reason is logged.
        """
        ...


class PassThroughFilter:
    """Reference impl. Keeps everything. v0.1 default — v0.2 adds real rules."""

    def keep(self, candidate: Candidate) -> tuple[bool, str]:
        return (True, "")


class CompositeFilter:
    """Run multiple filters in sequence. First filter to drop wins."""

    def __init__(self, filters: list[CandidateFilter]):
        self.filters = filters

    def keep(self, candidate: Candidate) -> tuple[bool, str]:
        for f in self.filters:
            keep, reason = f.keep(candidate)
            if not keep:
                return (False, reason)
        return (True, "")
