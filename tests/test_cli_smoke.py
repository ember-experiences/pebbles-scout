"""Smoke tests for pebbles-scout CLI — verify subcommands wire and parse."""

from pathlib import Path

from click.testing import CliRunner

from pebbles.scout.cli.main import scout_group


def test_help_works():
    runner = CliRunner()
    result = runner.invoke(scout_group, ["--help"])
    assert result.exit_code == 0
    assert "pebbles-scout" in result.output.lower() or "scout" in result.output.lower()
    # All five subcommands listed
    for cmd in ["init", "migrate", "run", "propose", "status"]:
        assert cmd in result.output


def test_status_command():
    runner = CliRunner()
    result = runner.invoke(scout_group, ["status"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_migrate_prints_sql():
    runner = CliRunner()
    result = runner.invoke(scout_group, ["migrate"])
    assert result.exit_code == 0
    assert "CREATE TABLE" in result.output
    assert "scout_clusters" in result.output
    assert "scout_accounts" in result.output
    assert "scout_candidates" in result.output
    assert "scout_metrics" in result.output


def test_init_scaffolds_principal(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        scout_group, ["init", "test_persona", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0
    target = tmp_path / "test_persona"
    assert target.exists()
    assert (target / "principal.yaml").exists()
    assert (target / "README.md").exists()
    yaml_content = (target / "principal.yaml").read_text()
    assert "test_persona" in yaml_content
    assert "scout:" in yaml_content
    assert "clusters:" in yaml_content


def test_init_refuses_to_overwrite(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(scout_group, ["init", "x", "--out", str(tmp_path)])
    result = runner.invoke(scout_group, ["init", "x", "--out", str(tmp_path)])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_propose_with_unknown_cluster_fails(tmp_path: Path):
    """Operator can't add to a cluster that doesn't exist on the principal."""
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        """id: harbor
name: Harbor
mode: ai_persona
extra:
  scout:
    clusters:
      - cluster_id: maritime_tech
        description: Marine
"""
    )
    runner = CliRunner()
    result = runner.invoke(
        scout_group,
        [
            "propose",
            "--principal",
            str(yaml_path),
            "@x",
            "--cluster",
            "nonexistent_cluster",
        ],
    )
    assert result.exit_code != 0
    assert "not in" in result.output.lower() or "nonexistent_cluster" in result.output


def test_propose_with_known_cluster_succeeds(tmp_path: Path):
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        """id: harbor
name: Harbor
mode: ai_persona
extra:
  scout:
    clusters:
      - cluster_id: maritime_tech
        description: Marine technology
"""
    )
    runner = CliRunner()
    result = runner.invoke(
        scout_group,
        [
            "propose",
            "--principal",
            str(yaml_path),
            "@maritime_researcher",
            "--cluster",
            "maritime_tech",
        ],
    )
    assert result.exit_code == 0
    assert "Added" in result.output or "active" in result.output.lower()
