from copilot_readiness.config import Config
from copilot_readiness.rules import run_all_rules
from copilot_readiness.rules.base import Status
from copilot_readiness.tmdl_parser import parse_model


def _findings_by_rule(findings, rule_id):
    return [f for f in findings if f.rule_id == rule_id]


def test_good_star_has_no_blocking_findings(good_star_path):
    model = parse_model(good_star_path)
    config = Config(fact_tables_by_model={"good_star": ["Sales"]})
    findings = run_all_rules(model, config)
    blocking = [f for f in findings if f.is_blocking]
    assert blocking == [], [f"{f.rule_id}:{f.obj}" for f in blocking]


def test_bad_snowflake_flags_many_to_many(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    findings = run_all_rules(model, config)
    m2m = _findings_by_rule(findings, "structure.many_to_many")
    assert any(f.status == Status.FAIL for f in m2m)


def test_bad_snowflake_flags_bidirectional(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    findings = run_all_rules(model, config)
    bidi = _findings_by_rule(findings, "structure.bidirectional")
    assert any(f.status == Status.FAIL for f in bidi)


def test_bad_snowflake_flags_inactive_exposed(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    findings = run_all_rules(model, config)
    inactive = _findings_by_rule(findings, "structure.inactive_exposed")
    # ShipDateKey is visible, so the inactive relationship must fail.
    assert any(f.status == Status.FAIL for f in inactive)


def test_bad_snowflake_flags_join_depth(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    findings = run_all_rules(model, config)
    depth = _findings_by_rule(findings, "structure.join_depth")
    failed_objects = {f.obj for f in depth if f.status == Status.FAIL}
    # SubCategory is 2 hops, Category is 3 hops from the fact.
    assert "DimSubCategory" in failed_objects
    assert "DimCategory" in failed_objects


def test_missing_fact_declaration_blocks(good_star_path):
    model = parse_model(good_star_path)
    findings = run_all_rules(model, Config())  # no fact declared
    config_err = _findings_by_rule(findings, "config.no_fact_table")
    assert any(f.is_blocking for f in config_err)
