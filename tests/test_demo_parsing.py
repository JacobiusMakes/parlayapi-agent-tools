"""Demo mode parsing, against real captured responses."""

from __future__ import annotations

import pytest

from parlayapi_tools.core import (
    DemoOdds,
    DemoPositiveEV,
    ParlayAPIError,
    Sport,
    events_from_payload,
    format_events_for_llm,
)


class TestDemoOddsEnvelope:
    def test_events_are_nested_under_events_key(self, try_mlb_odds):
        # The mistake this package exists to stop people making: the demo
        # response is an object, not a list, and the games hang off "events".
        assert isinstance(try_mlb_odds, dict)
        assert "events" in try_mlb_odds
        assert isinstance(try_mlb_odds["events"], list)

    def test_parses_the_envelope(self, try_mlb_odds):
        demo = DemoOdds.from_dict(try_mlb_odds)
        assert demo.demo is True
        assert demo.sport_key == "baseball_mlb"
        assert demo.events_returned == len(demo.events) == 5
        assert demo.demo_signup_url == "https://parlay-api.com/signup"
        assert isinstance(demo.demo_remaining_hour, int)

    def test_events_carry_teams_books_and_prices(self, try_mlb_odds):
        demo = DemoOdds.from_dict(try_mlb_odds)
        event = demo.events[0]
        assert event.id
        assert event.home_team and event.away_team
        assert event.commence_time and event.commence_time.endswith("Z")
        assert event.bookmakers, "demo events should carry bookmaker prices"

        book = event.bookmakers[0]
        h2h = book.market("h2h")
        assert h2h is not None, "the keyless demo serves the h2h market"
        assert len(h2h.outcomes) == 2
        for outcome in h2h.outcomes:
            assert outcome.name in (event.home_team, event.away_team)
            assert outcome.price is not None

    def test_raw_is_preserved_for_unmodelled_fields(self, try_mlb_odds):
        demo = DemoOdds.from_dict(try_mlb_odds)
        book = demo.events[0].bookmakers[0]
        # last_update_ms is real and not a dataclass field. It must survive.
        assert "last_update_ms" in book.raw

    def test_best_price_picks_the_highest_number(self, try_mlb_odds):
        demo = DemoOdds.from_dict(try_mlb_odds)
        event = demo.events[0]
        side = event.home_team
        best = event.best_price("h2h", side)
        assert best is not None
        book_key, price = best
        offered = [
            o.price
            for b in event.bookmakers
            for m in b.markets
            if m.key == "h2h"
            for o in m.outcomes
            if o.name == side and o.price is not None
        ]
        assert price == max(offered)
        assert book_key in {b.key for b in event.bookmakers}

    def test_missing_side_returns_none(self, try_mlb_odds):
        demo = DemoOdds.from_dict(try_mlb_odds)
        assert demo.events[0].best_price("h2h", "Not A Real Team") is None


class TestEventsFromPayload:
    def test_accepts_the_demo_envelope(self, try_mlb_odds):
        assert len(events_from_payload(try_mlb_odds)) == 5

    def test_accepts_a_bare_list(self, try_mlb_odds):
        # The keyed odds endpoint is the-odds-api compatible and documented
        # to answer with a bare list, so the same parser has to take both.
        assert len(events_from_payload(try_mlb_odds["events"])) == 5

    @pytest.mark.parametrize("payload", [None, {}, [], "nope", {"events": None}, 7])
    def test_junk_yields_no_events_instead_of_raising(self, payload):
        assert events_from_payload(payload) == ()


class TestPositiveEVDemo:
    def test_parses_opportunities(self, try_mlb_ev):
        demo = DemoPositiveEV.from_dict(try_mlb_ev)
        assert demo.sport_key == "baseball_mlb"
        assert demo.sharp_anchor == "pinnacle"
        assert demo.opportunities_returned == len(demo.opportunities)
        assert demo.opportunities

        opp = demo.opportunities[0]
        assert opp.book and opp.side
        assert opp.edge_pct is not None and opp.price is not None

    def test_edges_are_sorted_best_first(self, try_mlb_ev):
        edges = [o.edge_pct for o in DemoPositiveEV.from_dict(try_mlb_ev).opportunities]
        assert edges == sorted(edges, reverse=True)


class TestSports:
    def test_parses_sport_rows(self, sports_head):
        sports = [Sport.from_dict(row) for row in sports_head]
        keys = {s.key for s in sports}
        assert "baseball_mlb" in keys
        assert "americanfootball_nfl" in keys
        mlb = next(s for s in sports if s.key == "baseball_mlb")
        assert mlb.title == "MLB"
        assert mlb.group == "Baseball"


class TestErrorParsing:
    def test_missing_key_body_surfaces_signup_url(self, error_missing_key):
        err = ParlayAPIError.from_payload(error_missing_key, status=401)
        assert err.error_code == "MISSING_KEY"
        assert err.signup_url == "https://parlay-api.com/signup"
        assert err.request_id
        assert err.status == 401
        # The string form is what the model reads, so the fix must be in it.
        assert "signup" in str(err)

    def test_demo_sport_body_is_top_level_not_nested(self, error_demo_sport):
        # This body has no "detail" wrapper. Both shapes have to parse.
        assert "detail" not in error_demo_sport
        err = ParlayAPIError.from_payload(error_demo_sport, status=400)
        assert err.error_code == "demo_sport_not_supported"
        assert "baseball_mlb" in err.available_demo_sports
        assert "baseball_mlb" in str(err)

    def test_credit_limit_fields_are_carried(self):
        # Field names taken from the API's own error builder.
        body = {
            "detail": {
                "error": "OUT_OF_USAGE_CREDITS",
                "message": "You've used all your credits for this billing period.",
                "upgrade_url": "https://parlay-api.com/upgrade",
                "pricing_url": "https://parlay-api.com/pricing",
                "credits_reset_at": "2026-10-01T00:00:00Z",
                "status": 403,
            }
        }
        err = ParlayAPIError.from_payload(body, status=403)
        assert err.upgrade_url and err.pricing_url
        assert err.credits_reset_at == "2026-10-01T00:00:00Z"
        assert "2026-10-01T00:00:00Z" in str(err)

    def test_unparseable_body_still_gives_a_usable_message(self):
        err = ParlayAPIError.from_payload("<html>gateway timeout</html>", status=504)
        assert err.status == 504
        assert "504" in str(err)


class TestFormatForLLM:
    def test_renders_matchups_and_prices(self, try_mlb_odds):
        demo = DemoOdds.from_dict(try_mlb_odds)
        text = format_events_for_llm(demo.events, "h2h")
        first = demo.events[0]
        assert first.home_team in text
        assert first.away_team in text
        assert " at " in text
        # Compact by design: it must be far smaller than the raw JSON.
        assert len(text) < len(str(try_mlb_odds)) / 2

    def test_empty_input_says_so(self):
        assert format_events_for_llm([]) == "No events returned."
