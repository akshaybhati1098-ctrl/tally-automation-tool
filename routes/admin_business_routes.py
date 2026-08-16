from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from typing import Optional

from routes.admin_routes import enforce_admin_clearance, get_safe_base_context
from core.admin_telemetry import get_telemetry_db_connection
from psycopg2.extras import RealDictCursor

business_router = APIRouter(prefix="/admin", tags=["Business Analytics"])
templates = Jinja2Templates(directory="web/templates")

class UpgradeRequestIn(BaseModel):
    plan_name: str
    full_name: str
    email: EmailStr
    phone: str
    message: Optional[str] = None

@business_router.post("/api/subscription/request-upgrade")
async def request_upgrade(payload: UpgradeRequestIn, request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    plan_name = payload.plan_name.strip()
    if plan_name not in {"Basic", "Pro"}:
        raise HTTPException(status_code=400, detail="Invalid subscription plan")
    phone = payload.phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")

    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id FROM upgrade_requests
            WHERE user_id=%s AND status='pending'
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        if cur.fetchone():
            return JSONResponse({"success": False, "message": "You already have a pending upgrade request."})

        cur.execute("""
            INSERT INTO upgrade_requests
                (user_id, plan_name, full_name, email, phone, message, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
            RETURNING id, created_at
        """, (
            user_id, plan_name, payload.full_name.strip(),
            str(payload.email).strip().lower(), phone,
            (payload.message or "").strip() or None,
        ))
        row = cur.fetchone()
        conn.commit()
        return {
            "success": True,
            "request_id": row["id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

@business_router.get("/api/subscription/request-status")
async def subscription_request_status(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, plan_name, status, created_at, reviewed_at
            FROM upgrade_requests WHERE user_id=%s
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return {"exists": False}
        return {
            "exists": True, "id": row["id"], "plan_name": row["plan_name"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        }
    finally:
        cur.close()
        conn.close()

@business_router.get("/upgrade-requests", response_class=HTMLResponse)
async def view_upgrade_requests(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    return templates.TemplateResponse("admin/upgrade_requests.html", get_safe_base_context(request, admin_user))

@business_router.get("/api/upgrade-requests")
async def admin_upgrade_requests(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT r.id, r.user_id, u.username, u.email AS account_email,
                   r.plan_name, r.full_name, r.email, r.phone, r.message,
                   r.status, r.created_at, r.reviewed_at, r.reviewed_by
            FROM upgrade_requests r
            JOIN users u ON u.id=r.user_id
            ORDER BY CASE WHEN r.status='pending' THEN 0 ELSE 1 END, r.created_at DESC
        """)
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

@business_router.post("/api/upgrade-requests/{request_id}/approve")
async def approve_upgrade_request(request_id: int, request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, user_id, plan_name, status FROM upgrade_requests
            WHERE id=%s FOR UPDATE
        """, (request_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Upgrade request not found")
        if req["status"] != "pending":
            raise HTTPException(status_code=400, detail="Only pending requests can be approved")

        cur.execute("""
            SELECT id FROM subscription_plans
            WHERE plan_name=%s AND is_active=TRUE
        """, (req["plan_name"],))
        plan = cur.fetchone()
        if not plan:
            raise HTTPException(status_code=400, detail=f"Plan '{req['plan_name']}' is not active")

        cur.execute("""
            UPDATE users SET plan_id=%s, plan_name=%s, subscription_status='ACTIVE',
                plan_start=NOW(), plan_expiry=NOW() + INTERVAL '30 days'
            WHERE id=%s
        """, (plan["id"], req["plan_name"], req["user_id"]))

        cur.execute("""
            INSERT INTO feature_usage (user_id, feature_name, used_count, reset_date)
            VALUES (%s, 'party_matching', 0, CURRENT_DATE)
            ON CONFLICT (user_id, feature_name)
            DO UPDATE SET used_count=0, reset_date=CURRENT_DATE
        """, (req["user_id"],))

        cur.execute("""
            UPDATE upgrade_requests
            SET status='approved', reviewed_at=NOW(), reviewed_by=%s
            WHERE id=%s
        """, (admin_user, request_id))
        conn.commit()
        return {"success": True, "message": "Subscription activated successfully."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

@business_router.post("/api/upgrade-requests/{request_id}/reject")
async def reject_upgrade_request(request_id: int, request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    conn = get_telemetry_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE upgrade_requests
            SET status='rejected', reviewed_at=NOW(), reviewed_by=%s
            WHERE id=%s AND status='pending'
        """, (admin_user, request_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Pending upgrade request not found")
        conn.commit()
        return {"success": True, "message": "Upgrade request rejected."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

@business_router.get("/match-analytics", response_class=HTMLResponse)
async def view_match_analytics(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    context = get_safe_base_context(request, admin_user)
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT COUNT(*) as total_requests, ROUND(AVG(duration_ms)) as avg_duration,
                   ROUND(AVG((details->>'match_percentage')::numeric),2) as avg_match_rate,
                   SUM((details->>'rows_processed')::int) as total_rows
            FROM business_events WHERE event_type='match_party' AND status='success'
        """)
        context["kpis"] = cur.fetchone()
        cur.execute("""
            SELECT username,status,duration_ms,created_at,
                   (details->>'rows_processed') as rows,
                   (details->>'matched_rows') as matched,
                   (details->>'unmatched_rows') as unmatched
            FROM business_events WHERE event_type='match_party'
            ORDER BY created_at DESC LIMIT 50
        """)
        context["logs"] = cur.fetchall()
    finally:
        cur.close(); conn.close()
    return templates.TemplateResponse("admin/match_analytics.html", context)

@business_router.get("/conversion-analytics", response_class=HTMLResponse)
async def view_conversion_analytics(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    context = get_safe_base_context(request, admin_user)
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT COUNT(*) as total_conversions, ROUND(AVG(duration_ms)) as avg_duration,
                   SUM((details->>'rows_processed')::int) as total_rows,
                   SUM((details->>'exception_rows')::int) as total_exceptions
            FROM business_events WHERE event_type='convert_xml' AND status='success'
        """)
        context["kpis"] = cur.fetchone()
        cur.execute("""
            SELECT username,status,duration_ms,created_at,
                   (details->>'rows_processed') as rows,
                   (details->>'voucher_type') as vtype,
                   (details->>'exception_rows') as exceptions
            FROM business_events WHERE event_type='convert_xml'
            ORDER BY created_at DESC LIMIT 50
        """)
        context["logs"] = cur.fetchall()
    finally:
        cur.close(); conn.close()
    return templates.TemplateResponse("admin/conversion_analytics.html", context)
