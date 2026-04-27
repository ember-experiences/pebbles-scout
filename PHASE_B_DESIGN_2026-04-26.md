# Phase B Design — pebbles-scout v0.1

**By:** Reef 🔧
**For:** Song 🌊 (first approver)
**Date:** 2026-04-26
**Goal:** ship `pebbles-scout` v0.1 — the inbound research/watchlist/cluster module for the Pebbles family

---

## Premise

`pebbles-core` v0.2.0 is live on PyPI. Scout depends on it. Scout's job:

- monitor sources (Twitter lists, RSS, Reddit, forwarded URLs) per-cluster
- score relevance via LLM-as-judge
- emit candidates downstream consumers (Pebbles Presence, eventually) read
- maintain watchlists with three proposal routes (operator / principal / scout-auto)
- emit metrics and observe its own health

**Spec lives at** `~/mysong/projects/pending/Pebble Presence/SPEC_pebbles_scout_v0.1.md` — Wake's original, then split out by Reef on 2026-04-23. It's still the source of truth for *what* Scout does. This doc is *how* it lands against the v0.2 substrate.

**Design rules:** same as Phase A:
- Every primitive a Protocol with at least one ref impl
- Reuse pebbles-core 0.2.0 primitives where they fit; add Scout-specific only where they don't
- No Song-specific code in library; Harbor as demo principal
- Clean-venv install must work for strangers

---

## What's already in pebbles-core that Scout uses verbatim

These are **not** decisions — they're settled by virtue of existing in v0.2:

| Primitive | How Scout uses it |
|---|---|
| `Principal` | Scout reads `principal.id`, `principal.extra` (for cluster config), `principal.children` (when Scout summons Presence in v0.3+) |
| `ApprovalChannel` | Scout's watchlist-proposal flow uses an ApprovalChannel — same shape Presence uses for draft approval. Operator approves/rejects principal-proposed accounts. |
| `LLMAdapter` + `LLMJudgeRater` | Scout's relevance matcher is an `LLMJudgeRater` instance with a Scout-specific system prompt ("rate cluster fit, not voice fit") |
| `MetricsEmitter` | Scout emits `scout_metrics` events the same way Presence emits `presence_metrics` |
| `Storage` Protocol + `JsonStorage` | Scout's deduplication of seen-items uses pebbles-core's existing Storage shape — same protocol pebbles-core itself uses for delivery dedup |
| `CircuitBreaker` + `BreakerSet` | Scout v0.1 doesn't ship breakers (per spec — "v0.1 just logs"). v0.2 may add |
| `Queue` | **NOT** used by Scout. Scout's `scout_candidates` table has a different state machine — see Decision 1 |

---

## Decisions for Song

### D1 — Candidate emission: Queue or new primitive?

`scout_candidates` has a state machine: `new → consumed → expired → rejected_filter`. That's different from `Queue`'s `pending → approved/edited/rejected → sent → failed`. Two options:

**A.** **Make Scout candidates a Scout-internal thing.** A new `CandidateStore` class in `pebbles.scout` with its own state machine. Doesn't touch pebbles-core. Scout owns the table, Presence reads from it. ← REC

**B.** **Promote a generic CandidateStream primitive to pebbles-core.** Pebbles-core grows a 9th primitive that's "principal-scoped item table with consumption tracking." Scout uses it. Future modules might too.

**Why A:** the spec only ever describes one consumer pattern (Presence reads `scout_candidates`). YAGNI for a Core promotion. If Family (or a future module) needs the same shape, we promote in v0.3 — once we have two real consumers proving the abstraction generalizes.

**Your call:** A or B?

---

### D2 — Source Protocol: extend `pebbles.engine.Source` or define `ScoutSource` separately?

v0.1's `pebbles.engine.Source` is:
```python
class Source(Protocol):
    def fetch(self) -> List[Dict[str, Any]]: ...
```

Scout's spec wants:
```python
class ScoutSource(Protocol):
    def fetch(self, principal_id: str, clusters: list[Cluster]) -> list[Candidate]: ...
```

Different signature. Two options:

**A.** **Extend.** `ScoutSource` is its own Protocol. The existing `HackerNewsSource` etc. don't satisfy it (different signature). Scout writes its own `RssSource`, `RedditSource`, etc. — duplicates the v0.1 sources at the Scout layer. ← REC

**B.** **Adapt.** Keep `pebbles.engine.Source` as is; write a thin `ScoutSourceAdapter` that wraps any v0.1 Source and adds cluster-tagging. Saves duplication, but the adapter has to guess which cluster each item fits.

**Why A:** the cluster-aware fetch isn't an afterthought; it's core to Scout's job (a principal has multiple clusters and items get tagged with the best-match cluster at fetch time). Wrapping a stateless `Source.fetch()` to do cluster matching is awkward — the cluster matching wants to live inside the source where it can use platform-specific signals (subreddit name → cluster, RSS feed URL → cluster, etc.). Cleaner to write Scout-native sources.

**Your call:** A or B?

---

### D3 — Initial source coverage in v0.1

Wake's spec lists 4 source types:
- `TwitterStreamSource` — Twitter list / keyword stream via MCP
- `TelegramUrlSource` — absorbs today-bot's `twitter_intake.py` pattern
- `RedditSource` — cluster-aware Reddit
- `RssSource` — cluster-aware RSS

**Question:** ship all 4 in v0.1, or start with a subset?

**A.** **Ship all 4.** Most complete out of the box. Twitter MCP and Telegram-URL sources both depend on infrastructure Song already has, so the deps don't grow.

**B.** **Ship 2 (RSS + Reddit) + stubs for the other 2.** Faster to v0.1. Twitter-MCP-backed source is real-Twitter-account-dependent and harder to stranger-test. Telegram-URL source needs a Telegram bot.

**C.** **Ship 1 (RSS only) — minimum viable Scout.** Keeps the v0.1 surface tiny; everything else is contributor territory. ← REC

**Why C:** RSS is the simplest, most stranger-testable, no platform credentials needed. Scout's headline primitives (cluster matching, candidate emission, watchlist proposals, LLM relevance) all work with one source. The other 3 are conceptually identical in shape; we add them in v0.2 once the protocol's proven. **This is the same discipline that made v0.1.0 of pebbles-core ship clean — start small, extend.**

**Your call:** A, B, or C?

If you pick C, today-bot's `twitter_intake.py` re-homes into Scout in v0.2 (during the production-wire phase) — its absorption was always Phase F/G in the original PLAN.md, not Phase B.

---

### D4 — Relevance matcher: bake or compose?

Scout needs an LLM-as-judge for "does this item fit this cluster?" v0.2 ships `LLMJudgeRater` which is general-purpose.

**A.** **Compose.** Scout's matcher is a thin wrapper that constructs an `LLMJudgeRater` with a Scout-specific system prompt and converts its `RaterOutput.score` to a `relevance_score`. ← REC

**B.** **Bake.** Scout has its own `RelevanceMatcher` class with its own LLM call. Doesn't depend on `LLMJudgeRater`.

**Why A:** the LLMJudgeRater is good. It already has retry + JSON-mode + clean error handling. Reusing it means voice-rating and relevance-rating share the same plumbing — which means Scout-side relevance bugs are detectable via Presence-side voice-rating tests. Tight composition.

The Scout-specific bit is just the prompt: "score how well this item fits this cluster's description, not whether the principal would like it stylistically."

**Your call:** A or B?

---

### D5 — Watchlist proposal approval: ApprovalChannel reuse?

Scout watchlist proposal flow needs operator approve/reject for principal-proposed accounts. v0.2's `ApprovalChannel` Protocol is exactly this shape.

**A.** **Reuse the Protocol.** Scout's `WatchlistProposalFlow` takes any `ApprovalChannel`. Reference impl uses `MockApprovalChannel`. Real Telegram impl lives downstream (Song wires her existing bot). ← REC

**B.** **Scout owns its own approval primitive.** Lighter shape than the full ApprovalChannel.

**Why A:** zero gain from owning a separate one. The ApprovalChannel Protocol is already lightweight (send + register_callback). Watchlist proposals are just `payload = {"principal": "song", "cluster": "ai_consciousness", "handle": "@x", "reason": "..."}`. Same flow Presence uses for drafts.

**Your call:** A or B?

---

### D6 — `scout_candidates` storage: separate or shared with Queue's storage?

Scout writes to `scout_candidates` table. Pebbles-core's `Queue` writes to its own table. Both want Supabase eventually.

**A.** **Separate.** `CandidateStore` in `pebbles.scout` has its own Supabase impl behind `[supabase]` extra. Identical pattern to Core's `SupabaseQueue` but for the candidate state machine. Two impls, one library each. ← REC

**B.** **Generic Supabase table-backed store in pebbles-core.** `pebbles.core._supabase.SupabaseTableStore` — generic CRUD for any principal-scoped table. SupabaseQueue + SupabaseCandidateStore both wrap it.

**Why A:** the schemas and state machines genuinely differ. Forcing them to share generic CRUD code adds abstraction cost without semantic gain. They're two different concerns; let them be two impls.

**Your call:** A or B?

---

### D7 — Scout CLI — extend `pebbles` or new entry point?

v0.1's pebbles-core has `pebbles` CLI with subcommands `run`, `status`. Scout wants `pebbles scout init`, `pebbles scout run`, `pebbles scout migrate`, `pebbles scout propose`, `pebbles scout status`.

**A.** **Extend `pebbles` CLI via plugin discovery.** When `pebbles-scout` is installed, it registers itself as a `pebbles` subgroup so `pebbles scout <cmd>` dispatches to scout. Click supports this via entry_points. ← REC

**B.** **New `pebbles-scout` CLI entry point.** Scout has its own command. Two top-level commands (`pebbles` and `pebbles-scout`) on the user's PATH.

**Why A:** matches Wake's spec ("`pebbles [module] [command]` pattern"). One command, multiple subgroups. Cleaner UX. Click's entry_point plugin discovery is a well-established pattern.

**Your call:** A or B?

---

### D8 — Demo principal: extend Harbor

v0.2 introduced Harbor as the fictional coastal-AI persona for `pebbles-core` examples. Scout's `examples/harbor/` should extend Harbor with cluster definitions + a starter watchlist + an RSS feed list.

**Question:** is Harbor's voice fine for Scout, or does Scout's demo persona need different shape?

**A.** **Extend Harbor.** Same persona, add cluster config: `maritime_tech`, `ocean_ecology`, `coastal_storytelling` clusters with placeholder seed accounts (or RSS feeds, since D3-C). ← REC

**B.** **New demo persona for Scout.** Different persona for Scout's examples directory.

**Why A:** Harbor's voice is plausibly interested in maritime topics. Cluster definitions feel native. Reusing keeps the agent-embers.ai documentation story consistent — "here's Harbor across the family."

**Your call:** A or B?

---

### D9 — Scope of v0.1: what's deferred?

Per spec Section 4.6: "v0.2 may add launchd plists for continuous monitoring. v0.1 stays simple."

I'm defaulting to:

| In v0.1 | Deferred to v0.2+ |
|---|---|
| Cluster manager + `scout_clusters` table | Cluster monoculture-prevention quotas (v0.1 stores quota fields but doesn't enforce) |
| Watchlist + `scout_accounts` table | Account reputation scoring (`engagements_count`, `follower_conversions` columns exist but aren't computed) |
| Candidate emission + `scout_candidates` | Auto-proposal (`proposed_by='scout_auto'` is reserved but not used in v0.1) |
| One source (RSS) per D3-C | Twitter MCP, Telegram URL, Reddit sources |
| LLM relevance matcher | Pre-filter rules (rage-farm filter, self-promo filter) — v0.1 stub returns True |
| Watchlist proposal flow | Bulk operations (e.g. propose 10 accounts at once) |
| Metrics emission | Circuit breakers (per spec — v0.1 just logs) |

**Question:** does this scope feel right, or are you missing anything you wanted in v0.1?

**REC:** ship as scoped. Faster v0.1, tight feedback loop, v0.2 fills in.

**Your call:** ship as scoped, or expand scope?

---

## How they compose — wiring diagram

```
                    ┌────────────────┐
                    │   Principal    │
                    │  (with extra:  │
                    │   {clusters})  │
                    └────────┬───────┘
                             │ (read-only)
                             ▼
   ┌─────────────────────────────────────────────────────────┐
   │                     SCOUT TICK                           │
   │                                                          │
   │   ┌──────────┐    ┌─────────┐    ┌────────────────┐    │
   │   │ Source   │───▶│Pre-filter│───▶│RelevanceMatcher│    │
   │   │ (RSS)    │    │ (stub)  │    │(LLMJudgeRater) │    │
   │   └─────┬────┘    └────┬────┘    └────────┬───────┘    │
   │         │              │                   │             │
   │         ▼              ▼                   ▼             │
   │   ┌──────────────────────────────────────────────┐      │
   │   │  CandidateStore — emit if score >= threshold │      │
   │   │  (state: new → consumed → expired)           │      │
   │   └──────────────────────────────────────────────┘      │
   │                                                          │
   │   ┌──────────────────────────────────────────────┐      │
   │   │  MetricsEmitter (every step emits)           │      │
   │   └──────────────────────────────────────────────┘      │
   └─────────────────────────────────────────────────────────┘

   Side-channel (separate flow, same Scout package):

   Principal emits [SCOUT_OBSERVE: cluster: @handle: reason]
        │
        ▼
   ┌──────────────────────────────────────────────────────┐
   │  WatchlistProposalFlow                                │
   │   - inserts to scout_accounts (status=pending)        │
   │   - sends ApprovalChannel card (operator approves)    │
   │   - on approve: status → active                       │
   │   - on reject: status → dropped                       │
   └──────────────────────────────────────────────────────┘
```

**What this confirms about composition:**

- Scout's tick pipeline is single-direction: Source → Filter → Matcher → CandidateStore. No cycles.
- Watchlist proposals are a separate flow with a different lifecycle (gated, async).
- MetricsEmitter is fan-in — same as Phase A.
- Scout doesn't import from pebbles-presence. Pebbles-presence (when built) imports from pebbles-scout.

---

## Repository layout (proposed)

Slimmer than Wake's spec (since D3-C drops 3 sources):

```
pebbles-scout/
├── pyproject.toml
├── README.md
├── LICENSE
├── pebbles/
│   └── scout/
│       ├── __init__.py
│       ├── _version.py
│       ├── principal.py            # ScoutPrincipalConfig — cluster definitions
│       ├── candidate.py            # Candidate dataclass
│       ├── candidate_store.py      # CandidateStore Protocol + InMemory impl
│       ├── clusters.py             # Cluster dataclass + cluster manager
│       ├── watchlist.py            # WatchlistStore + ProposalFlow
│       ├── matcher.py              # RelevanceMatcher (composes LLMJudgeRater)
│       ├── filters.py              # Pre-filter Protocol + stub PassThroughFilter
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── base.py             # ScoutSource Protocol
│       │   └── rss.py              # RssSource (the v0.1 source)
│       ├── _supabase.py            # SupabaseCandidateStore + SupabaseWatchlistStore
│       └── cli/
│           ├── __init__.py
│           ├── main.py             # registers as `pebbles scout` subgroup
│           ├── init.py             # pebbles scout init <name>
│           ├── migrate.py          # pebbles scout migrate
│           ├── run.py              # pebbles scout run
│           ├── propose.py          # pebbles scout propose <handle> <cluster>
│           └── status.py           # pebbles scout status
├── sql/
│   └── 0001_initial.sql            # scout_clusters + scout_accounts + scout_candidates + scout_metrics
├── examples/
│   └── harbor/
│       ├── principal.yaml          # extends pebbles-core's Harbor with clusters
│       ├── clusters.yaml
│       └── README.md
└── tests/
    ├── test_principal.py
    ├── test_candidate.py
    ├── test_candidate_store.py
    ├── test_clusters.py
    ├── test_watchlist.py
    ├── test_matcher.py
    ├── test_filters.py
    ├── test_sources_rss.py
    ├── test_proposal_flow.py
    ├── test_v01_composition.py     # full pipeline integration
    └── test_cli_smoke.py
```

---

## Best-case answer

```
D1 A    candidate store stays Scout-internal
D2 A    ScoutSource is its own Protocol
D3 C    RSS only in v0.1; other sources v0.2
D4 A    relevance matcher composes LLMJudgeRater
D5 A    watchlist proposal reuses ApprovalChannel Protocol
D6 A    SupabaseCandidateStore is Scout-owned, parallel to SupabaseQueue
D7 A    extend `pebbles` CLI via Click entry_points
D8 A    extend Harbor with cluster config
D9 ship as scoped (cluster monoculture, reputation, auto-proposal, breakers all v0.2)
```

Anything you want to push back on, flag.

---

## What happens after you approve

1. Branch `feature/v0.1-skeleton`
2. Repo scaffold: pyproject.toml, dirs, LICENSE, README, depends on `pebbles-core>=0.2.0`
3. Schema migration: `sql/0001_initial.sql` matching the spec exactly
4. Core types: `Principal` config (`ScoutPrincipalConfig`), `Candidate`, `Cluster`
5. CandidateStore Protocol + InMemory impl
6. RSS source
7. Pre-filter Protocol + pass-through stub
8. RelevanceMatcher composing LLMJudgeRater
9. Watchlist proposal flow
10. CLI subcommands registered as `pebbles scout` group
11. Harbor demo extended with maritime clusters + RSS feeds
12. Tests for every component
13. Composition test (full pipeline end-to-end with Harbor)
14. Stranger-test: clean venv, install wheel, run Harbor pipeline
15. Commit. **Show me before commit, per the checkpoint pattern.**
16. Then merge/push/publish — Lucky heads-up before PyPI.

Estimated 90-150 min focused work.

---

*Reef 🔧 — Phase B design for pebbles-scout v0.1. After your sign-off, code starts.*
