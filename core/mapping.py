import json
import os
import logging
import psycopg2
from psycopg2.extras import Json, RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

# ==================== INIT ====================
def init_db():
    if not DATABASE_URL:
        return
    
    conn = get_db_connection()
    cur = conn.cursor()

    # ✅ FIX: add user_id + composite unique
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_mapping (
            id SERIAL PRIMARY KEY,
            company TEXT,
            user_id INTEGER,
            mapping JSONB NOT NULL,
            UNIQUE(company, user_id)
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# ==================== DEFAULT ====================
def get_default_mapping():
    return {
        "COMPANY_STATE": "Uttar Pradesh",
        "DEBUG": False,
        "SALES": {
            "0": "Sales - 0%",
            "5": "Local Sale @5%",
            "12": "Local Sale @12%",
            "18": "Local Sale @18%",
            "28": "Local Sale @28%"
        },
        "SALES_IGST": {
            "0": "Sales - IGST 0%",
            "5": "Interstate Sale @5%",
            "12": "Interstate Sale @12%",
            "18": "Interstate Sale @18%",
            "28": "Interstate Sale @28%"
        },
        "PURCHASE": {
            "0": "Purchase - 0%",
            "5": "Local Purchase @5%",
            "12": "Local Purchase @12%",
            "18": "Local Purchase @18%",
            "28": "Local Purchase @28%"
        },
        "CGST_RATES": {
            "5": "CGST @ 2.5%",
            "12": "CGST @ 6%",
            "18": "CGST @ 9%",
            "28": "CGST @ 14%"
        },
        "SGST_RATES": {
            "5": "SGST @ 2.5%",
            "12": "SGST @ 6%",
            "18": "SGST @ 9%",
            "28": "SGST @ 14%"
        },
        "IGST_RATES": {
            "5": "IGST @ 5%",
            "12": "IGST @ 12%",
            "18": "IGST @ 18%",
            "28": "IGST @ 28%"
        }
    }

# ==================== POSTGRES ====================
def load_all_mappings_postgres(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT company, mapping FROM company_mapping WHERE user_id=%s ORDER BY company",
        (user_id,)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    mappings = {}
    companies = []

    for row in rows:
        mappings[row["company"]] = row["mapping"]
        companies.append(row["company"])

    return companies, mappings


def save_company_mapping_postgres(company, mapping, user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO company_mapping (company, mapping, user_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (company, user_id)
        DO UPDATE SET mapping = EXCLUDED.mapping
    """, (company, Json(mapping), user_id))

    conn.commit()
    cur.close()
    conn.close()


def delete_company_postgres(company, user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM company_mapping WHERE company=%s AND user_id=%s",
        (company, user_id)
    )

    conn.commit()
    cur.close()
    conn.close()

# ==================== PUBLIC API ====================

def load_companies(user_id):
    companies, _ = load_all_mappings_postgres(user_id)

    if companies:
        return companies
    else:
        # create default for new user
        save_company_mapping_postgres("Default", get_default_mapping(), user_id)
        return ["Default"]


def add_company(name, user_id):
    if name == "Default":
        raise ValueError("Cannot add Default")

    companies, _ = load_all_mappings_postgres(user_id)

    if name in companies:
        raise ValueError("Company exists")

    save_company_mapping_postgres(name, get_default_mapping(), user_id)


def delete_company(name, user_id):
    if name == "Default":
        raise ValueError("Cannot delete Default")

    delete_company_postgres(name, user_id)


def get_company_mapping(name, user_id):
    _, mappings = load_all_mappings_postgres(user_id)

    if name not in mappings:
        raise ValueError("Not found")

    return mappings[name]


def save_company_mapping(name, mapping, user_id):
    save_company_mapping_postgres(name, mapping, user_id)
def migrate_json_to_postgres(user_id):
    """Migrate old JSON data into PostgreSQL for a specific user."""
    if not DATABASE_URL:
        logger.error("No DATABASE_URL, cannot migrate")
        return False

    try:
        json_data = load_mapping_json()
        companies = json_data.get("companies", [])
        mappings = json_data.get("mappings", {})

        for company in companies:
            if company in mappings:
                save_company_mapping_postgres(
                    company,
                    mappings[company],
                    user_id
                )
                logger.info(f"✅ Migrated {company} for user {user_id}")

        logger.info(f"🚀 Migration complete for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False