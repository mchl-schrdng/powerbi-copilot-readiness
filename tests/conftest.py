import os

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def fixtures_dir() -> str:
    return FIXTURES


@pytest.fixture
def good_star_path() -> str:
    return os.path.join(FIXTURES, "good_star.SemanticModel")


@pytest.fixture
def bad_snowflake_path() -> str:
    return os.path.join(FIXTURES, "bad_snowflake.SemanticModel")


@pytest.fixture
def fixtures_config() -> str:
    return os.path.join(FIXTURES, "readiness.yaml")
