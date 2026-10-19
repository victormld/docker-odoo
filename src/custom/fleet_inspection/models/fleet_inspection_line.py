from odoo import fields, models


class FleetInspectionLine(models.Model):
    _name = "fleet.inspection.line"
    _description = "Inspection Checklist Line"
    _order = "sequence, id"

    inspection_id = fields.Many2one("fleet.inspection", required=True, ondelete="cascade")
    item_id = fields.Many2one("fleet.inspection.item", string="Point", required=True)
    sequence = fields.Integer(related="item_id.sequence", store=True)
    critical = fields.Boolean(related="item_id.critical")
    result = fields.Selection(
        [("ok", "OK"), ("fail", "Failed"), ("na", "N/A")],
        string="Result",
    )
    comment = fields.Char(string="Comment")
    state = fields.Selection(related="inspection_id.state")
