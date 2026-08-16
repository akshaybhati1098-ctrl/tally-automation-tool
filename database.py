import os
import time
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")

# Keep the application-side pool deliberately below Supabase's session limit.
# The pool is shared by all modules that import get_db_connection().
DB_POOL_MIN = max(1, int(os.getenv("DB_POOL_MIN", "1")))
DB_POOL_MAX = max(DB_POOL_MIN, int(os.getenv("DB_POOL_MAX", "5")))

_db_pool = None
_pool_init_lock = threading.Lock()
_pool_slots = threading.BoundedSemaphore(DB_POOL_MAX)


def _get_pool():
    global _db_pool
    if _db_pool is None:
        with _pool_init_lock:
            if _db_pool is None:
                _db_pool = ThreadedConnectionPool(
                    DB_POOL_MIN,
                    DB_POOL_MAX,
                    DATABASE_URL,
                    sslmode="require",
                    connect_timeout=10,
                )
    return _db_pool


class _PooledConnection:
    """Compatibility wrapper whose close() returns the connection to the pool."""

    def __init__(self, pool, connection, cursor_factory=None):
        self._pool = pool
        self._connection = connection
        self._cursor_factory = cursor_factory
        self._returned = False

    def cursor(self, *args, **kwargs):
        if self._cursor_factory is not None and "cursor_factory" not in kwargs:
            kwargs["cursor_factory"] = self._cursor_factory
        return self._connection.cursor(*args, **kwargs)

    def close(self):
        if self._returned:
            return
        self._returned = True
        try:
            # A request that calls close() is finished. Roll back any unfinished
            # transaction before making this connection available to another request.
            self._connection.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._connection)
        except Exception:
            try:
                self._connection.close()
            except Exception:
                pass
        finally:
            self._pool_slots_release()

    def _pool_slots_release(self):
        try:
            _pool_slots.release()
        except ValueError:
            pass

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_db_connection(
    retries=3,
    backoff=1,
    cursor_factory=None
):
    """Return a pooled PostgreSQL connection with the existing API preserved."""
    for attempt in range(retries):
        acquired = _pool_slots.acquire(timeout=30)
        if not acquired:
            if attempt == retries - 1:
                raise psycopg2.OperationalError("Timed out waiting for an available database connection")
            time.sleep(backoff * (2 ** attempt))
            continue

        try:
            pool = _get_pool()
            connection = pool.getconn()
            return _PooledConnection(pool, connection, cursor_factory=cursor_factory)
        except psycopg2.OperationalError:
            _pool_slots.release()
            if attempt == retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            print(f"Retrying database connection in {wait}s...")
            time.sleep(wait)
        except Exception:
            _pool_slots.release()
            raise


@contextmanager
def get_db(cursor_factory=RealDictCursor):
    conn = get_db_connection(cursor_factory=cursor_factory)
    try:
        yield conn
    finally:
        conn.close()
