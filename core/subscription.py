from psycopg2.extras import RealDictCursor
from database import get_db_connection
from datetime import datetime, timedelta

from database import get_db_connection


def get_user_plan(user_id: int):
    """
    Returns the user's subscription along with plan details.
    """

    conn = get_db_connection(cursor_factory=RealDictCursor)

    cur = conn.cursor()

    cur.execute("""
        SELECT
            u.id,
            u.plan_id,
            u.subscription_status,
            u.plan_start,
            u.plan_expiry,

            p.plan_name,
            p.price,
            p.match_limit,
            p.connector_enabled,
            p.xml_enabled,
            p.ocr_enabled,
            p.priority_support,
            p.is_active

        FROM users u

        LEFT JOIN subscription_plans p
            ON p.id = u.plan_id

        WHERE u.id = %s
    """, (user_id,))

    data = cur.fetchone()

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

        # Basic has matching too (limited)
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
    """
    Returns usage row for a feature.
    """

    conn = get_db_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM feature_usage
        WHERE user_id=%s
        AND feature_name=%s
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

    usage = get_feature_usage(
        user_id,
        feature_name
    )

    if not usage:
        return limit

    return max(
        0,
        limit - usage["used_count"]
    )
def can_use_feature(user_id: int, feature_name: str):
    """
    Check whether the user can use a feature.
    Returns:
        (allowed, message)
    """

    if not has_feature(user_id, feature_name):
        return False, "Your current plan does not include this feature."

    plan = get_user_plan(user_id)

    if (
        plan["plan_expiry"] is not None
        and datetime.now() > plan["plan_expiry"]
    ):
        return False, "Your subscription has expired."

    remaining = get_remaining_feature_usage(
        user_id,
        feature_name
    )

    if remaining == -1:
        return True, ""

    if remaining <= 0:
        return False, "You have reached your matching limit."

    return True, ""

def increment_feature_usage(user_id: int, feature_name: str):
    """
    Increment feature usage.
    """

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO feature_usage
        (
            user_id,
            feature_name,
            used_count,
            reset_date
        )

        VALUES
        (
            %s,
            %s,
            1,
            CURRENT_DATE
        )

        ON CONFLICT
        (
            user_id,
            feature_name
        )

        DO UPDATE

        SET

            used_count = feature_usage.used_count + 1,

            reset_date = CURRENT_DATE
    """, (
        user_id,
        feature_name
    ))

    conn.commit()

    cur.close()
    conn.close()
def reset_feature_usage(user_id: int, feature_name: str):
    """
    Reset usage manually.
    """

    conn = get_db_connection()

    cur = conn.cursor()

    cur.execute("""
        UPDATE feature_usage

        SET

            used_count=0,

            reset_date=CURRENT_DATE

        WHERE

            user_id=%s

        AND

            feature_name=%s
    """, (
        user_id,
        feature_name
    ))

    conn.commit()

    cur.close()

    conn.close()

def update_user_subscription(
    user_id: int,
    plan_id: int,
    match_limit: int,
    subscription_status: str,
    plan_expiry
):

    conn = get_db_connection()
    cur = conn.cursor()

    # ---------------------------------------
    # Decide limit from selected plan
    # ---------------------------------------

    if plan_id == 1:          # Trial
        match_limit = 10

    elif plan_id == 2:        # Basic
        match_limit = 30

    elif plan_id == 3:        # Pro
        match_limit = -1

    # ---------------------------------------
    # Default expiry
    # ---------------------------------------

    if plan_expiry is None:

        plan_expiry = datetime.now() + timedelta(days=30)

    # ---------------------------------------
    # Update user
    # ---------------------------------------

    cur.execute("""

        UPDATE users

        SET

            plan_id=%s,

            subscription_status=%s,

            plan_start=NOW(),

            plan_expiry=%s

        WHERE id=%s

    """,
    (
        plan_id,
        subscription_status,
        plan_expiry,
        user_id
    ))

    # ---------------------------------------
    # Reset feature usage
    # ---------------------------------------

    cur.execute("""

        INSERT INTO feature_usage
        (
            user_id,
            feature_name,
            used_count,
            reset_date
        )

        VALUES
        (
            %s,
            'party_matching',
            0,
            CURRENT_DATE
        )

        ON CONFLICT
        (
            user_id,
            feature_name
        )

        DO UPDATE

        SET

            used_count=0,

            reset_date=CURRENT_DATE

    """,
    (
        user_id,
    ))

    conn.commit()

    cur.close()

    conn.close()

    return True
def assign_trial_plan(user_id: int):
    """
    Assign Free Trial plan to newly registered user.
    """

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Find Trial plan
    cur.execute("""
        SELECT id, trial_days
        FROM subscription_plans
        WHERE code='TRIAL'
    """)

    plan = cur.fetchone()

    if not plan:
        raise Exception("TRIAL plan not found.")

    expiry = datetime.now() + timedelta(days=plan["trial_days"])

    cur.execute("""
        UPDATE users
        SET
            plan_id=%s,
            subscription_status='TRIAL',
            plan_start=NOW(),
            plan_expiry=%s
        WHERE id=%s
    """,
    (
        plan["id"],
        expiry,
        user_id
    ))

    conn.commit()

    cur.close()
    conn.close()
def initialize_feature_usage(user_id: int):
    """
    Initialize usage counters for new user.
    """

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO feature_usage
        (
            user_id,
            feature_name,
            used_count,
            reset_date
        )
        VALUES
        (
            %s,
            'party_matching',
            0,
            CURRENT_DATE
        )
        ON CONFLICT (user_id, feature_name)
        DO NOTHING
    """,
    (
        user_id,
    ))

    conn.commit()

    cur.close()
    conn.close()