import os
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL")

class DB:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        # Application SQL uses SQLite-style question-mark placeholders.
        # Translate them to psycopg's parameter style.
        sql = sql.replace("?", "%s")
        return self.conn.execute(sql, params)

    def close(self):
        self.conn.close()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
    return DB(conn)

@contextmanager
def transaction(conn):
    # Close any implicit read transaction before starting the write transaction.
    conn.commit()
    conn.execute("BEGIN")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    conn = get_db()
    statements = [
        """CREATE TABLE IF NOT EXISTS evaluations(
          evaluation_id TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL,
          input_digest TEXT NOT NULL, verifier_jwk TEXT NOT NULL,
          propose_response TEXT NOT NULL, state TEXT NOT NULL,
          commit_fingerprint TEXT, commit_response TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS dossier_cache(
          dossier_id TEXT NOT NULL, content_fingerprint TEXT NOT NULL,
          proposal_json TEXT NOT NULL,
          PRIMARY KEY(dossier_id, content_fingerprint)
        )""",
        """CREATE TABLE IF NOT EXISTS proposals(
          evaluation_id TEXT NOT NULL REFERENCES evaluations(evaluation_id),
          dossier_id TEXT NOT NULL, call_id TEXT NOT NULL, action TEXT NOT NULL,
          proposal_digest TEXT NOT NULL, proposal_json TEXT NOT NULL,
          PRIMARY KEY(evaluation_id,dossier_id),
          UNIQUE(evaluation_id,call_id)
        )""",
        """CREATE TABLE IF NOT EXISTS receipts(
          evaluation_id TEXT NOT NULL REFERENCES evaluations(evaluation_id),
          dossier_id TEXT NOT NULL, call_id TEXT NOT NULL,
          receipt_id TEXT NOT NULL UNIQUE, receipt_json TEXT NOT NULL,
          PRIMARY KEY(evaluation_id,dossier_id)
        )"""
    ]
    try:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
