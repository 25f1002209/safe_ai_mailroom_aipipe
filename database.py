import os, sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DATABASE_PATH", "data/mailroom.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

@contextmanager
def transaction(conn):
    conn.execute("BEGIN IMMEDIATE")
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
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS evaluations(
      evaluation_id TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL,
      input_digest TEXT NOT NULL, verifier_jwk TEXT NOT NULL,
      propose_response TEXT NOT NULL, state TEXT NOT NULL,
      commit_fingerprint TEXT, commit_response TEXT
    );
    CREATE TABLE IF NOT EXISTS dossier_cache(
      dossier_id TEXT NOT NULL, content_fingerprint TEXT NOT NULL,
      proposal_json TEXT NOT NULL, PRIMARY KEY(dossier_id, content_fingerprint)
    );
    CREATE TABLE IF NOT EXISTS proposals(
      evaluation_id TEXT NOT NULL, dossier_id TEXT NOT NULL, call_id TEXT NOT NULL,
      action TEXT NOT NULL, proposal_digest TEXT NOT NULL, proposal_json TEXT NOT NULL,
      PRIMARY KEY(evaluation_id,dossier_id),
      UNIQUE(evaluation_id,call_id),
      FOREIGN KEY(evaluation_id) REFERENCES evaluations(evaluation_id)
    );
    CREATE TABLE IF NOT EXISTS receipts(
      evaluation_id TEXT NOT NULL, dossier_id TEXT NOT NULL, call_id TEXT NOT NULL,
      receipt_id TEXT NOT NULL, receipt_json TEXT NOT NULL,
      PRIMARY KEY(evaluation_id,dossier_id),
      UNIQUE(receipt_id),
      FOREIGN KEY(evaluation_id) REFERENCES evaluations(evaluation_id)
    );
    """)
    conn.commit()
    conn.close()
