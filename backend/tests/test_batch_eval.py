"""Evaluation copies must include WAL data and reset mutations between rounds."""
import sqlite3
from contextlib import closing

from scripts.batch_eval import _copy_database


def test_backup_includes_wal_and_restores_round_baseline(tmp_path):
    source = str(tmp_path / "source.db")
    baseline = str(tmp_path / "baseline.db")
    target = str(tmp_path / "round.db")
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE readings (value REAL)")
        conn.execute("INSERT INTO readings VALUES (10)")
        conn.commit()
        # Keep source open so committed data still resides in the WAL.
        _copy_database(source, baseline)
        _copy_database(baseline, target)
        with closing(sqlite3.connect(target)) as round_conn:
            assert round_conn.execute("SELECT value FROM readings").fetchone()[0] == 10
            round_conn.execute("UPDATE readings SET value=90")
            round_conn.commit()
        _copy_database(baseline, target)
        with closing(sqlite3.connect(target)) as round_conn:
            assert round_conn.execute("SELECT value FROM readings").fetchone()[0] == 10
        assert conn.execute("SELECT value FROM readings").fetchone()[0] == 10
