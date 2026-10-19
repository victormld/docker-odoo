from odoo import fields, models


class FleetInspectionVehicleType(models.Model):
    _name = "fleet.inspection.vehicle.type"
    _description = "Tipo de vehículo para inspecciones"
    _order = "sequence, id"

    name = fields.Char(string="Nombre", required=True)
    code = fields.Char(
        string="Código",
        required=True,
        help="Clave técnica estable. La usa la migración desde el antiguo campo de selección.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Ya existe un tipo de vehículo con ese código."),
    ]
