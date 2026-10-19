from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

VEHICLE_TYPES = [
    ("motorcycle", "Motorcycle"),
    ("car", "Car"),
    ("truck", "Truck"),
    ("other", "Other"),
]


class FleetInspection(models.Model):
    _name = "fleet.inspection"
    _description = "Vehicle Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Number", required=True, copy=False, readonly=True, default="/")
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        tracking=True,
    )
    vehicle_type = fields.Selection(
        VEHICLE_TYPES,
        string="Vehicle Type",
        required=True,
        default="car",
        tracking=True,
    )
    inspector_id = fields.Many2one(
        "res.users",
        string="Inspector",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    date = fields.Date(
        string="Date", required=True, default=fields.Date.context_today, tracking=True
    )
    odometer = fields.Float(string="Odometer")
    line_ids = fields.One2many(
        "fleet.inspection.line", "inspection_id", string="Checklist", copy=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    notes = fields.Text(string="Notes")
    failed_count = fields.Integer(string="Failed Points", compute="_compute_counts", store=True)
    pending_count = fields.Integer(string="Pending Points", compute="_compute_counts", store=True)
    is_overdue = fields.Boolean(string="Overdue", readonly=True, copy=False)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "The inspection number must be unique."),
    ]

    @api.depends("line_ids.result")
    def _compute_counts(self):
        for inspection in self:
            inspection.failed_count = len(inspection.line_ids.filtered(lambda l: l.result == "fail"))
            inspection.pending_count = len(inspection.line_ids.filtered(lambda l: not l.result))

    @api.constrains("odometer")
    def _check_odometer(self):
        for inspection in self:
            if inspection.odometer < 0:
                raise ValidationError(_("The odometer cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        items = self.env["fleet.inspection.item"].search([])
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("fleet.inspection") or "/"
            if not vals.get("line_ids"):
                vals["line_ids"] = [Command.create({"item_id": item.id}) for item in items]
        return super().create(vals_list)

    @api.depends("name", "vehicle_id.license_plate", "vehicle_id.name")
    def _compute_display_name(self):
        for inspection in self:
            vehicle = inspection.vehicle_id
            inspection.display_name = (
                f"{inspection.name} - {vehicle.license_plate or vehicle.name}" if vehicle else inspection.name
            )

    def action_start(self):
        for inspection in self:
            if not inspection.line_ids:
                raise UserError(_("Inspection %s has no checklist points.", inspection.name))
        self.write({"state": "in_progress"})

    def action_approve(self):
        for inspection in self:
            if inspection.pending_count:
                raise UserError(_("Inspection %s still has unchecked points.", inspection.name))
            critical_failed = inspection.line_ids.filtered(lambda l: l.result == "fail" and l.item_id.critical)
            if critical_failed:
                raise UserError(
                    _("Cannot approve: critical points failed (%s).",
                      ", ".join(critical_failed.mapped("item_id.name")))
                )
        self.write({"state": "approved", "is_overdue": False})

    def action_reject(self):
        self.write({"state": "rejected", "is_overdue": False})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def unlink(self):
        if any(inspection.state != "draft" for inspection in self):
            raise UserError(_("Only draft inspections can be deleted."))
        return super(FleetInspection, self).unlink()

    @api.model
    def _cron_mark_overdue(self, days=7):
        limit_date = fields.Date.context_today(self) - timedelta(days=days)
        overdue = self.search([("state", "=", "in_progress"), ("date", "<", limit_date), ("is_overdue", "=", False)])
        overdue.write({"is_overdue": True})
        for inspection in overdue:
            inspection.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=inspection.inspector_id.id,
                summary=inspection.with_context(lang=inspection.inspector_id.lang).env._(
                    "Inspection in progress for more than %s days", days),
            )
        return True
