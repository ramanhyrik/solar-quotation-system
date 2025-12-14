import sqlite3
import hashlib
from datetime import datetime
from contextlib import contextmanager
from passlib.hash import bcrypt

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
    """Hash password using bcrypt"""
    return bcrypt.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash"""
    try:
        return bcrypt.verify(password, hashed)
    except:
        # Fallback for old SHA-256 hashes (for migration)
        return hashlib.sha256(password.encode()).hexdigest() == hashed

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
