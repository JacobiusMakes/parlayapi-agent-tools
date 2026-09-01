"""Real odds with no API key and no signup.

    python examples/keyless_demo.py [sport_key]

Uses the free demo endpoints, which are capped at moneyline only, the first
5 games, and 60 requests per hour per IP.
"""

from __future__ import annotations

import sys

from parlayapi_tools import (
    DEMO_SPORTS,
    ParlayAPIClient,
    ParlayAPIError,
    format_events_for_llm,
)


def main() -> int:
    sport = sys.argv[1] if len(sys.argv) > 1 else "americanfootball_nfl"
    if sport not in DEMO_SPORTS:
        print(f"Demo sports: {', '.join(DEMO_SPORTS)}")
        return 2

    client = ParlayAPIClient(api_key=None)

    try:
        demo = client.demo_odds(sport)
    except ParlayAPIError as exc:
        print(f"Demo call failed: {exc}")
        return 1

    print(f"== {sport} moneylines ({demo.events_returned} games) ==")
    print(format_events_for_llm(demo.events, "h2h"))
    print()

    print("== best posted price per game ==")
    for event in demo.events:
        for side in (event.away_team, event.home_team):
            best = event.best_price("h2h", side)
            if best:
                book, price = best
                print(f"  {side}: {price:+.0f} at {book}")

    print()
    try:
        ev = client.demo_positive_ev(sport)
    except ParlayAPIError as exc:
        print(f"EV demo unavailable: {exc}")
        return 0

    print(f"== top +EV vs {ev.sharp_anchor} ==")
    for opp in ev.opportunities:
        print(
            f"  {opp.side} at {opp.book}: {opp.price:+.0f}, "
            f"edge {opp.edge_pct:.2f}%"
        )

    print()
    print(f"{demo.demo_remaining_hour} demo requests left this hour.")
    print("Full access, free tier 1,000 credits/month, no card:")
    print("  https://parlay-api.com/signup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
