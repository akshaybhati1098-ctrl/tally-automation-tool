 #!/usr/bin/env python3
import os
import sys
import bcrypt
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

def execute_migrations():
    if not DATABASE_URL:
        print("❌ CRITICAL: DATABASE_URL variable missing from the runtime context.")
        sys.exit(1)

    print("🌐 Connecting to target PostgreSQL data instance...")
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Schema Deployment Execution
        print("🛠️  Applying relational tables configuration schema...")
        
        cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER,
            username VARCHAR(150),
            event_type VARCHAR(100) NOT NULL,
            endpoint VARCHAR(255),
            status VARCHAR(50) NOT NULL,
            error_message TEXT,
            execution_time_ms INTEGER,
            details JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Performance optimization indices
        cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_event_type ON admin_logs(event_type);")

        # Table state synchronizations
        cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name='users' AND column_name='is_active';
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;")
            
        cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name='users' AND column_name='last_login';
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE users ADD COLUMN last_login TIMESTAMP WITH TIME ZONE;")

        # Seed Primary Core Administrator Account securely if not already present
        admin_username = os.environ.get("ADMIN_INIT_USER", "superadmin")
        admin_password = os.environ.get("ADMIN_INIT_PASS", "Production_Secure_Admin_2026!")
        
        cur.execute("SELECT id FROM admin_users WHERE username = %s;", (admin_username,))
        if not cur.fetchone():
            print(f"🔑 Generating core enterprise seed credentials for user: '{admin_username}'...")
            hashed_pass = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cur.execute("""
                INSERT INTO admin_users (username, password_hash) 
                VALUES (%s, %s);
            """, (admin_username, hashed_pass))
            print("✅ Initial administrative account provisioned successfully.")
        else:
            print("ℹ️  Primary administrator profile matches present system logs. Seeding skipped.")

        conn.commit()
        print("🚀 Systems migration cycle finalized successfully without processing friction.")

    except Exception as e:
        conn.rollback()
        print(f"❌ CRITICAL MIGRATION ERROR: Encountered structural failure processing queries: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    execute_migrations()