import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Assign the catalog vehicle type to every inspection from its former selection value.

    Runs after the catalog data is loaded. Only touches inspections without a type, so a
    second run changes nothing. Raising here rolls back the whole module update.
    """
    if not version or not sql.column_exists(cr, "fleet_inspection", "vehicle_type_legacy"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    vehicle_types = env["fleet.inspection.vehicle.type"].with_context(active_test=False)

    # Values that are not in the catalog get their own type, so no information is lost
    cr.execute("""
        SELECT DISTINCT vehicle_type_legacy
          FROM fleet_inspection
         WHERE vehicle_type_id IS NULL AND vehicle_type_legacy IS NOT NULL
    """)
    legacy_codes = {code for (code,) in cr.fetchall()}
    known_codes = set(vehicle_types.search([]).mapped("code"))
    for code in sorted(legacy_codes - known_codes):
        vehicle_types.create({"name": code, "code": code})
        _logger.warning("fleet_inspection: unknown vehicle type %r added to the catalog", code)
    env.flush_all()

    # Inspections without a former value become "other"
    cr.execute("""
        UPDATE fleet_inspection i
           SET vehicle_type_id = t.id
          FROM fleet_inspection_vehicle_type t
         WHERE i.vehicle_type_id IS NULL
           AND t.code = COALESCE(i.vehicle_type_legacy, 'other')
    """)
    _logger.info("fleet_inspection: %s inspections moved to the vehicle type catalog", cr.rowcount)

    cr.execute("SELECT count(*) FROM fleet_inspection WHERE vehicle_type_id IS NULL")
    (missing,) = cr.fetchone()
    if missing:
        raise RuntimeError(f"fleet_inspection: {missing} inspections still have no vehicle type")

    cr.execute("""
        SELECT t.code, count(*)
          FROM fleet_inspection i
          JOIN fleet_inspection_vehicle_type t ON t.id = i.vehicle_type_id
         GROUP BY t.code
         ORDER BY t.code
    """)
    _logger.info("fleet_inspection: inspections per vehicle type: %s", dict(cr.fetchall()))
