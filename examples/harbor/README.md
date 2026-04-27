# Harbor — pebbles-scout reference instance

Harbor is the cross-package demo persona for the Pebbles family. This directory
extends Harbor's `Principal` (defined in pebbles-core v0.2) with pebbles-scout
configuration: topical clusters and source feeds.

## Quick start

```bash
# Install
pip install pebbles-scout

# Inspect Harbor's config
cat examples/harbor/principal.yaml

# Print the schema migration
pebbles-scout migrate

# Operator-route watchlist add (in-memory only in v0.1)
pebbles-scout propose --principal examples/harbor/principal.yaml \
  @example_handle --cluster maritime_tech

# Run one fetch cycle (requires ANTHROPIC_API_KEY)
pebbles-scout run --principal examples/harbor/principal.yaml
```

## What Harbor demonstrates

- **Three clusters** scoped to maritime / ocean / coastal topics.
- **RSS sources** mapped per-cluster (each feed belongs to one cluster).
- **Relevance threshold of 0.55** — items below this aren't emitted.
- **In-memory storage** — v0.1 reference impls. Wire SupabaseCandidateStore
  / SupabaseWatchlistStore (v0.2 [supabase] extra) for persistent runs.

## Adapting Harbor for your own principal

1. Copy this directory under a new name.
2. Edit `principal.yaml`:
   - Change `id`, `name`, identity fields
   - Replace clusters with your own topical focus
   - Replace RSS feed URLs with feeds you actually want monitored
3. Run `pebbles-scout run --principal <your_dir>/principal.yaml`.

## What v0.1 doesn't do

- Persistent storage (v0.2)
- Twitter / Reddit / Telegram-URL sources (v0.2)
- Cluster monoculture quotas enforcement (v0.2)
- Account reputation scoring (v0.2)
- Scout auto-proposal of new accounts (v0.2)
- Pre-filter rules for rage-farm / spam (v0.2)
- Circuit breakers (v0.2)

v0.1's job: prove the substrate composes cleanly. v0.2 fills in the rest.
