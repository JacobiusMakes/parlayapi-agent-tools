"""LlamaIndex FunctionTool wrappers for ParlayAPI.

    from parlayapi_tools.llamaindex import get_parlayapi_tools

    tools = get_parlayapi_tools()          # reads PARLAY_API_KEY
    agent = FunctionAgent(tools=tools, llm=llm)

LlamaIndex is an optional dependency. Importing this module without it
installed raises an ImportError that says what to install, and the rest of
the package keeps working.

The tool names, descriptions and argument schemas are the same objects the
LangChain adapter and the raw JSON schemas use, so a model sees an
identical tool belt whichever framework you run.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .core import ParlayAPIClient
from .openai_schemas import TOOL_SPECS, get_handler

__all__ = ["get_parlayapi_tools", "get_keyless_tools"]

try:  # pragma: no cover - exercised by the import guard test
    from llama_index.core.tools import FunctionTool
except ImportError as _exc:  # pragma: no cover
    try:
        from llama_index.tools import FunctionTool  # type: ignore[no-redef]
    except ImportError:
        raise ImportError(
            "parlayapi_tools.llamaindex needs LlamaIndex. Install it with:\n"
            "    pip install 'parlayapi-agent-tools[llamaindex]'\n"
            "or\n"
            "    pip install llama-index-core\n"
            "The rest of parlayapi_tools works without it."
        ) from _exc

# The pydantic argument models are shared with the LangChain adapter and
# need pydantic only, which LlamaIndex already depends on.
from ._argschemas import ARG_SCHEMAS as _ARG_SCHEMAS  # noqa: E402

_KEYLESS = {
    "parlayapi_list_sports",
    "parlayapi_demo_odds",
    "parlayapi_demo_positive_ev",
}


def _bind(
    handler: Callable[..., Any], client: ParlayAPIClient, spec_name: str
) -> Callable[..., Any]:
    def call(**kwargs: Any) -> Any:
        return handler(client, **kwargs)

    call.__name__ = spec_name
    return call


def get_parlayapi_tools(
    api_key: str | None = None,
    *,
    client: ParlayAPIClient | None = None,
    include_demo: bool = True,
    only: Sequence[str] | None = None,
) -> list[FunctionTool]:
    """Build the ParlayAPI LlamaIndex tools.

    Args:
        api_key: ParlayAPI key. Defaults to the PARLAY_API_KEY environment
            variable. The three keyless tools work without one.
        client: Supply your own configured ParlayAPIClient instead.
        include_demo: Include the two keyless demo tools.
        only: Optional list of tool names to build.

    Returns:
        A list of llama_index FunctionTool objects, ready for FunctionAgent,
        ReActAgent, or any LlamaIndex agent worker.
    """
    client = client or ParlayAPIClient(api_key)
    wanted = set(only) if only else None

    tools: list[FunctionTool] = []
    for spec in TOOL_SPECS:
        if wanted is not None and spec.name not in wanted:
            continue
        if not include_demo and spec.name in {
            "parlayapi_demo_odds",
            "parlayapi_demo_positive_ev",
        }:
            continue

        kwargs: dict[str, Any] = {
            "fn": _bind(get_handler(spec.name), client, spec.name),
            "name": spec.name,
            "description": spec.description,
        }
        schema = _ARG_SCHEMAS.get(spec.name)
        if schema is not None:
            kwargs["fn_schema"] = schema
        tools.append(FunctionTool.from_defaults(**kwargs))
    return tools


def get_keyless_tools(**kwargs: Any) -> list[FunctionTool]:
    """Only the tools that need no API key, for demos and public examples."""
    return get_parlayapi_tools(only=sorted(_KEYLESS), **kwargs)
