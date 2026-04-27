"""RelevanceMatcher — score how well a candidate fits its tagged cluster.

Per design D4-A: this is a thin wrapper around pebbles-core's `LLMJudgeRater`
with a Scout-specific system prompt. The `LLMJudgeRater` already handles
retry, JSON-mode parsing, and clean error handling — we reuse that plumbing
and just specialize the prompt.

Scope: relevance ≠ voice-fit. The matcher answers "would the principal find
this item interesting given their cluster's stated topical focus?" — NOT
"would the principal want to engage publicly with this?" The voice-fit
question is Pebbles Presence's job (its rater), not Scout's.
"""

import logging
from dataclasses import dataclass

from pebbles.core.llm import LLMAdapter
from pebbles.core.rater import LLMJudgeRater, RaterInput, RaterOutput

from pebbles.scout.candidate import Candidate
from pebbles.scout.clusters import Cluster

logger = logging.getLogger(__name__)


SCOUT_RELEVANCE_SYSTEM_PROMPT = (
    "You rate how well a candidate item fits a topical cluster's focus area. "
    "You are scoring TOPICAL RELEVANCE only, not voice fit, not engagement worthiness, "
    "not whether the principal should publicly respond. Just: does this item belong in "
    "this cluster's bucket? Score from 0.0 (off-topic) to 1.0 (perfect fit). "
    'Output JSON: {"score": float, "notes": "one line, max 200 chars, why this score"}. '
    "You receive only the candidate text, the cluster description, and topical signals — "
    "no voice corpus, no rubric. Score blind to those."
)


@dataclass
class RelevanceVerdict:
    """The matcher's verdict on a candidate."""

    score: float
    notes: str

    def __post_init__(self):
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                f"relevance score must be in [0.0, 1.0], got {self.score}"
            )


class RelevanceMatcher:
    """Cluster-relevance scorer. Composes LLMJudgeRater under the hood."""

    def __init__(self, llm: LLMAdapter):
        self.llm = llm
        self._judge = LLMJudgeRater(llm=llm, system_prompt=SCOUT_RELEVANCE_SYSTEM_PROMPT)

    def score(self, candidate: Candidate, cluster: Cluster) -> RelevanceVerdict:
        """Score how well `candidate` fits `cluster`. Raises if LLM call fails."""
        if candidate.cluster_id != cluster.cluster_id:
            raise ValueError(
                f"Candidate tagged with cluster '{candidate.cluster_id}' but scoring "
                f"against '{cluster.cluster_id}' — cluster mismatch."
            )

        rubric = {
            "cluster_id": cluster.cluster_id,
            "description": cluster.description,
        }
        candidate_payload = {
            "text": candidate.target_content,
            "source": candidate.source,
            "platform": candidate.platform,
            "author": candidate.target_author,
        }

        rater_input = RaterInput(
            candidate=candidate_payload,
            rubric=rubric,
        )

        out: RaterOutput = self._judge.rate(rater_input)
        return RelevanceVerdict(score=out.score, notes=out.notes)
