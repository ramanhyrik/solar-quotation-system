from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from contextlib import asynccontextmanager
import secrets
from database import get_db, get_cursor, init_database, hash_password, verify_password, generate_quote_number, create_session_db, get_session_db, delete_session_db, cleanup_expired_sessions_db
from datetime import datetime
from decimal import Decimal
import json
import os
import shutil
import traceback
import re
import io
import glob
from urllib.parse import quote as url_quote
from pdf_generator import generate_quote_pdf, generate_leasing_quote_pdf
from quote_defaults import (
    QUOTE_TEXT_FIELD_MAP,
    calculate_annual_income,
    calculate_quarterly_value,
    get_effective_tariff_rate,
    get_legacy_quote_text_defaults,
    render_quote_template,
)
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

# Detect if running in production (on Render or other HTTPS environment)
IS_PRODUCTION = os.getenv("RENDER") is not None or os.getenv("PRODUCTION") is not None

# Persistent storage for user uploads (persistent disk in production, local in development)
PERSISTENT_UPLOADS_DIR = "/opt/render/project/src/uploads" if os.getenv("RENDER") else "static"

# Define all storage directories (user uploads go to persistent disk)
UPLOADS_DIR = os.path.join(PERSISTENT_UPLOADS_DIR, "uploads")
ROOF_IMAGES_DIR = os.path.join(PERSISTENT_UPLOADS_DIR, "roof_images")
ROOF_VISUALIZATIONS_DIR = os.path.join(PERSISTENT_UPLOADS_DIR, "roof_visualizations")
SIGNATURES_DIR = os.path.join(PERSISTENT_UPLOADS_DIR, "quote_signatures")
SIGNED_PDFS_DIR = os.path.join(PERSISTENT_UPLOADS_DIR, "signed_pdfs")
QUOTE_IMAGES_DIR = os.path.join(PERSISTENT_UPLOADS_DIR, "quote_images")

# Detection job store for async SAM processing
# Format: {job_id: {"status": "pending|running|completed|failed", "result": {...}, "error": str}}
detection_jobs = {}

# Thread pool for CPU-intensive SAM detection
detection_executor = ThreadPoolExecutor(max_workers=2)

def decimal_to_float(value):
    """Convert Decimal to float, or return value as-is if not Decimal"""
    if isinstance(value, Decimal):
        return float(value)
    return value

def convert_decimals_in_dict(data: dict) -> dict:
    """Convert all Decimal values in a dictionary to floats"""
    return {key: decimal_to_float(val) for key, val in data.items()}

def ensure_datetime(value):
    """Convert string to datetime if needed, or return datetime as-is"""
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    elif isinstance(value, datetime):
        return value
    else:
        raise ValueError(f"Expected datetime or str, got {type(value)}")

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing or replacing non-ASCII characters.
    This ensures the filename works in HTTP headers.
    """
    # Remove non-ASCII characters and replace spaces with underscores
    sanitized = re.sub(r'[^\x00-\x7F]+', '', filename)
    sanitized = sanitized.replace(' ', '_')
    # Remove any remaining problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', sanitized)
    # If filename becomes empty after sanitization, use a default
    if not sanitized or sanitized == '.pdf':
        sanitized = 'Quote.pdf'
    return sanitized


LEGACY_QUOTE_DEFAULTS = get_legacy_quote_text_defaults()
QUOTE_RENDER_PRICING_FIELDS = (
    "trees_multiplier",
    "degradation_rate",
    "operating_cost_base",
    "operating_cost_increase",
    "leasing_payment_ratio",
    "basic_assumptions_default",
    "revenue_calculation_default",
    "summary_default",
    "environmental_impact_default",
)


def format_template_number(value, decimals=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""

    if decimals == 0:
        return f"{int(round(number)):,}"

    return f"{number:,.{decimals}f}".rstrip("0").rstrip(".")


def get_latest_pricing(cursor):
    cursor.execute("SELECT * FROM pricing_parameters ORDER BY id DESC LIMIT 1")
    pricing = cursor.fetchone()
    return convert_decimals_in_dict(dict(pricing)) if pricing else {}


def calculate_quote_cashflow_25_years(quote_data: dict, pricing: dict) -> float:
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    total_price = float(quote_data.get("total_price") or 0)
    degradation_rate = float(pricing.get("degradation_rate") or 0.004)
    operating_cost_base = float(pricing.get("operating_cost_base") or 0.005)
    operating_cost_increase = float(pricing.get("operating_cost_increase") or 0.02)
    leasing_ratio = float(pricing.get("leasing_payment_ratio") or 0.25)
    model_type = quote_data.get("model_type", "purchase")

    total_cashflow = 0.0
    if model_type == "leasing":
        for year in range(25):
            yearly_revenue = annual_revenue * max(0.0, 1 - (degradation_rate * year))
            total_cashflow += yearly_revenue * leasing_ratio
        return total_cashflow

    base_operating_cost = total_price * operating_cost_base
    total_cashflow = -total_price
    for year in range(25):
        yearly_revenue = annual_revenue * max(0.0, 1 - (degradation_rate * year))
        yearly_operating_cost = base_operating_cost * ((1 + operating_cost_increase) ** year)
        total_cashflow += yearly_revenue - yearly_operating_cost
    return total_cashflow


def build_quote_render_context(quote_data: dict, pricing: dict) -> dict:
    annual_production = float(quote_data.get("annual_production") or 0)
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    total_price = float(quote_data.get("total_price") or 0)
    trees_multiplier = float(pricing.get("trees_multiplier") or 0.05)
    degradation_rate = float(pricing.get("degradation_rate") or 0.004)
    operating_cost_base = float(pricing.get("operating_cost_base") or 0.005)
    operating_cost_increase = float(pricing.get("operating_cost_increase") or 0.02)
    tariff_rate = get_effective_tariff_rate(
        quote_data.get("system_size"),
        pricing.get("tariff_rate"),
    )
    leasing_ratio = float(pricing.get("leasing_payment_ratio") or 0.25)
    revenue_share = leasing_ratio if quote_data.get("model_type") == "leasing" else 1.0
    annual_income = calculate_annual_income(
        annual_revenue,
        quote_data.get("system_value_after_25_years"),
        revenue_share,
    )
    cashflow_25 = calculate_quote_cashflow_25_years(quote_data, pricing)
    # "Total income" cube (סך הכנסה) = residual system value + 25-year cash flow.
    # The estimated quarterly value is that total spread over 25 years / 4.
    system_value_for_total = float(
        quote_data.get("system_value_after_25_years")
        or quote_data.get("total_price")
        or 0
    )
    quarterly_value = calculate_quarterly_value(system_value_for_total + cashflow_25)

    return {
        "system_size": format_template_number(quote_data.get("system_size"), 1),
        "roof_area": format_template_number(quote_data.get("roof_area"), 1),
        "annual_production": format_template_number(annual_production),
        # The quotation calls this value "annual income". Keep the legacy
        # placeholder name so existing administrator templates stay valid.
        "annual_revenue": format_template_number(annual_income),
        "gross_annual_revenue": format_template_number(annual_revenue),
        "total_price": format_template_number(total_price),
        "system_value_after_25_years": format_template_number(
            quote_data.get("system_value_after_25_years")
        ),
        "trees": format_template_number(annual_production * trees_multiplier),
        "co2_saved": format_template_number(annual_production * 0.5),
        "total_cashflow_25": format_template_number(cashflow_25),
        "quarterly_value": format_template_number(quarterly_value),
        "tariff_rate": format_template_number(tariff_rate, 2),
        "tariff_agorot": format_template_number(tariff_rate * 100),
        "degradation_rate_percent": format_template_number(degradation_rate * 100, 1),
        "operating_cost_base_percent": format_template_number(operating_cost_base * 100, 1),
        "operating_cost_increase_percent": format_template_number(
            operating_cost_increase * 100, 1
        ),
    }


def enrich_quote_render_data(quote_data: dict, pricing: Optional[dict] = None) -> dict:
    pricing = pricing or {}
    enriched = dict(quote_data)

    # Business rule: every quote is presented leasing-style (no client
    # investment; income is the leasing revenue share). Forcing the model here
    # keeps the PDF, sign page, dashboard and render context perfectly in sync
    # regardless of how the quote was originally saved.
    enriched["model_type"] = "leasing"

    for field in QUOTE_RENDER_PRICING_FIELDS:
        if field in pricing:
            enriched[field] = pricing.get(field)

    render_context = build_quote_render_context(enriched, pricing)
    enriched["annual_income"] = render_context["annual_revenue"]
    enriched["quarterly_value"] = render_context["quarterly_value"]
    for quote_field, pricing_field in QUOTE_TEXT_FIELD_MAP.items():
        template = (
            enriched.get(quote_field)
            or pricing.get(pricing_field)
            or LEGACY_QUOTE_DEFAULTS[pricing_field]
        )
        # Older quotes stored already-rendered default prose, so their numbers
        # became permanently stale. Recognize those stock sections and render
        # them again from the current template/context. Truly custom prose is
        # still preserved as entered.
        legacy_auto_prefixes = {
            "basic_assumptions_text": "1. החישוב מתבסס לפי חישוב של 1500 שעות שמש בשנה",
            "revenue_calculation_text": "חישוב ההכנסות מבוסס על ייצור שנתי של",
            "summary_text": "השקעה במערכת סולארית היא השקעה חכמה לטווח ארוך.",
            "environmental_impact_text": "המערכת הסולארית שלך תייצר כ-",
        }
        auto_prefix = legacy_auto_prefixes.get(quote_field)
        if (
            auto_prefix
            and isinstance(template, str)
            and template.strip().startswith(auto_prefix)
            and "{" not in template
        ):
            configured_template = pricing.get(pricing_field) or ""
            template = (
                configured_template
                if "{" in configured_template
                else LEGACY_QUOTE_DEFAULTS[pricing_field]
            )
        enriched[quote_field] = render_quote_template(template, render_context).strip()

    return enriched


def resolve_visualization_path(stored_path: str) -> Optional[str]:
    """
    Try to resolve a visualization path that might be stored as:
    - an absolute path (new behaviour)
    - a URL (/static/... or /uploads/...)
    - just a filename
    Returns the first existing path, or None if not found.
    """
    if not stored_path:
        return None

    # Direct path exists
    if os.path.exists(stored_path):
        return stored_path

    filename = os.path.basename(stored_path)
    if not filename:
        return None

    candidates = [
        os.path.join(ROOF_VISUALIZATIONS_DIR, filename),
        os.path.join(PERSISTENT_UPLOADS_DIR, filename),
        os.path.join(PERSISTENT_UPLOADS_DIR, "roof_visualizations", filename),
        os.path.join("static", "roof_visualizations", filename),
        os.path.join("static", filename),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


def find_visualization_for_design(design_id: int) -> Optional[str]:
    """
    Scan common visualization directories for a file matching the design_id.
    Returns the most recently modified match or None.
    """
    if not design_id:
        return None

    candidates: list[str] = []
    search_roots = [
        ROOF_VISUALIZATIONS_DIR,
        os.path.join(PERSISTENT_UPLOADS_DIR, "roof_visualizations"),
        os.path.join("static", "roof_visualizations"),
        PERSISTENT_UPLOADS_DIR,
        "static",
    ]
    patterns = [
        f"vis_{design_id}_*.png",
        f"vis_{design_id}_*.jpg",
        f"vis_{design_id}_*.jpeg",
        f"roof_design_{design_id}*.png",
        f"roof_design_{design_id}*.jpg",
        f"roof_design_{design_id}*.jpeg",
    ]

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for pattern in patterns:
            for path in glob.glob(os.path.join(root, pattern)):
                if os.path.isfile(path):
                    candidates.append(path)

    if not candidates:
        return None

    # Return most recently modified candidate
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]

def find_customer_signature(customer_phone: str = None, customer_email: str = None):
    """
    Find customer signature from submissions table based on phone or email.
    Returns the signature path if found, None otherwise.
    """
    if not customer_phone and not customer_email:
        return None

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Try to find by phone first (most reliable)
            if customer_phone:
                cursor.execute('''
                    SELECT signature_path FROM customer_submissions
                    WHERE customer_phone = %s
                    ORDER BY submission_date DESC
                    LIMIT 1
                ''', (customer_phone,))
                result = cursor.fetchone()
                if result and result['signature_path']:
                    signature_path = result['signature_path']
                    if os.path.exists(signature_path):
                        print(f"[INFO] Found customer signature by phone: {signature_path}")
                        return signature_path

            # Try to find by email if phone didn't work
            if customer_email:
                cursor.execute('''
                    SELECT signature_path FROM customer_submissions
                    WHERE customer_email = %s
                    ORDER BY submission_date DESC
                    LIMIT 1
                ''', (customer_email,))
                result = cursor.fetchone()
                if result and result['signature_path']:
                    signature_path = result['signature_path']
                    if os.path.exists(signature_path):
                        print(f"[INFO] Found customer signature by email: {signature_path}")
                        return signature_path

            print(f"[INFO] No signature found for customer (phone: {customer_phone}, email: {customer_email})")
            return None

    except Exception as e:
        print(f"[ERROR] Error finding customer signature: {e}")
        return None

def ensure_offer_image_column():
    """Idempotently ensure quote-customization columns exist.

    Runs after init_database() as a belt-and-suspenders safeguard so a
    silent failure in the phase-5 migration never breaks quote creation.
    Uses ADD COLUMN IF NOT EXISTS so repeated invocations are no-ops.
    """
    try:
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute(
                "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS offer_image_path TEXT"
            )
            cursor.execute(
                "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS financial_metrics_overrides TEXT"
            )
            conn.commit()
            print("[OK] Verified quotes.offer_image_path and financial_metrics_overrides columns exist")
    except Exception as e:
        print(f"[WARNING] Failed to verify quote-customization columns: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler"""
    # Startup - directories already created at module import time
    print(f"[OK] Using uploads directory: {PERSISTENT_UPLOADS_DIR}")

    init_database()
    ensure_offer_image_column()

    # Cleanup expired sessions on startup
    cleanup_expired_sessions_db()

    # AI detection via HuggingFace Space with local fallback
    print("[*] AI roof detection: HuggingFace SAM space with local contour fallback")
    print("[*] HF Space: https://huggingface.co/spaces/ramankamran/mobilesam-roof-api")
    print("[*] Remote model: SAM 3 roof detector on HuggingFace Spaces")
    print("[*] Fallback: local OpenCV contour detector when the remote space is unavailable")

    print("[*] Solar Quotation System started with SAM 3 AI roof detection!")
    print("[*] Database: PostgreSQL (Neon) - Persistence ENABLED")
    print("[*] Visit: http://localhost:8000")
    yield
    # Shutdown (if needed)
    print("[*] Shutting down...")

# Initialize FastAPI app
app = FastAPI(title="Solar Quotation System", lifespan=lifespan)

# Configure CORS for widget embedding
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directories exist before mounting (required at import time)
for directory in [UPLOADS_DIR, ROOF_IMAGES_DIR, ROOF_VISUALIZATIONS_DIR, SIGNATURES_DIR, SIGNED_PDFS_DIR, QUOTE_IMAGES_DIR]:
    os.makedirs(directory, exist_ok=True)

# Mount static files (CSS, JS, logos from app code)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount uploads directory (from persistent disk in production)
if os.getenv("RENDER"):
    app.mount("/uploads", StaticFiles(directory=PERSISTENT_UPLOADS_DIR), name="uploads")

# Templates
templates = Jinja2Templates(directory="templates")


def _compute_asset_version() -> str:
    """Cache-busting token for static JS/CSS.

    Uses the newest mtime of the front-end bundles so browsers re-fetch
    immediately after every deploy (Render re-checks-out the files, changing
    their mtime) while still caching between deploys.
    """
    newest = 0.0
    for name in ("dashboard.js", "dashboard.css"):
        try:
            newest = max(newest, os.path.getmtime(os.path.join("static", name)))
        except OSError:
            continue
    return str(int(newest)) if newest else str(int(datetime.now().timestamp()))


# Exposed to every Jinja template as {{ asset_version }}.
templates.env.globals["asset_version"] = _compute_asset_version()

# Health check endpoint for uptime monitoring
@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Health check endpoint for UptimeRobot and monitoring services (supports GET and HEAD)"""
    return {"status": "ok", "service": "solar-quotation-system"}

def create_session(user_id: int, email: str, role: str) -> str:
    """Create a new session in the database"""
    session_id = secrets.token_urlsafe(32)
    create_session_db(user_id, email, role, session_id, expires_hours=24)
    return session_id

def get_current_user(session_id: Optional[str] = Cookie(None)):
    """Get current user from session (database-backed)"""
    return get_session_db(session_id)

def require_auth(session_id: Optional[str] = Cookie(None)):
    """Strict authentication - raises exception if not logged in"""
    user = get_session_db(session_id)
    if not user:
        raise HTTPException(
            status_code=303,
            detail="Not authenticated",
            headers={"Location": "/login"}
        )
    return user

@app.get("/")
async def home():
    """Redirect to login page"""
    return RedirectResponse(url="/login", status_code=302)

@app.get("/widget", response_class=HTMLResponse)
async def widget(request: Request):
    """Embeddable calculator widget"""
    return templates.TemplateResponse("widget.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    """Handle login"""
    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user or not verify_password(password, user["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        session_id = create_session(user["id"], user["email"], user["role"])
        response = RedirectResponse(url="/dashboard", status_code=303)
        # Set secure cookie with proper settings
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=IS_PRODUCTION,  # Only send over HTTPS in production
            samesite="lax",  # CSRF protection
            max_age=86400  # 24 hours
        )
        return response

@app.get("/logout")
async def logout(session_id: Optional[str] = Cookie(None)):
    """Handle logout"""
    if session_id:
        delete_session_db(session_id)
    response = RedirectResponse(url="/", status_code=303)
    # Delete cookie with same settings as when it was set
    response.delete_cookie(
        key="session_id",
        secure=IS_PRODUCTION,
        httponly=True,
        samesite="lax"
    )
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(get_current_user)):
    """Sales dashboard"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    response = templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user
    })
    # Prevent caching of authenticated pages
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request, user=Depends(get_current_user)):
    """Admin panel"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    response = templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, user=Depends(get_current_user)):
    """User management page"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    response = templates.TemplateResponse("users.html", {
        "request": request,
        "user": user
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/submissions", response_class=HTMLResponse)
async def submissions_page(request: Request, user=Depends(get_current_user)):
    """Customer submissions management page"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    response = templates.TemplateResponse("submissions.html", {
        "request": request,
        "user": user
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/pricing")
async def get_pricing():
    """Get current pricing parameters"""
    with get_db() as conn:
        cursor = get_cursor(conn)
        return get_latest_pricing(cursor)

@app.post("/api/pricing")
async def update_pricing(
    price_per_kwp: Optional[float] = Form(None),
    production_per_kwp: Optional[float] = Form(None),
    tariff_rate: Optional[float] = Form(None),
    trees_multiplier: Optional[float] = Form(None),
    vat_rate: Optional[float] = Form(None),
    direction_south: Optional[float] = Form(None),
    direction_southeast: Optional[float] = Form(None),
    direction_southwest: Optional[float] = Form(None),
    direction_east_west: Optional[float] = Form(None),
    shading_factor: Optional[float] = Form(None),
    degradation_rate: Optional[float] = Form(None),
    operating_cost_base: Optional[float] = Form(None),
    operating_cost_increase: Optional[float] = Form(None),
    roof_area_per_kw: Optional[float] = Form(None),
    leasing_payment_ratio: Optional[float] = Form(None),
    basic_assumptions_default: Optional[str] = Form(None),
    revenue_calculation_default: Optional[str] = Form(None),
    summary_default: Optional[str] = Form(None),
    environmental_impact_default: Optional[str] = Form(None),
    user=Depends(get_current_user)
):
    """Update pricing and calculator parameters"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        current = get_latest_pricing(cursor)
        if not current:
            current = {
                "price_per_kwp": 4300,
                "production_per_kwp": 1360,
                "tariff_rate": 0.48,
                "trees_multiplier": 0.05,
                "vat_rate": 0.17,
                "direction_south": 1.0,
                "direction_southeast": 0.95,
                "direction_southwest": 0.95,
                "direction_east_west": 0.9,
                "shading_factor": 0.85,
                "degradation_rate": 0.004,
                "operating_cost_base": 0.005,
                "operating_cost_increase": 0.02,
                "roof_area_per_kw": 7.0,
                "leasing_payment_ratio": 0.25,
                **LEGACY_QUOTE_DEFAULTS,
            }

        merged = {
            "price_per_kwp": current.get("price_per_kwp") if price_per_kwp is None else price_per_kwp,
            "production_per_kwp": (
                current.get("production_per_kwp")
                if production_per_kwp is None
                else production_per_kwp
            ),
            "tariff_rate": current.get("tariff_rate") if tariff_rate is None else tariff_rate,
            "trees_multiplier": (
                current.get("trees_multiplier")
                if trees_multiplier is None
                else trees_multiplier
            ),
            "vat_rate": current.get("vat_rate") if vat_rate is None else vat_rate,
            "direction_south": (
                current.get("direction_south")
                if direction_south is None
                else direction_south
            ),
            "direction_southeast": (
                current.get("direction_southeast")
                if direction_southeast is None
                else direction_southeast
            ),
            "direction_southwest": (
                current.get("direction_southwest")
                if direction_southwest is None
                else direction_southwest
            ),
            "direction_east_west": (
                current.get("direction_east_west")
                if direction_east_west is None
                else direction_east_west
            ),
            "shading_factor": (
                current.get("shading_factor")
                if shading_factor is None
                else shading_factor
            ),
            "degradation_rate": (
                current.get("degradation_rate")
                if degradation_rate is None
                else degradation_rate
            ),
            "operating_cost_base": (
                current.get("operating_cost_base")
                if operating_cost_base is None
                else operating_cost_base
            ),
            "operating_cost_increase": (
                current.get("operating_cost_increase")
                if operating_cost_increase is None
                else operating_cost_increase
            ),
            "roof_area_per_kw": (
                current.get("roof_area_per_kw")
                if roof_area_per_kw is None
                else roof_area_per_kw
            ),
            "leasing_payment_ratio": (
                current.get("leasing_payment_ratio")
                if leasing_payment_ratio is None
                else leasing_payment_ratio
            ),
            "basic_assumptions_default": (
                current.get("basic_assumptions_default")
                if basic_assumptions_default is None
                else basic_assumptions_default
            ),
            "revenue_calculation_default": (
                current.get("revenue_calculation_default")
                if revenue_calculation_default is None
                else revenue_calculation_default
            ),
            "summary_default": (
                current.get("summary_default")
                if summary_default is None
                else summary_default
            ),
            "environmental_impact_default": (
                current.get("environmental_impact_default")
                if environmental_impact_default is None
                else environmental_impact_default
            ),
        }

        cursor.execute('''
            UPDATE pricing_parameters SET
            price_per_kwp = %s,
            production_per_kwp = %s,
            tariff_rate = %s,
            trees_multiplier = %s,
            vat_rate = %s,
            direction_south = %s,
            direction_southeast = %s,
            direction_southwest = %s,
            direction_east_west = %s,
            shading_factor = %s,
            degradation_rate = %s,
            operating_cost_base = %s,
            operating_cost_increase = %s,
            roof_area_per_kw = %s,
            leasing_payment_ratio = %s,
            basic_assumptions_default = %s,
            revenue_calculation_default = %s,
            summary_default = %s,
            environmental_impact_default = %s,
            updated_at = CURRENT_TIMESTAMP
        ''', (
            merged["price_per_kwp"],
            merged["production_per_kwp"],
            merged["tariff_rate"],
            merged["trees_multiplier"],
            merged["vat_rate"],
            merged["direction_south"],
            merged["direction_southeast"],
            merged["direction_southwest"],
            merged["direction_east_west"],
            merged["shading_factor"],
            merged["degradation_rate"],
            merged["operating_cost_base"],
            merged["operating_cost_increase"],
            merged["roof_area_per_kw"],
            merged["leasing_payment_ratio"],
            merged["basic_assumptions_default"],
            merged["revenue_calculation_default"],
            merged["summary_default"],
            merged["environmental_impact_default"],
        ))
        conn.commit()
        return {"message": "Settings updated successfully"}

@app.post("/api/calculate")
async def calculate_quote(
    system_size: float = Form(...),
):
    """Calculate quote based on system size"""
    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("SELECT * FROM pricing_parameters ORDER BY id DESC LIMIT 1")
        params = convert_decimals_in_dict(dict(cursor.fetchone()))

    total_price = system_size * params["price_per_kwp"]
    annual_production = system_size * params["production_per_kwp"]
    tariff_rate = get_effective_tariff_rate(system_size, params["tariff_rate"])
    annual_revenue = annual_production * tariff_rate
    payback_period = round(total_price / annual_revenue, 2) if annual_revenue > 0 else 0
    trees = int(annual_production * params["trees_multiplier"])
    co2_saved = int(annual_production * 0.5)

    return {
        "total_price": total_price,
        "annual_production": annual_production,
        "annual_revenue": annual_revenue,
        "tariff_rate": tariff_rate,
        "payback_period": payback_period,
        "environmental_impact": {
            "trees": trees,
            "co2_saved": co2_saved
        }
    }

@app.post("/api/quotes")
async def create_quote(request: Request, user=Depends(get_current_user)):
    """Create new quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO quotes (
                quote_number, customer_name, customer_phone, customer_email, customer_address,
                system_size, roof_area, annual_production, panel_type, panel_count,
                inverter_type, direction, tilt_angle, warranty_years,
                total_price, maintenance, service, system_value_after_25_years,
                basic_assumptions_text, revenue_calculation_text, summary_text,
                environmental_impact_text, offer_image_path, financial_metrics_overrides,
                annual_revenue, payback_period, model_type, created_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
        ''', (
            generate_quote_number(),
            data.get("customer_name"),
            data.get("customer_phone"),
            data.get("customer_email"),
            data.get("customer_address"),
            data.get("system_size"),
            data.get("roof_area"),
            data.get("annual_production"),
            data.get("panel_type"),
            data.get("panel_count"),
            data.get("inverter_type"),
            data.get("direction"),
            data.get("tilt_angle"),
            data.get("warranty_years", 25),
            data.get("total_price"),
            data.get("maintenance"),
            data.get("service"),
            data.get("system_value_after_25_years"),
            data.get("basic_assumptions_text"),
            data.get("revenue_calculation_text"),
            data.get("summary_text"),
            data.get("environmental_impact_text"),
            data.get("offer_image_path"),
            json.dumps(data.get("financial_metrics_overrides")) if data.get("financial_metrics_overrides") else None,
            data.get("annual_revenue"),
            data.get("payback_period"),
            data.get("model_type", "purchase"),
            user["user_id"]
        ))
        quote_id = cursor.fetchone()['id']
        conn.commit()

    return {"message": "Quote created successfully", "quote_id": quote_id}

@app.get("/api/quotes")
async def list_quotes(user=Depends(get_current_user)):
    """List all quotes"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT q.*, u.name as created_by_name
            FROM quotes q
            LEFT JOIN users u ON q.created_by = u.id
            ORDER BY q.created_at DESC
        ''')
        quotes = [convert_decimals_in_dict(dict(row)) for row in cursor.fetchall()]

    return {"quotes": quotes}

@app.get("/api/quotes/{quote_id}")
async def get_quote(quote_id: int, user=Depends(get_current_user)):
    """Get single quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT q.*, u.name as created_by_name, u.email as created_by_email
            FROM quotes q
            LEFT JOIN users u ON q.created_by = u.id
            WHERE q.id = %s
        ''', (quote_id,))
        quote = cursor.fetchone()
        pricing = get_latest_pricing(cursor)

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote_data = convert_decimals_in_dict(dict(quote))
    return enrich_quote_render_data(quote_data, pricing)

@app.delete("/api/quotes/{quote_id}")
async def delete_quote(quote_id: int, user=Depends(get_current_user)):
    """Delete quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("DELETE FROM quotes WHERE id = %s", (quote_id,))
        conn.commit()

    return {"message": "Quote deleted successfully"}

@app.get("/api/company")
async def get_company():
    """Get company settings"""
    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
        company = cursor.fetchone()
        return convert_decimals_in_dict(dict(company)) if company else {}

@app.post("/api/company")
async def update_company(
    company_name: str = Form(...),
    company_phone: str = Form(None),
    company_email: str = Form(None),
    company_address: str = Form(None),
    user=Depends(get_current_user)
):
    """Update company settings"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE company_settings SET
            company_name = %s,
            company_phone = %s,
            company_email = %s,
            company_address = %s,
            updated_at = CURRENT_TIMESTAMP
        ''', (company_name, company_phone, company_email, company_address))
        conn.commit()

    return {"message": "Company settings updated successfully"}

@app.post("/api/logo/upload")
async def upload_logo(logo: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload company logo"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"]
    if logo.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Only PNG, JPG, and SVG are allowed.")

    # Validate file size (max 5MB)
    content = await logo.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

    # Use configured uploads directory
    uploads_dir = UPLOADS_DIR

    # Generate unique filename
    file_extension = logo.filename.split('.')[-1]
    filename = f"logo.{file_extension}"
    file_path = os.path.join(uploads_dir, filename)

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)

    # Update database with logo path
    logo_url = f"/uploads/uploads/{filename}" if os.getenv("RENDER") else f"/static/uploads/{filename}"
    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE company_settings SET
            company_logo = %s,
            updated_at = CURRENT_TIMESTAMP
        ''', (logo_url,))
        conn.commit()

    return {"message": "Logo uploaded successfully", "logo_url": logo_url}

@app.delete("/api/logo/delete")
async def delete_logo(user=Depends(get_current_user)):
    """Delete company logo"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)

        # Get current logo path
        cursor.execute("SELECT company_logo FROM company_settings ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()

        if result and result['company_logo']:
            logo_path = result['company_logo']

            # Delete file if exists
            if logo_path.startswith('/static/'):
                file_path = logo_path[1:]  # Remove leading slash
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Error deleting file: {e}")

        # Update database
        cursor.execute('''
            UPDATE company_settings SET
            company_logo = NULL,
            updated_at = CURRENT_TIMESTAMP
        ''')
        conn.commit()

    return {"message": "Logo deleted successfully"}

@app.post("/api/quote-image/upload")
async def upload_quote_image(image: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload an image to attach to the quote PDF (below the environmental impact section)."""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    allowed_types = ["image/png", "image/jpeg", "image/jpg"]
    if image.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Only PNG and JPG are allowed.")

    content = await image.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

    file_extension = image.filename.rsplit('.', 1)[-1].lower() if '.' in image.filename else 'png'
    filename = f"quote_image_{user['user_id']}_{int(datetime.now().timestamp())}.{file_extension}"
    file_path = os.path.join(QUOTE_IMAGES_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    image_url = (
        f"/uploads/quote_images/{filename}"
        if os.getenv("RENDER")
        else f"/static/quote_images/{filename}"
    )
    return {"image_url": image_url, "image_path": file_path}

@app.get("/api/users")
async def get_users(user=Depends(get_current_user)):
    """Get all users"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("SELECT id, email, name, role, created_at FROM users ORDER BY created_at DESC")
        users_list = cursor.fetchall()
        return [dict(u) for u in users_list]

@app.post("/api/users")
async def create_user(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user=Depends(get_current_user)
):
    """Create new user"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate inputs
    if not name or not email or not password or not role:
        raise HTTPException(status_code=400, detail="All fields are required")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Check if email already exists
    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")

        # Create user with hashed password
        hashed_password = hash_password(password)
        cursor.execute('''
            INSERT INTO users (email, password, name, role)
            VALUES (%s, %s, %s, %s)
        ''', (email, hashed_password, name, role))
        conn.commit()

        print(f"[USER-CREATE] New user created: {email} with role: {role}")

    return {"message": "User created successfully"}

@app.put("/api/users/{user_id}")
async def update_user(
    user_id: int,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(None),
    user=Depends(get_current_user)
):
    """Update user"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate inputs
    if not name or not email or not role:
        raise HTTPException(status_code=400, detail="Name, email, and role are required")

    with get_db() as conn:
        cursor = get_cursor(conn)

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        # Check if email already exists for another user
        cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")

        # Update user
        if password:
            hashed_password = hash_password(password)
            cursor.execute('''
                UPDATE users SET
                email = %s,
                password = %s,
                name = %s,
                role = %s
                WHERE id = %s
            ''', (email, hashed_password, name, role, user_id))
        else:
            cursor.execute('''
                UPDATE users SET
                email = %s,
                name = %s,
                role = %s
                WHERE id = %s
            ''', (email, name, role, user_id))

        conn.commit()

    return {"message": "User updated successfully"}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, user=Depends(get_current_user)):
    """Delete user"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Prevent deleting yourself
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    with get_db() as conn:
        cursor = get_cursor(conn)

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        # Delete user
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()

    return {"message": "User deleted successfully"}

@app.get("/api/submissions")
async def get_submissions(user=Depends(get_current_user)):
    """Get all customer submissions"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)
        cursor.execute("""
            SELECT id, customer_name, customer_phone, customer_email,
                   customer_address, roof_area, signature_path,
                   submission_date, status, notes
            FROM customer_submissions
            ORDER BY submission_date DESC
        """)
        submissions = cursor.fetchall()
        return [convert_decimals_in_dict(dict(s)) for s in submissions]

@app.put("/api/submissions/{submission_id}")
async def update_submission(
    submission_id: int,
    status: str = Form(...),
    notes: str = Form(None),
    user=Depends(get_current_user)
):
    """Update submission status and notes"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate status
    valid_statuses = ["new", "contacted", "quoted", "converted", "rejected"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    with get_db() as conn:
        cursor = get_cursor(conn)

        # Check if submission exists
        cursor.execute("SELECT id FROM customer_submissions WHERE id = %s", (submission_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Submission not found")

        # Update submission
        cursor.execute("""
            UPDATE customer_submissions
            SET status = ?, notes = ?
            WHERE id = ?
        """, (status, notes, submission_id))
        conn.commit()

    return {"message": "Submission updated successfully"}

@app.delete("/api/submissions/{submission_id}")
async def delete_submission(submission_id: int, user=Depends(get_current_user)):
    """Delete customer submission"""
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = get_cursor(conn)

        # Get signature path before deleting
        cursor.execute("SELECT signature_path FROM customer_submissions WHERE id = %s", (submission_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Submission not found")

        # Delete signature file if exists
        if result['signature_path'] and os.path.exists(result['signature_path']):
            try:
                os.remove(result['signature_path'])
            except Exception as e:
                print(f"Error deleting signature file: {e}")

        # Delete submission
        cursor.execute("DELETE FROM customer_submissions WHERE id = %s", (submission_id,))
        conn.commit()

    return {"message": "Submission deleted successfully"}

@app.get("/api/quotes/{quote_id}/pdf")
async def generate_pdf(quote_id: int, user=Depends(get_current_user)):
    """Generate PDF for a quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get quote data
            cursor.execute('''
                SELECT q.*, u.name as created_by_name, u.email as created_by_email
                FROM quotes q
                LEFT JOIN users u ON q.created_by = u.id
                WHERE q.id = %s
            ''', (quote_id,))
            quote = cursor.fetchone()

            if not quote:
                raise HTTPException(status_code=404, detail="Quote not found")

            # Get company settings
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()
            pricing = get_latest_pricing(cursor)

            # Convert to dict and handle Decimals
            quote_data = enrich_quote_render_data(convert_decimals_in_dict(dict(quote)), pricing)
            company_info = convert_decimals_in_dict(dict(company)) if company else None

        print(f"[PDF] Generating PDF for quote #{quote_data.get('quote_number')}")
        print(f"[PDF] Customer: {quote_data.get('customer_name')}")
        print(f"[PDF] System size: {quote_data.get('system_size')}, Annual production: {quote_data.get('annual_production')}")

        # Find customer signature if available
        customer_signature_path = find_customer_signature(
            customer_phone=quote_data.get('customer_phone'),
            customer_email=quote_data.get('customer_email')
        )

        # Generate PDF based on model type
        try:
            model_type = quote_data.get('model_type', 'purchase')
            if model_type == 'leasing':
                pdf_buffer = generate_leasing_quote_pdf(quote_data, company_info, customer_signature_path)
                print(f"[PDF] Successfully generated LEASING PDF for quote #{quote_data.get('quote_number')}")
            else:
                pdf_buffer = generate_quote_pdf(quote_data, company_info, customer_signature_path)
                print(f"[PDF] Successfully generated PURCHASE PDF for quote #{quote_data.get('quote_number')}")
        except Exception as pdf_error:
            print(f"[ERROR] PDF generation failed: {type(pdf_error).__name__}: {str(pdf_error)}")
            traceback.print_exc()
            raise

        # Return as downloadable file
        quote_number = quote_data.get('quote_number', 'N/A')
        customer_name = quote_data.get('customer_name', 'Customer')

        # Create filename with ASCII-safe characters
        raw_filename = f"Quote_{quote_number}_{customer_name}.pdf"
        safe_filename = sanitize_filename(raw_filename)

        # For browsers that support UTF-8 filenames, also provide the encoded version
        encoded_filename = url_quote(raw_filename)

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={safe_filename}; filename*=UTF-8''{encoded_filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Unexpected error in PDF endpoint: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF: {str(e)}"
        )

@app.post("/api/quotes/{quote_id}/send-email")
async def send_quote_email(quote_id: int, user=Depends(get_current_user)):
    """Generate and send PDF quote to customer via email"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get quote data
            cursor.execute('''
                SELECT q.*, u.name as created_by_name, u.email as created_by_email
                FROM quotes q
                LEFT JOIN users u ON q.created_by = u.id
                WHERE q.id = %s
            ''', (quote_id,))
            quote = cursor.fetchone()

            if not quote:
                raise HTTPException(status_code=404, detail="Quote not found")

            # Get company settings
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()

            # Convert to dict and handle Decimals
            pricing = get_latest_pricing(cursor)
            quote_data = enrich_quote_render_data(convert_decimals_in_dict(dict(quote)), pricing)
            company_info = convert_decimals_in_dict(dict(company)) if company else {}

        # Check if customer email exists
        if not quote_data.get('customer_email'):
            raise HTTPException(status_code=400, detail="Customer email not found in quote")

        print(f"[EMAIL] Preparing to send quote #{quote_data.get('quote_number')} to {quote_data.get('customer_email')}")

        # Find customer signature if available
        customer_signature_path = find_customer_signature(
            customer_phone=quote_data.get('customer_phone'),
            customer_email=quote_data.get('customer_email')
        )

        # Generate PDF
        model_type = quote_data.get('model_type', 'purchase')
        if model_type == 'leasing':
            pdf_buffer = generate_leasing_quote_pdf(quote_data, company_info, customer_signature_path)
        else:
            pdf_buffer = generate_quote_pdf(quote_data, company_info, customer_signature_path)

        # Send email with PDF attachment
        email_sent = send_quote_pdf_email(quote_data, company_info, pdf_buffer, customer_signature_path)

        if email_sent:
            return JSONResponse(content={
                "message": "Quote PDF sent successfully",
                "email": quote_data.get('customer_email'),
                "has_signature": customer_signature_path is not None
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to send quote email: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.post("/api/quotes/{quote_id}/generate-signature-link")
async def generate_signature_link(quote_id: int, user=Depends(get_current_user)):
    """Generate a unique signature link for a quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get quote data
            cursor.execute("SELECT * FROM quotes WHERE id = %s", (quote_id,))
            quote = cursor.fetchone()

            if not quote:
                raise HTTPException(status_code=404, detail="Quote not found")

            quote_data = dict(quote)

            # Generate unique token (URL-safe)
            signature_token = secrets.token_urlsafe(32)

            # Set expiration (30 days from now)
            from datetime import timedelta
            expires_at = datetime.now() + timedelta(days=30)

            # Get base URL from environment or use Render URL
            base_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")

            # Check if there's already a pending signature request
            cursor.execute('''
                SELECT signature_token, status, expires_at
                FROM quote_signatures
                WHERE quote_id = %s AND status = 'pending'
                ORDER BY created_at DESC LIMIT 1
            ''', (quote_id,))
            existing = cursor.fetchone()

            if existing:
                # Check if existing token is still valid
                existing_expires = ensure_datetime(existing['expires_at'])
                if existing_expires > datetime.now():
                    # Return existing valid token
                    return JSONResponse(content={
                        "message": "Signature link already exists",
                        "signature_link": f"/sign/{existing['signature_token']}",
                        "full_url": f"{base_url}/sign/{existing['signature_token']}",
                        "expires_at": existing['expires_at'],
                        "quote_number": quote_data.get('quote_number'),
                        "customer_name": quote_data.get('customer_name')
                    })

            # Create new signature request
            cursor.execute('''
                INSERT INTO quote_signatures
                (quote_id, signature_token, status, expires_at)
                VALUES (%s, %s, 'pending', %s)
            ''', (quote_id, signature_token, expires_at))
            conn.commit()

            print(f"[SIGNATURE] Generated signature link for quote #{quote_data.get('quote_number')}")

            return JSONResponse(content={
                "message": "Signature link generated successfully",
                "signature_link": f"/sign/{signature_token}",
                "full_url": f"{base_url}/sign/{signature_token}",
                "expires_at": expires_at.isoformat(),
                "quote_number": quote_data.get('quote_number'),
                "customer_name": quote_data.get('customer_name'),
                "customer_email": quote_data.get('customer_email')
            })

    except Exception as e:
        print(f"[ERROR] Failed to generate signature link: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate signature link: {str(e)}")

@app.get("/api/quotes/{quote_id}/signature-status")
async def get_signature_status(quote_id: int, user=Depends(get_current_user)):
    """Get signature status for a quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            cursor.execute('''
                SELECT * FROM quote_signatures
                WHERE quote_id = %s
                ORDER BY created_at DESC LIMIT 1
            ''', (quote_id,))
            signature = cursor.fetchone()

            if not signature:
                return JSONResponse(content={
                    "has_signature_request": False,
                    "status": None
                })

            sig_data = dict(signature)
            return JSONResponse(content={
                "has_signature_request": True,
                "status": sig_data.get('status'),
                "viewed_at": sig_data.get('viewed_at'),
                "signed_at": sig_data.get('signed_at'),
                "expires_at": sig_data.get('expires_at'),
                "signature_link": f"/sign/{sig_data.get('signature_token')}" if sig_data.get('status') == 'pending' else None
            })

    except Exception as e:
        print(f"[ERROR] Failed to get signature status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Email configuration using SendGrid
# Get API key from environment variable for security
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
if not SENDGRID_API_KEY:
    print("[WARNING] SENDGRID_API_KEY environment variable not set - email notifications will not work")

EMAIL_CONFIG = {
    "sender_email": os.getenv("SENDER_EMAIL", "baydon.maximus@gmail.com"),  # SendGrid verified sender
    "sender_name": "Solar Quotation System",
    "recipient_email": os.getenv("RECIPIENT_EMAIL", "usolarisrael@gmail.com")  # Where to receive notifications
}

def send_email_notification(customer_data: dict, signature_path: str):
    """Send email notification when customer submits contact form using SendGrid API"""
    # Check if API key is configured
    if not SENDGRID_API_KEY:
        print("[EMAIL] SendGrid API key not configured - skipping email notification")
        return False

    try:
        # Prepare professional HTML email body
        email_body = f"""
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>פנייה חדשה ממערכת הצעות מחיר</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background-color: #f4f4f4; direction: rtl;">
    <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f4f4f4;">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table role="presentation" style="width: 600px; max-width: 100%; border-collapse: collapse; background-color: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- Header with logo -->
                    <tr>
                        <td style="padding: 30px; text-align: center; background: linear-gradient(135deg, #000080 0%, #000060 100%);">
                            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: bold;">מערכת הצעות מחיר - אנרגיה סולארית</h1>
                        </td>
                    </tr>

                    <!-- Main content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="color: #000080; margin: 0 0 20px 0; font-size: 22px; text-align: right;">לידיעתך - פנייה חדשה מהאתר</h2>

                            <p style="color: #333; font-size: 16px; line-height: 1.6; text-align: right; margin: 0 0 25px 0;">
                                התקבלה פנייה חדשה ממלא/ת טופס יצירת קשר באתר. להלן פרטי הלקוח:
                            </p>

                            <!-- Customer details box -->
                            <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f8f9fa; border-radius: 8px; margin-bottom: 25px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #000080;">שם מלא:</strong>
                                                    <span style="color: #333; float: left;">{customer_data.get('customer_name', 'לא צוין')}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #000080;">טלפון:</strong>
                                                    <span style="color: #333; float: left;">{customer_data.get('customer_phone', 'לא צוין')}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #000080;">אימייל:</strong>
                                                    <span style="color: #333; float: left;">{customer_data.get('customer_email', 'לא צוין')}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #000080;">כתובת:</strong>
                                                    <span style="color: #333; float: left;">{customer_data.get('customer_address', 'לא צוין')}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <strong style="color: #000080;">שטח גג (מ"ר):</strong>
                                                    <span style="color: #333; float: left;">{customer_data.get('roof_area', 'לא צוין')}</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- Submission date -->
                            <p style="color: #666; font-size: 14px; text-align: right; margin: 0 0 20px 0;">
                                <strong>תאריך הפנייה:</strong> {customer_data.get('submission_date', 'לא זמין')}
                            </p>

                            <!-- Call to action -->
                            <p style="color: #333; font-size: 15px; text-align: right; margin: 25px 0 0 0; line-height: 1.6;">
                                מומלץ ליצור קשר עם הלקוח בהקדם האפשרי כדי לספק שירות מקצועי ולהגדיל את סיכויי ההמרה.
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 30px; background-color: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center;">
                            <p style="margin: 0; color: #666; font-size: 13px;">
                                זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
                            </p>
                            <p style="margin: 10px 0 0 0; color: #999; font-size: 12px;">
                                נשלח מ-Solar Quotation System
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        # Plain text version for better deliverability
        plain_text = f"""
פנייה חדשה ממערכת הצעות מחיר - אנרגיה סולארית

פרטי הלקוח:
--------------
שם מלא: {customer_data.get('customer_name', 'לא צוין')}
טלפון: {customer_data.get('customer_phone', 'לא צוין')}
אימייל: {customer_data.get('customer_email', 'לא צוין')}
כתובת: {customer_data.get('customer_address', 'לא צוין')}
שטח גג: {customer_data.get('roof_area', 'לא צוין')} מ"ר

תאריך הפנייה: {customer_data.get('submission_date', 'לא זמין')}

---
זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
"""

        # Create SendGrid Mail object with both HTML and plain text
        message = Mail(
            from_email=(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_name"]),
            to_emails=EMAIL_CONFIG["recipient_email"],
            subject=f"פנייה חדשה מהאתר - {customer_data.get('customer_name', 'לקוח חדש')}",
            html_content=email_body,
            plain_text_content=plain_text
        )

        # Add attachment if signature exists
        if signature_path and os.path.exists(signature_path):
            with open(signature_path, 'rb') as f:
                signature_content = f.read()
                encoded_file = base64.b64encode(signature_content).decode()

            attached_file = Attachment(
                FileContent(encoded_file),
                FileName('customer_signature.png'),
                FileType('image/png'),
                Disposition('attachment')
            )
            message.attachment = attached_file

        # Send email using SendGrid API
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        # Check response status
        if response.status_code >= 200 and response.status_code < 300:
            print(f"[EMAIL] Successfully sent notification for {customer_data.get('customer_name')}")
            print(f"[EMAIL] SendGrid response status: {response.status_code}")
            return True
        else:
            print(f"[EMAIL ERROR] SendGrid API error - Status code: {response.status_code}")
            print(f"[EMAIL ERROR] Response body: {response.body}")
            print(f"[EMAIL ERROR] Response headers: {response.headers}")
            return False

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email: {str(e)}")
        traceback.print_exc()  # Print full traceback for debugging
        return False

def send_quote_pdf_email(quote_data: dict, company_info: dict, pdf_buffer, customer_signature_path: str = None):
    """
    Send PDF quote to customer via email with their signature embedded

    Args:
        quote_data: Dictionary containing quote information
        company_info: Dictionary containing company information
        pdf_buffer: BytesIO object containing the generated PDF
        customer_signature_path: Optional path to customer signature (for logging)

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    # Check if API key is configured
    if not SENDGRID_API_KEY:
        print("[EMAIL] SendGrid API key not configured - skipping quote email")
        return False

    # Validate customer email
    customer_email = quote_data.get('customer_email')
    if not customer_email:
        print("[EMAIL] No customer email provided - cannot send quote")
        return False

    try:
        customer_name = quote_data.get('customer_name', 'לקוח יקר')
        quote_number = quote_data.get('quote_number', 'N/A')
        model_type = quote_data.get('model_type', 'purchase')
        model_type_hebrew = 'ליסינג' if model_type == 'leasing' else 'רכישה'

        # Prepare professional HTML email body
        email_body = f"""
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>הצעת מחיר - מערכת סולארית</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background-color: #f4f4f4; direction: rtl;">
    <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f4f4f4;">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table role="presentation" style="width: 600px; max-width: 100%; border-collapse: collapse; background-color: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 30px; text-align: center; background: linear-gradient(135deg, #14181F 0%, #1A1D22 100%);">
                            <h1 style="color: #3AE478; margin: 0; font-size: 28px; font-weight: bold;">הצעת מחיר - מערכת סולארית</h1>
                        </td>
                    </tr>

                    <!-- Main content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="color: #3AE478; margin: 0 0 20px 0; font-size: 22px; text-align: right;">שלום {customer_name},</h2>

                            <p style="color: #333; font-size: 16px; line-height: 1.8; text-align: right; margin: 0 0 25px 0;">
                                תודה שפניתם אלינו! מצורפת הצעת המחיר שלכם למערכת סולארית.
                            </p>

                            <!-- Quote details box -->
                            <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f8fafc; border-radius: 8px; margin-bottom: 25px; border-right: 4px solid #3AE478;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #14181F;">מספר הצעה:</strong>
                                                    <span style="color: #333; float: left;">{quote_number}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #14181F;">סוג הצעה:</strong>
                                                    <span style="color: #333; float: left;">{model_type_hebrew}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <strong style="color: #14181F;">גודל מערכת:</strong>
                                                    <span style="color: #333; float: left;">{quote_data.get('system_size', 'N/A')} קילוואט</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- PDF attachment notice -->
                            <div style="background-color: #f3fff8; border-right: 4px solid #3AE478; padding: 20px; margin: 25px 0; text-align: right;">
                                <p style="margin: 0 0 10px 0; color: #14181F; font-size: 16px; font-weight: bold;">
                                    הצעת המחיר המלאה מצורפת
                                </p>
                                <p style="margin: 0; color: #333; font-size: 14px; line-height: 1.6;">
                                    ההצעה כוללת את כל הפרטים הטכניים, החישובים הפיננסיים, והחתימה שלכם.
                                    נשמח לענות על כל שאלה ולסייע בתהליך ההחלטה.
                                </p>
                            </div>

                            <!-- Call to action -->
                            <p style="color: #333; font-size: 15px; text-align: right; margin: 25px 0 0 0; line-height: 1.8;">
                                נשמח לעמוד לשירותכם בכל שאלה.<br/>
                                ניתן ליצור איתנו קשר בטלפון או באימייל.
                            </p>

                            <p style="color: #666; font-size: 14px; text-align: right; margin: 20px 0 0 0;">
                                בברכה,<br/>
                                <strong>{company_info.get('company_name', 'צוות האנרגיה הסולארית')}</strong>
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 30px; background-color: #f8fafc; border-top: 1px solid #d1d5db; text-align: center;">
                            <p style="margin: 0; color: #666; font-size: 13px;">
                                זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        # Plain text version
        plain_text = f"""
שלום {customer_name},

תודה שפניתם אלינו! מצורפת הצעת המחיר שלכם למערכת סולארית.

פרטי ההצעה:
--------------
מספר הצעה: {quote_number}
סוג הצעה: {model_type_hebrew}
גודל מערכת: {quote_data.get('system_size', 'N/A')} קילוואט

ההצעה המלאה מצורפת לאימייל זה וכוללת את כל הפרטים הטכניים והחישובים הפיננסיים.

נשמח לעמוד לשירותכם בכל שאלה.

בברכה,
{company_info.get('company_name', 'צוות האנרגיה הסולארית')}

---
זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
"""

        # Create SendGrid Mail object
        message = Mail(
            from_email=(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_name"]),
            to_emails=customer_email,
            subject=f"הצעת מחיר מספר {quote_number} - מערכת סולארית",
            html_content=email_body,
            plain_text_content=plain_text
        )

        # Attach PDF
        pdf_buffer.seek(0)  # Reset buffer position
        pdf_content = pdf_buffer.read()
        encoded_pdf = base64.b64encode(pdf_content).decode()

        pdf_attachment = Attachment(
            FileContent(encoded_pdf),
            FileName(f'Quote_{quote_number}_{customer_name}.pdf'),
            FileType('application/pdf'),
            Disposition('attachment')
        )
        message.attachment = pdf_attachment

        # Send email using SendGrid API
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        # Check response status
        if response.status_code >= 200 and response.status_code < 300:
            sig_info = "with signature" if customer_signature_path else "without signature"
            print(f"[EMAIL] Successfully sent quote PDF to {customer_email} ({sig_info})")
            print(f"[EMAIL] SendGrid response status: {response.status_code}")
            return True
        else:
            print(f"[EMAIL ERROR] SendGrid API error - Status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send quote PDF: {str(e)}")
        traceback.print_exc()
        return False

@app.get("/contact", response_class=HTMLResponse)
async def contact_form(request: Request):
    """Contact form - only accessible via calculator with parameters"""
    # Check if request has calculator parameters
    if not request.query_params.get('roof_area'):
        # Redirect to calculator if accessed directly
        return RedirectResponse(url="/widget", status_code=302)
    return templates.TemplateResponse("contact.html", {"request": request})

@app.post("/api/submit-contact")
async def submit_contact(
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_email: Optional[str] = Form(None),
    customer_address: Optional[str] = Form(None),
    roof_area: Optional[float] = Form(None)
):
    """Handle contact form submission (signature removed)"""
    try:
        # Save to database (no signature)
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO customer_submissions
                (customer_name, customer_phone, customer_email, customer_address, roof_area, signature_path, submission_date, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                customer_name,
                customer_phone,
                customer_email or None,
                customer_address or None,
                roof_area,
                None,  # No signature
                datetime.now(),
                'new'
            ))
            submission_id = cursor.fetchone()['id']
            conn.commit()

        # Prepare email data
        customer_data = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email or "N/A",
            "customer_address": customer_address or "N/A",
            "roof_area": roof_area or "N/A",
            "submission_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Send email notification without signature (don't fail if email fails)
        print(f"[EMAIL] Attempting to send email notification for {customer_name}")
        email_sent = send_email_notification(customer_data, None)  # No signature path
        if email_sent:
            print(f"[EMAIL] Email notification sent successfully")
        else:
            print(f"[EMAIL] Email notification failed - check error logs above")

        return JSONResponse(content={
            "message": "Submission received successfully",
            "submission_id": submission_id
        })

    except Exception as e:
        print(f"[ERROR] Contact submission failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sign/{token}", response_class=HTMLResponse)
async def signature_portal(token: str, request: Request):
    """Display signature portal page for customer"""
    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get signature request details
            cursor.execute('''
                SELECT qs.*, q.*
                FROM quote_signatures qs
                JOIN quotes q ON qs.quote_id = q.id
                WHERE qs.signature_token = %s
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = dict(result)

            # Check if expired
            expires_at = ensure_datetime(sig_data['expires_at'])
            if expires_at < datetime.now():
                return templates.TemplateResponse("sign_quote.html", {
                    "request": request,
                    "expired": True
                })

            # Check if already signed
            if sig_data['status'] == 'signed':
                return templates.TemplateResponse("sign_quote.html", {
                    "request": request,
                    "expired": True,  # Show as expired/invalid
                })

            # Mark as viewed if first time
            if not sig_data['viewed_at']:
                cursor.execute('''
                    UPDATE quote_signatures
                    SET viewed_at = %s, status = 'viewed'
                    WHERE signature_token = %s
                ''', (datetime.now(), token))
                conn.commit()

            pricing = get_latest_pricing(cursor)
            sig_data = enrich_quote_render_data(convert_decimals_in_dict(sig_data), pricing)

            # Format numbers for display
            total_price_formatted = f"{int(sig_data['total_price']):,}" if sig_data.get('total_price') else 'N/A'
            annual_revenue_formatted = sig_data.get("annual_income") or 'N/A'
            quarterly_value_formatted = sig_data.get("quarterly_value") or 'N/A'
            system_value_formatted = (
                f"{int(sig_data['system_value_after_25_years']):,}"
                if sig_data.get('system_value_after_25_years')
                else 'לא צוין'
            )

            return templates.TemplateResponse("sign_quote.html", {
                "request": request,
                "expired": False,
                "quote_id": sig_data.get('quote_id'),
                "quote_number": sig_data.get('quote_number'),
                "customer_name": sig_data.get('customer_name'),
                "customer_phone": sig_data.get('customer_phone'),
                "customer_email": sig_data.get('customer_email'),
                "customer_address": sig_data.get('customer_address'),
                "system_size": sig_data.get('system_size'),
                "roof_area": sig_data.get('roof_area'),
                "annual_production": sig_data.get('annual_production'),
                "maintenance": sig_data.get('maintenance'),
                "service": sig_data.get('service'),
                "annual_revenue": annual_revenue_formatted,
                "quarterly_value": quarterly_value_formatted,
                "system_value_after_25_years": system_value_formatted,
                "basic_assumptions_text": sig_data.get('basic_assumptions_text'),
                "revenue_calculation_text": sig_data.get('revenue_calculation_text'),
                "summary_text": sig_data.get('summary_text'),
                "environmental_impact_text": sig_data.get('environmental_impact_text'),
                "total_price": total_price_formatted,
                "model_type": sig_data.get('model_type', 'purchase')
            })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error loading signature portal: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sign/{token}/preview-pdf")
async def preview_quote_pdf(token: str):
    """Allow customer to view PDF quote using signature token (no authentication required)"""
    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get signature request and quote details
            cursor.execute('''
                SELECT qs.*, q.*
                FROM quote_signatures qs
                JOIN quotes q ON qs.quote_id = q.id
                WHERE qs.signature_token = %s
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = convert_decimals_in_dict(dict(result))

            # Check if expired
            expires_at = ensure_datetime(sig_data['expires_at'])
            if expires_at < datetime.now():
                raise HTTPException(status_code=400, detail="Signature link has expired")

            # Get company settings
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()
            company_info = convert_decimals_in_dict(dict(company)) if company else None
            pricing = get_latest_pricing(cursor)
            sig_data = enrich_quote_render_data(sig_data, pricing)

        # Generate PDF (without customer signature since they haven't signed yet)
        model_type = sig_data.get('model_type', 'purchase')
        if model_type == 'leasing':
            pdf_buffer = generate_leasing_quote_pdf(sig_data, company_info, None)
        else:
            pdf_buffer = generate_quote_pdf(sig_data, company_info, None)

        # Return PDF for inline viewing
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error generating PDF preview: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sign/{token}/signed-pdf")
async def view_signed_pdf(token: str):
    """Allow customer to view signed PDF after signing"""
    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get signature request and signed PDF path
            cursor.execute('''
                SELECT signed_pdf_path, status
                FROM quote_signatures
                WHERE signature_token = %s
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = dict(result)

            # Check if signed
            if sig_data['status'] != 'signed':
                raise HTTPException(status_code=400, detail="Quote not signed yet")

            signed_pdf_path = sig_data.get('signed_pdf_path')
            if not signed_pdf_path or not os.path.exists(signed_pdf_path):
                raise HTTPException(status_code=404, detail="Signed PDF not found")

        # Return signed PDF for inline viewing
        with open(signed_pdf_path, "rb") as pdf_file:
            pdf_content = pdf_file.read()

        return StreamingResponse(
            io.BytesIO(pdf_content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error viewing signed PDF: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sign/{token}")
async def submit_signature(token: str, signature: UploadFile = File(...), request: Request = None):
    """Handle customer signature submission"""
    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get signature request details
            cursor.execute('''
                SELECT qs.*, q.*
                FROM quote_signatures qs
                JOIN quotes q ON qs.quote_id = q.id
                WHERE qs.signature_token = %s
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = convert_decimals_in_dict(dict(result))

            # Check if expired
            expires_at = ensure_datetime(sig_data['expires_at'])
            if expires_at < datetime.now():
                raise HTTPException(status_code=400, detail="Signature link has expired")

            # Check if already signed
            if sig_data['status'] == 'signed':
                raise HTTPException(status_code=400, detail="Quote already signed")

            # Use configured signatures directory
            signatures_dir = SIGNATURES_DIR

            # Save signature image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            quote_number = sig_data.get('quote_number', 'unknown')
            signature_filename = f"quote_sig_{quote_number}_{timestamp}.png"
            signature_path = os.path.join(signatures_dir, signature_filename)

            with open(signature_path, "wb") as buffer:
                shutil.copyfileobj(signature.file, buffer)

            # Get client IP
            client_ip = request.client.host if request else "unknown"
            user_agent = request.headers.get("user-agent", "unknown") if request else "unknown"

            # Update signature record
            cursor.execute('''
                UPDATE quote_signatures
                SET signature_path = %s,
                    status = 'signed',
                    signed_at = %s,
                    customer_ip = %s,
                    customer_user_agent = %s
                WHERE signature_token = %s
            ''', (signature_path, datetime.now(), client_ip, user_agent, token))
            conn.commit()

            print(f"[SIGNATURE] Customer signed quote #{quote_number}")

            # Get company info for PDF generation
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()
            company_info = convert_decimals_in_dict(dict(company)) if company else {}
            pricing = get_latest_pricing(cursor)
            sig_data = enrich_quote_render_data(convert_decimals_in_dict(sig_data), pricing)

        # Generate signed PDF with customer signature
        model_type = sig_data.get('model_type', 'purchase')
        if model_type == 'leasing':
            pdf_buffer = generate_leasing_quote_pdf(sig_data, company_info, signature_path)
        else:
            pdf_buffer = generate_quote_pdf(sig_data, company_info, signature_path)

        # Use configured signed PDFs directory
        signed_pdfs_dir = SIGNED_PDFS_DIR

        signed_pdf_filename = f"signed_quote_{quote_number}_{timestamp}.pdf"
        signed_pdf_path = os.path.join(signed_pdfs_dir, signed_pdf_filename)

        with open(signed_pdf_path, "wb") as f:
            pdf_buffer.seek(0)
            f.write(pdf_buffer.read())

        # Update signature record with signed PDF path
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                UPDATE quote_signatures
                SET signed_pdf_path = %s
                WHERE signature_token = %s
            ''', (signed_pdf_path, token))
            conn.commit()

        # Send email notification to admin with signed PDF
        send_admin_signed_quote_notification(sig_data, company_info, pdf_buffer, signature_path, signed_pdf_path)

        # Generate URL for viewing signed PDF
        signed_pdf_url = f"/sign/{token}/signed-pdf"

        return JSONResponse(content={
            "message": "Signature submitted successfully",
            "quote_number": quote_number,
            "signed_pdf_url": signed_pdf_url
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error submitting signature: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to submit signature: {str(e)}")

def send_admin_signed_quote_notification(quote_data: dict, company_info: dict, pdf_buffer, signature_path: str, signed_pdf_path: str):
    """Send email notification to admin when customer signs a quote"""
    if not SENDGRID_API_KEY:
        print("[EMAIL] SendGrid API key not configured - skipping signed quote notification")
        return False

    try:
        customer_name = quote_data.get('customer_name', 'לקוח')
        quote_number = quote_data.get('quote_number', 'N/A')
        customer_phone = quote_data.get('customer_phone', 'לא צוין')
        customer_email = quote_data.get('customer_email', 'לא צוין')

        # Prepare email body
        email_body = f"""
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="UTF-8">
    <title>הצעת מחיר נחתמה - {quote_number}</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background-color: #f4f4f4; direction: rtl;">
    <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f4f4f4;">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table role="presentation" style="width: 600px; max-width: 100%; border-collapse: collapse; background-color: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding: 30px; text-align: center; background: linear-gradient(135deg, #28a745 0%, #20c997 100%);">
                            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: bold;">הצעת מחיר נחתמה!</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="color: #28a745; margin: 0 0 20px 0; font-size: 22px; text-align: right;">מזל טוב!</h2>

                            <p style="color: #333; font-size: 16px; line-height: 1.8; text-align: right; margin: 0 0 25px 0;">
                                הלקוח חתם על הצעת המחיר באופן דיגיטלי.
                            </p>

                            <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f8f9fa; border-radius: 8px; margin-bottom: 25px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #28a745;">מספר הצעה:</strong>
                                                    <span style="color: #333; float: left;">{quote_number}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #28a745;">שם לקוח:</strong>
                                                    <span style="color: #333; float: left;">{customer_name}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #28a745;">טלפון:</strong>
                                                    <span style="color: #333; float: left;">{customer_phone}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <strong style="color: #28a745;">אימייל:</strong>
                                                    <span style="color: #333; float: left;">{customer_email}</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <div style="background-color: #d4edda; border-right: 4px solid #28a745; padding: 20px; margin: 25px 0; text-align: right;">
                                <p style="margin: 0 0 10px 0; color: #155724; font-size: 16px; font-weight: bold;">
                                    הצעת המחיר החתומה מצורפת
                                </p>
                                <p style="margin: 0; color: #155724; font-size: 14px;">
                                    ההצעה כוללת את החתימה הדיגיטלית של הלקוח.
                                </p>
                            </div>

                            <p style="color: #333; font-size: 15px; text-align: right; margin: 25px 0 0 0; line-height: 1.8;">
                                <strong>צעדים הבאים:</strong><br/>
                                1. צור קשר עם הלקוח לתיאום התקנה<br/>
                                2. שלח את ההצעה החתומה ללקוח (אם נדרש)<br/>
                                3. עדכן את המערכת עם תאריך התקנה
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 30px; background-color: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center;">
                            <p style="margin: 0; color: #666; font-size: 13px;">
                                זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        plain_text = f"""
הצעת מחיר נחתמה!

מזל טוב! הלקוח חתם על הצעת המחיר באופן דיגיטלי.

פרטי ההצעה:
--------------
מספר הצעה: {quote_number}
שם לקוח: {customer_name}
טלפון: {customer_phone}
אימייל: {customer_email}

הצעת המחיר החתומה מצורפת לאימייל זה.

צעדים הבאים:
1. צור קשר עם הלקוח לתיאום התקנה
2. שלח את ההצעה החתומה ללקוח (אם נדרש)
3. עדכן את המערכת עם תאריך התקנה

---
זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
"""

        # Create email
        message = Mail(
            from_email=(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_name"]),
            to_emails=EMAIL_CONFIG["recipient_email"],
            subject=f"הצעת מחיר נחתמה - {quote_number} - {customer_name}",
            html_content=email_body,
            plain_text_content=plain_text
        )

        # Attach signed PDF
        pdf_buffer.seek(0)
        pdf_content = pdf_buffer.read()
        encoded_pdf = base64.b64encode(pdf_content).decode()

        pdf_attachment = Attachment(
            FileContent(encoded_pdf),
            FileName(f'Signed_Quote_{quote_number}_{customer_name}.pdf'),
            FileType('application/pdf'),
            Disposition('attachment')
        )
        message.attachment = pdf_attachment

        # Send email
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code >= 200 and response.status_code < 300:
            print(f"[EMAIL] Successfully sent signed quote notification for {quote_number}")
            return True
        else:
            print(f"[EMAIL ERROR] Failed to send signed quote notification")
            return False

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send signed quote notification: {str(e)}")
        traceback.print_exc()
        return False

# ========================================
# ROOF DESIGNER API ENDPOINTS
# ========================================

from roof_detector import calculate_panel_layout_from_data

@app.post("/api/roof-designer/upload")
async def upload_roof_image_endpoint(
    file: UploadFile = File(...),
    customer_name: str = Form(None),
    customer_address: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    zoom_level: int = Form(None),
    pixels_per_meter: float = Form(None),
    user=Depends(get_current_user)
):
    """
    Upload roof image for manual drawing (no AI detection)

    Optionally accepts coordinates and scale for full analysis.
    Returns image URL for user to draw on.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Use configured roof images directory
        uploads_dir = ROOF_IMAGES_DIR

        # Save uploaded image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"roof_{timestamp}.{file_extension}"
        file_path = os.path.join(uploads_dir, filename)

        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"[ROOF DESIGNER] Uploaded roof image: {file_path}")

        # Get image dimensions using PIL
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size

        # Calculate meters_per_pixel if pixels_per_meter provided
        meters_per_pixel = 1.0 / pixels_per_meter if pixels_per_meter and pixels_per_meter > 0 else None

        # Save to database with optional location and scale data
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO roof_designs (
                    customer_name, customer_address, original_image_path,
                    latitude, longitude, zoom_level,
                    pixels_per_meter, meters_per_pixel,
                    created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                customer_name,
                customer_address,
                file_path,
                latitude,
                longitude,
                zoom_level,
                pixels_per_meter,
                meters_per_pixel,
                user['user_id']
            ))
            design_id = cursor.fetchone()['id']
            conn.commit()

        print(f"[ROOF DESIGNER] Created design #{design_id}" +
              (f" with coordinates ({latitude}, {longitude})" if latitude and longitude else ""))

        response_data = {
            "success": True,
            "design_id": design_id,
            "image_url": f"/uploads/roof_images/{filename}" if os.getenv("RENDER") else f"/static/roof_images/{filename}",
            "image_dimensions": {"width": width, "height": height}
        }

        # Include location and scale data in response if provided
        if latitude is not None:
            response_data["latitude"] = latitude
        if longitude is not None:
            response_data["longitude"] = longitude
        if pixels_per_meter is not None:
            response_data["pixels_per_meter"] = pixels_per_meter

        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Roof image upload failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def run_sam_detection_sync(job_id: str, image_path: str):
    """
    Run MobileSAM detection synchronously in background thread.
    Updates detection_jobs dict with results.
    """
    try:
        print(f"[JOB-{job_id}] Starting MobileSAM detection")
        print(f"[JOB-{job_id}] Image path: {image_path}")

        # Update status to running
        detection_jobs[job_id]["status"] = "running"

        # Import and run MobileSAM detection
        from roof_detector_sam import auto_detect_roof_boundary

        detection_result = auto_detect_roof_boundary(image_path, max_candidates=1)

        if detection_result.get('success'):
            candidates = detection_result.get('candidates', [])
            print(f"[JOB-{job_id}] Completed - Found {len(candidates)} candidate(s)")

            detection_jobs[job_id]["status"] = "completed"
            detection_jobs[job_id]["result"] = {
                "success": True,
                "candidates": candidates,
                "total_found": detection_result.get('total_found', len(candidates)),
                "message": detection_result.get('message', f"Found {len(candidates)} roof candidates"),
                "strategy_used": detection_result.get('strategy_used'),
                "remote_error": detection_result.get('remote_error'),
            }
        else:
            error_msg = detection_result.get('error', 'Detection failed')
            print(f"[JOB-{job_id}] Failed - {error_msg}")
            detection_jobs[job_id]["status"] = "failed"
            detection_jobs[job_id]["error"] = error_msg

    except Exception as e:
        error_msg = str(e)
        print(f"[JOB-{job_id}] ✗ Exception - {error_msg}")
        import traceback
        traceback.print_exc()
        detection_jobs[job_id]["status"] = "failed"
        detection_jobs[job_id]["error"] = error_msg


@app.post("/api/roof-designer/auto-detect")
async def auto_detect_roof_endpoint(
    design_id: int = Form(...),
    user=Depends(get_current_user)
):
    """
    Start async MobileSAM roof boundary detection.
    Returns immediately with job_id - client polls /auto-detect-status for results.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Get design from database
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT original_image_path, created_by
                FROM roof_designs
                WHERE id = %s
            ''', (design_id,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Design not found")

            image_path = result["original_image_path"]
            created_by = result["created_by"]

            # Security: Check ownership
            if created_by is not None and created_by != user['user_id']:
                raise HTTPException(status_code=403, detail="Access denied")

        # Create unique job ID
        job_id = str(uuid.uuid4())

        # Initialize job
        detection_jobs[job_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "design_id": design_id
        }

        print(f"[AUTO-DETECT] Created job {job_id} for design #{design_id}")

        # Run detection in background thread (doesn't block request)
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            detection_executor,
            run_sam_detection_sync,
            job_id,
            image_path
        )

        # Return job ID immediately - client will poll for results
        return JSONResponse(content={
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": "Detection started - poll /api/roof-designer/auto-detect-status"
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Auto-detection job creation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/roof-designer/auto-detect-status/{job_id}")
async def get_detection_status(
    job_id: str,
    user=Depends(get_current_user)
):
    """
    Poll detection job status.
    Returns: {status: "pending|running|completed|failed", result: {...}, error: str}
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if job_id not in detection_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = detection_jobs[job_id]

    response = {
        "status": job["status"]
    }

    if job["status"] == "completed":
        response["result"] = job["result"]
    elif job["status"] == "failed":
        response["error"] = job["error"]

    return JSONResponse(content=response)

@app.post("/api/roof-designer/calculate-layout")
async def calculate_layout_endpoint(
    design_id: int = Form(...),
    roof_polygon: str = Form(...),
    obstacles: str = Form(...),
    panel_width_m: float = Form(1.7),
    panel_height_m: float = Form(1.0),
    panel_power_w: int = Form(400),
    spacing_m: float = Form(0.05),
    pixels_per_meter: float = Form(100.0),
    orientation: str = Form("landscape"),
    latitude: float = Form(None),
    longitude: float = Form(None),
    user=Depends(get_current_user)
):
    """
    Calculate optimal panel layout based on roof data

    User can edit the detected polygon/obstacles before calculation.
    Optional latitude/longitude can be provided for uploaded images to enable
    full analysis (measurements, sun analysis, energy estimates).
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Parse JSON data
        roof_polygon_data = json.loads(roof_polygon)
        obstacles_data = json.loads(obstacles)

        # Convert roof polygon to list of tuples
        if isinstance(roof_polygon_data[0], dict):
            roof_poly_points = [(p['x'], p['y']) for p in roof_polygon_data]
        else:
            roof_poly_points = [(p[0], p[1]) for p in roof_polygon_data]

        print(f"[ROOF DESIGNER] Calculating layout for design #{design_id}")
        print(f"[ROOF DESIGNER] Panel: {panel_width_m}x{panel_height_m}m, {panel_power_w}W")

        # PHASE 2: Get location data for automatic measurements
        measurements_data = {}
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT latitude, longitude, zoom_level
                FROM roof_designs WHERE id = %s
            ''', (design_id,))
            location = cursor.fetchone()

        # If coordinates provided but not in DB, update the design record
        use_lat = latitude if latitude is not None else (location['latitude'] if location else None)
        use_lon = longitude if longitude is not None else (location['longitude'] if location else None)
        use_zoom = location['zoom_level'] if location else 19

        # Update design with new coordinates if provided
        if latitude is not None and longitude is not None:
            with get_db() as conn:
                cursor = get_cursor(conn)
                cursor.execute('''
                    UPDATE roof_designs
                    SET latitude = %s, longitude = %s, zoom_level = COALESCE(zoom_level, 19)
                    WHERE id = %s
                ''', (latitude, longitude, design_id))
                conn.commit()
                print(f"[ROOF DESIGNER] Updated design #{design_id} with coordinates ({latitude}, {longitude})")

        # PHASE 2: Calculate automatic roof measurements if location available
        if use_lat and use_lon:
            from roof_measurements import calculate_comprehensive_measurements

            print("[ROOF DESIGNER] Calculating automatic measurements...")
            measurements_data = calculate_comprehensive_measurements(
                polygon_points=roof_poly_points,
                latitude=use_lat,
                longitude=use_lon,
                zoom_level=use_zoom or 19,
                pixels_per_meter=pixels_per_meter,
                building_type="residential"
            )
            print(f"[ROOF DESIGNER] Measurements: {measurements_data.get('summary', 'N/A')}")

        # Calculate panel layout
        layout_result = calculate_panel_layout_from_data(
            roof_polygon=roof_poly_points,
            obstacles=obstacles_data,
            panel_width_m=panel_width_m,
            panel_height_m=panel_height_m,
            panel_power_w=panel_power_w,
            spacing_m=spacing_m,
            pixels_per_meter=pixels_per_meter,
            orientation=orientation
        )

        if not layout_result['success']:
            return JSONResponse(
                status_code=400,
                content={"error": layout_result.get('error', 'Calculation failed')}
            )

        # Update database with results (including Phase 2 measurements)
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                UPDATE roof_designs SET
                    roof_polygon_json = %s,
                    obstacles_json = %s,
                    panels_json = %s,
                    panel_count = %s,
                    system_power_kw = %s,
                    roof_area_m2 = %s,
                    coverage_percent = %s,
                    pixels_per_meter = %s,
                    panel_width_m = %s,
                    panel_height_m = %s,
                    panel_power_w = %s,
                    spacing_m = %s,
                    orientation = %s,
                    roof_length_m = %s,
                    roof_width_m = %s,
                    roof_perimeter_m = %s,
                    roof_azimuth = %s,
                    roof_type = %s,
                    measurement_confidence = %s,
                    usable_area_m2 = %s,
                    estimated_panel_count = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (
                roof_polygon,
                obstacles,
                json.dumps(layout_result['panels']),
                layout_result['total_panels'],
                layout_result['total_power_kw'],
                layout_result['roof_area_m2'],
                layout_result['coverage_percent'],
                pixels_per_meter,
                panel_width_m,
                panel_height_m,
                panel_power_w,
                spacing_m,
                orientation,
                # Phase 2 measurements
                measurements_data.get('length_m'),
                measurements_data.get('width_m'),
                measurements_data.get('perimeter_m'),
                measurements_data.get('azimuth'),
                'complex' if len(roof_poly_points) > 6 else 'simple',
                measurements_data.get('validation', {}).get('confidence'),
                measurements_data.get('usable_area_m2'),
                measurements_data.get('panel_estimate', {}).get('estimated_panels'),
                design_id
            ))
            conn.commit()

        print(f"[ROOF DESIGNER] Layout calculated: {layout_result['total_panels']} panels, {layout_result['total_power_kw']} kW")

        # Build response with Phase 2 measurements
        response_data = {
            "success": True,
            "panels": layout_result['panels'],
            "total_panels": layout_result['total_panels'],
            "total_power_kw": layout_result['total_power_kw'],
            "coverage_percent": layout_result['coverage_percent'],
            "roof_area_m2": layout_result['roof_area_m2']
        }

        # Add Phase 2 measurements if available
        if measurements_data:
            response_data["measurements"] = {
                "length_m": measurements_data.get('length_m'),
                "width_m": measurements_data.get('width_m'),
                "area_m2": measurements_data.get('area_m2'),
                "usable_area_m2": measurements_data.get('usable_area_m2'),
                "perimeter_m": measurements_data.get('perimeter_m'),
                "azimuth": measurements_data.get('azimuth'),
                "orientation_name": measurements_data.get('orientation_name'),
                "is_suitable_south": measurements_data.get('is_suitable_south'),
                "confidence": measurements_data.get('validation', {}).get('confidence', 0),
                "warnings": measurements_data.get('validation', {}).get('warnings', []),
                "suggestions": measurements_data.get('validation', {}).get('suggestions', []),
                "estimated_panels": measurements_data.get('panel_estimate', {}).get('estimated_panels', 0),
                "summary": measurements_data.get('summary', '')
            }

        # PHASE 3: Add sun analysis if location available
        if use_lat and use_lon:
            try:
                from sun_calculations import (
                    get_current_sun_position,
                    calculate_solar_potential,
                    calculate_annual_irradiance_estimate
                )

                roof_azimuth = measurements_data.get('azimuth', 180) if measurements_data else 180

                # Current sun position
                current_sun = get_current_sun_position(
                    use_lat,
                    use_lon
                )

                # Solar potential based on roof orientation
                solar_potential = calculate_solar_potential(
                    use_lat,
                    use_lon,
                    roof_azimuth
                )

                # Annual irradiance estimate
                irradiance = calculate_annual_irradiance_estimate(
                    use_lat,
                    roof_azimuth
                )

                response_data["sun_analysis"] = {
                    "current_sun": {
                        "azimuth": current_sun['azimuth'],
                        "elevation": current_sun['elevation'],
                        "is_daytime": current_sun['is_daytime'],
                        "sunrise": current_sun['sunrise'],
                        "sunset": current_sun['sunset']
                    },
                    "solar_potential": {
                        "orientation_quality": solar_potential['orientation_quality'],
                        "overall_efficiency": solar_potential['overall_efficiency'],
                        "azimuth_efficiency": solar_potential['azimuth_efficiency'],
                        "annual_sun_hours": solar_potential['annual_sun_hours'],
                        "roof_direction": solar_potential['roof_direction'],
                        "recommendations": solar_potential['recommendations']
                    },
                    "irradiance": {
                        "annual_kwh_per_m2": irradiance['annual_kwh_per_m2'],
                        "efficiency_factor": irradiance['efficiency_factor']
                    }
                }

                print(f"[PHASE 3] Sun analysis: {solar_potential['orientation_quality']} ({solar_potential['overall_efficiency']}% efficiency)")

                # PHASE 4: Add energy production and financial estimates
                try:
                    from energy_calculations import calculate_complete_estimate

                    energy_estimate = calculate_complete_estimate(
                        system_power_kw=layout_result['total_power_kw'],
                        panel_count=layout_result['total_panels'],
                        latitude=use_lat,
                        orientation_efficiency=solar_potential['overall_efficiency'],
                        self_consumption_ratio=0.70
                    )

                    response_data["energy_estimate"] = {
                        "production": {
                            "annual_kwh": energy_estimate['production']['annual_kwh'],
                            "daily_avg_kwh": energy_estimate['production']['daily_avg_kwh'],
                            "monthly_kwh": energy_estimate['production']['monthly_kwh'],
                            "system_efficiency": energy_estimate['production']['system_efficiency']
                        },
                        "financial": {
                            "system_cost_nis": energy_estimate['financial']['system_cost']['total'],
                            "annual_savings_nis": energy_estimate['financial']['annual_savings']['total'],
                            "payback_years": energy_estimate['financial']['payback_years'],
                            "roi_25_years": energy_estimate['financial']['roi_25_years'],
                            "break_even_year": energy_estimate['financial']['break_even_year']
                        },
                        "environmental": {
                            "annual_co2_offset_kg": energy_estimate['environmental']['annual_co2_offset_kg'],
                            "trees_equivalent": energy_estimate['environmental']['equivalencies']['trees_planted']
                        }
                    }

                    print(f"[PHASE 4] Energy estimate: {energy_estimate['production']['annual_kwh']} kWh/year, payback {energy_estimate['financial']['payback_years']} years")

                    # Add electrical stringing calculation
                    try:
                        from energy_calculations import calculate_electrical_stringing

                        stringing = calculate_electrical_stringing(
                            panel_count=layout_result['total_panels'],
                            panel_power_w=panel_power_w
                        )

                        response_data["electrical_stringing"] = {
                            "string_count": stringing['string_count'],
                            "strings": stringing['strings'],
                            "mppt_assignments": stringing['mppt_assignments'],
                            "total_dc_power_kw": stringing['total_dc_power_kw'],
                            "max_string_voltage": stringing['max_string_voltage'],
                            "recommended_inverter_kw": stringing['recommended_inverter_kw'],
                            "warnings": stringing['warnings']
                        }
                        print(f"[PHASE 4] Stringing: {stringing['string_count']} strings, recommended inverter: {stringing['recommended_inverter_kw']} kW")

                    except Exception as stringing_error:
                        print(f"[PHASE 4] Stringing calculation error (non-fatal): {str(stringing_error)}")

                    # Save energy production data to database
                    try:
                        with get_db() as conn:
                            cursor = get_cursor(conn)
                            cursor.execute('''
                                UPDATE roof_designs SET
                                    annual_production_kwh = %s,
                                    annual_savings_nis = %s,
                                    system_cost_nis = %s,
                                    payback_years = %s,
                                    roi_25_years = %s,
                                    co2_offset_kg = %s,
                                    string_count = %s,
                                    recommended_inverter_kw = %s,
                                    energy_estimate_json = %s
                                WHERE id = %s
                            ''', (
                                energy_estimate['production']['annual_kwh'],
                                energy_estimate['financial']['annual_savings']['total'],
                                energy_estimate['financial']['system_cost']['total'],
                                energy_estimate['financial']['payback_years'],
                                energy_estimate['financial']['roi_25_years'],
                                energy_estimate['environmental']['annual_co2_offset_kg'],
                                response_data.get('electrical_stringing', {}).get('string_count'),
                                response_data.get('electrical_stringing', {}).get('recommended_inverter_kw'),
                                json.dumps(energy_estimate),
                                design_id
                            ))
                            conn.commit()
                            print(f"[PHASE 4] Energy data saved to database")
                    except Exception as db_error:
                        print(f"[PHASE 4] Failed to save energy data: {str(db_error)}")

                except Exception as energy_error:
                    print(f"[PHASE 4] Energy calculation error (non-fatal): {str(energy_error)}")

            except Exception as sun_error:
                print(f"[PHASE 3] Sun analysis error (non-fatal): {str(sun_error)}")
                # Don't fail the whole request if sun analysis fails

        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Panel layout calculation failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/roof-designer/design/{design_id}")
async def get_roof_design(design_id: int, user=Depends(get_current_user)):
    """Get roof design data by ID"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute("SELECT * FROM roof_designs WHERE id = %s", (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

            design_data = convert_decimals_in_dict(dict(design))

            # Parse JSON fields
            if design_data.get('roof_polygon_json'):
                design_data['roof_polygon'] = json.loads(design_data['roof_polygon_json'])
            if design_data.get('obstacles_json'):
                design_data['obstacles'] = json.loads(design_data['obstacles_json'])
            if design_data.get('panels_json'):
                design_data['panels'] = json.loads(design_data['panels_json'])

            return design_data

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get roof design: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/roof-designer/save-visualization")
async def save_visualization_endpoint(
    design_id: int = Form(...),
    visualization: str = Form(...),
    user=Depends(get_current_user)
):
    """Save canvas visualization image with roof and panels"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Verify design exists and user has access
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute("SELECT created_by FROM roof_designs WHERE id = %s", (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

        # Decode base64 canvas data (format: "data:image/png;base64,...")
        if visualization.startswith('data:image'):
            # Remove data URL prefix
            image_data = visualization.split(',')[1]
            image_bytes = base64.b64decode(image_data)
        else:
            raise HTTPException(status_code=400, detail="Invalid image data format")

        # Use configured roof visualizations directory
        vis_dir = ROOF_VISUALIZATIONS_DIR

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vis_filename = f"vis_{design_id}_{timestamp}.png"
        vis_path = os.path.join(vis_dir, vis_filename)

        # Save image
        with open(vis_path, 'wb') as f:
            f.write(image_bytes)

        # Update database
        with get_db() as conn:
            cursor = get_cursor(conn)
            cursor.execute('''
                UPDATE roof_designs SET processed_image_path = %s WHERE id = %s
            ''', (vis_path, design_id))
            conn.commit()

        return JSONResponse(content={
            "success": True,
            "visualization_url": f"/uploads/roof_visualizations/{vis_filename}" if os.getenv("RENDER") else f"/static/roof_visualizations/{vis_filename}"
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to save visualization: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/roof-designer", response_class=HTMLResponse)
async def roof_designer_page(request: Request, user=Depends(get_current_user)):
    """Roof designer UI page"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    response = templates.TemplateResponse("roof_designer.html", {
        "request": request,
        "user": user
    })
    # Prevent caching of authenticated pages
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/roof-designer/list")
async def list_roof_designs(user=Depends(get_current_user)):
    """List all roof designs for current user"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # All users can see all designs
            cursor.execute('''
                SELECT id, customer_name, customer_address, panel_count,
                       system_power_kw, roof_area_m2, created_at
                FROM roof_designs
                ORDER BY created_at DESC
            ''')

            designs = [convert_decimals_in_dict(dict(row)) for row in cursor.fetchall()]
            return {"designs": designs}

    except Exception as e:
        print(f"[ERROR] Failed to list designs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/roof-designer/update-metadata")
async def update_roof_design_metadata(
    design_id: int = Form(...),
    customer_name: str = Form(""),
    customer_address: str = Form(""),
    user=Depends(get_current_user)
):
    """Update customer name/address for a saved roof design"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Verify ownership (admin can edit all, users can only edit their own)
            cursor.execute('SELECT created_by FROM roof_designs WHERE id = %s', (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

            # Update metadata
            cursor.execute('''
                UPDATE roof_designs
                SET customer_name = %s, customer_address = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (customer_name, customer_address, design_id))

            conn.commit()
            return {"success": True, "message": "Design metadata updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to update design metadata: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/roof-designer/delete/{design_id}")
async def delete_roof_design(
    design_id: int,
    user=Depends(get_current_user)
):
    """Delete a roof design and associated image files"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get design details and verify ownership
            cursor.execute('''
                SELECT created_by, original_image_path, processed_image_path
                FROM roof_designs WHERE id = %s
            ''', (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

            design = dict(design)
            created_by = design.get('created_by')
            original_image_path = design.get('original_image_path')
            processed_image_path = design.get('processed_image_path')

            # Delete image files if they exist
            if original_image_path and os.path.exists(original_image_path):
                try:
                    os.remove(original_image_path)
                    print(f"[DELETE] Removed original image: {original_image_path}")
                except Exception as e:
                    print(f"[WARNING] Failed to delete original image: {e}")

            if processed_image_path and os.path.exists(processed_image_path):
                try:
                    os.remove(processed_image_path)
                    print(f"[DELETE] Removed visualization image: {processed_image_path}")
                except Exception as e:
                    print(f"[WARNING] Failed to delete visualization image: {e}")

            # Delete database record
            cursor.execute('DELETE FROM roof_designs WHERE id = %s', (design_id,))
            conn.commit()

            return {"success": True, "message": "Design deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to delete design: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/roof-designer/download/{design_id}")
async def download_roof_visualization(
    design_id: int,
    user=Depends(get_current_user)
):
    """Download roof visualization image as attachment"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = get_cursor(conn)

            # Get design details and verify ownership
            cursor.execute('''
                SELECT created_by, processed_image_path, customer_name, original_image_path
                FROM roof_designs WHERE id = %s
            ''', (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

            design = dict(design)
            created_by = design.get('created_by')
            processed_image_path = design.get('processed_image_path')
            customer_name = design.get('customer_name')
            original_image_path = design.get('original_image_path')

            # Check if visualization exists
            resolved_path = resolve_visualization_path(processed_image_path)
            if not resolved_path:
                # Try to locate a visualization by design_id on disk
                resolved_path = find_visualization_for_design(design_id)

            # If still missing, attempt to fall back to the original image
            if not resolved_path and original_image_path and os.path.exists(original_image_path):
                resolved_path = original_image_path

            if not resolved_path:
                raise HTTPException(status_code=404, detail="Visualization not found. Please save the design first.")

            # Backfill normalized path to database for future requests
            if resolved_path != processed_image_path:
                try:
                    cursor.execute(
                        "UPDATE roof_designs SET processed_image_path = %s WHERE id = %s",
                        (resolved_path, design_id)
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    # Non-fatal: continue serving the file even if the update fails

            # Read the image file
            with open(resolved_path, 'rb') as img_file:
                image_data = img_file.read()

            # Create safe filename
            safe_customer_name = sanitize_filename(customer_name) if customer_name else "design"
            ext = os.path.splitext(resolved_path)[1] or ".jpg"
            filename = f"roof_design_{safe_customer_name}_{design_id}{ext}"

            # Return image as downloadable attachment
            return StreamingResponse(
                io.BytesIO(image_data),
                media_type=f"image/{ext.lstrip('.').lower()}" if ext else "image/jpeg",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to download visualization: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PHASE 1: MAP INTEGRATION & GEOCODING API ENDPOINTS
# ============================================================================

@app.post("/api/geocode")
async def geocode_address_endpoint(
    address: str = Form(...),
    country: str = Form("Israel"),
    user=Depends(get_current_user)
):
    """
    Geocode an address to coordinates

    Converts street address to latitude/longitude using Nominatim API (OpenStreetMap)
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from geocoding_service import geocode_address

        result = geocode_address(address, country)

        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": "Address not found. Please check the address and try again."}
            )

        return JSONResponse(content={
            "success": True,
            "latitude": result['latitude'],
            "longitude": result['longitude'],
            "display_name": result['display_name'],
            "address_details": result.get('address_details', {})
        })

    except Exception as e:
        print(f"[ERROR] Geocoding failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reverse-geocode")
async def reverse_geocode_endpoint(
    latitude: float = Form(...),
    longitude: float = Form(...),
    user=Depends(get_current_user)
):
    """
    Reverse geocode coordinates to address

    Converts latitude/longitude to street address
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from geocoding_service import reverse_geocode

        result = reverse_geocode(latitude, longitude)

        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": "Address not found for these coordinates."}
            )

        return JSONResponse(content={
            "success": True,
            "display_name": result['display_name'],
            "address": result.get('address', {})
        })

    except Exception as e:
        print(f"[ERROR] Reverse geocoding failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search-addresses")
async def search_addresses_endpoint(
    query: str,
    country: str = "Israel",
    limit: int = 5,
    user=Depends(get_current_user)
):
    """
    Search for addresses (autocomplete)

    Returns list of matching addresses for autocomplete functionality
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from geocoding_service import search_addresses

        results = search_addresses(query, country, limit)

        return JSONResponse(content={
            "success": True,
            "results": results,
            "count": len(results)
        })

    except Exception as e:
        print(f"[ERROR] Address search failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/satellite-image")
async def get_satellite_image_endpoint(
    latitude: float,
    longitude: float,
    zoom: int = 20,
    width: int = 1200,
    height: int = 800,
    user=Depends(get_current_user)
):
    """
    Fetch satellite imagery for given coordinates

    Uses Mapbox Static API (100k requests/month free tier)
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from satellite_imagery import fetch_satellite_image

        # Fetch satellite image (uses FREE OpenStreetMap tiles by default, no API key required)
        image_data = fetch_satellite_image(
            latitude, longitude, zoom, width, height, use_cache=True, prefer_free=True
        )

        if not image_data:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to fetch satellite imagery"}
            )

        # Return image
        return StreamingResponse(
            io.BytesIO(image_data),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400"  # Cache for 24 hours
            }
        )

    except Exception as e:
        print(f"[ERROR] Satellite image fetch failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/roof-designer/from-address")
async def create_design_from_address_endpoint(
    address: str = Form(...),
    customer_name: str = Form(None),
    country: str = Form("Israel"),
    zoom: int = Form(20),
    user=Depends(get_current_user)
):
    """
    Create new roof design from address

    Workflow:
    1. Geocode address to coordinates
    2. Fetch satellite imagery
    3. Calculate meters per pixel
    4. Create design entry in database
    5. Return design ID and image

    This combines geocoding + satellite fetch into single operation
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from geocoding_service import geocode_address
        from satellite_imagery import fetch_satellite_image, get_meters_per_pixel

        # Step 1: Geocode address
        print(f"[FROM ADDRESS] Geocoding: {address}")
        geocode_result = geocode_address(address, country)

        if not geocode_result:
            return JSONResponse(
                status_code=404,
                content={"error": "Address not found. Please check the address and try again."}
            )

        latitude = geocode_result['latitude']
        longitude = geocode_result['longitude']
        display_name = geocode_result['display_name']

        print(f"[FROM ADDRESS] Found: {display_name} at ({latitude:.6f}, {longitude:.6f})")

        # Step 2: Fetch satellite image (uses FREE OpenStreetMap tiles, no API key required)
        print(f"[FROM ADDRESS] Fetching satellite image at zoom {zoom}")
        image_data = fetch_satellite_image(
            latitude, longitude, zoom, 1200, 800, use_cache=True, prefer_free=True
        )

        if not image_data:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to fetch satellite imagery"}
            )

        # Step 4: Save image to uploads directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_address = re.sub(r'[^\w\s-]', '', address)[:50].strip().replace(' ', '_')
        image_filename = f"roof_from_address_{safe_address}_{timestamp}.jpg"
        image_path = os.path.join(ROOF_IMAGES_DIR, image_filename)

        with open(image_path, "wb") as f:
            f.write(image_data)

        print(f"[FROM ADDRESS] Saved image: {image_path}")

        # Step 5: Calculate meters per pixel
        meters_per_pixel = get_meters_per_pixel(latitude, zoom)
        print(f"[FROM ADDRESS] Scale: {meters_per_pixel:.4f} m/px")

        # Step 6: Create design entry in database
        with get_db() as conn:
            cursor = get_cursor(conn)

            cursor.execute('''
                INSERT INTO roof_designs (
                    customer_name,
                    customer_address,
                    original_image_path,
                    latitude,
                    longitude,
                    zoom_level,
                    map_source,
                    geocoded_address,
                    meters_per_pixel,
                    pixels_per_meter,
                    created_by,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            ''', (
                customer_name or "Unknown",
                address,
                image_path,
                latitude,
                longitude,
                zoom,
                'mapbox',
                display_name,
                meters_per_pixel,
                1.0 / meters_per_pixel if meters_per_pixel > 0 else 100.0,
                user['user_id']
            ))

            design_id = cursor.fetchone()['id']
            conn.commit()

        print(f"[FROM ADDRESS] Created design #{design_id}")

        # Step 7: Return success with design data
        return JSONResponse(content={
            "success": True,
            "design_id": design_id,
            "latitude": latitude,
            "longitude": longitude,
            "geocoded_address": display_name,
            "zoom_level": zoom,
            "meters_per_pixel": round(meters_per_pixel, 4),
            "pixels_per_meter": round(1.0 / meters_per_pixel if meters_per_pixel > 0 else 100.0, 2),
            "image_path": image_path,
            "message": "Design created successfully from address"
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Create design from address failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/roof-designer/from-coordinates")
async def create_design_from_coordinates_endpoint(
    latitude: float = Form(...),
    longitude: float = Form(...),
    zoom: int = Form(20),
    address: str = Form(None),
    customer_name: str = Form(None),
    user=Depends(get_current_user)
):
    """
    Create new roof design directly from latitude/longitude coordinates.

    Workflow:
    1. (Optional) Reverse geocode to human-friendly address
    2. Fetch satellite imagery
    3. Calculate meters per pixel
    4. Create design entry in database
    5. Return design ID and image metadata
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from geocoding_service import reverse_geocode
        from satellite_imagery import fetch_satellite_image, get_meters_per_pixel

        # Step 1: Reverse geocode (best-effort, falls back to coordinates string)
        display_name = address or f"Coordinates ({latitude:.6f}, {longitude:.6f})"
        try:
            reverse_result = reverse_geocode(latitude, longitude)
            if reverse_result and reverse_result.get('display_name'):
                display_name = reverse_result['display_name']
        except Exception as ge:
            print(f"[WARN] Reverse geocoding failed for coordinates: {ge}")

        print(f"[FROM COORDS] Using: {display_name} at ({latitude:.6f}, {longitude:.6f})")

        # Step 2: Fetch satellite image (prefer free OSM tiles)
        print(f"[FROM COORDS] Fetching satellite image at zoom {zoom}")
        image_data = fetch_satellite_image(
            latitude, longitude, zoom, 1200, 800, use_cache=True, prefer_free=True
        )

        if not image_data:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to fetch satellite imagery"}
            )

        # Step 3: Save image to uploads directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r'[^\w\s-]', '', display_name)[:50].strip().replace(' ', '_') or "coords"
        image_filename = f"roof_from_coords_{safe_label}_{timestamp}.jpg"
        image_path = os.path.join(ROOF_IMAGES_DIR, image_filename)

        with open(image_path, "wb") as f:
            f.write(image_data)

        print(f"[FROM COORDS] Saved image: {image_path}")

        # Step 4: Calculate meters per pixel
        meters_per_pixel = get_meters_per_pixel(latitude, zoom)
        print(f"[FROM COORDS] Scale: {meters_per_pixel:.4f} m/px")

        # Step 5: Create design entry in database
        with get_db() as conn:
            cursor = get_cursor(conn)

            cursor.execute('''
                INSERT INTO roof_designs (
                    customer_name,
                    customer_address,
                    original_image_path,
                    latitude,
                    longitude,
                    zoom_level,
                    map_source,
                    geocoded_address,
                    meters_per_pixel,
                    pixels_per_meter,
                    created_by,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            ''', (
                customer_name or "Unknown",
                display_name,
                image_path,
                latitude,
                longitude,
                zoom,
                'osm',  # Prefer free OSM tiles by default
                display_name,
                meters_per_pixel,
                1.0 / meters_per_pixel if meters_per_pixel > 0 else 100.0,
                user['user_id']
            ))

            design_id = cursor.fetchone()['id']
            conn.commit()

        print(f"[FROM COORDS] Created design #{design_id}")

        # Step 6: Return success with design data
        return JSONResponse(content={
            "success": True,
            "design_id": design_id,
            "latitude": latitude,
            "longitude": longitude,
            "geocoded_address": display_name,
            "zoom_level": zoom,
            "meters_per_pixel": round(meters_per_pixel, 4),
            "pixels_per_meter": round(1.0 / meters_per_pixel if meters_per_pixel > 0 else 100.0, 2),
            "image_path": image_path,
            "message": "Design created successfully from coordinates"
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Create design from coordinates failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/map-config")
async def get_map_configuration(user=Depends(get_current_user)):
    """
    Get map service configuration status

    Returns information about which map services are available
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        mapbox_token = bool(os.getenv("MAPBOX_ACCESS_TOKEN"))

        return JSONResponse(content={
            "osm_available": True,  # Always available (FREE, no API key)
            "mapbox_available": mapbox_token,
            "google_maps_available": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
            "nominatim_available": True,  # Always available (free)
            "default_zoom": 19,  # OSM max zoom
            "default_map_source": "osm"  # OpenStreetMap by default (FREE)
        })

    except Exception as e:
        print(f"[ERROR] Get map config failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# END PHASE 1 API ENDPOINTS
# ============================================================================


# ============================================================================
# PHASE 3 API ENDPOINTS: SUN CALCULATIONS & SHADOW ANALYSIS
# ============================================================================

@app.get("/api/sun-position")
async def get_sun_position(
    latitude: float,
    longitude: float,
    timezone_offset: float = 2.0,
    user=Depends(get_current_user)
):
    """
    Get current sun position for a location.

    Returns azimuth, elevation, sunrise, sunset times.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from sun_calculations import get_current_sun_position

        result = get_current_sun_position(latitude, longitude, timezone_offset)

        return JSONResponse(content={
            "success": True,
            **result
        })

    except Exception as e:
        print(f"[ERROR] Get sun position failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/daily-shadows")
async def get_daily_shadows(
    latitude: float,
    longitude: float,
    obstruction_height: float = 0,
    date: str = None,
    timezone_offset: float = 2.0,
    user=Depends(get_current_user)
):
    """
    Get shadow analysis throughout a day for a location.

    Args:
        latitude: Location latitude
        longitude: Location longitude
        obstruction_height: Height of nearby obstructions in meters
        date: Date in YYYY-MM-DD format (default: today)
        timezone_offset: Hours offset from UTC (default: 2 for Israel)
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from sun_calculations import analyze_daily_shadows
        from datetime import datetime

        analysis_date = None
        if date:
            analysis_date = datetime.strptime(date, '%Y-%m-%d')

        result = analyze_daily_shadows(
            latitude, longitude, analysis_date, obstruction_height, timezone_offset
        )

        return JSONResponse(content={
            "success": True,
            **result
        })

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        print(f"[ERROR] Get daily shadows failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/solar-potential")
async def get_solar_potential(
    latitude: float,
    longitude: float,
    roof_azimuth: float,
    roof_tilt: float = 0,
    timezone_offset: float = 2.0,
    user=Depends(get_current_user)
):
    """
    Calculate solar potential for a roof based on orientation.

    Returns efficiency estimates, seasonal data, and recommendations.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from sun_calculations import calculate_solar_potential, calculate_annual_irradiance_estimate

        potential = calculate_solar_potential(
            latitude, longitude, roof_azimuth, roof_tilt, timezone_offset
        )

        irradiance = calculate_annual_irradiance_estimate(
            latitude, roof_azimuth, roof_tilt
        )

        return JSONResponse(content={
            "success": True,
            **potential,
            "irradiance": irradiance
        })

    except Exception as e:
        print(f"[ERROR] Get solar potential failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/roof-designer/sun-analysis")
async def analyze_roof_sun(
    design_id: int = Form(...),
    user=Depends(get_current_user)
):
    """
    Perform comprehensive sun analysis for a saved roof design.

    Uses the design's location and roof orientation to calculate
    solar potential, shadow patterns, and recommendations.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from sun_calculations import (
            get_current_sun_position,
            calculate_solar_potential,
            analyze_daily_shadows,
            calculate_annual_irradiance_estimate
        )

        # Get design data from database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT latitude, longitude, roof_azimuth, zoom_level
                FROM roof_designs
                WHERE id = %s AND user_id = %s
            """, (design_id, user['user_id']))

            design = cursor.fetchone()

        if not design:
            raise HTTPException(status_code=404, detail="Design not found")

        latitude = design['latitude']
        longitude = design['longitude']
        roof_azimuth = design['roof_azimuth'] or 180  # Default to south

        if not latitude or not longitude:
            raise HTTPException(
                status_code=400,
                detail="Design does not have location data. Please search an address first."
            )

        # Calculate current sun position
        current_sun = get_current_sun_position(latitude, longitude)

        # Calculate solar potential
        potential = calculate_solar_potential(latitude, longitude, roof_azimuth)

        # Daily shadow analysis
        shadows = analyze_daily_shadows(latitude, longitude, obstruction_height=0)

        # Annual irradiance estimate
        irradiance = calculate_annual_irradiance_estimate(latitude, roof_azimuth)

        # Update design with solar analysis data
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE roof_designs
                SET updated_at = NOW()
                WHERE id = %s
            """, (design_id,))
            conn.commit()

        return JSONResponse(content={
            "success": True,
            "design_id": design_id,
            "location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "current_sun": current_sun,
            "solar_potential": potential,
            "daily_shadows": shadows,
            "irradiance": irradiance
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Sun analysis failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# END PHASE 3 API ENDPOINTS
# ============================================================================


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
