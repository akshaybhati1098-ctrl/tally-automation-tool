from psycopg2.extras import RealDictCursor
from database import get_db_connection
from datetime import datetime, timedelta

from database import get_db_connection

XML_TRIAL_ROW_LIMIT = 10
XML_BASIC_ROW_LIMIT = 100
XML_PRO_ROW_LIMIT = 250

class XMLConversionLimitError(Exception):
    """Raised when an XML conversion exceeds the separate row allowance."""


def _ensure_pause_columns():
    """Ensure pause metadata exists for older production databases."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_paused_at TIMESTAMP")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_pause_remaining_seconds BIGINT")
        conn.commit()
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
    _ensure_pause_columns()
    conn = get_db_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.plan_id, u.subscription_status, u.plan_start, u.plan_expiry,
               u.subscription_paused_at, u.subscription_pause_remaining_seconds,
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
    conn.close()


def update_user_subscription(user_id: int, plan_id: int, match_limit: int, subscription_status: str, plan_expiry):
    """Update a subscription; PAUSED/ACTIVE transitions preserve existing usage."""
    _ensure_pause_columns()
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT plan_id, subscription_status, plan_expiry,
                   subscription_paused_at, subscription_pause_remaining_seconds
            FROM users WHERE id=%s FOR UPDATE
        """, (user_id,))
        current = cur.fetchone()
        if not current:
            raise ValueError("User not found.")

        requested_status = str(subscription_status or "ACTIVE").upper()
        current_status = str(current["subscription_status"] or "").upper()

        if requested_status == "PAUSED":
            if current_status != "PAUSED":
                expiry = current["plan_expiry"]
                remaining_seconds = max(0, int((expiry - datetime.now()).total_seconds())) if expiry else 0
                cur.execute("""
                    UPDATE users
                    SET subscription_status='PAUSED',
                        subscription_paused_at=NOW(),
                        subscription_pause_remaining_seconds=%s
                    WHERE id=%s
                """, (remaining_seconds, user_id))
            conn.commit()
            return True

        if requested_status == "ACTIVE" and current_status == "PAUSED":
            remaining_seconds = int(current["subscription_pause_remaining_seconds"] or 0)
            new_expiry = datetime.now() + timedelta(seconds=max(0, remaining_seconds))
            cur.execute("""
                UPDATE users
                SET subscription_status='ACTIVE',
                    plan_expiry=%s,
                    plan_start=COALESCE(plan_start, NOW()),
                    subscription_paused_at=NULL,
                    subscription_pause_remaining_seconds=NULL
                WHERE id=%s
            """, (new_expiry, user_id))
            conn.commit()
            return True

        if plan_id == 1:
            match_limit = 10
        elif plan_id == 2:
            match_limit = 30
        elif plan_id == 3:
            match_limit = -1
        if plan_expiry is None:
            plan_expiry = datetime.now() + timedelta(days=30)
        cur.execute("""
            UPDATE users SET plan_id=%s, subscription_status=%s, plan_start=NOW(), plan_expiry=%s,
                subscription_paused_at=NULL, subscription_pause_remaining_seconds=NULL
            WHERE id=%s
        """, (plan_id, requested_status, plan_expiry, user_id))
        cur.execute("""
            INSERT INTO feature_usage (user_id, feature_name, used_count, reset_date)
            VALUES (%s, 'party_matching', 0, CURRENT_DATE)
            ON CONFLICT (user_id, feature_name)
            DO UPDATE SET used_count=0, reset_date=CURRENT_DATE
        """, (user_id,))
        cur.execute("""
            INSERT INTO feature_usage (user_id, feature_name, used_count, reset_date)
            VALUES (%s, 'xml_conversion', 0, CURRENT_DATE)
            ON CONFLICT (user_id, feature_name)
            DO UPDATE SET used_count=0, reset_date=CURRENT_DATE
        """, (user_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def assign_trial_plan(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, trial_days FROM subscription_plans WHERE code='TRIAL'
    """)
    plan = cur.fetchone()
    if not plan:
        raise Exception("TRIAL plan not found.")
    expiry = datetime.now() + timedelta(days=plan["trial_days"])
    cur.execute("""
        UPDATE users SET plan_id=%s, subscription_status='TRIAL', plan_start=NOW(), plan_expiry=%s
        WHERE id=%s
    """, (plan["id"], expiry, user_id))
    conn.commit()
    cur.close()
    conn.close()


def initialize_feature_usage(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO feature_usage (user_id, feature_name, used_count, reset_date)
        VALUES (%s, 'party_matching', 0, CURRENT_DATE)
        ON CONFLICT (user_id, feature_name) DO NOTHING
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()
