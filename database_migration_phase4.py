"""
Database Migration: Phase 4 - Energy Production & Financial Estimates

Adds columns for storing energy production calculations and financial estimates
"""

from database import get_db


def migrate_phase4_energy_production():
    """
    Add energy production and financial columns to roof_designs table

    New columns:
    - annual_production_kwh: Estimated annual energy production
    - annual_savings_nis: Estimated annual savings in NIS
    - system_cost_nis: Total system cost estimate
    - payback_years: Estimated payback period
    - roi_25_years: 25-year ROI percentage
    - co2_offset_kg: Annual CO2 offset in kg
    - string_count: Number of electrical strings
    - recommended_inverter_kw: Recommended inverter size
    - energy_estimate_json: Full energy estimate JSON for detailed data
    """
    print("[MIGRATION] Starting Phase 4 - Energy Production & Financial Estimates")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Check if columns already exist
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'roof_designs'
                AND column_name IN (
                    'annual_production_kwh', 'annual_savings_nis', 'system_cost_nis',
                    'payback_years', 'roi_25_years', 'co2_offset_kg',
                    'string_count', 'recommended_inverter_kw', 'energy_estimate_json'
                )
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]

            if len(existing_columns) == 9:
                print("[MIGRATION] All Phase 4 columns already exist - skipping")
                return True

            print(f"[MIGRATION] Found {len(existing_columns)} existing columns, adding remaining...")

            # Add annual_production_kwh column if not exists
            if 'annual_production_kwh' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS annual_production_kwh NUMERIC
                ''')
                print("[MIGRATION] Added column: annual_production_kwh")

            # Add annual_savings_nis column if not exists
            if 'annual_savings_nis' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS annual_savings_nis NUMERIC
                ''')
                print("[MIGRATION] Added column: annual_savings_nis")

            # Add system_cost_nis column if not exists
            if 'system_cost_nis' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS system_cost_nis NUMERIC
                ''')
                print("[MIGRATION] Added column: system_cost_nis")

            # Add payback_years column if not exists
            if 'payback_years' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS payback_years NUMERIC
                ''')
                print("[MIGRATION] Added column: payback_years")

            # Add roi_25_years column if not exists
            if 'roi_25_years' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS roi_25_years NUMERIC
                ''')
                print("[MIGRATION] Added column: roi_25_years")

            # Add co2_offset_kg column if not exists
            if 'co2_offset_kg' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS co2_offset_kg NUMERIC
                ''')
                print("[MIGRATION] Added column: co2_offset_kg")

            # Add string_count column if not exists
            if 'string_count' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS string_count INTEGER
                ''')
                print("[MIGRATION] Added column: string_count")

            # Add recommended_inverter_kw column if not exists
            if 'recommended_inverter_kw' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS recommended_inverter_kw NUMERIC
                ''')
                print("[MIGRATION] Added column: recommended_inverter_kw")

            # Add energy_estimate_json column for full JSON data
            if 'energy_estimate_json' not in existing_columns:
                cursor.execute('''
                    ALTER TABLE roof_designs
                    ADD COLUMN IF NOT EXISTS energy_estimate_json TEXT
                ''')
                print("[MIGRATION] Added column: energy_estimate_json")

            # Create index on production data for queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_roof_designs_production
                ON roof_designs(annual_production_kwh, system_power_kw)
            ''')
            print("[MIGRATION] Created index on production data")

            # Create index on financial data
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_roof_designs_financial
                ON roof_designs(payback_years, annual_savings_nis)
            ''')
            print("[MIGRATION] Created index on financial data")

            conn.commit()
            print("[MIGRATION] Phase 4 migration completed successfully!")
            return True

    except Exception as e:
        print(f"[MIGRATION] Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False


def rollback_phase4_migration():
    """
    Rollback Phase 4 migration (remove added columns)

    WARNING: This will delete energy production data from existing roof designs!
    """
    print("[MIGRATION ROLLBACK] Rolling back Phase 4 - Energy Production")
    print("[MIGRATION ROLLBACK] WARNING: This will delete production data!")

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Remove columns
            cursor.execute('''
                ALTER TABLE roof_designs
                DROP COLUMN IF EXISTS annual_production_kwh,
                DROP COLUMN IF EXISTS annual_savings_nis,
                DROP COLUMN IF EXISTS system_cost_nis,
                DROP COLUMN IF EXISTS payback_years,
                DROP COLUMN IF EXISTS roi_25_years,
                DROP COLUMN IF EXISTS co2_offset_kg,
                DROP COLUMN IF EXISTS string_count,
                DROP COLUMN IF EXISTS recommended_inverter_kw,
                DROP COLUMN IF EXISTS energy_estimate_json
            ''')

            # Drop indexes
            cursor.execute('''
                DROP INDEX IF EXISTS idx_roof_designs_production
            ''')
            cursor.execute('''
                DROP INDEX IF EXISTS idx_roof_designs_financial
            ''')

            conn.commit()
            print("[MIGRATION ROLLBACK] Rollback completed")
            return True

    except Exception as e:
        print(f"[MIGRATION ROLLBACK] Error during rollback: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        # Rollback migration
        response = input("Are you sure you want to rollback Phase 4 migration? (yes/no): ")
        if response.lower() == "yes":
            rollback_phase4_migration()
        else:
            print("Rollback cancelled")
    else:
        # Run migration
        migrate_phase4_energy_production()
