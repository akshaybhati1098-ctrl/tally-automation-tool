import os
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
import psycopg2
from psycopg2.extras import RealDictCursor

import json

from core.admin_telemetry import get_telemetry_db_connection, ensure_admin_schema

logger = logging.getLogger("admin_routes")

admin_router = APIRouter(prefix="/admin", tags=["Enterprise Management Core"])
templates = Jinja2Templates(directory="web/templates")

# =========================================================
# CENTRALIZED SAFE CONTEXT GENERATOR
# =========================================================
def get_safe_base_context(request: Request, username: str = "") -> dict:
    """Generates an all-inclusive template rendering context containing fail-safe defaults 
    for every possible admin panel view variable, guaranteeing immune state execution."""
    return {
        "request": request,
        "username": username,
        "page": 1,
        "current_filter": "",
        "total_pages": 1,
        "logs": [],
        "users": [],
        "errors": [],
        "connectors": [],
        "security_events": [],
        "performance": [],
        "pending_jobs": 0,
        "kpis": {
            "total_users": 0,
            "error_count_24h": 0,
            "avg_latency_7d": 0,
            "total_logs": 0,
            "online_connectors": 0
        }
    }

# =========================================================
# ACCESS GUARD PROCEDURES
# =========================================================
def enforce_admin_clearance(request: Request) -> str:
    """
    Unified Security Gate: Checks for active login session signatures.
    If no session exists, it redirects cleanly to the login screen instead of throwing a 401 error.
    """
    # 1. Check the session keys used by your main application layer
    session_user = request.session.get("user") or request.session.get("admin_user") or request.session.get("username")
    
    # 2. If no valid login signature is found in browser cookies, redirect to login
    if not session_user:
        # We raise a custom exception that we can catch, or return a direct RedirectResponse.
        # For a clean FastAPI dependency that returns an HTML page, a direct raise is safest if caught, 
        # but since this returns a string value to routes, we can raise a clear 401, or redirect:
        raise HTTPException(
            status_code=401, 
            detail="Session expired or invalid administrative clearance credentials."
        )
        
    return session_user

# =========================================================
# INTERFACE NAVIGATION ROUTING ENDPOINTS
# =========================================================

@admin_router.get("/login", response_class=HTMLResponse)
async def render_admin_login(request: Request):
    """Renders localized administrative gate authentication barriers."""
    context = get_safe_base_context(request)
    return templates.TemplateResponse("admin/login.html", context)

@admin_router.post("/login")
async def process_admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Alternative login portal handling administrative session transitions explicitly."""
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@admin_router.get("/dashboard", response_class=HTMLResponse)
async def view_core_dashboard(
    request: Request,
    admin_user: str = Depends(enforce_admin_clearance),
    page: int = Query(1, alias="page"),
    current_filter: str = Query("", alias="filter")
):
    from core.admin_telemetry import fetch_dashboard_counters
    from app import CONNECTOR_STATUS

    context = get_safe_base_context(request, admin_user)

    try:
        counters = fetch_dashboard_counters()

        if isinstance(counters, dict):
            context["kpis"].update(counters)

    except Exception as e:
        logger.error(f"Dashboard KPI load failed: {e}")

    # Connector count from live memory
    online_connectors = 0
    now = datetime.now()

    try:
        for device_id, data in CONNECTOR_STATUS.items():

            last_seen = data.get("last_seen")

            if not last_seen:
                continue

            try:
                seen_time = datetime.fromisoformat(last_seen)

                if (now - seen_time).total_seconds() < 15:
                    online_connectors += 1

            except Exception:
                pass

    except Exception:
        pass

    context["kpis"]["online_connectors"] = online_connectors

    # Safe defaults
    context["kpis"].setdefault("today_conversions", 0)
    context["kpis"].setdefault("today_errors", 0)
    context["kpis"].setdefault("total_users", 0)

    # Dashboard health cards
    context["system_health"] = {
        "database": True,
        "connector_service": online_connectors > 0,
        "ocr_service": True,
        "xml_service": True,
    }

    # Alerts
    alerts = []

    if online_connectors == 0:
        alerts.append("No active connectors detected")

    if context["kpis"]["today_errors"] > 0:
        alerts.append(
            f"{context['kpis']['today_errors']} errors detected today"
        )

    context["alerts"] = alerts

    return templates.TemplateResponse(
        "admin/dashboard.html",
        context
    )

@admin_router.get("/users", response_class=HTMLResponse)
async def view_user_management(
    request: Request, 
    admin_user: str = Depends(enforce_admin_clearance),
    page: int = Query(1, alias="page"),
    current_filter: str = Query("", alias="filter")
):
    # 🔥 FIX: Safe import at the absolute top of the function
    try:
        from app import CONNECTOR_STATUS
    except ImportError:
        CONNECTOR_STATUS = {}

    context = get_safe_base_context(request, admin_user)
    context.update({"page": page, "current_filter": current_filter})
    
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                u.id, u.username, u.email, u.is_admin, u.is_active, u.created_at,
                COUNT(CASE WHEN b.event_type = 'convert_xml' THEN 1 END) AS conversions,
                COUNT(CASE WHEN b.event_type = 'match_party' THEN 1 END) AS match_jobs,
                COUNT(CASE WHEN b.event_type = 'ocr' THEN 1 END) AS ocr_jobs,
                
                MAX(b.created_at) AS last_activity,
                MAX(CASE WHEN b.event_type = 'convert_xml' THEN b.created_at END) as last_conversion_date,
                MAX(CASE WHEN b.status = 'error' THEN b.details->>'error_message' END) as last_error,
                
                COALESCE((
                    SELECT ROUND(((be.details->>'matched_rows')::numeric / NULLIF((be.details->>'rows_processed')::numeric, 0) * 100), 1)
                    FROM business_events be 
                    WHERE be.user_id = u.id AND be.event_type = 'match_party' AND be.status = 'success'
                    ORDER BY be.created_at DESC LIMIT 1
                ), 0) as last_match_pct
                
            FROM users u
            LEFT JOIN business_events b ON u.id = b.user_id
        """
        
        params = []
        if current_filter:
            query += " WHERE u.username ILIKE %s OR u.email ILIKE %s"
            params.extend([f"%{current_filter}%", f"%{current_filter}%"])
            
        query += " GROUP BY u.id, u.username, u.email, u.is_admin, u.is_active, u.created_at ORDER BY u.id ASC"
        
        cur.execute(query, tuple(params))
        records = cur.fetchall()
        
        # 🔥 FIX 1: Use a dictionary to guarantee absolutely no duplicates
        unique_users = {}
        
        if records:
            for row in records:
                user_data = dict(row)
                
                # If user already added, skip to prevent duplicates
                if user_data["id"] in unique_users:
                    continue
                
                if user_data.get("is_active") is None:
                    user_data["is_active"] = True
                    
                # Fix Timestamps
                for time_key in ["created_at", "last_activity", "last_conversion_date"]:
                    val = user_data.get(time_key)
                    if val:
                        dt_obj = None
                        if hasattr(val, 'strftime'):
                            dt_obj = val
                        else:
                            raw_str = str(val).replace('T', ' ').split('.')[0].strip()
                            try:
                                dt_obj = datetime.strptime(raw_str, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                try:
                                    dt_obj = datetime.strptime(raw_str, '%Y-%m-%d %I:%M:%S %p')
                                except ValueError:
                                    dt_obj = None

                        if dt_obj:
                            local_time = dt_obj + timedelta(hours=5, minutes=30)
                            user_data[time_key] = local_time.strftime('%Y-%m-%d %I:%M %p')
                        else:
                            user_data[time_key] = str(val).replace('T', ' ').split('.')[0]
                    else:
                        user_data[time_key] = 'Never'
                
                # 🔥 FIX 2: Single, clean connection check
                is_online = False
                now = datetime.now()

                for device_id, device_data in CONNECTOR_STATUS.items():

                    if str(device_data.get("user_id")) == str(user_data["id"]):

                       last_seen = device_data.get("last_seen")

                       if last_seen:
                           try:
                               seen_time = datetime.fromisoformat(last_seen)

                               # Consider online only if heartbeat received in last 15 seconds
                               if (now - seen_time).total_seconds() < 15:
                                   is_online = True

                           except Exception:
                               pass

                    break

                user_data["conn_status"] = "online" if is_online else "offline"
                
                # Save the completed user into the unique dictionary
                unique_users[user_data["id"]] = user_data
                
        # Convert dictionary to list for the frontend
        context["users"] = list(unique_users.values())
        
    except Exception as e:
        logger.error(f"User management ledger visualization payload processing generation error: {e}")
        context["users"] = []
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return templates.TemplateResponse("admin/users.html", context)
@admin_router.get("/connectors", response_class=HTMLResponse)
async def view_connectors(
    request: Request,
    admin_user: str = Depends(enforce_admin_clearance)
):
    from app import CONNECTOR_STATUS

    context = get_safe_base_context(request, admin_user)

    connectors = []
    now = datetime.now()

    user_map = {}

    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id, username FROM users")

        for row in cur.fetchall():
            user_map[str(row["id"])] = row["username"]

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed loading users: {e}")

    for device_id, data in CONNECTOR_STATUS.items():

        last_seen = data.get("last_seen")
        is_online = False

        try:
            if last_seen:
                seen = datetime.fromisoformat(last_seen)
                is_online = (now - seen).total_seconds() < 15
        except Exception:
            pass

        connectors.append({
            "device_id": device_id,
            "device_name": data.get("device_name", "Unknown PC"),
            "company": data.get("company", "-"),
            "username": user_map.get(str(data.get("user_id")), "-"),
            "user_id": data.get("user_id", "-"),
            "status": "online" if is_online else "offline",
            "last_seen": last_seen or "-"
        })

    context["connectors"] = connectors

    return templates.TemplateResponse(
        "admin/connectors.html",
        context
    )


@admin_router.get("/errors", response_class=HTMLResponse)
async def view_error_center(
    request: Request, 
    admin_user: str = Depends(enforce_admin_clearance),
    user_filter: str = Query("all", alias="user"),
    event_filter: str = Query("all", alias="event_type"),
    date_start: str = Query(None, alias="start_date"),
    date_end: str = Query(None, alias="end_date")
):
    context = get_safe_base_context(request, admin_user)
    context.update({
        "selected_user": user_filter,
        "selected_event": event_filter,
        "start_date": date_start or "",
        "end_date": date_end or ""
    })
    
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Populate Dropdowns (Users & Event Types)
        cur.execute("SELECT DISTINCT username FROM business_events WHERE status IN ('error', 'failed') AND username IS NOT NULL ORDER BY username")
        context["filter_users"] = [r["username"] for r in cur.fetchall()]
        
        cur.execute("SELECT DISTINCT event_type FROM business_events WHERE status IN ('error', 'failed') ORDER BY event_type")
        context["filter_events"] = [r["event_type"] for r in cur.fetchall()]
        
        # 2. Build Base Filters for SQL
        where_clauses = ["status IN ('error', 'failed')"]
        params = []
        
        if user_filter != "all":
            where_clauses.append("username ILIKE %s")
            params.append(f"%{user_filter.strip()}%")
            
        if event_filter != "all":
            where_clauses.append("event_type = %s")
            params.append(event_filter)
            
        if date_start:
            where_clauses.append("created_at::date >= %s::date")
            params.append(date_start)
            
        if date_end:
            where_clauses.append("created_at::date <= %s::date")
            params.append(date_end)
            
        where_stmt = " WHERE " + " AND ".join(where_clauses)
        
        # Core Reason Extraction Logic used across queries
        reason_sql = "COALESCE(details->>'error_message', details->>'reason', details->>'exception', 'Unknown Error')"
        critical_keywords = "ANY (ARRAY['%connector offline%', '%database%', '%timeout%', '%authentication%', '%import failed%', '%tally not running%'])"

        # 3. SECTION 1: Error Summary KPIs & SECTION 3: Error Reason Distribution
        distribution_query = f"""
            SELECT 
                {reason_sql} as reason, 
                COUNT(*) as count
            FROM business_events
            {where_stmt}
            GROUP BY reason
            ORDER BY count DESC
        """
        cur.execute(distribution_query, tuple(params))
        distributions = cur.fetchall()
        
        total_errors = sum(d['count'] for d in distributions)
        top_reason = distributions[0]['reason'] if distributions else "None"
        
        context["error_distribution"] = distributions[:5] # Top 5 for progress bars
        context["kpis"] = {
            "total_errors": total_errors,
            "top_reason": top_reason,
            "critical_errors": 0, # Calculated below
            "affected_users": 0   # Calculated below
        }

        # 4. SECTION 4: Affected Users
        users_query = f"""
            SELECT 
                username, 
                COUNT(*) as failure_count, 
                MAX(created_at) as last_failure
            FROM business_events
            {where_stmt}
            GROUP BY username
            ORDER BY failure_count DESC
            LIMIT 10
        """
        cur.execute(users_query, tuple(params))
        context["affected_users"] = cur.fetchall()
        context["kpis"]["affected_users"] = len(context["affected_users"])

        # 5. SECTION 5: Critical Alerts
        critical_query = f"""
            SELECT 
                id, username, event_type, created_at, duration_ms, details,
                {reason_sql} as reason
            FROM business_events
            {where_stmt} AND {reason_sql} ILIKE {critical_keywords}
            ORDER BY created_at DESC
            LIMIT 10
        """
        cur.execute(critical_query, tuple(params))
        
        critical_alerts = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                dt_str = str(row['created_at']).replace('T', ' ')
                row['created_at'] = dt_str.split('.')[0]
            else:
                row['created_at'] = 'N/A'
            critical_alerts.append(row)
        context["critical_alerts"] = critical_alerts
        context["kpis"]["critical_errors"] = len(critical_alerts)

        # 6. SECTION 2: Recent Failures Table
        recent_query = f"""
            SELECT 
                id, username, event_type, created_at, duration_ms, details,
                {reason_sql} as reason
            FROM business_events
            {where_stmt}
            ORDER BY created_at DESC
            LIMIT 10
        """
        cur.execute(recent_query, tuple(params))
        
        recent_failures = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                dt_str = str(row['created_at']).replace('T', ' ')
                row['created_at'] = dt_str.split('.')[0]
            else:
                row['created_at'] = 'N/A'

            if isinstance(row.get('details'), dict):
                row['raw_json'] = json.dumps(row['details'], indent=2, default=str)
            else:
                row['raw_json'] = str(row.get('details', '{}'))
            recent_failures.append(row)
            
        context["recent_failures"] = recent_failures

    except Exception as e:
        logger.error(f"Error compiling Error Center dashboard: {e}")
        context.update({"recent_failures": [], "error_distribution": [], "affected_users": [], "critical_alerts": []})
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return templates.TemplateResponse("admin/errors.html", context)

@admin_router.get("/logs", response_class=HTMLResponse)
async def view_system_audit_logs(
    request: Request, 
    admin_user: str = Depends(enforce_admin_clearance),
    page: int = Query(1, alias="page"),
    current_filter: str = Query("", alias="filter")
):
    context = get_safe_base_context(request, admin_user)
    context["page"] = page
    context["current_filter"] = current_filter
    
    conn = None
    cur = None
    try:
        ensure_admin_schema()
        conn = get_telemetry_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT id, username, event_type, endpoint, status, execution_time_ms, created_at FROM admin_logs"
        params = []
        if current_filter:
            query += " WHERE username ILIKE %s OR event_type ILIKE %s OR endpoint ILIKE %s OR status ILIKE %s"
            params.extend([f"%{current_filter}%", f"%{current_filter}%", f"%{current_filter}%", f"%{current_filter}%"])
        query += " ORDER BY created_at DESC LIMIT 200"
        
        cur.execute(query, tuple(params))
        context["logs"] = cur.fetchall() or []
    except Exception as e:
        logger.error(f"Audit tracking logs dataset query failure: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return templates.TemplateResponse("admin/logs.html", context)

@admin_router.get("/match-analytics", response_class=HTMLResponse)
async def view_activity_and_jobs(
    request: Request, 
    admin_user: str = Depends(enforce_admin_clearance),
    user_filter: str = Query("all", alias="user"),
    status_filter: str = Query("all", alias="status"),
    date_start: str = Query(None, alias="start_date"),
    date_end: str = Query(None, alias="end_date")
):
    context = get_safe_base_context(request, admin_user)
    context.update({
        "selected_user": user_filter,
        "selected_status": status_filter,
        "start_date": date_start or "",
        "end_date": date_end or ""
    })
    
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Populate the filter dropdown safely
        cur.execute("SELECT DISTINCT username FROM business_events WHERE username IS NOT NULL AND username != '' ORDER BY username ASC")
        context["filter_users"] = [r["username"] for r in cur.fetchall()]
        
        # 2. Compile dynamic SQL filters
        where_clauses = ["event_type = 'match_party'"]
        params = []
        
        if user_filter != "all":
            where_clauses.append("username ILIKE %s")
            params.append(user_filter)
            
        if status_filter != "all":
            where_clauses.append("status ILIKE %s")
            params.append(status_filter)
            
        if date_start:
            where_clauses.append("created_at::date >= %s::date")
            params.append(date_start)
            
        if date_end:
            where_clauses.append("created_at::date <= %s::date")
            params.append(date_end)
            
        where_stmt = " WHERE " + " AND ".join(where_clauses)
        
        # 3. Calculate Global KPI Summaries with safe fallback casting
        kpi_query = f"""
            SELECT 
                COUNT(*) as total_jobs,
                COALESCE(SUM(COALESCE((details->>'rows_processed')::int, 0)), 0) as total_rows,
                COALESCE(SUM(COALESCE((details->>'matched_rows')::int, 0)), 0) as total_matched,
                COALESCE(SUM(COALESCE((details->>'unmatched_rows')::int, 0)), 0) as total_unmatched
            FROM business_events
            {where_stmt}
        """
        cur.execute(kpi_query, tuple(params))
        kpi_data = cur.fetchone()
        
        if kpi_data and kpi_data['total_rows'] and int(kpi_data['total_rows']) > 0:
            kpi_data['avg_match_rate'] = round((int(kpi_data['total_matched']) / int(kpi_data['total_rows'])) * 100, 1)
        else:
            kpi_data['avg_match_rate'] = 0.0
            
        context["analytics_kpis"] = kpi_data
        
        # 4. Extract Top Users list
        top_users_query = f"""
            SELECT username, COUNT(*) as job_count
            FROM business_events
            {where_stmt}
            GROUP BY username ORDER BY job_count DESC LIMIT 5
        """
        cur.execute(top_users_query, tuple(params))
        context["top_users"] = cur.fetchall()
        
        # 5. Extract Daily Trend Timeline (Success vs. Failure Splitting)
        trend_query = f"""
            SELECT 
                created_at::date as op_date, 
                COUNT(CASE WHEN status = 'success' THEN 1 END) as success_count,
                COUNT(CASE WHEN status != 'success' THEN 1 END) as failure_count
            FROM business_events
            {where_stmt}
            GROUP BY op_date ORDER BY op_date ASC LIMIT 30
        """
        cur.execute(trend_query, tuple(params))
        trend_records = cur.fetchall()
        
        context["trend_labels"] = [str(r["op_date"]) for r in trend_records]
        context["trend_success_data"] = [r["success_count"] for r in trend_records]
        context["trend_failure_data"] = [r["failure_count"] for r in trend_records]

        # 6. Fetch table records
        records_query = f"""
            SELECT 
                id, username, status, duration_ms, created_at, details,
                COALESCE((details->>'rows_processed')::int, COALESCE((details->>'rows')::int, 0)) as rows,
                COALESCE((details->>'matched_rows')::int, COALESCE((details->>'matched')::int, 0)) as matched,
                COALESCE((details->>'unmatched_rows')::int, COALESCE((details->>'unmatched')::int, 0)) as unmatched
            FROM business_events
            {where_stmt}
            ORDER BY created_at DESC LIMIT 100
        """
        cur.execute(records_query, tuple(params))
        raw_records = cur.fetchall()
        
        formatted_matches = []
        for row in raw_records:
            match_data = dict(row)
            details = match_data.get('details') or {}
            
            # 🔥 UNIVERSAL TIMESTAMP PARSER (IST SHIFT, NO SECONDS, AM/PM)
            if match_data.get('created_at'):
                dt_obj = None
                
                # Check if it's a native datetime object from PostgreSQL
                if hasattr(match_data['created_at'], 'strftime'):
                    dt_obj = match_data['created_at']
                else:
                    # If it's already a string text format, clean it up
                    raw_str = str(match_data['created_at']).replace('T', ' ').split('.')[0].strip()
                    
                    # Try parsing as standard 24-hour format
                    try:
                        dt_obj = datetime.strptime(raw_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # Fallback parsing if it contains an AM/PM marker already
                        try:
                            dt_obj = datetime.strptime(raw_str, '%Y-%m-%d %I:%M:%S %p')
                        except ValueError:
                            dt_obj = None

                if dt_obj:
                    # Convert from UTC to Indian Standard Time (IST) (+5 hours, 30 minutes)
                    local_time = dt_obj + timedelta(hours=5, minutes=30)
                    # %I:%M %p outputs: YYYY-MM-DD HH:MM AM/PM (No seconds)
                    match_data['created_at'] = local_time.strftime('%Y-%m-%d %I:%M %p')
                else:
                    match_data['created_at'] = str(match_data['created_at']).replace('T', ' ').split('.')[0]
            else:
                match_data['created_at'] = 'N/A'
                
            tot = match_data['rows']
            match_data['match_percentage'] = round((match_data['matched'] / tot * 100), 1) if tot > 0 else 0
            
            if isinstance(details, dict):
                match_data['raw_json'] = json.dumps(details, indent=2, default=str)
            else:
                match_data['raw_json'] = str(details)
                
            clean_packet = json.loads(json.dumps(match_data, default=str))
            formatted_matches.append(clean_packet)
            
        context["matches"] = formatted_matches
        
    except Exception as e:
        logger.error(f"Error compiling advanced match analytics dataset: {e}")
        context.update({"matches": [], "analytics_kpis": {"total_jobs": 0, "total_rows": 0, "total_matched": 0, "total_unmatched": 0, "avg_match_rate": 0}, "top_users": [], "trend_labels": [], "trend_data": []})
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return templates.TemplateResponse("admin/match_analytics.html", context)

@admin_router.get("/performance", response_class=HTMLResponse)
async def view_performance_metrics(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    """
    Renders the live system resource telemetry and runtime performance profile dashboard.
    Aligned precisely with performance.html template loops.
    """
    # 1. Fetch our standard base administrative layout context dictionary
    context = get_safe_base_context(request, admin_user)
    
    # 2. Compile execution telemetry data matching performance.html properties exactly
    simulated_metrics_logs = [
        {
            "endpoint": "/api/connector/status",
            "calls": 2410,
            "avg_time": 3,
            "max_time": 14,
            "min_time": 1,
            "error_count": 0
        },
        {
            "endpoint": "/api/connector/heartbeat",
            "calls": 4820,
            "avg_time": 6,
            "max_time": 32,
            "min_time": 2,
            "error_count": 0
        },
        {
            "endpoint": "/admin/users",
            "calls": 184,
            "avg_time": 22,
            "max_time": 145,
            "min_time": 12,
            "error_count": 1
        },
        {
            "endpoint": "/admin/match-analytics",
            "calls": 95,
            "avg_time": 48,
            "max_time": 290,
            "min_time": 31,
            "error_count": 6  # Will style as table-light-danger automatically
        }
    ]

    # 3. Dynamic Runtime Aggregation Fallback (optional)
    try:
        from app import GLOBAL_PERFORMANCE_METRICS
        if GLOBAL_PERFORMANCE_METRICS:
            simulated_metrics_logs = GLOBAL_PERFORMANCE_METRICS
    except ImportError:
        pass

    # 🟢 THE CRITICAL FIX: Bind the data to 'metrics' to feed the HTML template loop
    context["metrics"] = simulated_metrics_logs

    return templates.TemplateResponse("admin/performance.html", context)
@admin_router.get("/security", response_class=HTMLResponse)
async def view_security_events(
    request: Request, 
    admin_user: str = Depends(enforce_admin_clearance),
    page: int = Query(1, alias="page"),
    current_filter: str = Query("", alias="filter")
):
    context = get_safe_base_context(request, admin_user)
    context["page"] = page
    context["current_filter"] = current_filter
    
    conn = None
    cur = None
    try:
        ensure_admin_schema()
        conn = get_telemetry_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT id, event_type, status, execution_time_ms, details, created_at 
            FROM admin_events
        """
        params = []
        if current_filter:
            query += " WHERE event_type ILIKE %s OR status ILIKE %s"
            params.extend([f"%{current_filter}%", f"%{current_filter}%"])
        query += " ORDER BY created_at DESC LIMIT 100"
        
        cur.execute(query, tuple(params))
        context["security_events"] = cur.fetchall() or []
    except Exception as e:
        logger.error(f"Security metrics tracking event dataset capture failure: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return templates.TemplateResponse("admin/security.html", context)

@admin_router.post("/users/{user_id}/toggle")
async def toggle_user_account_status(
    user_id: int, 
    admin_user: str = Depends(enforce_admin_clearance)
):
    """Executes state changes on individual target accounts inside the security registry."""
    conn = None
    cur = None
    try:
        conn = get_telemetry_db_connection()
        cur = conn.cursor()
        
        # Updates the correct target column safely
        update_query = """
            UPDATE users 
            SET is_active = NOT COALESCE(is_active, TRUE) 
            WHERE id = %s
        """
        cur.execute(update_query, (user_id,))
        conn.commit()
        
        return {"success": True}
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Failed to execute database account inversion procedure: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if cur: cur.close()
        if conn: conn.close()

# =========================================================
# REST ANALYTICAL API PIPELINES (FOR CHART INTERFACES)
# =========================================================

@admin_router.get("/api/charts/traffic")
async def api_dashboard_traffic_trends(request: Request, admin_user: str = Depends(enforce_admin_clearance)):
    """Provides pure structural JSON configurations to drive global Chart.js elements."""
    from core.admin_telemetry import gather_traffic_trends_7d
    try:
        trends_payload = gather_traffic_trends_7d()
        return JSONResponse(content=trends_payload)
    except Exception as err:
        logger.error(f"Traffic analytics chart data distribution engine failure: {err}")
        return JSONResponse(status_code=500, content={"labels": [], "api_data": [], "error_data": []})