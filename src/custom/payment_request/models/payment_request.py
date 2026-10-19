from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

# Business data the requester fills in: frozen once the request is submitted
LOCKED_FIELDS = {"partner_id", "requester_id", "amount", "currency_id", "concept", "date", "company_id"}


class PaymentRequest(models.Model):
    _name = "payment.request"
    _description = "Payment Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Number", required=True, copy=False, readonly=True, default="/")
    partner_id = fields.Many2one("res.partner", string="Supplier", required=True, index=True, tracking=True)
    requester_id = fields.Many2one(
        "res.users",
        string="Requested by",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    amount = fields.Monetary(required=True, tracking=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    concept = fields.Text(required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("paid", "Paid"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )

    @api.constrains("amount")
    def _check_amount(self):
        for request in self:
            if request.currency_id.compare_amounts(request.amount, 0.0) <= 0:
                raise ValidationError(_("The amount must be greater than zero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("payment.request") or "/"
        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_FIELDS.intersection(vals) and any(request.state != "draft" for request in self):
            raise UserError(_("A payment request cannot be modified once it has been submitted."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(request.state != "draft" for request in self):
            raise UserError(_("Only draft payment requests can be deleted."))

    # -- checks shared by the actions: they also apply when a method is called directly

    def _check_state(self, state):
        wrong = self.filtered(lambda request: request.state != state)
        if wrong:
            raise UserError(_("This action is not available for %s in its current status.",
                              ", ".join(wrong.mapped("name"))))

    def _check_group(self, group_xmlid, message):
        if not self.env.user.has_group(group_xmlid):
            raise AccessError(message)

    # -- actions

    def action_submit(self):
        self._check_state("draft")
        for request in self:
            if request.requester_id != self.env.user:
                raise AccessError(_("Only the requester can submit payment request %s.", request.name))
        self.write({"state": "submitted"})

    def action_approve(self):
        self._check_group("payment_request.group_payment_request_approver",
                          _("Only approvers can approve payment requests."))
        self._check_state("submitted")
        for request in self:
            if request.requester_id == self.env.user:
                raise AccessError(_("You cannot approve your own payment request %s.", request.name))
        self.write({"state": "approved"})

    def action_reject(self):
        self._check_group("payment_request.group_payment_request_approver",
                          _("Only approvers can reject payment requests."))
        self._check_state("submitted")
        self.write({"state": "rejected"})

    def action_mark_paid(self):
        self._check_group("payment_request.group_payment_request_treasury",
                          _("Only treasury can pay payment requests."))
        self._check_state("approved")
        self.write({"state": "paid"})
