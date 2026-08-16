import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
logger = logging.getLogger("admin_telemetry")

def get_telemetry_db_connection():
    """Establishes thread-isolated relational mappings with error fail-safes."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment registry key is not configured.")
    try:
        ssl_mode = os.environ.get("DB_SSLMODE", "require")
        if "127.0.0.1" in db_url or "localhost" in db_url:
            ssl_mode = "disable"
        if ssl_mode == "disable":
            return psycopg2.connect(db_url)
        return psycopg2.connect(db_url, sslmode=ssl_mode)
    except Exception as e:
        logger.error(f"PostgreSQL connection initialization failed: {e}")
        raise

def ensure_admin_schema() -> None:
    """Create telemetry tables and keep their columns backward compatible."""
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_events (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        logs_cols = [
            ("user_id", "INTEGER"),
            ("username", "TEXT"),
            ("event_type", "TEXT"),
            ("endpoint", "TEXT"),
            ("status", "TEXT"),
            ("execution_time_ms", "INTEGER DEFAULT 0"),
            ("error_message", "TEXT"),
            ("details", "JSONB")
        ]
        for name, dtype in logs_cols:
            cur.execute(f"ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS {name} {dtype};")

        # Security Guard uses admin_events. Keep it compatible with the
        # existing schema while giving it the same useful identity/action data.
        events_cols = [
            ("user_id", "INTEGER"),
            ("username", "TEXT"),
            ("action", "TEXT"),
            ("endpoint", "TEXT"),
            ("status", "TEXT"),
            ("execution_time_ms", "INTEGER DEFAULT 0"),
            ("details", "JSONB")
        ]
        for name, dtype in events_cols:
            cur.execute(f"ALTER TABLE admin_events ADD COLUMN IF NOT EXISTS {name} {dtype};")

        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Automated schema mapping self-migration encountered a roadblock: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def log_admin_event(
    user_id: Any = None,
    username: str = "anonymous_guest",
    event_type: str = "api_request",
    endpoint: str = None,
    status_str: str = "success",
    execution_time_ms: int = 0,
    error_message: str = None,
    details: dict = None
) -> bool:
    """Write operational telemetry and a matching Security Guard event."""
    conn = None
    cur = None
    try:
        # Keep schema creation out of every request path; app startup already
        # calls ensure_admin_schema(). The INSERT remains lightweight.
        conn = get_telemetry_db_connection()
        cur = conn.cursor()
        details_json = json.dumps(details or {})

        cur.execute("""
            INSERT INTO admin_logs (
                user_id, username, event_type, endpoint,
                status, execution_time_ms, error_message, details, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            user_id, username, event_type, endpoint,
            status_str, execution_time_ms, error_message, details_json
        ))

        # Mirror the same event into admin_events so Security Guard has a
        # real data source instead of depending on an unused empty table.
        cur.execute("""
            INSERT INTO admin_events (
                user_id, username, action, endpoint, status,
                execution_time_ms, details, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            user_id, username, event_type, endpoint,
            status_str, execution_time_ms, details_json
        ))

        conn.commit()
        return True
    except Exception as err:
        if conn:
            conn.rollback()
        logger.exception(f"Failed to commit metrics/security payload: {err}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def ensure_business_events_table():
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS business_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            event_type TEXT,
            status TEXT,
            duration_ms INTEGER,
            rows_processed INTEGER DEFAULT 0,
            matched_rows INTEGER DEFAULT 0,
            unmatched_rows INTEGER DEFAULT 0,
            voucher_type TEXT,
            pages_processed INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"business_events table creation failed: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def log_match_event(user_id, username, status, duration_ms, rows_processed, matched_rows, unmatched_rows):
    ensure_business_events_table()
    conn = None; cur = None
    try:
        conn = get_telemetry_db_connection(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO business_events (user_id, username, event_type, status, duration_ms, rows_processed, matched_rows, unmatched_rows)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (user_id, username, "match_party", status, duration_ms, rows_processed, matched_rows, unmatched_rows))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"log_match_event failed: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()

def log_conversion_event(user_id, username, status, duration_ms, rows_processed, voucher_type):
    ensure_business_events_table()
    conn = None; cur = None
    try:
        conn = get_telemetry_db_connection(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO business_events (user_id, username, event_type, status, duration_ms, rows_processed, voucher_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (user_id, username, "convert_xml", status, duration_ms, rows_processed, voucher_type))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"log_conversion_event failed: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()

def log_ocr_event(user_id, username, status, duration_ms, pages_processed):
    ensure_business_events_table()
    conn = None; cur = None
    try:
        conn = get_telemetry_db_connection(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO business_events (user_id, username, event_type, status, duration_ms, pages_processed)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (user_id, username, "ocr", status, duration_ms, pages_processed))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"log_ocr_event failed: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()

def log_business_error(user_id, username, event_type, error_message):
    ensure_business_events_table()
    conn = None; cur = None
    try:
        conn = get_telemetry_db_connection(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO business_events (user_id, username, event_type, status, error_message)
            VALUES (%s,%s,%s,%s,%s)
        """, (user_id, username, event_type, "error", error_message))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"log_business_error failed: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()

def fetch_dashboard_counters() -> Dict[str, int]:
    metrics = {"total_users": 0, "error_count_24h": 0, "avg_latency_7d": 0, "total_logs": 0}
    conn = None; cur = None
    try:
        conn = get_telemetry_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT COUNT(*) as total FROM users"); row = cur.fetchone(); metrics["total_users"] = int(row["total"] or 0) if row else 0
        except Exception as e:
            logger.warning(f"Telemetry collector missed total_users calculation index: {e}"); conn.rollback()
        try:
            cur.execute("SELECT COUNT(*) as total FROM admin_logs WHERE status = 'error' AND created_at >= NOW() - INTERVAL '24 hours'"); row = cur.fetchone(); metrics["error_count_24h"] = int(row["total"] or 0) if row else 0
        except Exception as e:
            logger.warning(f"Telemetry collector missed error_count_24h calculation index: {e}"); conn.rollback()
        try:
            cur.execute("SELECT COALESCE(AVG(execution_time_ms), 0) as avg_latency FROM admin_logs WHERE endpoint = '/api/convert' AND created_at >= NOW() - INTERVAL '7 days'"); row = cur.fetchone(); metrics["avg_latency_7d"] = int(row["avg_latency"] or 0) if row else 0
        except Exception as e:
            logger.warning(f"Telemetry collector missed avg_latency_7d calculation index: {e}"); conn.rollback()
        try:
            cur.execute("SELECT COUNT(*) as total FROM admin_logs"); row = cur.fetchone(); metrics["total_logs"] = int(row["total"] or 0) if row else 0
        except Exception as e:
            logger.warning(f"Telemetry collector missed total_logs calculation index: {e}"); conn.rollback()
    except Exception as err:
        logger.exception(f"Admin dashboard status aggregation interface failure: {err}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return metrics

def gather_traffic_trends_7d() -> Dict[str, List]:
    trends = {"labels": [], "api_data": [], "error_data": []}
    conn = None; cur = None
    try:
        conn = get_telemetry_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT TO_CHAR(created_at, 'YYYY-MM-DD') as log_date,
                   COUNT(CASE WHEN event_type = 'api_request' THEN 1 END) as api_requests,
                   COUNT(CASE WHEN status = 'error' OR event_type = 'system_crash' THEN 1 END) as structural_failures
            FROM admin_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY log_date ORDER BY log_date ASC
        """)
        records = cur.fetchall() or []
        trends["labels"] = [str(row["log_date"] or "") for row in records]
        trends["api_data"] = [int(row["api_requests"] or 0) for row in records]
        trends["error_data"] = [int(row["structural_failures"] or 0) for row in records]
    except Exception as err:
        logger.exception(f"Telemetry chronological timeline parser engine failure: {err}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return trends
