"""Every request the client builds must match the real OpenAPI document.

tests/fixtures/openapi_subset.json is trimmed straight out of
https://parlay-api.com/openapi.json. If a method here sends a path or a
query parameter that document does not list, these tests fail. That is the
guard against the usual failure mode for a hand written API wrapper:
plausible looking parameter names that the server quietly ignores.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.parse

import pytest

from parlayapi_tools.core import ParlayAPIClient, ParlayAPIError

from .conftest import load

OPENAPI = load("openapi_subset.json")


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture
def capture(monkeypatch):
    """Intercept urlopen and record the request instead of sending it."""
    calls: list[dict] = []

    def fake_urlopen(request, timeout=None):
        parsed = urllib.parse.urlparse(request.full_url)
        calls.append(
            {
                "url": request.full_url,
                "path": parsed.path,
                "params": dict(urllib.parse.parse_qsl(parsed.query)),
                "headers": {k.lower(): v for k, v in request.header_items()},
                "method": request.get_method(),
            }
        )
        return _FakeResponse(b"[]")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


def _template_for(path: str) -> str:
    """Map a concrete path back to its OpenAPI template."""
    for template in OPENAPI["paths"]:
        pattern = "^" + re.sub(r"\{[^/}]+\}", "[^/]+", template) + "$"
        if re.match(pattern, path):
            return template
    raise AssertionError(f"{path} matches no path in the captured OpenAPI document")


def _allowed_query(template: str) -> set[str]:
    return {
        p["name"]
        for p in OPENAPI["paths"][template]["parameters"]
        if p["in"] == "query"
    }


def assert_documented(call: dict) -> str:
    template = _template_for(call["path"])
    unknown = set(call["params"]) - _allowed_query(template)
    assert not unknown, f"{template} has no query parameter(s): {sorted(unknown)}"
    return template


class TestEndpointsExist:
    def test_list_sports(self, capture):
        ParlayAPIClient(api_key=None).list_sports()
        assert assert_documented(capture[0]) == "/v1/sports"
        assert capture[0]["params"] == {}

    def test_list_sports_include_inactive_uses_the_all_param(self, capture):
        ParlayAPIClient(api_key=None).list_sports(include_inactive=True)
        assert_documented(capture[0])
        assert capture[0]["params"] == {"all": "true"}

    def test_demo_odds(self, capture):
        client = ParlayAPIClient(api_key=None)
        with pytest.raises(ParlayAPIError):
            # A bare list is not a valid demo envelope; we should say so
            # rather than hand back an empty result.
            client.demo_odds("baseball_mlb")
        assert assert_documented(capture[0]) == "/v1/try/{sport_key}/odds"
        assert capture[0]["path"] == "/v1/try/baseball_mlb/odds"

    def test_demo_ev(self, capture):
        with pytest.raises(ParlayAPIError):
            ParlayAPIClient(api_key=None).demo_positive_ev("baseball_mlb")
        assert assert_documented(capture[0]) == "/v1/try/{sport_key}/ev"

    def test_get_odds_sends_camel_case_names(self, capture):
        ParlayAPIClient(api_key="k").get_odds(
            "americanfootball_nfl",
            regions="us,eu",
            markets="h2h,spreads",
            odds_format="decimal",
            bookmakers="pinnacle",
            event_ids="abc,def",
            commence_time_from="2026-09-09T00:00:00Z",
            commence_time_to="2026-09-10T00:00:00Z",
            date="2026-09-09",
            include_live=True,
        )
        call = capture[0]
        assert assert_documented(call) == "/v1/sports/{sport_key}/odds"
        assert call["params"] == {
            "regions": "us,eu",
            "markets": "h2h,spreads",
            "oddsFormat": "decimal",
            "bookmakers": "pinnacle",
            "eventIds": "abc,def",
            "commenceTimeFrom": "2026-09-09T00:00:00Z",
            "commenceTimeTo": "2026-09-10T00:00:00Z",
            "date": "2026-09-09",
            "include_live": "true",
        }

    def test_best_line(self, capture):
        ParlayAPIClient(api_key="k").best_line("americanfootball_nfl", markets="h2h,totals")
        call = capture[0]
        assert assert_documented(call) == "/v1/sports/{sport_key}/best-line"
        assert call["params"] == {"markets": "h2h,totals", "oddsFormat": "american"}

    def test_historical_closing_odds(self, capture):
        ParlayAPIClient(api_key="k").historical_closing_odds(
            "baseball_mlb",
            markets="player_strikeouts",
            bookmakers="pinnacle",
            season="2025",
            date_from="2025-08-01",
            date_to="2025-08-31",
            player="Skenes",
            limit=100,
            offset=0,
        )
        call = capture[0]
        assert assert_documented(call) == "/v1/historical/sports/{sport_key}/closing-odds"
        assert call["params"]["dateFrom"] == "2025-08-01"
        assert call["params"]["dateTo"] == "2025-08-31"
        assert call["params"]["player"] == "Skenes"
        assert call["params"]["limit"] == "100"

    def test_account(self, capture):
        ParlayAPIClient(api_key="k").account(by_endpoint=True)
        call = capture[0]
        assert assert_documented(call) == "/v1/account"
        assert call["params"] == {"by_endpoint": "true"}


class TestAuth:
    def test_key_travels_in_the_documented_header(self, capture):
        ParlayAPIClient(api_key="secret-key").get_odds("baseball_mlb")
        assert capture[0]["headers"]["x-api-key"] == "secret-key"

    def test_key_never_lands_in_the_query_string(self, capture):
        ParlayAPIClient(api_key="secret-key").get_odds("baseball_mlb")
        assert "secret-key" not in capture[0]["url"]

    def test_keyless_calls_send_no_auth_header(self, capture):
        ParlayAPIClient(api_key=None).list_sports()
        assert "x-api-key" not in capture[0]["headers"]

    def test_missing_key_fails_locally_with_the_signup_url(self, capture):
        client = ParlayAPIClient(api_key=None)
        with pytest.raises(ParlayAPIError) as excinfo:
            client.get_odds("baseball_mlb")
        assert excinfo.value.signup_url == "https://parlay-api.com/signup"
        assert not capture, "a keyless call to a keyed endpoint must not hit the network"

    def test_env_var_is_read(self, monkeypatch, capture):
        monkeypatch.setenv("PARLAY_API_KEY", "from-env")
        ParlayAPIClient().get_odds("baseball_mlb")
        assert capture[0]["headers"]["x-api-key"] == "from-env"

    def test_explicit_key_beats_the_env_var(self, monkeypatch, capture):
        monkeypatch.setenv("PARLAY_API_KEY", "from-env")
        ParlayAPIClient(api_key="explicit").get_odds("baseball_mlb")
        assert capture[0]["headers"]["x-api-key"] == "explicit"


class TestPathSafety:
    def test_sport_key_cannot_escape_its_path_segment(self, capture):
        ParlayAPIClient(api_key=None).list_sports()
        capture.clear()
        client = ParlayAPIClient(api_key=None)
        try:
            client.demo_odds("../../v1/account")
        except ParlayAPIError:
            pass
        assert capture[0]["path"] == "/v1/try/..%2F..%2Fv1%2Faccount/odds"


class TestHTTPErrors:
    def test_error_body_is_parsed_into_fields(self, monkeypatch, error_missing_key):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(json.dumps(error_missing_key).encode()),
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(ParlayAPIError) as excinfo:
            ParlayAPIClient(api_key="bad").get_odds("baseball_mlb")
        assert excinfo.value.error_code == "MISSING_KEY"
        assert excinfo.value.signup_url == "https://parlay-api.com/signup"

    def test_non_json_error_body_does_not_crash_the_parser(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 502, "Bad Gateway", {}, io.BytesIO(b"<html>502</html>")
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(ParlayAPIError) as excinfo:
            ParlayAPIClient(api_key="k").get_odds("baseball_mlb")
        assert excinfo.value.status == 502

    def test_network_failure_names_the_host(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("no route to host")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(ParlayAPIError) as excinfo:
            ParlayAPIClient(api_key="k").get_odds("baseball_mlb")
        assert "parlay-api.com" in str(excinfo.value)
