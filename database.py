import hashlib
import bcrypt
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from quote_defaults import get_legacy_quote_text_defaults

# PostgreSQL database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("[DB ERROR] DATABASE_URL environment variable is required!")

print("[DB] Using PostgreSQL database")

@contextmanager
def get_db():
    """Database connection context manager for PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()

def get_cursor(conn):
    """Get PostgreSQL cursor with RealDictCursor factory"""
    return conn.cursor(cursor_factory=RealDictCursor)

def init_database():
    """Initialize PostgreSQL database with tables"""
    print("[DB] Initializing PostgreSQL database...")
    legacy_defaults = get_legacy_quote_text_defaults()

    with get_db() as conn:
        cursor = conn.cursor()

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
                maintenance TEXT,
                service TEXT,
                system_value_after_25_years NUMERIC,
                basic_assumptions_text TEXT,
                revenue_calculation_text TEXT,
                summary_text TEXT,
                environmental_impact_text TEXT,
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
                leasing_payment_ratio NUMERIC DEFAULT 0.25,
                basic_assumptions_default TEXT,
                revenue_calculation_default TEXT,
                summary_default TEXT,
                environmental_impact_default TEXT,
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

        # Insert default data
        cursor.execute("SELECT COUNT(*) FROM pricing_parameters")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO pricing_parameters
                (
                    price_per_kwp, production_per_kwp, tariff_rate, trees_multiplier, vat_rate,
                    basic_assumptions_default, revenue_calculation_default, summary_default,
                    environmental_impact_default
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                4300,
                1360,
                0.48,
                0.05,
                0.17,
                legacy_defaults["basic_assumptions_default"],
                legacy_defaults["revenue_calculation_default"],
                legacy_defaults["summary_default"],
                legacy_defaults["environmental_impact_default"],
            ))
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

    print("[OK] Database initialized successfully!")

    # Run Phase 1 migration (Map Integration)
    try:
        from database_migration_phase1 import migrate_phase1_map_integration
        migrate_phase1_map_integration()
    except ImportError:
        print("[WARNING] database_migration_phase1.py not found - skipping Phase 1 migration")
    except Exception as e:
        print(f"[WARNING] Phase 1 migration failed: {e}")

    # Run Phase 2 migration (Automatic Roof Measurements)
    try:
        from database_migration_phase2 import migrate_phase2_roof_measurements
        migrate_phase2_roof_measurements()
    except ImportError:
        print("[WARNING] database_migration_phase2.py not found - skipping Phase 2 migration")
    except Exception as e:
        print(f"[WARNING] Phase 2 migration failed: {e}")

    # Run Phase 4 migration (Energy Production & Financial Estimates)
    try:
        from database_migration_phase4 import migrate_phase4_energy_production
        migrate_phase4_energy_production()
    except ImportError:
        print("[WARNING] database_migration_phase4.py not found - skipping Phase 4 migration")
    except Exception as e:
        print(f"[WARNING] Phase 4 migration failed: {e}")

    # Run Phase 5 migration (Quote refresh fields)
    try:
        from database_migration_phase5_quote_refresh import migrate_phase5_quote_refresh
        migrate_phase5_quote_refresh()
    except ImportError:
        print("[WARNING] database_migration_phase5_quote_refresh.py not found - skipping Phase 5 migration")
    except Exception as e:
        print(f"[WARNING] Phase 5 migration failed: {e}")

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

# Session management functions
def create_session_db(user_id: int, email: str, role: str, session_id: str, expires_hours: int = 24) -> None:
    """Create a new session in the database"""
    expires_at = datetime.now() + timedelta(hours=expires_hours)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (session_id, user_id, email, role, expires_at)
            VALUES (%s, %s, %s, %s, %s)
        ''', (session_id, user_id, email, role, expires_at))
        conn.commit()
        print(f"[SESSION] Created session for user {email} (expires in {expires_hours}h)")

def get_session_db(session_id: str) -> Optional[dict]:
    """Get session from database if valid and not expired"""
    if not session_id:
        return None

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT user_id, email, role, created_at, expires_at
            FROM sessions
            WHERE session_id = %s AND expires_at > NOW()
        ''', (session_id,))

        session = cursor.fetchone()
        return dict(session) if session else None

def delete_session_db(session_id: str) -> None:
    """Delete a session from the database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
        conn.commit()
        print(f"[SESSION] Deleted session: {session_id[:16]}...")

def cleanup_expired_sessions_db() -> int:
    """Remove expired sessions from the database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            print(f"[SESSION] Cleaned up {deleted_count} expired session(s)")
        return deleted_count

if __name__ == "__main__":
    init_database()
