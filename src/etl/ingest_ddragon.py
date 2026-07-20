"""Parse the cached Data Dragon snapshot -> champion_attributes.

Separate from ingest_oracle.py (different source, different cadence), but the
same doctrine: wipe-and-rebuild its own table, crash on surprises.
Run AFTER ingest_oracle.py (FK on champions).
"""

import json
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "lol.duckdb"
DDRAGON_DIR = DATA_DIR / "ddragon"


def main():
    files = sorted(DDRAGON_DIR.glob("champion_*.json"))
    if len(files) != 1:
        raise FileNotFoundError(f"expected exactly one snapshot, found {files}")
    version = files[0].stem.removeprefix("champion_")
    champs = json.loads(files[0].read_text(encoding="utf-8"))["data"]

    rows = []
    for c in champs.values():
        rows.append({
            "champion_id": int(c["key"]),
            "attack_mark": c["info"]["attack"],
            "defense_mark": c["info"]["defense"],
            "magic_mark": c["info"]["magic"],
            "difficulty_mark": c["info"]["difficulty"],
            "partype": c["partype"],
            "tag_primary": c["tags"][0],
            "tag_secondary": c["tags"][1] if len(c["tags"]) > 1 else None,
            **c["stats"],
            "ddragon_version": version,
        })
    df_attrs = pd.DataFrame(rows)

    con = duckdb.connect(str(DB_PATH))
    con.execute("DELETE FROM champion_attributes")
    con.execute("INSERT INTO champion_attributes BY NAME SELECT * FROM df_attrs")
    n = con.execute("SELECT COUNT(*) FROM champion_attributes").fetchone()[0]
    print(f"champion_attributes: {n} rows (ddragon {version})")
    con.close()


if __name__ == "__main__":
    main()