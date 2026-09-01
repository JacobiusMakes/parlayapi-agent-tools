"""Thin typed client for the ParlayAPI sports odds API.

Standard library only. No third party dependency is required to use this
module, which keeps the tool layer installable next to any agent framework
without dragging an HTTP stack in behind it.

Every path and query parameter used here was checked against the live
https://parlay-api.com/openapi.json before it was written. Anything that
could not be found there is not in this file.

Auth: set PARLAY_API_KEY in the environment, or pass api_key=... The key
travels in the X-API-Key header, which is the scheme the OpenAPI document
marks as recommended.

Free key, 1,000 credits per month, no card: https://parlay-api.com/signup
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

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

#: Kept in step with pyproject.toml by tests/test_packaging.py.
__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://parlay-api.com"

#: Sport keys the keyless demo endpoints accept. Source: the 400 body the
#: live API returns for an unsupported demo sport, read 2026-09-01.
DEMO_SPORTS: tuple[str, ...] = (
    "americanfootball_nfl",
    "baseball_mlb",
    "basketball_nba",
    "icehockey_nhl",
    "mma_mixed_martial_arts",
    "soccer_epl",
)

SIGNUP_URL = "https://parlay-api.com/signup"
PRICING_URL = "https://parlay-api.com/pricing"
MCP_URL = "https://parlay-api.com/mcp"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ParlayAPIError(RuntimeError):
    """An error the ParlayAPI returned, with its self service fields intact.

    The API answers a refusal with the next step as a *field*, not only as
    prose, so an agent can act on it. This exception keeps those fields
    rather than flattening everything into a string:

    * ``signup_url``       set on MISSING_KEY / INVALID_KEY
    * ``upgrade_url``      set on OUT_OF_USAGE_CREDITS / CREDIT_LIMIT_REACHED
      and on the free tier frequency cap
    * ``pricing_url``      set alongside ``upgrade_url``
    * ``credits_reset_at`` ISO timestamp when the credit allowance rolls over
    * ``request_id``       quote this when contacting support
    * ``available_demo_sports`` set when a demo call names a sport the demo
      does not cover

    Two live error bodies were captured while writing this module: the 401
    MISSING_KEY body wraps its fields under a ``detail`` key, and the demo
    400 body puts them at the top level. Both shapes are parsed.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        error_code: str | None = None,
        signup_url: str | None = None,
        upgrade_url: str | None = None,
        pricing_url: str | None = None,
        credits_reset_at: str | None = None,
        request_id: str | None = None,
        docs_url: str | None = None,
        available_demo_sports: Sequence[str] | None = None,
        instructions_for_agent: str | None = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.error_code = error_code
        self.signup_url = signup_url
        self.upgrade_url = upgrade_url
        self.pricing_url = pricing_url
        self.credits_reset_at = credits_reset_at
        self.request_id = request_id
        self.docs_url = docs_url
        self.available_demo_sports = list(available_demo_sports or [])
        self.instructions_for_agent = instructions_for_agent
        self.raw = raw

    # The string form is what an LLM sees when a tool call fails, so it has
    # to carry the fix, not just the complaint.
    def __str__(self) -> str:
        parts = [self.message]
        if self.signup_url:
            parts.append(f"Get a free key (1,000 credits/month, no card): {self.signup_url}")
        if self.upgrade_url:
            parts.append(f"Raise the limit: {self.upgrade_url}")
        if self.credits_reset_at:
            parts.append(f"Credits reset at {self.credits_reset_at}.")
        if self.available_demo_sports:
            parts.append("Demo sports: " + ", ".join(self.available_demo_sports) + ".")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " ".join(parts)

    @classmethod
    def from_payload(cls, payload: Any, status: int | None = None) -> ParlayAPIError:
        """Build an error from a decoded JSON body of either known shape."""
        body: Mapping[str, Any]
        if isinstance(payload, Mapping) and isinstance(payload.get("detail"), Mapping):
            body = payload["detail"]
        elif isinstance(payload, Mapping):
            body = payload
        else:
            body = {}

        message = body.get("message") or body.get("detail") or body.get("error")
        if not isinstance(message, str) or not message:
            message = f"ParlayAPI request failed with HTTP {status}."

        return cls(
            message,
            status=body.get("status") if isinstance(body.get("status"), int) else status,
            error_code=_as_str(body.get("error")),
            signup_url=_as_str(body.get("signup_url")),
            upgrade_url=_as_str(body.get("upgrade_url")),
            pricing_url=_as_str(body.get("pricing_url")),
            credits_reset_at=_as_str(body.get("credits_reset_at")),
            request_id=_as_str(body.get("request_id")),
            docs_url=_as_str(body.get("docs_url")),
            available_demo_sports=body.get("available_demo_sports")
            if isinstance(body.get("available_demo_sports"), list)
            else None,
            instructions_for_agent=_as_str(body.get("instructions_for_agent")),
            raw=payload,
        )


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


# ---------------------------------------------------------------------------
# Typed views over the JSON
# ---------------------------------------------------------------------------
#
# Every modelled field below was observed in a real response captured from
# the live API on 2026-09-01 (see tests/fixtures/). Anything the API sends
# that is not modelled is preserved verbatim on ``.raw``, so upgrading the
# API never silently drops data on the floor.


@dataclass(frozen=True)
class Sport:
    """One row of GET /v1/sports."""

    key: str
    title: str = ""
    group: str = ""
    description: str = ""
    active: bool = True
    has_outrights: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Sport:
        return cls(
            key=str(d.get("key", "")),
            title=str(d.get("title", "") or ""),
            group=str(d.get("group", "") or ""),
            description=str(d.get("description", "") or ""),
            active=bool(d.get("active", True)),
            has_outrights=bool(d.get("has_outrights", False)),
            raw=d,
        )


@dataclass(frozen=True)
class Outcome:
    """One priced side of a market."""

    name: str
    price: float | None = None
    point: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Outcome:
        return cls(
            name=str(d.get("name", "") or ""),
            price=_as_number(d.get("price")),
            point=_as_number(d.get("point")),
            raw=d,
        )


@dataclass(frozen=True)
class Market:
    """A market at one bookmaker, e.g. h2h, spreads, totals."""

    key: str
    last_update: str | None = None
    outcomes: tuple[Outcome, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Market:
        return cls(
            key=str(d.get("key", "") or ""),
            last_update=_as_str(d.get("last_update")),
            outcomes=tuple(
                Outcome.from_dict(o) for o in _as_dict_list(d.get("outcomes"))
            ),
            raw=d,
        )


@dataclass(frozen=True)
class Bookmaker:
    """One book's prices on one event."""

    key: str
    title: str = ""
    last_update: str | None = None
    markets: tuple[Market, ...] = ()
    stale_seconds: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Bookmaker:
        return cls(
            key=str(d.get("key", "") or ""),
            title=str(d.get("title", "") or ""),
            last_update=_as_str(d.get("last_update")),
            markets=tuple(Market.from_dict(m) for m in _as_dict_list(d.get("markets"))),
            stale_seconds=_as_number(d.get("stale_seconds")),
            raw=d,
        )

    def market(self, key: str) -> Market | None:
        for m in self.markets:
            if m.key == key:
                return m
        return None


@dataclass(frozen=True)
class Event:
    """One game or match with its bookmaker prices attached."""

    id: str
    sport_key: str = ""
    sport_title: str = ""
    commence_time: str | None = None
    home_team: str = ""
    away_team: str = ""
    bookmakers: tuple[Bookmaker, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Event:
        return cls(
            id=str(d.get("id", "") or ""),
            sport_key=str(d.get("sport_key", "") or ""),
            sport_title=str(d.get("sport_title", "") or ""),
            commence_time=_as_str(d.get("commence_time")),
            home_team=str(d.get("home_team", "") or ""),
            away_team=str(d.get("away_team", "") or ""),
            bookmakers=tuple(
                Bookmaker.from_dict(b) for b in _as_dict_list(d.get("bookmakers"))
            ),
            raw=d,
        )

    @property
    def matchup(self) -> str:
        if self.away_team and self.home_team:
            return f"{self.away_team} at {self.home_team}"
        return self.id

    def best_price(self, market_key: str, outcome_name: str) -> tuple[str, float] | None:
        """Highest posted price for one side, as (bookmaker_key, price).

        Prices are compared as sent. Ask the API for one odds format and
        stay in it: mixing American and decimal in one comparison is wrong.
        """
        best: tuple[str, float] | None = None
        for book in self.bookmakers:
            market = book.market(market_key)
            if market is None:
                continue
            for outcome in market.outcomes:
                if outcome.name != outcome_name or outcome.price is None:
                    continue
                if best is None or outcome.price > best[1]:
                    best = (book.key, outcome.price)
        return best


@dataclass(frozen=True)
class DemoOdds:
    """The envelope GET /v1/try/{sport_key}/odds returns.

    The events live under the ``events`` key. They are NOT at the top level,
    which is the single most common mistake when wiring the demo up.
    """

    sport_key: str
    events: tuple[Event, ...]
    events_returned: int = 0
    demo: bool = True
    demo_message: str = ""
    demo_signup_url: str = SIGNUP_URL
    demo_remaining_hour: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DemoOdds:
        events = tuple(Event.from_dict(e) for e in _as_dict_list(d.get("events")))
        returned = d.get("events_returned")
        return cls(
            sport_key=str(d.get("sport_key", "") or ""),
            events=events,
            events_returned=returned if isinstance(returned, int) else len(events),
            demo=bool(d.get("demo", True)),
            demo_message=str(d.get("demo_message", "") or ""),
            demo_signup_url=str(d.get("demo_signup_url") or SIGNUP_URL),
            demo_remaining_hour=d.get("demo_remaining_hour")
            if isinstance(d.get("demo_remaining_hour"), int)
            else None,
            raw=d,
        )


@dataclass(frozen=True)
class EVOpportunity:
    """One row of the keyless positive EV demo."""

    home_team: str = ""
    away_team: str = ""
    side: str = ""
    book: str = ""
    price: float | None = None
    edge_pct: float | None = None
    fair_prob_pct: float | None = None
    book_implied_pct: float | None = None
    commence_time: str | None = None
    sharp_anchor: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> EVOpportunity:
        return cls(
            home_team=str(d.get("home_team", "") or ""),
            away_team=str(d.get("away_team", "") or ""),
            side=str(d.get("side", "") or ""),
            book=str(d.get("book", "") or ""),
            price=_as_number(d.get("price")),
            edge_pct=_as_number(d.get("edge_pct")),
            fair_prob_pct=_as_number(d.get("fair_prob_pct")),
            book_implied_pct=_as_number(d.get("book_implied_pct")),
            commence_time=_as_str(d.get("commence_time")),
            sharp_anchor=_as_str(d.get("sharp_anchor")),
            raw=d,
        )


@dataclass(frozen=True)
class DemoPositiveEV:
    """The envelope GET /v1/try/{sport_key}/ev returns."""

    sport_key: str
    opportunities: tuple[EVOpportunity, ...]
    opportunities_returned: int = 0
    sharp_anchor: str | None = None
    method: str | None = None
    demo_message: str = ""
    demo_remaining_hour: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DemoPositiveEV:
        opps = tuple(
            EVOpportunity.from_dict(o) for o in _as_dict_list(d.get("opportunities"))
        )
        returned = d.get("opportunities_returned")
        return cls(
            sport_key=str(d.get("sport_key", "") or ""),
            opportunities=opps,
            opportunities_returned=returned if isinstance(returned, int) else len(opps),
            sharp_anchor=_as_str(d.get("sharp_anchor")),
            method=_as_str(d.get("method")),
            demo_message=str(d.get("demo_message", "") or ""),
            demo_remaining_hour=d.get("demo_remaining_hour")
            if isinstance(d.get("demo_remaining_hour"), int)
            else None,
            raw=d,
        )


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_dict_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def events_from_payload(payload: Any) -> tuple[Event, ...]:
    """Pull events out of an odds payload of either observed shape.

    The keyless demo wraps its events in ``{"events": [...]}``. The keyed
    odds endpoint is the-odds-api compatible and is documented to answer
    with a bare list. This accepts both rather than guessing, so a shape
    difference between tiers cannot turn into a silent empty result.
    """
    if isinstance(payload, list):
        return tuple(Event.from_dict(e) for e in _as_dict_list(payload))
    if isinstance(payload, Mapping):
        for key in ("events", "data", "results"):
            if isinstance(payload.get(key), list):
                return tuple(Event.from_dict(e) for e in _as_dict_list(payload[key]))
    return ()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ParlayAPIClient:
    """Minimal client over the ParlayAPI REST endpoints.

    >>> client = ParlayAPIClient()               # reads PARLAY_API_KEY
    >>> sports = client.list_sports()            # free, no key needed
    >>> demo = client.demo_odds("americanfootball_nfl")   # no key needed

    Only endpoints that exist in https://parlay-api.com/openapi.json are
    wrapped. Endpoints are called exactly as that document spells them,
    camelCase query parameters included.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        user_agent: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("PARLAY_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent or f"parlayapi-agent-tools/{__version__}"

    # -- plumbing ----------------------------------------------------------

    def _request(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        needs_key: bool,
    ) -> Any:
        if needs_key and not self.api_key:
            raise ParlayAPIError(
                "No ParlayAPI key configured. Set the PARLAY_API_KEY environment "
                "variable or pass api_key= to ParlayAPIClient.",
                status=None,
                error_code="MISSING_KEY_LOCAL",
                signup_url=SIGNUP_URL,
            )

        query = _clean_params(params)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:  # 4xx and 5xx
            raw = exc.read()
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                raise ParlayAPIError(
                    f"ParlayAPI returned HTTP {exc.code} with a non JSON body.",
                    status=exc.code,
                    raw=raw[:500].decode("utf-8", "replace"),
                ) from exc
            raise ParlayAPIError.from_payload(payload, status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise ParlayAPIError(
                f"Could not reach {self.base_url}: {exc.reason}",
                error_code="NETWORK_ERROR",
            ) from exc

        try:
            return json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ParlayAPIError(
                "ParlayAPI returned a body that is not valid JSON.",
                raw=body[:500].decode("utf-8", "replace"),
            ) from exc

    # -- free, no key ------------------------------------------------------

    def list_sports(self, include_inactive: bool = False) -> list[Sport]:
        """GET /v1/sports. Free, no credits, no key required.

        ``include_inactive`` maps to the documented ``all`` query parameter.
        """
        payload = self._request(
            "/v1/sports",
            {"all": "true" if include_inactive else None},
            needs_key=False,
        )
        rows = payload if isinstance(payload, list) else payload.get("sports", [])
        return [Sport.from_dict(row) for row in _as_dict_list(rows)]

    def demo_odds(self, sport_key: str) -> DemoOdds:
        """GET /v1/try/{sport_key}/odds. Keyless demo, moneyline only.

        Capped by the API at 60 requests per hour per IP and the first
        5 events. Sport must be one of DEMO_SPORTS.
        """
        payload = self._request(f"/v1/try/{_seg(sport_key)}/odds", needs_key=False)
        if not isinstance(payload, Mapping):
            raise ParlayAPIError(
                "Unexpected demo odds payload: expected a JSON object with an "
                "'events' key.",
                raw=payload,
            )
        return DemoOdds.from_dict(payload)

    def demo_positive_ev(self, sport_key: str) -> DemoPositiveEV:
        """GET /v1/try/{sport_key}/ev. Keyless positive EV demo.

        Capped by the API at 60 requests per hour per IP and the top
        5 opportunities by edge percent.
        """
        payload = self._request(f"/v1/try/{_seg(sport_key)}/ev", needs_key=False)
        if not isinstance(payload, Mapping):
            raise ParlayAPIError(
                "Unexpected demo EV payload: expected a JSON object with an "
                "'opportunities' key.",
                raw=payload,
            )
        return DemoPositiveEV.from_dict(payload)

    # -- key required ------------------------------------------------------

    def get_odds(
        self,
        sport_key: str,
        *,
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "american",
        bookmakers: str | None = None,
        event_ids: str | None = None,
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
        date: str | None = None,
        include_live: bool = False,
    ) -> list[Event]:
        """GET /v1/sports/{sport_key}/odds. Key required.

        Credits: markets count multiplied by regions count.
        """
        payload = self.get_odds_raw(
            sport_key,
            regions=regions,
            markets=markets,
            odds_format=odds_format,
            bookmakers=bookmakers,
            event_ids=event_ids,
            commence_time_from=commence_time_from,
            commence_time_to=commence_time_to,
            date=date,
            include_live=include_live,
        )
        return list(events_from_payload(payload))

    def get_odds_raw(
        self,
        sport_key: str,
        *,
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "american",
        bookmakers: str | None = None,
        event_ids: str | None = None,
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
        date: str | None = None,
        include_live: bool = False,
    ) -> Any:
        """Same call as get_odds, returning the decoded JSON untouched."""
        return self._request(
            f"/v1/sports/{_seg(sport_key)}/odds",
            {
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
                "bookmakers": bookmakers,
                "eventIds": event_ids,
                "commenceTimeFrom": commence_time_from,
                "commenceTimeTo": commence_time_to,
                "date": date,
                "include_live": "true" if include_live else None,
            },
            needs_key=True,
        )

    def best_line(
        self,
        sport_key: str,
        *,
        markets: str = "h2h",
        odds_format: str = "american",
        bookmakers: str | None = None,
    ) -> Any:
        """GET /v1/sports/{sport_key}/best-line. Key required. 5 credits.

        The OpenAPI document describes this as an alias of
        /v1/sports/{sport_key}/compare with the same response shape: every
        event with each book's prices side by side, plus the best price and
        the hold percentage per outcome.

        Returns the decoded JSON as sent. The response body is not modelled
        here because it could not be verified against a live authenticated
        call while this package was written.
        """
        return self._request(
            f"/v1/sports/{_seg(sport_key)}/best-line",
            {
                "markets": markets,
                "oddsFormat": odds_format,
                "bookmakers": bookmakers,
            },
            needs_key=True,
        )

    def historical_closing_odds(
        self,
        sport_key: str,
        *,
        markets: str = "h2h",
        bookmakers: str | None = None,
        season: str | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        player: str | None = None,
        odds_format: str = "american",
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        """GET /v1/historical/sports/{sport_key}/closing-odds. Key required.

        10 credits per call. Availability depends on tier. Returns the
        decoded JSON as sent, for the same reason as best_line.
        """
        return self._request(
            f"/v1/historical/sports/{_seg(sport_key)}/closing-odds",
            {
                "markets": markets,
                "bookmakers": bookmakers,
                "season": season,
                "date": date,
                "dateFrom": date_from,
                "dateTo": date_to,
                "player": player,
                "oddsFormat": odds_format,
                "limit": limit,
                "offset": offset,
            },
            needs_key=True,
        )

    def account(self, by_endpoint: bool = False) -> Any:
        """GET /v1/account. Key required. Credits used and remaining."""
        return self._request(
            "/v1/account",
            {"by_endpoint": "true" if by_endpoint else None},
            needs_key=True,
        )


def _seg(value: str) -> str:
    """Quote one path segment so a sport key cannot escape the path."""
    return urllib.parse.quote(str(value).strip(), safe="")


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    return {k: v for k, v in params.items() if v is not None and v != ""}


def format_events_for_llm(events: Iterable[Event], market_key: str = "h2h") -> str:
    """Render events as compact text a language model can read cheaply.

    Full odds JSON is large and repetitive. When a tool result is going
    straight into a prompt, this keeps the useful part: who plays, when,
    and every book's price on the named market.
    """
    lines: list[str] = []
    for event in events:
        header = f"{event.matchup}"
        if event.commence_time:
            header += f" (starts {event.commence_time})"
        lines.append(header)
        any_price = False
        for book in event.bookmakers:
            market = book.market(market_key)
            if market is None:
                continue
            prices = ", ".join(
                f"{o.name} {_fmt_price(o.price)}"
                + (f" @{o.point:g}" if o.point is not None else "")
                for o in market.outcomes
            )
            if prices:
                any_price = True
                lines.append(f"  {book.title or book.key}: {prices}")
        if not any_price:
            lines.append(f"  no {market_key} prices returned")
    if not lines:
        return "No events returned."
    return "\n".join(lines)


def _fmt_price(price: float | None) -> str:
    if price is None:
        return "n/a"
    if float(price).is_integer():
        return str(int(price))
    return f"{price:g}"
