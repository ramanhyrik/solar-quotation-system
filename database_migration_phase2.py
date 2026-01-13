"""
Database Migration: Phase 2 - Automatic Roof Measurements

Adds columns for real-world dimensions, orientation, and measurement validation
"""

import os
from database import get_db

def migrate_phase2_roof_measurements():
    """
    Add measurement-related columns to roof_designs table

    New columns:
    - roof_length_m: Longest roof dimension in meters
    - roof_width_m: Perpendicular width in meters
    - roof_perimeter_m: Total perimeter in meters
    - roof_azimuth: Roof orientation (0-360°, 0=North)
    - roof_type: Roof shape (flat/gabled/hipped/complex)
    - measurement_confidence: Confidence score (0-100%)
    - usable_area_m2: Area after setbacks
    - estimated_panel_count: Quick estimate before detailed calculation
    """
    print("[MIGRATION] Starting Phase 2 - Automatic Roof Measurements")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Check if columns already exist
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'roof_designs'
                AND column_name IN (
                    'roof_length_m', 'roof_width_m', 'roof_perimeter_m',
                    'roof_azimuth', 'roof_type', 'measurement_confidence',
                    'usable_area_m2', 'estimated_panel_count'
                )
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]

            if len(existing_columns) == 8:
                print("[MIGRATION] ✓ All Phase 2 columns already exist - skipping")
                return True

            print(f"[MIGRATION] Found {len(existing_columns)} existing columns, adding remaining...")

            # Add roof_length_m column if not exists
            if 'roof_length_m' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS roof_length_m NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: roof_length_m")

            # Add roof_width_m column if not exists
            if 'roof_width_m' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS roof_width_m NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: roof_width_m")

            # Add roof_perimeter_m column if not exists
            if 'roof_perimeter_m' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS roof_perimeter_m NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: roof_perimeter_m")

            # Add roof_azimuth column if not exists (0-360 degrees, 0=North)
            if 'roof_azimuth' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS roof_azimuth NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: roof_azimuth")

            # Add roof_type column if not exists
            if 'roof_type' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS roof_type VARCHAR(50) DEFAULT 'flat'
                ''')
                print("[MIGRATION] ✓ Added column: roof_type")

            # Add measurement_confidence column if not exists (0-100%)
            if 'measurement_confidence' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS measurement_confidence NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: measurement_confidence")

            # Add usable_area_m2 column if not exists (area after setbacks)
            if 'usable_area_m2' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS usable_area_m2 NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: usable_area_m2")

            # Add estimated_panel_count column if not exists
            if 'estimated_panel_count' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS estimated_panel_count INTEGER
                ''')
                print("[MIGRATION] ✓ Added column: estimated_panel_count")

            # Create index on roof dimensions for queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_roof_designs_dimensions
                ON roof_designs(roof_length_m, roof_width_m, roof_area_m2)
            ''')
            print("[MIGRATION] ✓ Created index on roof dimensions")

            # Create index on roof orientation
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_roof_designs_orientation
                ON roof_designs(roof_azimuth)
            ''')
            print("[MIGRATION] ✓ Created index on roof orientation")

            conn.commit()
            print("[MIGRATION] ✓ Phase 2 migration completed successfully!")
            return True

    except Exception as e:
        print(f"[MIGRATION] ✗ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False


def rollback_phase2_migration():
    """
    Rollback Phase 2 migration (remove added columns)

    WARNING: This will delete measurement data from existing roof designs!
    """
    print("[MIGRATION ROLLBACK] Rolling back Phase 2 - Automatic Roof Measurements")
    print("[MIGRATION ROLLBACK] WARNING: This will delete measurement data!")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Remove columns
            cursor.execute('''
                ALTER TABLE roof_designs
                DROP COLUMN IF EXISTS roof_length_m,
                DROP COLUMN IF EXISTS roof_width_m,
                DROP COLUMN IF EXISTS roof_perimeter_m,
                DROP COLUMN IF EXISTS roof_azimuth,
                DROP COLUMN IF EXISTS roof_type,
                DROP COLUMN IF EXISTS measurement_confidence,
                DROP COLUMN IF EXISTS usable_area_m2,
                DROP COLUMN IF EXISTS estimated_panel_count
            ''')

            # Drop indexes
            cursor.execute('''
                DROP INDEX IF EXISTS idx_roof_designs_dimensions
            ''')
            cursor.execute('''
                DROP INDEX IF EXISTS idx_roof_designs_orientation
            ''')

            conn.commit()
            print("[MIGRATION ROLLBACK] ✓ Rollback completed")
            return True

    except Exception as e:
        print(f"[MIGRATION ROLLBACK] ✗ Error during rollback: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        # Rollback migration
        response = input("Are you sure you want to rollback Phase 2 migration? (yes/no): ")
        if response.lower() == "yes":
            rollback_phase2_migration()
        else:
            print("Rollback cancelled")
    else:
        # Run migration
        migrate_phase2_roof_measurements()
