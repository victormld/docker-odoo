from odoo import fields, models


class FleetInspectionVehicleType(models.Model):
    _name = "fleet.inspection.vehicle.type"
    _description = "Inspection Vehicle Type"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        help="Stable technical key. Used by the migration from the former selection field.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "A vehicle type with this code already exists."),
    ]
