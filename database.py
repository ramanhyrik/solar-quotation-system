import sqlite3
import hashlib
import bcrypt
import os
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

# Use persistent disk on Render, local file for development
def get_persistent_dir():
    """Get the persistent directory with validation"""
    if os.getenv("RENDER"):
        # On Render, ALWAYS use the persistent disk mount point
        persistent_path = "/opt/render/project/src"

        # Verify the persistent disk is mounted and writable
        if os.path.exists(persistent_path) and os.access(persistent_path, os.W_OK):
            print(f"[DB] Using Render persistent disk: {persistent_path}")
            return persistent_path
        else:
            # CRITICAL: If persistent disk isn't available, log error and fail fast
            error_msg = f"[DB ERROR] Persistent disk not found or not writable at {persistent_path}!"
            print(error_msg)
            raise RuntimeError(error_msg)
    else:
        # Local development
        print("[DB] Using local directory for development")
        return "."

PERSISTENT_DIR = get_persistent_dir()
DATABASE_FILE = os.path.join(PERSISTENT_DIR, "data", "solar_quotes.db")

@contextmanager
def get_db():
    """Database connection context manager"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize database with tables"""
    # Ensure database directory exists
    db_dir = os.path.dirname(DATABASE_FILE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        print(f"[DB] Created database directory: {db_dir}")

    # Log the absolute database file path for verification
    abs_db_path = os.path.abspath(DATABASE_FILE)
    print(f"[DB] Database file location: {abs_db_path}")

    # Verify database directory is writable
    if not os.access(db_dir, os.W_OK):
        raise RuntimeError(f"[DB ERROR] Database directory is not writable: {db_dir}")

    with get_db() as conn:
        cursor = conn.cursor()

        # Users table
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

        # Sessions table (persistent session storage)
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

        # Create index on expires_at for faster cleanup
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
            ON sessions(expires_at)
        ''')

        # Quotes table
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

        # Pricing parameters table
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

        # Company settings table
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

        # Customer submissions table (public contact form)
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

        # Quote signatures table (for web portal digital signatures)
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

        # Roof designs table (for AI-powered panel layout)
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

        # Add model_type column to quotes table if it doesn't exist (migration)
        cursor.execute("PRAGMA table_info(quotes)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'model_type' not in columns:
            cursor.execute("ALTER TABLE quotes ADD COLUMN model_type TEXT DEFAULT 'purchase'")
            conn.commit()
            print("[OK] Added model_type column to quotes table")

        # Add calculator parameters to pricing_parameters table (migration)
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

        # Insert default pricing parameters if not exists
        cursor.execute("SELECT COUNT(*) FROM pricing_parameters")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO pricing_parameters
                (price_per_kwp, production_per_kwp, tariff_rate, trees_multiplier, vat_rate)
                VALUES (4300, 1360, 0.48, 0.05, 0.17)
            ''')
            conn.commit()

        # Insert default company settings if not exists
        cursor.execute("SELECT COUNT(*) FROM company_settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO company_settings
                (company_name, company_email, primary_color, secondary_color)
                VALUES ('U Solar', 'usolarisrael@gmail.com', '#00358A', '#D9FF0D')
            ''')
            conn.commit()

        # Create default admin user if not exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN'")
        if cursor.fetchone()[0] == 0:
            # Default password: admin123
            hashed_password = hashlib.sha256("admin123".encode()).hexdigest()
            cursor.execute('''
                INSERT INTO users (email, password, name, role)
                VALUES ('admin@solar.com', ?, 'Admin User', 'ADMIN')
            ''', (hashed_password,))
            conn.commit()
            print("[OK] Default admin user created: admin@solar.com / admin123")

def hash_password(password: str) -> str:
    """Hash password using bcrypt with SHA-256 pre-hash (handles any length)"""
    # Pre-hash with SHA-256 to handle passwords longer than 72 bytes
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    # Hash with bcrypt
    return bcrypt.hashpw(password_hash.encode(), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt with SHA-256 pre-hash or legacy hashes"""
    try:
        # Check if it's a bcrypt hash (starts with $2b$, $2a$, or $2y$)
        if hashed.startswith('$2'):
            # Pre-hash with SHA-256 (same as hash_password)
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            return bcrypt.checkpw(password_hash.encode(), hashed.encode())
        else:
            # Fallback for old SHA-256 hashes (default admin user)
            return hashlib.sha256(password.encode()).hexdigest() == hashed
    except Exception as e:
        print(f"[AUTH] Password verification error: {e}")
        return False

def generate_quote_number() -> str:
    """Generate unique quote number"""
    from datetime import datetime
    import random
    date_part = datetime.now().strftime("%Y%m")
    random_part = f"{random.randint(1000, 9999):04d}"
    return f"SQ-{date_part}-{random_part}"

# Session management functions (persistent session storage)
def create_session_db(user_id: int, email: str, role: str, session_id: str, expires_hours: int = 24) -> None:
    """Create a new session in the database"""
    from datetime import timedelta
    expires_at = datetime.now() + timedelta(hours=expires_hours)

    with get_db() as conn:
        cursor = conn.cursor()
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
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, email, role, created_at, expires_at
            FROM sessions
            WHERE session_id = ? AND expires_at > datetime('now')
        ''', (session_id,))
        session = cursor.fetchone()

        if session:
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
        cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        print(f"[SESSION] Deleted session: {session_id[:16]}...")

def cleanup_expired_sessions_db() -> int:
    """Remove expired sessions from the database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            print(f"[SESSION] Cleaned up {deleted_count} expired session(s)")
        return deleted_count

if __name__ == "__main__":
    init_database()
    print("[OK] Database initialized successfully!")
