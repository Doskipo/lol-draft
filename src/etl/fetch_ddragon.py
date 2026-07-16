"""One-time fetch of Data Dragon champion data -> data/ddragon/.

Re-run only when a new champion ships (ingest will crash on the unmapped name).
"""

import json
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DDRAGON_DIR = PROJECT_ROOT / "data" / "ddragon"


def main():
    versions = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()
    version = versions[0]          # latest — looked up once, recorded in the filename
    champs = requests.get(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    ).json()

    DDRAGON_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DDRAGON_DIR / f"champion_{version}.json"
    out_path.write_text(json.dumps(champs), encoding="utf-8")
    print(f"saved {out_path.name}")


if __name__ == "__main__":
    main()