"""Raw function calling schemas for OpenAI and Anthropic tool use.

No framework needed. Copy ``OPENAI_TOOLS`` into the ``tools=`` argument of
an OpenAI chat completion, or ``ANTHROPIC_TOOLS`` into the ``tools=``
argument of an Anthropic messages call, then route the model's tool calls
through ``dispatch()``.

This module is the single source of truth for tool names, descriptions and
argument schemas. The LangChain and LlamaIndex adapters read from here, so
the three surfaces cannot drift apart.

The descriptions are written for a model, not for a human reader. Each one
says what the tool returns, when to reach for it, what it costs in credits,
and which mistake to avoid.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any

from .core import (
    DEMO_SPORTS,
    ParlayAPIClient,
    ParlayAPIError,
    format_events_for_llm,
)

__all__ = [
    "ANTHROPIC_TOOLS",
    "OPENAI_TOOLS",
    "TOOL_SPECS",
    "ToolSpec",
    "dispatch",
    "get_handler",
]

_DEMO_LIST = ", ".join(DEMO_SPORTS)

_SPORT_KEY_DESC = (
    "Sport key exactly as GET /v1/sports returns it, for example "
    "americanfootball_nfl, basketball_nba, baseball_mlb, icehockey_nhl, "
    "soccer_epl. Call parlayapi_list_sports first if you are not certain; "
    "an invented key returns an error, not a guess."
)


class ToolSpec:
    """One tool: name, model facing description, JSON Schema, handler."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Mapping[str, Any],
        handler_name: str,
    ) -> None:
        self.name = name
        self.description = description.strip()
        self.parameters = dict(parameters)
        self.handler_name = handler_name

    def openai(self) -> dict[str, Any]:
        """Schema in OpenAI chat completions ``tools`` form."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def anthropic(self) -> dict[str, Any]:
        """Schema in Anthropic messages ``tools`` form."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
#
# Each handler takes a client plus the model's arguments and returns a
# JSON serialisable result. Errors are returned as a dict rather than
# raised, because a model recovers better from a readable failure than
# from a stack trace, and our API puts the fix in the error body.


def _error_result(exc: ParlayAPIError) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": str(exc)}
    for name in (
        "error_code",
        "status",
        "signup_url",
        "upgrade_url",
        "pricing_url",
        "credits_reset_at",
        "request_id",
    ):
        value = getattr(exc, name, None)
        if value:
            out[name] = value
    if exc.available_demo_sports:
        out["available_demo_sports"] = exc.available_demo_sports
    return out


def _guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Turn a raised ParlayAPIError into a result dict the model can read."""

    @functools.wraps(fn)
    def wrapped(client: ParlayAPIClient, **kwargs: Any) -> Any:
        try:
            return fn(client, **kwargs)
        except ParlayAPIError as exc:
            return _error_result(exc)

    return wrapped


@_guard
def _h_list_sports(
    client: ParlayAPIClient,
    group: str | None = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    sports = client.list_sports(include_inactive=include_inactive)
    if group:
        needle = group.strip().lower()
        sports = [s for s in sports if needle in s.group.lower()]
    return {
        "ok": True,
        "count": len(sports),
        "sports": [
            {"key": s.key, "title": s.title, "group": s.group, "active": s.active}
            for s in sports
        ],
    }


@_guard
def _h_get_odds(
    client: ParlayAPIClient,
    sport_key: str,
    regions: str = "us",
    markets: str = "h2h",
    odds_format: str = "american",
    bookmakers: str | None = None,
    date: str | None = None,
    include_live: bool = False,
    as_text: bool = True,
) -> dict[str, Any]:
    events = client.get_odds(
        sport_key,
        regions=regions,
        markets=markets,
        odds_format=odds_format,
        bookmakers=bookmakers,
        date=date,
        include_live=include_live,
    )
    first_market = markets.split(",")[0].strip() or "h2h"
    result: dict[str, Any] = {
        "ok": True,
        "sport_key": sport_key,
        "events_returned": len(events),
        "odds_format": odds_format,
    }
    if as_text:
        result["summary"] = format_events_for_llm(events, first_market)
    else:
        result["events"] = [dict(e.raw) for e in events]
    return result


@_guard
def _h_best_line(
    client: ParlayAPIClient,
    sport_key: str,
    markets: str = "h2h",
    odds_format: str = "american",
    bookmakers: str | None = None,
) -> dict[str, Any]:
    payload = client.best_line(
        sport_key,
        markets=markets,
        odds_format=odds_format,
        bookmakers=bookmakers,
    )
    return {"ok": True, "sport_key": sport_key, "result": payload}


@_guard
def _h_closing_odds(
    client: ParlayAPIClient,
    sport_key: str,
    markets: str = "h2h",
    bookmakers: str | None = None,
    season: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    player: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    payload = client.historical_closing_odds(
        sport_key,
        markets=markets,
        bookmakers=bookmakers,
        season=season,
        date=date,
        date_from=date_from,
        date_to=date_to,
        player=player,
        limit=limit,
    )
    return {"ok": True, "sport_key": sport_key, "result": payload}


@_guard
def _h_demo_odds(
    client: ParlayAPIClient,
    sport_key: str = "americanfootball_nfl",
    as_text: bool = True,
) -> dict[str, Any]:
    demo = client.demo_odds(sport_key)
    result: dict[str, Any] = {
        "ok": True,
        "demo": True,
        "sport_key": demo.sport_key,
        "events_returned": demo.events_returned,
        "requests_left_this_hour": demo.demo_remaining_hour,
        "note": demo.demo_message,
    }
    if as_text:
        result["summary"] = format_events_for_llm(demo.events, "h2h")
    else:
        result["events"] = [dict(e.raw) for e in demo.events]
    return result


@_guard
def _h_demo_positive_ev(
    client: ParlayAPIClient,
    sport_key: str = "americanfootball_nfl",
) -> dict[str, Any]:
    demo = client.demo_positive_ev(sport_key)
    return {
        "ok": True,
        "demo": True,
        "sport_key": demo.sport_key,
        "sharp_anchor": demo.sharp_anchor,
        "method": demo.method,
        "requests_left_this_hour": demo.demo_remaining_hour,
        "opportunities": [dict(o.raw) for o in demo.opportunities],
        "note": demo.demo_message,
    }


_HANDLERS: dict[str, Callable[..., Any]] = {
    "list_sports": _h_list_sports,
    "get_odds": _h_get_odds,
    "best_line": _h_best_line,
    "closing_odds": _h_closing_odds,
    "demo_odds": _h_demo_odds,
    "demo_positive_ev": _h_demo_positive_ev,
}


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="parlayapi_list_sports",
        description="""
List every sport key ParlayAPI serves, with its human title and group
(Baseball, American Football, Soccer, and so on). Call this FIRST whenever
you are unsure which sport key another ParlayAPI tool wants: every other
tool takes a key from this list, and a made up key fails rather than being
guessed at. Covers 90+ sport keys including the major US leagues, the
soccer catalog, MMA, boxing, cricket and esports. Free: no API key and no
credits are needed for this call.
""",
        parameters={
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "description": (
                        "Optional case insensitive filter on the group name, for "
                        "example 'soccer', 'baseball', 'american football'. Applied "
                        "locally after the list is fetched."
                    ),
                },
                "include_inactive": {
                    "type": "boolean",
                    "description": (
                        "Include sports that are out of season or otherwise not "
                        "currently served. Default false."
                    ),
                    "default": False,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
        handler_name="list_sports",
    ),
    ToolSpec(
        name="parlayapi_get_odds",
        description="""
Get current bookmaker odds for upcoming games in one sport, across 30+
sportsbooks. This is the workhorse tool: use it for "what are the odds on
X", "who is favored", "what line is book Y offering", and for any question
that needs live prices.

Returns one entry per game with each book's prices for the markets you
asked for. Markets: h2h (moneyline), spreads, totals. Regions: us, us2, uk,
eu, au, ca and others; use eu to include Pinnacle and European books.

Costs credits: number of markets multiplied by number of regions, so
markets='h2h' with regions='us' is the cheapest call and
markets='h2h,spreads,totals' with regions='us,eu' costs six times as much.
Ask for only what the question needs.

Requires an API key in the PARLAY_API_KEY environment variable. If the call
reports a missing or invalid key, tell the user a free key with 1,000
credits per month and no card is at https://parlay-api.com/signup rather
than retrying.

Pregame only by default. Set include_live true to also get games already in
progress.
""",
        parameters={
            "type": "object",
            "properties": {
                "sport_key": {"type": "string", "description": _SPORT_KEY_DESC},
                "regions": {
                    "type": "string",
                    "description": (
                        "Comma separated bookmaker regions: us, us2, uk, eu, au, ca, "
                        "fr, mx, latam, br, asia. Default 'us'. Each extra region "
                        "multiplies the credit cost."
                    ),
                    "default": "us",
                },
                "markets": {
                    "type": "string",
                    "description": (
                        "Comma separated markets: h2h (moneyline), spreads, totals. "
                        "Default 'h2h'. Each extra market multiplies the credit cost."
                    ),
                    "default": "h2h",
                },
                "odds_format": {
                    "type": "string",
                    "enum": ["american", "decimal"],
                    "description": (
                        "Price format. 'american' gives -150 / +130 style prices, "
                        "'decimal' gives 1.67 / 2.30. Pick one and do not compare "
                        "prices across formats."
                    ),
                    "default": "american",
                },
                "bookmakers": {
                    "type": "string",
                    "description": (
                        "Optional comma separated bookmaker keys, for example "
                        "'pinnacle,draftkings'. Overrides regions when set."
                    ),
                },
                "date": {
                    "type": "string",
                    "description": (
                        "Optional UTC date YYYY-MM-DD. Limits results to games "
                        "starting on that date."
                    ),
                },
                "include_live": {
                    "type": "boolean",
                    "description": "Also include games already in progress. Default false.",
                    "default": False,
                },
            },
            "required": ["sport_key"],
            "additionalProperties": False,
        },
        handler_name="get_odds",
    ),
    ToolSpec(
        name="parlayapi_get_best_line",
        description="""
Compare one sport's prices across every available bookmaker and get the
best price per outcome, plus the hold percentage each book is charging.
Use this for "where should I bet this", "who has the best price on X", and
for line shopping questions, instead of fetching raw odds and sorting them
yourself.

Costs 5 credits per call regardless of how many games come back, so it is
cheaper than a wide multi market odds call when the question is purely
"which book is best".

Requires an API key. Returns the API response as sent.
""",
        parameters={
            "type": "object",
            "properties": {
                "sport_key": {"type": "string", "description": _SPORT_KEY_DESC},
                "markets": {
                    "type": "string",
                    "description": (
                        "Comma separated markets: h2h, spreads, totals. Default 'h2h'."
                    ),
                    "default": "h2h",
                },
                "odds_format": {
                    "type": "string",
                    "enum": ["american", "decimal"],
                    "description": (
                        "Price format. 'american' gives -150 / +130 prices, 'decimal' "
                        "gives 1.67 / 2.30."
                    ),
                    "default": "american",
                },
                "bookmakers": {
                    "type": "string",
                    "description": (
                        "Optional comma separated bookmaker keys to restrict the "
                        "comparison to."
                    ),
                },
            },
            "required": ["sport_key"],
            "additionalProperties": False,
        },
        handler_name="best_line",
    ),
    ToolSpec(
        name="parlayapi_get_historical_closing_odds",
        description="""
Look up historical CLOSING lines: the final price a book showed before a
game started. Use this for closing line value work, backtests, and any
question about what a line was in the past. Do not use it for today's
prices; use parlayapi_get_odds for those.

Covers game lines (h2h, spreads, totals) and player props. For props pass a
player market key such as player_points, player_strikeouts, player_pass_yds
and optionally a player name to filter on.

Costs 10 credits per call and how far back you may read depends on the
account tier: the free tier's historical window is 48 hours, and the paid
tiers widen it substantially. If the call comes back saying the range is
not available on this tier, say so plainly and point at
https://parlay-api.com/pricing rather than retrying with a different date.

Requires an API key. Returns the API response as sent.
""",
        parameters={
            "type": "object",
            "properties": {
                "sport_key": {"type": "string", "description": _SPORT_KEY_DESC},
                "markets": {
                    "type": "string",
                    "description": (
                        "Comma separated. Game lines: h2h, spreads, totals. Player "
                        "props: player_points, player_rebounds, player_assists, "
                        "player_strikeouts, player_total_bases, player_pass_yds, "
                        "player_rush_yds, player_shots_on_goal and other player_* "
                        "keys. Default 'h2h'."
                    ),
                    "default": "h2h",
                },
                "bookmakers": {
                    "type": "string",
                    "description": (
                        "Optional comma separated book keys. Game line queries "
                        "default to pinnacle, which is the usual sharp reference."
                    ),
                },
                "season": {
                    "type": "string",
                    "description": "Optional season filter for game lines, for example '2023-24'.",
                },
                "date": {
                    "type": "string",
                    "description": "Single UTC date YYYY-MM-DD. Shortcut for date_from = date_to.",
                },
                "date_from": {"type": "string", "description": "Range start, YYYY-MM-DD."},
                "date_to": {"type": "string", "description": "Range end, YYYY-MM-DD."},
                "player": {
                    "type": "string",
                    "description": "Optional player name substring, used with a player_* market.",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Rows per page, 1 to 5000. Keep it small when summarising "
                        "for a person."
                    ),
                    "minimum": 1,
                    "maximum": 5000,
                },
            },
            "required": ["sport_key"],
            "additionalProperties": False,
        },
        handler_name="closing_odds",
    ),
    ToolSpec(
        name="parlayapi_demo_odds",
        description=f"""
Free keyless sample of live moneyline odds. Needs no API key at all, which
makes it the right tool when no key is configured and you still want to
show real data instead of apologising.

Deliberately limited by the API: moneyline only, the first 5 games only,
and 60 requests per hour per IP address. Sports supported: {_DEMO_LIST}.

When you use this, tell the user the result is a capped free sample and
that a full key with 1,000 credits per month and no card is at
https://parlay-api.com/signup.
""",
        parameters={
            "type": "object",
            "properties": {
                "sport_key": {
                    "type": "string",
                    "enum": list(DEMO_SPORTS),
                    "description": "One of the six sports the keyless demo covers.",
                    "default": "americanfootball_nfl",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        handler_name="demo_odds",
    ),
    ToolSpec(
        name="parlayapi_demo_positive_ev",
        description=f"""
Free keyless sample of positive expected value moneyline bets. Needs no API
key. The API devigs Pinnacle's two sided price into a no vig fair
probability, then reports every other book whose offered price implies a
lower probability than that fair number; the gap is the edge.

Deliberately limited by the API: moneyline only, top 5 opportunities by
edge, 60 requests per hour per IP. Sports supported: {_DEMO_LIST}.

An edge computed this way is an estimate against one sharp reference book,
not a guarantee. Present it as such, and never present any result from
these tools as betting advice.
""",
        parameters={
            "type": "object",
            "properties": {
                "sport_key": {
                    "type": "string",
                    "enum": list(DEMO_SPORTS),
                    "description": "One of the six sports the keyless demo covers.",
                    "default": "americanfootball_nfl",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        handler_name="demo_positive_ev",
    ),
)


OPENAI_TOOLS: list[dict[str, Any]] = [spec.openai() for spec in TOOL_SPECS]
ANTHROPIC_TOOLS: list[dict[str, Any]] = [spec.anthropic() for spec in TOOL_SPECS]

_SPEC_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def get_handler(tool_name: str) -> Callable[..., Any]:
    """Return the python callable behind a tool name."""
    spec = _SPEC_BY_NAME.get(tool_name)
    if spec is None:
        raise KeyError(f"Unknown ParlayAPI tool: {tool_name}")
    return _HANDLERS[spec.handler_name]


def dispatch(
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
    *,
    client: ParlayAPIClient | None = None,
) -> Any:
    """Run a tool call the model asked for.

    >>> dispatch("parlayapi_demo_odds", {"sport_key": "baseball_mlb"})

    Unknown tool names and bad arguments come back as an ``{"ok": False}``
    dict, so a model can read the problem and correct itself instead of the
    whole agent loop dying on an exception.
    """
    client = client or ParlayAPIClient()
    try:
        handler = get_handler(tool_name)
    except KeyError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "available_tools": list(_SPEC_BY_NAME),
        }
    try:
        return handler(client, **dict(arguments or {}))
    except TypeError as exc:
        spec = _SPEC_BY_NAME[tool_name]
        return {
            "ok": False,
            "error": f"Bad arguments for {tool_name}: {exc}",
            "expected_parameters": sorted(spec.parameters.get("properties", {})),
        }
