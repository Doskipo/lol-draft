"""Ingest Oracle's Elixir CSVs into the normalized DuckDB schema

Strategy: wipe-and-rebuild (idempotent). The CSVs are the source of truth, 
the DB is derived. Safe to re-run at any time.

"""

from pathlib import Path

import json
import duckdb
import pandas as pd

# --- Constants ---

PROJECT_ROOT = Path(__file__).resolve().parents[2]      # src/etl/ -> src/ -> project root
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "lol.duckdb"
DDRAGON_DIR = DATA_DIR / "ddragon"
SEEDS_DIR = DATA_DIR / "seeds"

SCHEMA_PATH = PROJECT_ROOT / "src" / "db" / "schema.sql"

# (side, action_type, team_slot)
DRAFT_SEQ = {
    ("Blue", "ban", 1): 1,   ("Red", "ban", 1): 2,
    ("Blue", "ban", 2): 3,   ("Red", "ban", 2): 4,
    ("Blue", "ban", 3): 5,   ("Red", "ban", 3): 6,
    ("Blue", "pick", 1): 7,  ("Red", "pick", 1): 8,
    ("Red", "pick", 2): 9,   ("Blue", "pick", 2): 10,
    ("Blue", "pick", 3): 11, ("Red", "pick", 3): 12,
    ("Red", "ban", 4): 13,   ("Blue", "ban", 4): 14,
    ("Red", "ban", 5): 15,   ("Blue", "ban", 5): 16,
    ("Red", "pick", 4): 17,  ("Blue", "pick", 4): 18,
    ("Blue", "pick", 5): 19, ("Red", "pick", 5): 20,
}


# --- Auxiliary Functions ---

def apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Apply schema.sql (idempotent — IF NOT EXISTS / OR REPLACE inside)."""
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

def wipe(con: duckdb.DuckDBPyConnection) -> None:
    """Wipe (reverse dependency order) ONLY the tables this script rebuilds.
    Never touch hand-built tables (fearless_config) or other scripts' tables."""
    for table in ["fearless_config","draft_actions", "games", "series", "team_aliases",
                  "players", "teams", "champion_attributes", "champions"]:
        con.execute(f"DELETE FROM {table}")

# --- Stages ---


def load_name_to_id() -> dict[str, int]:
    """Build champion name -> Riot numeric ID from the cached Data Dragon file."""
    files = sorted(DDRAGON_DIR.glob("champion_*.json"))
    if len(files) != 1:
        raise FileNotFoundError(
            f"expected exactly one cached Data Dragon file, found {len(files)}: "
            f"{[f.name for f in files]} — run fetch_ddragon.py / remove old snapshots"
        )
    champs = json.loads(files[0].read_text(encoding="utf-8"))["data"]
    return {c["name"]: int(c["key"]) for c in champs.values()}


def validate_champion_names(df: pd.DataFrame, name_to_id: dict[str, int]) -> None:
    """Every champion name in the CSV must map to an ID — crash loudly if not."""
    ban_cols = ["ban1", "ban2", "ban3", "ban4", "ban5"]
    seen = set(df["champion"].dropna())
    for col in ban_cols:
        seen |= set(df[col].dropna())
    unmapped = seen - name_to_id.keys()
    if unmapped:
        raise ValueError(
            f"{len(unmapped)} champion name(s) in CSV not in Data Dragon snapshot: "
            f"{sorted(unmapped)} — stale snapshot or spelling drift"
        )
    print(f"champion validation: {len(seen)} distinct names in CSV, all mapped")


def ingest_champions(con: duckdb.DuckDBPyConnection, name_to_id: dict[str, int]) -> None:
    """Fill `champions` with the full Data Dragon roster."""
    df_champs = pd.DataFrame(
        [(cid, name) for name, cid in name_to_id.items()],
        columns=["champion_id", "name"],
    )
    con.execute("INSERT INTO champions SELECT champion_id, name FROM df_champs")
    n = con.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
    print(f"champions: {n} rows")


def ingest_teams(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> dict[str, int]:
    """Fill `teams` + `team_aliases`. Returns OE teamid -> our team_id."""
    rows = df.dropna(subset=["teamid"])

    # enforce the 1:1, if a future CSV breaks it, crash loudly
    multi = rows.groupby("teamid")["teamname"].nunique()
    if (multi > 1).any():
        raise ValueError(f"teamid with multiple names: {multi[multi > 1].index.tolist()}")

    df_teams = (
        rows.groupby("teamid")
        .agg(name=("teamname", "first"),
             league_region=("league", lambda s: s.mode().iloc[0]))
        .reset_index()
        .sort_values("teamid")
        .reset_index(drop=True)
    )
    df_teams["team_id"] = range(1, len(df_teams) + 1)   # mint surrogate keys

    con.execute("INSERT INTO teams SELECT team_id, name, league_region FROM df_teams")

    # aliases: the OE name AND the OE teamid both resolve to our team
    name_alias = df_teams[["name", "team_id"]].rename(columns={"name": "alias"})
    oeid_alias = df_teams[["teamid", "team_id"]].rename(columns={"teamid": "alias"})
    aliases = pd.concat([name_alias, oeid_alias], ignore_index=True)

    # seed file: hand-curated cross-source spellings -> canonical OE name -> team_id
    seed = pd.read_csv(SEEDS_DIR / "team_aliases.csv")
    name_to_tid = dict(zip(df_teams["name"], df_teams["team_id"]))
    missing = set(seed["canonical_name"]) - name_to_tid.keys()
    if missing:
        raise ValueError(f"seed canonical names not found in this CSV: {sorted(missing)}")
    seed_alias = pd.DataFrame({
        "alias": seed["alias"],
        "team_id": seed["canonical_name"].map(name_to_tid),
    })
    aliases = pd.concat([aliases, seed_alias], ignore_index=True)

    con.execute("INSERT INTO team_aliases SELECT alias, team_id FROM aliases")

    n_t = con.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    n_a = con.execute("SELECT COUNT(*) FROM team_aliases").fetchone()[0]
    print(f"teams: {n_t} rows · team_aliases: {n_a} rows")

    return dict(zip(df_teams["teamid"], df_teams["team_id"]))


def ingest_players(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    """Fill `players` — v0: name-as-ID (parking lot: player_aliases if it bites)."""
    df_players = (
        df.dropna(subset=["playername"])[["playername"]]
        .drop_duplicates()
        .rename(columns={"playername": "player_id"})
    )
    con.execute("INSERT INTO players SELECT player_id FROM df_players")
    n = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    print(f"players: {n} rows")



def ingest_games(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame,
    oe_to_team: dict[str, int], kept: set[str],
) -> None:
    """Fill `games` — insertion only; admission was decided upstream."""
    team_rows = df[(df["position"] == "team") & (df["gameid"].isin(kept))]
    blue = team_rows[team_rows["side"] == "Blue"]
    red = team_rows[team_rows["side"] == "Red"]
    games = blue.merge(red, on="gameid", suffixes=("_blue", "_red"))

    df_games = pd.DataFrame({
        "game_id": games["gameid"],
        "patch": games["patch_blue"],
        "blue_team_id": games["teamid_blue"].map(oe_to_team),
        "red_team_id": games["teamid_red"].map(oe_to_team),
        "date": pd.to_datetime(games["date_blue"]),
        "blue_team_won": games["result_blue"].astype(bool),
        "league": games["league_blue"],
        "series_id": None,
        "game_in_series": None,
    })

    matches = load_series_matches()
    if matches is not None:
        df_series, matches = build_series(df_games, matches)
        con.execute("INSERT INTO series BY NAME SELECT * FROM df_series")
        df_games = df_games.drop(columns=["series_id", "game_in_series"]).merge(
            matches[["game_id", "series_id", "game_in_series"]], on="game_id", how="left")
        print(f"series: {len(df_series)} rows")

    con.execute("INSERT INTO games SELECT * FROM df_games")
    n = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    print(f"games: {n} rows")


def insert_draft_actions(con: duckdb.DuckDBPyConnection, df_actions: pd.DataFrame) -> None:
    con.execute("INSERT INTO draft_actions SELECT * FROM df_actions")
    n = con.execute("SELECT COUNT(*) FROM draft_actions").fetchone()[0]
    print(f"draft_actions: {n} rows ({n // 20 if n % 20 == 0 else 'NOT DIVISIBLE BY 20!'} games)")



def load_raw(csv_path: Path) -> pd.DataFrame:
    """Read one OE CSV with correct dtypes."""
    df = pd.read_csv(csv_path, dtype={
        "patch" : "string",
        "url" : "string",
        "split" : "string"
        })
    print(f"loaded {csv_path.name}: {len(df):,} rows, {df['gameid'].nunique():,} games")
    return df


# --- Functional Core ---

def select_draft_complete_games(df: pd.DataFrame) -> set[str]:
    """Admission check #1: team rows must carry teamid + pick order.
    Reality's holes -> drop-and-report."""
    team_rows = df[df["position"] == "team"]
    bad = team_rows[team_rows["teamid"].isna() | team_rows["pick1"].isna()]
    kept = set(team_rows["gameid"]) - set(bad["gameid"])
    if len(bad):
        by_league = bad.drop_duplicates("gameid")["league"].value_counts()
        print(f"skipping {bad['gameid'].nunique()} game(s) with missing teamid/picks; by league:")
        print(by_league.to_string())
    return kept

def build_draft_actions(
    df: pd.DataFrame, kept: set[str], name_to_id: dict[str, int]
) -> tuple[pd.DataFrame, set[str]]:
    """Weave per-team pick/ban columns into the ordered 20-action draft.
    Pure computation — no DB writes. Returns (actions, contradiction_games)."""
    team_rows = df[(df["position"] == "team") & (df["gameid"].isin(kept))]

    actions = team_rows.melt(
        id_vars=["gameid", "side"],
        value_vars=[f"{t}{i}" for t in ("ban", "pick") for i in range(1, 6)],
        var_name="col", value_name="champ_name",
    )
    actions["action_type"] = actions["col"].str.extract(r"^(ban|pick)")
    actions["slot"] = actions["col"].str.extract(r"(\d)$").astype(int)
    actions["seq_index"] = [
        DRAFT_SEQ[(side, t, slot)]
        for side, t, slot in zip(actions["side"], actions["action_type"], actions["slot"])
    ]
    actions["champion_id"] = actions["champ_name"].map(name_to_id).astype("Int64")

    player_rows = df[(df["position"] != "team") & (df["gameid"].isin(kept))][
        ["gameid", "side", "champion", "playername", "position"]
    ].rename(columns={"champion": "champ_name", "playername": "player_id", "position": "role"})
    actions = actions.merge(player_rows, on=["gameid", "side", "champ_name"], how="left")

    picks = actions[actions["action_type"] == "pick"]

    # our-bug tripwire: every pick name must map (validated upstream) -> crash
    if picks["champion_id"].isna().any():
        raise ValueError("pick without champion_id — mapping assumption broken")

    # admission check #2: pick columns must agree with player rows -> drop-and-report
    orphans = set(picks[picks["player_id"].isna()]["gameid"].unique())
    if orphans:
        print(f"dropping {len(orphans)} game(s) whose pick columns contradict player rows: "
              f"{sorted(orphans)}")
        actions = actions[~actions["gameid"].isin(orphans)]

    df_actions = pd.DataFrame({
        "game_id": actions["gameid"],
        "seq_index": actions["seq_index"],
        "action_type": actions["action_type"],
        "side": actions["side"].str.lower(),
        "champion_id": actions["champion_id"],
        "player_id": actions["player_id"],
        "role": actions["role"],
    })
    return df_actions, orphans

def load_series_matches() -> pd.DataFrame | None:
    path = DATA_DIR / "derived" / "lp_series_matches.csv"
    if not path.exists():
        print("no series-matches file — series info left NULL "
              "(run match_leaguepedia.py, then re-run this ingest)")
        return None
    return pd.read_csv(path, dtype={"series_id": "string"})


def build_series(df_games: pd.DataFrame, matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Derive series facts from matched games. Returns (df_series, kept_matches)."""
    m = matches.merge(
        df_games.drop(columns=["series_id", "game_in_series"]), on="game_id"
    )
    m["winner_id"] = m["blue_team_id"].where(m["blue_team_won"], m["red_team_id"])

    def summarize(s: pd.DataFrame) -> pd.Series:
        best_of = 2 * int(s.groupby("winner_id").size().max()) - 1
        return pd.Series({
            "best_of": best_of if best_of in (1, 3, 5) else None,
            "team1_id": s["blue_team_id"].iloc[0],
            "team2_id": s["red_team_id"].iloc[0],
            "event": s["event"].iloc[0],
            "date": s["date"].min(),
        })

    df_series = (m.groupby("series_id").apply(summarize, include_groups=False)
                   .reset_index())
    bad = df_series[df_series["best_of"].isna()]
    if len(bad):
        print(f"skipping {len(bad)} series with underivable best_of (forfeit/incomplete)")
        df_series = df_series[df_series["best_of"].notna()]
        matches = matches[matches["series_id"].isin(df_series["series_id"])]
    return df_series, matches


def ingest_fearless(con: duckdb.DuckDBPyConnection) -> None:
    path = SEEDS_DIR / "fearless_config.csv"
    df_fc = pd.read_csv(path, dtype={"event": "string", "mode": "string"})
    con.execute("INSERT INTO fearless_config BY NAME SELECT * FROM df_fc")
    print(f"fearless_config: {len(df_fc)} rows")


# --- Orchestrator ---
def main():
    # ---- compute & validate (no DB) ----
    df = load_raw(DATA_DIR / "2025_LoL_esports_match_data_from_OraclesElixir.csv")
    name_to_id = load_name_to_id()
    validate_champion_names(df, name_to_id)

    kept = select_draft_complete_games(df)
    df_actions, orphans = build_draft_actions(df, kept, name_to_id)
    kept -= orphans          # the final verdict: one set, both writers obey it

    # ---- write (all admission decisions final) ----
    con = duckdb.connect(str(DB_PATH))
    apply_schema(con)
    wipe(con)
    ingest_champions(con, name_to_id)
    oe_to_team = ingest_teams(con, df)
    ingest_players(con, df)
    ingest_games(con, df, oe_to_team, kept)
    insert_draft_actions(con, df_actions)
    ingest_fearless(con)
    con.close()

if __name__ == "__main__":
    main()



"""
import json
from pathlib import Path
import pandas as pd

champs = json.loads(Path("data/ddragon/champion_16.14.1.json").read_text(encoding="utf-8"))["data"]
all_names = {c["name"] for c in champs.values()}

df = pd.read_csv("data/2025_LoL_esports_match_data_from_OraclesElixir.csv", dtype={"patch": "string", "url": "string", "split": "string"})
seen = set(df["champion"].dropna())
for col in ["ban1", "ban2", "ban3", "ban4", "ban5"]:
    seen |= set(df[col].dropna())

all_names - seen
"""