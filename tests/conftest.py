"""Shared fixtures.

Every JSON file under tests/fixtures/ is a real response captured from the
live API on 2026-09-01. Nothing here is hand written, because a parser
tested against invented JSON only proves the invention parses.
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="session")
def try_mlb_odds():
    """Captured GET https://parlay-api.com/v1/try/baseball_mlb/odds"""
    return load("try_baseball_mlb_odds.json")


@pytest.fixture(scope="session")
def try_mlb_ev():
    """Captured GET https://parlay-api.com/v1/try/baseball_mlb/ev"""
    return load("try_baseball_mlb_ev.json")


@pytest.fixture(scope="session")
def sports_head():
    """First 40 rows of the captured GET https://parlay-api.com/v1/sports"""
    return load("sports_head.json")


@pytest.fixture(scope="session")
def error_missing_key():
    """Captured 401 from an unauthenticated GET /v1/sports/{key}/odds"""
    return load("error_missing_key.json")


@pytest.fixture(scope="session")
def error_demo_sport():
    """Captured 400 from GET /v1/try/not_a_sport/odds"""
    return load("error_demo_sport.json")
