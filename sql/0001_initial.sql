-- ============================================================================
-- pebbles-scout v0.1 schema
-- Applied by: pebbles scout migrate
-- ============================================================================

-- Clusters (per principal)
CREATE TABLE IF NOT EXISTS scout_clusters (
    id BIGSERIAL PRIMARY KEY,
    principal_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    description TEXT NOT NULL,
    weekly_min_candidates INTEGER NOT NULL DEFAULT 0,
    weekly_max_candidates INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (principal_id, cluster_id)
);
CREATE INDEX IF NOT EXISTS idx_scout_clusters_principal ON scout_clusters(principal_id);

-- Accounts (watchlist)
CREATE TABLE IF NOT EXISTS scout_accounts (
    id BIGSERIAL PRIMARY KEY,
    principal_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'twitter',
    handle TEXT NOT NULL,
    follower_count INTEGER,
    last_seen_at TIMESTAMPTZ,
    engagements_count INTEGER NOT NULL DEFAULT 0,
    follower_conversions INTEGER NOT NULL DEFAULT 0,
    proposed_by TEXT NOT NULL DEFAULT 'operator',
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (principal_id, platform, handle),
    CONSTRAINT scout_accounts_proposed_by_check CHECK (proposed_by IN ('operator', 'principal', 'scout_auto')),
    CONSTRAINT scout_accounts_status_check CHECK (status IN ('active', 'pending_approval', 'dropped'))
);
CREATE INDEX IF NOT EXISTS idx_scout_accounts_principal_cluster ON scout_accounts(principal_id, cluster_id);
CREATE INDEX IF NOT EXISTS idx_scout_accounts_status ON scout_accounts(status);

-- Candidates (what Scout emits for downstream consumers like Presence)
CREATE TABLE IF NOT EXISTS scout_candidates (
    id BIGSERIAL PRIMARY KEY,
    principal_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    source TEXT NOT NULL,
    platform TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    target_author TEXT,
    target_author_follower_count INTEGER,
    target_content TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    relevance_score NUMERIC(4,3),
    relevance_notes TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    consumed_at TIMESTAMPTZ,
    consumed_by TEXT,
    metadata JSONB,
    CONSTRAINT scout_candidates_status_check CHECK (status IN ('new','consumed','expired','rejected_filter'))
);
CREATE INDEX IF NOT EXISTS idx_scout_candidates_principal_status ON scout_candidates(principal_id, status);
CREATE INDEX IF NOT EXISTS idx_scout_candidates_cluster_time ON scout_candidates(principal_id, cluster_id, discovered_at DESC);

-- Metrics (per-principal event stream)
CREATE TABLE IF NOT EXISTS scout_metrics (
    id BIGSERIAL PRIMARY KEY,
    principal_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_type TEXT NOT NULL,
    metric_value NUMERIC,
    metadata JSONB
);
CREATE INDEX IF NOT EXISTS idx_scout_metrics_principal_type_time ON scout_metrics(principal_id, metric_type, occurred_at DESC);
