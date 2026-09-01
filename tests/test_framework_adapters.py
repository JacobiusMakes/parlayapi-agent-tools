"""The LangChain and LlamaIndex adapters.

Each framework is optional, so each block skips when its framework is not
installed. The point of these tests is that the adapter really builds real
tool objects, not that a mock accepted our arguments.
"""

from __future__ import annotations

import json

import pytest

from parlayapi_tools.core import ParlayAPIClient
from parlayapi_tools.openai_schemas import TOOL_SPECS

TOOL_NAMES = {spec.name for spec in TOOL_SPECS}
KEYLESS = {
    "parlayapi_list_sports",
    "parlayapi_demo_odds",
    "parlayapi_demo_positive_ev",
}


class TestArgSchemas:
    """These need pydantic only, which both frameworks depend on."""

    def test_every_tool_has_an_argument_model(self):
        pytest.importorskip("pydantic")
        from parlayapi_tools._argschemas import ARG_SCHEMAS

        assert set(ARG_SCHEMAS) == TOOL_NAMES

    def test_model_fields_match_the_json_schema(self):
        pytest.importorskip("pydantic")
        from parlayapi_tools._argschemas import ARG_SCHEMAS

        for spec in TOOL_SPECS:
            model = ARG_SCHEMAS[spec.name]
            assert set(model.model_fields) == set(spec.parameters["properties"]), (
                f"{spec.name}: pydantic model and JSON schema disagree on arguments"
            )

    def test_required_arguments_agree(self):
        pytest.importorskip("pydantic")
        from parlayapi_tools._argschemas import ARG_SCHEMAS

        for spec in TOOL_SPECS:
            model = ARG_SCHEMAS[spec.name]
            required = {
                name for name, f in model.model_fields.items() if f.is_required()
            }
            assert required == set(spec.parameters["required"]), spec.name

    def test_every_field_carries_help_text_for_the_model(self):
        pytest.importorskip("pydantic")
        from parlayapi_tools._argschemas import ARG_SCHEMAS

        for name, model in ARG_SCHEMAS.items():
            for field_name, f in model.model_fields.items():
                assert f.description, f"{name}.{field_name} has no description"


class TestLangChain:
    @pytest.fixture(autouse=True)
    def _requires_langchain(self):
        pytest.importorskip("langchain_core")

    def test_builds_one_structured_tool_per_spec(self):
        from parlayapi_tools.langchain import get_parlayapi_tools

        tools = get_parlayapi_tools(api_key="test-key")
        assert {t.name for t in tools} == TOOL_NAMES
        for tool in tools:
            assert tool.description and len(tool.description) > 200
            assert tool.args_schema is not None

    def test_tool_args_are_exposed_to_the_model(self):
        from parlayapi_tools.langchain import get_parlayapi_tools

        odds = next(
            t
            for t in get_parlayapi_tools(api_key="test-key")
            if t.name == "parlayapi_get_odds"
        )
        assert "sport_key" in odds.args
        assert odds.args["sport_key"].get("description")
        # The whole tool must survive a JSON round trip for the wire format.
        json.dumps(odds.args)

    def test_only_filter_narrows_the_tool_belt(self):
        from parlayapi_tools.langchain import get_keyless_tools

        assert {t.name for t in get_keyless_tools()} == KEYLESS

    def test_include_demo_false_drops_the_demo_tools(self):
        from parlayapi_tools.langchain import get_parlayapi_tools

        names = {t.name for t in get_parlayapi_tools(api_key="k", include_demo=False)}
        assert "parlayapi_demo_odds" not in names
        assert "parlayapi_get_odds" in names

    def test_invoking_a_tool_without_a_key_returns_the_signup_url(self):
        from parlayapi_tools.langchain import get_parlayapi_tools

        tools = get_parlayapi_tools(client=ParlayAPIClient(api_key=None))
        odds = next(t for t in tools if t.name == "parlayapi_get_odds")
        result = odds.invoke({"sport_key": "americanfootball_nfl"})
        assert result["ok"] is False
        assert result["signup_url"] == "https://parlay-api.com/signup"

    def test_bad_arguments_are_rejected_by_the_schema(self):
        from parlayapi_tools.langchain import get_parlayapi_tools

        odds = next(
            t
            for t in get_parlayapi_tools(api_key="k")
            if t.name == "parlayapi_get_odds"
        )
        # pydantic's ValidationError subclasses ValueError.
        with pytest.raises(ValueError):
            odds.invoke({"regions": "us"})  # sport_key is required


class TestLlamaIndex:
    @pytest.fixture(autouse=True)
    def _requires_llamaindex(self):
        pytest.importorskip("llama_index.core")

    def test_builds_one_function_tool_per_spec(self):
        from parlayapi_tools.llamaindex import get_parlayapi_tools

        tools = get_parlayapi_tools(api_key="test-key")
        assert {t.metadata.name for t in tools} == TOOL_NAMES
        for tool in tools:
            assert tool.metadata.description
            assert tool.metadata.fn_schema is not None

    def test_openai_tool_schema_round_trips(self):
        from parlayapi_tools.llamaindex import get_parlayapi_tools

        tools = get_parlayapi_tools(api_key="test-key")
        for tool in tools:
            schema = tool.metadata.to_openai_tool()
            assert schema["function"]["name"] == tool.metadata.name
            json.dumps(schema)

    def test_calling_a_tool_without_a_key_returns_the_signup_url(self):
        from parlayapi_tools.llamaindex import get_parlayapi_tools

        tools = get_parlayapi_tools(client=ParlayAPIClient(api_key=None))
        odds = next(t for t in tools if t.metadata.name == "parlayapi_get_odds")
        output = odds.call(sport_key="americanfootball_nfl")
        assert "parlay-api.com/signup" in str(output)
