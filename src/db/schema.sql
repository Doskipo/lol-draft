-- schema.sql — LoL draft recommender database
-- Design decisions documented in docs/PROJECT_SPEC.md §2.1
-- Quirks discovered in notebooks/02_entity_spike.ipynb:
--   patch stored as VARCHAR (OE double drops trailing zeros: 15.10 -> 15.1)
--   champions keyed on Riot numeric ID (Leaguepedia speaks IDs, OE speaks names)

CREATE TABLE IF NOT EXISTS champions (
    champion_id  INTEGER PRIMARY KEY,   -- Riot's numeric ID (Data Dragon 'key')
    name         VARCHAR NOT NULL       -- display name, matches OE spelling
);




CREATE TABLE IF NOT EXISTS teams (
    team_id            INTEGER PRIMARY KEY,     -- surrogate key assigned at ingest; name variants resolved via team_aliases
    name               VARCHAR NOT NULL,        -- display name, may change between seasons although same team
    league_region      VARCHAR                  -- league which the team belongs to: LCK, LEC...
);


CREATE TABLE IF NOT EXISTS team_aliases (
    alias    VARCHAR PRIMARY KEY,              -- any spelling seen in any source
    team_id  INTEGER NOT NULL REFERENCES teams(team_id)
);


CREATE TABLE IF NOT EXISTS players (                  -- v0: name-as-ID; known limit (renames/collisions), player_aliases table if it bites
    player_id    VARCHAR PRIMARY KEY   
);


CREATE TABLE IF NOT EXISTS series (
    series_id   VARCHAR PRIMARY KEY,                                 
    best_of     INTEGER NOT NULL CHECK (best_of IN (1, 3, 5)),      -- best of 1, 3 or 5
    team1_id    INTEGER REFERENCES teams(team_id),                     -- id of one team
    team2_id    INTEGER REFERENCES teams(team_id),                      -- id of the other team
    event       VARCHAR,                                             -- LCK, LEC.. or other like MSI, Worlds, EWC... (the thing is its not the same as league in teams, since teams belong to a region not a competition). (advanced idea: NULL if its a scrim? for own teams developing this tool....)
    date        DATE NOT NULL
);
-- games point here via games.series_id; series contents are queried, not stored

CREATE TABLE IF NOT EXISTS games (
    game_id             VARCHAR PRIMARY KEY,                                -- id of the game
    patch               VARCHAR NOT NULL,                                         
    blue_team_id        INTEGER NOT NULL REFERENCES teams(team_id),
    red_team_id         INTEGER NOT NULL REFERENCES teams(team_id),                  -- id of the two teams
    date                DATE NOT NULL,
    blue_team_won       BOOLEAN NOT NULL,                                   -- booleans because for ml framework we will need it anyayways. We need to link the side to the team though, important
    league              VARCHAR,
    series_id           VARCHAR REFERENCES series(series_id),
    game_in_series      INTEGER
);



CREATE TABLE IF NOT EXISTS draft_actions (
    game_id             VARCHAR NOT NULL REFERENCES games(game_id),
    seq_index           INTEGER NOT NULL,                                          -- 1..20, global order via verified weave rules
    action_type         VARCHAR NOT NULL CHECK (action_type IN ('pick','ban')),
    side                VARCHAR NOT NULL CHECK (side IN ('blue','red')),
    champion_id         INTEGER REFERENCES champions(champion_id),                 -- NULL = forfeited ban
    player_id           VARCHAR REFERENCES players(player_id),                     -- NULL for bans
    role                VARCHAR,                                                   -- NULL for bans
    PRIMARY KEY (game_id, seq_index)
);


CREATE TABLE IF NOT EXISTS champion_attributes (
    champion_id             INTEGER PRIMARY KEY REFERENCES champions(champion_id),
    attack_mark             INTEGER NOT NULL,                           -- mark from 0 to 10 by Dragon
    defense_mark            INTEGER NOT NULL,                           -- mark from 0 to 10 by Dragon
    magic_mark              INTEGER NOT NULL,                           -- mark from 0 to 10 by Dragon
    difficulty_mark         INTEGER NOT NULL,                           -- mark from 0 to 10 by Dragon
    partype                 VARCHAR NOT NULL,                           -- blood well, mana, energy...
    -- here would be great to introduce what we talked about manually, cc, dash, global... these are VERY important i think
    tag_primary             VARCHAR NOT NULL,
    tag_secondary           VARCHAR,
    -- stats
    hp                      DOUBLE NOT NULL,
    hpperlevel              DOUBLE NOT NULL,
    mp                      DOUBLE NOT NULL,
    mpperlevel              DOUBLE NOT NULL,
    movespeed               DOUBLE NOT NULL,
    armor                   DOUBLE NOT NULL,
    armorperlevel           DOUBLE NOT NULL,
    spellblock              DOUBLE NOT NULL,
    spellblockperlevel      DOUBLE NOT NULL,
    attackrange             DOUBLE NOT NULL,
    hpregen                 DOUBLE NOT NULL,
    hpregenperlevel         DOUBLE NOT NULL,
    mpregen                 DOUBLE NOT NULL,
    mpregenperlevel         DOUBLE NOT NULL,
    crit                    DOUBLE NOT NULL,
    critperlevel            DOUBLE NOT NULL,
    attackdamage            DOUBLE NOT NULL,
    attackdamageperlevel    DOUBLE NOT NULL,
    attackspeed             DOUBLE NOT NULL,
    attackspeedperlevel     DOUBLE NOT NULL,
    ddragon_version         VARCHAR
);





CREATE TABLE IF NOT EXISTS fearless_config (
    event                   VARCHAR NOT NULL,              -- 'LCK 2025', 'MSI 2025'...
    date_start              DATE NOT NULL,
    date_end                DATE,                          -- NULL = still in force
    mode                    VARCHAR NOT NULL CHECK (mode IN ('none','soft','hard')),
    PRIMARY KEY (event, date_start)
);
-- hand-built from the public adoption timeline (spec §2.2); a game's mode is found
-- by matching its league/event + date against these ranges


CREATE OR REPLACE VIEW champion_meta AS
WITH picks AS (
    SELECT da.champion_id, g.patch,
           COUNT(*) AS n_games,
           SUM(CASE WHEN (da.side = 'blue') = g.blue_team_won THEN 1 ELSE 0 END) AS n_wins
    FROM draft_actions da
    JOIN games g USING (game_id)
    WHERE da.action_type = 'pick'
    GROUP BY da.champion_id, g.patch
),
bans AS (
    SELECT da.champion_id, g.patch, COUNT(*) AS n_bans
    FROM draft_actions da
    JOIN games g USING (game_id)
    WHERE da.action_type = 'ban' AND da.champion_id IS NOT NULL
    GROUP BY da.champion_id, g.patch
)
SELECT
    COALESCE(p.champion_id, b.champion_id) AS champion_id,
    COALESCE(p.patch,       b.patch)       AS patch,
    COALESCE(p.n_games, 0)                 AS n_games,
    COALESCE(p.n_wins,  0)                 AS n_wins,
    COALESCE(b.n_bans,  0)                 AS n_bans
FROM picks p
FULL OUTER JOIN bans b
  ON p.champion_id = b.champion_id AND p.patch = b.patch