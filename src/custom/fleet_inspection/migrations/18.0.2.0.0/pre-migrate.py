import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Keep the former vehicle_type selection values before Odoo updates the table.

    Runs before the ORM creates the new columns, and does nothing on a second run.
    """
    if not version:
        return
    if sql.column_exists(cr, "fleet_inspection", "vehicle_type") and \
            not sql.column_exists(cr, "fleet_inspection", "vehicle_type_legacy"):
        sql.rename_column(cr, "fleet_inspection", "vehicle_type", "vehicle_type_legacy")
        # The former field was required: keeping NOT NULL would block every new inspection
        cr.execute("ALTER TABLE fleet_inspection ALTER COLUMN vehicle_type_legacy DROP NOT NULL")
        _logger.info("fleet_inspection: former vehicle_type column kept as vehicle_type_legacy")
    # Create the new column empty. If the ORM created it, it would fill every existing
    # row with the default type (Car) whenever the catalog already exists, and the
    # post-migration would no longer know which rows still need their real type.
    cr.execute("ALTER TABLE fleet_inspection ADD COLUMN IF NOT EXISTS vehicle_type_id int4")
