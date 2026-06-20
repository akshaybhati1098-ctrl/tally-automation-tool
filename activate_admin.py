import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

# ⚠️ Change this to your actual registered account email
TARGET_EMAIL = "akshaybhati1098@gmail.com" 

def make_user_admin():
    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL not found in environmental variables.")
        return
        
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET is_admin = TRUE WHERE email = %s RETURNING username", 
                (TARGET_EMAIL,)
            )
            user = cur.fetchone()
            if user:
                print(f"✅ Success! User '{user[0]}' has been promoted to Platform Admin.")
            else:
                print(f"❌ Error: Could not find any account with the email '{TARGET_EMAIL}'.")
        conn.commit()
    except Exception as e:
        print(f"❌ Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    make_user_admin()