import psycopg2

from odoo.exceptions import AccessError
from odoo.modules.migration import load_script
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from odoo.tools.sql import column_exists

MIGRATION_DIR = "fleet_inspection/migrations/18.0.2.0.0"


@tagged("post_install", "-at_install")
class TestVehicleType(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Test Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Test Model", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "license_plate": "AB123CD"})
        cls.inspector = cls.env["res.users"].create({
            "name": "Test Inspector",
            "login": "vehicle_type_inspector_test",
            "groups_id": [(6, 0, [cls.env.ref("fleet_inspection.group_fleet_inspection_user").id])],
        })
        cls.types = {
            code: cls.env.ref(f"fleet_inspection.vehicle_type_{code}")
            for code in ("motorcycle", "car", "truck", "other")
        }

    def _new_inspection(self, **vals):
        return self.env["fleet.inspection"].create({"vehicle_id": self.vehicle.id, **vals})

    def _load_migration(self, name):
        logger_name = f"fleet_inspection_{name.replace('-', '_')}"
        return load_script(f"{MIGRATION_DIR}/{name}.py", logger_name), logger_name

    # -- catalog ---------------------------------------------------------------

    def test_default_vehicle_type_is_car(self):
        self.assertEqual(self._new_inspection().vehicle_type_id, self.types["car"])

    def test_inspector_cannot_create_vehicle_types(self):
        with self.assertRaises(AccessError):
            self.env["fleet.inspection.vehicle.type"].with_user(self.inspector).create(
                {"name": "Bus", "code": "bus"})

    @mute_logger("odoo.sql_db")
    def test_vehicle_type_in_use_cannot_be_deleted(self):
        self._new_inspection(vehicle_type_id=self.types["truck"].id)
        with self.assertRaises(psycopg2.IntegrityError), self.cr.savepoint():
            self.types["truck"].unlink()

    @mute_logger("odoo.sql_db")
    def test_vehicle_type_code_is_unique(self):
        with self.assertRaises(psycopg2.IntegrityError), self.cr.savepoint():
            self.env["fleet.inspection.vehicle.type"].create({"name": "Another car", "code": "car"})
            self.env.flush_all()

    # -- migration from the former selection field -----------------------------
    # Each test rebuilds the table as it was before the update, inside the test
    # transaction: the schema changes are rolled back when the test ends.

    def test_pre_migrate_keeps_legacy_values(self):
        cr = self.env.cr
        inspection = self._new_inspection()
        self.env.flush_all()
        # Table of version 18.0.1: required vehicle_type, no vehicle_type_id yet
        cr.execute("ALTER TABLE fleet_inspection ADD COLUMN vehicle_type varchar")
        cr.execute("UPDATE fleet_inspection SET vehicle_type = 'truck'")
        cr.execute("ALTER TABLE fleet_inspection ALTER COLUMN vehicle_type SET NOT NULL")
        cr.execute("ALTER TABLE fleet_inspection DROP COLUMN vehicle_type_id")

        pre_migrate, _logger_name = self._load_migration("pre-migrate")
        for _run in range(2):  # the second run must change nothing
            pre_migrate.migrate(cr, "18.0.1.0.0")
            self.assertFalse(column_exists(cr, "fleet_inspection", "vehicle_type"))
            cr.execute("SELECT vehicle_type_legacy, vehicle_type_id FROM fleet_inspection WHERE id = %s",
                       [inspection.id])
            self.assertEqual(cr.fetchone(), ("truck", None))

        # The legacy column no longer blocks new inspections
        self.env.invalidate_all()
        self._new_inspection()
        self.env.flush_all()

    def test_post_migrate_maps_legacy_values(self):
        cr = self.env.cr
        legacy_values = ["motorcycle", "car", "truck", "other", "bus", None]
        inspections = self.env["fleet.inspection"].concat(*(self._new_inspection() for _value in legacy_values))
        self.env.flush_all()
        # Table right after the pre-migration: legacy values kept, no catalog type yet
        cr.execute("ALTER TABLE fleet_inspection ADD COLUMN vehicle_type_legacy varchar")
        cr.execute("ALTER TABLE fleet_inspection ALTER COLUMN vehicle_type_id DROP NOT NULL")
        for inspection, value in zip(inspections, legacy_values):
            cr.execute("UPDATE fleet_inspection SET vehicle_type_legacy = %s, vehicle_type_id = NULL WHERE id = %s",
                       [value, inspection.id])
        self.env.invalidate_all()

        post_migrate, logger_name = self._load_migration("post-migrate")
        with self.assertLogs(logger_name, level="WARNING") as logs:
            post_migrate.migrate(cr, "18.0.1.0.0")
        self.assertIn("'bus'", logs.output[0])
        post_migrate.migrate(cr, "18.0.1.0.0")  # the second run must change nothing
        self.env.invalidate_all()

        bus = self.env["fleet.inspection.vehicle.type"].search([("code", "=", "bus")])
        self.assertEqual(len(bus), 1, "An unknown value gets exactly one catalog type")
        self.assertEqual(
            [inspection.vehicle_type_id for inspection in inspections],
            [self.types["motorcycle"], self.types["car"], self.types["truck"], self.types["other"],
             bus, self.types["other"]],
        )
