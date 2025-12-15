from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from contextlib import asynccontextmanager
import secrets
from database import get_db, init_database, hash_password, verify_password, generate_quote_number
from datetime import datetime
import json
import os
import shutil
import traceback
import re
from urllib.parse import quote as url_quote
from pdf_generator import generate_quote_pdf, generate_leasing_quote_pdf
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64

# Detect if running in production (on Render or other HTTPS environment)
IS_PRODUCTION = os.getenv("RENDER") is not None or os.getenv("PRODUCTION") is not None

# Session store (in-memory for simplicity)
sessions = {}

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler"""
    # Startup
    init_database()
    print("[*] Solar Quotation System started!")
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

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Health check endpoint for uptime monitoring
@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Health check endpoint for UptimeRobot and monitoring services (supports GET and HEAD)"""
    return {"status": "ok", "service": "solar-quotation-system"}

def create_session(user_id: int, email: str, role: str) -> str:
    """Create a new session"""
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "created_at": datetime.now()
    }
    return session_id

def get_current_user(session_id: Optional[str] = Cookie(None)):
    """Get current user from session"""
    if not session_id or session_id not in sessions:
        return None
    return sessions[session_id]

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
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
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
    if session_id and session_id in sessions:
        del sessions[session_id]
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
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user
    })

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request, user=Depends(get_current_user)):
    """Admin panel"""
    if not user or user["role"] != "ADMIN":
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user
    })

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, user=Depends(get_current_user)):
    """User management page"""
    if not user or user["role"] != "ADMIN":
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("users.html", {
        "request": request,
        "user": user
    })

@app.get("/submissions", response_class=HTMLResponse)
async def submissions_page(request: Request, user=Depends(get_current_user)):
    """Customer submissions management page"""
    if not user or user["role"] != "ADMIN":
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("submissions.html", {
        "request": request,
        "user": user
    })

@app.get("/api/pricing")
async def get_pricing():
    """Get current pricing parameters"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pricing_parameters ORDER BY id DESC LIMIT 1")
        pricing = cursor.fetchone()
        return dict(pricing) if pricing else {}

@app.post("/api/pricing")
async def update_pricing(
    price_per_kwp: float = Form(...),
    production_per_kwp: float = Form(...),
    tariff_rate: float = Form(...),
    trees_multiplier: float = Form(0.05),
    vat_rate: float = Form(0.17),
    user=Depends(get_current_user)
):
    """Update pricing parameters (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pricing_parameters SET
            price_per_kwp = ?,
            production_per_kwp = ?,
            tariff_rate = ?,
            trees_multiplier = ?,
            vat_rate = ?,
            updated_at = CURRENT_TIMESTAMP
        ''', (price_per_kwp, production_per_kwp, tariff_rate, trees_multiplier, vat_rate))
        conn.commit()
        return {"message": "Pricing updated successfully"}

@app.post("/api/calculate")
async def calculate_quote(
    system_size: float = Form(...),
):
    """Calculate quote based on system size"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pricing_parameters ORDER BY id DESC LIMIT 1")
        params = dict(cursor.fetchone())

    total_price = system_size * params["price_per_kwp"]
    annual_production = system_size * params["production_per_kwp"]
    annual_revenue = annual_production * params["tariff_rate"]
    payback_period = round(total_price / annual_revenue, 2) if annual_revenue > 0 else 0
    trees = int(annual_production * params["trees_multiplier"])
    co2_saved = int(annual_production * 0.5)

    return {
        "total_price": total_price,
        "annual_production": annual_production,
        "annual_revenue": annual_revenue,
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
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO quotes (
                quote_number, customer_name, customer_phone, customer_email, customer_address,
                system_size, roof_area, annual_production, panel_type, panel_count,
                inverter_type, direction, tilt_angle, warranty_years,
                total_price, annual_revenue, payback_period, model_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            data.get("annual_revenue"),
            data.get("payback_period"),
            data.get("model_type", "purchase"),
            user["user_id"]
        ))
        conn.commit()
        quote_id = cursor.lastrowid

    return {"message": "Quote created successfully", "quote_id": quote_id}

@app.get("/api/quotes")
async def list_quotes(user=Depends(get_current_user)):
    """List all quotes"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT q.*, u.name as created_by_name
            FROM quotes q
            LEFT JOIN users u ON q.created_by = u.id
            ORDER BY q.created_at DESC
        ''')
        quotes = [dict(row) for row in cursor.fetchall()]

    return {"quotes": quotes}

@app.get("/api/quotes/{quote_id}")
async def get_quote(quote_id: int, user=Depends(get_current_user)):
    """Get single quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT q.*, u.name as created_by_name, u.email as created_by_email
            FROM quotes q
            LEFT JOIN users u ON q.created_by = u.id
            WHERE q.id = ?
        ''', (quote_id,))
        quote = cursor.fetchone()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    return dict(quote)

@app.delete("/api/quotes/{quote_id}")
async def delete_quote(quote_id: int, user=Depends(get_current_user)):
    """Delete quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
        conn.commit()

    return {"message": "Quote deleted successfully"}

@app.get("/api/company")
async def get_company():
    """Get company settings"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
        company = cursor.fetchone()
        return dict(company) if company else {}

@app.post("/api/company")
async def update_company(
    company_name: str = Form(...),
    company_phone: str = Form(None),
    company_email: str = Form(None),
    company_address: str = Form(None),
    user=Depends(get_current_user)
):
    """Update company settings (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE company_settings SET
            company_name = ?,
            company_phone = ?,
            company_email = ?,
            company_address = ?,
            updated_at = CURRENT_TIMESTAMP
        ''', (company_name, company_phone, company_email, company_address))
        conn.commit()

    return {"message": "Company settings updated successfully"}

@app.post("/api/logo/upload")
async def upload_logo(logo: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload company logo (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"]
    if logo.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Only PNG, JPG, and SVG are allowed.")

    # Validate file size (max 5MB)
    content = await logo.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

    # Create uploads directory if it doesn't exist
    uploads_dir = "static/uploads"
    os.makedirs(uploads_dir, exist_ok=True)

    # Generate unique filename
    file_extension = logo.filename.split('.')[-1]
    filename = f"logo.{file_extension}"
    file_path = os.path.join(uploads_dir, filename)

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)

    # Update database with logo path
    logo_url = f"/static/uploads/{filename}"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE company_settings SET
            company_logo = ?,
            updated_at = CURRENT_TIMESTAMP
        ''', (logo_url,))
        conn.commit()

    return {"message": "Logo uploaded successfully", "logo_url": logo_url}

@app.delete("/api/logo/delete")
async def delete_logo(user=Depends(get_current_user)):
    """Delete company logo (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()

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

@app.get("/api/users")
async def get_users(user=Depends(get_current_user)):
    """Get all users (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, name, role, created_at FROM users ORDER BY created_at DESC")
        users_list = cursor.fetchall()
        return [dict(u) for u in users_list]

@app.post("/api/users")
async def create_user(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("SALES_REP"),
    user=Depends(get_current_user)
):
    """Create new user (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate role
    if role not in ["ADMIN", "SALES_REP"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    # Check if email already exists
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")

        # Create user
        hashed_password = hash_password(password)
        cursor.execute('''
            INSERT INTO users (email, password, name, role)
            VALUES (?, ?, ?, ?)
        ''', (email, hashed_password, name, role))
        conn.commit()

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
    """Update user (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate role
    if role not in ["ADMIN", "SALES_REP"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        # Check if email already exists for another user
        cursor.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")

        # Update user
        if password:
            hashed_password = hash_password(password)
            cursor.execute('''
                UPDATE users SET
                email = ?,
                password = ?,
                name = ?,
                role = ?
                WHERE id = ?
            ''', (email, hashed_password, name, role, user_id))
        else:
            cursor.execute('''
                UPDATE users SET
                email = ?,
                name = ?,
                role = ?
                WHERE id = ?
            ''', (email, name, role, user_id))

        conn.commit()

    return {"message": "User updated successfully"}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, user=Depends(get_current_user)):
    """Delete user (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Prevent deleting yourself
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        # Delete user
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    return {"message": "User deleted successfully"}

@app.get("/api/submissions")
async def get_submissions(user=Depends(get_current_user)):
    """Get all customer submissions (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, customer_name, customer_phone, customer_email,
                   customer_address, roof_area, signature_path,
                   submission_date, status, notes
            FROM customer_submissions
            ORDER BY submission_date DESC
        """)
        submissions = cursor.fetchall()
        return [dict(s) for s in submissions]

@app.put("/api/submissions/{submission_id}")
async def update_submission(
    submission_id: int,
    status: str = Form(...),
    notes: str = Form(None),
    user=Depends(get_current_user)
):
    """Update submission status and notes (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Validate status
    valid_statuses = ["new", "contacted", "quoted", "converted", "rejected"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if submission exists
        cursor.execute("SELECT id FROM customer_submissions WHERE id = ?", (submission_id,))
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
    """Delete customer submission (admin only)"""
    if not user or user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()

        # Get signature path before deleting
        cursor.execute("SELECT signature_path FROM customer_submissions WHERE id = ?", (submission_id,))
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
        cursor.execute("DELETE FROM customer_submissions WHERE id = ?", (submission_id,))
        conn.commit()

    return {"message": "Submission deleted successfully"}

@app.get("/api/quotes/{quote_id}/pdf")
async def generate_pdf(quote_id: int, user=Depends(get_current_user)):
    """Generate PDF for a quote"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Get quote data
            cursor.execute('''
                SELECT q.*, u.name as created_by_name, u.email as created_by_email
                FROM quotes q
                LEFT JOIN users u ON q.created_by = u.id
                WHERE q.id = ?
            ''', (quote_id,))
            quote = cursor.fetchone()

            if not quote:
                raise HTTPException(status_code=404, detail="Quote not found")

            # Get company settings
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()

            # Convert to dict
            quote_data = dict(quote)
            company_info = dict(company) if company else None

        print(f"[PDF] Generating PDF for quote #{quote_data.get('quote_number')}")
        print(f"[PDF] Customer: {quote_data.get('customer_name')}")
        print(f"[PDF] System size: {quote_data.get('system_size')}, Annual production: {quote_data.get('annual_production')}")

        # Generate PDF based on model type
        try:
            model_type = quote_data.get('model_type', 'purchase')
            if model_type == 'leasing':
                pdf_buffer = generate_leasing_quote_pdf(quote_data, company_info)
                print(f"[PDF] Successfully generated LEASING PDF for quote #{quote_data.get('quote_number')}")
            else:
                pdf_buffer = generate_quote_pdf(quote_data, company_info)
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

# Email configuration using SendGrid
# Get API key from environment variable for security
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
if not SENDGRID_API_KEY:
    print("[WARNING] SENDGRID_API_KEY environment variable not set - email notifications will not work")

EMAIL_CONFIG = {
    "sender_email": os.getenv("SENDER_EMAIL", "baydon.maximus@gmail.com"),  # SendGrid verified sender
    "sender_name": "Solar Quotation System",
    "recipient_email": os.getenv("RECIPIENT_EMAIL", "engr.ramankamran@gmail.com")  # Where to receive notifications
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
                            <h2 style="color: #000080; margin: 0 0 20px 0; font-size: 22px; text-align: right;">לידיעתך - פנייה חדשה מהאתר 💡</h2>

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

                            <!-- Signature note -->
                            <div style="background-color: #e8f4f8; border-right: 4px solid #000080; padding: 15px; margin: 20px 0; text-align: right;">
                                <p style="margin: 0; color: #333; font-size: 14px;">
                                    📎 <strong>חתימה דיגיטלית:</strong> החתימה הדיגיטלית של הלקוח מצורפת לאימייל זה.
                                </p>
                            </div>

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

החתימה הדיגיטלית של הלקוח מצורפת לאימייל זה.

---
זהו הודעה אוטומטית ממערכת הצעות המחיר לאנרגיה סולארית
"""

        # Create SendGrid Mail object with both HTML and plain text
        message = Mail(
            from_email=(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_name"]),
            to_emails=EMAIL_CONFIG["recipient_email"],
            subject=f"🌞 פנייה חדשה מהאתר - {customer_data.get('customer_name', 'לקוח חדש')}",
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

@app.get("/contact", response_class=HTMLResponse)
async def contact_form(request: Request):
    """Public contact form page"""
    return templates.TemplateResponse("contact.html", {"request": request})

@app.post("/api/submit-contact")
async def submit_contact(
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_email: Optional[str] = Form(None),
    customer_address: Optional[str] = Form(None),
    roof_area: Optional[float] = Form(None),
    signature: UploadFile = File(...)
):
    """Handle contact form submission with signature"""
    try:
        # Create signatures directory if it doesn't exist
        signatures_dir = os.path.join("static", "signatures")
        os.makedirs(signatures_dir, exist_ok=True)

        # Save signature image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        signature_filename = f"signature_{timestamp}_{secrets.token_hex(4)}.png"
        signature_path = os.path.join(signatures_dir, signature_filename)

        with open(signature_path, "wb") as buffer:
            shutil.copyfileobj(signature.file, buffer)

        # Save to database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO customer_submissions
                (customer_name, customer_phone, customer_email, customer_address, roof_area, signature_path, submission_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                customer_name,
                customer_phone,
                customer_email or None,
                customer_address or None,
                roof_area,
                signature_path,
                datetime.now(),
                'new'
            ))
            conn.commit()
            submission_id = cursor.lastrowid

        # Prepare email data
        customer_data = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email or "N/A",
            "customer_address": customer_address or "N/A",
            "roof_area": roof_area or "N/A",
            "submission_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Send email notification (don't fail if email fails)
        print(f"[EMAIL] Attempting to send email notification for {customer_name}")
        email_sent = send_email_notification(customer_data, signature_path)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
