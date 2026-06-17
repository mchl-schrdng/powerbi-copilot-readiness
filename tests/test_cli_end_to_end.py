import json

from copilot_readiness.cli import main


def test_good_star_exits_zero(good_star_path, fixtures_config, capsys):
    code = main(["lint", good_star_path, "--config", fixtures_config])
    out = capsys.readouterr().out
    assert code == 0
    assert "READY" in out


def test_bad_snowflake_exits_one(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config])
    out = capsys.readouterr().out
    assert code == 1
    assert "NOT READY" in out


def test_markdown_report_has_dashboard_and_blocking(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config, "--format", "markdown"])
    out = capsys.readouterr().out
    assert code == 1
    assert "NOT READY" in out
    assert "| Model | Verdict |" in out          # the summary dashboard table
    assert "Blocking gates" in out
    assert "copilot-readiness-linter" in out      # sticky-comment marker


def test_quiet_hides_blocking_detail(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config, "--quiet"])
    out = capsys.readouterr().out
    assert code == 1
    assert "Summary:" in out
    assert "Blocking gates (must fix)" not in out


def test_default_shows_blocking_not_warnings(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config])
    out = capsys.readouterr().out
    assert "Blocking gates (must fix)" in out
    # Warnings section only appears at -v.
    assert "\nWarnings\n" not in out


def test_verbose_shows_warnings(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config, "-v"])
    out = capsys.readouterr().out
    assert "Warnings" in out


def test_ignore_rules_unblocks(bad_snowflake_path, fixtures_config, capsys):
    # Ignoring every structural gate leaves no blocker, so the model passes.
    code = main([
        "lint", bad_snowflake_path, "--config", fixtures_config,
        "--ignore", "structure.many_to_many,structure.bidirectional,structure.inactive_exposed,structure.join_depth",
    ])
    assert code == 0


def test_select_section_only(bad_snowflake_path, fixtures_config, capsys):
    # Selecting only metadata drops the structural gates, so exit is 0 (warnings only).
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config, "--select", "metadata"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Direct many-to-many" not in out


def test_github_format_emits_annotations(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config, "--format", "github"])
    out = capsys.readouterr().out
    assert code == 1
    assert "::error title=Copilot Readiness" in out
    assert "::notice title=Copilot Readiness::" in out


def test_json_report_is_valid(bad_snowflake_path, fixtures_config, capsys):
    code = main(["lint", bad_snowflake_path, "--config", fixtures_config, "--format", "json"])
    out = capsys.readouterr().out
    assert code == 1
    payload = json.loads(out)
    assert payload["overall_ready"] is False
    assert payload["models"][0]["blocking_count"] >= 1


def test_scan_repo_discovers_both_models(fixtures_dir, fixtures_config, capsys):
    code = main(["lint", fixtures_dir, "--config", fixtures_config])
    out = capsys.readouterr().out
    # bad_snowflake makes the overall run fail.
    assert code == 1
    assert "good_star" in out
    assert "bad_snowflake" in out
