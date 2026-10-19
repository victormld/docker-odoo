from odoo import fields, models


class PaymentRequestPaymentWizard(models.TransientModel):
    _name = "payment.request.payment.wizard"
    _description = "Pay Payment Request"

    request_id = fields.Many2one("payment.request", required=True, readonly=True)
    company_id = fields.Many2one(related="request_id.company_id")
    partner_id = fields.Many2one(related="request_id.partner_id")
    amount = fields.Monetary(related="request_id.amount")
    currency_id = fields.Many2one(related="request_id.currency_id")
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        default=lambda self: self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1),
    )
    payment_date = fields.Date(required=True, default=fields.Date.context_today)

    def action_pay(self):
        self.ensure_one()
        self.request_id._pay(self.journal_id, self.payment_date)
        return {"type": "ir.actions.act_window_close"}
