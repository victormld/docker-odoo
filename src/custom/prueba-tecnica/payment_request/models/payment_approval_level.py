from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PaymentApprovalLevel(models.Model):
    _name = "payment.approval.level"
    _description = "Payment Approval Level"
    _order = "company_id, min_amount, id"

    name = fields.Char(required=True, translate=True)
    min_amount = fields.Monetary(
        string="Minimum Amount",
        currency_field="currency_id",
        help="Requests whose amount, converted to the company currency, reaches this value use this level.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    approver_id = fields.Many2one(
        "res.users",
        string="Approver",
        required=True,
        domain=lambda self: [("groups_id", "in", self.env.ref("payment_request.group_payment_request_approver").ids)],
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    @api.constrains("min_amount")
    def _check_min_amount(self):
        for level in self:
            if level.currency_id.compare_amounts(level.min_amount, 0.0) < 0:
                raise ValidationError(_("The minimum amount of an approval level cannot be negative."))

    @api.constrains("approver_id")
    def _check_approver(self):
        for level in self:
            if not level.approver_id.has_group("payment_request.group_payment_request_approver"):
                raise ValidationError(_("%s is not an approver of payment requests.", level.approver_id.name))
