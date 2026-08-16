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
        return True
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Failed to log business event {event_type}: {e}")
        return False
    finally:
        if cur: cur.close()
        if conn: conn.close()


def _confirm_latest_match_event(user_id, rows_processed):
    """Promote the latest matching preview to a real match job only after XML conversion succeeds.

    Party Matching is a preparation step. Match Analytics should count it only when the
    resulting data is actually converted to XML. The row-count check prevents an unrelated
    conversion from consuming an older pending match event for the same user.
    """
    if user_id is None:
        return

    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE business_events
            SET
                event_type = 'match_party',
                status = 'success',
                details = COALESCE(details, '{}'::jsonb) || jsonb_build_object(
                    'conversion_confirmed', true,
                    'conversion_confirmed_at', NOW()
                )
            WHERE id = (
                SELECT id
                FROM business_events
                WHERE user_id = %s
                  AND event_type = 'match_party_pending'
                  AND status = 'pending'
                  AND COALESCE((details->>'rows_processed')::int, -1) = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            )
        """, (user_id, rows_processed))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Failed to confirm pending match analytics event: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()


def log_match_event(user_id: int, username: str, status: str, duration_ms: int,
                    rows_processed: int, matched: int, unmatched: int, ledgers_fetched: int):
    """Store Party Matching as pending until its output is actually converted to XML."""
    details = {
        "rows_processed": rows_processed,
        "matched_rows": matched,
        "unmatched_rows": unmatched,
        "ledgers_fetched": ledgers_fetched,
        "match_percentage": round((matched / rows_processed * 100), 2) if rows_processed > 0 else 0,
    }

    # Do not expose this as a real match job yet. The conversion step will promote it.
    _safe_insert_event(
        user_id,
        username,
        "match_party_pending",
        "pending",
        duration_ms,
        details,
    )


def log_conversion_event(user_id: int, username: str, status: str, duration_ms: int,
                         rows_processed: int, voucher_type: str, exceptions: int):
    """Log XML conversion and confirm the associated Party Matching job on success."""
    details = {
        "rows_processed": rows_processed,
        "voucher_type": voucher_type,
        "exception_rows": exceptions,
    }
    inserted = _safe_insert_event(user_id, username, "convert_xml", status, duration_ms, details)

    # Only a successful XML conversion turns a Party Matching preview into a counted match job.
    if inserted and status == "success":
        _confirm_latest_match_event(user_id, rows_processed)


def log_ocr_event(user_id: int, username: str, status: str, duration_ms: int,
                  file_type: str, pages: int, rows_generated: int):
    """Privacy-safe logging for OCR Data Extraction."""
    details = {
        "file_type": file_type,
        "pages_processed": pages,
        "rows_generated": rows_generated,
    }
    _safe_insert_event(user_id, username, "ocr", status, duration_ms, details)


def log_business_error(user_id: int, username: str, event_type: str, error_type: str, error_message: str):
    """Records logical business failures (not stack traces)."""
    details = {
        "error_type": error_type,
        "error_message": error_message,
    }
    _safe_insert_event(user_id, username, event_type, "error", 0, details)
