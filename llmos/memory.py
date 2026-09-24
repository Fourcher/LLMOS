"""Long-term memory on the encrypted volume: preferences, facts, transcript,
scheduled tasks and permission grants. One SQLite file."""
import re
import sqlite3
import threading
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS prefs(key TEXT PRIMARY KEY, value TEXT, updated_at REAL);
CREATE VIRTUAL TABLE IF NOT EXISTS facts USING fts5(text, created_at UNINDEXED);
CREATE VIRTUAL TABLE IF NOT EXISTS transcript USING fts5(role UNINDEXED, text, ts UNINDEXED);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, next_run REAL, cron TEXT, request TEXT,
    last_run REAL, last_result TEXT, enabled INTEGER DEFAULT 1, created_at REAL);
CREATE TABLE IF NOT EXISTS grants(tool TEXT PRIMARY KEY, granted_at REAL);
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, ts REAL, text TEXT, seen INTEGER DEFAULT 0);
"""


class Memory:
    def __init__(self, path=None):
        self.path = path or config.dpath("memory.db")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript(SCHEMA)

    def q(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    # preferences
    def set_pref(self, key, value):
        key = re.sub(r"\s+", "_", key.strip().lower())[:60]
        self.q("INSERT INTO prefs VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
               key, str(value)[:300], time.time())
        return key

    def forget(self, key):
        k = re.sub(r"\s+", "_", key.strip().lower())
        n = len(self.q("SELECT 1 FROM prefs WHERE key=?", k))
        self.q("DELETE FROM prefs WHERE key=?", k)
        if not n:
            rows = self.q("SELECT rowid FROM facts WHERE facts MATCH ?", fts_query(key))
            for (rid,) in rows:
                self.q("DELETE FROM facts WHERE rowid=?", rid)
            n = len(rows)
        return n

    def prefs(self):
        return self.q("SELECT key, value FROM prefs ORDER BY updated_at")

    def pref(self, key, default=None):
        r = self.q("SELECT value FROM prefs WHERE key=?", key)
        return r[0][0] if r else default

    # facts
    def add_fact(self, text):
        self.q("INSERT INTO facts(text, created_at) VALUES(?,?)", text[:500], time.time())

    def search(self, query, n=5):
        fq = fts_query(query)
        if not fq:
            return []
        try:
            return [r[0] for r in self.q("SELECT text FROM facts WHERE facts MATCH ? ORDER BY rank LIMIT ?", fq, n)]
        except sqlite3.OperationalError:
            return []

    def search_transcript(self, query, n=8):
        fq = fts_query(query)
        if not fq:
            return []
        try:
            return self.q("SELECT ts, role, text FROM transcript WHERE transcript MATCH ? ORDER BY rank LIMIT ?", fq, n)
        except sqlite3.OperationalError:
            return []

    def log(self, role, text):
        self.q("INSERT INTO transcript(role, text, ts) VALUES(?,?,?)", role, text[:4000], time.time())

    def prune(self, days=30):
        self.q("DELETE FROM transcript WHERE ts < ?", time.time() - days * 86400)

    def wipe_transcript(self):
        self.q("DELETE FROM transcript")

    # grants
    def grant(self, tool):
        self.q("INSERT OR REPLACE INTO grants VALUES(?,?)", tool, time.time())

    def grants(self):
        return [r[0] for r in self.q("SELECT tool FROM grants ORDER BY tool")]

    def revoke(self, tool=None):
        if tool:
            self.q("DELETE FROM grants WHERE tool=?", tool)
        else:
            self.q("DELETE FROM grants")

    # notes shown at the next prompt
    def note(self, text):
        self.q("INSERT INTO notes(ts, text) VALUES(?,?)", time.time(), text[:1000])

    def unseen_notes(self):
        rows = self.q("SELECT id, ts, text FROM notes WHERE seen=0 ORDER BY ts")
        if rows:
            self.q("UPDATE notes SET seen=1 WHERE seen=0")
        return rows


def fts_query(text):
    words = re.findall(r"\w{3,}", text.lower())
    stop = {"the", "and", "for", "you", "what", "that", "this", "with", "are", "was", "how", "who", "can",
            "please", "tell", "about", "does", "did", "have", "has", "from", "into", "your", "mine", "my"}
    words = [w for w in words if w not in stop][:12]
    return " OR ".join('"%s"' % w for w in words)


class RamMemory(Memory):
    """Used before the data volume is unlocked or when running from RAM."""

    def __init__(self):
        super().__init__(":memory:")
