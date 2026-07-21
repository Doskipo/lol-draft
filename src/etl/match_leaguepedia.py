"""Match cached Leaguepedia games to our games -> series + game_in_series.

Key (spike-proven): (date +/-1 day, frozenset of 10 picked champion IDs).
Series reconstruction: within a tournament sorted by start time, gameInSeries
resetting to 1 starts a new series. Unmatched games keep NULL series info
(drop-and-report; schema designed for it).
"""

import json
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LP_DIR = PROJECT_ROOT / "data" / "leaguepedia"
DB_PATH = PROJECT_ROOT / "data" / "lol.duckdb"


def load_our_games(con) -> dict[tuple, list]:
    """Build lookup: frozenset(10 champ ids) -> [(game_id, date, league), ...]."""
    df = con.execute("""
        SELECT g.game_id, g.date, g.league,
               LIST(da.champion_id) AS champs
        FROM games g
        JOIN draft_actions da USING (game_id)
        WHERE da.action_type = 'pick'
        GROUP BY g.game_id, g.date, g.league
    """).df()
    lookup: dict[frozenset, list] = {}
    for _, r in df.iterrows():
        key = frozenset(int(c) for c in r["champs"])
        if len(key) != 10:
            continue                      # duplicate-champ anomaly; can't key on it
        lookup.setdefault(key, []).append((r["game_id"], pd.Timestamp(r["date"]), r["league"]))
    return lookup


def match_lp_game(lp_game: dict, lookup: dict) -> str | None:
    """Return our game_id or None."""
    picks = frozenset(
        p["championId"]
        for team in ("BLUE", "RED")
        for p in lp_game["teams"][team]["players"]
    )
    candidates = lookup.get(picks)
    if not candidates:
        return None
    lp_date = pd.Timestamp(lp_game["start"]).tz_localize(None)
    close = [gid for gid, date, _ in candidates if abs((date - lp_date).days) <= 1]
    if len(close) != 1:
        return None                       # ambiguous or date-mismatched -> unmatched
    return close[0]


def main():
    con = duckdb.connect(str(DB_PATH))
    lookup = load_our_games(con)
    print(f"our games indexed: {sum(len(v) for v in lookup.values())}")

    series_rows, game_updates, report = [], [], []
    next_series_id = 1

    for path in sorted(LP_DIR.glob("*.json")):
        lp_games = json.loads(path.read_text(encoding="utf-8"))
        lp_games.sort(key=lambda g: g["start"] or "")

        current_series = None
        n_matched = 0
        for g in lp_games:
            gis = g.get("gameInSeries")
            if gis == 1 or current_series is None:
                current_series = next_series_id
                next_series_id += 1
                series_rows.append({"series_id": current_series,
                                    "event": path.stem})
            our_id = match_lp_game(g, lookup)
            if our_id is not None:
                n_matched += 1
                game_updates.append({"game_id": our_id,
                                     "series_id": current_series,
                                     "game_in_series": gis})
        report.append({"tournament": path.stem,
                       "lp_games": len(lp_games),
                       "matched": n_matched,
                       "rate": round(n_matched / len(lp_games), 3) if lp_games else 0})

    rep = pd.DataFrame(report)
    print(rep.to_string(index=False))
    print(f"\ntotal matched: {rep['matched'].sum()} / {rep['lp_games'].sum()}")

    # ---- pure compute -> derived file (DuckDB can't UPDATE FK-referenced rows;
    # series info is applied by ingest_oracle at insert time)
    df_updates = pd.DataFrame(game_updates)
    df_updates["series_id"] = df_updates["series_id"].astype(str)
    ev = pd.DataFrame(series_rows)
    ev["series_id"] = ev["series_id"].astype(str)
    out = df_updates.merge(ev, on="series_id")

    derived = PROJECT_ROOT / "data" / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    out.to_csv(derived / "lp_series_matches.csv", index=False)
    print(f"\nwrote {len(out)} matches -> data/derived/lp_series_matches.csv")
    con.close()


if __name__ == "__main__":
    main()