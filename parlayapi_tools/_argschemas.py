"""Pydantic argument schemas shared by the framework adapters.

These models need pydantic and nothing else. Both the LangChain and the
LlamaIndex adapters import them, so a model sees identical argument names,
types and per field help text whichever framework is driving.

Field descriptions are read by the model when it decides how to fill an
argument, so they carry the same weight as the tool description itself.
"""

from __future__ import annotations

try:  # pragma: no cover
    from pydantic import BaseModel, Field
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "parlayapi_tools argument schemas need pydantic. Install with:\n"
        "    pip install pydantic\n"
        "The stdlib only client in parlayapi_tools.core works without it."
    ) from _exc

__all__ = [
    "ARG_SCHEMAS",
    "BestLineArgs",
    "ClosingOddsArgs",
    "DemoSportArgs",
    "GetOddsArgs",
    "ListSportsArgs",
]


_SPORT_KEY_HELP = (
    "Sport key exactly as parlayapi_list_sports returns it, for example "
    "americanfootball_nfl, basketball_nba, baseball_mlb, icehockey_nhl or "
    "soccer_epl. Do not invent one."
)

_DEMO_SPORT_HELP = (
    "One of the six sports the keyless demo covers: americanfootball_nfl, "
    "baseball_mlb, basketball_nba, icehockey_nhl, soccer_epl, "
    "mma_mixed_martial_arts."
)


class ListSportsArgs(BaseModel):
    """Arguments for parlayapi_list_sports."""

    group: str | None = Field(
        default=None,
        description=(
            "Optional case insensitive group filter, for example 'soccer', "
            "'baseball', 'american football'."
        ),
    )
    include_inactive: bool = Field(
        default=False,
        description="Include sports that are out of season or not currently served.",
    )


class GetOddsArgs(BaseModel):
    """Arguments for parlayapi_get_odds."""

    sport_key: str = Field(description=_SPORT_KEY_HELP)
    regions: str = Field(
        default="us",
        description=(
            "Comma separated bookmaker regions: us, us2, uk, eu, au, ca, fr, mx, "
            "latam, br, asia. Use eu to include Pinnacle. Each extra region "
            "multiplies the credit cost."
        ),
    )
    markets: str = Field(
        default="h2h",
        description=(
            "Comma separated markets: h2h (moneyline), spreads, totals. Each "
            "extra market multiplies the credit cost, so ask for only what the "
            "question needs."
        ),
    )
    odds_format: str = Field(
        default="american",
        description="Either 'american' for -150 / +130 prices or 'decimal' for 1.67 / 2.30.",
    )
    bookmakers: str | None = Field(
        default=None,
        description=(
            "Optional comma separated book keys such as 'pinnacle,draftkings'. "
            "Overrides regions when set."
        ),
    )
    date: str | None = Field(
        default=None,
        description="Optional UTC date YYYY-MM-DD to limit results to one day's games.",
    )
    include_live: bool = Field(
        default=False,
        description="Also include games already in progress. Off by default.",
    )


class BestLineArgs(BaseModel):
    """Arguments for parlayapi_get_best_line."""

    sport_key: str = Field(description=_SPORT_KEY_HELP)
    markets: str = Field(
        default="h2h",
        description="Comma separated markets: h2h, spreads, totals.",
    )
    odds_format: str = Field(
        default="american",
        description="Either 'american' or 'decimal'.",
    )
    bookmakers: str | None = Field(
        default=None,
        description="Optional comma separated book keys to restrict the comparison to.",
    )


class ClosingOddsArgs(BaseModel):
    """Arguments for parlayapi_get_historical_closing_odds."""

    sport_key: str = Field(description=_SPORT_KEY_HELP)
    markets: str = Field(
        default="h2h",
        description=(
            "Comma separated. Game lines: h2h, spreads, totals. Player props: "
            "player_points, player_rebounds, player_assists, player_strikeouts, "
            "player_total_bases, player_pass_yds, player_rush_yds, "
            "player_shots_on_goal and other player_* keys."
        ),
    )
    bookmakers: str | None = Field(
        default=None,
        description=(
            "Optional comma separated book keys. Game line queries default to "
            "pinnacle, the usual sharp reference."
        ),
    )
    season: str | None = Field(
        default=None, description="Optional season filter for game lines, e.g. '2023-24'."
    )
    date: str | None = Field(
        default=None, description="Single UTC date YYYY-MM-DD."
    )
    date_from: str | None = Field(default=None, description="Range start, YYYY-MM-DD.")
    date_to: str | None = Field(default=None, description="Range end, YYYY-MM-DD.")
    player: str | None = Field(
        default=None,
        description="Optional player name substring, used together with a player_* market.",
    )
    limit: int | None = Field(
        default=None,
        description="Rows per page, 1 to 5000. Keep it small when summarising for a person.",
    )


class DemoSportArgs(BaseModel):
    """Arguments for the keyless demo tools."""

    sport_key: str = Field(
        default="americanfootball_nfl",
        description=_DEMO_SPORT_HELP,
    )


ARG_SCHEMAS: dict[str, type[BaseModel]] = {
    "parlayapi_list_sports": ListSportsArgs,
    "parlayapi_get_odds": GetOddsArgs,
    "parlayapi_get_best_line": BestLineArgs,
    "parlayapi_get_historical_closing_odds": ClosingOddsArgs,
    "parlayapi_demo_odds": DemoSportArgs,
    "parlayapi_demo_positive_ev": DemoSportArgs,
}
