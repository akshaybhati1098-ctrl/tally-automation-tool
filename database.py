import os
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")


def get_db_connection(
    retries=3,
    backoff=1,
    cursor_factory=None
):
    """
    Returns a PostgreSQL connection.
    """

    for attempt in range(retries):

        try:

            kwargs = {
                "sslmode": "require",
                "connect_timeout": 10,
            }

            if cursor_factory:
                kwargs["cursor_factory"] = cursor_factory

            return psycopg2.connect(
                DATABASE_URL,
                **kwargs
            )

        except psycopg2.OperationalError:

            if attempt == retries - 1:
                raise

            wait = backoff * (2 ** attempt)

            print(f"Retrying database connection in {wait}s...")

            time.sleep(wait)


@contextmanager
def get_db(cursor_factory=RealDictCursor):

    conn = get_db_connection(cursor_factory=cursor_factory)

    try:

        yield conn

    finally:

        conn.close()
