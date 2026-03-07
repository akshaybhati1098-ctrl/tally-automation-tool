import json
import os
import logging
import psycopg2
from psycopg2.extras import Json, RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment (set by Render)
DATABASE_URL = os.environ.get("DATABASE_URL")
logger.info(f"DATABASE_URL exists: {bool(DATABASE_URL)}")
if DATABASE_URL:
    logger.info(f"DATABASE_URL starts with: {DATABASE_URL[:20]}...")

if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable not set! Using JSON file fallback.")
    # We'll keep JSON as fallback but log error

def get_db_connection():
    """Return a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Create the mapping table if it doesn't exist."""
    if not DATABASE_URL:
        logger.warning("No DATABASE_URL, skipping PostgreSQL initialization")
        return
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS company_mapping (
                company TEXT PRIMARY KEY,
                mapping JSONB NOT NULL
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("PostgreSQL database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL database: {e}")

# Initialize PostgreSQL if available
try:
    init_db()
except Exception as e:
    logger.error(f"PostgreSQL initialization failed: {e}")

# JSON file fallback (keep for backward compatibility)
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)
MAP_FILE = os.path.join(DATA_DIR, "mapping.json")


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


# ==================== POSTGRESQL FUNCTIONS ====================

def load_all_mappings_postgres():
    """Load all companies and mappings from PostgreSQL."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT company, mapping FROM company_mapping ORDER BY company")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        mappings = {}
        companies = []
        for row in rows:
            company = row["company"]
            mapping = row["mapping"]
            mappings[company] = mapping
            companies.append(company)

        # If no companies exist, create the default one
        if not companies:
            logger.info("No companies found in PostgreSQL, creating Default company")
            default = "Default"
            save_company_mapping_postgres(default, get_default_mapping())
            companies = [default]
            mappings[default] = get_default_mapping()

        return companies, mappings
    except Exception as e:
        logger.error(f"Error loading from PostgreSQL: {e}")
        return None, None

def save_company_mapping_postgres(company, mapping):
    """Save a company mapping to PostgreSQL."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO company_mapping (company, mapping)
            VALUES (%s, %s)
            ON CONFLICT (company) DO UPDATE
            SET mapping = EXCLUDED.mapping
            """,
            (company, Json(mapping))
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Saved mapping for company: {company} to PostgreSQL")
        return True
    except Exception as e:
        logger.error(f"Error saving to PostgreSQL for {company}: {e}")
        return False

def delete_company_postgres(company):
    """Delete a company from PostgreSQL."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM company_mapping WHERE company = %s", (company,))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Deleted company: {company} from PostgreSQL")
        return True
    except Exception as e:
        logger.error(f"Error deleting from PostgreSQL: {e}")
        return False


# ==================== JSON FALLBACK FUNCTIONS ====================

def load_mapping_json():
    if not os.path.exists(MAP_FILE):
        data = {
            "companies": ["Default"],
            "mappings": {
                "Default": get_default_mapping()
            }
        }
        save_mapping_json(data)
        return data

    with open(MAP_FILE, "r") as f:
        data = json.load(f)

    if "companies" not in data:
        data = {
            "companies": ["Default"],
            "mappings": {
                "Default": data
            }
        }
        save_mapping_json(data)

    return data


def save_mapping_json(data):
    with open(MAP_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ==================== PUBLIC API (AUTO-SELECTS POSTGRES OR JSON) ====================

def load_companies():
    """Load companies - tries PostgreSQL first, falls back to JSON."""
    if DATABASE_URL:
        companies, _ = load_all_mappings_postgres()
        if companies is not None:
            return companies
    
    # Fallback to JSON
    logger.warning("Falling back to JSON file for companies")
    return load_mapping_json().get("companies", [])


def add_company(name):
    """Add a company - tries PostgreSQL first, falls back to JSON."""
    if name == "Default":
        raise ValueError("Cannot add Default company - it already exists")
    
    if DATABASE_URL:
        companies, _ = load_all_mappings_postgres()
        if companies is not None:
            if name in companies:
                raise ValueError(f"Company '{name}' already exists")
            
            success = save_company_mapping_postgres(name, get_default_mapping())
            if success:
                logger.info(f"Added company {name} to PostgreSQL")
                return
            else:
                logger.error(f"Failed to add {name} to PostgreSQL, trying JSON fallback")
    
    # Fallback to JSON
    logger.warning(f"Falling back to JSON file for adding company: {name}")
    data = load_mapping_json()
    if name in data["companies"]:
        raise ValueError(f"Company '{name}' already exists")
    data["companies"].append(name)
    data["mappings"][name] = get_default_mapping()
    save_mapping_json(data)


def delete_company(name):
    """Delete a company - tries PostgreSQL first, falls back to JSON."""
    if name == "Default":
        raise ValueError("Cannot delete Default company")
    
    if DATABASE_URL:
        success = delete_company_postgres(name)
        if success:
            logger.info(f"Deleted company {name} from PostgreSQL")
            return
        else:
            logger.error(f"Failed to delete {name} from PostgreSQL, trying JSON fallback")
    
    # Fallback to JSON
    logger.warning(f"Falling back to JSON file for deleting company: {name}")
    data = load_mapping_json()
    if name not in data["companies"]:
        raise ValueError(f"Company '{name}' not found")
    data["companies"].remove(name)
    del data["mappings"][name]
    save_mapping_json(data)


def get_company_mapping(name):
    """Get company mapping - tries PostgreSQL first, falls back to JSON."""
    if DATABASE_URL:
        companies, mappings = load_all_mappings_postgres()
        if companies is not None and name in mappings:
            return mappings[name]
    
    # Fallback to JSON
    logger.warning(f"Falling back to JSON file for getting mapping: {name}")
    data = load_mapping_json()
    if name not in data["mappings"]:
        raise ValueError(f"Company '{name}' not found")
    return data["mappings"][name]


def save_company_mapping(name, mapping):
    """Save company mapping - tries PostgreSQL first, falls back to JSON."""
    if DATABASE_URL:
        success = save_company_mapping_postgres(name, mapping)
        if success:
            logger.info(f"Saved mapping for {name} to PostgreSQL")
            return
        else:
            logger.error(f"Failed to save {name} to PostgreSQL, trying JSON fallback")
    
    # Fallback to JSON
    logger.warning(f"Falling back to JSON file for saving mapping: {name}")
    data = load_mapping_json()
    if name not in data["mappings"]:
        raise ValueError(f"Company '{name}' not found")
    data["mappings"][name] = mapping
    save_mapping_json(data)


# Optional: Migration function to move JSON data to PostgreSQL
def migrate_json_to_postgres():
    """One-time function to migrate existing JSON data to PostgreSQL."""
    if not DATABASE_URL:
        logger.error("No DATABASE_URL, cannot migrate")
        return False
    
    try:
        # Load from JSON
        json_data = load_mapping_json()
        companies = json_data.get("companies", [])
        mappings = json_data.get("mappings", {})
        
        # Save each to PostgreSQL
        for company in companies:
            if company in mappings:
                save_company_mapping_postgres(company, mappings[company])
                logger.info(f"Migrated {company} to PostgreSQL")
        
        logger.info(f"Migration complete: {len(companies)} companies migrated")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False