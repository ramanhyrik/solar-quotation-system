import hashlib
import bcrypt
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional
import random

# Database configuration - PostgreSQL on Render, SQLite locally
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("[DB] Using PostgreSQL database")
else:
    import sqlite3
    print("[DB] Using SQLite database for local development")

@contextmanager
def get_db():
    """Database connection context manager - works with both PostgreSQL and SQLite"""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            yield conn
        finally:
            conn.close()
    else:
        # SQLite for local development
        db_dir = os.path.dirname("data/solar_quotes.db")
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect("data/solar_quotes.db")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def init_database():
    """Initialize database with tables - supports both PostgreSQL and SQLite"""
    print(f"[DB] Initializing database...")

    with get_db() as conn:
        cursor = conn.cursor()

        if USE_POSTGRES:
            # PostgreSQL syntax
            print("[DB] Creating PostgreSQL tables...")

            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    name VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'SALES_REP',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                ON sessions(expires_at)
            ''')

            # Quotes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quotes (
                    id SERIAL PRIMARY KEY,
                    quote_number VARCHAR(100) UNIQUE NOT NULL,
                    customer_name VARCHAR(255) NOT NULL,
                    customer_phone VARCHAR(50),
                    customer_email VARCHAR(255),
                    customer_address TEXT,
                    system_size NUMERIC NOT NULL,
                    roof_area NUMERIC,
                    annual_production NUMERIC,
                    panel_type VARCHAR(255),
                    panel_count INTEGER,
                    inverter_type VARCHAR(255),
                    direction VARCHAR(50),
                    tilt_angle NUMERIC,
                    warranty_years INTEGER DEFAULT 25,
                    total_price NUMERIC NOT NULL,
                    annual_revenue NUMERIC NOT NULL,
                    payback_period NUMERIC NOT NULL,
                    status VARCHAR(50) DEFAULT 'DRAFT',
                    model_type VARCHAR(50) DEFAULT 'purchase',
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')

            # Pricing parameters table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pricing_parameters (
                    id SERIAL PRIMARY KEY,
                    price_per_kwp NUMERIC DEFAULT 4300,
                    production_per_kwp NUMERIC DEFAULT 1360,
                    tariff_rate NUMERIC DEFAULT 0.48,
                    trees_multiplier NUMERIC DEFAULT 0.05,
                    vat_rate NUMERIC DEFAULT 0.17,
                    direction_south NUMERIC DEFAULT 1.0,
                    direction_southeast NUMERIC DEFAULT 0.95,
                    direction_southwest NUMERIC DEFAULT 0.95,
                    direction_east_west NUMERIC DEFAULT 0.9,
                    shading_factor NUMERIC DEFAULT 0.85,
                    degradation_rate NUMERIC DEFAULT 0.004,
                    operating_cost_base NUMERIC DEFAULT 0.005,
                    operating_cost_increase NUMERIC DEFAULT 0.02,
                    roof_area_per_kw NUMERIC DEFAULT 7.0,
                    leasing_payment_ratio NUMERIC DEFAULT 0.3,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Company settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS company_settings (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(255) DEFAULT 'Solar Pro',
                    company_phone VARCHAR(50),
                    company_email VARCHAR(255),
                    company_address TEXT,
                    company_logo TEXT,
                    primary_color VARCHAR(20) DEFAULT '#00358A',
                    secondary_color VARCHAR(20) DEFAULT '#D9FF0D',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Customer submissions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customer_submissions (
                    id SERIAL PRIMARY KEY,
                    customer_name VARCHAR(255) NOT NULL,
                    customer_phone VARCHAR(50),
                    customer_email VARCHAR(255),
                    customer_address TEXT,
                    roof_area NUMERIC,
                    signature_path TEXT,
                    submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'new',
                    notes TEXT
                )
            ''')

            # Quote signatures table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quote_signatures (
                    id SERIAL PRIMARY KEY,
                    quote_id INTEGER NOT NULL,
                    signature_token VARCHAR(255) UNIQUE NOT NULL,
                    signature_path TEXT,
                    signed_pdf_path TEXT,
                    customer_ip VARCHAR(100),
                    customer_user_agent TEXT,
                    status VARCHAR(50) DEFAULT 'pending',
                    expires_at TIMESTAMP,
                    viewed_at TIMESTAMP,
                    signed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE
                )
            ''')

            # Roof designs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roof_designs (
                    id SERIAL PRIMARY KEY,
                    quote_id INTEGER,
                    customer_name VARCHAR(255),
                    customer_address TEXT,
                    original_image_path TEXT NOT NULL,
                    processed_image_path TEXT,
                    roof_polygon_json TEXT,
                    obstacles_json TEXT,
                    panels_json TEXT,
                    panel_count INTEGER,
                    system_power_kw NUMERIC,
                    roof_area_m2 NUMERIC,
                    coverage_percent NUMERIC,
                    pixels_per_meter NUMERIC DEFAULT 100,
                    panel_width_m NUMERIC DEFAULT 1.7,
                    panel_height_m NUMERIC DEFAULT 1.0,
                    panel_power_w INTEGER DEFAULT 400,
                    spacing_m NUMERIC DEFAULT 0.05,
                    orientation VARCHAR(50) DEFAULT 'landscape',
                    detection_confidence NUMERIC,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE SET NULL,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')

            conn.commit()

            # Insert default data for PostgreSQL (using %s placeholders)
            cursor.execute("SELECT COUNT(*) FROM pricing_parameters")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO pricing_parameters
                    (price_per_kwp, production_per_kwp, tariff_rate, trees_multiplier, vat_rate)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (4300, 1360, 0.48, 0.05, 0.17))
                conn.commit()
                print("[OK] Default pricing parameters created")

            cursor.execute("SELECT COUNT(*) FROM company_settings")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO company_settings
                    (company_name, company_email, primary_color, secondary_color)
                    VALUES (%s, %s, %s, %s)
                ''', ('U Solar', 'usolarisrael@gmail.com', '#00358A', '#D9FF0D'))
                conn.commit()
                print("[OK] Default company settings created")

            cursor.execute("SELECT COUNT(*) FROM users WHERE role=%s", ('ADMIN',))
            if cursor.fetchone()[0] == 0:
                hashed_password = hashlib.sha256("admin123".encode()).hexdigest()
                cursor.execute('''
                    INSERT INTO users (email, password, name, role)
                    VALUES (%s, %s, %s, %s)
                ''', ('admin@solar.com', hashed_password, 'Admin User', 'ADMIN'))
                conn.commit()
                print("[OK] Default admin user created: admin@solar.com / admin123")

        else:
            # SQLite syntax (original code)
            print("[DB] Creating SQLite tables...")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    name TEXT,
                    role TEXT DEFAULT 'SALES_REP',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                ON sessions(expires_at)
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote_number TEXT UNIQUE NOT NULL,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT,
                    customer_email TEXT,
                    customer_address TEXT,
                    system_size REAL NOT NULL,
                    roof_area REAL,
                    annual_production REAL,
                    panel_type TEXT,
                    panel_count INTEGER,
                    inverter_type TEXT,
                    direction TEXT,
                    tilt_angle REAL,
                    warranty_years INTEGER DEFAULT 25,
                    total_price REAL NOT NULL,
                    annual_revenue REAL NOT NULL,
                    payback_period REAL NOT NULL,
                    status TEXT DEFAULT 'DRAFT',
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pricing_parameters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    price_per_kwp REAL DEFAULT 4300,
                    production_per_kwp REAL DEFAULT 1360,
                    tariff_rate REAL DEFAULT 0.48,
                    trees_multiplier REAL DEFAULT 0.05,
                    vat_rate REAL DEFAULT 0.17,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS company_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT DEFAULT 'Solar Pro',
                    company_phone TEXT,
                    company_email TEXT,
                    company_address TEXT,
                    company_logo TEXT,
                    primary_color TEXT DEFAULT '#00358A',
                    secondary_color TEXT DEFAULT '#D9FF0D',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customer_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT,
                    customer_email TEXT,
                    customer_address TEXT,
                    roof_area REAL,
                    signature_path TEXT,
                    submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'new',
                    notes TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quote_signatures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote_id INTEGER NOT NULL,
                    signature_token TEXT UNIQUE NOT NULL,
                    signature_path TEXT,
                    signed_pdf_path TEXT,
                    customer_ip TEXT,
                    customer_user_agent TEXT,
                    status TEXT DEFAULT 'pending',
                    expires_at TIMESTAMP,
                    viewed_at TIMESTAMP,
                    signed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roof_designs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote_id INTEGER,
                    customer_name TEXT,
                    customer_address TEXT,
                    original_image_path TEXT NOT NULL,
                    processed_image_path TEXT,
                    roof_polygon_json TEXT,
                    obstacles_json TEXT,
                    panels_json TEXT,
                    panel_count INTEGER,
                    system_power_kw REAL,
                    roof_area_m2 REAL,
                    coverage_percent REAL,
                    pixels_per_meter REAL DEFAULT 100,
                    panel_width_m REAL DEFAULT 1.7,
                    panel_height_m REAL DEFAULT 1.0,
                    panel_power_w INTEGER DEFAULT 400,
                    spacing_m REAL DEFAULT 0.05,
                    orientation TEXT DEFAULT 'landscape',
                    detection_confidence REAL,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE SET NULL,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')

            conn.commit()

            # SQLite migrations
            cursor.execute("PRAGMA table_info(quotes)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'model_type' not in columns:
                cursor.execute("ALTER TABLE quotes ADD COLUMN model_type TEXT DEFAULT 'purchase'")
                conn.commit()
                print("[OK] Added model_type column to quotes table")

            cursor.execute("PRAGMA table_info(pricing_parameters)")
            pricing_columns = [col[1] for col in cursor.fetchall()]

            calculator_params = {
                'direction_south': 1.0,
                'direction_southeast': 0.95,
                'direction_southwest': 0.95,
                'direction_east_west': 0.9,
                'shading_factor': 0.85,
                'degradation_rate': 0.004,
                'operating_cost_base': 0.005,
                'operating_cost_increase': 0.02,
                'roof_area_per_kw': 7.0,
                'leasing_payment_ratio': 0.3
            }

            for param, default_value in calculator_params.items():
                if param not in pricing_columns:
                    cursor.execute(f"ALTER TABLE pricing_parameters ADD COLUMN {param} REAL DEFAULT {default_value}")
                    print(f"[OK] Added {param} to pricing_parameters")

            conn.commit()

            # Insert default data for SQLite
            cursor.execute("SELECT COUNT(*) FROM pricing_parameters")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO pricing_parameters
                    (price_per_kwp, production_per_kwp, tariff_rate, trees_multiplier, vat_rate)
                    VALUES (4300, 1360, 0.48, 0.05, 0.17)
                ''')
                conn.commit()

            cursor.execute("SELECT COUNT(*) FROM company_settings")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO company_settings
                    (company_name, company_email, primary_color, secondary_color)
                    VALUES ('U Solar', 'usolarisrael@gmail.com', '#00358A', '#D9FF0D')
                ''')
                conn.commit()

            cursor.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN'")
            if cursor.fetchone()[0] == 0:
                hashed_password = hashlib.sha256("admin123".encode()).hexdigest()
                cursor.execute('''
                    INSERT INTO users (email, password, name, role)
                    VALUES ('admin@solar.com', ?, 'Admin User', 'ADMIN')
                ''', (hashed_password,))
                conn.commit()
                print("[OK] Default admin user created: admin@solar.com / admin123")

    print("[OK] Database initialized successfully!")

def hash_password(password: str) -> str:
    """Hash password using bcrypt with SHA-256 pre-hash (handles any length)"""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return bcrypt.hashpw(password_hash.encode(), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt with SHA-256 pre-hash or legacy hashes"""
    try:
        if hashed.startswith('$2'):
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            return bcrypt.checkpw(password_hash.encode(), hashed.encode())
        else:
            return hashlib.sha256(password.encode()).hexdigest() == hashed
    except Exception as e:
        print(f"[AUTH] Password verification error: {e}")
        return False

def generate_quote_number() -> str:
    """Generate unique quote number"""
    date_part = datetime.now().strftime("%Y%m")
    random_part = f"{random.randint(1000, 9999):04d}"
    return f"SQ-{date_part}-{random_part}"

# Session management functions (persistent session storage)
def create_session_db(user_id: int, email: str, role: str, session_id: str, expires_hours: int = 24) -> None:
    """Create a new session in the database"""
    expires_at = datetime.now() + timedelta(hours=expires_hours)

    with get_db() as conn:
        cursor = conn.cursor()
        if USE_POSTGRES:
            cursor.execute('''
                INSERT INTO sessions (session_id, user_id, email, role, expires_at)
                VALUES (%s, %s, %s, %s, %s)
            ''', (session_id, user_id, email, role, expires_at))
        else:
            cursor.execute('''
                INSERT INTO sessions (session_id, user_id, email, role, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, user_id, email, role, expires_at))
        conn.commit()
        print(f"[SESSION] Created session for user {email} (expires in {expires_hours}h)")

def get_session_db(session_id: str) -> Optional[dict]:
    """Get session from database if valid and not expired"""
    if not session_id:
        return None

    with get_db() as conn:
        if USE_POSTGRES:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT user_id, email, role, created_at, expires_at
                FROM sessions
                WHERE session_id = %s AND expires_at > NOW()
            ''', (session_id,))
        else:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, email, role, created_at, expires_at
                FROM sessions
                WHERE session_id = ? AND expires_at > datetime('now')
            ''', (session_id,))

        session = cursor.fetchone()

        if session:
            if USE_POSTGRES:
                return dict(session)
            else:
                return {
                    "user_id": session["user_id"],
                    "email": session["email"],
                    "role": session["role"],
                    "created_at": session["created_at"]
                }
        return None

def delete_session_db(session_id: str) -> None:
    """Delete a session from the database"""
    with get_db() as conn:
        cursor = conn.cursor()
        if USE_POSTGRES:
            cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
        else:
            cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        print(f"[SESSION] Deleted session: {session_id[:16]}...")

def cleanup_expired_sessions_db() -> int:
    """Remove expired sessions from the database"""
    with get_db() as conn:
        cursor = conn.cursor()
        if USE_POSTGRES:
            cursor.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
        else:
            cursor.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            print(f"[SESSION] Cleaned up {deleted_count} expired session(s)")
        return deleted_count

if __name__ == "__main__":
    init_database()
    print("[OK] Database initialized successfully!")
