from copilot_readiness.config import Config
from copilot_readiness.rules import run_all_rules
from copilot_readiness.rules.base import Status
from copilot_readiness.tmdl_parser import parse_model


def _by_rule(findings, rule_id):
    return [f for f in findings if f.rule_id == rule_id]


def test_naming_flags_technical_prefixes(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    findings = run_all_rules(model, Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]}))
    naming = _by_rule(findings, "metadata.naming")
    flagged = {f.obj for f in naming if f.status == Status.FAIL}
    assert "f_sls_trx" in flagged
    assert any(o.startswith("DimCustomer") or o == "DimCustomer" for o in flagged)


def test_good_star_naming_passes(good_star_path):
    model = parse_model(good_star_path)
    findings = run_all_rules(model, Config(fact_tables_by_model={"good_star": ["Sales"]}))
    naming = _by_rule(findings, "metadata.naming")
    assert all(f.status == Status.PASS for f in naming)


def test_non_summable_year_flagged(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    findings = run_all_rules(model, Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]}))
    non_summable = _by_rule(findings, "metadata.non_summable")
    failed = {f.obj for f in non_summable if f.status == Status.FAIL}
    # DimDate.Year is summarizeBy sum; CustomerKey on the fact is summed too.
    assert "DimDate.Year" in failed


def test_geo_category_pass_on_good_star(good_star_path):
    model = parse_model(good_star_path)
    findings = run_all_rules(model, Config(fact_tables_by_model={"good_star": ["Sales"]}))
    geo = _by_rule(findings, "metadata.geo_category")
    assert geo and all(f.status == Status.PASS for f in geo)


def test_synonyms_manual_when_no_culture(good_star_path):
    model = parse_model(good_star_path)
    findings = run_all_rules(model, Config(fact_tables_by_model={"good_star": ["Sales"]}))
    syn = _by_rule(findings, "metadata.synonyms")
    assert syn and syn[0].status == Status.MANUAL
    assert syn[0].auto_verified is False
