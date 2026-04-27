# pebbles-scout

**Inbound research, watchlists, and candidate discovery for AI agents — Tier 2 of the Pebbles family.**

```bash
pip install pebbles-scout
```

`pebbles-scout` is the **inbound** half of an agent's public-facing engine: it monitors sources (RSS in v0.1; Twitter / Reddit / forwarded URLs in v0.2), scores candidate items against your topical clusters, maintains watchlists with a three-route proposal flow, and emits candidates for downstream consumers (like pebbles-presence) to pick up.

Built on [pebbles-core](https://pypi.org/project/pebbles-core/) v0.2.0.

## What Scout does

For a Principal you define, Scout:

1. **Monitors sources** — RSS feeds, mapped per-cluster
2. **Pre-filters** — drops obvious rejects (v0.1 ships a stub; v0.2 adds rage-farm / self-promo rules)
3. **Scores relevance** — LLM-as-judge rates how well each item fits its tagged cluster
4. **Emits candidates** — items above your threshold land in `scout_candidates` for downstream
5. **Maintains watchlists** — three proposal routes (operator / principal / scout-auto)

Scout does NOT:
- Draft content (that's [pebbles-presence](https://github.com/ember-experiences/pebbles-presence))
- Rate voice fit (that's Presence's rater)
- Post anything (that's Presence's platform adapters)

The split keeps each module composable.

## Quick start

```bash
# Install
pip install pebbles-scout

# Scaffold a starter principal
pebbles-scout init my-agent
cd my-agent

# Edit principal.yaml — define your clusters and RSS feeds
$EDITOR principal.yaml

# Print the schema migration
pebbles-scout migrate
# → run the SQL against your Supabase / Postgres

# Run one fetch cycle (needs ANTHROPIC_API_KEY)
pebbles-scout run --principal principal.yaml

# Add an account to a watchlist (operator route)
pebbles-scout propose @some_handle --cluster my_cluster --principal principal.yaml
```

## Reference principal: Harbor

`examples/harbor/` ships a working configuration for a fictional coastal-AI persona named Harbor (the cross-package demo persona introduced in pebbles-core v0.2). Use it as a starting point or to verify your install.

```bash
pebbles-scout run --principal examples/harbor/principal.yaml
```

## v0.1 scope

**In v0.1:**
- Cluster definitions + `scout_clusters` table
- Watchlist + `scout_accounts` table + 3-route proposal flow
- Candidate emission + `scout_candidates` table with state machine
- One source: `RssSource` (cluster-aware RSS monitoring)
- LLM relevance matcher (composes pebbles-core's `LLMJudgeRater`)
- Pass-through pre-filter (real rules in v0.2)
- Watchlist proposal flow (operator-add immediate; principal-propose gated via `ApprovalChannel`)
- In-memory reference impls for every store (CandidateStore, WatchlistStore)
- CLI: `init`, `migrate`, `run`, `propose`, `status`

**Deferred to v0.2+:**
- SupabaseCandidateStore + SupabaseWatchlistStore (persistent storage behind `[supabase]` extra)
- Twitter MCP, Reddit, Telegram-URL sources
- Cluster monoculture quotas (enforced)
- Account reputation scoring (computed)
- Scout auto-proposal
- Pre-filter rules (rage-farm, self-promo)
- Bulk operations
- Circuit breakers

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Family

- [pebbles-core](https://pypi.org/project/pebbles-core/) — Tier 1, recipient-as-user delivery + substrate primitives
- **pebbles-scout** — Tier 2 (this package), inbound research
- pebbles-presence — Tier 3 (planned), outbound drafter / approval / posting
- pebbles-family — Tier 4 (planned), recipient-as-user's-people delivery
