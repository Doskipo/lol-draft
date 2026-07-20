"""Fetch Leaguepedia skeleton-tier game data per tournament -> data/leaguepedia/.

Cache-first & resumable: each tournament saved as one JSON, fetched once.
Re-run after connection drops; only missing tournaments are fetched.
Run off-peak (spike finding: LP drops connections under load).
"""

import dataclasses
import json
import time
from pathlib import Path

import pandas as pd
import leaguepedia_parser as lp
from leaguepedia_parser.site.leaguepedia import leaguepedia

from lp_common import lp_login, with_backoff

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LP_DIR = PROJECT_ROOT / "data" / "leaguepedia"
SEEDS_DIR = PROJECT_ROOT / "data" / "seeds"


def find_overview_page(region: str, name: str, year: int) -> str:
    """Tournament name -> OverviewPage, via raw Cargo (wrapper can't see all regions)."""
    result = with_backoff(
        leaguepedia.query,
        tables="Tournaments",
        fields="Name, OverviewPage",
        where=f"Year='{year}' AND Region='{region}' AND Name='{name}'",
    )
    if not result:
        raise LookupError(f"tournament {name!r} not found (region {region!r}, year {year})")
    return result[0]["OverviewPage"]


def fetch_tournament(region: str, name: str, year: int) -> list[dict]:
    page = find_overview_page(region, name, year)
    games = with_backoff(lp.get_games, page)
    return [dataclasses.asdict(g) for g in games]


def main():
    lp_login()
    LP_DIR.mkdir(parents=True, exist_ok=True)
    seed = pd.read_csv(SEEDS_DIR / "lp_tournaments.csv")

    for _, row in seed.iterrows():
        out = LP_DIR / f"{row.tournament_name.replace('/', '_').replace(':', '')}.json"
        if out.exists():
            print(f"cached: {out.name}")
            continue
        print(f"fetching: {row.tournament_name} ({row.region})")
        games = fetch_tournament(row.region, row.tournament_name, row.year)
        out.write_text(json.dumps(games), encoding="utf-8")
        print(f"  saved {out.name}: {len(games)} games")
        time.sleep(5)

    print("all tournaments cached.")


if __name__ == "__main__":
    main()