"""SQLite storage for resumable Long Game reports."""

import json
import sqlite3
import time
from contextlib import closing, contextmanager


class LongGameStorage:
    def __init__(self, path, retain_reports=False):
        self.path = path
        self.retain_reports = retain_reports
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS long_game_jobs (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, inputs TEXT, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS long_game_checkpoints (
                    job_id TEXT NOT NULL REFERENCES long_game_jobs(id) ON DELETE CASCADE,
                    key TEXT NOT NULL, answer TEXT NOT NULL, PRIMARY KEY (job_id, key)
                );
            """)

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            yield db

    def save_state(self, job_id, job):
        state = {key: job[key] for key in ("status", "activity", "analysis", "as_of", "error", "resumable")
                 if key in job}
        with self.connection() as db:
            db.execute(
                "INSERT INTO long_game_jobs(id, state, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
                (job_id, json.dumps(state), time.time()),
            )

    def latest_job_id(self):
        with self.connection() as db:
            row = db.execute(
                "SELECT id FROM long_game_jobs ORDER BY CASE WHEN json_extract(state, '$.status') = 'running' "
                "OR json_extract(state, '$.resumable') = 1 THEN 0 ELSE 1 END, updated_at DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def completed_reports(self):
        with self.connection() as db:
            rows = db.execute(
                "SELECT id, json_extract(state, '$.as_of'), json_extract(state, '$.resumable') "
                "FROM long_game_jobs WHERE json_extract(state, '$.status') = 'completed' "
                "AND length(json_extract(state, '$.analysis')) > 0 ORDER BY updated_at DESC"
            ).fetchall()
        return [{"job_id": row[0], "as_of": row[1], "partial": bool(row[2])} for row in rows]

    def latest_completed_job_id(self):
        reports = self.completed_reports()
        return reports[0]["job_id"] if reports else None

    def read_state(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT state FROM long_game_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        state = json.loads(row[0])
        if state["status"] == "running":
            # Live jobs are served by the worker's in-memory registry.
            message = "The server restarted during analysis. Choose Resume to continue from the saved checkpoint."
            state.update(status="failed", resumable=True, error=message)
            state["activity"].append(message)
        return state

    def save_inputs(self, job_id, inputs):
        with self.connection() as db:
            db.execute("UPDATE long_game_jobs SET inputs=? WHERE id=?", (json.dumps(inputs), job_id))

    def load_work(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT inputs FROM long_game_jobs WHERE id=?", (job_id,)).fetchone()
            notes = dict(db.execute("SELECT key, answer FROM long_game_checkpoints WHERE job_id=?", (job_id,)))
        return (json.loads(row[0]) if row and row[0] else None), notes

    def save_checkpoint(self, job_id, key, answer):
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO long_game_checkpoints(job_id, key, answer) VALUES (?, ?, ?)",
                (job_id, key, answer),
            )

    def finish(self, job_id):
        with self.connection() as db:
            db.execute("UPDATE long_game_jobs SET inputs=NULL WHERE id=?", (job_id,))
            db.execute("DELETE FROM long_game_checkpoints WHERE job_id=?", (job_id,))

    def prune(self, active_ids):
        cutoff = time.time() - 7 * 86400
        placeholders = ",".join("?" for _ in active_ids) or "NULL"
        query = "DELETE FROM long_game_jobs WHERE updated_at < ?"
        if self.retain_reports:
            query += " AND coalesce(length(json_extract(state, '$.analysis')), 0) = 0"
        if active_ids:
            query += f" AND id NOT IN ({placeholders})"
        with self.connection() as db:
            db.execute(query, (cutoff, *active_ids))
