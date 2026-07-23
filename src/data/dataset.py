# src/data/dataset.py
"""
DraftDataset — emits draft decision-states as training samples.

Build order (filled in piece by piece):
  Layer 0  __init__ materialization + index maps   <-- THIS STEP
  Layer 1  enumerate decision-states (one game -> many samples)
  Layer 2  encode a state into fixed-slot tensors
  Layer 3  fearless-unavailable set (series computation)
  Layer 4  __len__ / __getitem__
"""

import numpy as np
import duckdb
from torch.utils.data import Dataset

PAD = 0  # reserved index: "empty slot / no champion" (early draft, missed bans, NULL)


class DraftDataset(Dataset):
    def __init__(self, db_path: str = "data/lol.duckdb"):
        con = duckdb.connect(str(db_path), read_only=True)

        # --- pull everything into memory, once ---
        self.games = con.execute("""
            SELECT game_id, patch, blue_team_id, red_team_id, blue_team_won,
                   series_id, game_in_series, date, league
            FROM games
            ORDER BY date, game_id
        """).df()

        self.actions = con.execute("""
            SELECT game_id, seq_index, action_type, side, champion_id, player_id, role
            FROM draft_actions
            ORDER BY game_id, seq_index
        """).df()

        champions = con.execute(
            "SELECT champion_id, name FROM champions ORDER BY champion_id"
        ).df()
        players = con.execute(
            "SELECT player_id FROM players ORDER BY player_id"
        ).df()
        patches = con.execute(
            "SELECT patch FROM patch_order ORDER BY major, minor"
        ).df()

        con.close()  # no live handle survives into DataLoader workers

        # --- index maps: raw id -> dense contiguous index (PAD=0 reserved) ---
        self.champ_to_idx = {int(c): i + 1 for i, c in enumerate(champions.champion_id)}
        self.idx_to_champ_name = {PAD: "<PAD>"}
        for i, (cid, name) in enumerate(zip(champions.champion_id, champions.name)):
            self.idx_to_champ_name[i + 1] = name

        self.player_to_idx = {p: i + 1 for i, p in enumerate(players.player_id)}
        self.patch_to_idx = {p: i for i, p in enumerate(patches.patch)}  # no PAD needed

        self.n_champions = len(self.champ_to_idx) + 1   # +1 for PAD
        self.n_players   = len(self.player_to_idx) + 1
        self.n_patches   = len(self.patch_to_idx)

        self.samples = []  # filled in Layer 1

    def champ_idx(self, champion_id):
        """Raw champion_id (or NULL/None/NaN) -> dense index; NULL -> PAD."""
        if champion_id is None or (isinstance(champion_id, float) and np.isnan(champion_id)):
            return PAD
        return self.champ_to_idx[int(champion_id)]

    def __len__(self):
        raise NotImplementedError("Layer 4")

    def __getitem__(self, i):
        raise NotImplementedError("Layer 4")


if __name__ == "__main__":
    ds = DraftDataset()
    raw = sorted(ds.champ_to_idx)
    print(f"games loaded        : {len(ds.games):,}")
    print(f"draft actions       : {len(ds.actions):,}")
    print(f"champions (+PAD)    : {ds.n_champions}   (PAD=0 reserved)")
    print(f"raw champion_id span: {raw[0]}..{raw[-1]}  <- sparse, non-contiguous")
    print(f"dense index span    : 1..{len(raw)}       <- what the embedding sees")
    print(f"players (+PAD)      : {ds.n_players:,}")
    print(f"patches             : {ds.n_patches}")