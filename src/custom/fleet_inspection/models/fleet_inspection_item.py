from odoo import fields, models


class FleetInspectionItem(models.Model):
    _name = "fleet.inspection.item"
    _description = "Inspection Checklist Point"
    _order = "sequence, id"

    name = fields.Char(string="Point to Check", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    critical = fields.Boolean(
        string="Critical",
        help="If a critical point fails, the inspection cannot be approved.",
    )
