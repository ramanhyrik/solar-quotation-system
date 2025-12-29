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
import io
from urllib.parse import quote as url_quote
from pdf_generator import generate_quote_pdf, generate_leasing_quote_pdf
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64
from download_sam_model import download_sam_model

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

def find_customer_signature(customer_phone: str = None, customer_email: str = None):
    """
    Find customer signature from submissions table based on phone or email.
    Returns the signature path if found, None otherwise.
    """
    if not customer_phone and not customer_email:
        return None

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Try to find by phone first (most reliable)
            if customer_phone:
                cursor.execute('''
                    SELECT signature_path FROM customer_submissions
                    WHERE customer_phone = ?
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
                    WHERE customer_email = ?
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler"""
    # Startup
    init_database()

    # Download SAM model if not present (non-interactive mode)
    print("[*] Checking SAM model availability...")
    try:
        download_sam_model(interactive=False)
    except Exception as e:
        print(f"[WARNING] SAM model download failed: {e}")
        print("[WARNING] Roof detection will not be available until model is downloaded")

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
            company_info = dict(company) if company else {}

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
            cursor = conn.cursor()

            # Get quote data
            cursor.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,))
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
                WHERE quote_id = ? AND status = 'pending'
                ORDER BY created_at DESC LIMIT 1
            ''', (quote_id,))
            existing = cursor.fetchone()

            if existing:
                # Check if existing token is still valid
                existing_expires = datetime.fromisoformat(existing['expires_at'])
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
                VALUES (?, ?, 'pending', ?)
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
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM quote_signatures
                WHERE quote_id = ?
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
                        <td style="padding: 30px; text-align: center; background: linear-gradient(135deg, #000080 0%, #000060 100%);">
                            <h1 style="color: #D9FF0D; margin: 0; font-size: 28px; font-weight: bold;">הצעת מחיר - מערכת סולארית</h1>
                        </td>
                    </tr>

                    <!-- Main content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="color: #000080; margin: 0 0 20px 0; font-size: 22px; text-align: right;">שלום {customer_name},</h2>

                            <p style="color: #333; font-size: 16px; line-height: 1.8; text-align: right; margin: 0 0 25px 0;">
                                תודה שפניתם אלינו! מצורפת הצעת המחיר שלכם למערכת סולארית.
                            </p>

                            <!-- Quote details box -->
                            <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f8f9fa; border-radius: 8px; margin-bottom: 25px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #000080;">מספר הצעה:</strong>
                                                    <span style="color: #333; float: left;">{quote_number}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #e0e0e0;">
                                                    <strong style="color: #000080;">סוג הצעה:</strong>
                                                    <span style="color: #333; float: left;">{model_type_hebrew}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <strong style="color: #000080;">גודל מערכת:</strong>
                                                    <span style="color: #333; float: left;">{quote_data.get('system_size', 'N/A')} קוט״ש</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- PDF attachment notice -->
                            <div style="background-color: #e8f4f8; border-right: 4px solid #000080; padding: 20px; margin: 25px 0; text-align: right;">
                                <p style="margin: 0 0 10px 0; color: #000080; font-size: 16px; font-weight: bold;">
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

        # Plain text version
        plain_text = f"""
שלום {customer_name},

תודה שפניתם אלינו! מצורפת הצעת המחיר שלכם למערכת סולארית.

פרטי ההצעה:
--------------
מספר הצעה: {quote_number}
סוג הצעה: {model_type_hebrew}
גודל מערכת: {quote_data.get('system_size', 'N/A')} קוט״ש

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
                None,  # No signature
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
            cursor = conn.cursor()

            # Get signature request details
            cursor.execute('''
                SELECT qs.*, q.*
                FROM quote_signatures qs
                JOIN quotes q ON qs.quote_id = q.id
                WHERE qs.signature_token = ?
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = dict(result)

            # Check if expired
            expires_at = datetime.fromisoformat(sig_data['expires_at'])
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
                    SET viewed_at = ?, status = 'viewed'
                    WHERE signature_token = ?
                ''', (datetime.now(), token))
                conn.commit()

            # Format numbers for display
            total_price_formatted = f"{int(sig_data['total_price']):,}" if sig_data.get('total_price') else 'N/A'
            annual_revenue_formatted = f"{int(sig_data['annual_revenue']):,}" if sig_data.get('annual_revenue') else 'N/A'

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
                "panel_type": sig_data.get('panel_type'),
                "panel_count": sig_data.get('panel_count'),
                "inverter_type": sig_data.get('inverter_type'),
                "annual_production": sig_data.get('annual_production'),
                "annual_revenue": annual_revenue_formatted,
                "payback_period": sig_data.get('payback_period'),
                "warranty_years": sig_data.get('warranty_years'),
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
            cursor = conn.cursor()

            # Get signature request and quote details
            cursor.execute('''
                SELECT qs.*, q.*
                FROM quote_signatures qs
                JOIN quotes q ON qs.quote_id = q.id
                WHERE qs.signature_token = ?
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = dict(result)

            # Check if expired
            expires_at = datetime.fromisoformat(sig_data['expires_at'])
            if expires_at < datetime.now():
                raise HTTPException(status_code=400, detail="Signature link has expired")

            # Get company settings
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()
            company_info = dict(company) if company else None

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
            cursor = conn.cursor()

            # Get signature request and signed PDF path
            cursor.execute('''
                SELECT signed_pdf_path, status
                FROM quote_signatures
                WHERE signature_token = ?
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
            cursor = conn.cursor()

            # Get signature request details
            cursor.execute('''
                SELECT qs.*, q.*
                FROM quote_signatures qs
                JOIN quotes q ON qs.quote_id = q.id
                WHERE qs.signature_token = ?
            ''', (token,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Signature request not found")

            sig_data = dict(result)

            # Check if expired
            expires_at = datetime.fromisoformat(sig_data['expires_at'])
            if expires_at < datetime.now():
                raise HTTPException(status_code=400, detail="Signature link has expired")

            # Check if already signed
            if sig_data['status'] == 'signed':
                raise HTTPException(status_code=400, detail="Quote already signed")

            # Create quote_signatures directory if it doesn't exist
            signatures_dir = os.path.join("static", "quote_signatures")
            os.makedirs(signatures_dir, exist_ok=True)

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
                SET signature_path = ?,
                    status = 'signed',
                    signed_at = ?,
                    customer_ip = ?,
                    customer_user_agent = ?
                WHERE signature_token = ?
            ''', (signature_path, datetime.now(), client_ip, user_agent, token))
            conn.commit()

            print(f"[SIGNATURE] Customer signed quote #{quote_number}")

            # Get company info for PDF generation
            cursor.execute("SELECT * FROM company_settings ORDER BY id DESC LIMIT 1")
            company = cursor.fetchone()
            company_info = dict(company) if company else {}

        # Generate signed PDF with customer signature
        model_type = sig_data.get('model_type', 'purchase')
        if model_type == 'leasing':
            pdf_buffer = generate_leasing_quote_pdf(sig_data, company_info, signature_path)
        else:
            pdf_buffer = generate_quote_pdf(sig_data, company_info, signature_path)

        # Save signed PDF
        signed_pdfs_dir = os.path.join("static", "signed_pdfs")
        os.makedirs(signed_pdfs_dir, exist_ok=True)

        signed_pdf_filename = f"signed_quote_{quote_number}_{timestamp}.pdf"
        signed_pdf_path = os.path.join(signed_pdfs_dir, signed_pdf_filename)

        with open(signed_pdf_path, "wb") as f:
            pdf_buffer.seek(0)
            f.write(pdf_buffer.read())

        # Update signature record with signed PDF path
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE quote_signatures
                SET signed_pdf_path = ?
                WHERE signature_token = ?
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

from roof_detector import process_roof_image, calculate_panel_layout_from_data, RoofDetector

@app.post("/api/roof-designer/upload")
async def upload_roof_image_endpoint(
    file: UploadFile = File(...),
    customer_name: str = Form(None),
    customer_address: str = Form(None),
    user=Depends(get_current_user)
):
    """
    Upload roof image and run AI detection (standalone - no quote required)

    Returns initial detected roof polygon and obstacles
    """
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Create uploads directory
        uploads_dir = os.path.join("static", "roof_images")
        os.makedirs(uploads_dir, exist_ok=True)

        # Save uploaded image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"roof_{timestamp}.{file_extension}"
        file_path = os.path.join(uploads_dir, filename)

        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"[ROOF DESIGNER] Processing roof image: {file_path}")

        # Run AI detection
        analysis_result = process_roof_image(file_path, min_obstacle_size=500)

        if not analysis_result['success']:
            return JSONResponse(
                status_code=400,
                content={"error": analysis_result.get('error', 'Detection failed')}
            )

        # Save initial detection to database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO roof_designs (
                    customer_name, customer_address, original_image_path,
                    roof_polygon_json, obstacles_json, detection_confidence,
                    created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                customer_name,
                customer_address,
                file_path,
                json.dumps(analysis_result['roof_polygon']),
                json.dumps(analysis_result['obstacles']),
                analysis_result['confidence'],
                user['user_id']
            ))
            conn.commit()
            design_id = cursor.lastrowid

        print(f"[ROOF DESIGNER] Created design #{design_id}")

        return JSONResponse(content={
            "success": True,
            "design_id": design_id,
            "roof_polygon": analysis_result['roof_polygon'],
            "obstacles": analysis_result['obstacles'],
            "confidence": analysis_result['confidence'],
            "image_url": f"/static/roof_images/{filename}",
            "image_dimensions": analysis_result['image_dimensions']
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Roof image upload failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
    user=Depends(get_current_user)
):
    """
    Calculate optimal panel layout based on roof data

    User can edit the detected polygon/obstacles before calculation
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

        # Update database with results
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE roof_designs SET
                    roof_polygon_json = ?,
                    obstacles_json = ?,
                    panels_json = ?,
                    panel_count = ?,
                    system_power_kw = ?,
                    roof_area_m2 = ?,
                    coverage_percent = ?,
                    pixels_per_meter = ?,
                    panel_width_m = ?,
                    panel_height_m = ?,
                    panel_power_w = ?,
                    spacing_m = ?,
                    orientation = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
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
                design_id
            ))
            conn.commit()

        print(f"[ROOF DESIGNER] Layout calculated: {layout_result['total_panels']} panels, {layout_result['total_power_kw']} kW")

        return JSONResponse(content={
            "success": True,
            "panels": layout_result['panels'],
            "total_panels": layout_result['total_panels'],
            "total_power_kw": layout_result['total_power_kw'],
            "coverage_percent": layout_result['coverage_percent'],
            "roof_area_m2": layout_result['roof_area_m2']
        })

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
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM roof_designs WHERE id = ?", (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

            design_data = dict(design)

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
    user=Depends(get_current_user)
):
    """Generate and save visualization image with roof, obstacles, and panels"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Get design data
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM roof_designs WHERE id = ?", (design_id,))
            design = cursor.fetchone()

            if not design:
                raise HTTPException(status_code=404, detail="Design not found")

            design_data = dict(design)

        # Parse data
        roof_polygon = json.loads(design_data['roof_polygon_json'])
        obstacles = json.loads(design_data['obstacles_json']) if design_data.get('obstacles_json') else []
        panels = json.loads(design_data['panels_json']) if design_data.get('panels_json') else []

        # Create visualization
        detector = RoofDetector(design_data['original_image_path'])

        vis_dir = os.path.join("static", "roof_visualizations")
        os.makedirs(vis_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vis_filename = f"vis_{design_id}_{timestamp}.jpg"
        vis_path = os.path.join(vis_dir, vis_filename)

        detector.save_visualization(vis_path, roof_polygon, obstacles, panels)

        # Update database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE roof_designs SET processed_image_path = ? WHERE id = ?
            ''', (vis_path, design_id))
            conn.commit()

        return JSONResponse(content={
            "success": True,
            "visualization_url": f"/static/roof_visualizations/{vis_filename}"
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to save visualization: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/roof-designer", response_class=HTMLResponse)
async def roof_designer_page(request: Request, user=Depends(get_current_user)):
    """Roof designer UI page - standalone tool"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("roof_designer.html", {
        "request": request,
        "user": user
    })

@app.get("/api/roof-designer/list")
async def list_roof_designs(user=Depends(get_current_user)):
    """List all roof designs for current user"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Admin can see all, others see only their own
            if user["role"] == "ADMIN":
                cursor.execute('''
                    SELECT id, customer_name, customer_address, panel_count,
                           system_power_kw, roof_area_m2, created_at
                    FROM roof_designs
                    ORDER BY created_at DESC
                ''')
            else:
                cursor.execute('''
                    SELECT id, customer_name, customer_address, panel_count,
                           system_power_kw, roof_area_m2, created_at
                    FROM roof_designs
                    WHERE created_by = ?
                    ORDER BY created_at DESC
                ''', (user['user_id'],))

            designs = [dict(row) for row in cursor.fetchall()]
            return {"designs": designs}

    except Exception as e:
        print(f"[ERROR] Failed to list designs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
