"""Function calling schemas with no framework at all.

    python examples/raw_function_calling.py

Prints the OpenAI and Anthropic tool schemas, then runs one tool call
through dispatch() exactly the way an agent loop would, using the keyless
demo so it works without an API key.
"""

from __future__ import annotations

import json

from parlayapi_tools.core import ParlayAPIClient
from parlayapi_tools.openai_schemas import ANTHROPIC_TOOLS, OPENAI_TOOLS, dispatch


def main() -> int:
    print("== OpenAI tools= payload ==")
    print(json.dumps(OPENAI_TOOLS[0], indent=2)[:900], "...\n")

    print("== Anthropic tools= payload ==")
    print(json.dumps(ANTHROPIC_TOOLS[0], indent=2)[:900], "...\n")

    print("== tool names ==")
    for tool in OPENAI_TOOLS:
        print("  ", tool["function"]["name"])
    print()

    # This is the shape of what a model sends back, and what you do with it.
    tool_call = {
        "name": "parlayapi_demo_odds",
        "arguments": {"sport_key": "americanfootball_nfl"},
    }
    print(f"== dispatching {tool_call['name']} ==")
    result = dispatch(
        tool_call["name"],
        tool_call["arguments"],
        client=ParlayAPIClient(api_key=None),
    )
    if result.get("ok"):
        print(result["summary"])
    else:
        # Errors come back as data, with the fix included as a field.
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
