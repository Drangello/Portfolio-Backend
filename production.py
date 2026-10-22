"""Small persistent limiter for this single-VM deployment (no external service)."""
from contextlib import closing
import sqlite3
import time

from werkzeug.wrappers import Response


class LoopbackOnly:
    """Check the socket peer BEFORE ProxyFix rewrites REMOTE_ADDR."""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("REMOTE_ADDR") not in {"127.0.0.1", "::1"}:
            return Response(status=403)(environ, start_response)
        return self.app(environ, start_response)


def allow_request(path: str, address: str, ip_limit: int, global_limit: int) -> bool:
    """Fixed windows: five/IP/minute and thirty total/hour; count every POST.

    SQLite serializes updates across threads/processes. Unavailable storage fails
    closed in the caller. Old IP entries expire after an hour. The global cap
    bounds both SMTP work and database growth. No message content is stored.
    """
    now = int(time.time())
    windows = [("ip:" + address, now // 60, ip_limit), ("global", now // 3600, global_limit)]
    with closing(sqlite3.connect(path, timeout=2)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL, updated INTEGER NOT NULL)")
        db.execute("DELETE FROM limits WHERE updated < ?", (now - 3600,))
        counts = []
        for key, window, limit in windows:
            row = db.execute("SELECT window, count FROM limits WHERE key = ?", (key,)).fetchone()
            count = row[1] if row and row[0] == window else 0
            if count >= limit:
                return False
            counts.append(count + 1)
        for (key, window, _), count in zip(windows, counts):
            db.execute("INSERT OR REPLACE INTO limits VALUES (?, ?, ?, ?)", (key, window, count, now))
    return True
