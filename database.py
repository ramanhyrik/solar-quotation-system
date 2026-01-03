import sqlite3
import hashlib
import bcrypt
from datetime import datetime
from contextlib import contextmanager

DATABASE_FILE = "solar_quotes.db"

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

if __name__ == "__main__":
    init_database()
    print("[OK] Database initialized successfully!")
