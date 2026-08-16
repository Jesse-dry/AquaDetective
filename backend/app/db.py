"""SQLite 连接与建表。"""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,            -- source|segment|confluence|outlet
  x REAL NOT NULL, y REAL NOT NULL,
  flow REAL NOT NULL,            -- m3/s
  velocity REAL NOT NULL,        -- m/s
  k REAL NOT NULL DEFAULT 0.1    -- 降解系数 1/d
);
CREATE TABLE IF NOT EXISTS edges (
  from_node TEXT NOT NULL REFERENCES nodes(id),
  to_node   TEXT NOT NULL REFERENCES nodes(id),
  distance_m REAL NOT NULL,
  PRIMARY KEY (from_node, to_node)
);
CREATE TABLE IF NOT EXISTS stations (
  id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES nodes(id),
  interval_min INTEGER NOT NULL DEFAULT 15,
  indicators TEXT NOT NULL       -- JSON 数组
);
CREATE TABLE IF NOT EXISTS enterprises (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  industry TEXT NOT NULL,
  node_id TEXT NOT NULL REFERENCES nodes(id),
  discharge_pattern TEXT NOT NULL -- JSON
);
CREATE TABLE IF NOT EXISTS fingerprints (
  enterprise_id TEXT PRIMARY KEY REFERENCES enterprises(id),
  spectrum TEXT NOT NULL,        -- JSON 荧光峰 [{lex,lem,amp,sigma}]
  pollutants TEXT NOT NULL       -- JSON 归一化污染物比例向量
);
CREATE TABLE IF NOT EXISTS readings (
  station_id TEXT NOT NULL REFERENCES stations(id),
  ts INTEGER NOT NULL,
  indicator TEXT NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY (station_id, ts, indicator)
);
CREATE INDEX IF NOT EXISTS idx_readings_station ON readings(station_id, ts);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  station_id TEXT NOT NULL,
  indicators TEXT NOT NULL,      -- JSON 数组
  onset_ts INTEGER NOT NULL,
  severity TEXT NOT NULL,        -- low|medium|high
  etype TEXT NOT NULL,           -- sudden|periodic|gradual
  truth_source TEXT,             -- Ground Truth 企业 id（演示验证用，可为空）
  status TEXT DEFAULT 'open'     -- open|investigating|resolved
);
CREATE TABLE IF NOT EXISTS investigations (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(id),
  started_at INTEGER NOT NULL,
  conclusion TEXT,               -- JSON
  status TEXT DEFAULT 'running'  -- running|resolved|failed
);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def db_is_empty(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS c FROM nodes").fetchone()
    return row["c"] == 0
