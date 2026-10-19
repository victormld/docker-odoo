from odoo import fields, models


class PaymentRequestRejectWizard(models.TransientModel):
    _name = "payment.request.reject.wizard"
    _description = "Reject Payment Request"

    request_id = fields.Many2one("payment.request", required=True, readonly=True)
    reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.request_id._reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
