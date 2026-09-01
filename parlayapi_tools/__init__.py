"""Ready made ParlayAPI tools for LangChain, LlamaIndex and raw function calling.

The core client is standard library only. The framework adapters are
imported explicitly, so having just one framework installed is fine:

    from parlayapi_tools import ParlayAPIClient           # always works
    from parlayapi_tools.langchain import get_parlayapi_tools    # needs LangChain
    from parlayapi_tools.llamaindex import get_parlayapi_tools   # needs LlamaIndex
    from parlayapi_tools.openai_schemas import OPENAI_TOOLS      # needs neither

Free key, 1,000 credits per month, no card: https://parlay-api.com/signup
"""

from __future__ import annotations

from .core import (
    DEFAULT_BASE_URL,
    DEMO_SPORTS,
    Bookmaker,
    DemoOdds,
    DemoPositiveEV,
    Event,
    EVOpportunity,
    Market,
    Outcome,
    ParlayAPIClient,
    ParlayAPIError,
    Sport,
    __version__,
    events_from_payload,
    format_events_for_llm,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEMO_SPORTS",
    "Bookmaker",
    "DemoOdds",
    "DemoPositiveEV",
    "EVOpportunity",
    "Event",
    "Market",
    "Outcome",
    "ParlayAPIClient",
    "ParlayAPIError",
    "Sport",
    "__version__",
    "events_from_payload",
    "format_events_for_llm",
]
