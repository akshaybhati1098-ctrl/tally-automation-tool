from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor
from routes.admin_routes import enforce_admin_clearance, get_safe_base_context
from core.admin_telemetry import get_telemetry_db_connection

business_router = APIRouter(prefix="/admin", tags=["Business Analytics"])
templates = Jinja2Templates(directory="web/templates")

@business_router.get("/match-analytics", response_class=HTMLResponse)
async def view_match_analytics(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    context = get_safe_base_context(request, admin_user)
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Aggregated KPI Metrics using JSONB parsing
        cur.execute("""
            SELECT 
                COUNT(*) as total_requests,
                ROUND(AVG(duration_ms)) as avg_duration,
                ROUND(AVG((details->>'match_percentage')::numeric), 2) as avg_match_rate,
                SUM((details->>'rows_processed')::int) as total_rows
            FROM business_events 
            WHERE event_type = 'match_party' AND status = 'success'
        """)
        context["kpis"] = cur.fetchone()

        # Recent Logs Table
        cur.execute("""
            SELECT username, status, duration_ms, created_at,
                   (details->>'rows_processed') as rows,
                   (details->>'matched_rows') as matched,
                   (details->>'unmatched_rows') as unmatched
            FROM business_events 
            WHERE event_type = 'match_party' 
            ORDER BY created_at DESC LIMIT 50
        """)
        context["logs"] = cur.fetchall()
    finally:
        cur.close()
        conn.close()
        
    return templates.TemplateResponse("admin/match_analytics.html", context)

@business_router.get("/conversion-analytics", response_class=HTMLResponse)
async def view_conversion_analytics(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    context = get_safe_base_context(request, admin_user)
    conn = get_telemetry_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT 
                COUNT(*) as total_conversions,
                ROUND(AVG(duration_ms)) as avg_duration,
                SUM((details->>'rows_processed')::int) as total_rows,
                SUM((details->>'exception_rows')::int) as total_exceptions
            FROM business_events 
            WHERE event_type = 'convert_xml' AND status = 'success'
        """)
        context["kpis"] = cur.fetchone()

        cur.execute("""
            SELECT username, status, duration_ms, created_at,
                   (details->>'rows_processed') as rows,
                   (details->>'voucher_type') as vtype,
                   (details->>'exception_rows') as exceptions
            FROM business_events 
            WHERE event_type = 'convert_xml' 
            ORDER BY created_at DESC LIMIT 50
        """)
        context["logs"] = cur.fetchall()
    finally:
        cur.close()
        conn.close()
        
    return templates.TemplateResponse("admin/conversion_analytics.html", context)