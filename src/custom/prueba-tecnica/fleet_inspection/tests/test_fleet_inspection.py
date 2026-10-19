from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFleetInspection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Marca de prueba"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Modelo de prueba", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "license_plate": "AB123CD"})
        cls.inspector = cls.env["res.users"].create({
            "name": "Inspector de prueba",
            "login": "inspector_test",
            "groups_id": [(6, 0, [cls.env.ref("fleet_inspection.group_fleet_inspection_user").id])],
        })
        cls.other_inspector = cls.env["res.users"].create({
            "name": "Otro inspector",
            "login": "other_inspector_test",
            "groups_id": [(6, 0, [cls.env.ref("fleet_inspection.group_fleet_inspection_user").id])],
        })
        cls.supervisor = cls.env["res.users"].create({
            "name": "Test Supervisor",
            "login": "supervisor_test",
            "groups_id": [(6, 0, [cls.env.ref("fleet_inspection.group_fleet_inspection_manager").id])],
        })

    def _new_inspection(self, **vals):
        values = {
            "vehicle_id": self.vehicle.id,
            "vehicle_type_id": self.env.ref("fleet_inspection.vehicle_type_truck").id,
            "inspector_id": self.inspector.id,
        }
        values.update(vals)
        return self.env["fleet.inspection"].create(values)

    def test_create_loads_checklist_and_sequence(self):
        inspection = self._new_inspection()
        self.assertTrue(inspection.name.startswith("INS/"))
        items = self.env["fleet.inspection.item"].search([])
        self.assertEqual(inspection.line_ids.mapped("item_id"), items)

    def test_display_name_includes_plate(self):
        # Odoo 18 no longer calls name_get: the visible name comes from display_name
        inspection = self._new_inspection()
        self.assertEqual(inspection.display_name, f"{inspection.name} - AB123CD")
        no_plate = self.env["fleet.vehicle"].create({"model_id": self.vehicle.model_id.id})
        inspection.vehicle_id = no_plate
        self.assertEqual(inspection.display_name, f"{inspection.name} - {no_plate.name}")

    def test_full_flow_approved(self):
        inspection = self._new_inspection()
        inspection.action_start()
        self.assertEqual(inspection.state, "in_progress")
        with self.assertRaises(UserError):
            inspection.action_approve()
        inspection.line_ids.write({"result": "ok"})
        inspection.action_approve()
        self.assertEqual(inspection.state, "approved")

    def test_critical_failure_blocks_approval(self):
        inspection = self._new_inspection()
        inspection.action_start()
        inspection.line_ids.write({"result": "ok"})
        brakes = inspection.line_ids.filtered(lambda l: l.item_id == self.env.ref("fleet_inspection.item_brakes"))
        brakes.result = "fail"
        self.assertEqual(inspection.failed_count, 1)
        with self.assertRaises(UserError):
            inspection.action_approve()
        inspection.action_reject()
        self.assertEqual(inspection.state, "rejected")

    def test_negative_odometer(self):
        with self.assertRaises(ValidationError):
            self._new_inspection(odometer=-10)

    def test_inspector_sees_only_own(self):
        own = self._new_inspection()
        other = self._new_inspection(inspector_id=self.other_inspector.id)
        visible = self.env["fleet.inspection"].with_user(self.inspector).search([])
        self.assertIn(own, visible)
        self.assertNotIn(other, visible)

    def test_inspector_cannot_delete(self):
        inspection = self._new_inspection()
        with self.assertRaises(AccessError):
            inspection.with_user(self.inspector).unlink()

    def test_form_default_inspector(self):
        form = Form(self.env["fleet.inspection"].with_user(self.inspector))
        form.vehicle_id = self.vehicle
        inspection = form.save()
        self.assertEqual(inspection.inspector_id, self.inspector)
        self.assertEqual(inspection.vehicle_type_id, self.env.ref("fleet_inspection.vehicle_type_car"))

    def test_cron_marks_overdue_once(self):
        inspection = self._new_inspection(date=fields.Date.today() - timedelta(days=10))
        inspection.action_start()
        self.env["fleet.inspection"]._cron_mark_overdue()
        self.env["fleet.inspection"]._cron_mark_overdue()
        self.assertTrue(inspection.is_overdue)
        self.assertEqual(len(inspection.activity_ids), 1)

    def test_fields_editable_by_state(self):
        inspection = self._new_inspection()
        with Form(inspection) as form:
            form.vehicle_id = self.vehicle
            form.date = fields.Date.today()
        inspection.action_start()
        form = Form(inspection)
        for field_name in ("vehicle_id", "vehicle_type_id", "date"):
            with self.subTest(field=field_name), self.assertRaises(AssertionError):
                setattr(form, field_name, inspection[field_name])
        form.odometer = 1500
        form.save()
        inspection.line_ids.write({"result": "ok"})
        inspection.action_approve()
        with self.assertRaises(AssertionError):
            Form(inspection).odometer = 2000

    def test_start_requires_checklist(self):
        inspection = self._new_inspection()
        inspection.line_ids.unlink()
        with self.assertRaises(UserError):
            inspection.action_start()
        self.assertEqual(inspection.state, "draft")

    def test_reset_rejected_to_draft(self):
        inspection = self._new_inspection()
        inspection.action_start()
        inspection.action_reject()
        inspection.action_reset_draft()
        self.assertEqual(inspection.state, "draft")

    def test_only_drafts_can_be_deleted(self):
        started = self._new_inspection()
        started.action_start()
        with self.assertRaises(UserError):
            started.with_user(self.supervisor).unlink()
        draft = self._new_inspection()
        draft.with_user(self.supervisor).unlink()
        self.assertFalse(draft.exists())

    def test_report_renders(self):
        inspection = self._new_inspection()
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "fleet_inspection.action_report_fleet_inspection", inspection.ids)
        html = html.decode()
        for expected in (inspection.name, "AB123CD", inspection.vehicle_type_id.name):
            self.assertIn(expected, html)
