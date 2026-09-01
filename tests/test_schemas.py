"""The tool schemas: shape, wiring, and what the descriptions promise."""

from __future__ import annotations

import inspect
import json
import re

import pytest

from parlayapi_tools.core import DEMO_SPORTS, ParlayAPIClient
from parlayapi_tools.openai_schemas import (
    ANTHROPIC_TOOLS,
    OPENAI_TOOLS,
    TOOL_SPECS,
    dispatch,
    get_handler,
)

TOOL_NAMES = [spec.name for spec in TOOL_SPECS]


class TestSpecShape:
    def test_names_are_unique_and_namespaced(self):
        assert len(set(TOOL_NAMES)) == len(TOOL_NAMES)
        assert all(name.startswith("parlayapi_") for name in TOOL_NAMES)

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=TOOL_NAMES)
    def test_schema_is_a_valid_object_schema(self, spec):
        params = spec.parameters
        assert params["type"] == "object"
        assert isinstance(params["properties"], dict)
        assert params["additionalProperties"] is False
        for name, prop in params["properties"].items():
            assert prop.get("type"), f"{spec.name}.{name} has no type"
            assert prop.get("description"), f"{spec.name}.{name} has no description"

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=TOOL_NAMES)
    def test_required_args_are_declared_properties(self, spec):
        missing = set(spec.parameters["required"]) - set(spec.parameters["properties"])
        assert not missing, f"{spec.name} requires undeclared args: {missing}"

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=TOOL_NAMES)
    def test_description_is_written_for_a_model(self, spec):
        # A one liner is not a prompt. These descriptions are the only thing
        # standing between the model and a wrong tool choice.
        assert len(spec.description) > 200, f"{spec.name} description is too thin"
        assert "\n" in spec.description

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=TOOL_NAMES)
    def test_schema_is_json_serialisable(self, spec):
        json.loads(json.dumps(spec.openai()))
        json.loads(json.dumps(spec.anthropic()))


class TestWiring:
    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=TOOL_NAMES)
    def test_every_declared_argument_exists_on_the_handler(self, spec):
        handler = get_handler(spec.name)
        # functools.wraps means signature() sees through the error guard.
        accepted = set(inspect.signature(handler).parameters)
        declared = set(spec.parameters["properties"])
        unknown = declared - accepted
        assert not unknown, f"{spec.name} declares args its handler rejects: {unknown}"

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=TOOL_NAMES)
    def test_every_required_handler_argument_is_declared(self, spec):
        handler = get_handler(spec.name)
        sig = inspect.signature(handler)
        required_on_handler = {
            name
            for name, p in sig.parameters.items()
            if name != "client" and p.default is inspect.Parameter.empty
        }
        assert required_on_handler <= set(spec.parameters["required"])


class TestProviderShapes:
    def test_openai_shape(self):
        assert len(OPENAI_TOOLS) == len(TOOL_SPECS)
        for tool in OPENAI_TOOLS:
            assert tool["type"] == "function"
            assert set(tool["function"]) == {"name", "description", "parameters"}

    def test_anthropic_shape(self):
        assert len(ANTHROPIC_TOOLS) == len(TOOL_SPECS)
        for tool in ANTHROPIC_TOOLS:
            assert set(tool) == {"name", "description", "input_schema"}
            assert tool["input_schema"]["type"] == "object"

    def test_both_providers_describe_the_same_tools(self):
        assert [t["function"]["name"] for t in OPENAI_TOOLS] == [
            t["name"] for t in ANTHROPIC_TOOLS
        ]
        assert [t["function"]["parameters"] for t in OPENAI_TOOLS] == [
            t["input_schema"] for t in ANTHROPIC_TOOLS
        ]


class TestDemoConsistency:
    @pytest.mark.parametrize(
        "name", ["parlayapi_demo_odds", "parlayapi_demo_positive_ev"]
    )
    def test_demo_enum_matches_what_the_api_accepts(self, name):
        spec = next(s for s in TOOL_SPECS if s.name == name)
        enum = spec.parameters["properties"]["sport_key"]["enum"]
        assert sorted(enum) == sorted(DEMO_SPORTS)

    @pytest.mark.parametrize(
        "name", ["parlayapi_demo_odds", "parlayapi_demo_positive_ev"]
    )
    def test_demo_default_is_a_demo_sport(self, name):
        spec = next(s for s in TOOL_SPECS if s.name == name)
        assert spec.parameters["properties"]["sport_key"]["default"] in DEMO_SPORTS


class TestHonesty:
    """Claims in model facing text have to survive the same review as the
    marketing site, because the model repeats them to the user verbatim."""

    # Whitespace collapsed, so a claim cannot hide from this check just by
    # falling across a line break in the source.
    ALL_TEXT = re.sub(
        r"\s+",
        " ",
        "\n".join(
            spec.description + json.dumps(spec.parameters) for spec in TOOL_SPECS
        ),
    )

    def test_no_dashes_that_break_the_house_style(self):
        # Written as escapes, not literal characters, so a dash scrubber
        # run over this repo cannot quietly rewrite the assertion into one
        # that always passes.
        assert "\u2014" not in self.ALL_TEXT, "em dash in model facing text"
        assert "\u2013" not in self.ALL_TEXT, "en dash in model facing text"

    def test_no_hardcoded_paid_prices(self):
        lowered = self.ALL_TEXT.lower()
        for banned in ("$5", "$20", "$40", "/month for", "per month for $"):
            assert banned not in lowered, f"paid price {banned!r} is hardcoded"

    def test_free_tier_is_described_correctly(self):
        assert "1,000 credits" in self.ALL_TEXT
        assert "no card" in self.ALL_TEXT
        assert "https://parlay-api.com/signup" in self.ALL_TEXT

    def test_book_count_claim_matches_the_approved_wording(self):
        assert "30+ sportsbooks" in self.ALL_TEXT
        for overclaim in ("40+ sportsbooks", "50+ sportsbooks", "every sportsbook"):
            assert overclaim not in self.ALL_TEXT

    def test_no_uptime_or_customer_claims(self):
        lowered = self.ALL_TEXT.lower()
        for banned in ("99.9", "uptime", "thousands of customers", "trusted by"):
            assert banned not in lowered

    def test_ev_tool_does_not_promise_profit(self):
        spec = next(s for s in TOOL_SPECS if s.name == "parlayapi_demo_positive_ev")
        lowered = spec.description.lower()
        assert "not a guarantee" in lowered
        assert "never present any result from" in lowered
        assert "guaranteed profit" not in lowered


class TestDispatch:
    def test_unknown_tool_returns_a_readable_error(self):
        result = dispatch("parlayapi_not_a_tool", {})
        assert result["ok"] is False
        assert "parlayapi_get_odds" in result["available_tools"]

    def test_bad_arguments_return_the_expected_parameter_list(self):
        result = dispatch("parlayapi_demo_odds", {"sport": "nfl"})
        assert result["ok"] is False
        assert "sport_key" in result["expected_parameters"]

    def test_missing_key_is_returned_not_raised(self, monkeypatch):
        monkeypatch.delenv("PARLAY_API_KEY", raising=False)
        result = dispatch(
            "parlayapi_get_odds",
            {"sport_key": "americanfootball_nfl"},
            client=ParlayAPIClient(api_key=None),
        )
        assert result["ok"] is False
        assert result["signup_url"] == "https://parlay-api.com/signup"
