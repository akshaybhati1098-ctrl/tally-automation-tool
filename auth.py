from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from database import get_db

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# Dependency to get current user from request cookies
async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
        
    # 🔥 LIVE SESSION VERIFICATION: Ensure the account status hasn't changed mid-session
    with get_db() as conn:
        user = conn.execute(
            "SELECT username, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        
    if not user:
        return None
        
    # Kick the user out immediately if they are flagged as suspended
    is_active_val = user["is_active"] if isinstance(user, dict) else user[1]
    if is_active_val == 0 or is_active_val is False:
        return None
        
    return {"id": int(user_id), "username": payload.get("username")}