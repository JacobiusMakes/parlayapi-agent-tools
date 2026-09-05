# parlayapi-agent-tools

[![ci](https://github.com/JacobiusMakes/parlayapi-agent-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/JacobiusMakes/parlayapi-agent-tools/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/JacobiusMakes/parlayapi-agent-tools/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Ready made [ParlayAPI](https://parlay-api.com) sports odds tools for LangChain, LlamaIndex, and
plain OpenAI or Anthropic function calling.

Live bookmaker odds across 30+ sportsbooks, cross book line comparison, and historical closing
lines, wrapped as agent tools with descriptions written for a model to read. Three of the six
tools need no API key at all, and two of those return real odds, so an agent can quote live
prices before anyone signs up for anything.

```python
from parlayapi_tools.langchain import get_parlayapi_tools

tools = get_parlayapi_tools()   # reads PARLAY_API_KEY from the environment
```

## Install

**Not on PyPI yet.** Install from source until it is published:

```bash
pip install "parlayapi-agent-tools[langchain] @ git+https://github.com/JacobiusMakes/parlayapi-agent-tools"
```

Swap `[langchain]` for `[llamaindex]`, or drop the extra entirely for the client and the raw JSON
schemas on their own.

Once it is published, the usual form works:

```bash
pip install parlayapi-agent-tools[langchain]     # LangChain adapter
pip install parlayapi-agent-tools[llamaindex]    # LlamaIndex adapter
pip install parlayapi-agent-tools                # client and raw JSON schemas only
```

The core client is standard library only. Framework imports are guarded, so having just one
framework installed is fine, and having none installed still gives you `ParlayAPIClient` and the
raw function calling schemas.

Want a running example before wiring anything yourself?
[parlayapi-betting-agent-starter](https://github.com/JacobiusMakes/parlayapi-betting-agent-starter)
installs this package, pulls live odds keyless, and prints no-vig fair lines with one command, or
one click in Colab or Codespaces.

## 60 second quickstart

### LangChain

```python
import os
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from parlayapi_tools.langchain import get_parlayapi_tools

os.environ["PARLAY_API_KEY"] = "your-key"      # https://parlay-api.com/signup

agent = create_react_agent(
    ChatOpenAI(model="gpt-4o-mini"),
    get_parlayapi_tools(),
)

result = agent.invoke({
    "messages": [("user", "Which book has the best price on the Chiefs this week?")]
})
print(result["messages"][-1].content)
```

### LlamaIndex

```python
import os
from llama_index.llms.openai import OpenAI
from llama_index.core.agent.workflow import FunctionAgent
from parlayapi_tools.llamaindex import get_parlayapi_tools

os.environ["PARLAY_API_KEY"] = "your-key"

agent = FunctionAgent(
    tools=get_parlayapi_tools(),
    llm=OpenAI(model="gpt-4o-mini"),
)

print(await agent.run("What are tonight's NHL moneylines, and where is the best price?"))
```

### OpenAI function calling, no framework

```python
from openai import OpenAI
from parlayapi_tools.openai_schemas import OPENAI_TOOLS, dispatch

client = OpenAI()
messages = [{"role": "user", "content": "What are the NFL odds this weekend?"}]

response = client.chat.completions.create(
    model="gpt-4o-mini", messages=messages, tools=OPENAI_TOOLS
)

for call in response.choices[0].message.tool_calls or []:
    import json
    result = dispatch(call.function.name, json.loads(call.function.arguments))
    # append the result as a tool message and call the model again
```

### Anthropic tool use, no framework

```python
import anthropic
from parlayapi_tools.openai_schemas import ANTHROPIC_TOOLS, dispatch

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=4096,
    tools=ANTHROPIC_TOOLS,
    messages=[{"role": "user", "content": "Best moneyline price on the Yankees tonight?"}],
)

for block in response.content:
    if block.type == "tool_use":
        result = dispatch(block.name, block.input)
```

`dispatch()` returns plain JSON serialisable dicts, including for failures, so a tool error never
takes the agent loop down with it.

## Keyless demo, nothing to sign up for

Three tools need no API key: `parlayapi_list_sports` plus the two demo tools below. Use the demo
tools in examples, in READMEs, and as a fallback when a user has not configured a key yet.

```python
from parlayapi_tools import ParlayAPIClient, format_events_for_llm

demo = ParlayAPIClient().demo_odds("americanfootball_nfl")
print(demo.demo_remaining_hour, "demo requests left this hour")
print(format_events_for_llm(demo.events, "h2h"))
```

```
41 demo requests left this hour
New England Patriots at Seattle Seahawks (starts 2026-09-10T00:15:00Z)
  FanDuel: Seattle Seahawks -196, New England Patriots 164
  Pinnacle: Seattle Seahawks -191, New England Patriots 166
  ...
```

The keyless demo is capped by the API at moneyline only, the first 5 games, and 60 requests per
hour per IP, across these six sports: `americanfootball_nfl`, `baseball_mlb`, `basketball_nba`,
`icehockey_nhl`, `soccer_epl`, `mma_mixed_martial_arts`.

## The tools

| Tool | Key needed | Credits | Endpoint |
| --- | --- | --- | --- |
| `parlayapi_list_sports` | no | free | `GET /v1/sports` |
| `parlayapi_get_odds` | yes | markets x regions | `GET /v1/sports/{sport_key}/odds` |
| `parlayapi_get_best_line` | yes | 5 | `GET /v1/sports/{sport_key}/best-line` |
| `parlayapi_get_historical_closing_odds` | yes | 10 | `GET /v1/historical/sports/{sport_key}/closing-odds` |
| `parlayapi_demo_odds` | no | free | `GET /v1/try/{sport_key}/odds` |
| `parlayapi_demo_positive_ev` | no | free | `GET /v1/try/{sport_key}/ev` |

Every path, query parameter and credit cost above was read from
[parlay-api.com/openapi.json](https://parlay-api.com/openapi.json) and
`/v1/meta/credit-costs` on 2026-09-01. A trimmed copy of that document ships in
`tests/fixtures/openapi_subset.json`, and the test suite fails if this client ever sends a
parameter it does not list.

## Getting a key

Free tier: 1,000 credits per month, no card. [parlay-api.com/signup](https://parlay-api.com/signup)

Set it as `PARLAY_API_KEY`, or pass `api_key=` to `get_parlayapi_tools()` or `ParlayAPIClient()`.
It travels in the `X-API-Key` header and is never put in a query string.

Tier allowances and prices: [parlay-api.com/pricing](https://parlay-api.com/pricing).

## Already using MCP?

If your agent speaks Model Context Protocol, you may not need this package at all. ParlayAPI has a
hosted MCP endpoint, so there is nothing to install:

```
POST https://parlay-api.com/mcp/http
```

Details and client configuration: [parlay-api.com/mcp](https://parlay-api.com/mcp). There is also a
`parlayapi-mcp` package on PyPI for a local stdio server.

Use this package instead when you want the tools inside your own agent framework, want to select or
rename the tool belt, or want to post process results before they reach the model.

## Honest limits

**Not every endpoint is wrapped.** The API has around 200 paths: arbitrage, middles, player props,
injuries, live SSE feeds, parlay pricing, CLV and more. This package deliberately wraps six, the
ones that answer the majority of "what are the odds" questions without bloating an agent's tool
belt. Anything not wrapped is one `ParlayAPIClient._request` call away, or use the MCP route.

**Historical depth depends on your tier.** The historical window on the free tier is 48 hours. Paid
tiers widen it substantially. A tool call outside your window comes back as an error with an
`upgrade_url`, not as an empty result, and the tool surfaces that field rather than swallowing it.

**Response shapes.** The demo endpoints and `GET /v1/sports` are modelled as typed dataclasses, and
those models are tested against real captured responses. `best_line` and
`historical_closing_odds` return the decoded JSON exactly as the API sends it, because their
response bodies could not be verified against a live authenticated call while this package was
written. Anything the API sends that is not modelled is preserved on `.raw`, so nothing is dropped.

**Untested paths.** The keyless endpoints are covered by a live end to end smoke test. The three
key requiring endpoints have their request construction tested against the OpenAPI document and
their error handling tested against real captured error bodies, but no live authenticated call was
made. See `tests/` for exactly what runs.

**Rate limits.** The keyless demo is 60 requests per hour per IP. If your agent may loop, keep the
demo tools out of the belt once a real key is configured.

**This is data, not advice.** The positive EV tool reports an edge computed against one sharp
reference book. That is an estimate, not a guarantee, and nothing this package returns is betting
advice.

## Running the tests

```bash
pip install -e ".[dev,langchain,llamaindex]"
pytest                                # unit tests, no network
PARLAYAPI_LIVE_TESTS=1 pytest -m network   # keyless live smoke test
ruff check .
```

Every fixture under `tests/fixtures/` is a real response captured from the live API on 2026-09-01.
None of it is hand written.

## License

MIT. See [LICENSE](LICENSE).

---

Part of the [ParlayAPI](https://parlay-api.com) ecosystem: a real-time sports odds API with a free tier of 1,000 credits per month, no card required. Explore all the tools at [github.com/JacobiusMakes](https://github.com/JacobiusMakes).
