# Interpretable, Patch-Generalizing Draft Recommendation for Pro League of Legends

**Project spec & roadmap** — pro-primary data, part-time cadence, deliverable = repo + demo + short paper.

---

## 0. One-paragraph thesis

A single **win-probability (WP) model** over the 10-slot draft is the backbone. Champion
**recommendation**, **ban valuation**, and **explanations** are all read-outs of that one function.
The novelty vs prior work (DraftArtist, JueWuDraft, NeuralAC, DraftRec) is the combination of
(a) **ordered pro draft data** (pick/ban order, which the Riot API lacks), (b) a **fixed-vs-meta
champion decomposition** that generalizes across patches, (c) an **interpretable relation-graph +
archetype** layer, (d) **player-conditioned bans** as denial, (e) a **hybrid soloQ↔pro** training
scheme (Phase 7) where soloQ supplies low-variance champion/player representations and pro supplies
coordinated team value + draft structure, and (f) **fearless-draft awareness** — modeling the
series-level champion lockout (Phase 5) that *no prior model handles*, since hard fearless postdates
all of them (LPL 2024 / global 2025). Prior work is soloQ, black-box, single-patch, pick-only, and
single-game.

The paper's narrative device: an **identically-trained black-box set-Transformer** is built alongside
the structured value from Phase 1 and serves as the *antagonist* throughout — every contribution is
demonstrated as "the structured model does X, the black-box (with identical data, mask, and training)
does not."

---

## 1. Scope: what ships vs what's stretch

Part-time over a summer ≈ 10–12 focused hrs/week for ~12 weeks. Prioritize ruthlessly.

| Tier | Component | Status |
|:-----|:-----------------------------|:-------|
| **Core (must ship — this is the paper)** | Data pipeline + SQL DB | required |
| | WP backbone + dumb priors as floors | required |
| | Black-box set-Transformer (the *antagonist* baseline, §3.3b) | required |
| | Fixed/meta champion decomposition (gap 1) | required |
| | Relation-graph embeddings + archetypes (gap 4) | required |
| | Future-patch evaluation | required |
| | Fearless-correct availability mask + series data | required |
| **Hook (the paper's originality)** | Player-conditioned bans (gap 3) | target |
| | Flex / latent-role + flex-value metric (gap 2) | target |
| | Fearless series-state modeling (gap 6, Phase 5) | target |
| | Hybrid soloQ↔pro pretraining (Phase 7) | target |
| **Stretch (demo candy, not an evaluated claim)** | Counterpick one-step lookahead (gap 5) | stretch |
| | Live LCU champ-select demo | stretch |

Goal is **all gaps covered**. The ordering below is a dependency order, not a priority cut — but if
time slips, the Core block is the part that must ship standalone. Bans before flex (cleaner eval),
and build the **pro-only spine before the hybrid** so something trains end-to-end first.

---

## 2. Data

**Sources (pro / tournament — required because Riot's API has no tournament data and no pick order):**
- **Oracle's Elixir** — free daily CSVs since 2014, 12 rows/game, includes pick order. *Backbone.*
- **Leaguepedia** — SQL-like Cargo tables via `leaguepedia-parser`. *Post-spike role: supplement* —
  `gameInSeries` (series structure) from the cheap tier; player metadata via detail calls (Phases 4/7).
  Draft order no longer needs it: OE + verified weave rules reconstruct it (see spike outcome below).
- **gol.gg** — scrape as supplement / cross-validation only (no official API).
- **Riot Data Dragon** — static champion attributes (the fixed `v_attr`). *Required for gap 1.*
- **Riot API (soloQ)** — *first-class source for Phase 7.* Two roles: (i) **variance reduction** —
  millions of games give low-noise champion/synergy/counter estimates and stable embeddings that pro
  data is too small to support; (ii) **player histories** — real individuals live in soloQ, so this is
  where player representations are learned *and* where the runtime op.gg input comes from. Note: soloQ
  win-rate is **not** an optimality signal (it rewards solo-carry/forgiving champions); coordinated
  optimality comes from the **pro** win label. Also hosts the live **LCU** demo.
  *Register the personal API key in W1* (it's instant, and soloQ meta stats may be needed earlier than
  Phase 7 if pro-only meta features prove too noisy); the production-key application is a separate,
  slower process — file it when Phase 7 approaches.

**Reality check to run FIRST (before any modeling):** count games per patch in Oracle's Elixir.
The meta shifts every patch and you cannot naively pool 10 years, so your *effective per-meta sample
size* is the number that constrains every modeling choice. This is why the fixed/meta split matters —
it shares statistical strength across patches.

**Second reality check — fearless data is scarce and recent.** Hard fearless only exists from ~2025
(soft from LPL 2024), so fearless *series* data spans a handful of patches at most. This compounds the
small-data problem and makes the fixed-attribute generalization (gap 1) and soloQ pretraining (Phase 7)
even more load-bearing for the fearless modeling. Note soloQ has **no** native fearless format, so the
series/fearless signal is pro-only and rare — count fearless series per patch early, like games/patch.

**Third reality check — entity-resolution spike (1 day, before committing to full ingest).** Cross-source
reconciliation (Oracle's Elixir ↔ Leaguepedia game / player / team IDs, renames, region quirks) is where
projects like this bleed weeks, and series reconstruction depends on it. Take **50 games** and try to join
them across both sources; see what breaks. Pre-committed fallback if reconciliation is ugly: Oracle's
Elixir alone gives picks + pick order (bans exist but unordered) — enough for everything except the
ordered-ban analysis. Decide *in advance* what gets dropped, not mid-crisis.

> **✅ Spike outcome (0.2b, done):** matching on **(date ±1 day, frozenset of 10 picked champion IDs)**
> achieved **15/15**; zero champion-name aliases needed (OE spelling = Data Dragon spelling). Team-*name*
> joins would have failed on **7/15** games (sponsor prefixes / mid-season renames: `Kiwoom DRX`↔`DRX`,
> `HANJIN BRION`↔`OKSavingsBank BRION`, …) — champion-set key vindicated; those 7 pairs seed `team_aliases`.
> Also verified: (i) `picksBans` at LP's detail tier matches the fixed tournament interleave exactly →
> **OE per-team order + format rules reconstructs the full 20-action draft** (weave rules verified);
> (ii) patch schemes differ (OE `15.06` double ↔ LP `'25.06'` string) — reconcile on suffix, store VARCHAR;
> (iii) identities live in LP's nested `.sources` (players incl. real name/country; team names);
> (iv) costs: bot-password auth mandatory; ~10–30 s/detail call (2 parallel requests each), connection
> drops under load, much faster off-peak → cached background scripts + exponential backoff, never interactive.
> **Verdict: OE = backbone incl. full draft order; Leaguepedia = supplement** — `gameInSeries` from the
> cheap skeleton tier, detail calls only where player metadata matters (Phases 4/7).

### 2.1 SQL schema (normalize on ingest) — ✅ implemented in `src/db/schema.sql` (11 tables)

```sql
champions(champion_id PK, name)                      -- keyed on Riot numeric ID (LP speaks IDs, OE names)
teams(team_id PK, name, league_region)               -- surrogate key assigned at ingest
team_aliases(alias PK, team_id FK)                   -- every spelling seen anywhere -> canonical team
                                                     --   (seeded by the 7 spike mismatch pairs)
players(player_id PK)                                -- v0: name-as-ID; player_aliases if it bites
series(series_id PK, best_of CHECK(1,3,5), team1_id FK, team2_id FK, event, date)
games(game_id PK, patch VARCHAR, blue_team_id FK, red_team_id FK, date,
      blue_team_won BOOL, league, series_id FK NULL, game_in_series NULL)
draft_actions(game_id FK, seq_index, action_type CHECK(pick,ban), side CHECK(blue,red),
              champion_id FK NULL, player_id FK NULL, role NULL,
              PRIMARY KEY (game_id, seq_index))      -- THE ordered draft, via verified weave rules
champion_attributes(champion_id PK/FK, info marks, partype, tag_primary/secondary,
                    ~20 Data Dragon base stats as DOUBLE, ddragon_version)  -- fixed v_attr snapshot
champion_meta(champion_id, patch, n_games, n_wins, n_bans,
              PK(champion_id, patch))                -- grain: (champion, patch); bans live here
champion_role_meta(champion_id, patch, role, n_games, n_wins,
              PK(champion_id, patch, role))          -- grain adds role; feeds Phase 6 q(r|c,π)
fearless_config(event, date_start, date_end NULL, mode CHECK(none,soft,hard),
              PK(event, date_start))                 -- hand-built adoption timeline
```

Design principles baked in (each traceable to a Phase-0 finding): **patch is VARCHAR** everywhere
(OE stores a double and drops trailing zeros: 15.10 → 15.1, which silently breaks cross-source joins);
**facts, not features** — store counts (`n_wins`, `n_games`), never rates; winrates, normalizations,
comfort scores are pipeline-computed (also why there's no `player_game` table: histories are a query
over `draft_actions` picks); **stable surrogate keys + alias tables** for identity that drifts across
sources/seasons; **one grain per table** (bans have no role → `champion_meta`, not `champion_role_meta`);
**derive, don't duplicate** (one `blue_team_won`, no redundant red twin; series winner queried, not stored).

`draft_actions` is the table pro data gives you and the Riot API does not — the linchpin for flex,
bans, and counterpick. `series` + `game_in_series` are the linchpin for **fearless**: from them you
derive, per (series, game), the **fearless-unavailable set** = champions picked in earlier games
(both teams for `hard`, same team only for `soft`). `fearless_mode` is not a data field anywhere —
you build the `fearless_config` lookup by hand from the public adoption timeline (LPL soft 2024 →
hard 2025; LCK Cup, LEC, LTA, First Stand/MSI/Worlds hard from 2025), keyed by event + date.

### 2.2 Anti-leakage rule for aggregated features (bake in from day one)

Any feature that is an **aggregate over games** (per-patch winrate / pickrate / banrate in
`champion_meta`; co-pick / matchup winrates behind relation-graph edges) must be computed **as-of**:

- **Meta features for patch $\pi_T$ come from patch $\pi_{T-1}$** (or, stricter, from games strictly
  before the current game's date). At test time on a future patch, the alternative — same-patch
  aggregates — is computed from the very games being evaluated (leakage), and at *real* draft time on a
  fresh patch those aggregates don't exist yet. As-of is also the honest deployment scenario.
- **Relation-graph edges are built from the training window only** (or time-decayed), never the full
  dataset, or the future-patch eval silently leaks.

Implement as date-parameterized SQL views / query functions (`meta_asof(champion, date)`,
`edges_asof(date)`) so leakage is structurally impossible rather than a discipline problem.
Retrofitting this after ingest is painful — it goes in `schema.sql`/`queries.py` from the start.

---

## 3. Architecture: one backbone, modular heads

### 3.0 v0 model in one place (block → concept → technique → data)

The v0 core is a **structured, additive, availability-conditioned value** — deliberately *not* a
monolithic black box, because the additive structure is what makes interpretability and fearless
generalization the *same* property. This table is the canonical reference (matches `architecture.svg`):

| Block | Concept | Technique (v0) | Data |
|:--------|:-----------|:--------------|:-----------------------|
| Champion input | id + attributes + meta | feature assembly | Data Dragon + match-aggregated meta |
| Relation graph | synergy · counter · role | typed edges from stats | co-pick / matchup win-rates (Oracle's + soloQ) |
| Player histories | champion pool / form | sequence of past games | Riot API · op.gg (soloQ) |
| Champion encoder | fixed ⊕ meta split | embedding + MLP + gate | — |
| Relation GNN | relational embeddings | R-GCN / GAT (PyG) | — |
| Player encoder | history → `z_p` | **Transformer** (set/seq) | — |
| Primitives | base, syn, ctr (vuln ≡ ctrᵀ) | bilinear / small-MLP scorers | — |
| Archetypes | soft champion clusters | clustering / prototype head | — |
| **Value `V(c\|A)`** | additive + exposure | **deterministic combiner** | — |
| Available set `A` | feasible + fearless-consumed | mask (LCU live at inference) | series/draft state |
| WP head | trains the primitives | logistic / FM · BCE loss | pro outcomes |
| Recommend / Ban / Explain | read-outs of `V` | argmax / Δ / term attribution | — |

The value:

$$\begin{aligned}
V(c \mid \text{allies},\text{enemies},A) \;=\;\; & \text{base}(c\mid\pi) \;+\; \sum_{a\in\text{allies}}\text{syn}(c,a) \\
&+\; \sum_{e\in\text{enemies}}\text{ctr}(c,e) \;-\; \text{exposure}(c\mid A)
\end{aligned}$$

$$\text{exposure}(c\mid A) \;=\; \operatorname*{softmax}_{\,r\in A_{\text{enemy}}}\; w_r\,\text{vuln}(c,r), \qquad \text{vuln}(c,r) \;\equiv\; \text{ctr}(r,c) \qquad(\text{best \emph{available} answer to } c)$$

**`vuln` is not a separate primitive — it is `ctr` read in transpose.** This is deliberate: the WP loss
only flows gradients through base/syn/ctr (exposure appears in the recommendation read-out, not the
training objective), so a free-standing `vuln` scorer would never be trained. Defining
$\text{vuln}(c,r)\equiv\text{ctr}(r,c)$ means exposure is *derived* from a trained primitive with zero
extra parameters, and tightens the fearless claim: *the same trained counter primitive, read in reverse
and conditioned on availability*.

**Weights $w_r$:** uniform in v0. Once the enemy pick-likelihood head exists (Phase 4), set
$w_r \propto p(\text{enemy picks } r)$ — an unweighted softmax over all of $A_\text{enemy}$ overweights
champions the enemy would never pick (wrong role, in no one's pool). This *unifies* the ban module and
the exposure operator into one mechanism (see §3.6).

`A` enters **only here**, not in the encoders or primitives — that separation is what lets you train
primitives without fearless and test the read-out on it (see §3.8). Any learned residual on top must
stay availability-agnostic so it can't memorize fearless.

### 3.1 Champion encoder — fixed/meta decomposition (gap 1, from `v_attr`)

$$z_c \;=\; e_c \;+\; z_{\text{fix}}(a_c) \;+\; g\cdot z_{\text{meta}}(c,\pi)$$

where $e_c$ is the patch-invariant identity embedding; $z_{\text{fix}}(a_c)$ is an MLP over intrinsic
attributes (range, damage type, CC, mobility, tags) that **generalizes across patches**; and
$z_{\text{meta}}(c,\pi)$ is patch-conditioned (winrate/pickrate/banrate, buff/nerf flags, per-patch
vector), gated by $g$.
Claim to prove: hold out a **future patch**; the fixed part places new/reworked champions sensibly
where an ID-only model cannot.

**Small-N discipline (per-patch pro N will be a few hundred games at best):**
- `base(c|π)` **flows through $z_c$** (a small head on the champion encoding) — never a free
  (champion, patch) parameter table, or the model overfits exactly where the fixed/meta split was
  supposed to save it.
- Raw `champion_meta` stats (winrate etc. on ~tens of pro games per champ per patch) are mostly noise —
  apply **empirical-Bayes shrinkage** toward the previous patch's value / a global prior before they
  enter $z_{\text{meta}}$ (shrinkage weight $\propto n_{\text{games}}$). If pro-only meta features stay
  too noisy even shrunk, soloQ aggregates are the fallback (personal API key registered W1).

### 3.2 Player encoder (player-conditioning)
$z_p = \text{PlayerEncoder}(\text{history}_p)$ — transformer/set over recent games (champion, role,
result, patch). Captures champion pool + form + role flexibility. (DraftRec's player network is the
reference.) **Trained on soloQ histories** and shared across domains — see §6 (Phase 7) for the
train/inference consistency rule (at runtime you only have op.gg/soloQ histories, so pros must also be
represented via their soloQ accounts during pro fine-tuning).

### 3.3 WP backbone — structured spine + black-box antagonist (BOTH ship in Phase 1)

**(a) Structured spine (the model).** The WP head is the additive value of §3.0 read team-vs-team —
$P(\text{blue wins})$ is a logistic / factorization-machine readout of
$\sum \text{base} + \sum \text{syn} - \sum \text{ctr}$ over the two lineups, trained with BCE on
outcomes. This trains the primitives and stays interpretable + fearless-generalizable. Everything
(recommend / ban / explain) reads out of this.

**(b) Set-Transformer (the antagonist — not an upgrade, a *baseline*).** Tokenize 10 slots
$\text{token}_i = z_{c_i} \oplus z_{p_i} \oplus \text{role} \oplus \text{side} \oplus \text{draftpos}$,
run a set/sequence Transformer → per-team pooling → $P(\text{blue wins})$. Permutation-equivariant
within team (tags, not raw order); draft-step positional encoding gives counterpick awareness.
**Its role:** the headline experiment (§3.8) needs an *identically-trained black-box* that sees the same
data and the same mask but has no availability-conditioned structure — this is it. Build it in Phase 1
alongside (a); it also serves as a raw-fit ceiling (if the additive spine trails it badly on plain WP
accuracy, the primitives are underfit).

Route *recommendation* through the structured value regardless, so generalization comes from the
read-out, not the backbone. If later the additive spine needs extra expressivity, an
availability-agnostic learned residual on top of (a) is the sanctioned upgrade path — never routing
recommendations through (b).

### 3.4 Recommendation read-out (the live use)
At current slot for player $p$, role $r$, feasible set $F$:
$\text{recommend} = \arg\max_{c\in F}\, \mathbb{E}[\text{WP}\mid \text{slot}\leftarrow c]$. Greedy first;
one-step opponent reply → shallow lookahead is stretch.
**$F$ excludes the fearless-consumed set** (champions played earlier in the series) in addition to
this game's picks/bans — see §3.8.

### 3.5 Relation graph + archetypes (gap 4, the interpretability layer)
Static graph: nodes = champions; typed edges = **synergy** (co-pick winrate lift), **counter**
(cross-team matchup winrate), **shared-role**. Small GNN (PyTorch Geometric) → embeddings whose
edge/attention weights *are* the explanation. Cluster embeddings → **archetypes** (engage, poke,
scaling carry, enchanter, dive…) → enables strategy-level recommendation ("you need a frontline
engager") and the global archetype map (your visual artifact).

### 3.6 Bans — player-conditioned denial (gap 3, from dual-pooling idea)

$$\text{BanValue}(c) \;=\; \mathbb{E}\!\left[\text{WP}_{\text{us}}\mid c\text{ available to enemy}\right] \;-\; \mathbb{E}\!\left[\text{WP}_{\text{us}}\mid c\text{ banned}\right]$$

Weight "available" by each enemy player's probability of picking $c$ (from history) $\times$ their
strength with it. High-value ban = champion an enemy player both loves and is strong on. Pro data makes
this signal strong (pro bans are surgically targeted).

**Unification:** the same pick-likelihood head supplies the weights $w_r$ in the exposure operator
(§3.0) — bans and exposure are one mechanism ("what is the opponent realistically going to do with what's
available?") applied in two directions. One head, two read-outs; a nicer paper story and less code.
Note the eval caveat up front: top-k accuracy vs actual pro bans measures *predictable* bans, not *good*
bans — report it as a sanity check, and let the WP-delta denial case study carry the argument.

### 3.7 Flex / latent role (gap 2, from `flex_uncertain`) — if time
Model role as latent: $q(r\mid c,\pi)$ = distribution over roles $c$ is played in this patch; team
encoder marginalizes over assignments. Bonus original metric: **flex value** = entropy of $q$, i.e.
how much a flex pick degrades opponent counterpick ability. Few works measure this. *Fearless amplifies
this:* with A-tier picks drafted away mid-series, flex/role-swing picks are how teams avoid being
cornered, so the flex module's value rises under fearless.

### 3.8 Fearless / series-state module (gap 6, from `hard-deletion (Fearless)`)
Fearless makes the draft a **series-level** problem: a champion *played* in an earlier game is locked
for the rest of the Bo3/Bo5 (`hard` = both teams; `soft` = same team only), stacking on the normal
10-ban phase. Two distinct things, and only the second needs fearless data:

**(A) Within-game value under a shrunken pool — generalizes WITHOUT fearless data.** This is the
"concepts not data" core. Fearless removes champions from `A`; the `exposure(c|A)` operator (§3.0) then
*computes* the consequence — when `c`'s usual answers are consumed, `exposure` drops and `V(c)` rises,
by construction, never memorized. So the primitives train on standard/soloQ data and the
availability-conditioned read-out is correct on fearless states. **Make `exposure` archetype-level**
(is there an available *answer archetype*, not just a single champion?) so it captures compositional
counterplay — this is why the archetype layer (§3.5) is load-bearing, not decoration. Mask correctness
(removing the consumed set from `F`) is the cheap prerequisite and ships in the core spine.

**(B) Cross-game pool management — genuinely needs fearless data / search (Phase 5 + stretch).** Saving
a pick for the decider, baiting the enemy into burning a comfort — these are *series-level* decisions
the within-game operator can't express. Model the depleting pool as series state: `game_in_series`,
score, `fearless_mode`, and a **dual-pooled consumed summary** (our-consumed vs their-consumed — the
original draft's dual-pooling idea, now justified). Remaining-pool player conditioning: a player's
comfort is relative to what's *left*, so a depleted one-trick reads as weaker and more predictable.
Full multi-game series search / RL is **stretch** (Phase 8).

**Headline experiment (the paper's centerpiece) — metrics defined UP FRONT, because "the black-box
fails" must be measurable.** Train every primitive on **non-fearless** data only; the claim is that the
availability-conditioned read-out elevates exactly the picks whose answers are consumed, where the
identically-trained black-box set-Transformer (§3.3b, same data, same mask) does not. Actual pro picks
in fearless games are a *confounded* label (pros adapt too) and fearless data is scarce, so the eval has
a primary result that needs **zero fearless data** plus confirmations on the real thing:

1. **Synthetic counter-consumption probe (PRIMARY figure — needs no fearless data).** Take real
   non-fearless drafts; artificially remove a champion $c$'s top-$k$ counters from $A$; measure
   $\Delta V(c)$ in the structured model vs $\Delta \widehat{WP}$-attribution in the black-box.
   Prediction: the structured model responds monotonically in $k$ (exposure drops by construction);
   the black-box, whose function never conditions on $A$ beyond the hard mask, does not. Dose-response
   curve = the figure.
2. **Stratified rank agreement (real fearless states, confirmation).** Rank correlation between model
   recommendation and actual pro picks, *stratified by whether the pick's usual counters were consumed*.
   The structured model's advantage should concentrate in the consumed stratum.
3. **Late-series calibration (real fearless states, confirmation).** WP Brier/ECE broken down by
   `game_in_series` — games 4–5 are where pools are most depleted and where availability-conditioning
   should pay.

That demonstrates learned *concepts*, not memorized meta; fearless data becomes confirmation +
calibration, which dissolves the scarce-data worry. The champion-diversity-per-series figure (§4) is the
Riot-facing result. Note the probe (1) only needs trained primitives + exposure, so a v0 of it runs as
early as **Phase 3** — don't wait for Phase 5.

---

## 4. Evaluation (this is what makes it a paper, not a demo)

- **Splits:** train ≤ patch T, validate T+1, test T+2+. NEVER random splits (leaks the meta).
  Report per-future-patch. **Feature leakage:** all aggregated features obey the as-of rule (§2.2) —
  meta features from the *previous* patch, relation edges from the training window only.
- **WP model:** accuracy, AUC, and **calibration (Brier / ECE)** — a recommender's WP must be meaningful.
- **Recommendation:** top-k accuracy (is the actually-picked champion ranked high?) AND predicted-WP
  uplift of recommended vs actual (since actual pick ≠ optimal pick). Beat both priors
  (meta tier-list, player-comfort) and a re-implemented DraftRec-style baseline.
- **Fixed/meta ablation:** cross-patch generalization — fixed-attribute model degrades gracefully on
  unseen champions vs ID-only model that can't represent them.
- **Bans:** top-k ban accuracy (predict actual pro bans) **as a sanity check only** — it measures
  *predictable* bans, not *good* bans; the WP-delta denial case study carries the argument.
- **Hybrid ablation (Phase 7):** pro-only vs soloQ-pretrained→pro-fine-tuned. This directly measures
  what the hybrid buys (better embeddings? better cold-start? better calibration on rare matchups?).
  Also check **domain/patch separability** — soloQ and pro don't share patch timing exactly, so verify
  the domain variable isn't silently absorbing patch effects (e.g. hold domain fixed, vary patch).
- **Fearless — centerpiece (metrics fixed in §3.8):** (0) **synthetic counter-consumption probe** —
  the primary, fearless-data-free figure (dose-response of $\Delta V$ vs # counters removed, structured
  vs black-box); (i) sanity — recommendations must never name a consumed champion (mask is hard, but
  verify); (ii) does series-state conditioning help? compare WP/recommendation with vs without the
  consumed-pool summary, broken down by `game_in_series`; (iii) **stratified rank agreement** on real
  fearless states (advantage should concentrate where a pick's counters were consumed);
  (iv) **late-series calibration** — Brier/ECE by `game_in_series`; (v) **diversity metric** — champion
  diversity per series, the exact thing Riot tracked when justifying fearless, a compelling figure;
  (vi) recency split — train on earlier 2025 series, test on later ones (doubles as a stress test).
- **Interpretability:** synergy/counter attribution examples + archetype-map viz + one reproduced
  pro-draft case study.

---

## 5. Tech stack (also: your stated learning goals)

- **DB:** SQLite or DuckDB for dev (zero-setup, real SQL, DuckDB reads CSVs directly). Postgres if you
  want the industry-standard resume line. — *this is the SQL/data-engineering practice.*
- **ETL:** Python + polars (or pandas), `leaguepedia-parser`, requests/bs4 for gol.gg.
- **ML:** PyTorch + PyTorch Geometric (GNN). PyTorch Lightning (optional, cuts boilerplate).
- **MLOps:** Hydra (configs) + Weights & Biases (experiment tracking) — good repo hygiene, looks good.
- **Compute:** these models are tiny (10 tokens, ~170-champion vocab). A single GPU or even CPU is fine.
  The hard parts are data + non-stationarity + eval design, not scale.

### Repo layout
```
lol-draft/
  data/                      # raw csvs + db file
  src/
    etl/                     # ingest_oracle.py, ingest_leaguepedia.py, scrape_golgg.py,
                             #   ingest_riot_soloq.py, build_db.py
    db/                      # schema.sql, queries.py
    data/                    # dataset.py (PyTorch Dataset), splits.py (future-patch splitter),
                             #   domains.py (soloQ vs pro domain tagging)
    models/
      champion_encoder.py    # fixed/meta (shared across domains)
      player_encoder.py      # soloQ-trained, shared across domains
      relation_graph.py      # GNN + archetypes
      wp_model.py            # backbone (domain-conditioned head)
      heads/                 # ban_head.py, flex.py, recommend.py
    train/                   # train_soloq.py (Stage A), train_pro.py (Stage B), hydra configs
    eval/                    # metrics.py, future_patch_eval.py
    demo/                    # lcu_client.py (stretch)
  notebooks/                 # EDA, archetype viz
  paper/                     # short writeup
  README.md
```

---

## 6. Hybrid soloQ ↔ pro (best of both worlds — Phase 7)

**Goal:** combine soloQ's statistical mass with pro's coordinated value and draft structure, through
**shared encoders** that both domains train, meeting at the champion and player representations.

### 6.1 What each domain actually contributes (correct the framing)
- **SoloQ is *not* the optimality signal.** SoloQ win-rate rewards solo-carry, forgiving champions and
  uncoordinated play; "optimal" in coordinated play can differ sharply. So soloQ ≠ optimality.
- **SoloQ gives:** (i) *low-variance* champion / synergy / counter estimates → stable champion encoder
  and relation graph (pro data is too small for this); (ii) *player histories* for the player encoder,
  both at train time and at inference (op.gg).
- **Pro gives:** the *coordinated-optimality* win label + the only place draft **structure** exists
  (pick/ban order, flex, targeted bans, counterpick).
- **The seam:** the champion encoder and the player encoder are **shared**; domain (soloQ vs pro) is
  just another context variable alongside patch, carried by a **domain token**.

### 6.2 Training procedure (two-stage, preferred)
- **Stage A — soloQ.** Train champion encoder + relation-graph GNN + player encoder against a *soloQ*
  WP head. No draft order needed (soloQ has none): 10 champions + players + roles → win. Large data →
  stable, well-conditioned embeddings.
- **Stage B — pro.** Initialize all three encoders from Stage A; train the **order-aware draft
  backbone + ban head + flex module** against a *pro* WP head, with a domain token. Recommendation and
  bans read out of the **pro** head (coordinated value), personalized through soloQ-trained player reps.
- **Guard against catastrophic forgetting:** the pro set is tiny and can distort the good soloQ
  embeddings. Use a light **soloQ-replay regularizer** in Stage B (mix in soloQ batches / freeze-then-
  thaw encoders / small LR on shared params).
- **Alternative — one-stage multitask:** shared encoders, two heads, sample both domains. Avoids
  forgetting but the pro signal drowns unless you **oversample pro** or up-weight its loss. Start
  two-stage; switch only if forgetting actually shows up.

### 6.3 Train/inference consistency rule (the critical catch)
At inference you have **only soloQ histories** (the user's op.gg). Therefore in Stage B you must
represent pro players **via their soloQ accounts**, through the *same* soloQ-trained player encoder —
**not** via pro-game stats. Otherwise the pro backbone learns to expect a richer player representation
than any real user can supply, and silently degrades in deployment. Pros have soloQ accounts; use them.
This is *why* the player encoder is trained on soloQ in the first place — it's the only representation
available at runtime.

### 6.4 The op.gg product flow (inference-time conditioning, not weights)
The shipped product is **pre-trained**. A user supplies 10 op.gg profiles (5 ally, 5 enemy); the player
encoder maps each history → a representation that **conditions** the live recommendation. This is a
runtime input, not per-user training and not literally model weights. It generalizes to unseen players
because the encoder learned the mapping *history → representation* (same as DraftRec). This is where
"a player's own stats are the strongest factor" gets cashed in.

### 6.5 Costs & risks (go in clear-eyed)
- **Two pipelines:** champion IDs align via Data Dragon, but patches, roles, and player IDs across
  soloQ and pro need reconciling.
- **Transfer machinery** + the 5 gap modules on top = real added effort.
- **Domain/patch confound:** soloQ and pro patch timing differ → domain and patch can entangle; test
  separability (see Eval §4).
- **Mitigation / build order:** ship the **pro-only spine first** (trains, evaluates, demos end-to-end),
  then add soloQ as an *additive* pretraining layer underneath. The hybrid becomes an upgrade you bolt
  on, not a prerequisite — and it gives the clean ablation pro-only vs soloQ-pretrained→pro.

---

## 7. Timeline (part-time, ~12+ weeks — a guide, expect slippage)

- **W1–3:** Data pipeline + DB + EDA. **Day 1–2: register Riot personal API key + run the 50-game
  entity-resolution spike (§2)** — its outcome decides the Leaguepedia commitment. Confirm
  pick/ban-order columns; count games/patch. As-of aggregation views (§2.2) go into the schema now.
  Reconstruct **series** (`series_id`, `game_in_series`) + build the `fearless_config` lookup; count
  fearless series/patch. *(Most of the SQL learning lives here — don't rush it.)*
- **W4–5:** WP backbone (**both** the additive spine and the black-box set-Transformer antagonist,
  §3.3) + priors + eval harness + **fearless-correct mask** (cheap). First baselines.
- **W6–7:** Fixed/meta decomposition + future-patch ablation. **Contribution #1.**
- **W8–9:** Relation graph + archetypes + interpretability viz. **Contribution #2.**
- **W10–11:** Player-conditioned bans. **Contribution #3 (the hook).**
- **W12:** Writeup + demo polish for the pro-only spine (first shippable milestone; already
  fearless-*legal* via the mask).
- **Phase 5 — Fearless series strategy:** consumed-pool dual-summary, remaining-pool player
  conditioning, pool-management + diversity eval. **Contribution #5** (the most novel — no prior model
  does it).
- **Phase 6 — Flex / latent role** (gap 2); pairs naturally with Phase 5 (flex matters more under fearless).
- **Phase 7 — Hybrid soloQ↔pro:** soloQ pipeline → Stage A pretraining → Stage B pro fine-tuning with
  replay guard → hybrid ablation. **Contribution #4.**
- **Phase 8 — Stretch:** counterpick lookahead, multi-game series search, live LCU demo.

Non-negotiable core = W1–12 (pro-only, fearless-legal). Phases 5–8 are additive upgrades on a spine
that already works.

---

## 8. Paper outline (short / lightning-talk style)

1. **Problem:** draft as perfect-info sequential game; why pro/ordered data + patch non-stationarity.
2. **Related work:** DraftArtist & JueWuDraft (WP+search, player-agnostic), NeuralAC (synergy, no
   players), DraftRec (player-conditioned, soloQ, black-box, single-patch). Your delta in one table —
   and note **all predate fearless draft**, so none model the series-level lockout.
3. **Method:** WP backbone; fixed/meta decomposition; relation-graph + archetypes; ban denial; flex;
   fearless series-state module; hybrid soloQ↔pro with shared encoders (soloQ = coverage/variance-
   reduction, **not** optimality).
4. **Experiments:** future-patch eval; ablations (fixed/meta, **fearless series-state**, **pro-only vs
   hybrid**); vs priors + DraftRec baseline; champion-diversity figure; interpretability case study.
5. **Demo:** archetype map + per-pick explanations on a live fearless series (+ LCU if reached).
6. **Limitations:** small per-patch data; scarce/recent fearless data; pro ≠ soloQ; actual-pick ≠
   optimal-pick label noise; single-game WP ≠ multi-game series optimum; domain/patch confound.

---

## 9. First concrete step

Download **one** Oracle's Elixir CSV, load it (DuckDB: `SELECT * FROM 'oe_2024.csv' LIMIT 50`),
and answer three questions before writing any model code:
1. Confirm the pick-order and ban columns exist and how they're laid out across the 12 rows/game.
2. Count distinct games **per patch** — your effective per-meta sample size.
3. How many distinct (champion, patch) pairs appear — this sizes the meta-embedding table.
4. Then the **entity-resolution spike**: join 50 of those games against Leaguepedia and see what
   breaks, *before* committing to the full dual-source ingest.

Those numbers determine whether you lean harder on the fixed-attribute generalization (small data) or
can afford richer per-patch meta embeddings (large data) — and whether Leaguepedia is a first-class
source or a supplement.
