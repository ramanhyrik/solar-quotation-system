"""
Database Migration: Phase 6 - Configurable Financial Metric Cubes

Adds pricing_parameters.financial_metrics_config, a JSON list of cube
definitions ({label, calculation, enabled}) managed from the admin panel.

Safe to run repeatedly (ADD COLUMN IF NOT EXISTS). A NULL/empty value is
treated as "use the built-in default cubes", so seeding is optional and no
existing quote changes until the admin edits the configuration.
"""

from database import get_db


def migrate_phase6_metrics_config():
    print("[MIGRATION] Starting Phase 6 - Financial Metrics Config")
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "ALTER TABLE pricing_parameters "
                "ADD COLUMN IF NOT EXISTS financial_metrics_config TEXT"
            )
            conn.commit()
            print("[MIGRATION] Phase 6 migration completed successfully!")
            return True
    except Exception as e:
        print(f"[MIGRATION] Error during Phase 6 migration: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    migrate_phase6_metrics_config()
