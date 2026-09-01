"""A LangChain agent with the ParlayAPI tool belt.

    pip install "parlayapi-agent-tools[langchain]" langchain-openai langgraph
    export PARLAY_API_KEY=...        # https://parlay-api.com/signup
    export OPENAI_API_KEY=...
    python examples/langchain_agent.py "Who is favored in tonight's NHL games?"

Without PARLAY_API_KEY set, this still runs: it hands the model only the
keyless tools, so the agent answers from the free demo feed instead of
refusing.
"""

from __future__ import annotations

import os
import sys

from parlayapi_tools.langchain import get_keyless_tools, get_parlayapi_tools


def build_tools():
    if os.environ.get("PARLAY_API_KEY"):
        return get_parlayapi_tools(), "full tool belt"
    return get_keyless_tools(), "keyless demo tools only (PARLAY_API_KEY is unset)"


def main() -> int:
    question = " ".join(sys.argv[1:]) or "What are tonight's NFL moneylines?"
    tools, mode = build_tools()
    print(f"[{mode}: {', '.join(t.name for t in tools)}]\n")

    try:
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        # No LLM configured. Still show that the tools work on their own.
        print("langchain-openai / langgraph not installed, calling a tool directly.\n")
        demo = next(t for t in tools if t.name == "parlayapi_demo_odds")
        print(demo.invoke({"sport_key": "americanfootball_nfl"})["summary"])
        return 0

    agent = create_react_agent(ChatOpenAI(model="gpt-4o-mini"), tools)
    result = agent.invoke({"messages": [("user", question)]})
    print(result["messages"][-1].content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
