"""Append-only audit trail of everything that happens to a proposal, in SQLite."""
import json
import sqlite3
from datetime import datetime, timezone


class Audit:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("""CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT, kind TEXT, t REAL,
            proposal_id TEXT, data TEXT, ts TEXT)""")
        self.db.commit()
        self.match_id: str | None = None

    def log(self, kind: str, t: float, proposal_id: str | None, data: dict) -> dict:
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        cur = self.db.execute(
            "INSERT INTO audit (match_id, kind, t, proposal_id, data, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (self.match_id, kind, round(t, 1), proposal_id, json.dumps(data, default=str), ts))
        self.db.commit()
        return {"id": cur.lastrowid, "match_id": self.match_id, "kind": kind, "t": round(t, 1),
                "proposal_id": proposal_id, "data": data, "ts": ts}

    def all(self, match_id: str | None = None) -> list[dict]:
        query = "SELECT id, match_id, kind, t, proposal_id, data, ts FROM audit"
        rows = self.db.execute(query + (" WHERE match_id = ?" if match_id else "") + " ORDER BY id",
                               (match_id,) if match_id else ()).fetchall()
        return [{"id": r[0], "match_id": r[1], "kind": r[2], "t": r[3], "proposal_id": r[4],
                 "data": json.loads(r[5]), "ts": r[6]} for r in rows]
