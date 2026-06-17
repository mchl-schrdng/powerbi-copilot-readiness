from copilot_readiness.config import Config
from copilot_readiness.gate import Verdict, evaluate
from copilot_readiness.rules import run_all_rules
from copilot_readiness.tmdl_parser import parse_model


def test_undeclared_fact_is_incomplete_not_not_ready(good_star_path):
    """A clean model with no declared fact is INCOMPLETE, not NOT READY."""
    model = parse_model(good_star_path)
    result = evaluate(model.name, good_star_path, run_all_rules(model, Config()))
    assert result.verdict == Verdict.INCOMPLETE
    assert result.is_ready is False
    assert result.real_blocking == []      # no genuine defect
    assert result.config_gaps              # just the missing input


def test_finition_score_capped_when_not_ready(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    result = evaluate(model.name, bad_snowflake_path, run_all_rules(model, config))
    assert result.verdict == Verdict.NOT_READY
    assert result.finition is not None and result.finition <= 49


def test_good_star_finition_not_capped(good_star_path):
    model = parse_model(good_star_path)
    config = Config(fact_tables_by_model={"good_star": ["Sales"]})
    result = evaluate(model.name, good_star_path, run_all_rules(model, config))
    assert result.verdict == Verdict.READY
    # A clean star scores well above the NOT READY cap.
    assert result.finition is not None and result.finition > 49


def test_good_star_is_ready(good_star_path):
    model = parse_model(good_star_path)
    config = Config(fact_tables_by_model={"good_star": ["Sales"]})
    result = evaluate(model.name, good_star_path, run_all_rules(model, config))
    assert result.is_ready is True
    assert result.blocking == []


def test_bad_snowflake_is_not_ready(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    result = evaluate(model.name, bad_snowflake_path, run_all_rules(model, config))
    assert result.is_ready is False
    assert len(result.blocking) >= 1


def test_severity_override_can_demote_a_gate(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(
        fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]},
        severity_overrides={
            "structure.many_to_many": "WARN",
            "structure.bidirectional": "WARN",
            "structure.inactive_exposed": "WARN",
            "structure.join_depth": "WARN",
        },
    )
    result = evaluate(model.name, bad_snowflake_path, run_all_rules(model, config))
    # With every structural gate demoted, nothing blocks anymore.
    assert result.is_ready is True
