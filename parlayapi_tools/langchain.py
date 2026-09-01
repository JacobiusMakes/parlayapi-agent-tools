"""LangChain StructuredTool wrappers for ParlayAPI.

    from parlayapi_tools.langchain import get_parlayapi_tools

    tools = get_parlayapi_tools()          # reads PARLAY_API_KEY
    agent = create_react_agent(llm, tools)

LangChain is an optional dependency. Importing this module without it
installed raises an ImportError that says what to install, and the rest of
the package keeps working.

Every tool description here comes from ``parlayapi_tools.openai_schemas``,
so the LangChain, LlamaIndex and raw JSON surfaces always say the same
thing to the model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .core import ParlayAPIClient
from .openai_schemas import TOOL_SPECS, get_handler

__all__ = ["ARG_SCHEMAS", "get_keyless_tools", "get_parlayapi_tools"]

try:  # pragma: no cover - exercised by the import guard test
    from langchain_core.tools import StructuredTool
except ImportError as _exc:  # pragma: no cover
    try:
        from langchain.tools import StructuredTool  # type: ignore[no-redef]
    except ImportError:
        raise ImportError(
            "parlayapi_tools.langchain needs LangChain. Install it with:\n"
            "    pip install 'parlayapi-agent-tools[langchain]'\n"
            "or\n"
            "    pip install langchain-core\n"
            "The rest of parlayapi_tools works without it."
        ) from _exc

from ._argschemas import ARG_SCHEMAS  # noqa: E402  (after the import guard)

_KEYLESS = {
    "parlayapi_list_sports",
    "parlayapi_demo_odds",
    "parlayapi_demo_positive_ev",
}


def _bind(handler: Callable[..., Any], client: ParlayAPIClient) -> Callable[..., Any]:
    def call(**kwargs: Any) -> Any:
        return handler(client, **kwargs)

    return call


def get_parlayapi_tools(
    api_key: str | None = None,
    *,
    client: ParlayAPIClient | None = None,
    include_demo: bool = True,
    only: Sequence[str] | None = None,
) -> list[StructuredTool]:
    """Build the ParlayAPI LangChain tools.

    Args:
        api_key: ParlayAPI key. Defaults to the PARLAY_API_KEY environment
            variable. The three keyless tools work without one.
        client: Supply your own configured ParlayAPIClient instead.
        include_demo: Include the two keyless demo tools. Leave them in when
            a key may be missing, so the agent can still show real data.
        only: Optional list of tool names to build, for a tighter tool belt.

    Returns:
        A list of langchain_core StructuredTool objects, ready to hand to
        create_react_agent, bind_tools, or any LangChain agent executor.
    """
    client = client or ParlayAPIClient(api_key)
    wanted = set(only) if only else None

    tools: list[StructuredTool] = []
    for spec in TOOL_SPECS:
        if wanted is not None and spec.name not in wanted:
            continue
        if not include_demo and spec.name in {
            "parlayapi_demo_odds",
            "parlayapi_demo_positive_ev",
        }:
            continue
        tools.append(
            StructuredTool.from_function(
                func=_bind(get_handler(spec.name), client),
                name=spec.name,
                description=spec.description,
                args_schema=ARG_SCHEMAS[spec.name],
                return_direct=False,
            )
        )
    return tools


def get_keyless_tools(**kwargs: Any) -> list[StructuredTool]:
    """Only the tools that need no API key, for demos and public examples."""
    return get_parlayapi_tools(only=sorted(_KEYLESS), **kwargs)
