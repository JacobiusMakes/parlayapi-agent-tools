"""End to end smoke test against the live keyless endpoints.

No API key involved, so anyone can run this:

    pytest -m network

Skipped by default in CI so a network blip cannot turn a code review red.
Run it with PARLAYAPI_LIVE_TESTS=1, or with -m network.

The live demo endpoints are rate limited to 60 requests per hour per IP
(30 for arbitrage), so this file makes exactly two calls.
"""

from __future__ import annotations

import os

import pytest

from parlayapi_tools import DEMO_SPORTS, ParlayAPIClient, ParlayAPIError
from parlayapi_tools.openai_schemas import dispatch

LIVE = os.environ.get("PARLAYAPI_LIVE_TESTS") == "1"

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not LIVE, reason="set PARLAYAPI_LIVE_TESTS=1 to hit the live API"
    ),
]


@pytest.fixture(scope="module")
def live_demo():
    client = ParlayAPIClient(api_key=None)
    try:
        return client.demo_odds("baseball_mlb")
    except ParlayAPIError as exc:
        pytest.skip(f"live demo endpoint unavailable: {exc}")


def test_demo_odds_end_to_end(live_demo):
    assert live_demo.demo is True
    assert live_demo.sport_key == "baseball_mlb"
    assert live_demo.events, "the demo should return events"
    assert live_demo.events_returned == len(live_demo.events)
    assert live_demo.demo_signup_url.startswith("https://parlay-api.com")

    event = live_demo.events[0]
    assert event.home_team and event.away_team
    assert event.bookmakers, "the demo should return bookmaker prices"
    prices = [
        o.price
        for b in event.bookmakers
        for m in b.markets
        if m.key == "h2h"
        for o in m.outcomes
    ]
    assert prices and all(p is not None for p in prices)


def test_dispatch_runs_a_real_tool_call_without_a_key():
    result = dispatch(
        "parlayapi_demo_odds",
        {"sport_key": "americanfootball_nfl"},
        client=ParlayAPIClient(api_key=None),
    )
    if not result.get("ok"):
        pytest.skip(f"live demo endpoint unavailable: {result.get('error')}")
    assert result["demo"] is True
    assert result["sport_key"] == "americanfootball_nfl"
    assert isinstance(result["summary"], str) and result["summary"]


def test_unsupported_demo_sport_reports_the_supported_list():
    client = ParlayAPIClient(api_key=None)
    with pytest.raises(ParlayAPIError) as excinfo:
        client.demo_odds("not_a_real_sport")
    assert set(excinfo.value.available_demo_sports) == set(DEMO_SPORTS)
