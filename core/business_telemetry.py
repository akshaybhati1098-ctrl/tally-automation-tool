import json
import logging
from datetime import datetime
import psycopg2
from core.admin_telemetry import get_telemetry_db_connection

logger = logging.getLogger("business_telemetry")

def _safe_insert_event(user_id, username, event_type, status, duration_ms, details):
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO business_events (user_id, username, event_type, status, duration_ms, details, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, username, event_type, status, duration_ms, json.dumps(details)))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Failed to log business event {event_type}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()

def log_match_event(user_id: int, username: str, status: str, duration_ms: int, 
                    rows_processed: int, matched: int, unmatched: int, ledgers_fetched: int):
    """Privacy-safe logging for Party Matching."""
    details = {
        "rows_processed": rows_processed,
        "matched_rows": matched,
        "unmatched_rows": unmatched,
        "ledgers_fetched": ledgers_fetched,
        "match_percentage": round((matched / rows_processed * 100), 2) if rows_processed > 0 else 0
    }
    _safe_insert_event(user_id, username, "match_party", status, duration_ms, details)

def log_conversion_event(user_id: int, username: str, status: str, duration_ms: int, 
                         rows_processed: int, voucher_type: str, exceptions: int):
    """Privacy-safe logging for XML Conversion."""
    details = {
        "rows_processed": rows_processed,
        "voucher_type": voucher_type,
        "exception_rows": exceptions
    }
    _safe_insert_event(user_id, username, "convert_xml", status, duration_ms, details)

def log_ocr_event(user_id: int, username: str, status: str, duration_ms: int, 
                  file_type: str, pages: int, rows_generated: int):
    """Privacy-safe logging for OCR Data Extraction."""
    details = {
        "file_type": file_type,
        "pages_processed": pages,
        "rows_generated": rows_generated
    }
    _safe_insert_event(user_id, username, "ocr", status, duration_ms, details)

def log_business_error(user_id: int, username: str, event_type: str, error_type: str, error_message: str):
    """Records logical business failures (not stack traces)."""
    details = {
        "error_type": error_type,
        "error_message": error_message
    }
    _safe_insert_event(user_id, username, event_type, "error", 0, details)

