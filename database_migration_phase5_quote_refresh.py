"""
Database Migration: Phase 5 - Quote Refresh

Adds the quote text/default fields introduced by the refreshed quotation flow.
"""

from database import get_db
from quote_defaults import get_legacy_quote_text_defaults


def migrate_phase5_quote_refresh():
    print("[MIGRATION] Starting Phase 5 - Quote Refresh")
    legacy_defaults = get_legacy_quote_text_defaults()

    quote_columns = {
        "maintenance": "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS maintenance TEXT",
        "service": "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS service TEXT",
        "system_value_after_25_years": (
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS system_value_after_25_years NUMERIC"
        ),
        "basic_assumptions_text": (
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS basic_assumptions_text TEXT"
        ),
        "revenue_calculation_text": (
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS revenue_calculation_text TEXT"
        ),
        "summary_text": "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS summary_text TEXT",
        "environmental_impact_text": (
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS environmental_impact_text TEXT"
        ),
    }

    pricing_columns = {
        "basic_assumptions_default": (
            "ALTER TABLE pricing_parameters ADD COLUMN IF NOT EXISTS basic_assumptions_default TEXT"
        ),
        "revenue_calculation_default": (
            "ALTER TABLE pricing_parameters ADD COLUMN IF NOT EXISTS revenue_calculation_default TEXT"
        ),
        "summary_default": (
            "ALTER TABLE pricing_parameters ADD COLUMN IF NOT EXISTS summary_default TEXT"
        ),
        "environmental_impact_default": (
            "ALTER TABLE pricing_parameters ADD COLUMN IF NOT EXISTS environmental_impact_default TEXT"
        ),
    }

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            for sql in quote_columns.values():
                cursor.execute(sql)

            for sql in pricing_columns.values():
                cursor.execute(sql)

            cursor.execute("SELECT COUNT(*) FROM pricing_parameters")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    """
                    INSERT INTO pricing_parameters (
                        price_per_kwp, production_per_kwp, tariff_rate, trees_multiplier, vat_rate,
                        basic_assumptions_default, revenue_calculation_default, summary_default,
                        environmental_impact_default
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        4300,
                        1360,
                        0.48,
                        0.05,
                        0.17,
                        legacy_defaults["basic_assumptions_default"],
                        legacy_defaults["revenue_calculation_default"],
                        legacy_defaults["summary_default"],
                        legacy_defaults["environmental_impact_default"],
                    ),
                )
            else:
                for field, value in legacy_defaults.items():
                    cursor.execute(
                        f"""
                        UPDATE pricing_parameters
                        SET {field} = %s
                        WHERE ({field} IS NULL OR {field} = '')
                        """,
                        (value,),
                    )

            conn.commit()
            print("[MIGRATION] Phase 5 migration completed successfully!")
            return True
    except Exception as e:
        print(f"[MIGRATION] Error during Phase 5 migration: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    migrate_phase5_quote_refresh()
