import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSpanishTranslation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_VE")
        cls.env["ir.module.module"]._load_module_terms(["fleet_inspection"], ["es_VE"], overwrite=True)
        cls.env = cls.env(context=dict(cls.env.context, lang="es_VE"))
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Test Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Test Model", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "license_plate": "AB123CD"})

    def test_labels_and_data_in_spanish(self):
        field_info = self.env["fleet.inspection"].fields_get(["vehicle_type_id", "state"], ["string", "selection"])
        self.assertEqual(field_info["vehicle_type_id"]["string"], "Tipo de vehículo")
        self.assertEqual(dict(field_info["state"]["selection"])["draft"], "Borrador")
        self.assertEqual(self.env.ref("fleet_inspection.vehicle_type_car").name, "Carro")
        self.assertEqual(self.env.ref("fleet_inspection.item_brakes").name, "Frenos")
        self.assertEqual(self.env.ref("fleet_inspection.action_report_fleet_inspection").print_report_name,
                         "'Inspección - %s' % object.name")
        # Not in Odoo's export: added by hand to the template and to es.po
        self.assertEqual(self.env.ref("base.module_fleet_inspection").shortdesc, "Inspecciones de vehículos")

    def test_messages_in_spanish_keep_their_variable(self):
        inspection = self.env["fleet.inspection"].create({"vehicle_id": self.vehicle.id})
        inspection.action_start()
        expected = f"Faltan puntos por revisar en la inspección {inspection.name}."
        with self.assertRaisesRegex(UserError, f"^{re.escape(expected)}$"):
            inspection.action_approve()
        with self.assertRaisesRegex(UserError, r"^Solo se pueden eliminar inspecciones en borrador\.$"):
            inspection.unlink()

    def test_overdue_activity_in_inspector_language(self):
        inspector = self.env["res.users"].create({
            "name": "Spanish Inspector",
            "login": "spanish_inspector_test",
            "lang": "es_VE",
            "groups_id": [(6, 0, [self.env.ref("fleet_inspection.group_fleet_inspection_user").id])],
        })
        inspection = self.env["fleet.inspection"].with_context(lang="en_US").create({
            "vehicle_id": self.vehicle.id,
            "inspector_id": inspector.id,
            "date": fields.Date.today() - timedelta(days=10),
        })
        inspection.action_start()
        # The cron runs in English; the activity must follow the inspector's language
        inspection.with_context(lang="en_US")._cron_mark_overdue()
        self.assertEqual(inspection.activity_ids.summary, "Inspección en curso desde hace más de 7 días")
