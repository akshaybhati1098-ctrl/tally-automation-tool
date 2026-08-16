from psycopg2.extras import RealDictCursor
from database import get_db_connection
from datetime import datetime, timedelta

XML_TRIAL_ROW_LIMIT = 10
XML_BASIC_ROW_LIMIT = 100
XML_PRO_ROW_LIMIT = 250

class XMLConversionLimitError(Exception):
    """Raised when an XML conversion exceeds the separate row allowance."""


# Schema migrations must not run on every request. ALTER TABLE takes an
# ACCESS EXCLUSIVE lock and can block normal users when the users table is busy.
# The pause migration is therefore handled separately by sql/subscription_pause.sql.
_pause_columns_available_cache = None


def _ensure_pause_columns():
    """Check pause-column availability without performing DDL during requests.

    Returns True when both pause columns exist. Older databases can continue to
    read subscription data safely until the migration is applied, instead of
    blocking a request on ALTER TABLE.
    """
    global _pause_columns_available_cache

    if _pause_columns_available_cache is not None:
        return _pause_columns_available_cache

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'users'
              AND column_name IN (
                  'subscription_paused_at',
                  'subscription_pause_remaining_seconds'
              )
        """)
        count = int(cur.fetchone()[0] or 0)
        _pause_columns_available_cache = count == 2
        return _pause_columns_available_cache
    finally:
        cur.close()
        conn.close()


def _xml_limit_from_plan_name(plan_name):
    name = str(plan_name or "").strip().lower()
    if name == "trial":
        return XML_TRIAL_ROW_LIMIT
    if name == "basic":
        return XML_BASIC_ROW_LIMIT
    if name == "pro":
        return XML_PRO_ROW_LIMIT
    return 0


def get_user_plan(user_id: int):
    has_pause_columns = _ensure_pause_columns()
    conn = get_db_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    pause_select = "u.subscription_paused_at, u.subscription_pause_remaining_seconds," if has_pause_columns else "NULL AS subscription_paused_at, NULL AS subscription_pause_remaining_seconds,"

    cur.execute(f"""
        SELECT u.id, u.plan_id, u.subscription_status, u.plan_start, u.plan_expiry,
               {pause_select}
               p.plan_name, p.price, p.match_limit, p.connector_enabled,
               p.xml_enabled, p.ocr_enabled, p.priority_support, p.is_active
        FROM users u
        LEFT JOIN subscription_plans p ON p.id = u.plan_id
        WHERE u.id = %s
    """, (user_id,))
    data = cur.fetchone()

    if data:
        xml_limit = _xml_limit_from_plan_name(data["plan_name"])
        try:
            cur.execute("SELECT xml_row_limit FROM subscription_plans WHERE id=%s", (data["plan_id"],))
            xml_limit_row = cur.fetchone()
            if xml_limit_row and xml_limit_row[0] is not None:
                xml_limit = int(xml_limit_row[0])
        except Exception:
            conn.rollback()

        xml_usage = get_feature_usage(user_id, "xml_conversion")
        xml_used = int(xml_usage["used_count"]) if xml_usage else 0
        data["xml_row_limit"] = xml_limit
        data["xml_used_count"] = xml_used
        data["xml_remaining"] = max(0, xml_limit - xml_used)
        data["is_paused"] = str(data.get("subscription_status") or "").upper() == "PAUSED"

    cur.close()
    conn.close()
    return data


def get_plan_name(user_id: int):
    plan = get_user_plan(user_id)
    if not plan:
        return "Basic"
    return plan["plan_name"]


def has_feature(user_id: int, feature: str):
    plan = get_user_plan(user_id)
    if not plan:
        return False
    feature_map = {
        "connector": plan["connector_enabled"],
        "xml": plan["xml_enabled"],
        "ocr": plan["ocr_enabled"],
        "priority_support": plan["priority_support"],
        "party_matching": True,
    }
    return feature_map.get(feature, False)


def get_match_limit(user_id):
    plan = get_user_plan(user_id)
    if not plan:
        return 0
    limit = plan["match_limit"]
    if limit is None:
        return 0
    return limit

# ==========================================
# FEATURE USAGE
# ==========================================

def get_feature_usage(user_id: int, feature_name: str):
    conn = get_db_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM feature_usage
        WHERE user_id=%s AND feature_name=%s
    """, (user_id, feature_name))
    usage = cur.fetchone()
    cur.close()
    conn.close()
    return usage


def get_remaining_feature_usage(user_id, feature_name):
    if feature_name != "party_matching":
        return -1
    limit = get_match_limit(user_id)
    if limit is None:
        return 0
    if limit == -1:
        return -1
    usage = get_feature_usage(user_id, feature_name)
    if not usage:
        return limit
    return max(0, limit - usage["used_count"])


def get_remaining_xml_rows(user_id: int):
    plan = get_user_plan(user_id)
    return int(plan.get("xml_remaining", 0)) if plan else 0


def check_xml_conversion_quota(user_id: int, row_count: int):
    """Check XML row allowance before generating XML; does not deduct."""
    try:
        rows = int(row_count)
    except (TypeError, ValueError):
        raise XMLConversionLimitError("Unable to determine the number of Excel rows for conversion.")
    if rows <= 0:
        raise XMLConversionLimitError("No Excel rows are available for XML conversion.")

    plan = get_user_plan(user_id)
    if not plan:
        raise XMLConversionLimitError("Unable to verify your XML conversion allowance.")
    if plan.get("is_paused"):
        raise XMLConversionLimitError(
            "⏸️ Your subscription is currently paused. Excel → Tally XML conversion is unavailable until your subscription is resumed."
        )
    limit = int(plan.get("xml_row_limit", 0))
    usage = get_feature_usage(user_id, "xml_conversion")
    used = int(usage["used_count"]) if usage else 0
    remaining = max(0, limit - used)
    if rows > remaining:
        raise XMLConversionLimitError(
            f"This Excel contains {rows} rows, but you have only {remaining} XML conversion rows remaining. "
            f"Please use a smaller Excel file or upgrade your plan."
        )
    return True


def increment_xml_conversion_usage(user_id: int, row_count: int):
    """Deduct XML rows only after XML generation succeeds."""
    rows = int(row_count)
    if rows <= 0:
        raise XMLConversionLimitError("Invalid XML conversion row count.")

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO feature_usage (user_id, feature_name, used_count, reset_date)
            VALUES (%s, 'xml_conversion', 0, CURRENT_DATE)
            ON CONFLICT (user_id, feature_name) DO NOTHING
        """, (user_id,))

        plan = get_user_plan(user_id)
        if plan and plan.get("is_paused"):
            raise XMLConversionLimitError(
                "⏸️ Your subscription is currently paused. Excel → Tally XML conversion is unavailable until your subscription is resumed."
            )
        limit = int(plan.get("xml_row_limit", 0)) if plan else 0
        cur.execute("""
            SELECT used_count FROM feature_usage
            WHERE user_id=%s AND feature_name='xml_conversion'
            FOR UPDATE
        """, (user_id,))
        usage = cur.fetchone()
        used = int(usage[0]) if usage else 0
        if used + rows > limit:
            remaining = max(0, limit - used)
            raise XMLConversionLimitError(
                f"This Excel contains {rows} rows, but you have only {remaining} XML conversion rows remaining. "
                f"Please use a smaller Excel file or upgrade your plan."
            )
        cur.execute("""
            UPDATE feature_usage
            SET used_count = used_count + %s, reset_date = CURRENT_DATE
            WHERE user_id=%s AND feature_name='xml_conversion'
        """, (rows, user_id))
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def can_use_feature(user_id: int, feature_name: str):
    if not has_feature(user_id, feature_name):
        return False, "Your current plan does not include this feature."
    plan = get_user_plan(user_id)
    if plan.get("is_paused"):
        if feature_name == "party_matching":
            return False, "⏸️ Your subscription is currently paused. Party Matching is unavailable until your subscription is resumed."
        return False, "⏸️ Your subscription is currently paused."
    if plan["plan_expiry"] is not None and datetime.now() > plan["plan_expiry"]:
        return False, "Your subscription has expired."
    remaining = get_remaining_feature_usage(user_id, feature_name)
    if remaining == -1:
        return True, ""
    if remaining <= 0:
        return False, "You have reached your matching limit."
    return True, ""


def increment_feature_usage(user_id: int, feature_name: str):
    """Existing Party Matching usage logic; intentionally unchanged."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO feature_usage (user_id, feature_name, used_count, reset_date)
        VALUES (%s, %s, 1, CURRENT_DATE)
        ON CONFLICT (user_id, feature_name)
        DO UPDATE SET used_count = feature_usage.used_count + 1, reset_date = CURRENT_DATE
    """, (user_id, feature_name))
    conn.commit()
    cur.close()
    conn.close()


def reset_feature_usage(user_id: int, feature_name: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE feature_usage SET used_count=0, reset_date=CURRENT_DATE
        WHERE user_id=%s AND feature_name=%s
    """, (user_id, feature_name))
    conn.commit()
    cur.close()
