"""pebbles-scout CLI entry point.

Registered as a top-level `pebbles-scout` console script (per D7 deviation
note in PHASE_B_DESIGN_2026-04-26.md — pebbles-core 0.2.0 doesn't yet load
plugin subgroups; that lands in 0.2.1+, at which point `pebbles scout <cmd>`
will also work via the entry_points declaration).

Subcommands:
    pebbles-scout migrate          -- print/run schema migration
    pebbles-scout init <name>      -- scaffold a new principal config
    pebbles-scout run              -- one-shot fetch (or --loop)
    pebbles-scout propose          -- operator add account to watchlist
    pebbles-scout status           -- show recent candidates + watchlist counts
"""

import logging
from pathlib import Path

import click

from pebbles.scout._version import __version__

logger = logging.getLogger(__name__)


@click.group(name="scout")
@click.version_option(version=__version__, prog_name="pebbles-scout")
def scout_group():
    """pebbles-scout — inbound research, watchlists, and candidate discovery."""
    pass


@scout_group.command()
@click.option(
    "--principal",
    "principal_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to principal.yaml",
)
@click.option(
    "--anthropic-key",
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key for relevance matcher",
)
@click.option("--loop", is_flag=True, help="Run continuously every 30 minutes")
def run(principal_path: Path, anthropic_key: str, loop: bool):
    """Fetch new items from sources, score relevance, emit candidates."""
    import time

    from pebbles.core.principal import Principal
    from pebbles.core.llm import AnthropicAdapter
    from pebbles.core.metrics import InMemoryMetrics

    from pebbles.scout.candidate_store import InMemoryCandidateStore
    from pebbles.scout.filters import PassThroughFilter
    from pebbles.scout.matcher import RelevanceMatcher
    from pebbles.scout.principal import ScoutPrincipalConfig
    from pebbles.scout.sources.rss import RssSource

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

    principal = Principal.from_yaml(principal_path)
    config = ScoutPrincipalConfig.from_principal(principal)

    if not anthropic_key:
        raise click.ClickException(
            "Anthropic API key required (--anthropic-key or ANTHROPIC_API_KEY env var)"
        )
    llm = AnthropicAdapter(api_key=anthropic_key)
    matcher = RelevanceMatcher(llm=llm)
    pre_filter = PassThroughFilter()
    store = InMemoryCandidateStore()
    metrics = InMemoryMetrics()

    rss = RssSource.from_config(config.sources)
    sources = [s for s in [rss] if s is not None]
    if not sources:
        raise click.ClickException("No sources configured in principal.extra.scout.sources")

    def tick():
        click.echo(f"Scout tick for principal={principal.id}")
        for source in sources:
            try:
                candidates = source.fetch(principal.id, config.clusters)
            except Exception as e:
                logger.error(f"Source {source.__class__.__name__} failed: {e}")
                metrics.emit(principal.id, "source_unavailable", metadata={"error": str(e)})
                continue

            for c in candidates:
                keep, reason = pre_filter.keep(c)
                if not keep:
                    metrics.emit(principal.id, "rejected_filter", metadata={"reason": reason})
                    continue

                cluster = config.cluster_by_id(c.cluster_id)
                if cluster is None:
                    logger.warning(f"Candidate tagged with unknown cluster: {c.cluster_id}")
                    continue

                try:
                    verdict = matcher.score(c, cluster)
                except Exception as e:
                    logger.error(f"Relevance match failed: {e}")
                    metrics.emit(principal.id, "matcher_unavailable", metadata={"error": str(e)})
                    continue

                if verdict.score < config.relevance_threshold:
                    metrics.emit(
                        principal.id,
                        "below_threshold",
                        value=verdict.score,
                        metadata={"target_ref": c.target_ref},
                    )
                    continue

                c.relevance_score = verdict.score
                c.relevance_notes = verdict.notes
                cid = store.add(c)
                metrics.emit(
                    principal.id,
                    "candidate_emitted",
                    value=verdict.score,
                    metadata={"candidate_id": cid, "cluster_id": c.cluster_id},
                )
                click.echo(
                    f"  + emitted candidate {cid[:8]} (cluster={c.cluster_id}, "
                    f"score={verdict.score:.2f}): {c.target_content[:80]}"
                )

    if loop:
        click.echo("Running continuous loop (30 min interval). Ctrl-C to stop.")
        while True:
            tick()
            time.sleep(1800)
    else:
        tick()
        click.echo(f"Done. {len(store.list(principal.id))} new candidates emitted.")


@scout_group.command()
def migrate():
    """Print the schema SQL for scout_clusters / scout_accounts / scout_candidates / scout_metrics.

    v0.1 doesn't apply migrations directly — it prints the SQL for you to run
    via your DB tooling (Supabase MCP, psql, the dashboard, etc.).
    """
    sql_path = Path(__file__).parent.parent.parent.parent / "sql" / "0001_initial.sql"
    if not sql_path.exists():
        raise click.ClickException(f"Schema file not found: {sql_path}")
    click.echo(sql_path.read_text())


@scout_group.command()
@click.argument("name")
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("./examples"),
    help="Where to scaffold the principal directory",
)
def init(name: str, out_dir: Path):
    """Scaffold a new principal config directory under examples/."""
    target = out_dir / name
    if target.exists():
        raise click.ClickException(f"Target already exists: {target}")
    target.mkdir(parents=True)

    principal_yaml = target / "principal.yaml"
    principal_yaml.write_text(
        f"""# {name}/principal.yaml — pebbles-scout starter

id: {name}
name: {name.title()}
mode: ai_persona

voice_corpus: []
voice_anchors: {{}}
rubric: {{}}
disclosure: {{}}

extra:
  scout:
    relevance_threshold: 0.55
    clusters:
      - cluster_id: example_cluster
        description: "Replace with your topical focus."
        weekly_min_candidates: 0
        weekly_max_candidates: 50
    sources:
      rss:
        feeds:
          - url: "https://example.com/feed.xml"
            cluster: example_cluster
"""
    )

    readme = target / "README.md"
    readme.write_text(
        f"""# {name}

Starter principal config for pebbles-scout.

## Next steps

1. Edit `principal.yaml` — define your real clusters and RSS feeds.
2. Run `pebbles-scout migrate` and apply the SQL to your storage.
3. Run `pebbles-scout run --principal {name}/principal.yaml`.
"""
    )

    click.echo(f"Scaffolded {target}")
    click.echo(f"  - {principal_yaml}")
    click.echo(f"  - {readme}")


@scout_group.command()
@click.option(
    "--principal",
    "principal_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.argument("handle")
@click.option("--cluster", "cluster_id", required=True)
@click.option("--platform", default="twitter")
@click.option("--notes", default="")
def propose(
    principal_path: Path, handle: str, cluster_id: str, platform: str, notes: str
):
    """Operator-route watchlist add: appends an account immediately as active."""
    from pebbles.core.principal import Principal

    from pebbles.scout.principal import ScoutPrincipalConfig
    from pebbles.scout.watchlist import InMemoryWatchlistStore, ProposalFlow

    principal = Principal.from_yaml(principal_path)
    config = ScoutPrincipalConfig.from_principal(principal)

    if config.cluster_by_id(cluster_id) is None:
        raise click.ClickException(
            f"Cluster '{cluster_id}' not in principal '{principal.id}'. "
            f"Defined clusters: {[c.cluster_id for c in config.clusters]}"
        )

    store = InMemoryWatchlistStore()
    flow = ProposalFlow(store=store)
    account_id = flow.operator_propose(
        principal_id=principal.id,
        cluster_id=cluster_id,
        handle=handle,
        platform=platform,
        notes=notes,
    )
    click.echo(
        f"Added {handle} to {principal.id}/{cluster_id} as active. "
        f"account_id={account_id}"
    )
    click.echo(
        "(Note: v0.1 in-memory store — for persistent watchlists wire a "
        "WatchlistStore-impl backed by your DB.)"
    )


@scout_group.command()
def status():
    """Show pebbles-scout version + diagnostic info."""
    click.echo(f"pebbles-scout v{__version__}")
    click.echo("v0.1 ships in-memory primitives — persistent state requires wiring")
    click.echo("Persistent stores: SupabaseCandidateStore, SupabaseWatchlistStore (planned [supabase] extra)")


if __name__ == "__main__":
    scout_group()
