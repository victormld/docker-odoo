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
            ("in_process", "In Process"),
            ("paid", "Paid"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
        # Set by hand up to approved or rejected; once paid, it follows the accounting payment
        compute="_compute_state",
        store=True,
        readonly=False,
    )
    approval_level_id = fields.Many2one("payment.approval.level", readonly=True, copy=False)
    approver_id = fields.Many2one("res.users", string="Approver", readonly=True, copy=False, tracking=True)
    approval_date = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(readonly=True, copy=False)
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True, copy=False, tracking=True)
    # Related fields are read as superuser: the requester sees the payment data without accounting rights
    payment_reference = fields.Char(related="payment_id.name", string="Payment Reference")
    payment_date = fields.Date(related="payment_id.date", string="Payment Date")
    payment_journal = fields.Char(related="payment_id.journal_id.name", string="Paid From")
    payment_state = fields.Selection(related="payment_id.state", string="Payment Status")

    @api.depends("payment_id.state")
    def _compute_state(self):
        """Treasury registers the payment: in process. Accounting confirms it: paid.

        The payment reaches paid when accounting reconciles it (with the supplier bill in
        Community), and that is a recomputation, not a write: the dependency catches it.
        Without a payment, the status stays as the flow left it.
        """
        for request in self.filtered("payment_id"):
            request.state = "paid" if request.payment_id.state == "paid" else "in_process"

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

    def _check_approval_rights(self):
        self._check_group("payment_request.group_payment_request_approver",
                          _("Only approvers can approve or reject payment requests."))
        self._check_state("submitted")
        for request in self:
            if request.approver_id != self.env.user:
                raise AccessError(_("Only %(approver)s can approve or reject payment request %(request)s.",
                                    approver=request.approver_id.name, request=request.name))

    def _find_approval_level(self):
        """Level that applies to the amount, converted to the company currency.

        Nobody approves their own request: if the level's approver is the requester,
        the next level up takes the request.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        amount = self.currency_id._convert(self.amount, company_currency, self.company_id, self.date)
        levels = self.env["payment.approval.level"].search([("company_id", "=", self.company_id.id)])
        applicable = levels.filtered(lambda level: company_currency.compare_amounts(level.min_amount, amount) <= 0)
        if not applicable:
            raise UserError(_("No approval level applies to payment request %s. "
                              "Ask your administrator to configure the approval levels.", self.name))
        candidates = levels.filtered(lambda level: level.min_amount >= applicable[-1].min_amount)
        level = next((level for level in candidates if level.approver_id != self.requester_id), None)
        if not level:
            raise UserError(_("Payment request %s has no approver other than its requester. "
                              "Ask your administrator to configure the approval levels.", self.name))
        return level

    def _close_approval_activity(self):
        for request in self:
            request.activity_feedback(["mail.mail_activity_data_todo"], user_id=request.approver_id.id)

    # -- actions

    def action_submit(self):
        self._check_state("draft")
        for request in self:
            if request.requester_id != self.env.user:
                raise AccessError(_("Only the requester can submit payment request %s.", request.name))
            level = request._find_approval_level()
            request.write({"state": "submitted", "approval_level_id": level.id, "approver_id": level.approver_id.id})
            # Explicit, not left to the automatic subscription: the requester must hear about the decision
            request.message_subscribe(partner_ids=request.requester_id.partner_id.ids)
            # The activity is what the approver sees pending, in their own language
            request.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=level.approver_id.id,
                summary=request.with_context(lang=level.approver_id.lang).env._(
                    "Approve or reject payment request %s", request.name),
            )

    def action_approve(self):
        self._check_approval_rights()
        self.write({"state": "approved", "approval_date": fields.Datetime.now()})
        self._close_approval_activity()

    def action_reject(self):
        self._check_approval_rights()
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reject Payment Request"),
            "res_model": "payment.request.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def _reject(self, reason):
        self._check_approval_rights()
        if not (reason or "").strip():
            raise UserError(_("Explain why the payment request is rejected: the requester needs to know."))
        self.write({"state": "rejected", "rejection_reason": reason})
        for request in self:
            # A comment, not a note: it notifies the followers, starting with the requester
            request.message_post(body=_("Payment request rejected. Reason: %s", reason),
                                 subtype_xmlid="mail.mt_comment")
        self._close_approval_activity()

    def _check_payment_rights(self):
        self._check_group("payment_request.group_payment_request_treasury",
                          _("Only treasury can pay payment requests."))
        # Checking the status also prevents paying the same request twice
        self._check_state("approved")

    def action_open_payment_wizard(self):
        self._check_payment_rights()
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pay Payment Request"),
            "res_model": "payment.request.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def _pay(self, journal, payment_date):
        """Register the supplier payment in accounting and link it to the request."""
        self.ensure_one()
        self._check_payment_rights()
        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.partner_id.id,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "journal_id": journal.id,
            "date": payment_date,
            "memo": self.name,
            "payment_request_id": self.id,
        })
        payment.action_post()
        # The status follows the payment: in process, or paid if the journal posts straight to the bank
        self.payment_id = payment
        return payment

    def _release_payment(self, reason):
        """The payment was cancelled, rejected or deleted in accounting: treasury has to pay again."""
        self.ensure_one()
        self.write({"state": "approved", "payment_id": False})
        self.message_post(body=_("%s The request is approved again so treasury can pay it.", reason),
                          subtype_xmlid="mail.mt_note")

    def action_view_payment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "res_id": self.payment_id.id,
            "view_mode": "form",
        }
