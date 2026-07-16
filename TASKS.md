# TASKS — LoL Draft Recommender (v0)

Living tracker. Companion to `PROJECT_SPEC.md`.
- **Spec = why/how** (design; changes slowly). **Tasks = what/now** (checklist; changes constantly).
- Drive off the **▶ CURRENT FOCUS** marker. When a phase is fully checked, move ▶ down.
- Check boxes with `[x]`. Park stray ideas in the Parking Lot at the bottom rather than derailing.

Legend: `[core]` required · `[novel]` your contribution · `[stretch]` upside.

---

## Phase tree (mermaid — renders in most markdown viewers)

```mermaid
graph TD
  P0["Phase 0 · data &amp; infra (+ series) — W1-3 ▶"]:::core
  P1["Phase 1 · WP backbone + priors + fearless mask — W4-5"]:::core
  P2["Phase 2 · fixed/meta champ — #1"]:::novel
  P3["Phase 3 · relation graph + archetypes — #2"]:::novel
  P4["Phase 4 · bans (denial) — #3"]:::novel
  M(["Milestone · pro-only spine, fearless-legal — W12"]):::mile
  P5["Phase 5 · fearless series strategy — #5"]:::novel
  P6["Phase 6 · flex / latent role"]:::novel
  P7["Phase 7 · hybrid soloQ↔pro — #4"]:::novel
  P8["Phase 8 · stretch: lookahead, series search, LCU"]:::stretch
  P0 --> P1 --> P2 --> P3 --> P4 --> M
  M --> P5 --> P6 --> P8
  M --> P7 --> P8
  classDef core fill:#E1F5EE,stroke:#0F6E56,color:#04342C;
  classDef novel fill:#EEEDFE,stroke:#534AB7,color:#26215C;
  classDef mile fill:#FAEEDA,stroke:#854F0B,color:#412402;
  classDef stretch fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
```

---

## ▶ CURRENT FOCUS — Phase 0 · Data & infra (W1–3) `[core]`

> Exit criteria: a queryable DB + a PyTorch `Dataset` that yields draft states + the
> games-per-patch number written down.

**0.1 Environment & repo**
- [x] Create repo `lol-draft`, `git init`, Python env (uv or conda)
- [x] **Register Riot personal API key** (instant; needed as soloQ-meta fallback long before Phase 7 —
      the *production* key application is separate and slow, file it when Phase 7 approaches)
- [x] Install: `polars`, `duckdb`, `requests`, `torch`, `torch-geometric` (PyG later is fine)
- [x] Lay down the folder skeleton from `PROJECT_SPEC.md` §5
- [ ] (defer) Hydra + Weights & Biases — add when training starts in Phase 1

**0.2 First data look — the gating numbers** *(do this before any modeling)*
- [x] Download one Oracle's Elixir CSV (latest full year) from oracleselixir.com
- [x] Load in DuckDB; inspect the 12-rows-per-game layout
- [x] Confirm the pick-order and ban columns exist; write down the column mapping
- [x] **Count distinct games per patch** → record: `200–900, typically ~500–600` (tail patches 15.21+
      near-empty: post-Worlds off-season → min-N rule for test patches, see parking lot)
- [x] Count distinct (champion, patch) pairs → record: `3,183` (~800 of ~4,000 possible pairs never
      occur in a full year → ID-only per-patch representation impossible; ≈30 games/champ/patch avg, 0–5 off-meta)
- [x] Decision note: small per-patch N ⇒ lean harder on fixed attributes + shrinkage (spec §3.1) + Phase 6. **Locked.**

**0.2b Entity-resolution spike** *(done — full write-up in `notebooks/02_entity_spike.ipynb` + spec §2 outcome box)*
- [x] Join OE ↔ Leaguepedia on **(date ±1, frozenset of 10 picked champion IDs)** → **15/15 matched**;
      0 champion aliases needed; **7/15 team-name mismatches** (sponsor prefixes/renames) → seed `team_aliases`
- [x] Bonus finds: LP `picksBans` verifies the **weave rules** (OE per-team order + format = full 20-action
      draft); patch schemes differ (`15.06`↔`'25.06'`); identities hide in LP's `.sources`; costs measured
      (bot-password auth, ~10–30 s/detail call, backoff + incremental cache mandatory, fetch off-peak)
- [x] Decision note: **OE = backbone incl. full draft order; Leaguepedia = supplement** —
      `gameInSeries` from cheap skeleton tier; detail calls only for player metadata (Phases 4/7)

**0.3 Schema & ingest**
- [x] Write `schema.sql` — **11 tables live** (`SHOW TABLES` verified), incl. `team_aliases` (seeded by
      spike) and the `champion_meta` / `champion_role_meta` grain split; principles documented in spec §2.1
- [ ] **As-of aggregation views** (spec §2.2): `meta_asof(champion, date)` = previous-patch stats,
      `edges_asof(date)` = train-window-only relation stats — leakage structurally impossible
- [x] `ingest_oracle.py`: CSV → normalized tables — **9,534 games / 190,680 draft actions (÷20 exact)**.
      Two-phase structure (compute+validate, then write); central `wipe()` in reverse-FK order;
      admission = *our* fields, not OE's `datacompleteness` flag (LPL kept!); drop-and-report for
      source holes (506 ID-less minor-league games + 1 LRS pick/player contradiction), crash for
      our bugs; missed bans → NULL-champion actions; `fetch_ddragon.py` pins the snapshot (16.14.1)
- [x] Sanity queries: FK audit **0 orphans**; 300 NULL-champion bans (0.31%, matches measured
      missingness); Locke = the only never-drafted champion (post-season release — universe ⊃ observed
      as designed); Aatrox winrate cross-check DB vs CSV consistent (deltas ⊂ the 507 excluded games)

**0.4 Enrich**
- [ ] Riot Data Dragon → `champion_attributes` (the fixed `v_attr`; `name_to_id` map already built in spike)
- [ ] Leaguepedia *(scoped per spike verdict)* → `gameInSeries` via cheap skeleton tier, matched on
      champion-set key; cached background script with backoff, run off-peak
- [x] gol.gg spot-check: pick/ban column order verified against a real draft (done during 0.2)

**0.4b Series & fearless** *(needed for Phase 5 — set it up now while in the data)*
- [ ] Reconstruct series: populate `series` + `games.series_id` / `game_in_series` (Leaguepedia is cleanest)
- [ ] Build `fearless_config` lookup by hand (event + date → none/soft/hard) from the adoption timeline
- [ ] Derive helper: per (series, game) → fearless-unavailable set (both-teams for hard, same-team for soft)
- [ ] **Count fearless series per patch** → record: `____` (tells you if Phase 5 has enough data)

**0.5 Dataset & splits**
- [ ] `dataset.py`: emit a draft *state* sample (picks/bans so far, turn, side, patch, players)
- [ ] `splits.py`: future-patch splitter (train ≤T, val T+1, test T+2+)
- [ ] EDA notebook: pick/ban frequency, patch coverage, role distributions

---

## Phase 1 · WP backbone + priors (W4–5) `[core]`

> Exit: **both** WP models (structured spine + black-box antagonist) beat both priors on a held-out
> **future** patch; `recommend()` works through the structured value.

- [ ] Prior A — meta tier-list (top-winrate champ per role/patch)
- [ ] Prior B — player-comfort (player's best champ per role from history)
- [ ] Tokenizer: champion ⊕ role ⊕ side ⊕ patch (players added later)
- [ ] **Structured spine (the model):** additive value → logistic/FM WP read-out team-vs-team,
      BCE on outcomes — trains base / syn / ctr (spec §3.3a)
- [ ] **Black-box set-Transformer (the antagonist):** same data, same mask, no availability structure —
      the baseline the centerpiece experiment beats; also the raw-fit ceiling check (spec §3.3b)
- [ ] **Exposure operator:** `vuln(c,r) ≡ ctr(r,c)` (transpose — no separate scorer, no untrained
      params); softmax over `A_enemy`, uniform weights in v0 (pick-likelihood weights arrive in Phase 4)
- [ ] Train loop + metrics: accuracy, AUC, **Brier / ECE** (calibration) — for BOTH models
- [ ] Future-patch eval harness (as-of features only, spec §2.2); confirm both models > priors
- [ ] **Fearless-correct mask:** `F` also removes the series consumed-set (cheap; makes the model legal)
- [ ] Greedy recommendation read-out (argmax V over feasible set — always through the structured value)

---

## Phase 2 · Fixed/meta champion encoder (W6–7) `[novel]` — contribution #1

- [ ] `z_fix(a_c)` MLP over intrinsic attributes
- [ ] `z_meta(c, π)` patch-conditioned component + gate — inputs are **shrunk** meta stats
      (empirical-Bayes toward previous patch / global prior, weight ∝ n_games; spec §3.1)
- [ ] `base(c|π)` head reads from `z_c` — **never** a free (champion, patch) table
- [ ] Ablation: ID-only vs +fixed vs +meta on unseen-champion / future-patch
- [ ] Plot: generalization gap narrows with fixed attributes

---

## Phase 3 · Relation graph + archetypes (W8–9) `[novel]` — contribution #2

- [ ] Build synergy / counter / shared-role edges from match stats — **train-window only / as-of**
      (`edges_asof`, spec §2.2; full-dataset edges leak into future-patch eval)
- [ ] GNN (PyG) over the static graph → champion embeddings feed the WP model
- [ ] Archetype clustering + soft-assignment head
- [ ] Interpretability: per-pick attribution ("synergy with X / counter to Y")
- [ ] Archetype-map visualization (the visual artifact)
- [ ] **Synthetic counter-consumption probe, v0** (centerpiece dry-run — needs NO fearless data):
      remove champ `c`'s top-k counters from `A` on real drafts → ΔV dose-response, structured vs
      black-box (spec §3.8 metric 1). If this doesn't separate the models, find out NOW, not in Phase 5

---

## Phase 4 · Player-conditioned bans (W10–11) `[novel]` — contribution #3

- [ ] Enemy pick-likelihood head (from histories)
- [ ] `BanValue(c)` = WP delta over enemy comfort picks
- [ ] **Wire pick-likelihood into the exposure weights** `w_r` (spec §3.0/§3.6 — one head, two
      read-outs: bans and exposure are the same mechanism)
- [ ] Eval: top-k ban accuracy vs actual pro bans (**sanity only** — measures predictable, not good,
      bans) + the WP-delta denial case study that carries the argument

---

## ◆ Milestone · pro-only spine ships (W12)

- [ ] End-to-end on a real draft: data → WP → recommend + bans + explanations
- [ ] **Centerpiece probe figure v0** (from Phase 3) in the writeup — the paper's primary result
      already exists at the milestone, before any fearless data is touched
- [ ] Draft of the short writeup (problem, method, results vs priors + DraftRec + the black-box antagonist)
- [ ] Repo `README` + a reproducible run command

---

## Phase 5 · Fearless series strategy `[novel]` — gap 6, contribution #5

> The most novel piece — no prior model handles fearless. Mask-correctness already shipped in Phase 1;
> this is the strategic modeling on top.

- [ ] Consumed-pool summary fed to the WP backbone (dual-pooled: our-consumed vs their-consumed)
- [ ] Series-context features: `game_in_series`, series score, `fearless_mode`
- [ ] Remaining-pool player conditioning (comfort = best *remaining* champion)
- [ ] Eval: with vs without series-state, broken down by `game_in_series`
- [ ] **Stratified rank agreement** on real fearless states (advantage should concentrate in the
      consumed-counters stratum — spec §3.8 metric 2)
- [ ] **Late-series calibration**: Brier/ECE by `game_in_series` (spec §3.8 metric 3)
- [ ] Champion-diversity figure per series (the Riot-facing result)
- [ ] Recency split: train earlier-2025 series, test later

---

## Phase 6 · Flex / latent role `[novel]` — gap 2

- [ ] `q(r | c, π)` role distribution from data
- [ ] Marginalize over role assignments in the team encoder
- [ ] Flex-value metric (entropy) + analysis (amplified under fearless — pairs with Phase 5)

---

## Phase 7 · Hybrid soloQ ↔ pro `[novel]` — contribution #4

- [ ] **File the Riot production API key application** (personal key done in 0.1; production approval takes time)
- [ ] `ingest_riot_soloq.py` → soloQ matches + player histories
- [ ] Reconcile champion / patch / role / player IDs across domains
- [ ] Stage A: pretrain champion + relation + player encoders on soloQ WP
- [ ] Stage B: init from A; fine-tune order-aware backbone + heads on pro (domain token)
- [ ] Consistency rule: represent pros via their **soloQ** accounts through the shared encoder
- [ ] soloQ-replay guard against catastrophic forgetting
- [ ] Ablation: pro-only vs hybrid; domain/patch separability check

---

## Phase 8 · Stretch `[stretch]`

- [ ] One-step opponent-reply model → shallow lookahead / MCTS
- [ ] Multi-game series search (true fearless meta-game over the Bo5)
- [ ] LCU client: read the live champ-select session
- [ ] Live demo: paste 10 op.gg profiles → recommendations + explanations

---

## Paper (throughout)

- [ ] Maintain the related-work delta table (vs DraftArtist, JueWuDraft, NeuralAC, DraftRec)
- [ ] Log every ablation result the day you get it
- [ ] Figures: archetype map · generalization plot · ban case study · champion-diversity-per-series

---

## Parking lot (revisit later, don't derail now)

- Late-year patches are useless as test patches for the future-patch split; the splitter should require a minimum-N per eval patch. Coincides with post-Worlds off-season, almost no pro play.
- Manual champion mechanic flags (CC / dash / global / healing) as `champion_attributes` enrichment — only if Phase 2 ablations show fixed attributes matter; ~170 champs is hand-buildable.
- Historical `champion_attributes` (Data Dragon archives every version) — v0 deliberately uses one snapshot (`ddragon_version` records which).
- `player_aliases` table if name-as-ID bites; `player_accounts` (op.gg/soloQ links, one player → many accounts) arrives in Phase 7.
- Feature normalization (e.g. stats relative to max) lives in the pipeline, computed on train window only — never in the DB.
- Scrims support: `series.event = NULL` convention (the "teams using this tool on their own scrims" idea).
- Ban role-targeting is derivable (join ban champion vs `champion_role_meta`) — no schema change; the player-level version IS Phase 4.
- Off-meta playstyle identity (lethality-Sion problem): unobservable in draft data; represented indirectly via role conditioning + player conditioning (Phases 4/6/7).
- Minor-league ID-less games skipped at ingest (~480 games, 62 name-only teams, LJL-dominated;
  plus ~26 order-less games): rescuable via name-minted teams if per-patch N ever gets desperate.
  Decision: cleaner N over more N — majors all have pristine IDs.