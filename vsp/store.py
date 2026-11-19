"""DuckDB storage. One file, committed back to the repo by the workflow."""
from __future__ import annotations

from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id            VARCHAR PRIMARY KEY,   -- sha1 of canonical URL
    url           VARCHAR NOT NULL,
    canonical_url VARCHAR NOT NULL,
    source        VARCHAR NOT NULL,
    title         VARCHAR NOT NULL,
    summary       VARCHAR,
    published_at  TIMESTAMP,
    fetched_at    TIMESTAMP NOT NULL,
    duplicate_of  VARCHAR                -- set when the title matches an earlier story
);

CREATE TABLE IF NOT EXISTS classifications (
    story_id        VARCHAR PRIMARY KEY,
    model           VARCHAR,
    prompt_version  VARCHAR,
    tier            VARCHAR,   -- core | adjacent | off_scope
    section         VARCHAR,   -- money_moves | launch_radar | regulation | exits_shutdowns | market_data | skip
    company         VARCHAR,
    country         VARCHAR,
    amount_text     VARCHAR,
    relevance       INTEGER,   -- 0–10
    headline        VARCHAR,
    one_line        VARCHAR,
    summary         VARCHAR,
    why_it_matters  VARCHAR,
    key_number      VARCHAR,
    leaves_vegan    BOOLEAN,
    classified_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_runs (
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    status      VARCHAR,   -- ok | error
    n_items     INTEGER,
    n_new       INTEGER,
    error       VARCHAR
);
"""


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con
