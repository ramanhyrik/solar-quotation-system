"""
Database Migration: Phase 1 - Map Integration

Adds columns for geocoding and satellite imagery support to roof_designs table
"""

import os
from database import get_db

def migrate_phase1_map_integration():
    """
    Add location-related columns to roof_designs table

    New columns:
    - latitude: Geographic latitude coordinate
    - longitude: Geographic longitude coordinate
    - zoom_level: Map zoom level used for imagery
    - map_source: Source of map imagery (mapbox/google/osm)
    - geocoded_address: Full geocoded address from Nominatim
    - meters_per_pixel: Calculated scale factor for measurements
    """
    print("[MIGRATION] Starting Phase 1 - Map Integration")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Check if columns already exist
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'roof_designs'
                AND column_name IN ('latitude', 'longitude', 'zoom_level', 'map_source', 'geocoded_address', 'meters_per_pixel')
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]

            if len(existing_columns) == 6:
                print("[MIGRATION] ✓ All Phase 1 columns already exist - skipping")
                return True

            print(f"[MIGRATION] Found {len(existing_columns)} existing columns, adding remaining...")

            # Add latitude column if not exists
            if 'latitude' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS latitude NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: latitude")

            # Add longitude column if not exists
            if 'longitude' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS longitude NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: longitude")

            # Add zoom_level column if not exists
            if 'zoom_level' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS zoom_level INTEGER DEFAULT 20
                ''')
                print("[MIGRATION] ✓ Added column: zoom_level")

            # Add map_source column if not exists
            if 'map_source' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS map_source VARCHAR(50) DEFAULT 'mapbox'
                ''')
                print("[MIGRATION] ✓ Added column: map_source")

            # Add geocoded_address column if not exists
            if 'geocoded_address' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS geocoded_address TEXT
                ''')
                print("[MIGRATION] ✓ Added column: geocoded_address")

            # Add meters_per_pixel column if not exists
            if 'meters_per_pixel' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS meters_per_pixel NUMERIC
                ''')
                print("[MIGRATION] ✓ Added column: meters_per_pixel")

            # Create index on latitude/longitude for spatial queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_roof_designs_location
                ON roof_designs(latitude, longitude)
            ''')
            print("[MIGRATION] ✓ Created index on latitude/longitude")

            conn.commit()
            print("[MIGRATION] ✓ Phase 1 migration completed successfully!")
            return True

    except Exception as e:
        print(f"[MIGRATION] ✗ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False


def rollback_phase1_migration():
    """
    Rollback Phase 1 migration (remove added columns)

    WARNING: This will delete location data from existing roof designs!
    """
    print("[MIGRATION ROLLBACK] Rolling back Phase 1 - Map Integration")
    print("[MIGRATION ROLLBACK] WARNING: This will delete location data!")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Remove columns
            cursor.execute('''
                ALTER TABLE roof_designs
                DROP COLUMN IF EXISTS latitude,
                DROP COLUMN IF EXISTS longitude,
                DROP COLUMN IF EXISTS zoom_level,
                DROP COLUMN IF EXISTS map_source,
                DROP COLUMN IF EXISTS geocoded_address,
                DROP COLUMN IF EXISTS meters_per_pixel
            ''')

            # Drop index
            cursor.execute('''
                DROP INDEX IF EXISTS idx_roof_designs_location
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
        response = input("Are you sure you want to rollback Phase 1 migration? (yes/no): ")
        if response.lower() == "yes":
            rollback_phase1_migration()
        else:
            print("Rollback cancelled")
    else:
        # Run migration
        migrate_phase1_map_integration()
